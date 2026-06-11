"""
Uploadt gegenereerde posts naar een apart tabblad in de Google Sheet.
Maakt het tabblad aan als het niet bestaat; overschrijft als het al bestaat.

Tabbladnaam: Posts_YYYY_WXX  (bijv. Posts_2026_W24)

Kolommen:
  klant_id | bedrijfsnaam | platform | dag | publicatiedatum | caption | hashtags |
  status | opmerkingen | beeldtitel | geplande_datum | geplande_tijd | afbeelding_url |
  afbeelding_drive_id | publicatie_status | meta_post_id | publicatie_log

Status begint als 'concept'. Via het dashboard kan dit 'goedgekeurd' of 'afgewezen' worden.
De planningskolommen (geplande_datum t/m publicatie_log) worden later vanuit de
"📅 Planning"-tab in het dashboard ingevuld (zie blueprints/content_planning.md).

Usage:
    python systems/upload_posts_to_sheets.py
    python systems/upload_posts_to_sheets.py --posts-file intermediates/posts_2026-06-03.json
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
import gspread

load_dotenv(override=True)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "klant_id", "bedrijfsnaam", "platform", "dag",
    "publicatiedatum", "caption", "hashtags", "status", "opmerkingen", "beeldtitel",
    "geplande_datum", "geplande_tijd", "afbeelding_url", "afbeelding_drive_id",
    "publicatie_status", "meta_post_id", "publicatie_log",
]

MONTHS_NL = [
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
]

DAYS_NL = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag"]


def _format_date_nl(d: date) -> str:
    return f"{d.day} {MONTHS_NL[d.month - 1]} {d.year}"


def _day_to_date(dag: str, week_start: date) -> str:
    """Converteert dagnaam naar exacte datum binnen de targetweek."""
    for i, name in enumerate(DAYS_NL):
        if name.lower() == dag.lower():
            return _format_date_nl(week_start + timedelta(days=i))
    return dag


def _sheet_client(service_account_json: str):
    creds = Credentials.from_service_account_info(
        json.loads(service_account_json), scopes=SCOPES
    )
    return gspread.authorize(creds)


def _latest_file(pattern: str):
    files = sorted(Path("intermediates").glob(pattern), reverse=True)
    return str(files[0]) if files else None


def upload_posts(posts_data: dict, spreadsheet_id: str, service_account_json: str) -> str:
    """Uploadt alle posts naar een nieuw tabblad. Geeft de tabbladnaam terug."""
    # Bepaal week-info uit de eerste klant
    first = next(iter(posts_data.values()))
    week_start = date.fromisoformat(first["week_start"])
    week_nr = week_start.isocalendar()[1]
    tab_name = f"Posts_{week_start.year}_W{week_nr:02d}"

    client = _sheet_client(service_account_json)
    spreadsheet = client.open_by_key(spreadsheet_id)

    # Maak tabblad aan of wis bestaande inhoud
    try:
        worksheet = spreadsheet.worksheet(tab_name)
        worksheet.clear()
        print(f"Bestaand tabblad gewist: {tab_name}")
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=tab_name, rows=500, cols=len(HEADERS))
        print(f"Nieuw tabblad aangemaakt: {tab_name}")

    rows = [HEADERS]

    for klant_id, data in posts_data.items():
        client_info = data["client"]
        bedrijfsnaam = client_info["bedrijfsnaam"]
        posts = data["posts"]

        for platform in ("instagram", "linkedin", "facebook"):
            for post in posts.get(platform, []):
                dag = post.get("dag", "")
                rows.append([
                    klant_id,
                    bedrijfsnaam,
                    platform,
                    dag,
                    _day_to_date(dag, week_start),
                    post.get("caption", ""),
                    post.get("hashtags", ""),
                    "concept",
                    "",
                    post.get("beeldtitel", ""),
                    "",  # geplande_datum
                    "",  # geplande_tijd
                    "",  # afbeelding_url
                    "",  # afbeelding_drive_id
                    "",  # publicatie_status
                    "",  # meta_post_id
                    "",  # publicatie_log
                ])

    worksheet.update(rows, value_input_option="RAW")

    # Opmaak: header vet, kolommen bevries
    worksheet.freeze(rows=1)
    worksheet.format("A1:Q1", {"textFormat": {"bold": True}})

    print(f"{len(rows) - 1} posts geüpload naar tabblad '{tab_name}'")
    return tab_name


def main():
    parser = argparse.ArgumentParser(description="Upload posts naar Google Sheets")
    parser.add_argument("--posts-file", help="Pad naar posts JSON")
    args = parser.parse_args()

    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    if not spreadsheet_id or not service_account_json:
        print("GOOGLE_SHEETS_SPREADSHEET_ID of GOOGLE_SERVICE_ACCOUNT_JSON ontbreekt in .env", file=sys.stderr)
        sys.exit(1)

    posts_file = args.posts_file or _latest_file("posts_*.json")
    if not posts_file:
        print("Geen posts-bestand gevonden. Voer eerst generate_weekly_posts.py uit.", file=sys.stderr)
        sys.exit(1)

    with open(posts_file, encoding="utf-8") as f:
        posts_data = json.load(f)

    print(f"Posts geladen: {len(posts_data)} klanten uit {posts_file}")
    tab = upload_posts(posts_data, spreadsheet_id, service_account_json)
    print(f"Klaar. Tabblad: {tab}")


if __name__ == "__main__":
    main()
