"""Базовая сущность Livi.

Паттерн HA 2026.10: не переопределяем cached_property (is_on/native_value/
extra_state_attributes/available), а выставляем _attr_* в хуке
_update_state(), который дергается из _handle_coordinator_update().
"""
from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DeviceKind
from .coordinator import LiviCoordinator, LiviObject


class LiviEntity(CoordinatorEntity[LiviCoordinator]):
    """Родитель для всех сущностей Livi.

    Хранит ключи (console_id, device_key) и на каждое обновление
    заново находит актуальные данные — устройства не «застывают».
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LiviCoordinator,
        obj: LiviObject,
        device: dict[str, Any] | None,
        kind: DeviceKind,
        suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._console_id = obj.console_id
        self._kind = kind
        self._suffix = suffix
        # Ключ устройства: SerialNumber, fallback Id, для объекта — console_id
        if device is not None:
            self._device_key = str(device.get("SerialNumber") or device.get("Id") or suffix)
            device_name = device.get("Name") or kind.model
        else:
            self._device_key = obj.console_id
            device_name = obj.name
        self._attr_unique_id = f"livi:{self._console_id}:{self._device_key}:{suffix}"

        is_hub = self._device_key == obj.console_id
        info: DeviceInfo = {
            "identifiers": {(DOMAIN, f"{self._console_id}:{self._device_key}")},
            "name": device_name,
            "manufacturer": "Livicom",
            "model": kind.model,
        }
        if not self._device_key.isdigit():
            info["serial_number"] = self._device_key
        if not is_hub:
            # хаб объекта — родительское устройство (registry id из pre-registered
            # в __init__.py устройства, паттерн enphase_envoy)
            config_entry = self.coordinator.config_entry
            assert config_entry is not None  # setup всегда через config entry
            info["via_device_id"] = dr.async_get_device_id_by_identifier(
                self.coordinator.hass,
                (DOMAIN, f"{self._console_id}:{self._console_id}"),
                config_entry_id=config_entry.entry_id,
            )
        self._attr_device_info = info
        # Для сущностей хаба (device=None) имя устройства = имя объекта
        self._is_hub_entity = is_hub

    @callback
    def _handle_coordinator_update(self) -> None:
        """Обновление данных координатора: пересчитываем _attr_* и пишем состояние."""
        self._update_state(self._current_device())
        super()._handle_coordinator_update()

    def _current_object(self) -> LiviObject | None:
        """Актуальный объект из последних данных координатора."""
        return self.coordinator.data.get(self._console_id)

    def _current_device(self) -> dict[str, Any] | None:
        """Актуальные данные устройства (None, если устройство исчезло)."""
        obj = self._current_object()
        if obj is None:
            return None
        for dev in obj.devices:
            key = str(dev.get("SerialNumber") or dev.get("Id") or "")
            if key == self._device_key:
                return dev
        return None

    def _update_state(self, device: dict[str, Any] | None) -> None:
        """Хук подклассов: выставить _attr_is_on / _attr_native_value / атрибуты."""
