"""
Gedeelde helpers voor de Meta Graph API (Instagram & Facebook) en Google
Sheets-toegang. Gebruikt door fetch_meta_insights.py, fetch_post_insights.py
en publish_scheduled_posts.py — houdt de Meta-laag op één plek zodat
rate-limit-fixes, API-versie-upgrades en auth-eigenaardigheden niet meermaals
gefixt hoeven te worden.

Vereist in .env:
    GOOGLE_SERVICE_ACCOUNT_JSON
    META_ACCESS_TOKEN
"""

import json
import os

import gspread
import requests
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

GRAPH_VERSION = "v21.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"


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


def _graph_post(path: str, params: dict) -> dict:
    resp = requests.post(f"{GRAPH_URL}/{path}", data=params, timeout=30)
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", "Onbekende Graph API-fout"))
    return data


def _page_access_tokens(token: str) -> dict:
    """Haalt per Facebook-pagina een Page Access Token op (nodig voor /insights en publiceren)."""
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
