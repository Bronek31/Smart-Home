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

REGIONS = {
    "eu": "https://openapi.tuyaeu.com",
    "we": "https://openapi-weaz.tuyaeu.com",
    "us": "https://openapi.tuyaus.com",
    "ue": "https://openapi-ueaz.tuyaus.com",
    "in": "https://openapi.tuyain.com",
    "cn": "https://openapi.tuyacn.com",
}

DATA_DIR = Path("data")
MANIFEST = DATA_DIR / "index.json"
FIELDS = ["ts", "device_id", "code", "value"]
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
RATE_LIMIT_CODES = {40000309, 1104, 2009}
TEMP_UNITS = {"°c", "℃", "c", "°f", "℉", "f"}
HUM_UNITS = {"%", "％"}
KNOWN_TEMP = {"va_temperature", "temp_current", "temper_value"}
KNOWN_HUM = {"va_humidity", "humidity_value", "humidity_current"}
NOT_A_SENSOR = (
    "colour", "color", "bright", "work_mode", "scene", "countdown",
    "set", "correct", "calibration", "alarm", "upper", "lower", "unit_convert",
)


def classify(code: str, unit: str) -> str | None:
    low, u = code.lower(), (unit or "").strip().lower()
    if any(bad in low for bad in NOT_A_SENSOR):
        return None
    if "battery" in low:
        return "battery"
    if low in KNOWN_TEMP or ("temp" in low and u in TEMP_UNITS):
        return "temp"
    if low in KNOWN_HUM or ("humi" in low and u in HUM_UNITS):
        return "hum"
    return None


class TuyaError(RuntimeError):
    pass


class Tuya:
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
        self.min_gap = float(os.environ.get("TUYA_MIN_GAP", "1.2"))
        self.last_call = 0.0
        self.log_api = None

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

    def _throttle(self) -> None:
        wait = self.min_gap - (time.monotonic() - self.last_call)
        if wait > 0:
            time.sleep(wait)
        self.last_call = time.monotonic()

    def get(self, path: str, params: dict | None = None, _retry: bool = True) -> dict:
        if not self.token or time.time() > self.token_expires - 60:
            self._refresh_token()
        full = path
        if params:
            query = "&".join(
                f"{k}={params[k]}" for k in sorted(params) if params[k] is not None
            )
            full = f"{path}?{query}"
        for attempt in range(5):
            self._throttle()
            resp = self.session.get(
                self.base + full, headers=self._headers("GET", full, True), timeout=30
            )
            data = resp.json()
            if data.get("success"):
                return data
            if data.get("code") in RATE_LIMIT_CODES:
                pause = min(3 * (2 ** attempt), 30)
                print(f"  limit zapytań Tuya, czekam {pause} s…", flush=True)
                time.sleep(pause)
                continue
            if data.get("code") in (1010, 1013) and _retry:
                self.token = ""
                return self.get(path, params, _retry=False)
            return data
        return data


def explain(data: dict) -> str:
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


def list_devices(client: Tuya) -> list[dict]:
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
        unit = spec.get("unit") or ""
        kind = classify(code, unit)
        if kind is None:
            continue
        codes[code] = {
            "kind": kind,
            "unit": unit or {"temp": "°C", "hum": "%", "battery": "%"}[kind],
            "scale": int(spec.get("scale", 0) or 0),
        }
    return codes


def fetch_logs(client: Tuya, device_id: str, start_ms: int, end_ms: int) -> list[dict]:
    if client.log_api is None:
        probe = _logs(client, "v2", device_id, start_ms, end_ms)
        if probe is not None:
            client.log_api = "v2"
            return probe
        client.log_api = "v1"
    rows = _logs(client, client.log_api, device_id, start_ms, end_ms)
    if rows is None:
        raise TuyaError(
            f"Endpoint logów ({client.log_api}) odmówił dla urządzenia {device_id}."
        )
    return rows


def _logs(client, version, device_id, start_ms, end_ms) -> list[dict] | None:
    out, cursor = [], None
    for _ in range(300):
        params = {"start_time": start_ms, "end_time": end_ms, "size": 100}
        if version == "v2":
            path = f"/v2.0/cloud/thing/{device_id}/report-logs"
            if cursor:
                params["last_row_key"] = cursor
        else:
            path = f"/v1.0/devices/{device_id}/logs"
            params["type"] = 7
            if cursor:
                params["start_row_key"] = cursor
        data = client.get(path, params)
        if not data.get("success"):
            if out:
                print(f"  uwaga: {explain(data)}", flush=True)
                return out
            return None
        result = data.get("result") or {}
        out.extend(result.get("logs", []))
        if not (result.get("has_more") or result.get("has_next")):
            break
        cursor = result.get("last_row_key") or result.get("next_row_key")
        if not cursor:
            break
    return out


def parse_since(text: str) -> int:
    text = (text or "").strip()
    if not text:
        return 0
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise TuyaError(
            f"TUYA_SINCE ma zły format: {text!r}.\n"
            "Użyj np. 2026-08-13 albo 2026-08-12T21:30+02:00 (czas polski latem)."
        )
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000)


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


def purge_before(since_ms: int) -> int:
    """Usuwa z istniejących CSV wszystkie rekordy wcześniejsze niż TUYA_SINCE."""
    if not since_ms:
        return 0
    removed = 0
    for path in DATA_DIR.glob("*.csv"):
        month = path.stem
        rows = load_month(month)
        if not rows:
            continue
        kept = []
        for row in rows:
            try:
                when = int(datetime.fromisoformat(row["ts"].replace("Z", "+00:00")).timestamp() * 1000)
            except (KeyError, ValueError, TypeError):
                kept.append(row)
                continue
            if when < since_ms:
                removed += 1
            else:
                kept.append(row)
        if len(kept) != len(rows):
            save_month(month, kept)
    return removed


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
            {"updated": iso(int(time.time() * 1000)), "months": months, "devices": devices},
            ensure_ascii=False, indent=2,
        ) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Kolektor odczytów z chmury Tuya")
    parser.add_argument("--discover", action="store_true", help="wypisz urządzenia i zakończ")
    parser.add_argument("--days", type=int, default=7, help="ile dni wstecz pobrać (Tuya trzyma maksymalnie 7)")
    parser.add_argument("--dry-run", action="store_true", help="pokaż, co by się zapisało, ale nie zapisuj")
    args = parser.parse_args()

    client_id = os.environ.get("TUYA_CLIENT_ID", "").strip()
    secret = os.environ.get("TUYA_CLIENT_SECRET", "").strip()
    region = os.environ.get("TUYA_REGION", "eu").strip().lower()
    if not client_id or not secret:
        print("Brakuje TUYA_CLIENT_ID albo TUYA_CLIENT_SECRET.", file=sys.stderr)
        print("Lokalnie: export TUYA_CLIENT_ID=... ; w Actions: sekrety repozytorium.", file=sys.stderr)
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
                print(f"      pole: {code} ({meta['kind']}, {meta['unit']}, scale={meta['scale']})")
            print()
        return 0

    wanted = [d.strip() for d in os.environ.get("TUYA_DEVICE_IDS", "").split(",") if d.strip()]
    if wanted:
        all_devices = [d for d in all_devices if d["id"] in wanted]

    end_ms = int(time.time() * 1000)
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=args.days)).timestamp() * 1000)
    since_ms = parse_since(os.environ.get("TUYA_SINCE", ""))
    if since_ms:
        start_ms = max(start_ms, since_ms)
        print(f"Zbieram wyłącznie odczyty od {iso(since_ms)}.\n", flush=True)
        if since_ms >= end_ms:
            print("Granica leży w przyszłości — na razie nie ma czego zbierać.", file=sys.stderr)

    DATA_DIR.mkdir(exist_ok=True)
    removed = purge_before(since_ms)
    if removed:
        print(f"Usunięto {removed} starych odczytów sprzed TUYA_SINCE.", flush=True)

    manifest_devices, collected = {}, []
    cached = {}
    if MANIFEST.exists():
        try:
            for dev_id, entry in json.loads(MANIFEST.read_text(encoding="utf-8")).get("devices", {}).items():
                known = entry.get("codes") or {}
                if all("scale" in meta for meta in known.values()) and known:
                    cached[dev_id] = {c: dict(m) for c, m in known.items()}
        except (ValueError, OSError):
            pass

    failed = []
    for dev in all_devices:
        device_id = dev["id"]
        name = dev.get("name") or device_id
        codes = cached.get(device_id) or describe_codes(client, device_id)
        if not any(m["kind"] in ("temp", "hum") for m in codes.values()):
            continue
        manifest_devices[device_id] = {
            "name": name,
            "codes": {c: {"kind": m["kind"], "unit": m["unit"], "scale": m["scale"]} for c, m in codes.items()},
        }
        try:
            logs = fetch_logs(client, device_id, start_ms, end_ms)
        except (TuyaError, requests.RequestException) as err:
            failed.append(name)
            print(f"{name}: pominięty — {err}", flush=True)
            continue
        kept = 0
        for entry in logs:
            code = entry.get("code")
            meta = codes.get(code)
            if not meta:
                continue
            raw = entry.get("value")
            try:
                value = f'{float(raw) / (10 ** meta["scale"]):g}'
            except (TypeError, ValueError):
                if meta["kind"] != "battery" or raw is None:
                    continue
                value = str(raw)
            when = int(entry["event_time"])
            if since_ms and when < since_ms:
                continue
            collected.append({"ts": iso(when), "device_id": device_id, "code": code, "value": value})
            kept += 1
        print(f"{name}: {kept} odczytów z ostatnich {args.days} dni", flush=True)

    if not manifest_devices:
        print("\nŻadne urządzenie nie zgłosiło temperatury ani wilgotności.", file=sys.stderr)
        print("Uruchom `python fetch.py --discover` i sprawdź listę.", file=sys.stderr)
        return 1
    if args.dry_run:
        print(f"\n[dry-run] {len(collected)} odczytów, nic nie zapisano.")
        return 0

    added = merge(collected)
    write_manifest(manifest_devices)
    print(f"\nDopisano {added} nowych odczytów ({len(collected) - added} już było).")
    if failed:
        print(f"Pominięte czujniki: {', '.join(failed)}.")
        print("Dane pozostałych zostały zapisane. Następny przebieg nadrobi resztę — okno 7 dni jeszcze się nie zamknęło.")
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
