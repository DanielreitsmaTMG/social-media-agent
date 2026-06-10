"""
Creates the "Klantprofielen Social Media" Google Sheet with correct headers and formatting.
Run once during project setup. Requires GOOGLE_SERVICE_ACCOUNT_JSON and optionally
GOOGLE_SHEETS_SPREADSHEET_ID in .env (if empty, a new sheet is created).
"""

import json
import os
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv(override=True)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    # Identiteit
    "klant_id",
    "bedrijfsnaam",
    "actief",
    "taal",
    # Platformen & frequentie (posts per week; 0 = platform niet actief)
    "instagram_posts_pw",
    "linkedin_posts_pw",
    "facebook_posts_pw",
    # Merkpersoonlijkheid
    "toon",
    "doelgroep",
    "kernthemas",
    "vaste_hashtags",
    "vermijd",
    # Online aanwezigheid (optioneel — worden gescraped voor tone of voice context)
    "website_url",
    "instagram_url",
    "facebook_url",
    "linkedin_url",
    # Meta Graph API-koppeling (voor realtime statistieken)
    "instagram_business_account_id",
    "facebook_page_id",
    # Weekcontext (wordt wekelijks bijgewerkt)
    "extra_context",
    # Aflevering
    "google_doc_folder_id",
]

EXAMPLE_ROWS = [
    [
        "aura_interieur",
        "Aura Peeperkorn Interieur",
        "TRUE",
        "nl",
        3, 2, 1,
        "Warm, inspirerend en persoonlijk. Niet te formeel.",
        "Huiseigenaren 35-60 jaar met interesse in interieur en wonen",
        "interieur, duurzaam wonen, kleuradvies, styling, renovatie",
        "#interieur #interiorinspiration #wonenenmeer #interieurstyling",
        "Concurrentienamen, prijsvergelijkingen, politieke uitspraken",
        "https://www.aurainterieur.nl",
        "https://www.instagram.com/aurainterieur/",
        "https://www.facebook.com/aurainterieur",
        "https://www.linkedin.com/company/aura-interieur/",
        "",
        "",
        "",
        "1A2B3C4D5E6F7G8H",
    ],
    [
        "hoogehuys",
        "Hoogehuys",
        "TRUE",
        "nl",
        2, 3, 2,
        "Professioneel, betrouwbaar en nuchter. Zakelijke toon.",
        "Ondernemers en vastgoedinvesteerders in de regio",
        "vastgoed, projectontwikkeling, duurzaamheid, locatie",
        "#vastgoed #projectontwikkeling #hoogehuys",
        "Speculatieve uitspraken over marktprijzen",
        "https://www.hoogehuys.nl",
        "",
        "",
        "https://www.linkedin.com/company/hoogehuys/",
        "",
        "",
        "",
        "2B3C4D5E6F7G8H9I",
    ],
]

COLUMN_NOTES = {
    "klant_id": "Unieke slug zonder spaties, bijv. aura_interieur",
    "actief": "TRUE of FALSE — FALSE = overgeslagen bij generatie",
    "taal": "nl of en",
    "instagram_posts_pw": "Aantal posts per week (0 = platform niet gebruiken)",
    "linkedin_posts_pw": "Aantal posts per week (0 = platform niet gebruiken)",
    "facebook_posts_pw": "Aantal posts per week (0 = platform niet gebruiken)",
    "kernthemas": "Komma-gescheiden lijst van onderwerpen",
    "website_url": "Volledig URL incl. https:// — wordt gescraped voor tone of voice",
    "instagram_url": "Volledig profiel-URL — wordt gescraped voor bio en stijl",
    "facebook_url": "Volledig pagina-URL — wordt gescraped voor beschrijving",
    "linkedin_url": "Volledig bedrijfspagina-URL — wordt gescraped voor beschrijving",
    "instagram_business_account_id": "Numeriek ID via systems/list_meta_accounts.py — voor realtime statistieken",
    "facebook_page_id": "Numeriek ID via systems/list_meta_accounts.py — voor realtime statistieken",
    "extra_context": "Wekelijks bij te werken: lopende campagnes, acties, seizoen",
    "google_doc_folder_id": "Google Drive folder-ID uit de URL van de klantmap",
}


def main():
    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not service_account_json:
        raise EnvironmentError("GOOGLE_SERVICE_ACCOUNT_JSON not set in .env")

    creds = Credentials.from_service_account_info(
        json.loads(service_account_json), scopes=SCOPES
    )
    client = gspread.authorize(creds)

    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    if spreadsheet_id:
        sheet = client.open_by_key(spreadsheet_id).sheet1
        print(f"Opened existing sheet: {spreadsheet_id}")
    else:
        spreadsheet = client.create("Klantprofielen Social Media")
        sheet = spreadsheet.sheet1
        spreadsheet.share(None, perm_type="anyone", role="writer")
        print(f"Created new sheet: {spreadsheet.id}")
        print(f"Add to .env: GOOGLE_SHEETS_SPREADSHEET_ID={spreadsheet.id}")

    sheet.clear()
    sheet.append_row(HEADERS)
    for row in EXAMPLE_ROWS:
        sheet.append_row(row)

    # Freeze header row
    sheet.freeze(rows=1)

    # Column widths (approximate, in pixels)
    column_widths = {
        1: 140,   # klant_id
        2: 200,   # bedrijfsnaam
        3: 70,    # actief
        4: 60,    # taal
        5: 110,   # instagram_posts_pw
        6: 110,   # linkedin_posts_pw
        7: 110,   # facebook_posts_pw
        8: 280,   # toon
        9: 240,   # doelgroep
        10: 280,  # kernthemas
        11: 240,  # vaste_hashtags
        12: 200,  # vermijd
        13: 220,  # website_url
        14: 220,  # instagram_url
        15: 220,  # facebook_url
        16: 220,  # linkedin_url
        17: 240,  # instagram_business_account_id
        18: 200,  # facebook_page_id
        19: 300,  # extra_context
        20: 200,  # google_doc_folder_id
    }
    requests = [
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet.id,
                    "dimension": "COLUMNS",
                    "startIndex": col - 1,
                    "endIndex": col,
                },
                "properties": {"pixelSize": width},
                "fields": "pixelSize",
            }
        }
        for col, width in column_widths.items()
    ]
    sheet.spreadsheet.batch_update({"requests": requests})

    print(f"Sheet ready with {len(HEADERS)} columns and {len(EXAMPLE_ROWS)} example rows.")
    print("Remove or overwrite example rows before production use.")


if __name__ == "__main__":
    main()
