import json
import hashlib
from pathlib import Path

from src.utils.helpers import Settings, Props
from src.logic.data_loader import DataLoader
from src.logic.optimizer import CoefficientCalculator, ILPSolver

TIERS = [1, 2, 3, 4]
SLOT_MIN, SLOT_MAX = 1, 25
MAX_COPY_MIN, MAX_COPY_MAX = 1, 5
BLACKLISTS = [
    ["Душа", "Пустышка"],
    ["Пустышка"]
]

PROPS_DIR = Path(__file__).parents[2] / 'props'
OUTPUT_DIR = Path(__file__).parents[2] / 'data' / 'achievable_maxima'


def compute_hash(tier: int, slots: int, max_copy: int, blacklist: list[str], props_data: dict) -> str:
    payload = {
        'tier': tier,
        'slots': slots,
        'max_copy': max_copy,
        'blacklist': blacklist,
        'props': [
            {
                'name': name,
                'low': meta.get('low'),
                'high': meta.get('high')
            }
            for name, meta in sorted(props_data.items(), key=lambda x: x[0])
        ]
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def compute_achievable_maxima(settings: Settings) -> tuple[dict, dict]:
    props = Props.load(
        PROPS_DIR / f'props_tier{settings.tier}.yaml',
        settings.num_slots
    )

    df = DataLoader(settings).load()
    calc = CoefficientCalculator(props, df)
    calc.compute()

    solver = ILPSolver(df, calc.coef, props.data, settings)

    maxima: dict[str, float] = {}
    for prop_name in props.data:
        maxima[prop_name] = solver._get_achievable_max(prop_name)
    return props.data, maxima


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for tier in TIERS:
        print(f"[ИНФО] Обрабатываем тир {tier}...")
        results: dict[str, dict] = {}
        for slots in range(SLOT_MIN, SLOT_MAX + 1):
            for max_copy in range(MAX_COPY_MIN, MAX_COPY_MAX + 1):
                for blacklist in BLACKLISTS:
                    print(f"[ИНФО] Считаем для слотов: {slots}, максимум копий: {max_copy}, исключения: {blacklist}")
                    settings = Settings()
                    settings.tier = tier
                    settings.num_slots = slots
                    settings.max_copy = max_copy
                    settings.blacklist = blacklist

                    props_data, maxima = compute_achievable_maxima(settings)
                    hsh = compute_hash(tier, slots, max_copy, blacklist, props_data)

                    key = f"slots_{slots}_maxcopy_{max_copy}_blacklist_{'_'.join(blacklist)}"
                    results[key] = {
                        'hash': hsh,
                        'maxima': maxima
                    }

                    print(f"[ГОТОВО] Хэш рассчитан: {hsh} для ключа: {key}")

        out_file = OUTPUT_DIR / f'achievable_tier{tier}.json'
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"[ФАЙЛ] Результаты сохранены в: {out_file.resolve()}")


if __name__ == '__main__':
    main()
