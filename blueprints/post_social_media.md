# Blueprint: Posten op Social Media

## Doel

Publiceer een post op één of meerdere platformen (Instagram, LinkedIn, Facebook) vanuit één centrale instructie.

---

## Benodigde input

| Veld | Verplicht | Omschrijving |
|---|---|---|
| `caption` | Ja | De tekst van de post |
| `image_path` | Nee | Lokaal pad naar afbeelding (JPG/PNG) |
| `platforms` | Ja | Lijst: `instagram`, `linkedin`, `facebook` (of combinatie) |
| `scheduled_time` | Nee | ISO 8601 — weglaten voor directe publicatie |

Als `caption` of `platforms` ontbreekt: stop en vraag om de missende input.  
Ga nooit raden welk platform bedoeld wordt.

---

## Systems

Voer per platform het bijbehorende script uit:

| Platform | Script |
|---|---|
| Instagram | `systems/post_instagram.py` |
| LinkedIn | `systems/post_linkedin.py` |
| Facebook | `systems/post_facebook.py` |

Voer scripts parallel uit als meerdere platformen gevraagd zijn.  
Een fout op één platform stopt de andere niet.

---

## Stappen

1. Valideer de input (caption aanwezig, platforms geldig, afbeelding bestaat als opgegeven)
2. Voer de scripts uit voor de opgegeven platformen
3. Verzamel de post-URL's of post-ID's uit de output
4. Rapporteer per platform: geslaagd / mislukt + reden

---

## Verwachte output

Per platform één regel:
```
✓ LinkedIn  — https://www.linkedin.com/feed/update/urn:li:share:...
✓ Facebook  — post_id: 123456789
✓ Instagram — media_id: 987654321
```

---

## Edge cases

**Afbeelding vereist voor Instagram**  
Instagram ondersteunt geen tekst-only posts via de API. Als geen `image_path` opgegeven is en Instagram in de lijst staat: vraag alsnog om een afbeelding, of sla Instagram over na bevestiging.

**Rate limits**  
- Instagram Graph API: max. 200 calls per uur per token  
- LinkedIn API: max. 100 posts per dag per app  
- Facebook Graph API: limieten variëren per endpoint  
Bij een 429-fout: wacht de opgegeven `Retry-After` af en probeer opnieuw. Vraag toestemming voor opnieuw uitvoeren als kosten verbonden zijn.

**Ongeldige token / verlopen credentials**  
Stop direct, meld welk platform faalt, en geef aan waar de token vernieuwd kan worden (zie `.env`).

**Post mislukt op één platform**  
Log de fout, ga door met de overige platformen en rapporteer het verschil in de eindstatus.

---

## Credentials (in `.env`)

```
INSTAGRAM_ACCESS_TOKEN=
INSTAGRAM_ACCOUNT_ID=
LINKEDIN_ACCESS_TOKEN=
LINKEDIN_ORGANIZATION_ID=
FACEBOOK_ACCESS_TOKEN=
FACEBOOK_PAGE_ID=
```
