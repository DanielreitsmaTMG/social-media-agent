"""
Publiceert ingeplande posts (kolom `publicatie_status == "gepland"` in de
Posts_YYYY_WNN-tabbladen) automatisch naar Instagram en Facebook via de Meta
Graph API, zodra `geplande_datum` + `geplande_tijd` (Europe/Amsterdam) is
bereikt.

Bedoeld om periodiek te draaien via GitHub Actions
(.github/workflows/publish_scheduled_posts.yml, elke 15 minuten).

Vereist in .env / repo secrets:
    GOOGLE_SHEETS_SPREADSHEET_ID
    GOOGLE_SERVICE_ACCOUNT_JSON
    META_ACCESS_TOKEN

Statusmachine (kolom `publicatie_status`):
    "" / "gepland" -> "bezig" -> "gepubliceerd" (+ meta_post_id)
                              -> "mislukt"      (+ publicatie_log, retry via dashboard)

Usage:
    python systems/publish_scheduled_posts.py
    python systems/publish_scheduled_posts.py --dry-run
"""

import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from meta_common import _graph_get, _graph_post, _page_access_tokens, _sheet_client

load_dotenv(override=True)

AMSTERDAM_TZ = ZoneInfo("Europe/Amsterdam")

# Kolomletters voor de planningskolommen K-Q in Posts_YYYY_WNN
# (zie systems/upload_posts_to_sheets.py / blueprints/content_planning.md)
COL_GEPLANDE_DATUM = "K"
COL_GEPLANDE_TIJD = "L"
COL_AFBEELDING_URL = "M"
COL_AFBEELDING_DRIVE_ID = "N"
COL_PUBLICATIE_STATUS = "O"
COL_META_POST_ID = "P"
COL_PUBLICATIE_LOG = "Q"


def _now_ams() -> datetime:
    return datetime.now(AMSTERDAM_TZ).replace(tzinfo=None)


def _is_due(post: dict, now: datetime) -> bool:
    geplande_datum = (post.get("geplande_datum") or "").strip()
    geplande_tijd = (post.get("geplande_tijd") or "09:00").strip()
    if not geplande_datum:
        return False
    try:
        scheduled = datetime.strptime(f"{geplande_datum} {geplande_tijd}", "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    return scheduled <= now


def _load_meta_accounts(spreadsheet) -> dict:
    """Geeft {klant_id: {"ig_id": ..., "page_id": ...}} terug uit sheet1."""
    sheet = spreadsheet.sheet1
    headers = sheet.row_values(1)
    col_map = {h: i + 1 for i, h in enumerate(headers)}
    klant_id_col = col_map.get("klant_id", 1)

    accounts = {}
    for row in sheet.get_all_values()[1:]:
        if len(row) < klant_id_col:
            continue
        klant_id = row[klant_id_col - 1].strip()
        if not klant_id:
            continue
        client = {h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)}
        accounts[klant_id] = {
            "ig_id": client.get("instagram_business_account_id", "").strip(),
            "page_id": client.get("facebook_page_id", "").strip(),
        }
    return accounts


def _publish_instagram(ig_id: str, image_url: str, caption: str, token: str) -> str:
    """Maakt een media-container aan en publiceert deze. Geeft de gepubliceerde post-id terug."""
    container = _graph_post(
        f"{ig_id}/media",
        {"image_url": image_url, "caption": caption, "access_token": token},
    )
    creation_id = container.get("id")
    if not creation_id:
        raise RuntimeError("Geen creation_id ontvangen van /media")

    result = _graph_post(
        f"{ig_id}/media_publish",
        {"creation_id": creation_id, "access_token": token},
    )
    post_id = result.get("id")
    if not post_id:
        raise RuntimeError("Geen post-id ontvangen van /media_publish")
    return post_id


def _publish_facebook(page_id: str, image_url: str, caption: str, page_token: str) -> str:
    """Plaatst een foto-post op de Facebook-pagina. Geeft de post-id terug."""
    result = _graph_post(
        f"{page_id}/photos",
        {"url": image_url, "caption": caption, "published": "true", "access_token": page_token},
    )
    post_id = result.get("post_id") or result.get("id")
    if not post_id:
        raise RuntimeError("Geen post-id ontvangen van /photos")
    return post_id


def main():
    parser = argparse.ArgumentParser(description="Publiceer ingeplande posts naar Instagram/Facebook")
    parser.add_argument("--dry-run", action="store_true", help="Toon wat er zou gebeuren, zonder te publiceren of de sheet bij te werken")
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

    accounts = _load_meta_accounts(spreadsheet)
    page_tokens = _page_access_tokens(token)

    now = _now_ams()
    print(f"Huidige tijd (Europe/Amsterdam): {now.isoformat(timespec='minutes')}")

    post_tabs = [ws for ws in spreadsheet.worksheets() if ws.title.startswith("Posts_")]
    if not post_tabs:
        print("Geen Posts_*-tabbladen gevonden.")
        return

    total_due = 0
    total_published = 0
    total_failed = 0

    for ws in post_tabs:
        records = ws.get_all_records(default_blank="")
        due_rows = [(i, r) for i, r in enumerate(records, start=2)
                    if r.get("publicatie_status", "").strip() == "gepland" and _is_due(r, now)]
        if not due_rows:
            continue

        print(f"\n📄 {ws.title}: {len(due_rows)} post(en) klaar om te publiceren")
        total_due += len(due_rows)

        for row_idx, post in due_rows:
            klant_id = post.get("klant_id", "")
            bedrijfsnaam = post.get("bedrijfsnaam", klant_id)
            platform = post.get("platform", "")
            afbeelding_url = (post.get("afbeelding_url") or "").strip()
            caption = (post.get("caption") or "").strip()
            hashtags = (post.get("hashtags") or "").strip()
            full_caption = f"{caption}\n\n{hashtags}".strip() if hashtags else caption

            print(f"  Rij {row_idx}: {bedrijfsnaam} · {platform}")

            if not afbeelding_url:
                print("    ⚠️  Geen afbeelding_url ingevuld — overgeslagen")
                if not args.dry_run:
                    ws.batch_update([
                        {"range": f"{COL_PUBLICATIE_STATUS}{row_idx}", "values": [["mislukt"]]},
                        {"range": f"{COL_PUBLICATIE_LOG}{row_idx}", "values": [["Geen afbeelding geüpload"]]},
                    ], value_input_option="RAW")
                total_failed += 1
                continue

            account = accounts.get(klant_id, {})

            if args.dry_run:
                print(f"    [dry-run] zou publiceren naar {platform}")
                continue

            # Zet status op 'bezig' om dubbele publicatie bij overlappende runs te voorkomen
            ws.update(range_name=f"{COL_PUBLICATIE_STATUS}{row_idx}", values=[["bezig"]], value_input_option="RAW")

            try:
                if platform == "instagram":
                    ig_id = account.get("ig_id", "")
                    if not ig_id:
                        raise RuntimeError("Geen instagram_business_account_id gekoppeld voor deze klant")
                    post_id = _publish_instagram(ig_id, afbeelding_url, full_caption, token)
                elif platform == "facebook":
                    page_id = account.get("page_id", "")
                    page_token = page_tokens.get(page_id)
                    if not page_id:
                        raise RuntimeError("Geen facebook_page_id gekoppeld voor deze klant")
                    if not page_token:
                        raise RuntimeError("Geen Page Access Token gevonden voor deze pagina")
                    post_id = _publish_facebook(page_id, afbeelding_url, full_caption, page_token)
                else:
                    raise RuntimeError(f"Automatisch publiceren wordt niet ondersteund voor platform '{platform}'")
            except RuntimeError as e:
                print(f"    ❌ Mislukt: {e}")
                ws.batch_update([
                    {"range": f"{COL_PUBLICATIE_STATUS}{row_idx}", "values": [["mislukt"]]},
                    {"range": f"{COL_PUBLICATIE_LOG}{row_idx}", "values": [[str(e)]]},
                ], value_input_option="RAW")
                total_failed += 1
                continue

            print(f"    ✅ Gepubliceerd — post-id {post_id}")
            ws.batch_update([
                {"range": f"{COL_PUBLICATIE_STATUS}{row_idx}", "values": [["gepubliceerd"]]},
                {"range": f"{COL_META_POST_ID}{row_idx}", "values": [[post_id]]},
                {"range": f"{COL_PUBLICATIE_LOG}{row_idx}", "values": [[""]]},
            ], value_input_option="RAW")
            total_published += 1

    print(f"\nKlaar. {total_due} post(en) verwerkt — {total_published} gepubliceerd, {total_failed} mislukt.")


if __name__ == "__main__":
    main()
