"""
Maakt per klant een Google Doc aan met de gegenereerde weekposts.
Plaatst het document in de Google Drive-map van de klant (google_doc_folder_id).

De HTML-upload aanpak converteert automatisch naar een opgemaakt Google Doc
zonder de complexiteit van de Docs API batchUpdate.

Usage:
    python systems/create_weekly_doc.py
    python systems/create_weekly_doc.py --posts-file intermediates/posts_2026-06-05.json
    python systems/create_weekly_doc.py --client-id aura_interieur

Output: intermediates/report_YYYY-MM-DD.json
  Dict keyed by klant_id -> {"doc_url": ..., "doc_id": ...}
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

from typing import Optional

from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

load_dotenv(override=True)

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]

MONTHS_NL = [
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
]

PLATFORM_LABELS = {
    "instagram": "Instagram",
    "linkedin": "LinkedIn",
    "facebook": "Facebook",
}

PLATFORM_COLORS = {
    "instagram": "#E1306C",
    "linkedin": "#0077B5",
    "facebook": "#1877F2",
}


def _drive_service(service_account_json: str):
    creds = Credentials.from_service_account_info(
        json.loads(service_account_json), scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def _week_number(d: date) -> int:
    return d.isocalendar()[1]


def _format_date_nl(d: date) -> str:
    return f"{d.day} {MONTHS_NL[d.month - 1]}"


def _doc_title(bedrijfsnaam: str, week_start: date, week_end: date) -> str:
    week_nr = _week_number(week_start)
    return (
        f"{bedrijfsnaam} — Social Media "
        f"| Week {week_nr} "
        f"| {_format_date_nl(week_start)} – {_format_date_nl(week_end)} {week_end.year}"
    )


def _build_html(bedrijfsnaam: str, posts: dict, week_start: date, week_end: date) -> str:
    week_nr = _week_number(week_start)
    title = _doc_title(bedrijfsnaam, week_start, week_end)
    generated_at = datetime.now().strftime("%d-%m-%Y %H:%M")

    sections = []
    for platform_key in ("instagram", "linkedin", "facebook"):
        platform_posts = posts.get(platform_key, [])
        if not platform_posts:
            continue

        label = PLATFORM_LABELS[platform_key]
        color = PLATFORM_COLORS[platform_key]

        post_blocks = []
        for post in platform_posts:
            dag = post.get("dag", "")
            caption = post.get("caption", "").replace("\n", "<br>")
            hashtags = post.get("hashtags", "")
            post_blocks.append(f"""
        <div style="margin-bottom: 24px; padding: 16px; border-left: 3px solid {color}; background: #fafafa;">
          <p style="margin: 0 0 4px 0; font-weight: bold; color: #555;">📅 {dag}</p>
          <p style="margin: 0 0 12px 0; line-height: 1.6;">{caption}</p>
          <p style="margin: 0; color: {color}; font-size: 13px;">{hashtags}</p>
        </div>""")

        sections.append(f"""
      <div style="margin-bottom: 32px;">
        <h2 style="color: {color}; border-bottom: 2px solid {color}; padding-bottom: 6px;">
          {label} — {len(platform_posts)} post{"s" if len(platform_posts) > 1 else ""}
        </h2>
        {"".join(post_blocks)}
      </div>""")

    content = "\n".join(sections) if sections else "<p>Geen posts gegenereerd.</p>"

    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; font-size: 14px; color: #333; max-width: 800px; margin: 40px auto; padding: 0 20px; }}
    h1 {{ color: #111; font-size: 20px; margin-bottom: 4px; }}
    h2 {{ font-size: 16px; margin-top: 32px; }}
    .meta {{ color: #888; font-size: 12px; margin-bottom: 32px; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="meta">Gegenereerd op {generated_at} · Week {week_nr} {week_end.year}</p>
  {content}
</body>
</html>"""


def create_doc(
    drive_service,
    client: dict,
    posts: dict,
    week_start: date,
    week_end: date,
) -> dict:
    bedrijfsnaam = client["bedrijfsnaam"]
    folder_id = client.get("google_doc_folder_id", "").strip()

    if not folder_id:
        raise ValueError(f"Geen google_doc_folder_id voor {bedrijfsnaam}")

    title = _doc_title(bedrijfsnaam, week_start, week_end)
    html = _build_html(bedrijfsnaam, posts, week_start, week_end)

    file_metadata = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [folder_id],
    }
    media = MediaInMemoryUpload(html.encode("utf-8"), mimetype="text/html", resumable=False)

    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink",
    ).execute()

    return {
        "doc_id": file["id"],
        "doc_url": file["webViewLink"],
        "title": title,
    }


def _latest_file(pattern: str) -> Optional[str]:
    files = sorted(Path("intermediates").glob(pattern), reverse=True)
    return str(files[0]) if files else None


def main():
    parser = argparse.ArgumentParser(description="Maak Google Docs aan voor wekelijkse posts")
    parser.add_argument("--posts-file", help="Pad naar posts JSON (default: laatste in intermediates/)")
    parser.add_argument("--client-id", help="Verwerk alleen deze klant")
    parser.add_argument("--output", help="Pad naar rapportbestand")
    args = parser.parse_args()

    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not service_account_json:
        raise EnvironmentError("GOOGLE_SERVICE_ACCOUNT_JSON not set in .env")

    posts_file = args.posts_file or _latest_file("posts_*.json")
    if not posts_file or not Path(posts_file).exists():
        print("Geen posts-bestand gevonden. Voer eerst generate_weekly_posts.py uit.", file=sys.stderr)
        sys.exit(1)

    with open(posts_file, encoding="utf-8") as f:
        all_posts = json.load(f)

    if args.client_id:
        if args.client_id not in all_posts:
            print(f"Klant '{args.client_id}' niet in posts-bestand.", file=sys.stderr)
            sys.exit(1)
        all_posts = {args.client_id: all_posts[args.client_id]}

    drive_svc = _drive_service(service_account_json)

    output_path = args.output or f"intermediates/report_{date.today()}.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Laad bestaande output om te hervatten
    report = {}
    if Path(output_path).exists():
        with open(output_path, encoding="utf-8") as f:
            report = json.load(f)
        print(f"Hervat: {len(report)} docs al aangemaakt.")

    to_process = {k: v for k, v in all_posts.items() if k not in report}
    print(f"{len(to_process)} Google Docs aan te maken...\n")

    succeeded = 0
    failed = []

    for i, (klant_id, data) in enumerate(to_process.items(), 1):
        client = data["client"]
        posts = data["posts"]
        week_start = date.fromisoformat(data["week_start"])
        week_end = date.fromisoformat(data["week_end"])

        print(f"  [{i}/{len(to_process)}] {client['bedrijfsnaam']}...", end=" ", flush=True)

        try:
            result = create_doc(drive_svc, client, posts, week_start, week_end)
            report[klant_id] = result
            succeeded += 1
            print(f"✓  {result['doc_url']}")
        except Exception as e:
            print(f"✗  {e}")
            failed.append((klant_id, str(e)))

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*40}")
    print(f"✓ Aangemaakt: {succeeded}/{len(to_process)} documenten")
    if failed:
        print(f"✗ Mislukt ({len(failed)}):")
        for klant_id, reason in failed:
            print(f"  - {klant_id}: {reason}")
    print(f"Rapport opgeslagen: {output_path}")


if __name__ == "__main__":
    main()
