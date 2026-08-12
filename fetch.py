#!/usr/bin/env python3
"""
Pobiera historyczne odczyty czujników z chmury Tuya i dopisuje je do plików CSV.

Tuya trzyma 7 dni logów za darmo, więc każde uruchomienie pobiera okno 7-dniowe
i dokłada tylko te odczyty, których jeszcze nie ma. Dzięki temu nieudany albo
pominięty przebieg niczego nie kosztuje — następny nadrobi zaległości.

Użycie:
    python fetch.py --discover     # wypisz urządzenia widoczne na koncie
    python fetch.py                # pobierz ostatnie 7 dni i zapisz do data/
    python fetch.py --days 3       # węższe okno
    python fetch.py --dry-run      # policz, ale nie zapisuj
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# --- konfiguracja ------------------------------------------------------------

REGIONS = {
    "eu": "https://openapi.tuyaeu.com",       # Central Europe  <- domyślne dla Polski
    "we": "https://openapi-weaz.tuyaeu.com",  # Western Europe
    "us": "https://openapi.tuyaus.com",       # Western America
    "ue": "https://openapi-ueaz.tuyaus.com",  # Eastern America
    "in": "https://openapi.tuyain.com",       # India
    "cn": "https://openapi.tuyacn.com",       # China
}

DATA_DIR = Path("data")
MANIFEST = DATA_DIR / "index.json"
FIELDS = ["ts", "device_id", "code", "value"]
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

# Po tych fragmentach nazwy rozpoznajemy, czym jest dany odczyt.
KIND_HINTS = [
    ("temp", "temp"),
    ("humi", "hum"),
    ("battery", "battery"),
]


class TuyaError(RuntimeError):
    pass


# --- klient API --------------------------------------------------------------


class Tuya:
    """Minimalny klient Tuya Cloud API z podpisywaniem HMAC-SHA256."""

    def __init__(self, client_id: str, secret: str, region: str):
        if region not in REGIONS:
            raise TuyaError(
                f"Nieznany region {region!r}. Dozwolone: {', '.join(REGIONS)}"
            )
        self.client_id = client_id
        self.secret = secret
        self.base = REGIONS[region]
        self.token = ""
        self.token_expires = 0.0
        self.session = requests.Session()

    def _headers(self, method: str, path: str, with_token: bool) -> dict:
        t = str(int(time.time() * 1000))
        string_to_sign = "\n".join([method, EMPTY_SHA256, "", path])
        token = self.token if with_token else ""
        message = self.client_id + token + t + string_to_sign
        sign = hmac.new(
            self.secret.encode(), message.encode(), hashlib.sha256
        ).hexdigest().upper()
        headers = {
            "client_id": self.client_id,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
        }
        if with_token:
            headers["access_token"] = self.token
        return headers

    def _refresh_token(self) -> None:
        path = "/v1.0/token?grant_type=1"
        resp = self.session.get(
            self.base + path, headers=self._headers("GET", path, False), timeout=30
        )
        data = resp.json()
        if not data.get("success"):
            raise TuyaError(explain(data))
        result = data["result"]
        self.token = result["access_token"]
        self.token_expires = time.time() + int(result.get("expire_time", 7200))

    def get(self, path: str, params: dict | None = None, _retry: bool = True) -> dict:
        if not self.token or time.time() > self.token_expires - 60:
            self._refresh_token()

        full = path
        if params:
            # Parametry MUSZĄ być posortowane alfabetycznie — inaczej podpis nie przejdzie.
            query = "&".join(
                f"{k}={params[k]}" for k in sorted(params) if params[k] is not None
            )
            full = f"{path}?{query}"

        resp = self.session.get(
            self.base + full, headers=self._headers("GET", full, True), timeout=30
        )
        data = resp.json()

        # 1010 / 1013 = token wygasł albo unieważniony — odśwież i spróbuj raz jeszcze.
        if not data.get("success") and data.get("code") in (1010, 1013) and _retry:
            self.token = ""
            return self.get(path, params, _retry=False)

        return data


def explain(data: dict) -> str:
    """Zamienia kod błędu Tuya na komunikat, z którym da się coś zrobić."""
    code = data.get("code")
    msg = data.get("msg", "brak treści błędu")
    hints = {
        1004: "Zły podpis. Sprawdź, czy Access Secret jest przepisany w całości.",
        1106: "Brak uprawnień. Czy urządzenie na pewno należy do podpiętego konta?",
        1114: "Zły region. Projekt jest w innym data center, niż podałeś w TUYA_REGION.",
        2007: "Zły region albo Access ID nie pasuje do data center.",
        28841002: (
            "Wygasł trial IoT Core. Wejdź na iot.tuya.com → Cloud → Development, "
            "otwórz projekt i złóż wniosek o przedłużenie. Zatwierdzają w 1-2 dni robocze."
        ),
    }
    hint = hints.get(code, "")
    return f"Tuya odrzuciła zapytanie (kod {code}): {msg}. {hint}".strip()


# --- odczyt urządzeń ---------------------------------------------------------


def list_devices(client: Tuya) -> list[dict]:
    """Wszystkie urządzenia z konta Smart Life podpiętego do projektu."""
    devices, last_key = [], None
    while True:
        params = {"page_size": 100}
        if last_key:
            params["last_row_key"] = last_key
        data = client.get("/v1.0/iot-01/associated-users/devices", params)
        if not data.get("success"):
            raise TuyaError(explain(data))
        result = data.get("result") or {}
        devices.extend(result.get("devices", []))
        if not result.get("has_more"):
            break
        last_key = result.get("last_row_key")
        if not last_key:
            break
    return devices


def describe_codes(client: Tuya, device_id: str) -> dict:
    """
    Zwraca opis pól odczytu urządzenia: {kod: {kind, unit, scale}}.

    scale mówi, przez ile podzielić surową wartość — czujniki Tuya raportują
    temperaturę jako liczbę całkowitą, np. 235 przy scale=1 oznacza 23,5 °C.
    """
    data = client.get(f"/v1.0/devices/{device_id}/specifications")
    if not data.get("success"):
        return {}

    codes = {}
    for item in (data.get("result") or {}).get("status", []):
        code = item.get("code", "")
        try:
            spec = json.loads(item.get("values") or "{}")
        except (ValueError, TypeError):
            spec = {}

        kind = None
        for needle, label in KIND_HINTS:
            if needle in code.lower():
                kind = label
                break
        if kind is None:
            continue

        codes[code] = {
            "kind": kind,
            "unit": spec.get("unit") or ("°C" if kind == "temp" else "%"),
            "scale": int(spec.get("scale", 0) or 0),
        }
    return codes


def fetch_logs(client: Tuya, device_id: str, start_ms: int, end_ms: int) -> list[dict]:
    """
    Pobiera logi odczytów. Najpierw próbuje nowszego endpointu v2.0,
    a jeśli konto go nie obsługuje — spada na starszy v1.0.
    """
    rows = _logs_v2(client, device_id, start_ms, end_ms)
    if rows is None:
        rows = _logs_v1(client, device_id, start_ms, end_ms)
    return rows or []


def _logs_v2(client, device_id, start_ms, end_ms) -> list[dict] | None:
    out, last_key = [], None
    for _ in range(300):  # bezpiecznik przed pętlą bez końca
        params = {"start_time": start_ms, "end_time": end_ms, "size": 100}
        if last_key:
            params["last_row_key"] = last_key
        data = client.get(f"/v2.0/cloud/thing/{device_id}/report-logs", params)
        if not data.get("success"):
            return None
        result = data.get("result") or {}
        out.extend(result.get("logs", []))
        if not result.get("has_more"):
            break
        last_key = result.get("last_row_key")
        if not last_key:
            break
    return out


def _logs_v1(client, device_id, start_ms, end_ms) -> list[dict] | None:
    out, row_key = [], None
    for _ in range(300):
        params = {"type": 7, "start_time": start_ms, "end_time": end_ms, "size": 100}
        if row_key:
            params["start_row_key"] = row_key
        data = client.get(f"/v1.0/devices/{device_id}/logs", params)
        if not data.get("success"):
            raise TuyaError(explain(data))
        result = data.get("result") or {}
        out.extend(result.get("logs", []))
        if not result.get("has_next"):
            break
        row_key = result.get("next_row_key")
        if not row_key:
            break
    return out


# --- zapis do plików ---------------------------------------------------------


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_month(month: str) -> list[dict]:
    path = DATA_DIR / f"{month}.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_month(month: str, rows: list[dict]) -> None:
    rows.sort(key=lambda r: (r["ts"], r["device_id"], r["code"]))
    path = DATA_DIR / f"{month}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def merge(new_rows: list[dict]) -> int:
    """Dokłada odczyty do plików miesięcznych, pomijając te już zapisane."""
    by_month: dict[str, list[dict]] = {}
    for row in new_rows:
        by_month.setdefault(row["ts"][:7], []).append(row)

    added = 0
    for month, incoming in by_month.items():
        existing = load_month(month)
        seen = {(r["ts"], r["device_id"], r["code"]) for r in existing}
        fresh = []
        for row in incoming:
            key = (row["ts"], row["device_id"], row["code"])
            if key in seen:
                continue
            seen.add(key)
            fresh.append(row)
        if fresh:
            save_month(month, existing + fresh)
            added += len(fresh)
    return added


def write_manifest(devices: dict) -> None:
    months = sorted(p.stem for p in DATA_DIR.glob("*.csv"))
    MANIFEST.write_text(
        json.dumps(
            {
                "updated": iso(int(time.time() * 1000)),
                "months": months,
                "devices": devices,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


# --- główny przebieg ---------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Kolektor odczytów z chmury Tuya")
    parser.add_argument("--discover", action="store_true",
                        help="wypisz urządzenia i zakończ")
    parser.add_argument("--days", type=int, default=7,
                        help="ile dni wstecz pobrać (Tuya trzyma maksymalnie 7)")
    parser.add_argument("--dry-run", action="store_true",
                        help="pokaż, co by się zapisało, ale nie zapisuj")
    args = parser.parse_args()

    client_id = os.environ.get("TUYA_CLIENT_ID", "").strip()
    secret = os.environ.get("TUYA_CLIENT_SECRET", "").strip()
    region = os.environ.get("TUYA_REGION", "eu").strip().lower()

    if not client_id or not secret:
        print("Brakuje TUYA_CLIENT_ID albo TUYA_CLIENT_SECRET.", file=sys.stderr)
        print("Lokalnie: export TUYA_CLIENT_ID=... ; w Actions: sekrety repozytorium.",
              file=sys.stderr)
        return 2

    client = Tuya(client_id, secret, region)
    all_devices = list_devices(client)

    if args.discover:
        print(f"Znaleziono {len(all_devices)} urządzeń w regionie {region}:\n")
        for dev in all_devices:
            codes = describe_codes(client, dev["id"])
            marker = "czujnik" if codes else "-"
            print(f"  {dev['id']}   {dev.get('name', '?')}")
            print(f"      kategoria: {dev.get('category', '?')}   rola: {marker}")
            for code, meta in codes.items():
                print(f"      pole: {code} ({meta['kind']}, {meta['unit']}, "
                      f"scale={meta['scale']})")
            print()
        return 0

    # Jeśli podano listę ID — bierzemy tylko je. Jeśli nie — same czujniki.
    wanted = [d.strip() for d in os.environ.get("TUYA_DEVICE_IDS", "").split(",") if d.strip()]
    if wanted:
        all_devices = [d for d in all_devices if d["id"] in wanted]

    end_ms = int(time.time() * 1000)
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=args.days)).timestamp() * 1000)

    DATA_DIR.mkdir(exist_ok=True)
    manifest_devices, collected = {}, []

    for dev in all_devices:
        device_id = dev["id"]
        name = dev.get("name") or device_id
        codes = describe_codes(client, device_id)
        if not codes:
            continue  # bramka, wtyczka, cokolwiek bez temperatury i wilgotności

        manifest_devices[device_id] = {
            "name": name,
            "codes": {c: {"kind": m["kind"], "unit": m["unit"]} for c, m in codes.items()},
        }

        logs = fetch_logs(client, device_id, start_ms, end_ms)
        kept = 0
        for entry in logs:
            code = entry.get("code")
            meta = codes.get(code)
            if not meta:
                continue
            try:
                value = float(entry["value"]) / (10 ** meta["scale"])
            except (TypeError, ValueError, KeyError):
                continue
            collected.append({
                "ts": iso(int(entry["event_time"])),
                "device_id": device_id,
                "code": code,
                "value": f"{value:g}",
            })
            kept += 1
        print(f"{name}: {kept} odczytów z ostatnich {args.days} dni")

    if not manifest_devices:
        print("\nŻadne urządzenie nie zgłosiło temperatury ani wilgotności.",
              file=sys.stderr)
        print("Uruchom `python fetch.py --discover` i sprawdź listę.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"\n[dry-run] {len(collected)} odczytów, nic nie zapisano.")
        return 0

    added = merge(collected)
    write_manifest(manifest_devices)
    print(f"\nDopisano {added} nowych odczytów ({len(collected) - added} już było).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except TuyaError as err:
        print(f"\n{err}", file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as err:
        print(f"\nProblem z siecią: {err}", file=sys.stderr)
        sys.exit(1)
