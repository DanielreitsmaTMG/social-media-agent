# Agent-instructies

Je werkt binnen het **BOS-framework** (Blueprints, Orchestrators, Systems).

Deze architectuur scheidt verantwoordelijkheden zodat probabilistische AI het denkwerk doet en deterministische code de uitvoering.  
Die scheiding maakt het systeem betrouwbaar, schaalbaar en controleerbaar.

---

# De BOS-architectuur

## Laag 1: Blueprints (De instructies)

Markdown SOP’s opgeslagen in `blueprints/`

Elke Blueprint definieert:

- Het doel
- Benodigde input
- Welke systems gebruikt moeten worden
- Verwachte output
- Hoe edge cases worden afgehandeld

Blueprints zijn geschreven in normale taal, zoals je een senior teamlid zou briefen.

Een Blueprint beschrijft **wat** moet gebeuren en **hoe** het moet gebeuren.  
Het is geen losse prompt, maar een operationele instructie.

---

## Laag 2: Orchestrator (De beslisser)

Dit is jouw rol.

Je bent verantwoordelijk voor intelligente coördinatie.

Taken:

- Lees de relevante Blueprint
- Voer systems in de juiste volgorde uit
- Ga netjes om met fouten
- Stel verduidelijkende vragen wanneer input ontbreekt
- Probeer niet zelf taken uit te voeren die via systems bestaan

Je verbindt intentie met uitvoering zonder alles zelf te proberen te doen.

Voorbeeld:

Moet je data van een website halen?  
Probeer dat niet direct.

Lees eerst `blueprints/scrape_website.md`, bepaal de benodigde input en voer daarna `systems/scrape_single_site.py` uit.

---

## Laag 3: Systems (De uitvoering)

Python-scripts in `systems/` die het echte werk doen.

Voorbeelden:

- API-calls  
- Datatransformaties  
- Bestandsbewerkingen  
- Database-queries  

Credentials en API-sleutels staan uitsluitend in `.env`.

Deze scripts zijn:

- Deterministisch
- Consistent
- Testbaar
- Snel

---

# Waarom dit belangrijk is

Wanneer AI alles zelf probeert te doen, daalt de nauwkeurigheid snel.

Als elke stap 90% accuraat is, blijft na vijf stappen nog maar ongeveer 59% succes over.

Door uitvoering uit te besteden aan deterministische scripts:

- Verminder je cumulatieve fouten
- Blijf je gefocust op orkestratie
- Vergroot je betrouwbaarheid
- Bouw je een schaalbaar systeem

AI denkt.  
Code voert uit.

---

# Hoe je moet werken

## 1. Zoek eerst naar bestaande systems

Voordat je iets nieuws bouwt:

- Check `systems/`
- Controleer of een bestaande Blueprint dit al dekt

Maak alleen nieuwe scripts als er echt niets bestaat voor die taak.

---

## 2. Leer en pas aan wanneer iets faalt

Bij een fout:

- Lees de volledige foutmelding en stacktrace
- Analyseer de oorzaak
- Fix het script
- Test opnieuw

Bij betaalde API’s:  
Altijd eerst toestemming vragen voordat je opnieuw runt.

Documenteer wat je geleerd hebt in de Blueprint:

- Rate limits
- Timing-eigenaardigheden
- Onverwacht gedrag
- Nieuwe optimale aanpak

Voorbeeld:

Je wordt rate-limited door een API  
Je duikt in de documentatie  
Je vindt een batch-endpoint  
Je refactort het system  
Je verifieert dat het werkt  
Je update de Blueprint zodat dit niet opnieuw gebeurt

---

## 3. Houd Blueprints actueel

Blueprints moeten meegroeien.

Ontdek je:

- Betere methodes
- Beperkingen
- Terugkerende problemen

Dan update je de Blueprint.

Maak of overschrijf ze niet zonder toestemming, tenzij expliciet gevraagd.

Blueprints zijn je instructies.  
Ze moeten verfijnd worden, niet na één keer gebruik vervangen.

---

# De zelfverbeter-lus

Elke fout maakt het systeem sterker:

1. Bepaal wat kapot ging  
2. Fix het system  
3. Controleer dat de fix werkt  
4. Update de Blueprint met de nieuwe aanpak  
5. Ga verder met een robuuster systeem  

Zo verbetert het framework continu.

---

# Bestandsstructuur

## Wat hoort waar:

Deliverables  
Eindresultaten gaan naar cloudservices (Google Sheets, Slides, etc.) zodat ze direct bruikbaar zijn.

Intermediates  
Tijdelijke bestanden die opnieuw gegenereerd kunnen worden.

## Directory-indeling:

project/
├── blueprints/          # Markdown SOP's en instructies
│   ├── example_task.md
│   └── ...
├── systems/             # Python-scripts voor uitvoering
│   ├── example_system.py
│   └── ...
├── .env                 # API-sleutels en credentials
├── CLAUDE.md            # Agent-instructies en projectcontext
└── README.md            # Projectoverzicht

blueprints/ bevat alleen Markdown-bestanden.
Elke Blueprint beschrijft één taak of workflow.

systems/ bevat alleen Python-scripts.
Elk script doet één ding en doet dat goed.

.env wordt nooit gecommit of gedeeld.
Alle credentials en API-sleutels staan hier.

Deliverables gaan naar cloudservices (Google Sheets, Slides, etc.) zodat ze direct bruikbaar zijn.

Tijdelijke bestanden en tussenresultaten blijven lokaal en kunnen opnieuw gegenereerd worden.

---

# Samenvatting

- Blueprints beschrijven wat er moet gebeuren
- De Orchestrator (jij) bepaalt wanneer en in welke volgorde
- Systems voeren het uit via deterministische code
- Fouten worden geanalyseerd, gefixt en gedocumenteerd
