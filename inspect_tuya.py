#!/usr/bin/env python3
"""Jednorazowa diagnostyka tego, co faktycznie zwraca Tuya API.

Nie zapisuje danych do data/. Raport zawiera specyfikację DP, aktualny status
urządzenia oraz kilka ostatnich surowych raportów z endpointu logów.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fetch import TuyaError, Tuya, explain, list_devices, _logs


def utc_iso(ms: int | str | None) -> str | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def get_spec(client: Tuya, device_id: str) -> dict:
    return client.get(f"/v1.0/devices/{device_id}/specifications")


def get_status(client: Tuya, device_id: str) -> dict:
    return client.get(f"/v1.0/devices/{device_id}/status")


def get_detail(client: Tuya, device_id: str) -> dict:
    return client.get(f"/v1.0/devices/{device_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnostyka Tuya API")
    parser.add_argument("--hours", type=int, default=24, help="ile godzin logów przejrzeć")
    parser.add_argument("--samples", type=int, default=10, help="ile ostatnich logów pokazać na urządzenie")
    parser.add_argument("--output", default="tuya_debug.json", help="plik raportu JSON")
    args = parser.parse_args()

    client_id = os.environ.get("TUYA_CLIENT_ID", "").strip()
    secret = os.environ.get("TUYA_CLIENT_SECRET", "").strip()
    region = os.environ.get("TUYA_REGION", "eu").strip().lower()
    if not client_id or not secret:
        raise TuyaError("Brakuje TUYA_CLIENT_ID albo TUYA_CLIENT_SECRET.")

    client = Tuya(client_id, secret, region)
    devices = list_devices(client)
    wanted = {x.strip() for x in os.environ.get("TUYA_DEVICE_IDS", "").split(",") if x.strip()}
    if wanted:
        devices = [d for d in devices if d.get("id") in wanted]

    end_ms = int(time.time() * 1000)
    start_ms = int((datetime.now(timezone.utc) - timedelta(hours=max(1, args.hours))).timestamp() * 1000)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "region": region,
        "device_count": len(devices),
        "window": {"start": utc_iso(start_ms), "end": utc_iso(end_ms)},
        "devices": [],
    }

    for device in devices:
        device_id = device.get("id")
        name = device.get("name") or device_id
        item = {
            "id": device_id,
            "name": name,
            "category": device.get("category"),
            "product_id": device.get("product_id"),
            "online_from_device_list": device.get("online"),
        }

        spec = get_spec(client, device_id)
        item["specification_api"] = spec

        status = get_status(client, device_id)
        item["status_api"] = status

        detail = get_detail(client, device_id)
        item["device_detail_api"] = detail

        # Pobierz kilka ostatnich raportów bez filtrowania kodów DP, żeby zobaczyć
        # także pola, których fetch.py obecnie nie rozpoznaje (np. bateria/RSSI).
        logs = _logs(client, "v2", device_id, start_ms, end_ms)
        log_api = "v2"
        if logs is None:
            logs = _logs(client, "v1", device_id, start_ms, end_ms)
            log_api = "v1"
        item["log_api"] = log_api if logs is not None else None
        item["recent_logs"] = (logs or [])[-args.samples:]
        item["recent_log_count"] = len(logs or [])
        report["devices"].append(item)

    output = Path(args.output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nZapisano raport: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TuyaError as exc:
        raise SystemExit(f"Błąd Tuya: {exc}")
