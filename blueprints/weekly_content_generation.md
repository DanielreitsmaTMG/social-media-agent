# Blueprint: Wekelijkse Social Media Content Generatie

## Doel

Genereer elke week op woensdagavond om 23:00 voor alle actieve klanten de social media posts voor de week erop.  
Elke klant krijgt een eigen Google Doc met kant-en-klare posts per platform.

---

## Trigger

Automatisch elke **woensdag om 23:00**.  
Handmatig starten kan ook — geef dan de gewenste weekdatum mee (standaard: eerstvolgende maandag).

---

## Benodigde input

Alle klantdata staat in één Google Sheet: **"Klantprofielen Social Media"**.

### Verplichte kolommen per klant

| Kolom | Omschrijving |
|---|---|
| `klant_id` | Unieke slug zonder spaties, bijv. `aura_interieur` |
| `bedrijfsnaam` | Weergavenaam |
| `actief` | `TRUE` / `FALSE` — inactieve klanten worden overgeslagen |
| `taal` | `nl` of `en` |
| `instagram_posts_pw` | Posts per week op Instagram (0 = platform niet actief) |
| `linkedin_posts_pw` | Posts per week op LinkedIn (0 = platform niet actief) |
| `facebook_posts_pw` | Posts per week op Facebook (0 = platform niet actief) |
| `toon` | Schrijfstijl, bijv. "warm, inspirerend en persoonlijk" |
| `doelgroep` | Wie de posts moet bereiken |
| `kernthemas` | Komma-gescheiden onderwerpen, bijv. "interieur, duurzaamheid, wonen" |
| `vaste_hashtags` | Hashtags die altijd meegenomen worden |
| `vermijd` | Onderwerpen, woorden of stijlen die nooit gebruikt mogen worden |
| `extra_context` | Wekelijks bij te werken: lopende campagnes, acties, seizoen |
| `prestatie_inzichten` | Automatisch ingevuld door `systems/update_performance_insights.py` op basis van best presterende posts (Meta-koppeling) — niet handmatig wijzigen |
| `google_doc_folder_id` | Google Drive folder-ID uit de URL van de klantmap |

---

## Systems

| Stap | Script | Omschrijving |
|---|---|---|
| 1 | `systems/read_client_profiles.py` | Laad alle actieve klantprofielen uit Google Sheets |
| 2 | `systems/scrape_client_sources.py` | Scrape website en social URLs voor tone of voice context |
| 3 | `systems/generate_weekly_posts.py` | Genereer posts per klant via Claude API (gebruikt o.a. `prestatie_inzichten` als extra context) |
| 4 | `systems/create_weekly_doc.py` | Maak Google Doc aan per klant in de juiste Drive-folder |

> 💡 Voor klanten met een Meta-koppeling wordt `prestatie_inzichten` periodiek
> bijgewerkt door `systems/update_performance_insights.py` (zie blueprint
> *meta_insights_koppeling*). Draai dit idealiter vóór de wekelijkse
> contentgeneratie zodat de nieuwste inzichten worden meegenomen.

Tussenresultaten worden opgeslagen in `intermediates/` zodat je bij een fout kunt hervatten zonder eerdere stappen te herhalen.

---

## Stappen

1. Bepaal de targetweek (eerstvolgende maandag t/m vrijdag na uitvoerdatum)
2. `python systems/read_client_profiles.py` → `intermediates/clients_DATUM.json`
3. `python systems/scrape_client_sources.py` → `intermediates/scraped_DATUM.json`
4. `python systems/generate_weekly_posts.py` → `intermediates/posts_DATUM.json`
5. `python systems/create_weekly_doc.py` → `intermediates/report_DATUM.json` + Google Docs per klant
6. Rapporteer het rapport uit stap 5: aantal geslaagd, mislukt, URLs van de aangemaakte docs

---

## Opbouw van het weekdocument per klant

```
[Bedrijfsnaam] — Social Media Posts | Week XX | DD MMM – DD MMM JJJJ

INSTAGRAM (3 posts)
────────────────────
📅 Maandag
[post-tekst]
#hashtag1 #hashtag2

📅 Woensdag
[post-tekst]
...

LINKEDIN (2 posts)
────────────────────
📅 Dinsdag
[post-tekst]
...

FACEBOOK (2 posts)
────────────────────
...
```

---

## Richtlijnen voor contentgeneratie

- Varieer de invalshoek van posts binnen dezelfde week (informatief / inspirerend / actiegericht)
- Gebruik altijd de vaste hashtags uit het profiel, aangevuld met relevante weekhashtags
- Volg de toon en vermijd de onderwerpen uit het profiel strikt
- Posts voor Instagram zijn korter en visueel gedreven; LinkedIn is informatiever en professioneler
- Eindig LinkedIn-posts niet met een vraag als er al een call-to-action is
- Gebruik nooit een koppelteken (-) in de posttekst, ook niet als opsommingsteken of gedachtestreepje
- Een CTA linkt altijd naar de pagina die inhoudelijk aansluit bij het onderwerp van die post — niet naar de homepage, maar naar de relevante dienstenpagina, blogpost of contactpagina
- Temporele relevantie: verwijs nooit naar evenementen of deadlines die vóór de publicatiedatum van de post vallen. Gescrapete content met verouderde datums mag alleen als achtergrond voor toon dienen, niet als actueel nieuws

---

## Verwachte output

```
✓ Verwerkt: 47/50 klanten
✓ Posts gegenereerd: 312
✗ Mislukt (3): aura_interieur (API timeout), hoogehuys (lege folder-ID), lodt_media (geen actieve platformen)
```

---

## Edge cases

**Klant heeft geen `google_doc_folder_id`**  
Sla de klant over, log als fout, ga door met de rest. Meld aan het einde.

**`extra_context` is leeg**  
Geen probleem — genereer op basis van kernthemas en toon.

**API rate limit (Claude)**  
Verwerk klanten in batches van 10 met een pauze van 10 seconden ertussen.

**Google Doc bestaat al voor die week**  
Overschrijf niet automatisch. Vraag toestemming of maak een versie aan met suffix `_v2`.

**Klant staat op `actief = FALSE`**  
Altijd overslaan, ook als handmatig gestart.

**Minder dan 50 klanten actief**  
Normaal gedrag — verwerk alleen actieve rijen.

---

## Credentials (in `.env`)

```
ANTHROPIC_API_KEY=
GOOGLE_SHEETS_SPREADSHEET_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=
```
