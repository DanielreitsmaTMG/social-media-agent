# Blueprint: Content-planning & automatische publicatie

## Doel
Goedgekeurde posts (status `goedgekeurd` in `Posts_YYYY_WNN`) voorzien van een
afbeelding, inplannen op een datum/tijd, en automatisch laten publiceren naar
Instagram en Facebook — zoals Meta Business Suite / Hootsuite, maar volledig
zelf gehost (geen extra abonnement).

## Status
🟢 Actief. Fase A (uploaden + inplannen via dashboard) en Fase B (automatisch
publiceren via GitHub Actions) zijn beide gebouwd.

## Flow

1. **Goedkeuring** (tab "✅ Goedkeuring"): posts krijgen status `goedgekeurd`.
2. **Planning** (tab "📅 Planning"):
   - Per goedgekeurde post wordt een afbeelding geüpload via
     `st.file_uploader` → `systems/drive_upload.py` → opgeslagen in een
     "Planning"-submap binnen de Drive-map van de klant
     (`google_doc_folder_id`), met publieke leesrechten ("anyone with the
     link") zodat de Meta Graph API de afbeelding kan ophalen.
   - Een datum + tijd wordt ingepland via "📌 Inplannen". Dit zet
     `publicatie_status = "gepland"`.
   - Een agenda-overzicht bovenaan toont alle ingeplande posts gesorteerd op
     datum/tijd, met statusbadge.
3. **Automatisch publiceren** (`systems/publish_scheduled_posts.py`, draait
   elke 15 minuten via `.github/workflows/publish_scheduled_posts.yml`):
   - Doorzoekt alle `Posts_*`-tabbladen op rijen met
     `publicatie_status == "gepland"` waarvan `geplande_datum` +
     `geplande_tijd` (Europe/Amsterdam) verstreken is.
   - Zet de rij eerst op `bezig` (voorkomt dubbele publicatie bij
     overlappende runs).
   - **Instagram**: `POST /{ig_id}/media` (image_url + caption) →
     `POST /{ig_id}/media_publish`.
   - **Facebook**: `POST /{page_id}/photos` met `url`, `caption`,
     `published=true` (Page Access Token via `/me/accounts`).
   - Bij succes: `publicatie_status = "gepubliceerd"` + `meta_post_id`.
   - Bij fout: `publicatie_status = "mislukt"` + foutmelding in
     `publicatie_log`. Zichtbaar in de Planning-tab; opnieuw inplannen
     (datum/tijd + "Inplannen") probeert het opnieuw.

## Sheet-kolommen (Posts_YYYY_WNN, kolom K t/m Q)

| Kolom | Naam | Omschrijving |
|---|---|---|
| K | `geplande_datum` | ISO-datum (YYYY-MM-DD) waarop gepubliceerd moet worden |
| L | `geplande_tijd` | Tijd (HH:MM, Europe/Amsterdam) |
| M | `afbeelding_url` | Publieke Drive-URL (`https://drive.google.com/uc?export=view&id=...`) |
| N | `afbeelding_drive_id` | Drive file-ID van de geüploade afbeelding |
| O | `publicatie_status` | leeg → `gepland` → `bezig` → `gepubliceerd` / `mislukt` |
| P | `meta_post_id` | ID van de gepubliceerde post (Instagram/Facebook) |
| Q | `publicatie_log` | Foutmelding bij `mislukt`, leeg bij succes |

Oudere tabbladen (vóór deze feature geüpload) hebben alleen kolom A-J.
`dashboard.py` vult de header-rij automatisch aan via
`_ensure_planning_columns()` zodra er voor het eerst in zo'n tabblad wordt
geschreven.

## Edge cases / geleerde lessen

- **Geen afbeelding → kan niet ingepland worden.** De knop "📌 Inplannen" is
  uitgeschakeld zolang `afbeelding_url` leeg is.
- **LinkedIn wordt niet automatisch gepubliceerd** — alleen Instagram en
  Facebook hebben een publicatie-API via deze koppeling. LinkedIn-posts
  blijven gewoon op `goedgekeurd` staan en worden handmatig geplaatst.
- **Klant zonder `instagram_business_account_id` / `facebook_page_id`**:
  publicatie mislukt met een duidelijke `publicatie_log`-melding ("Geen
  instagram_business_account_id gekoppeld voor deze klant" /
  "Geen facebook_page_id gekoppeld..."). Zie
  `blueprints/meta_insights_koppeling.md` voor het koppelen van klanten.
- **GitHub Actions cron is niet seconde-precies** — een vertraging van een
  paar minuten t.o.v. de ingeplande tijd is normaal en geen probleem.
  Scheduled workflows worden door GitHub automatisch uitgeschakeld na 60
  dagen zonder repo-activiteit; bij een actief gebruikte repo is dit geen
  issue.
- **Drive-afbeeldingen moeten publiek leesbaar zijn** ("anyone with the
  link") — anders kan de Meta Graph API de `image_url` niet ophalen en
  mislukt de IG/FB-publicatie met een download-fout. `drive_upload.py` zet
  deze permissie automatisch.
- **Dubbele publicatie**: het script zet de status meteen op `bezig` voordat
  het de Graph API aanroept, zodat een overlappende run (bijv. bij een trage
  vorige run) dezelfde rij niet nogmaals oppakt.

## Nieuwe instantie opzetten (kopieerbaar/verkoopbaar)

Deze tool bevat geen hardcoded klantgegevens in code — alle configuratie
loopt via `.env` (lokaal) / Streamlit secrets (cloud) / GitHub repo secrets,
en per-klant data staat in de Google Sheet. Om de tool voor een nieuwe
klant/bureau in te richten:

1. **Repository klonen** naar een nieuwe locatie/remote.
2. **Eigen Google Sheet** aanmaken met dezelfde tabbladstructuur:
   - Sheet1: klantprofielen (zie `systems/client_profiles_template.csv`),
     incl. kolommen `google_doc_folder_id`, `instagram_business_account_id`,
     `facebook_page_id`.
   - `Posts_YYYY_WNN`-tabbladen worden automatisch aangemaakt door
     `systems/upload_posts_to_sheets.py`.
3. **Eigen Google service account** aanmaken (Sheets + Drive API ingeschakeld),
   gedeeld met de nieuwe Sheet (Editor-rechten) en met de Drive-mappen van de
   klant(en).
4. **Eigen Meta-app + system user + token** volgens
   `blueprints/meta_insights_koppeling.md` (stap 1), gekoppeld aan het
   Business Manager-portfolio van de nieuwe klant/bureau.
5. **Secrets instellen**:
   - Lokaal `.env`: `GOOGLE_SHEETS_SPREADSHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON`,
     `META_ACCESS_TOKEN`, `ANTHROPIC_API_KEY`.
   - Streamlit Cloud (Settings → Secrets): dezelfde waarden + `auth`-sectie
     voor logins.
   - GitHub repo secrets (Settings → Secrets and variables → Actions):
     `GOOGLE_SHEETS_SPREADSHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON`,
     `META_ACCESS_TOKEN` — nodig voor `publish_scheduled_posts.yml`.
6. **GitHub Actions workflow testen** via "Run workflow" (workflow_dispatch)
   vóórdat de cron actief gebruikt wordt — controleer de run-log op
   authenticatie-/koppelingsfouten.
7. Klanten zonder Meta-koppeling werken gewoon door (Goedkeuring/Planning
   blijven werken; alleen automatisch publiceren wordt overgeslagen met een
   nette `publicatie_log`-melding).
