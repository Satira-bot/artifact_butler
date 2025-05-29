import argparse
import time
from pathlib import Path
from typing import List

import pulp as pl
import pandas as pd

from src.utils.constants import DEFAULT_DATA_FILE, PROPS_DIR
from src.utils.helpers import Settings, Props
from src.logic.data_loader import DataLoader
from src.logic.optimizer import CoefficientCalculator, ILPSolver

TIER: int = 3
NUM_SLOTS: int = 19
MAX_COPY: int = 3
IGNORE_PROPS: List[str] = ["food", "water"]
W_MIN, W_MAX, W_STEP = 1.0, 5.0, 0.1
EPSILON: float = 1e-6
N_ALT: int = 250
JITTER: float = 0.8

DEFAULT_BUILD: list[tuple[str, int, int]] = [
    ("Батарейка", 3, 1),
    ("Выверт", 3, 3),
    ("Грави", 3, 3),
    ("Кристалл", 3, 2),
    ("Лунный свет", 3, 1),
    ("Маяк", 3, 3),
    ("Ночная звезда", 3, 3),
    ("Пузырь", 3, 1),
    ("Снежинка", 3, 3),
    ("Череп скряги", 3, 1),
]


def load_build(path: Path | None) -> list[tuple[str, int, int]]:
    if path is None:
        return DEFAULT_BUILD

    build: list[tuple[str, int, int]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            name, tier, cnt = line.strip().split("\t")
            build.append((name, int(tier), int(cnt)))
    return build


def build_vector(build: list[tuple[str, int, int]], coef: dict[str, list[float]], df: pd.DataFrame, props: Props) -> \
        list[float]:
    """Преобразует сборку в вектор значений свойств."""
    res = [0.0] * len(props.data)
    prop_idx = {p: i for i, p in enumerate(props.data)}
    for name, tier, cnt in build:
        row = df[(df["Имя"] == name) & (df["Тир"] == tier)].iloc[0]
        idx = row.name
        for p, vec in coef.items():
            res[prop_idx[p]] += vec[idx] * cnt
    return res


def generate_alternatives(solver: ILPSolver, df: pd.DataFrame) -> list[list[tuple[str, int, int]]]:
    """Генерирует N_ALT альтернатив с помощью solve_once."""
    alts: list[list[tuple[str, int, int]]] = []
    seen: set[tuple[tuple[str, int, int], ...]] = set()

    for _ in range(N_ALT * 3):  # потолок попыток
        alt, *_ = solver.solve_once(jitter=JITTER)
        if not alt:
            continue
        key = tuple(sorted(alt))
        if key in seen:
            continue
        seen.add(key)
        alts.append(alt)
        if len(alts) >= N_ALT:
            break
    return alts


def build_ilp(weights_vars: dict[str, pl.LpVariable], ref_v: list[float], alt_vs: list[list[float]],
              props: Props) -> pl.LpProblem:
    """Собирает MILP для подбора весов."""
    prob = pl.LpProblem("InverseWeights", pl.LpMinimize)

    prob += pl.lpSum(weights_vars.values())

    for v_alt in alt_vs:
        lhs = pl.lpSum(weights_vars[p] * ref_v[i] for i, p in enumerate(props.data) if p not in IGNORE_PROPS)
        rhs = pl.lpSum(weights_vars[p] * v_alt[i] for i, p in enumerate(props.data) if p not in IGNORE_PROPS)
        prob += lhs >= rhs + EPSILON

    return prob


def main():
    ap = argparse.ArgumentParser(description="Recover property weights so that a reference build is optimal.")
    ap.add_argument("--build", type=Path, default=None, help="TSV file with reference build (Имя,Тир,Кол-во)")
    args = ap.parse_args()

    settings = Settings(data_file=str(DEFAULT_DATA_FILE), tier=TIER, num_slots=NUM_SLOTS, max_copy=MAX_COPY)
    df = DataLoader(settings).load()

    props = Props.load(PROPS_DIR / f"props_tier{TIER}.yaml", NUM_SLOTS)
    calc = CoefficientCalculator(props, df)
    calc.compute()

    solver_tmp = ILPSolver(df, calc.coef, props.data, settings)
    achievable_max = {p: solver_tmp._get_achievable_max(p) for p in props.data}

    for p, meta in props.data.items():
        meta["low"] = 0
        meta["high"] = achievable_max[p]
        meta["use"] = True

    ref_build = load_build(args.build)
    ref_vec = build_vector(ref_build, calc.coef, df, props)

    solver_alt = ILPSolver(df, calc.coef, props.data, settings)
    alts = generate_alternatives(solver_alt, df)
    alt_vecs = [build_vector(b, calc.coef, df, props) for b in alts]

    weights_vars = {}
    for p in props.data:
        w = pl.LpVariable(f"w_{p}", lowBound=0, upBound=int(W_MAX / W_STEP), cat=pl.LpInteger)
        if p in IGNORE_PROPS:
            weights_vars[p] = 0 * w
        else:
            weights_vars[p] = w

    prob = build_ilp(weights_vars, ref_vec, alt_vecs, props)

    start = time.time()
    prob.solve(pl.PULP_CBC_CMD(msg=False, timeLimit=5))
    elapsed = time.time() - start

    status = pl.LpStatus[prob.status]
    print(f"\nСтатус: {status} в {elapsed:.2f}s  |  альтернатив проверено: {len(alts)}")

    if status != "Optimal":
        print("Все херня, давай по новой")
        return

    print("\n=== Восстановление весов (priority 1–5) ===")
    for p in props.data:
        if p in IGNORE_PROPS:
            print(f"{p:<20}: 0 (ignored)")
            continue
        w_val = weights_vars[p].value() * W_STEP
        print(f"{p:<20}: {w_val:.1f}")


if __name__ == "__main__":
    main()
