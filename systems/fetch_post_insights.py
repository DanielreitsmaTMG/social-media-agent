"""
Haalt per klant de laatste posts (Instagram + Facebook) op met hun bereik en
engagement, en schrijft dit naar het tabblad "Statistieken_Posts". Dit voedt:

- Top-presterende posts per klant (dashboard)
- Engagement rate per post
- Beste posttijden (dag/uur-analyse op basis van post_datum + engagement_rate)
- Inzichten die teruggekoppeld kunnen worden naar de contentgenerator

Vereist in .env:
    GOOGLE_SHEETS_SPREADSHEET_ID
    GOOGLE_SERVICE_ACCOUNT_JSON
    META_ACCESS_TOKEN

Usage:
    python systems/fetch_post_insights.py
    python systems/fetch_post_insights.py --client-id DR-005
    python systems/fetch_post_insights.py --limit 15
"""

import argparse
import json
import os
import sys

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

POSTS_SHEET_NAME = "Statistieken_Posts"
POSTS_HEADERS = [
    "datum_opgehaald",
    "klant_id",
    "bedrijfsnaam",
    "platform",
    "post_datum",
    "type",
    "caption_kort",
    "link",
    "bereik",
    "interacties",
    "engagement_rate",
]


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


def _graph_get_url(url: str) -> dict:
    resp = requests.get(url, timeout=20)
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", "Onbekende Graph API-fout"))
    return data


def _page_access_tokens(token: str) -> dict:
    tokens = {}
    url = "me/accounts"
    params = {"access_token": token, "limit": 100}
    while url:
        try:
            data = _graph_get(url, params) if params else _graph_get_url(url)
        except RuntimeError as e:
            print(f"  ⚠️  Page access tokens ophalen mislukt: {e}")
            break
        for page in data.get("data", []):
            if page.get("id") and page.get("access_token"):
                tokens[page["id"]] = page["access_token"]
        url = data.get("paging", {}).get("next")
        params = None
    return tokens


def _ensure_posts_sheet(spreadsheet):
    try:
        ws = spreadsheet.worksheet(POSTS_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=POSTS_SHEET_NAME, rows=2000, cols=len(POSTS_HEADERS))
        ws.append_row(POSTS_HEADERS)
        ws.freeze(rows=1)
        print(f'Tabblad "{POSTS_SHEET_NAME}" aangemaakt.')
    return ws


def _short_caption(text: str, length: int = 90) -> str:
    text = (text or "").replace("\n", " ").strip()
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "…"


def _instagram_posts(ig_id: str, token: str, limit: int) -> list[dict]:
    rows = []
    try:
        data = _graph_get(
            f"{ig_id}/media",
            {
                "fields": "id,caption,timestamp,media_type,permalink,like_count,comments_count",
                "limit": limit,
                "access_token": token,
            },
        )
    except RuntimeError as e:
        print(f"    ⚠️  IG posts ophalen mislukt: {e}")
        return rows

    for media in data.get("data", []):
        media_id = media.get("id")
        like_count = media.get("like_count", 0) or 0
        comments_count = media.get("comments_count", 0) or 0

        bereik = None
        interacties = like_count + comments_count
        try:
            insights = _graph_get(
                f"{media_id}/insights",
                {"metric": "reach,saved,total_interactions", "access_token": token},
            )
            for entry in insights.get("data", []):
                values = entry.get("values", [])
                if not values:
                    continue
                value = values[0].get("value")
                if entry.get("name") == "reach":
                    bereik = value
                elif entry.get("name") == "total_interactions":
                    interacties = value
        except RuntimeError as e:
            print(f"    ⚠️  IG media-insights ({media_id}) mislukt: {e}")

        engagement_rate = round(interacties / bereik, 4) if bereik else None

        rows.append({
            "platform": "instagram",
            "post_datum": media.get("timestamp", "")[:10],
            "type": media.get("media_type", ""),
            "caption_kort": _short_caption(media.get("caption", "")),
            "link": media.get("permalink", ""),
            "bereik": bereik,
            "interacties": interacties,
            "engagement_rate": engagement_rate,
        })

    return rows


def _facebook_posts(page_id: str, page_token: str, limit: int) -> list[dict]:
    rows = []
    if not page_token:
        return rows
    try:
        data = _graph_get(
            f"{page_id}/posts",
            {
                "fields": "id,message,created_time,permalink_url,likes.summary(true),comments.summary(true),shares",
                "limit": limit,
                "access_token": page_token,
            },
        )
    except RuntimeError as e:
        print(f"    ⚠️  FB posts ophalen mislukt: {e}")
        return rows

    for post in data.get("data", []):
        post_id = post.get("id")
        likes = post.get("likes", {}).get("summary", {}).get("total_count", 0) or 0
        comments = post.get("comments", {}).get("summary", {}).get("total_count", 0) or 0
        shares = post.get("shares", {}).get("count", 0) or 0
        interacties = likes + comments + shares

        bereik = None
        try:
            insights = _graph_get(
                f"{post_id}/insights",
                {"metric": "post_impressions_unique", "access_token": page_token},
            )
            for entry in insights.get("data", []):
                values = entry.get("values", [])
                if values:
                    bereik = values[0].get("value")
        except RuntimeError as e:
            print(f"    ⚠️  FB post-insights ({post_id}) mislukt: {e}")

        engagement_rate = round(interacties / bereik, 4) if bereik else None

        rows.append({
            "platform": "facebook",
            "post_datum": post.get("created_time", "")[:10],
            "type": "post",
            "caption_kort": _short_caption(post.get("message", "")),
            "link": post.get("permalink_url", ""),
            "bereik": bereik,
            "interacties": interacties,
            "engagement_rate": engagement_rate,
        })

    return rows


def main():
    parser = argparse.ArgumentParser(description="Haal post-insights op en sla op in Google Sheet")
    parser.add_argument("--client-id", help="Verwerk alleen deze klant")
    parser.add_argument("--limit", type=int, default=10, help="Aantal recente posts per platform (default 10)")
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

    posts_ws = _ensure_posts_sheet(spreadsheet)

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
            continue

        to_process.append((klant_id, client, ig_id, page_id))

    if not to_process:
        print("Geen klanten met Meta-koppeling gevonden.")
        return

    print(f"{len(to_process)} klant(en) te verwerken...\n")

    page_tokens = _page_access_tokens(token)

    from datetime import date
    today = date.today().isoformat()
    new_rows = []

    for klant_id, client, ig_id, page_id in to_process:
        bedrijfsnaam = client.get("bedrijfsnaam", klant_id)
        print(f"  {bedrijfsnaam} ({klant_id})")

        posts = []
        if ig_id:
            posts += _instagram_posts(ig_id, token, args.limit)
        if page_id:
            posts += _facebook_posts(page_id, page_tokens.get(page_id), args.limit)

        for post in posts:
            new_rows.append([
                today,
                klant_id,
                bedrijfsnaam,
                post["platform"],
                post["post_datum"],
                post["type"],
                post["caption_kort"],
                post["link"],
                post["bereik"] if post["bereik"] is not None else "",
                post["interacties"],
                post["engagement_rate"] if post["engagement_rate"] is not None else "",
            ])

        print(f"    {len(posts)} posts opgehaald")

    if new_rows:
        posts_ws.append_rows(new_rows, value_input_option="RAW")
        print(f"\n{len(new_rows)} rij(en) toegevoegd aan tabblad '{POSTS_SHEET_NAME}'.")


if __name__ == "__main__":
    main()
