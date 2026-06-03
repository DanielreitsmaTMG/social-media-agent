# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

# BOS-framework: Marketing Agent Social Media

Een agent die wekelijks voor ~50 klanten social media posts schrijft en aanlevert.  
Elke woensdagavond om 23:00 genereert de agent posts voor de week erop, per klant een eigen Google Doc.

Dit project werkt volgens het **BOS-framework** (Blueprints, Orchestrators, Systems):  
AI doet het denkwerk, deterministische code doet de uitvoering.

---

## Jouw rol: Orchestrator

Je verbindt intentie met uitvoering. Je:

- Leest de relevante Blueprint in `blueprints/` voordat je iets doet
- Voert `systems/`-scripts uit in de juiste volgorde
- Stelt verduidelijkende vragen als input ontbreekt
- Voert taken **niet zelf uit** als er een system voor bestaat
- Documenteert fouten, rate limits en nieuwe inzichten terug in de Blueprint

---

## Bestandsstructuur

```
project/
├── blueprints/                         # Markdown SOP's — beschrijven WAT en HOE
│   ├── weekly_content_generation.md    # Hoofdworkflow: wekelijkse contentgeneratie
│   └── post_social_media.md            # (toekomstig) directe publicatie
├── systems/                            # Python-scripts — deterministische uitvoering
│   ├── read_client_profiles.py         # Laad klantprofielen uit Google Sheets
│   ├── generate_weekly_posts.py        # Genereer posts via Claude API
│   └── create_weekly_doc.py            # Maak Google Doc per klant aan
├── .env                                # API-sleutels (nooit committen)
├── CLAUDE.md
└── README.md
```

**blueprints/** — één `.md` per taak of workflow  
**systems/** — één `.py` per taak, doet één ding goed  
**Deliverables** → Google Docs per klant in hun eigen Drive-folder  
**Klantdata** → Google Sheet "Klantprofielen Social Media"

---

## Werkwijze

### Vóór elke taak
1. Check `systems/` — bestaat er al een script voor?
2. Check `blueprints/` — is er al een SOP?
3. Bouw alleen iets nieuws als er echt niets bestaat.

### Bij een fout
1. Lees de volledige foutmelding en stacktrace
2. Analyseer de oorzaak en fix het script
3. Test opnieuw
4. Update de Blueprint met wat je geleerd hebt (rate limits, edge cases, betere aanpak)
5. Bij betaalde API's (Claude, Google): vraag eerst toestemming voor je opnieuw runt

### Blueprints updaten
- Verfijn Blueprints wanneer je betere methodes of beperkingen ontdekt
- Maak of overschrijf ze niet zonder toestemming, tenzij expliciet gevraagd

---

## Waarom deze scheiding

Elke AI-stap heeft ~90% nauwkeurigheid. Na vijf stappen resteert ~59%.  
Door uitvoering te delegeren aan deterministische scripts:
- Reduceer je cumulatieve fouten
- Blijft Claude gefocust op orkestratie
- Is het systeem schaalbaar en controleerbaar
