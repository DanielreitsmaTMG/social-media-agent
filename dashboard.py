"""
Social Media Agent Dashboard

Toont actieve klanten en de volgende geplande run.
Leest klantdata live uit Google Sheets.

Lokaal starten:
    streamlit run dashboard.py

Vereist in .env (of Streamlit Cloud secrets):
    GOOGLE_SERVICE_ACCOUNT_JSON
    GOOGLE_SHEETS_SPREADSHEET_ID
"""

import base64
import json
import os
from datetime import datetime, timedelta

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

# ── Paginaconfiguratie ────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Social Media Agent",
    page_icon="📱",
    layout="wide",
)

# ── Helpers ───────────────────────────────────────────────────────────────────

PLATFORM_ICONS = {
    "instagram": "📸",
    "linkedin":  "💼",
    "facebook":  "👥",
}

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _next_thursday_13() -> datetime:
    """Geeft de eerstvolgende donderdag om 13:00 Amsterdam-tijd terug (als UTC-naïeve datetime)."""
    now = datetime.now()
    days_ahead = (3 - now.weekday()) % 7  # 3 = donderdag
    if days_ahead == 0 and now.hour >= 13:
        days_ahead = 7
    next_run = now.replace(hour=13, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
    return next_run


def _format_countdown(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    days    = total_seconds // 86400
    hours   = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}u {minutes}m"
    return f"{hours}u {minutes}m"


@st.cache_data(ttl=300)  # Cache 5 minuten
def load_clients() -> list[dict]:
    # Lees spreadsheet ID
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID") or st.secrets.get("GOOGLE_SHEETS_SPREADSHEET_ID")
    if not spreadsheet_id:
        st.error("GOOGLE_SHEETS_SPREADSHEET_ID ontbreekt in secrets.")
        return []

    # Lees service account — base64 string heeft voorkeur (geen TOML-escapingproblemen)
    try:
        b64 = (os.getenv("GOOGLE_SERVICE_ACCOUNT_B64")
               or st.secrets.get("GOOGLE_SERVICE_ACCOUNT_B64"))
        if not b64:
            part1 = st.secrets.get("GOOGLE_SA_B64_1", "")
            part2 = st.secrets.get("GOOGLE_SA_B64_2", "")
            if part1 and part2:
                b64 = part1 + part2
        if b64:
            sa_info = json.loads(base64.b64decode(b64).decode())
        else:
            sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
            if not sa_json:
                st.error("GOOGLE_SERVICE_ACCOUNT_B64 ontbreekt in secrets.")
                return []
            sa_info = json.loads(sa_json)
    except Exception as e:
        st.error(f"Fout bij laden service account: {e}")
        return []

    try:
        creds  = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        client = gspread.authorize(creds)
        sheet  = client.open_by_key(spreadsheet_id).sheet1
        rows   = sheet.get_all_records(default_blank="")
    except Exception as e:
        st.error(f"Fout bij verbinden met Google Sheets: {e}")
        return []

    active = []
    for row in rows:
        if str(row.get("actief", "")).strip().upper() != "TRUE":
            continue
        for platform in ("instagram", "linkedin", "facebook"):
            key = f"{platform}_posts_pw"
            try:
                row[key] = int(row[key])
            except (ValueError, TypeError):
                row[key] = 0
        active.append(row)

    return active


def _platform_summary(client: dict) -> str:
    parts = []
    for platform in ("instagram", "linkedin", "facebook"):
        count = client.get(f"{platform}_posts_pw", 0)
        if count:
            parts.append(f"{PLATFORM_ICONS[platform]} {count}x")
    return "  ".join(parts) if parts else "—"


def _total_posts_pw(client: dict) -> int:
    return sum(client.get(f"{p}_posts_pw", 0) for p in ("instagram", "linkedin", "facebook"))


# ── Layout ────────────────────────────────────────────────────────────────────

st.title("📱 Social Media Agent")
st.caption("Live overzicht van actieve klanten en geplande contentruns")

# Tijdelijke debug — wordt verwijderd zodra verbinding werkt
with st.expander("🔧 Debug: beschikbare secrets"):
    try:
        keys = list(st.secrets.keys())
        st.write("Gevonden secret-keys:", keys)
    except Exception as e:
        st.write("Geen secrets gevonden:", e)

st.divider()

# Volgende run
col1, col2, col3 = st.columns(3)

next_run = _next_thursday_13()
delta    = next_run - datetime.now()

with col1:
    st.metric(
        label="Volgende run",
        value=next_run.strftime("donderdag %d %b om 13:00"),
        delta=f"over {_format_countdown(delta)}",
        delta_color="off",
    )

clients = load_clients()

with col2:
    st.metric("Actieve klanten", len(clients))

with col3:
    total_posts = sum(_total_posts_pw(c) for c in clients)
    st.metric("Posts per week", total_posts)

st.divider()

# Klantenoverzicht
st.subheader("Actieve klanten")

if not clients:
    st.warning("Geen klanten gevonden. Controleer de Google Sheet en credentials.")
else:
    # Zoekfilter
    search = st.text_input("Zoek op klantnaam", placeholder="Typ een naam...")
    if search:
        clients = [c for c in clients if search.lower() in c.get("bedrijfsnaam", "").lower()]

    # Tabel
    for client in clients:
        with st.expander(
            f"**{client['bedrijfsnaam']}**  ·  {_platform_summary(client)}  ·  {_total_posts_pw(client)} posts/week",
            expanded=False,
        ):
            col_a, col_b = st.columns(2)

            with col_a:
                st.markdown("**Platformen**")
                for platform in ("instagram", "linkedin", "facebook"):
                    count = client.get(f"{platform}_posts_pw", 0)
                    if count:
                        st.write(f"{PLATFORM_ICONS[platform]} {platform.capitalize()}: {count}x per week")

                st.markdown("**Toon**")
                st.write(client.get("toon") or "_Niet ingevuld_")

                st.markdown("**Doelgroep**")
                st.write(client.get("doelgroep") or "_Niet ingevuld_")

            with col_b:
                st.markdown("**Kernthema's**")
                themas = client.get("kernthemas", "")
                if themas:
                    for t in themas.split(","):
                        st.write(f"· {t.strip()}")
                else:
                    st.write("_Niet ingevuld_")

                st.markdown("**Vaste hashtags**")
                st.code(client.get("vaste_hashtags") or "—", language=None)

                urls = {
                    "Website":   client.get("website_url"),
                    "Instagram": client.get("instagram_url"),
                    "LinkedIn":  client.get("linkedin_url"),
                    "Facebook":  client.get("facebook_url"),
                }
                links = [(label, url) for label, url in urls.items() if url]
                if links:
                    st.markdown("**Links**")
                    for label, url in links:
                        st.markdown(f"[{label}]({url})")

    st.caption(f"Gegevens worden elke 5 minuten vernieuwd · Laatste update: {datetime.now().strftime('%H:%M:%S')}")
