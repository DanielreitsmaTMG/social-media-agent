# Blueprint: Meta (Instagram & Facebook) Insights-koppeling

## Doel
Per klant realtime statistieken tonen in Top Socials: volgers, bereik (reach),
impressies, engagement (likes/comments/shares/saves) — opgehaald via de
officiële **Meta Graph API**, niet via scraping.

## Status
- 🟡 In opbouw. TopMediaGroep heeft via het eigen Business Manager-portfolio
  toegang tot **±60% van de klanten**. We starten daarmee; de overige klanten
  worden later toegevoegd zodra hun Instagram/Facebook-accounts zijn
  gekoppeld aan ons portfolio.
- Klanten zonder koppeling tonen gewoon geen statistieken (nette lege state),
  de rest van de tool blijft normaal werken.

## Benodigde input

### 1. Eénmalig: Meta-app + toegangstoken (TopMediaGroep-kant)
1. Ga naar [developers.facebook.com](https://developers.facebook.com/) → **Mijn apps** → **App maken**.
   - Type: "Business".
   - Koppel de app aan het TopMediaGroep Business Manager-portfolio.
2. Voeg de producten **"Instagram Graph API"** en **"Facebook Login for Business"** toe aan de app.
3. Maak in Business Manager (business.facebook.com) onder **Instellingen → Gebruikers → Systeemgebruikers**
   een **systeemgebruiker** aan (bijv. "Top Socials Bot") met rol "Werknemer".
4. Geef die systeemgebruiker toegang tot de Facebook-pagina's / Instagram-bedrijfsaccounts
   van de klanten die al in het portfolio zitten.
5. Genereer voor de systeemgebruiker een **toegangstoken** met scopes:
   - `pages_read_engagement`
   - `pages_show_list`
   - `instagram_basic`
   - `instagram_manage_insights`
   - `business_management`
   Kies **"Token verloopt nooit"** (system user tokens kunnen permanent zijn).
6. Zet dit token in `.env` / Streamlit secrets als:
   ```
   META_ACCESS_TOKEN=...
   ```

> ⚠️ Dit token geeft toegang tot de gekoppelde accounts — nooit in chat plakken,
> alleen in `.env` (lokaal) of Streamlit Cloud → Settings → Secrets.

### 2. Per klant: Instagram Business Account ID + Facebook Page ID
Voor elke klant met toegang via het portfolio moet de **Instagram Business
Account ID** (en optioneel Facebook Page ID) bekend zijn. Deze worden
opgehaald met `systems/list_meta_accounts.py` (zie hieronder) zodra het
toegangstoken is ingesteld — dat script toont alle pagina's + gekoppelde
IG-accounts die de systeemgebruiker kan zien, zodat je per klant het juiste
ID kunt overnemen.

Deze ID's worden opgeslagen in twee nieuwe kolommen in de klanten-sheet:
- `instagram_business_account_id`
- `facebook_page_id`

Klanten zonder deze ID's worden overgeslagen bij het ophalen van statistieken.

## Systems

- **`systems/list_meta_accounts.py`** *(nieuw)* — toont alle Facebook-pagina's
  + gekoppelde Instagram-accounts die het token kan zien, met hun ID's.
  Gebruikt om de sheet eenmalig (en later incrementeel) te vullen.
- **`systems/fetch_meta_insights.py`** *(nieuw)* — haalt per klant met een
  ingevulde `instagram_business_account_id`:
  - volgersaantal (`followers_count`)
  - bereik laatste 7/28 dagen (`reach`)
  - impressies (`impressions`)
  - profielbezoeken (`profile_views`)
  - engagement van de laatste posts (likes, comments, saves, shares)

  en schrijft dit weg naar een nieuwe sheet-tab **"Statistieken"** — één rij
  per klant per ophaalmoment, zodat er een geschiedenis ontstaat voor
  trendgrafieken.

  Draait via een geplande taak (bijv. dagelijks), net als
  `update_follower_counts.py`.

## Output / Dashboard
- Nieuw tabblad **"📊 Statistieken"** in `dashboard.py`:
  - Per klant: kaarten met volgers (+ groei t.o.v. vorige meting), bereik,
    impressies, engagement-rate.
  - Lijngrafiek van volgersgroei/bereik over tijd (uit de "Statistieken"-tab).
  - Klanten zonder Meta-koppeling: nette melding "Nog niet gekoppeld".

## Edge cases / geleerde lessen
- (in te vullen zodra we tegen rate limits / permissies aanlopen)
- Facebook Graph API rate limit: standaard ~200 calls/uur per gebruiker per
  app — bij 60+ klanten dagelijks ophalen past dit ruim.
- IG Insights vereisen een **Instagram Business- of Creator-account** gekoppeld
  aan een Facebook-pagina — persoonlijke accounts werken niet.
