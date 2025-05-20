import pandas as pd
from io import BytesIO
from typing import Dict, List, Any

from src.utils.helpers import Settings
from src.utils.constants import build_label_alt, build_label_det


class ExcelExporter:
    """Создаёт и оформляет Excel-отчёты по результатам расчётов.

    Основные возможности:
      • Формирование сводной таблицы с результатами.
      • Запись данных в Excel с форматированием и автоссылками.
      • Поддержка экспорта прямо в память (как bytes).
    """

    def __init__(self, settings: Settings, stat_keys: List[str]) -> None:
        self.settings = settings
        self.stat_keys = stat_keys
        self.col_map = {
            "Type": "Тип",
            "Run": "Прогон",
            "Sheet": "Лист",
            "Score": "Счёт",
            "slots": "Слотов",
            "rad": "Радиация",
            "food": "Еда",
            "water": "Вода",
            "temp": "Температура",
            "jump": "Высота прыжка",
            "stamina": "Выносливость",
            "defence": "Защита от ударов",
            "anom_defence": "Защита от аномалий",
            "bullet_defence": "Защита от пуль",
            "blood": "Кровь",
            "resilience": "Стойкость",
            "health": "Здоровье",
            "cut_risk": "Лечение порезов",
            "break_risk": "Лечение переломов"
        }

    def _comparison_df(self,
                       best: Dict[str, Any],
                       alts: List[Dict[str, Any]]) -> pd.DataFrame:

        det_row: Dict[str, Any] = {
            "Type": f"{build_label_det}",
            "Run": None,
            "Sheet": f"{build_label_det}",
            "Score": best.get("score", 0.0),
        }
        for k in self.stat_keys:
            det_row[k] = best.get("stats", {}).get(k, 0.0)

        alt_rows: List[Dict[str, Any]] = []
        for idx, alt in enumerate(alts, 1):
            row: Dict[str, Any] = {
                "Type": f"{build_label_alt}",
                "Run": alt.get("run", idx),
                "Sheet": f"Альт {idx}",
                "Score": alt.get("score", 0.0),
            }
            for k in self.stat_keys:
                row[k] = alt.get(k, 0.0)
            alt_rows.append(row)

        rows = [det_row] + alt_rows
        df_all = pd.DataFrame(rows)

        mask_nonzero = ~(df_all[self.stat_keys] == 0).all(axis=1)
        df_filtered = df_all[mask_nonzero]

        cols = ["Type", "Run", "Sheet", "Score", *self.stat_keys]
        return df_filtered[cols]

    def build_bytes(self,
                    best: Dict[str, Any],
                    alts: List[Dict[str, Any]]) -> bytes:
        """
        Формирует Excel-отчёт в памяти и возвращает его в виде байтов.

        Колонки автоматически переименовываются по col_map.
        Использует XlsxWriter для форматирования, автоссылок и цветовой шкалы значений.

        :param best: Детерминированный результат расчёта.
        :param alts: Список альтернативных сборок.
        :return: Содержимое Excel-файла в формате bytes.
        """
        buf = BytesIO()

        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            comp_df = (
                self._comparison_df(best, alts)
                .rename(columns=self.col_map)
            )
            comp_df.to_excel(writer, sheet_name="Сравнение", index=False)
            ws = writer.sheets["Сравнение"]
            ws.autofilter(0, 0, len(comp_df), len(comp_df.columns) - 1)

            for idx, col in enumerate(comp_df.columns):
                if col in (self.col_map["Type"], self.col_map["Sheet"]):
                    width = 14
                elif col in (self.col_map["Run"], self.col_map["Score"]):
                    width = 8
                else:
                    width = 16
                ws.set_column(idx, idx, width)

            sheet_col = comp_df.columns.get_loc(self.col_map["Sheet"])

            for row_num, sheet_name in enumerate(self._comparison_df(best, alts)["Sheet"], start=1):
                if pd.notna(sheet_name):
                    url = f"internal:'{sheet_name}'!A1"
                    ws.write_url(row_num, sheet_col, url, string=sheet_name)

            last_row = len(comp_df)

            for idx, col in enumerate(comp_df.columns):
                if col in (self.col_map["Type"], self.col_map["Run"], self.col_map["Sheet"]):
                    continue
                ws.conditional_format(
                    1, idx, last_row, idx,
                    {
                        "type": "3_color_scale",
                        "min_color": "#FF0000",
                        "mid_color": "#FFFF00",
                        "max_color": "#00FF00",
                    }
                )

            det_df = (
                pd.DataFrame(best["build"].items(), columns=["Artifact", "Count"])
                .rename(columns={
                    "Artifact": self.col_map.get("Artifact", "Артефакт"),
                    "Count": self.col_map.get("Count", "Количество")
                })
            )
            det_df.to_excel(writer, sheet_name=build_label_det, index=False)
            ws_det = writer.sheets[build_label_det]
            ws_det.set_column(0, 0, 20)
            ws_det.set_column(1, 1, 8)

            for idx, alt in enumerate(alts, 1):
                alt_df = (
                    pd.DataFrame(alt["build"].items(), columns=["Artifact", "Count"])
                    .rename(columns={
                        "Artifact": self.col_map.get("Artifact", "Артефакт"),
                        "Count": self.col_map.get("Count", "Количество")
                    })
                )
                sheet_name = f"Альт {idx}"
                alt_df.to_excel(writer, sheet_name=sheet_name, index=False)
                ws_alt = writer.sheets[sheet_name]
                ws_alt.set_column(0, 0, 20)
                ws_alt.set_column(1, 1, 8)

        buf.seek(0)
        return buf.read()
