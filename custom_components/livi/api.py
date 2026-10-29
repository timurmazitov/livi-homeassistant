"""Клиент облачного API Livi (livicom.ru).

Схема (восстановлена из APK Livi 2.1.7):
  POST /Token                        — получение токена (ASP.NET Identity, form-urlencoded)
  GET  api/v3/Object/ListObjects     — список объектов охраны/умного дома
  GET  api/v3/ConsoleState/ListDevices?idConsole=... — устройства объекта

Заголовки Client-* имитируют официальное приложение (ClientInfoInterceptor).
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import aiohttp

API_BASE = "https://api.livicom.ru:11201/api/v3/"
AUTH_URL = "https://api.livicom.ru:11201/Token"
AUTH_URL_ALT = "https://api.livicom.ru:11201/api/v3/Token"

# Заголовки из ClientInfoInterceptor / ClientInfoHeaders официального приложения
CLIENT_HEADERS = {
    "Client-Type": "mobile-app",
    "Client-Platform": "android",
    "Client-Version": "2.1.7",
    "Client-Build": "374",
    "Accept-Language": "ru",
}

DEFAULT_TIMEOUT = 30
TOKEN_EXPIRY_MARGIN = timedelta(minutes=5)


class LiviApiError(Exception):
    """Базовая ошибка API."""


class LiviAuthError(LiviApiError):
    """Неверный логин/пароль или токен истёк без возможности обновления."""


class LiviClient:
    """Асинхронный клиент Livi. Не знает про Home Assistant."""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        api_base: str = API_BASE,
    ) -> None:
        # Сервер принимает телефон без '+': 79001234567 (проверено живым тестом).
        # Email передаём как есть.
        self._username = username.removeprefix("+")
        self._password = password
        self._session = session
        self._api_base = api_base
        self._token: str | None = None
        self._token_expires: datetime | None = None
        self._token_lock = asyncio.Lock()

    # -- низкий уровень ----------------------------------------------------

    @property
    def _headers(self) -> dict[str, str]:
        h = dict(CLIENT_HEADERS)
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        try:
            async with self._session.request(
                method, url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT), **kwargs
            ) as resp:
                if resp.status == 401:
                    # токен протух: сбросим и попробуем ещё раз один раз
                    self._token = None
                    await self._ensure_token()
                    async with self._session.request(
                        method, url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT), **kwargs
                    ) as retry:
                        retry.raise_for_status()
                        return await retry.json()
                resp.raise_for_status()
                if resp.content_type == "application/json":
                    return await resp.json()
                return await resp.text()
        except aiohttp.ClientResponseError as err:
            if err.status in (400, 403) and "/Token" in url:
                raise LiviAuthError(f"Ошибка авторизации: {err.status}") from err
            raise LiviApiError(f"HTTP {err.status} на {urlsplit(url).path}") from err
        except (TimeoutError, aiohttp.ClientError) as err:
            raise LiviApiError(f"Сетевая ошибка: {err}") from err

    # -- авторизация ---------------------------------------------------------

    async def _ensure_token(self) -> None:
        if self._token and self._token_expires and datetime.now(UTC) < self._token_expires:
            return
        async with self._token_lock:
            if self._token and self._token_expires and datetime.now(UTC) < self._token_expires:
                return
            await self._fetch_token()

    async def _fetch_token(self) -> None:
        data = {
            "username": self._username,
            "password": self._password,
            "grant_type": "password",
        }
        last_error: Exception | None = None
        for token_url in (AUTH_URL, AUTH_URL_ALT):
            try:
                async with self._session.post(
                    token_url,
                    data=data,
                    headers={**CLIENT_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
                    timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
                ) as resp:
                    if resp.status in (200,) and resp.content_type == "application/json":
                        payload = await resp.json()
                        self._token = payload["access_token"]
                        self._token_expires = self._parse_expires(payload)
                        return
                    if resp.status in (400, 403):
                        # ASP.NET Identity отвечает 400 invalid_grant на неверные данные
                        body = await resp.text()
                        if "invalid_grant" in body or resp.status == 400:
                            last_error = LiviAuthError("Неверный логин или пароль")
                            continue
                    last_error = LiviApiError(f"Неожиданный ответ {resp.status} от {token_url}")
            except (TimeoutError, aiohttp.ClientError) as err:
                last_error = LiviApiError(f"Сетевая ошибка при логине: {err}")
        raise last_error or LiviAuthError("Авторизация не удалась")

    @staticmethod
    def _parse_expires(payload: dict[str, Any]) -> datetime:
        """Приоритет: строка .expires (RFC1123), fallback: expires_in (секунды)."""
        raw = payload.get(".expires")
        if raw:
            try:
                from email.utils import parsedate_to_datetime

                dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt - TOKEN_EXPIRY_MARGIN
            except (TypeError, ValueError):
                pass
        seconds = int(payload.get("expires_in", 3600))
        return datetime.now(UTC) + timedelta(seconds=seconds) - TOKEN_EXPIRY_MARGIN

    # -- публичный API ---------------------------------------------------------

    async def async_get_objects(self) -> list[dict[str, Any]]:
        """GET Object/ListObjects — список объектов (домов/квартир)."""
        await self._ensure_token()
        result = await self._request("GET", f"{self._api_base}Object/ListObjects")
        if isinstance(result, dict):
            # некоторые версии API оборачивают список
            result = result.get("Objects") or result.get("ListObjects") or []
        return result

    async def async_get_devices(self, console_id: str) -> list[dict[str, Any]]:
        """GET ConsoleState/ListDevices — устройства объекта."""
        await self._ensure_token()
        result = await self._request(
            "GET", f"{self._api_base}ConsoleState/ListDevices", params={"idConsole": console_id}
        )
        if isinstance(result, dict):
            result = result.get("Devices") or []
        return result

    async def async_get_console_status(self, console_id: str) -> dict[str, Any]:
        """GET ConsoleState/StateConsole — состояние хаба."""
        await self._ensure_token()
        result = await self._request(
            "GET", f"{self._api_base}ConsoleState/StateConsole", params={"idConsole": console_id}
        )
        return result if isinstance(result, dict) else {}

    async def validate(self) -> list[dict[str, Any]]:
        """Проверка учётных данных: возвращает список объектов."""
        objects = await self.async_get_objects()
        if not isinstance(objects, list):
            raise LiviApiError("Неожиданный формат ответа ListObjects")
        return objects
