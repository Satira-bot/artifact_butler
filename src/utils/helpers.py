import re
import yaml
import base64
import random
import pandas as pd
import streamlit as st
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple

from src.utils.constants import footer_phrases, DEFAULT_DATA_FILE


@dataclass
class Settings:
    """
    Глобальные настройки оптимизатора. Меняются через UI Streamlit.
    """
    data_file: str = str(DEFAULT_DATA_FILE)
    tier: int = 3
    num_slots: int = 17
    max_copy: int = 3
    blacklist: List[str] = field(default_factory=lambda: ["Душа", "Пустышка"])
    jitter: float = 0.0
    alt_jitter: float = 0.30
    alt_cnt: int = 10
    alt_runs: int = 10
    props_file: str = "props_tier3.yaml"

    def __post_init__(self) -> None:
        self.alt_runs =self.alt_cnt

    def recompute(self) -> None:
        """
        Пересчитывает вычисляемые поля после изменения основных настроек.
        Централизует логику пересчёта зависимых параметров.
        """
        self.alt_runs = self.alt_cnt
        # self.alt_runs = round(self.alt_cnt * 1.5)

    def update_alt_count(self, count: int) -> None:
        """Удобный сеттер: меняем alt_cnt + сразу вызываем recompute()."""
        self.alt_cnt = count
        self.recompute()


class Props:
    """
    Обёртка над YAML-файлом с правилами (приоритеты, минимумы/максимумы).
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.display: dict[str, str] = {
            name: meta.get("rus", meta.get("column", name))
            for name, meta in self.data.items()
        }
        self.display = {
            k: meta.get("rus", meta.get("column", k))
            for k, meta in data.items()
        }

    def __post_init__(self) -> None:
        self.display: dict[str, str] = {
            name: meta.get("rus", meta.get("column", name))
            for name, meta in self.data.items()
        }

    @classmethod
    def load(cls, path: str, num_slots: int) -> "Props":
        with open(path, encoding="utf-8") as f:
            props_dict = yaml.safe_load(f)
        props_dict["slots"]["low"] = num_slots
        props_dict["slots"]["high"] = num_slots
        return cls(props_dict)

    def rus(self, key: str) -> str:
        """Возвращает человеко-понятное (русское) название для системного ключа"""
        return self.display.get(key, key)

    def save(self, path: str) -> None:
        """
        Сохраняем актуальные правила обратно в YAML.
        """
        with open(path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(self.data, f, allow_unicode=True)


def normalize_blacklist_input(raw: str) -> Tuple[List[str], str | None]:
    """
    Обрабатывает строку из текстового поля и возвращает чистый список имён.
    Дополнительно подсказывает, если в разделителях закралась коварная опечатка.
    """

    bad_separator = re.compile(r"[;/\\|.]+")
    cleaned = bad_separator.sub(",", raw)

    info_msg = (
        "Ах! Неловкость вышла… Ваши символы оказались неподходящими, я поспешил заменить их на запятые! "
        "Всё уже исправлено, не волнуйтесь!"
        if cleaned != raw else None
    )

    items = [s.strip() for s in cleaned.split(",") if s.strip()]
    return items, info_msg


def validate_blacklist(items: List[str],
                       available_names: List[str]
                       ) -> Tuple[List[str], List[str]]:
    """
    Делит входной список на (valid, invalid) с учётом регистра.
    Возвращает пары уже в «правильном» регистре из available_names.
    """
    norm = {name.lower(): name for name in available_names}
    valid, invalid = [], []
    for item in items:
        match = norm.get(item.lower())
        (valid if match else invalid).append(match or item)
    return valid, invalid


def validate_adv_props(df: pd.DataFrame) -> List[str]:
    """
    Проверяет корректность расширенных настроек свойств.
    Если что-то задано странно — аккуратно сообщает об этом.
    """
    errors: List[str] = []

    if not df["Use"].any():
        errors.append("Ах! Ни одно свойство не выбрано! "
                      "Прошу, отметьте хотя бы одно в расширенных настройках — иначе мне неловко продолжать!")

    mask = df["Use"] & df["Min enabled"] & df["Max enabled"]
    for _, row in df[mask].iterrows():
        if row["Min"] > row["Max"]:
            errors.append(
                f"О, скромное замечание! В свойстве «{row['Property']}» "
                f"нижняя граница ({row['Min']}) не может быть больше верхней ({row['Max']})."
            )

    return errors


def validate_fixed_count(fixed: List[Tuple[str, int]],
                         num_slots: int
                         ) -> List[str]:
    """
    Проверяет, что число фиксированных артефактов ≤ num_slots - 1.
    """
    errors: List[str] = []
    total = len(fixed)
    if total > num_slots - 1:
        errors.append(
            f"Вы зафиксировали {total} артефактов — но максимум можно {num_slots - 1}. "
            "Один слот Лакей должен оставить себе для манёвра."
        )
    return errors


def validate_fixed_copies(fixed: List[Tuple[str, int]],
                          max_copy: int
                          ) -> List[str]:
    """
    Проверяет, что ни один артефакт не зафиксирован более max_copy раз.
    """
    errors: List[str] = []
    counts = Counter(fixed)
    for (name, tier), cnt in counts.items():
        if cnt > max_copy:
            errors.append(
                f"Лакей хмурится: «{name}» (Тир {tier}) — {cnt} копий при лимите {max_copy}. "
                f"Он покашлял и сделал вид, что не заметил. Но не смог."
            )
    return errors


def validate_all(df: pd.DataFrame,
                 fixed: List[Tuple[str, int]],
                 num_slots: int,
                 max_copy: int
                 ) -> List[str]:
    """
    Запускает все проверки: расширенные свойства + fixed_count + fixed_copies.
    """
    errors: List[str] = []

    if df is None:
        errors.append("Не удалось прочитать расширенные настройки")
        return errors

    errors += validate_adv_props(df)
    errors += validate_fixed_count(fixed, num_slots)
    errors += validate_fixed_copies(fixed, max_copy)
    return errors


def get_random_footer_phrase() -> str:
    """Возвращает случайную фразу"""
    return random.choice(footer_phrases)


def props_to_df(props: Props) -> pd.DataFrame:
    """
    Преобразует свойства в удобный DataFrame для редактирования.
    Скрытые служебные параметры остаются за кулисами.
    """
    rows: List[Dict[str, Any]] = []
    hidden = {"slots"}

    for name, meta in props.data.items():
        if name in hidden:
            continue
        rows.append({
            "Use": bool(meta.get("use", False)),
            "Property": props.rus(name),
            "Priority": float(meta.get("priority", 0)),
            "Min enabled": meta.get("low") is not None,
            "Min": int(meta.get("low") or 0),
            "Max enabled": meta.get("high") is not None,
            "Max": int(meta.get("high") or 0),
        })
    return pd.DataFrame(rows)


def df_to_props(df: pd.DataFrame, props: Props) -> None:
    """
    Обновляет свойства из отредактированного DataFrame обратно в props.data.
    Русские подписи колонок сопоставляются с внутренними ключами.
    """
    reverse_display: dict[str, str] = {
        rus_name: key for key, rus_name in props.display.items()
    }

    for _, row in df.iterrows():
        rus_name = row["Property"]
        key = reverse_display.get(rus_name)
        if key is None:
            continue

        meta: dict[str, Any] = props.data[key]
        meta["use"] = bool(row["Use"])

        if not row["Use"]:
            meta["priority"] = 0
        else:
            meta["priority"] = float(row["Priority"])

        if row["Min enabled"]:
            meta["low"] = float(row["Min"])
        else:
            meta.pop("low", None)

        if row["Max enabled"]:
            meta["high"] = float(row["Max"])
        else:
            meta.pop("high", None)


@st.cache_data(show_spinner=False)
def get_base64_image(image_path):
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()
