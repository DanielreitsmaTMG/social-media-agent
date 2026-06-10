"""
Genereert per klant een kort, AI-gebaseerd inzicht ("welke onderwerpen/insteken/
formats presteren goed") op basis van de best presterende posts uit het tabblad
"Posts_Statistieken", en schrijft dit naar de kolom `prestatie_inzichten` in de
klanten-sheet (sheet1). Dit wordt vervolgens automatisch meegenomen door
`generate_weekly_posts.py` als extra context bij het genereren van nieuwe content
(zie `_build_prompt`).

Sluit zo de loop: statistieken -> inzichten -> betere content.

Vereist in .env:
    GOOGLE_SHEETS_SPREADSHEET_ID
    GOOGLE_SERVICE_ACCOUNT_JSON
    ANTHROPIC_API_KEY

Usage:
    python systems/update_performance_insights.py
    python systems/update_performance_insights.py --client-id DR-005
"""

import argparse
import json
import os
import sys

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv(override=True)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

POSTS_SHEET_NAME = "Posts_Statistieken"
INSIGHTS_COLUMN = "prestatie_inzichten"
MODEL = "claude-haiku-4-5"


def _sheet_client():
    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not service_account_json:
        raise EnvironmentError("GOOGLE_SERVICE_ACCOUNT_JSON ontbreekt in .env")
    creds = Credentials.from_service_account_info(
        json.loads(service_account_json), scopes=SCOPES
    )
    return gspread.authorize(creds)


def _ensure_column(worksheet, headers: list[str], column: str) -> dict[str, int]:
    col_map = {h: i + 1 for i, h in enumerate(headers)}
    if column not in col_map:
        worksheet.update_cell(1, len(headers) + 1, column)
        col_map[column] = len(headers) + 1
        headers.append(column)
    return col_map


def _to_float(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _generate_insight(api_key: str, bedrijfsnaam: str, top_posts: list[dict]) -> str:
    import anthropic

    lines = []
    for p in top_posts:
        rate = p.get("engagement_rate")
        rate_str = f"{rate:.1%}" if rate is not None else "onbekend"
        lines.append(
            f"- ({p.get('platform')}, {p.get('post_datum')}, type: {p.get('type')}, "
            f"engagement rate: {rate_str}): \"{p.get('caption_kort')}\""
        )

    prompt = (
        f"Je bent een social media-strateeg. Hieronder staan de best presterende recente "
        f"posts van klant '{bedrijfsnaam}', gesorteerd op engagement rate:\n\n"
        + "\n".join(lines)
        + "\n\nSchrijf in het Nederlands een kort advies (max 2-3 zinnen) over welke "
        "onderwerpen, invalshoeken of contentformats blijkbaar goed aanslaan bij deze "
        "doelgroep, zodat dit als richtlijn kan dienen voor nieuwe content. Wees concreet "
        "en actiegericht. Geen opsomming, alleen lopende tekst, geen inleidende zin zoals "
        "'Hier is...'."
    )

    ac = anthropic.Anthropic(api_key=api_key)
    message = ac.messages.create(
        model=MODEL,
        max_tokens=250,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def main():
    parser = argparse.ArgumentParser(description="Genereer prestatie-inzichten per klant")
    parser.add_argument("--client-id", help="Verwerk alleen deze klant")
    parser.add_argument("--top-n", type=int, default=5, help="Aantal top-posts om te analyseren (default 5)")
    args = parser.parse_args()

    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not spreadsheet_id:
        print("GOOGLE_SHEETS_SPREADSHEET_ID ontbreekt in .env", file=sys.stderr)
        sys.exit(1)
    if not api_key:
        print("ANTHROPIC_API_KEY ontbreekt in .env", file=sys.stderr)
        sys.exit(1)

    gc = _sheet_client()
    spreadsheet = gc.open_by_key(spreadsheet_id)
    sheet = spreadsheet.sheet1

    try:
        posts_ws = spreadsheet.worksheet(POSTS_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        print(f"Tabblad '{POSTS_SHEET_NAME}' bestaat nog niet. Draai eerst fetch_post_insights.py.", file=sys.stderr)
        sys.exit(1)

    posts_records = posts_ws.get_all_records(default_blank="")

    headers = sheet.row_values(1)
    col_map = _ensure_column(sheet, headers, INSIGHTS_COLUMN)
    headers = sheet.row_values(1)
    col_map = {h: i + 1 for i, h in enumerate(headers)}
    all_rows = sheet.get_all_values()

    klant_id_col = col_map.get("klant_id", 1)
    actief_col = col_map.get("actief", 3)
    bedrijfsnaam_col = col_map.get("bedrijfsnaam", 2)

    to_process = []
    for row_idx, row in enumerate(all_rows[1:], start=2):
        if len(row) < actief_col or row[actief_col - 1].strip().upper() != "TRUE":
            continue
        klant_id = row[klant_id_col - 1].strip()
        if args.client_id and klant_id != args.client_id:
            continue
        bedrijfsnaam = row[bedrijfsnaam_col - 1].strip() if len(row) >= bedrijfsnaam_col else klant_id
        to_process.append((row_idx, klant_id, bedrijfsnaam))

    if not to_process:
        print("Geen klanten gevonden om te verwerken.")
        return

    print(f"{len(to_process)} klant(en) te verwerken...\n")

    updates = []
    for row_idx, klant_id, bedrijfsnaam in to_process:
        client_posts = [p for p in posts_records if p.get("klant_id") == klant_id]
        for p in client_posts:
            p["engagement_rate"] = _to_float(p.get("engagement_rate"))

        ranked = sorted(
            [p for p in client_posts if p.get("engagement_rate") is not None],
            key=lambda p: p["engagement_rate"], reverse=True,
        )

        if not ranked:
            print(f"  {bedrijfsnaam} ({klant_id}): geen post-data, overgeslagen")
            continue

        top_posts = ranked[: args.top_n]
        try:
            insight = _generate_insight(api_key, bedrijfsnaam, top_posts)
        except Exception as e:
            print(f"  {bedrijfsnaam} ({klant_id}): ⚠️  AI-inzicht mislukt: {e}")
            continue

        cell = gspread.utils.rowcol_to_a1(row_idx, col_map[INSIGHTS_COLUMN])
        updates.append({"range": cell, "values": [[insight]]})
        print(f"  {bedrijfsnaam} ({klant_id}): {insight[:100]}...")

    if updates:
        sheet.batch_update(updates, value_input_option="RAW")
        print(f"\n{len(updates)} klant(en) bijgewerkt in kolom '{INSIGHTS_COLUMN}'.")


if __name__ == "__main__":
    main()
