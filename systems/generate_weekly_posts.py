"""
Genereert wekelijkse social media posts voor alle actieve klanten via de Claude API.
Verwerkt klanten sequentieel in batches om rate limits te respecteren.

Usage:
    python systems/generate_weekly_posts.py
    python systems/generate_weekly_posts.py --week-start 2026-06-09
    python systems/generate_weekly_posts.py --client-id aura_interieur
    python systems/generate_weekly_posts.py --clients-file intermediates/clients_2026-06-05.json

Output: intermediates/posts_YYYY-MM-DD.json
"""

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from typing import Optional

import anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

MODEL = "claude-opus-4-8"
BATCH_SIZE = 10
DELAY_WITHIN_BATCH = 2   # seconden tussen klanten in dezelfde batch
DELAY_BETWEEN_BATCHES = 15  # seconden tussen batches

DAYS_NL = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag"]
DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def _next_monday(from_date: Optional[date] = None) -> date:
    """Returns the Monday of next week."""
    d = from_date or date.today()
    days_ahead = 7 - d.weekday()  # weekday(): 0=Mon, 6=Sun
    return d + timedelta(days=days_ahead)


def _format_date_nl(d: date) -> str:
    months = ["jan", "feb", "mrt", "apr", "mei", "jun",
              "jul", "aug", "sep", "okt", "nov", "dec"]
    return f"{d.day} {months[d.month - 1]}"


def _build_prompt(client: dict, scraped_context: str, week_start: date, week_end: date) -> str:
    lang = client.get("taal", "nl").lower()
    days = DAYS_NL if lang == "nl" else DAYS_EN

    platform_lines = []
    for platform in ("instagram", "linkedin", "facebook"):
        count = client.get(f"{platform}_posts_pw", 0)
        if count > 0:
            platform_lines.append(f"- {platform.capitalize()}: {count} posts")

    if not platform_lines:
        return ""

    extra = client.get("extra_context", "").strip()
    extra_section = f"\nExtra context voor deze week:\n{extra}" if extra else ""

    prestatie = client.get("prestatie_inzichten", "").strip()
    prestatie_section = (
        f"\nPrestatie-inzichten op basis van eerdere posts (gebruik dit om de invalshoek/onderwerpen "
        f"af te stemmen op wat goed werkt bij deze doelgroep):\n{prestatie}"
        if prestatie
        else ""
    )

    scraped_section = (
        f"\nContext gescraped van de online aanwezigheid van de klant "
        f"(gebruik dit om de toon en informatie beter af te stemmen):\n{scraped_context}"
        if scraped_context.strip()
        else ""
    )

    today = date.today()
    week_label = (
        f"{_format_date_nl(week_start)} – {_format_date_nl(week_end)} {week_end.year}"
        if lang == "nl"
        else f"{week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}"
    )

    # Bouw een dagoverzicht zodat Claude exact weet welke datum bij welke dag hoort
    day_dates = []
    for i, day_name in enumerate(days[:5]):
        d = week_start + timedelta(days=i)
        day_dates.append(f"  {day_name} = {_format_date_nl(d)} {d.year}")
    day_date_overview = "\n".join(day_dates)

    return f"""Genereer social media posts voor {client['bedrijfsnaam']} voor de week van {week_label}.

Vandaag is het {_format_date_nl(today)} {today.year}. De posts worden gepubliceerd in de week van {week_label}.
De exacte publicatiedatums zijn:
{day_date_overview}

Belangrijk voor temporele relevantie:
- Gebruik "vandaag", "morgen", "deze week" alleen als die verwijzing klopt voor de publicatiedatum van de post
- Verwijs NIET naar evenementen, deadlines of acties die vóór {_format_date_nl(week_start)} {week_start.year} vallen — die zijn al voorbij als de post gepubliceerd wordt
- Als gescrapete content verwijst naar een datum die voor de targetweek ligt, gebruik die informatie dan alleen als achtergrond voor de toon, niet als actueel nieuws

Klantprofiel:
- Toon: {client['toon']}
- Doelgroep: {client['doelgroep']}
- Kernthema's: {client['kernthemas']}
- Vaste hashtags: {client['vaste_hashtags']}
- Vermijd altijd: {client['vermijd']}
- Taal van de posts: {lang}{extra_section}{scraped_section}{prestatie_section}

Genereer:
{chr(10).join(platform_lines)}

Richtlijnen:
- Varieer de invalshoek per post: mix informatief, inspirerend en actiegericht
- Instagram: visueel gedreven, korte alinea's, gebruik emoji's spaarzaam
- LinkedIn: inhoudelijk en professioneel, geen salesy taal, mag langer
- Facebook: conversationeel en toegankelijk, mag een vraag bevatten
- Voeg bij elke post de vaste hashtags toe plus 3-5 passende extra hashtags
- Spreid posts logisch over de week ({', '.join(days)})
- Schrijf posts volledig uitgewerkt, niet als concept
- Gebruik NOOIT een koppelteken (-) in de posttekst, ook niet als opsommingsteken of gedachtestreepje
- Elke post die een CTA bevat moet linken naar de pagina op de website die inhoudelijk aansluit bij het onderwerp van die post. Gebruik dus niet altijd de homepage, maar de relevante dienstenpagina, blogpost of contactpagina

Geef de output als valide JSON in exact dit formaat:
{{
  "instagram": [
    {{"dag": "Maandag", "caption": "...", "hashtags": "#hashtag1 #hashtag2", "beeldtitel": "Korte titel voor afbeelding"}},
    ...
  ],
  "linkedin": [...],
  "facebook": [...]
}}

De beeldtitel is een korte titel (maximaal 6 woorden) die de lading van de afbeelding dekt. Dit wordt door de studio gebruikt als tekst in de afbeelding.

Laat een platform-sleutel weg als dat platform 0 posts heeft.
Geen tekst buiten de JSON."""


def generate_for_client(
    client: dict,
    scraped_context: str,
    week_start: date,
    week_end: date,
    anthropic_client: anthropic.Anthropic,
) -> Optional[dict]:
    prompt = _build_prompt(client, scraped_context, week_start, week_end)
    if not prompt:
        print(f"    Geen actieve platformen — overgeslagen.")
        return None

    message = anthropic_client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=(
            "Je bent een professionele social media contentschrijver. "
            "Je retourneert uitsluitend valide JSON, geen uitleg of opmaak eromheen."
        ),
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip().rstrip("```").strip()

    return json.loads(raw)


def _latest_file(pattern: str) -> Optional[str]:
    files = sorted(Path("intermediates").glob(pattern), reverse=True)
    return str(files[0]) if files else None


def main():
    parser = argparse.ArgumentParser(description="Genereer wekelijkse social media posts")
    parser.add_argument("--week-start", help="Startdatum van de week (YYYY-MM-DD, default: volgende maandag)")
    parser.add_argument("--clients-file", help="Pad naar clients JSON")
    parser.add_argument("--scraped-file", help="Pad naar scraped context JSON")
    parser.add_argument("--client-id", help="Verwerk alleen deze klant")
    parser.add_argument("--output", help="Pad naar outputbestand")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set in .env")

    anthropic_client = anthropic.Anthropic(api_key=api_key)

    # Bepaal de week
    if args.week_start:
        week_start = date.fromisoformat(args.week_start)
    else:
        week_start = _next_monday()
    week_end = week_start + timedelta(days=4)  # vrijdag

    print(f"Week: {week_start} t/m {week_end}")

    # Laad clients
    clients_file = args.clients_file or _latest_file("clients_*.json")
    if not clients_file:
        print("Geen clients-bestand gevonden. Voer eerst read_client_profiles.py uit.", file=sys.stderr)
        sys.exit(1)
    with open(clients_file, encoding="utf-8") as f:
        clients = json.load(f)

    if args.client_id:
        clients = [c for c in clients if c["klant_id"] == args.client_id]
        if not clients:
            print(f"Klant '{args.client_id}' niet gevonden.", file=sys.stderr)
            sys.exit(1)

    # Laad scraped context (optioneel)
    scraped: dict = {}
    scraped_file = args.scraped_file or _latest_file("scraped_*.json")
    if scraped_file and Path(scraped_file).exists():
        with open(scraped_file, encoding="utf-8") as f:
            scraped = json.load(f)
        print(f"Scraped context geladen: {scraped_file}")
    else:
        print("Geen scraped context gevonden — posts worden gegenereerd zonder websitecontext.")

    # Output pad
    output_path = args.output or f"intermediates/posts_{date.today()}.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Laad bestaande output zodat we kunnen hervatten bij een crash
    results = {}
    if Path(output_path).exists():
        with open(output_path, encoding="utf-8") as f:
            results = json.load(f)
        print(f"Hervat: {len(results)} klanten al verwerkt.")

    to_process = [c for c in clients if c["klant_id"] not in results]
    print(f"{len(to_process)} klanten te verwerken in batches van {BATCH_SIZE}.\n")

    succeeded = 0
    failed = []

    for batch_start in range(0, len(to_process), BATCH_SIZE):
        batch = to_process[batch_start: batch_start + BATCH_SIZE]
        batch_nr = batch_start // BATCH_SIZE + 1
        total_batches = (len(to_process) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"--- Batch {batch_nr}/{total_batches} ---")

        for i, client in enumerate(batch):
            klant_id = client["klant_id"]
            print(f"  [{batch_start + i + 1}/{len(to_process)}] {client['bedrijfsnaam']}...", end=" ", flush=True)

            try:
                posts = generate_for_client(
                    client,
                    scraped.get(klant_id, ""),
                    week_start,
                    week_end,
                    anthropic_client,
                )
                if posts is not None:
                    results[klant_id] = {
                        "client": client,
                        "week_start": str(week_start),
                        "week_end": str(week_end),
                        "posts": posts,
                    }
                    succeeded += 1
                    print("✓")
            except json.JSONDecodeError as e:
                print(f"✗ (JSON parse fout: {e})")
                failed.append((klant_id, str(e)))
            except Exception as e:
                print(f"✗ ({e})")
                failed.append((klant_id, str(e)))

            # Sla tussenresultaten op na elke klant
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

            if i < len(batch) - 1:
                time.sleep(DELAY_WITHIN_BATCH)

        if batch_start + BATCH_SIZE < len(to_process):
            print(f"  Wacht {DELAY_BETWEEN_BATCHES}s voor volgende batch...")
            time.sleep(DELAY_BETWEEN_BATCHES)

    print(f"\n{'='*40}")
    print(f"✓ Verwerkt: {succeeded}/{len(to_process)} klanten")
    if failed:
        print(f"✗ Mislukt ({len(failed)}):")
        for klant_id, reason in failed:
            print(f"  - {klant_id}: {reason}")
    print(f"Opgeslagen: {output_path}")


if __name__ == "__main__":
    main()
