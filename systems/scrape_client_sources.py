"""
Scrapes available URLs per klant (website, Instagram, Facebook, LinkedIn) om
tone of voice en bedrijfsinformatie te extraheren als context voor contentgeneratie.

URLs zijn optioneel — aanwezige URLs worden gescraped, ontbrekende worden overgeslagen.
Een mislukte URL stopt de rest van de klant niet.

Usage:
    python systems/scrape_client_sources.py
    python systems/scrape_client_sources.py --clients-file intermediates/clients_2026-06-05.json
    python systems/scrape_client_sources.py --client-id aura_interieur

Output: intermediates/scraped_YYYY-MM-DD.json
  Dict keyed by klant_id -> scraped context string
"""

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse, urljoin

from typing import Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(override=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
}

SOCIAL_DOMAINS = {"instagram.com", "facebook.com", "linkedin.com", "twitter.com", "x.com"}
TIMEOUT = 12
DELAY_BETWEEN_CLIENTS = 1.5  # seconden


def _is_social(url: str) -> bool:
    domain = urlparse(url).netloc.lower().lstrip("www.")
    return any(sd in domain for sd in SOCIAL_DOMAINS)


def _fetch(url: str) -> Optional[BeautifulSoup]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"    ✗ {url}: {e}", file=sys.stderr)
        return None


def _extract_meta(soup: BeautifulSoup) -> dict:
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    meta_desc = soup.find("meta", attrs={"name": "description"})
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    return {
        "title": (og_title or {}).get("content") or title,
        "description": (og_desc or meta_desc or {}).get("content") or "",
    }


def _extract_body_text(soup: BeautifulSoup, max_chars: int = 3000) -> str:
    """Extracts readable body text from a non-social page."""
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    # Prefer main content areas
    for selector in ["main", "article", '[role="main"]', ".content", "#content"]:
        container = soup.select_one(selector)
        if container:
            text = container.get_text(separator=" ", strip=True)
            if len(text) > 200:
                return text[:max_chars]

    return soup.get_text(separator=" ", strip=True)[:max_chars]


def _try_about_page(base_url: str) -> str:
    """Tries to find and scrape an /over or /about page for richer context."""
    for slug in ("/over", "/over-ons", "/about", "/about-us", "/wie-zijn-wij"):
        url = urljoin(base_url, slug)
        soup = _fetch(url)
        if soup:
            text = _extract_body_text(soup, max_chars=2000)
            if len(text) > 300:
                return f"[Over-pagina: {url}]\n{text}"
    return ""


def scrape_url(url: str) -> str:
    """Returns extracted context text for a single URL."""
    if not url or not url.startswith("http"):
        return ""

    soup = _fetch(url)
    if not soup:
        return ""

    meta = _extract_meta(soup)
    parts = []

    if meta["title"]:
        parts.append(f"Naam/titel: {meta['title']}")
    if meta["description"]:
        parts.append(f"Beschrijving: {meta['description']}")

    if not _is_social(url):
        body = _extract_body_text(soup)
        if body:
            parts.append(f"Websitetekst:\n{body}")
        about = _try_about_page(url)
        if about:
            parts.append(about)
    else:
        # For social pages: bio/description is usually in og:description
        pass

    return "\n\n".join(parts)


def scrape_client(client: dict) -> str:
    """Scrapes all available URLs for a client and returns combined context."""
    klant_id = client["klant_id"]
    url_fields = {
        "website_url": "Website",
        "instagram_url": "Instagram",
        "facebook_url": "Facebook",
        "linkedin_url": "LinkedIn",
    }

    sections = []
    for field, label in url_fields.items():
        url = client.get(field, "").strip()
        if not url:
            continue
        print(f"    Scraping {label}: {url}")
        context = scrape_url(url)
        if context:
            sections.append(f"=== {label} ({url}) ===\n{context}")

    return "\n\n".join(sections)


def load_clients(clients_file: str) -> list[dict]:
    with open(clients_file, encoding="utf-8") as f:
        return json.load(f)


def _latest_clients_file() -> str:
    files = sorted(Path("intermediates").glob("clients_*.json"), reverse=True)
    if not files:
        raise FileNotFoundError(
            "Geen clients-bestand gevonden in intermediates/. "
            "Voer eerst read_client_profiles.py uit."
        )
    return str(files[0])


def main():
    parser = argparse.ArgumentParser(description="Scrape klant-URLs voor tone of voice context")
    parser.add_argument("--clients-file", help="Pad naar clients JSON (default: laatste in intermediates/)")
    parser.add_argument("--client-id", help="Verwerk alleen deze klant")
    parser.add_argument("--output", help="Pad naar outputbestand")
    args = parser.parse_args()

    clients_file = args.clients_file or _latest_clients_file()
    clients = load_clients(clients_file)
    print(f"Geladen: {len(clients)} klanten uit {clients_file}")

    if args.client_id:
        clients = [c for c in clients if c["klant_id"] == args.client_id]
        if not clients:
            print(f"Klant '{args.client_id}' niet gevonden.", file=sys.stderr)
            sys.exit(1)

    # Alleen klanten met minstens één URL
    to_scrape = [
        c for c in clients
        if any(c.get(f, "").strip() for f in ("website_url", "instagram_url", "facebook_url", "linkedin_url"))
    ]
    print(f"{len(to_scrape)} klanten hebben URLs om te scrapen.")

    results = {}
    for i, client in enumerate(to_scrape, 1):
        klant_id = client["klant_id"]
        print(f"\n[{i}/{len(to_scrape)}] {client['bedrijfsnaam']} ({klant_id})")
        context = scrape_client(client)
        results[klant_id] = context
        if i < len(to_scrape):
            time.sleep(DELAY_BETWEEN_CLIENTS)

    # Klanten zonder URLs krijgen een lege string
    for client in clients:
        results.setdefault(client["klant_id"], "")

    output_path = args.output or f"intermediates/scraped_{date.today()}.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    scraped_count = sum(1 for v in results.values() if v)
    print(f"\nKlaar. {scraped_count}/{len(clients)} klanten hebben gescrapete context.")
    print(f"Opgeslagen: {output_path}")


if __name__ == "__main__":
    main()
