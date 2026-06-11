"""
Haalt realtime statistieken (volgers, bereik, impressies, profielbezoeken,
engagement) op via de Meta Graph API voor klanten met een ingevulde
`instagram_business_account_id` en/of `facebook_page_id` in de
"Klantprofielen Social Media"-sheet, en schrijft één rij per klant per run
weg naar het tabblad "Statistieken" (wordt aangemaakt als het nog niet bestaat).

Vereist in .env:
    GOOGLE_SHEETS_SPREADSHEET_ID
    GOOGLE_SERVICE_ACCOUNT_JSON
    META_ACCESS_TOKEN   (system user token, zie blueprints/meta_insights_koppeling.md)

Usage:
    python systems/fetch_meta_insights.py
    python systems/fetch_meta_insights.py --client-id aura_interieur

Klanten zonder instagram_business_account_id/facebook_page_id worden
overgeslagen (nog niet gekoppeld aan het Business Manager-portfolio).
"""

import argparse
import os
import sys
from datetime import date, timedelta

import gspread
from dotenv import load_dotenv

from meta_common import _graph_get, _graph_get_url, _page_access_tokens, _sheet_client

load_dotenv(override=True)

ID_COLUMNS = ["instagram_business_account_id", "facebook_page_id"]

STATS_SHEET_NAME = "Statistieken"
STATS_HEADERS = [
    "datum",
    "klant_id",
    "bedrijfsnaam",
    "instagram_volgers",
    "instagram_bereik_7d",
    "instagram_impressies_7d",
    "instagram_profielbezoeken_7d",
    "facebook_volgers",
    "facebook_bereik_7d",
    "facebook_impressies_7d",
    "facebook_engagement_7d",
]


def _ensure_columns(worksheet, headers: list[str], required: list[str]) -> dict[str, int]:
    """Zorgt dat de vereiste kolommen bestaan in `worksheet`. Geeft {kolomnaam: index}."""
    col_map = {h: i + 1 for i, h in enumerate(headers)}
    for col in required:
        if col not in col_map:
            worksheet.update_cell(1, len(headers) + 1, col)
            col_map[col] = len(headers) + 1
            headers.append(col)
    return col_map


def _ensure_stats_sheet(spreadsheet):
    try:
        ws = spreadsheet.worksheet(STATS_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=STATS_SHEET_NAME, rows=1000, cols=len(STATS_HEADERS))
        ws.append_row(STATS_HEADERS)
        ws.freeze(rows=1)
        print(f'Tabblad "{STATS_SHEET_NAME}" aangemaakt.')
    return ws


def _ig_insight_total(ig_id: str, metric: str, since, until, token: str):
    """Haalt een IG-insight op via metric_type=total_value (nieuwe Graph API-stijl)."""
    data = _graph_get(
        f"{ig_id}/insights",
        {
            "metric": metric,
            "period": "day",
            "metric_type": "total_value",
            "since": since.isoformat(),
            "until": until.isoformat(),
            "access_token": token,
        },
    )
    for entry in data.get("data", []):
        total = entry.get("total_value", {})
        if isinstance(total.get("value"), (int, float)):
            return total["value"]
    return None


def _instagram_stats(ig_id: str, token: str) -> dict:
    """Haalt volgers, bereik, profielweergaven en profielbezoeken (laatste 7 dagen) op."""
    out = {
        "instagram_volgers": "",
        "instagram_bereik_7d": "",
        "instagram_impressies_7d": "",
        "instagram_profielbezoeken_7d": "",
    }

    # Volgersaantal
    try:
        data = _graph_get(ig_id, {"fields": "followers_count", "access_token": token})
        out["instagram_volgers"] = data.get("followers_count", "")
    except RuntimeError as e:
        print(f"    ⚠️  IG volgers ophalen mislukt: {e}")

    # Bereik / profielweergaven / profielbezoeken laatste 7 dagen
    # (Graph API v21+: deze metrics vereisen metric_type=total_value;
    #  "impressions" is uitgefaseerd, vervangen door "views")
    until = date.today()
    since = until - timedelta(days=7)
    for metric, key in [
        ("reach", "instagram_bereik_7d"),
        ("views", "instagram_impressies_7d"),
        ("profile_views", "instagram_profielbezoeken_7d"),
    ]:
        try:
            value = _ig_insight_total(ig_id, metric, since, until, token)
            if value is not None:
                out[key] = value
        except RuntimeError as e:
            print(f"    ⚠️  IG {metric} ophalen mislukt: {e}")

    return out


def _facebook_stats(page_id: str, token: str, page_token: str = None) -> dict:
    """Haalt paginavolgers, bereik, paginaweergaven en engagement (laatste 7 dagen) op.

    Insights-endpoints (`/insights`) vereisen een Page Access Token, niet het
    systeemgebruiker-token zelf. `page_token` wordt opgehaald via /me/accounts.
    """
    out = {
        "facebook_volgers": "",
        "facebook_bereik_7d": "",
        "facebook_impressies_7d": "",
        "facebook_engagement_7d": "",
    }

    try:
        data = _graph_get(page_id, {"fields": "followers_count", "access_token": token})
        out["facebook_volgers"] = data.get("followers_count", "")
    except RuntimeError as e:
        print(f"    ⚠️  FB volgers ophalen mislukt: {e}")

    if not page_token:
        print("    ⚠️  Geen page access token gevonden — bereik/impressies/engagement overgeslagen")
        return out

    until = date.today()
    since = until - timedelta(days=7)
    for metric, key in [
        ("page_impressions_unique", "facebook_bereik_7d"),
        ("page_views_total", "facebook_impressies_7d"),
        ("page_post_engagements", "facebook_engagement_7d"),
    ]:
        try:
            data = _graph_get(
                f"{page_id}/insights",
                {
                    "metric": metric,
                    "period": "day",
                    "since": since.isoformat(),
                    "until": until.isoformat(),
                    "access_token": page_token,
                },
            )
            values = []
            for entry in data.get("data", []):
                for v in entry.get("values", []):
                    if isinstance(v.get("value"), (int, float)):
                        values.append(v["value"])
            if values:
                out[key] = sum(values)
        except RuntimeError as e:
            print(f"    ⚠️  FB {metric} ophalen mislukt: {e}")

    return out


def main():
    parser = argparse.ArgumentParser(description="Haal Meta-statistieken op en sla op in Google Sheet")
    parser.add_argument("--client-id", help="Verwerk alleen deze klant")
    args = parser.parse_args()

    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    token = os.getenv("META_ACCESS_TOKEN")

    if not spreadsheet_id:
        print("GOOGLE_SHEETS_SPREADSHEET_ID ontbreekt in .env", file=sys.stderr)
        sys.exit(1)
    if not token:
        print("META_ACCESS_TOKEN ontbreekt in .env — zie blueprints/meta_insights_koppeling.md", file=sys.stderr)
        sys.exit(1)

    gc = _sheet_client()
    spreadsheet = gc.open_by_key(spreadsheet_id)
    sheet = spreadsheet.sheet1

    headers = sheet.row_values(1)
    col_map = _ensure_columns(sheet, headers, ID_COLUMNS)
    headers = sheet.row_values(1)
    col_map = {h: i + 1 for i, h in enumerate(headers)}

    all_rows = sheet.get_all_values()
    klant_id_col = col_map.get("klant_id", 1)
    actief_col = col_map.get("actief", 3)

    stats_ws = _ensure_stats_sheet(spreadsheet)

    to_process = []
    for row in all_rows[1:]:
        if len(row) < actief_col or row[actief_col - 1].strip().upper() != "TRUE":
            continue
        klant_id = row[klant_id_col - 1].strip()
        if args.client_id and klant_id != args.client_id:
            continue

        client = {h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)}
        ig_id = client.get("instagram_business_account_id", "").strip()
        page_id = client.get("facebook_page_id", "").strip()

        if not ig_id and not page_id:
            continue  # nog niet gekoppeld aan Meta-portfolio

        to_process.append((klant_id, client, ig_id, page_id))

    if not to_process:
        print("Geen klanten met instagram_business_account_id of facebook_page_id gevonden.")
        print("Vul deze kolommen in (zie systems/list_meta_accounts.py) om te starten.")
        return

    print(f"{len(to_process)} klant(en) met Meta-koppeling te verwerken...\n")

    page_tokens = _page_access_tokens(token)

    today = date.today().isoformat()
    new_rows = []

    for klant_id, client, ig_id, page_id in to_process:
        bedrijfsnaam = client.get("bedrijfsnaam", klant_id)
        print(f"  {bedrijfsnaam} ({klant_id})")

        row_data = {h: "" for h in STATS_HEADERS}
        row_data["datum"] = today
        row_data["klant_id"] = klant_id
        row_data["bedrijfsnaam"] = bedrijfsnaam

        if ig_id:
            row_data.update(_instagram_stats(ig_id, token))
        if page_id:
            row_data.update(_facebook_stats(page_id, token, page_tokens.get(page_id)))

        new_rows.append([row_data[h] for h in STATS_HEADERS])

    if new_rows:
        stats_ws.append_rows(new_rows, value_input_option="RAW")
        print(f"\n{len(new_rows)} rij(en) toegevoegd aan tabblad '{STATS_SHEET_NAME}'.")


if __name__ == "__main__":
    main()
