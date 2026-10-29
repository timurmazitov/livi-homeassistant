"""Константы и маппинги интеграции Livi.

Маппинги сверен с живыми ответами API (fixtures/) и enum ApiTypeSensor APK 2.1.7.
TypeSensor приходит в PascalCase: LiviCs, LiviMs, LiviFs2, LiviRelay1224, LiviHTS...
Состояние устройства — в Sensor.Value ("True"/"False" тревога, "On"/"Off" реле)
и Sensor.Channels (температура/влажность).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

DOMAIN = "livi"

PLATFORMS = ["sensor", "binary_sensor"]

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 30  # секунд


@dataclass(frozen=True)
class DeviceKind:
    """Как представить устройство Livi в HA.

    style:
      alarm       — binary_sensor, on при тревоге (Sensor.Value == "True" или Events ALARM*)
      switch      — sensor со значением Sensor.Value (On/Off): реле, сирена
      temp        — sensor температуры из Channels
      temp_hum    — sensor температуры (канал 3) + влажности (канал 4)
      water_crane — кран: 2 клапана + 2 счётчика (sensor) + утечка (binary)
      online      — sensor online/offline (прочее)
      hub         — хаб (создаётся из ConsoleState объекта, не из списка устройств)
    """

    model: str
    style: str
    entity_suffix: str
    alarm_prefix: str = "ALARM"


# Модель по ConsoleState.Type объекта
HUB_MODELS: dict[str, str] = {
    "SmartHub": "Livi Smart Hub",
    "SmartHub4G": "Livi Smart Hub 4G",
    "SmartHubMini": "Livi Smart Hub Mini",
    "CONSOLE": "Livi Console",
}

DEVICE_KINDS: dict[str, DeviceKind] = {
    # Датчики тревоги
    "LIVI_CS": DeviceKind("Livi Door/Window Sensor", "alarm", "opening"),
    "LIVI_RC": DeviceKind("Livi Glass Break Sensor", "alarm", "glass"),
    "LIVI_MS": DeviceKind("Livi Motion Sensor", "alarm", "motion"),
    "LIVI_MSW": DeviceKind("Livi Motion Sensor W", "alarm", "motion"),
    "LIVI_FS": DeviceKind("Livi Smoke Sensor", "alarm", "smoke", "ALARM_FIRE"),
    "LIVI_FS_2": DeviceKind("Livi Smoke Sensor 2", "alarm", "smoke", "ALARM_FIRE"),
    "LIVI_LS": DeviceKind("Livi Water Leak Sensor", "alarm", "leak"),
    "LIVI_LS_2": DeviceKind("Livi Water Leak Sensor 2", "alarm", "leak"),
    "LIVI_LL": DeviceKind("Livi Liquid Level Sensor", "alarm", "level"),
    "LIVI_VS": DeviceKind("Livi Vibration Sensor", "alarm", "vibration"),
    "LIVI_VS_2": DeviceKind("Livi Vibration Sensor 2", "alarm", "vibration"),
    "LIVI_GS": DeviceKind("Livi Gas Sensor", "alarm", "gas"),
    "LIVI_CSM": DeviceKind("Livi CO Sensor", "alarm", "co"),
    "SENSOR": DeviceKind("Livi Sensor", "alarm", "generic"),
    "UNIVERSAL_SENSOR": DeviceKind("Livi Universal Sensor", "alarm", "universal"),
    # Исполнительные устройства: состояние в Sensor.Value (On/Off)
    "LIVI_RELAY": DeviceKind("Livi Relay", "switch", "relay"),
    "LIVI_RELAY_2DIN": DeviceKind("Livi Relay 2DIN", "switch", "relay_2din"),
    "LIVI_RELAY_1224": DeviceKind("Livi Relay 1224", "switch", "relay_1224"),
    "LIVI_SIREN": DeviceKind("Livi Siren", "switch", "siren"),
    "LIVI_SIREN_2": DeviceKind("Livi Siren 2", "switch", "siren2"),
    "LIVI_LIGHT_CONTROL": DeviceKind("Livi Light Control", "switch", "light"),
    "LIVI_ROLLER_SHUTTER": DeviceKind("Livi Roller Shutter", "switch", "shutter"),
    "LIVI_OR": DeviceKind("Livi Outdoor Relay", "switch", "outdoor_relay"),
    # Климат: температура/влажность в Sensor.Channels
    "LIVI_TS": DeviceKind("Livi Temperature Sensor", "temp", "temperature"),
    "LIVI_HTS": DeviceKind("Livi Humidity/Temperature Sensor", "temp_hum", "climate"),
    "LIVI_RTRM": DeviceKind("Livi Room Thermostat", "switch", "thermostat"),
    # Кран с водосчётчиками и датчиком утечки
    "LIVI_WC": DeviceKind("Livi Water Crane", "water_crane", "crane"),
    # Управление/идентификация: только online/offline
    "KEY_FOB": DeviceKind("Livi Key Fob", "online", "fob"),
    "LIVI_RFID": DeviceKind("Livi RFID Reader", "online", "rfid"),
    "LIVI_KEYPAD": DeviceKind("Livi Keypad", "online", "keypad"),
}

# PascalCase-варианты, отличающиеся от простого upper()
TYPE_ALIASES: dict[str, str] = {
    "LIVI_FS2": "LIVI_FS_2",
    "LIVI_RELAY1224": "LIVI_RELAY_1224",
}

# Режим охраны (ProtectionMode) -> значение сенсора «Охрана»
PROTECTION_MODE_RU: dict[str, str] = {
    "IS_DISARMED": "disarmed",
    "DISARMING": "disarming",
    "PROTECTION": "armed",
    "ARM": "armed",
    "ARM_APP": "armed_home",
    "ARM_PART": "armed_home",
    "PARTIAL_PROTECTION": "armed_home",
    "ERROR_PROTECTION": "error",
    "UNKNOWN": "unknown",
}

# Статус охраны (ProtectionStatus): неблагоприятные показываем как значение сенсора
PROTECTION_STATUS_RU: dict[str, str] = {
    "ALARM": "alarm",
    "ALARM_DELAY": "alarm_delay",
}


def _normalize_type(type_sensor: str) -> str:
    """LiviCs -> LIVI_CS, LiviFs2 -> LIVI_FS_2, LiviRelay1224 -> LIVI_RELAY_1224."""
    upper = type_sensor.upper()
    if upper in DEVICE_KINDS:
        return upper
    if upper.startswith("LIVI") and "_" not in upper and len(upper) > 4:
        rest = upper[4:]
        # LIVIFS2 -> LIVI_FS_2, LIVIRELAY1224 -> LIVI_RELAY_1224
        rest = re.sub(r"(?<=[A-Z])(?=[0-9])", "_", rest)
        return f"LIVI_{rest}"
    return TYPE_ALIASES.get(upper, upper)


def device_kind(type_sensor: str | None) -> DeviceKind:
    """DeviceKind по строке TypeSensor (неизвестные типы -> online)."""
    if not type_sensor:
        return DeviceKind("Livi Device", "online", "unknown")
    return DEVICE_KINDS.get(
        _normalize_type(type_sensor), DeviceKind(f"Livi {type_sensor}", "online", "unknown")
    )


def sensor_value(device: dict[str, Any]) -> str | None:
    """Sensor.Value устройства (строка: 'True'/'False'/'On'/'Off')."""
    sensor = device.get("Sensor")
    if isinstance(sensor, dict):
        value = sensor.get("Value")
        if value is not None:
            return str(value)
    return None


def is_alarm_now(device: dict[str, Any], kind: DeviceKind) -> bool:
    """Тревога: Sensor.Value == 'True' либо ALARM* среди Events[].Type."""
    if kind.style != "alarm":
        return False
    if sensor_value(device) == "True":
        return True
    events = device.get("Events") or []
    for ev in events:
        ev_type = (ev.get("Type") or "").upper() if isinstance(ev, dict) else str(ev).upper()
        if ev_type.startswith(kind.alarm_prefix):
            return True
    return False


def _channels(device: dict[str, Any]) -> list[dict[str, Any]]:
    """Sensor.Channels, только включённые и исправные."""
    sensor = device.get("Sensor")
    if not isinstance(sensor, dict):
        return []
    channels = sensor.get("Channels")
    if not isinstance(channels, list):
        return []
    return [
        ch
        for ch in channels
        if isinstance(ch, dict) and ch.get("IsEnabled") and not ch.get("IsFaulty")
    ]


def extract_temperature(device: dict[str, Any]) -> float | None:
    """Температура: канал 3 (основной), fallback — первый активный канал."""
    channels = _channels(device)
    if not channels:
        return None
    for ch in channels:
        if ch.get("Number") == 3 and isinstance(ch.get("Value"), (int, float)):
            return float(ch["Value"])
    for ch in channels:
        if isinstance(ch.get("Value"), (int, float)):
            return float(ch["Value"])
    return None


def extract_humidity(device: dict[str, Any]) -> float | None:
    """Влажность (LiviHTS): канал 4."""
    for ch in _channels(device):
        if ch.get("Number") == 4 and isinstance(ch.get("Value"), (int, float)):
            return float(ch["Value"])
    return None


def leak_active(device: dict[str, Any]) -> bool | None:
    """Утечка у LiviWc: любой канал LiquidLeakSensor.Value == 'True'."""
    sensor = device.get("Sensor")
    if not isinstance(sensor, dict):
        return None
    leak = sensor.get("LiquidLeakSensor")
    if not isinstance(leak, dict):
        return None
    channels = leak.get("Channels") or []
    result = False
    for ch in channels:
        if isinstance(ch, dict) and str(ch.get("Value")) == "True":
            result = True
    return result
