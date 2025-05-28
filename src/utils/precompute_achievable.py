import json
import hashlib
import os

from concurrent.futures import ProcessPoolExecutor, as_completed

from src.utils.constants import ACHIEVABLE_DIR, PROPS_DIR, preset_map
from src.utils.helpers import Settings, Props
from src.logic.data_loader import DataLoader
from src.logic.optimizer import CoefficientCalculator, ILPSolver

TIERS = [1, 2, 3, 4]
SLOT_MIN, SLOT_MAX = 3, 25
MAX_COPY_MIN, MAX_COPY_MAX = 1, 5
BLACKLISTS = [
    ["Душа", "Пустышка"],
    ["Пустышка"],
]


def compute_hash(tier: int,
                 slots: int,
                 max_copy: int,
                 blacklist: list[str],
                 props_file: str,
                 props_data: dict,
                 ) -> str:
    payload = {
        "tier": tier,
        "slots": slots,
        "max_copy": max_copy,
        "blacklist": blacklist,
        "props_file": props_file,
        "props": [
            {"name": name, "low": meta.get("low"), "high": meta.get("high")}
            for name, meta in sorted(props_data.items(), key=lambda x: x[0])
        ],
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_achievable_extrema(settings: Settings) -> tuple[dict, dict]:
    """
    Загружаем props, строим DataFrame и вычисляем реальный максимум
    для каждого «используемого» и приоритетного свойства.
    """
    props = Props.load(PROPS_DIR / settings.props_file, settings.num_slots)
    df = DataLoader(settings).load()

    calc = CoefficientCalculator(props, df)
    calc.compute()

    solver = ILPSolver(df, calc.coef, props.data, settings)

    maxima: dict[str, float] = {}
    for p, meta in props.data.items():
        if not meta.get("use", False) or meta.get("priority", 0) <= 0:
            continue

        if hasattr(solver, "_achievable_max_cache"):
            solver._achievable_max_cache.clear()

        maxima[p] = solver._get_achievable_max(p)

    return props.data, maxima


def worker(args):
    tier, slots, max_copy, blacklist, props_file = args
    settings = Settings()
    settings.tier = tier
    settings.num_slots = slots
    settings.max_copy = max_copy
    settings.blacklist = blacklist
    settings.props_file = props_file

    props_data, maxima = compute_achievable_extrema(settings)
    hsh = compute_hash(tier, slots, max_copy, blacklist, props_file, props_data)
    key = (
        f"{props_file.replace('.yaml', '')}_"
        f"tier_{tier}_"
        f"slots_{slots}_"
        f"maxcopy_{max_copy}_"
        f"blacklist_{'_'.join(blacklist)}"
    )
    return key, {"hash": hsh, "maxima": maxima}


def main() -> None:
    ACHIEVABLE_DIR.mkdir(parents=True, exist_ok=True)

    combos = [
        (tier, slots, mc, bl, preset_cfg["props_file"])
        for preset_cfg in preset_map.values()
        for tier in TIERS
        for slots in range(SLOT_MIN, SLOT_MAX + 1)
        for mc in range(MAX_COPY_MIN, MAX_COPY_MAX + 1)
        for bl in BLACKLISTS
    ]
    total = len(combos)

    results: dict[str, dict] = {}
    workers = os.cpu_count() or 16

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for idx, args in enumerate(combos, start=1):
            tier, slots, max_copy, blacklist, props_file = args
            print(f"[SUBMIT] {idx}/{total} → tier={tier}, slots={slots}, max_copy={max_copy}, bl={blacklist}")
            fut = executor.submit(worker, args)
            futures[fut] = args

        print("[INFO] All tasks submitted, awaiting results...")

        done = 0
        for fut in as_completed(futures):
            done += 1
            tier, slots, max_copy, blacklist, props_file = futures[fut]
            try:
                key, res = fut.result()
                results[key] = res
                print(f"[DONE] {done}/{total} → key={key}, hash={res['hash']}")
            except Exception as e:
                print(f"[ERROR] Task tier={tier}, slots={slots}, max_copy={max_copy}, bl={blacklist} failed: {e}")

    for preset_name, preset_cfg in preset_map.items():
        props_file = preset_cfg["props_file"]
        stem = props_file.replace(".yaml", "")
        out_file = ACHIEVABLE_DIR / f"achievable_{props_file.replace('.yaml', '')}.json"
        filtered = {k: v for k, v in results.items() if stem in k}
        print(f"[WRITE] preset={preset_name}, props_file={props_file}, entries={len(filtered)} → {out_file.name}")
        with out_file.open("w", encoding="utf-8") as f:
            json.dump(filtered, f, ensure_ascii=False, indent=2)
        print(f"[FILE]  Saved {out_file.resolve()}")


if __name__ == "__main__":
    main()
