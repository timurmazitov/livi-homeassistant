#!/usr/bin/env python3
"""Тест-скрипт Livi API: логин + список объектов + список устройств.

Использование:
    export LIVI_LOGIN="+79001234567"
    export LIVI_PASSWORD="ваш_пароль"
    python3 scripts/test_livi_api.py

Результаты:
  - печатает сводку в терминал
  - сохраняет ответы в fixtures/*.json (маскированные, без токена)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

BASE_PROD = "https://api.livicom.ru:11201/api/v3/"
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

# Заголовки, которые шлёт приложение Livi 2.1.7 (из ClientInfoInterceptor)
CLIENT_HEADERS = {
    "Client-Type": "mobile-app",
    "Client-Platform": "android",
    "Client-Version": "2.1.7",
    "Client-Build": "374",
    "Client-OS-Version": "14",
    "Client-Device": "HomeAssistant-Bridge",
    "Accept-Language": "ru",
}

TOKEN_CANDIDATES = [
    "https://api.livicom.ru:11201/Token",        # Retrofit: путь от корня хоста
    "https://api.livicom.ru:11201/api/v3/Token", # на случай другого резолва
]

USERNAME_VARIANTS_TPL = [
    "{login}",            # как есть: +79001234567
    "{login_noplus}",     # 79001234567
    "{login_8}",          # 89069958588
]


def phone_variants(login: str) -> list[str]:
    out = []
    for tpl in USERNAME_VARIANTS_TPL:
        v = tpl.format(
            login=login,
            login_noplus=login.lstrip("+"),
            login_8="8" + login.lstrip("+")[1:] if login.startswith("+7") else login,
        )
        if v not in out:
            out.append(v)
    return out


def login(session: requests.Session, username: str, password: str) -> tuple[dict | None, tuple[int, str] | None]:
    """POST /Token (ASP.NET Identity). Возвращает (json, None) или (None, (код, ошибка))."""
    last_err: tuple[int, str] | None = None
    for token_url in TOKEN_CANDIDATES:
        resp = session.post(
            token_url,
            data={"username": username, "password": password, "grant_type": "password"},
            headers={**CLIENT_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
        print(f"  POST {token_url} [{username}] -> {resp.status_code}")
        if resp.ok and "access_token" in (resp_json := resp.json()):
            return resp_json, None
        last_err = (resp.status_code, resp.text[:300])
    return None, last_err


def authed_get(session: requests.Session, token: str, url: str, **params):
    resp = session.get(
        url, params=params, headers={**CLIENT_HEADERS, "Authorization": f"Bearer {token}"}, timeout=30
    )
    print(f"  GET {resp.url} -> {resp.status_code}")
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    login_ = os.environ.get("LIVI_LOGIN")
    password = os.environ.get("LIVI_PASSWORD")
    if not login_ or not password:
        print("Задайте переменные окружения LIVI_LOGIN и LIVI_PASSWORD")
        return 2

    FIXTURES.mkdir(exist_ok=True)
    session = requests.Session()

    print("== Логин ==")
    token = None
    for username in phone_variants(login_):
        result, err = login(session, username, password)
        if result is not None and "access_token" in result:
            token = result["access_token"]
            print(f"  УСПЕХ: username={username!r}")
            print(f"  token_type={result.get('token_type')}, expires_in={result.get('expires_in')}")
            print(f"  .issued={result.get('.issued')}, .expires={result.get('.expires')}")
            break
        print(f"  неудача: {err}")
    if not token:
        print("!! Логин не удался ни с одним вариантом username")
        return 1

    print("== Объекты (Object/ListObjects) ==")
    objects = authed_get(session, token, BASE_PROD + "Object/ListObjects")
    (FIXTURES / "objects.json").write_text(json.dumps(objects, ensure_ascii=False, indent=2))
    if not isinstance(objects, list):
        print(f"  неожиданный формат: {str(objects)[:300]}")
        return 1
    print(f"  объектов: {len(objects)}")

    for obj in objects:
        cid = obj.get("IdConsole") or obj.get("Id") or "?"
        name = obj.get("Name", "?")
        print(f"\n== Устройства объекта {name!r} (idConsole={cid}) ==")
        try:
            devices = authed_get(session, token, BASE_PROD + "ConsoleState/ListDevices", idConsole=cid)
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"  ошибка: {e}")
            continue
        safe = str(cid).replace("/", "_")
        (FIXTURES / f"devices_{safe}.json").write_text(json.dumps(devices, ensure_ascii=False, indent=2))
        devs = devices.get("Devices", []) if isinstance(devices, dict) else devices
        print(f"  устройств: {len(devs)}")
        for d in devs:
            print(
                "   - {TypeSensor:<18} {SerialNumber:<14} {Name:<28} online={IsConnected} "
                "signal={SignalLevel} body_closed={IsBodyClosed} events={n_events}".format(
                    n_events=len(d.get("Events") or []),
                    **{k: d.get(k) for k in ("TypeSensor", "SerialNumber", "Name", "IsConnected", "SignalLevel", "IsBodyClosed")},
                )
            )

    print("\n== Готово ==")
    print(f"Fixture-файлы в: {FIXTURES}")
    print("(токен не сохраняется)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
