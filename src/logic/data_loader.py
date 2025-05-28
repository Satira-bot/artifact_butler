import json
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any

from src.utils.helpers import Settings


class DataLoader:
    """
    Загружает данные об артефактах из указанных источников.
    Поддерживаются два формата:
      • Excel (.xlsx) — старый формат данных.
      • JSON (data/artifacts_data.json) — новый предпочтительный формат.
    """

    def __init__(self, settings: Settings) -> None:
        self.set = settings
        self.file = Path(settings.data_file)

    def load(self) -> pd.DataFrame:
        """
        Загружает данные об артефактах в DataFrame.
        Источник выбирается автоматически по формату файла.
        """
        if self.file.suffix.lower() == ".json":
            return self._load_json()
        return self._load_excel()

    def _load_json(self) -> pd.DataFrame:
        """
        Загружает данные из JSON-формата и приводит их к табличному виду.
        Формирует таблицу с колонками:
          «Имя», «Тир», все свойства (отсутствующие заполняются нулями).
        """
        with self.file.open(encoding="utf-8") as f:
            data: Dict[str, Dict[str, Dict[str, Any]]] = json.load(f)

        rows: List[Dict[str, Any]] = []
        for art_name, tiers in data.items():
            for tier_str, props in tiers.items():
                rows.append({
                    "Имя": art_name,
                    "Тир": int(tier_str),
                    **props
                })

        df_all = pd.DataFrame(rows).fillna(0)

        return df_all.reset_index(drop=True)

    def _load_excel(self) -> pd.DataFrame:
        """
        Загружает данные из Excel (.xlsx).
        Используется как fallback для совместимости со старым форматом.
        """
        df = pd.read_excel(self.file, sheet_name=0).fillna(0)
        return df.reset_index(drop=True)

