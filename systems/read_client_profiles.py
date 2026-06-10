"""
Reads all active client profiles from the "Klantprofielen Social Media" Google Sheet.

Usage:
    python systems/read_client_profiles.py
    python systems/read_client_profiles.py --output intermediates/clients_custom.json

Output: intermediates/clients_YYYY-MM-DD.json
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv(override=True)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

REQUIRED_COLUMNS = {
    "klant_id", "bedrijfsnaam", "actief", "taal",
    "instagram_posts_pw", "linkedin_posts_pw", "facebook_posts_pw",
    "toon", "doelgroep", "kernthemas", "vaste_hashtags", "vermijd",
    "google_doc_folder_id",
}

OPTIONAL_COLUMNS = {
    "extra_context",
    "website_url", "instagram_url", "facebook_url", "linkedin_url",
    "instagram_business_account_id", "facebook_page_id",
}


def _sheet_client():
    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not service_account_json:
        raise EnvironmentError("GOOGLE_SERVICE_ACCOUNT_JSON not set in .env")
    creds = Credentials.from_service_account_info(
        json.loads(service_account_json), scopes=SCOPES
    )
    return gspread.authorize(creds)


def read_profiles(spreadsheet_id: str) -> list[dict]:
    client = _sheet_client()
    sheet = client.open_by_key(spreadsheet_id).sheet1
    rows = sheet.get_all_records(default_blank="")

    active = []
    for i, row in enumerate(rows, start=2):
        if str(row.get("actief", "")).strip().upper() != "TRUE":
            continue

        missing = [col for col in REQUIRED_COLUMNS if col not in row]
        if missing:
            print(
                f"  Row {i} ({row.get('klant_id', '?')}): ontbrekende kolommen {missing} — overgeslagen",
                file=sys.stderr,
            )
            continue

        for platform in ("instagram", "linkedin", "facebook"):
            key = f"{platform}_posts_pw"
            try:
                row[key] = int(row[key])
            except (ValueError, TypeError):
                row[key] = 0

        for col in OPTIONAL_COLUMNS:
            row.setdefault(col, "")

        active.append(row)

    return active


def main():
    parser = argparse.ArgumentParser(description="Lees actieve klantprofielen uit Google Sheets")
    parser.add_argument("--output", help="Pad naar outputbestand")
    args = parser.parse_args()

    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    if not spreadsheet_id:
        raise EnvironmentError("GOOGLE_SHEETS_SPREADSHEET_ID not set in .env")

    print("Klantprofielen laden uit Google Sheets...")
    profiles = read_profiles(spreadsheet_id)
    print(f"{len(profiles)} actieve klanten gevonden.")

    output_path = args.output or f"intermediates/clients_{date.today()}.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)

    print(f"Opgeslagen: {output_path}")


if __name__ == "__main__":
    main()
