"""
Toont alle Facebook-pagina's (en gekoppelde Instagram-bedrijfsaccounts) die
zichtbaar zijn voor het Meta-toegangstoken in .env (META_ACCESS_TOKEN).

Gebruik dit éénmalig (en later opnieuw als er klanten bijkomen) om de juiste
`instagram_business_account_id` en `facebook_page_id` per klant te vinden,
zodat ze in de "Klantprofielen Social Media"-sheet kunnen worden ingevuld.

Usage:
    python systems/list_meta_accounts.py

Vereist in .env:
    META_ACCESS_TOKEN=<system user access token met pages_show_list,
                        instagram_basic, business_management>
"""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

GRAPH_VERSION = "v21.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"


def main():
    token = os.getenv("META_ACCESS_TOKEN")
    if not token:
        print("META_ACCESS_TOKEN ontbreekt in .env", file=sys.stderr)
        sys.exit(1)

    print("Pagina's ophalen die dit token kan zien...\n")

    url = f"{GRAPH_URL}/me/accounts"
    params = {
        "fields": "id,name,access_token,instagram_business_account{id,username,name}",
        "access_token": token,
        "limit": 100,
    }

    found = 0
    while url:
        resp = requests.get(url, params=params, timeout=20)
        data = resp.json()

        if "error" in data:
            err = data["error"]
            print(f"Fout van Meta Graph API: {err.get('message')}", file=sys.stderr)
            print(f"  type={err.get('type')} code={err.get('code')}", file=sys.stderr)
            sys.exit(1)

        for page in data.get("data", []):
            found += 1
            page_id = page.get("id")
            page_name = page.get("name")
            ig = page.get("instagram_business_account")

            print(f"📄 {page_name}")
            print(f"   facebook_page_id           = {page_id}")
            if ig:
                print(f"   instagram_business_account_id = {ig.get('id')}  (@{ig.get('username')})")
            else:
                print(f"   instagram_business_account_id = (geen Instagram gekoppeld aan deze pagina)")
            print()

        # Paginatie
        next_url = data.get("paging", {}).get("next")
        if next_url:
            url = next_url
            params = None  # next_url bevat alle parameters al
        else:
            url = None

    if found == 0:
        print("Geen pagina's gevonden. Controleer of de systeemgebruiker toegang")
        print("heeft tot de Facebook-pagina's van de klanten in Business Manager.")
    else:
        print(f"\n{found} pagina('s) gevonden.")
        print("\nVul de bijbehorende ID's in bij de juiste klant in de")
        print('"Klantprofielen Social Media"-sheet, kolommen:')
        print("  - instagram_business_account_id")
        print("  - facebook_page_id")


if __name__ == "__main__":
    main()
