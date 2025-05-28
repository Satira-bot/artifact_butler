import json
import hashlib
import streamlit as st

from src.utils.constants import ACHIEVABLE_DIR
from typing import Dict, Any, Callable, Optional, Tuple


def generate_achievable_hash(tier: int,
                             slots: int,
                             max_copy: int,
                             blacklist: list[str],
                             props_data: Dict[str, Any],
                             props_file: str
                             ) -> str:
    """
    Строит SHA-256 хеш ограничений для поиска в кэше:
    tier, number of slots, max_copy, blacklist, props_file и props (name, low, high).
    """
    payload = {
        'tier': tier,
        'slots': slots,
        'max_copy': max_copy,
        'blacklist': blacklist,
        'props_file': props_file,
        'props': [
            {'name': name, 'low': meta.get('low'), 'high': meta.get('high')}
            for name, meta in sorted(props_data.items(), key=lambda x: x[0])
        ]
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def load_session_achievable(hash_key: str) -> Optional[Dict[str, Dict[str, float]]]:
    """
    Пытается получить предрасчёт из Streamlit session_state.
    """
    cache = st.session_state.get('achievable_cache', {})
    return cache.get(hash_key)


def save_session_achievable(hash_key: str, data: Dict[str, float]) -> None:
    """
    Сохраняет предрасчёт в session_state.
    """
    if 'achievable_cache' not in st.session_state:
        st.session_state['achievable_cache'] = {}
    st.session_state['achievable_cache'][hash_key] = data


def load_disk_achievable(preset_id: str, hash_key: str) -> Optional[Dict[str, Any]]:
    """
    Ищет предрасчёт в JSON-файле для заданного пресета на диске.
    """
    file_path = ACHIEVABLE_DIR / f'achievable_{preset_id}.json'
    if not file_path.exists():
        return None
    with file_path.open(encoding='utf-8') as f:
        all_data = json.load(f)
    entry = all_data.get(hash_key)
    return entry if entry else None


def get_or_compute_achievable(settings: Any,
                              props_data: Dict[str, Any],
                              compute_fn: Callable[[Any], Tuple[Dict[str, Any], Dict[str, float]]]
                              ) -> Dict[str, float]:
    """
    Универсальная функция: три шага поиска кэша (session -> disk -> расчёт).
    compute_fn должен вернуть кортеж (props_data, maxima).
    """
    # preset_id = settings.props_file
    hash_key = generate_achievable_hash(
        settings.tier,
        settings.num_slots,
        settings.max_copy,
        sorted(settings.blacklist),
        props_data,
        settings.props_file
    )

    result = load_session_achievable(hash_key)
    if result is not None:
        return result

    # result = load_disk_achievable(preset_id, hash_key)
    # if result is not None:
    #     save_session_achievable(hash_key, result)
    #     return result

    _, maxima = compute_fn(settings)
    save_session_achievable(hash_key, maxima)
    return maxima
