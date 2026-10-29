"""Config flow: ввод логина/пароля Livi (HA 2026.10: probatio.Schema, OptionsFlow.config_entry — property)."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import probatio
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant, callback

from .api import LiviApiError, LiviAuthError, LiviClient
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Проверяем учётные данные реальным запросом к API."""
    session = aiohttp.ClientSession()
    try:
        client = LiviClient(username=data["username"], password=data["password"], session=session)
        objects = await client.validate()
    finally:
        await session.close()

    if not objects:
        # Аккаунт валиден, но объектов нет — разрешаем, устройства появятся позже
        _LOGGER.warning("Livi: аккаунт без объектов")
    return {"title": "Livi", "objects_count": len(objects)}


class LiviConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow для Livi."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            # одна учётка = одна запись
            self._async_abort_entries_match({"username": user_input["username"]})
            try:
                info = await validate_input(self.hass, user_input)
            except LiviAuthError:
                errors["base"] = "invalid_auth"
            except (LiviApiError, aiohttp.ClientError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Неожиданная ошибка при подключении к Livi")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input["username"])
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema(
                {
                    probatio.Required("username"): str,
                    probatio.Required("password"): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> LiviOptionsFlow:
        return LiviOptionsFlow()


class LiviOptionsFlow(config_entries.OptionsFlow):
    """Настройки: интервал опроса."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        schema = probatio.Schema(
            {
                probatio.Optional(CONF_SCAN_INTERVAL, default=current): int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
