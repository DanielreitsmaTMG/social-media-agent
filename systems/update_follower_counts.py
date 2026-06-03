"""
Scraped volgersaantallen per klant van LinkedIn, Instagram en Facebook
en slaat ze op in de Google Sheet (kolommen: linkedin_volgers, instagram_volgers, facebook_volgers).

Draait op de Mac (geen datacenter-IP) zodat Social Blade en LinkedIn niet blokkeren.
Wordt wekelijks uitgevoerd als onderdeel van de pipeline.

Usage:
    python systems/update_follower_counts.py
    python systems/update_follower_counts.py --client-id antwan_tuinprojecten
"""

import argparse
import json
import os
import re
import sys
import time
from urllib.parse import urlparse

from typing import Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
import gspread

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
}

REQUIRED_COLUMNS = ["linkedin_volgers", "instagram_volgers", "facebook_volgers"]


def _fetch(url: str) -> Optional[BeautifulSoup]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        if r.status_code == 200:
            return BeautifulSoup(r.text, "html.parser")
    except Exception:
        pass
    return None


def _parse_count(text: str) -> str:
    if not text:
        return ""
    for pattern in [
        r"([\d.,]+[KkMm]?)\s*(?:followers|volgers|abonnees)",
        r"([\d.,]+[KkMm]?)\s*(?:likes|vind-ik-leuks|fans)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).replace(",", ".")
    return ""


def _extract_handle(url: str) -> str:
    if not url:
        return ""
    parts = [p for p in urlparse(url).path.strip("/").split("/") if p]
    return parts[0] if parts else ""


def _linkedin_count(url: str) -> str:
    if not url:
        return ""
    soup = _fetch(url)
    if not soup:
        return ""
    for attr, name in [("property", "og:description"), ("name", "description")]:
        tag = soup.find("meta", {attr: name})
        if tag and tag.get("content"):
            count = _parse_count(tag["content"])
            if count:
                return count
    return ""


def _socialblade_count(platform: str, handle: str) -> str:
    if not handle:
        return ""
    paths = {"instagram": "instagram/user", "facebook": "facebook/page"}
    path = paths.get(platform)
    if not path:
        return ""
    soup = _fetch(f"https://socialblade.com/{path}/{handle}")
    if not soup:
        return ""
    text = soup.get_text(" ", strip=True)
    m = re.search(r"([\d,]+)\s*(?:Followers|Subscriber)", text, re.IGNORECASE)
    if m:
        return m.group(1).replace(",", ".")
    return ""


def get_follower_counts(client: dict) -> dict:
    counts = {"linkedin_volgers": "", "instagram_volgers": "", "facebook_volgers": ""}

    linkedin_url  = client.get("linkedin_url", "")
    instagram_url = client.get("instagram_url", "")
    facebook_url  = client.get("facebook_url", "")

    if linkedin_url:
        counts["linkedin_volgers"] = _linkedin_count(linkedin_url)

    if instagram_url:
        handle = _extract_handle(instagram_url)
        counts["instagram_volgers"] = _socialblade_count("instagram", handle)

    if facebook_url:
        handle = _extract_handle(facebook_url)
        counts["facebook_volgers"] = _socialblade_count("facebook", handle)

    return counts


def _sheet_client(service_account_json: str):
    creds = Credentials.from_service_account_info(
        json.loads(service_account_json), scopes=SCOPES
    )
    return gspread.authorize(creds)


def _ensure_columns(worksheet, headers: list[str]) -> dict[str, int]:
    """Zorgt dat de vereiste kolommen bestaan. Geeft {kolomnaam: index} terug."""
    col_map = {}
    for i, h in enumerate(headers, start=1):
        col_map[h] = i

    for col in REQUIRED_COLUMNS:
        if col not in col_map:
            # Voeg kolom toe aan het einde
            worksheet.update_cell(1, len(headers) + 1, col)
            col_map[col] = len(headers) + 1
            headers.append(col)

    return col_map


def main():
    parser = argparse.ArgumentParser(description="Haal volgersaantallen op en sla op in Google Sheet")
    parser.add_argument("--client-id", help="Verwerk alleen deze klant")
    args = parser.parse_args()

    spreadsheet_id      = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    if not spreadsheet_id or not service_account_json:
        print("Credentials ontbreken in .env", file=sys.stderr)
        sys.exit(1)

    gc        = _sheet_client(service_account_json)
    sheet     = gc.open_by_key(spreadsheet_id).sheet1
    all_rows  = sheet.get_all_values()
    headers   = all_rows[0]

    col_map = _ensure_columns(sheet, headers)

    # Herlaad headers na eventuele toevoeging
    headers = sheet.row_values(1)
    col_map = {h: i + 1 for i, h in enumerate(headers)}

    klant_id_col = col_map.get("klant_id", 1)
    actief_col   = col_map.get("actief", 3)

    to_process = []
    for row_idx, row in enumerate(all_rows[1:], start=2):
        if len(row) < actief_col:
            continue
        if row[actief_col - 1].strip().upper() != "TRUE":
            continue
        klant_id = row[klant_id_col - 1].strip()
        if args.client_id and klant_id != args.client_id:
            continue

        # Bouw client dict
        client = {h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)}
        to_process.append((row_idx, klant_id, client))

    print(f"{len(to_process)} klanten te verwerken...")

    for i, (row_idx, klant_id, client) in enumerate(to_process, 1):
        bedrijfsnaam = client.get("bedrijfsnaam", klant_id)
        print(f"  [{i}/{len(to_process)}] {bedrijfsnaam}...", end=" ", flush=True)

        counts = get_follower_counts(client)

        # Schrijf terug naar sheet
        updates = []
        for col_name, value in counts.items():
            if col_name in col_map:
                col_letter = gspread.utils.rowcol_to_a1(row_idx, col_map[col_name])[:-1]
                updates.append({
                    "range": f"{col_letter}{row_idx}",
                    "values": [[value]],
                })

        if updates:
            sheet.batch_update(updates, value_input_option="RAW")

        results = " | ".join(
            f"{k.replace('_volgers','')}: {v or '—'}"
            for k, v in counts.items()
        )
        print(f"✓  {results}")

        if i < len(to_process):
            time.sleep(1.5)

    print(f"\nKlaar. Volgersaantallen opgeslagen in Google Sheet.")


if __name__ == "__main__":
    main()
