"""
Haalt de volgers-demografie (leeftijd, geslacht, land) op van gekoppelde
Instagram-accounts en schrijft dit naar het tabblad "Demografie".

Vereist in .env:
    GOOGLE_SHEETS_SPREADSHEET_ID
    GOOGLE_SERVICE_ACCOUNT_JSON
    META_ACCESS_TOKEN

Usage:
    python systems/fetch_audience_demographics.py
    python systems/fetch_audience_demographics.py --client-id DR-005

Let op: alleen beschikbaar voor Instagram (follower_demographics).
Facebook Pages bieden deze breakdown niet via dezelfde route.
"""

import argparse
import json
import os
import sys
from datetime import date

import gspread
import requests
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv(override=True)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

GRAPH_VERSION = "v21.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"

DEMO_SHEET_NAME = "Demografie"
DEMO_HEADERS = ["datum", "klant_id", "bedrijfsnaam", "dimensie", "waarde", "aantal"]

BREAKDOWNS = {
    "leeftijd_geslacht": "age,gender",
    "land": "country",
}


def _sheet_client():
    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not service_account_json:
        raise EnvironmentError("GOOGLE_SERVICE_ACCOUNT_JSON ontbreekt in .env")
    creds = Credentials.from_service_account_info(
        json.loads(service_account_json), scopes=SCOPES
    )
    return gspread.authorize(creds)


def _graph_get(path: str, params: dict) -> dict:
    resp = requests.get(f"{GRAPH_URL}/{path}", params=params, timeout=20)
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", "Onbekende Graph API-fout"))
    return data


def _ensure_demo_sheet(spreadsheet):
    try:
        ws = spreadsheet.worksheet(DEMO_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=DEMO_SHEET_NAME, rows=1000, cols=len(DEMO_HEADERS))
        ws.append_row(DEMO_HEADERS)
        ws.freeze(rows=1)
        print(f'Tabblad "{DEMO_SHEET_NAME}" aangemaakt.')
    return ws


def _demographics(ig_id: str, token: str) -> dict[str, list[tuple[str, int]]]:
    """Geeft per dimensie een lijst (waarde-label, aantal) terug."""
    out = {}
    for dim_key, breakdown in BREAKDOWNS.items():
        try:
            data = _graph_get(
                f"{ig_id}/insights",
                {
                    "metric": "follower_demographics",
                    "period": "lifetime",
                    "metric_type": "total_value",
                    "breakdown": breakdown,
                    "access_token": token,
                },
            )
        except RuntimeError as e:
            print(f"    ⚠️  Demografie ({dim_key}) ophalen mislukt: {e}")
            continue

        for entry in data.get("data", []):
            for bd in entry.get("total_value", {}).get("breakdowns", []):
                for result in bd.get("results", []):
                    label = "/".join(result.get("dimension_values", []))
                    value = result.get("value", 0)
                    out.setdefault(dim_key, []).append((label, value))

    return out


def main():
    parser = argparse.ArgumentParser(description="Haal volgers-demografie op en sla op in Google Sheet")
    parser.add_argument("--client-id", help="Verwerk alleen deze klant")
    args = parser.parse_args()

    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    token = os.getenv("META_ACCESS_TOKEN")

    if not spreadsheet_id:
        print("GOOGLE_SHEETS_SPREADSHEET_ID ontbreekt in .env", file=sys.stderr)
        sys.exit(1)
    if not token:
        print("META_ACCESS_TOKEN ontbreekt in .env", file=sys.stderr)
        sys.exit(1)

    gc = _sheet_client()
    spreadsheet = gc.open_by_key(spreadsheet_id)
    sheet = spreadsheet.sheet1

    headers = sheet.row_values(1)
    col_map = {h: i + 1 for i, h in enumerate(headers)}
    all_rows = sheet.get_all_values()
    klant_id_col = col_map.get("klant_id", 1)
    actief_col = col_map.get("actief", 3)

    demo_ws = _ensure_demo_sheet(spreadsheet)

    to_process = []
    for row in all_rows[1:]:
        if len(row) < actief_col or row[actief_col - 1].strip().upper() != "TRUE":
            continue
        klant_id = row[klant_id_col - 1].strip()
        if args.client_id and klant_id != args.client_id:
            continue

        client = {h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)}
        ig_id = client.get("instagram_business_account_id", "").strip()
        if not ig_id:
            continue

        to_process.append((klant_id, client, ig_id))

    if not to_process:
        print("Geen klanten met instagram_business_account_id gevonden.")
        return

    print(f"{len(to_process)} klant(en) te verwerken...\n")

    today = date.today().isoformat()
    new_rows = []

    for klant_id, client, ig_id in to_process:
        bedrijfsnaam = client.get("bedrijfsnaam", klant_id)
        print(f"  {bedrijfsnaam} ({klant_id})")

        demo = _demographics(ig_id, token)
        for dim_key, values in demo.items():
            for label, value in values:
                new_rows.append([today, klant_id, bedrijfsnaam, dim_key, label, value])

        print(f"    {sum(len(v) for v in demo.values())} datapunten")

    if new_rows:
        # Verwijder eerdere metingen van vandaag voor deze klanten (voorkom duplicaten bij herhaalde runs)
        existing = demo_ws.get_all_values()
        if len(existing) > 1:
            klant_ids_today = {r[1] for r in [row[:3] for row in new_rows]}
            keep = [existing[0]] + [
                r for r in existing[1:]
                if not (r[0] == today and r[1] in klant_ids_today)
            ]
            if len(keep) != len(existing):
                demo_ws.clear()
                demo_ws.append_rows(keep, value_input_option="RAW")

        demo_ws.append_rows(new_rows, value_input_option="RAW")
        print(f"\n{len(new_rows)} rij(en) toegevoegd aan tabblad '{DEMO_SHEET_NAME}'.")


if __name__ == "__main__":
    main()
