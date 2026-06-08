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
import io
import json
import os
import re
import zipfile
from datetime import datetime, date, timedelta
from urllib.parse import urlparse

import gspread
import requests
import streamlit as st
import streamlit.components.v1 as components
from bs4 import BeautifulSoup  # nog gebruikt voor logo-scraping
from google.oauth2.service_account import Credentials as WriteCredentials
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv(override=True)

# ── Paginaconfiguratie ────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Top Socials · TopMediaGroep",
    page_icon="✨",
    layout="wide",
)

# ── Helpers ───────────────────────────────────────────────────────────────────

PLATFORM_COLORS = {
    "instagram": "#E1306C",
    "linkedin":  "#0077B5",
    "facebook":  "#1877F2",
}

def _platform_badge(label: str, color: str) -> str:
    """Zelfvoorzienend platform-icoon (geen externe afbeelding nodig — rendert altijd,
    zodat icoon en tekst nooit door elkaar kunnen lopen door een mislukte image-load)."""
    return (
        f'<span style="display:inline-flex;align-items:center;justify-content:center;'
        f'width:20px;height:20px;min-width:20px;border-radius:6px;background:{color};'
        f'color:#fff;font-size:9px;font-weight:800;letter-spacing:.02em;'
        f'margin-right:7px;vertical-align:middle;line-height:1;">{label}</span>'
    )


PLATFORM_ICON_HTML = {
    "instagram": _platform_badge("IG", PLATFORM_COLORS["instagram"]),
    "linkedin":  _platform_badge("IN", PLATFORM_COLORS["linkedin"]),
    "facebook":  _platform_badge("FB", PLATFORM_COLORS["facebook"]),
}

PLATFORM_LABELS = {
    "instagram": "Instagram",
    "linkedin":  "LinkedIn",
    "facebook":  "Facebook",
}

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _next_wednesday_23() -> datetime:
    """Geeft de eerstvolgende woensdag om 23:00 Amsterdam-tijd terug (als UTC-naïeve datetime)."""
    now = datetime.now()
    days_ahead = (2 - now.weekday()) % 7  # 2 = woensdag
    if days_ahead == 0 and now.hour >= 23:
        days_ahead = 7
    next_run = now.replace(hour=23, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
    return next_run


def _format_countdown(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    days    = total_seconds // 86400
    hours   = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}u {minutes}m"
    return f"{hours}u {minutes}m"


SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def get_profile_image(website_url: str) -> str:
    """Geeft Google favicon-URL terug — geen scraping, altijd instant."""
    if not website_url:
        return ""
    domain = urlparse(website_url).netloc
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128" if domain else ""


def _extract_handle(url: str) -> str:
    """Haalt de gebruikersnaam/paginanaam uit een social media URL."""
    if not url:
        return ""
    parts = [p for p in urlparse(url).path.strip("/").split("/") if p]
    return parts[0] if parts else ""


def _client_follower_counts(client: dict) -> dict:
    """Leest opgeslagen volgersaantallen uit de Google Sheet — geen live scraping."""
    return {
        "instagram": client.get("instagram_volgers", "") or "—",
        "linkedin":  client.get("linkedin_volgers",  "") or "—",
        "facebook":  client.get("facebook_volgers",  "") or "—",
    }


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


def _platform_summary_text(client: dict) -> str:
    parts = []
    for platform, label in PLATFORM_LABELS.items():
        count = client.get(f"{platform}_posts_pw", 0)
        if count:
            parts.append(f"{label} {count}x")
    return "  ·  ".join(parts) if parts else "—"


def _platform_summary_html(client: dict) -> str:
    parts = []
    for platform, label in PLATFORM_LABELS.items():
        count = client.get(f"{platform}_posts_pw", 0)
        if count:
            icon = PLATFORM_ICON_HTML[platform]
            color = PLATFORM_COLORS[platform]
            parts.append(
                f'<span style="margin-right:16px;">{icon}'
                f'<span style="color:{color};font-weight:600;">{label}</span>'
                f' <span style="color:#666;">{count}x/week</span></span>'
            )
    return "".join(parts) if parts else "—"


def _total_posts_pw(client: dict) -> int:
    return sum(client.get(f"{p}_posts_pw", 0) for p in ("instagram", "linkedin", "facebook"))


# ── Merk & design system ──────────────────────────────────────────────────────
#
# "Top Socials" — het content-cockpit van TopMediaGroep.
# Eén consistente kleuren-, typografie- en componentenset zodat de tool oogt
# als een afgewerkt product i.p.v. een intern script.

BRAND = {
    "primary":      "#4F46E5",   # indigo — hoofdkleur van het merk
    "primary_dark": "#3730A3",
    "primary_soft": "#EEF2FF",
    "accent":       "#F97316",   # warm oranje accent
    "success":      "#16A34A",
    "warning":      "#F59E0B",
    "danger":       "#DC2626",
    "ink":          "#111827",   # primaire tekstkleur
    "ink_soft":     "#6B7280",   # secundaire tekstkleur
    "line":         "#E5E7EB",   # randen
    "surface":      "#FFFFFF",   # kaarten
    "canvas":       "#F7F8FB",   # paginabackground
}

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

:root {{
    --brand-primary: {BRAND['primary']};
    --brand-primary-dark: {BRAND['primary_dark']};
    --brand-primary-soft: {BRAND['primary_soft']};
    --brand-accent: {BRAND['accent']};
    --brand-success: {BRAND['success']};
    --brand-warning: {BRAND['warning']};
    --brand-danger: {BRAND['danger']};
    --brand-ink: {BRAND['ink']};
    --brand-ink-soft: {BRAND['ink_soft']};
    --brand-line: {BRAND['line']};
    --brand-surface: {BRAND['surface']};
    --brand-canvas: {BRAND['canvas']};
}}

/* ── Basistypografie ───────────────────────────────────────────────────── */
/* Let op: NIET op alle span/div toepassen — Streamlit gebruikt voor pijltjes en
   icoontjes (bv. de pijl van een expander) een icoon-lettertype dat tekst zoals
   "keyboard_arrow_right" omzet naar een glyph. Een te brede font-override breekt
   dat en toont de letterlijke tekst, wat overlap met labels veroorzaakt. */
html, body, .stApp,
.stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown span:not([class*="material"]),
.stCaption, .stText, p, label,
.stButton button, .stDownloadButton button, .stLinkButton a,
input, textarea, select,
[data-testid="stMetricLabel"], [data-testid="stMetricValue"],
[data-testid="stWidgetLabel"] {{
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
}}
/* Icoon-lettertypes van Streamlit met rust laten */
[data-testid*="Icon"], [class*="material-symbols"], [class*="MaterialSymbols"],
.stApp [class*="icon"] {{
    font-family: 'Material Symbols Rounded', 'Material Icons' !important;
}}
.stApp {{
    background: var(--brand-canvas);
}}
h1, h2, h3, h4 {{
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-weight: 800 !important;
    color: var(--brand-ink) !important;
    letter-spacing: -0.02em;
}}
p, .stMarkdown, .stCaption, label {{
    color: var(--brand-ink);
}}

/* ── Streamlit-chrome verbergen voor een productgevoel ─────────────────── */
#MainMenu, footer, header[data-testid="stHeader"] {{ visibility: hidden; height: 0; }}
.block-container {{ padding-top: 1.6rem; max-width: 1280px; }}

/* ── Merk-header (Top Socials wordmark) ──────────────────────────────────────── */
.topsoc-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 6px;
}}
.topsoc-brand {{
    display: flex;
    align-items: center;
    gap: 12px;
}}
.topsoc-logo {{
    width: 42px;
    height: 42px;
    border-radius: 12px;
    background: linear-gradient(135deg, var(--brand-primary), var(--brand-accent));
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    box-shadow: 0 6px 16px rgba(79,70,229,.28);
}}
.topsoc-titles {{ line-height: 1.15; }}
.topsoc-name {{
    font-size: 22px;
    font-weight: 800;
    color: var(--brand-ink);
    letter-spacing: -0.02em;
}}
.topsoc-sub {{
    font-size: 13px;
    color: var(--brand-ink-soft);
    font-weight: 500;
}}
.topsoc-pill {{
    background: var(--brand-primary-soft);
    color: var(--brand-primary-dark);
    font-size: 12px;
    font-weight: 700;
    padding: 6px 14px;
    border-radius: 99px;
    letter-spacing: .02em;
}}

/* ── KPI / metric-kaarten ──────────────────────────────────────────────── */
[data-testid="stMetric"] {{
    background: var(--brand-surface);
    border: 1px solid var(--brand-line);
    border-radius: 16px;
    padding: 16px 20px;
    box-shadow: 0 1px 2px rgba(16,24,40,.04);
}}
[data-testid="stMetricLabel"] {{
    font-size: 12px !important;
    font-weight: 700 !important;
    color: var(--brand-ink-soft) !important;
    text-transform: uppercase;
    letter-spacing: .06em;
}}
[data-testid="stMetricValue"] {{
    font-size: 22px !important;
    font-weight: 800 !important;
    color: var(--brand-ink) !important;
}}

/* ── Tabs ──────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {{
    gap: 6px;
    border-bottom: 1px solid var(--brand-line);
}}
.stTabs [data-baseweb="tab"] {{
    height: 42px;
    border-radius: 10px 10px 0 0;
    padding: 0 18px;
    font-weight: 700;
    font-size: 14px;
    color: var(--brand-ink-soft);
    background: transparent;
}}
.stTabs [aria-selected="true"] {{
    color: var(--brand-primary) !important;
    background: var(--brand-primary-soft) !important;
    border-bottom: 3px solid var(--brand-primary) !important;
}}

/* ── Knoppen ───────────────────────────────────────────────────────────── */
.stButton > button, .stDownloadButton > button, .stLinkButton > a {{
    border-radius: 10px !important;
    font-weight: 700 !important;
    border: 1px solid var(--brand-line) !important;
    transition: all .12s ease;
}}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
    background: var(--brand-primary) !important;
    border-color: var(--brand-primary) !important;
    box-shadow: 0 4px 12px rgba(79,70,229,.25);
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
    border-color: var(--brand-primary) !important;
    color: var(--brand-primary) !important;
}}

/* ── Inputs ────────────────────────────────────────────────────────────── */
.stTextInput input, .stSelectbox div[data-baseweb="select"] > div, .stTextArea textarea {{
    border-radius: 10px !important;
    border-color: var(--brand-line) !important;
}}
.stTextInput input:focus, .stTextArea textarea:focus {{
    border-color: var(--brand-primary) !important;
    box-shadow: 0 0 0 1px var(--brand-primary) !important;
}}

/* ── Expanders ─────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {{
    border: 1px solid var(--brand-line) !important;
    border-radius: 14px !important;
    background: var(--brand-surface);
    box-shadow: 0 1px 2px rgba(16,24,40,.04);
}}

/* ── Card-stijl voor elke klant ────────────────────────────────────────── */
.client-card {{
    display: flex;
    align-items: stretch;
    border: 1px solid var(--brand-line);
    border-radius: 16px;
    margin-bottom: 10px;
    overflow: hidden;
    background: var(--brand-surface);
    box-shadow: 0 1px 3px rgba(16,24,40,.05);
    transition: box-shadow .15s, transform .15s;
}}
.client-card:hover {{
    box-shadow: 0 8px 24px rgba(16,24,40,.08);
    transform: translateY(-1px);
}}

/* Logo-blok links */
.client-logo-block {{
    width: 68px;
    min-width: 68px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--brand-primary-soft);
    border-right: 1px solid var(--brand-line);
    padding: 12px 8px;
}}
.client-logo-block img {{
    width: 44px;
    height: 44px;
    border-radius: 10px;
    object-fit: cover;
}}
.client-logo-placeholder {{
    width: 44px;
    height: 44px;
    border-radius: 10px;
    background: linear-gradient(135deg, var(--brand-primary), var(--brand-accent));
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
}}

/* Koptekst rechts van het logo */
.client-header-content {{
    flex: 1;
    padding: 14px 18px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 4px;
}}
.client-name {{
    font-size: 15px;
    font-weight: 800;
    color: var(--brand-ink);
    line-height: 1.2;
    letter-spacing: -0.01em;
}}
.client-meta {{
    font-size: 13px;
    color: var(--brand-ink-soft);
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
}}
.client-meta img {{
    vertical-align: middle;
    margin-right: 3px;
}}

/* Verberg de Streamlit expander-knop stijl binnen kaarten */
.card-expander [data-testid="stExpander"] {{
    border: none !important;
    box-shadow: none !important;
    border-radius: 0 !important;
}}
.card-expander [data-testid="stExpander"] summary {{
    padding: 14px 16px !important;
    border-bottom: 1px solid #f0f0f0;
}}
</style>
""", unsafe_allow_html=True)

# ── Merk-header ───────────────────────────────────────────────────────────────

st.markdown(
    """
    <div class="topsoc-header">
        <div class="topsoc-brand">
            <div class="topsoc-logo">✨</div>
            <div class="topsoc-titles">
                <div class="topsoc-name">Top Socials</div>
                <div class="topsoc-sub">Content &amp; goedkeuring voor al je social-mediaklanten</div>
            </div>
        </div>
        <div class="topsoc-pill">Live overzicht</div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption("Volg, beoordeel en verstuur social media content voor al je klanten — op één plek.")

st.divider()

# Volgende run
col1, col2, col3 = st.columns(3)

next_run = _next_wednesday_23()
delta    = next_run - datetime.now()

with col1:
    st.metric(
        label="Volgende run",
        value=next_run.strftime("woensdag %d %b om 23:00"),
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

tab_klanten, tab_goedkeuring = st.tabs(["📋 Klanten", "✅ Goedkeuring"])

with tab_klanten:
    st.subheader("Actieve klanten")

    if not clients:
        st.warning("Geen klanten gevonden. Controleer de Google Sheet en credentials.")
    else:
        # Zoekfilter
        search = st.text_input("Zoek op klantnaam", placeholder="Typ een naam...")
        if search:
            clients = [c for c in clients if search.lower() in c.get("bedrijfsnaam", "").lower()]

    # Klantenkaarten
    for client in clients:
        total     = _total_posts_pw(client)
        klant_id  = client.get("klant_id", client["bedrijfsnaam"])
        img_url   = get_profile_image(client.get("website_url", ""))
        followers = _client_follower_counts(client)

        # Bouw platform-badges voor de header
        badge_parts = []
        for platform, label in PLATFORM_LABELS.items():
            count = client.get(f"{platform}_posts_pw", 0)
            if count:
                color = PLATFORM_COLORS[platform]
                icon  = PLATFORM_ICON_HTML[platform]
                foll  = followers.get(platform, "—")
                foll_str = f" · {foll}" if foll and foll != "—" else ""
                badge_parts.append(
                    f'<span style="display:inline-flex;align-items:center;gap:3px;'
                    f'background:{color}18;color:{color};border-radius:6px;'
                    f'padding:2px 8px;font-size:12px;font-weight:600;">'
                    f'{icon}{label} {count}x{foll_str}</span>'
                )
        badges_html = "&nbsp;".join(badge_parts)

        # Logo HTML
        if img_url:
            logo_html = f'<img src="{img_url}">'
        else:
            logo_html = '<div class="client-logo-placeholder">🏢</div>'

        # Card header (altijd zichtbaar)
        st.markdown(f"""
        <div class="client-card">
            <div class="client-logo-block">{logo_html}</div>
            <div class="client-header-content">
                <div class="client-name">{client['bedrijfsnaam']}</div>
                <div class="client-meta">{badges_html}&nbsp;&nbsp;<span>{total} posts/week</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Uitklapbare details direct eronder
        with st.expander("Details", expanded=False):
            col_a, col_b = st.columns(2)

            with col_a:
                st.markdown("**Platformen & volgers**")
                for platform, label in PLATFORM_LABELS.items():
                    count = client.get(f"{platform}_posts_pw", 0)
                    if count:
                        icon  = PLATFORM_ICON_HTML[platform]
                        color = PLATFORM_COLORS[platform]
                        foll  = followers.get(platform, "—")
                        foll_text = f"· {foll} volgers" if foll and foll != "—" else ""
                        st.markdown(
                            f'{icon}<span style="color:{color};font-weight:600;">{label}</span>'
                            f' <span style="color:#555;">{count}x/week {foll_text}</span>',
                            unsafe_allow_html=True,
                        )
                st.write("")

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
                links = [(lbl, url) for lbl, url in urls.items() if url]
                if links:
                    st.markdown("**Links**")
                    for lbl, url in links:
                        st.markdown(f"[{lbl}]({url})")

    st.caption(f"Gegevens worden elke 5 minuten vernieuwd · Laatste update: {datetime.now().strftime('%H:%M:%S')}")

# ── Goedkeuring tab ───────────────────────────────────────────────────────────

WRITE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

STATUS_OPTIONS  = ["concept", "goedgekeurd", "afgewezen"]
STATUS_COLORS   = {"concept": "#f59e0b", "goedgekeurd": "#22c55e", "afgewezen": "#ef4444"}
STATUS_LABELS   = {"concept": "⏳ Concept", "goedgekeurd": "✅ Goedgekeurd", "afgewezen": "❌ Afgewezen"}


def _get_write_client(sa_info: dict):
    creds = WriteCredentials.from_service_account_info(sa_info, scopes=WRITE_SCOPES)
    return gspread.authorize(creds)


def _get_read_client(sa_info: dict):
    creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_data(ttl=60)
def load_post_tabs(spreadsheet_id: str, sa_info_json: str) -> list[str]:
    """Geeft alle tabbladen terug die beginnen met 'Posts_'."""
    sa_info = json.loads(sa_info_json)
    gc = _get_read_client(sa_info)
    spreadsheet = gc.open_by_key(spreadsheet_id)
    return sorted(
        [ws.title for ws in spreadsheet.worksheets() if ws.title.startswith("Posts_")],
        reverse=True,
    )


@st.cache_data(ttl=30)
def load_posts_from_tab(spreadsheet_id: str, tab_name: str, sa_info_json: str) -> list[dict]:
    """Laadt alle posts uit een specifiek tabblad."""
    sa_info = json.loads(sa_info_json)
    gc = _get_read_client(sa_info)
    worksheet = gc.open_by_key(spreadsheet_id).worksheet(tab_name)
    return worksheet.get_all_records(default_blank="")


def save_titles(spreadsheet_id: str, tab_name: str, titles: dict, sa_info_json: str):
    """Schrijft beeldtitels naar kolom J. titles = {row_index: titel_str}"""
    if not titles:
        return
    sa_info = json.loads(sa_info_json)
    gc = _get_write_client(sa_info)
    worksheet = gc.open_by_key(spreadsheet_id).worksheet(tab_name)
    batch = []
    headers = worksheet.row_values(1)
    if len(headers) < 10 or headers[9] != "beeldtitel":
        batch.append({"range": "J1", "values": [["beeldtitel"]]})
    for ri, t in titles.items():
        batch.append({"range": f"J{ri}", "values": [[t]]})
    if batch:
        worksheet.batch_update(batch, value_input_option="RAW")


def generate_image_titles(rows: list, api_key: str) -> dict:
    """Genereert beeldtitels (max 6 woorden) via Claude Haiku. Geeft {row_idx: titel} terug."""
    import anthropic
    ac = anthropic.Anthropic(api_key=api_key)
    results = {}
    for row_idx, post in rows:
        prompt = (
            f"Schrijf een beeldtitel voor deze social media post. "
            f"Maximaal 6 woorden. Alleen de titel, geen uitleg, geen aanhalingstekens.\n\n"
            f"Platform: {post.get('platform', '')}\n"
            f"Tekst: {post.get('caption', '')}"
        )
        msg = ac.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=30,
            messages=[{"role": "user", "content": prompt}],
        )
        title = msg.content[0].text.strip().strip('"').strip("'")
        words = title.split()
        results[row_idx] = " ".join(words[:6])
    return results


def save_statuses(spreadsheet_id: str, tab_name: str, updates: dict, sa_info_json: str):
    """Schrijft statuswijzigingen terug naar het tabblad. updates = {row_index: (status, opmerking)}"""
    sa_info = json.loads(sa_info_json)
    gc = _get_write_client(sa_info)
    worksheet = gc.open_by_key(spreadsheet_id).worksheet(tab_name)
    batch = []
    for row_idx, (status, opmerking) in updates.items():
        batch.append({"range": f"H{row_idx}:I{row_idx}", "values": [[status, opmerking]]})
    worksheet.batch_update(batch, value_input_option="RAW")


MONTHS_NL_LONG = [
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
]

PLATFORM_LABELS_EXPORT = {"instagram": "Instagram", "linkedin": "LinkedIn", "facebook": "Facebook"}
PLATFORM_COLORS_EXPORT  = {"instagram": (0xE1, 0x30, 0x6C), "linkedin": (0x00, 0x77, 0xB5), "facebook": (0x18, 0x77, 0xF2)}


@st.cache_data(ttl=300)
def load_client_dict(spreadsheet_id: str, sa_info_json: str) -> dict:
    """Laadt klantprofielen als dict keyed by bedrijfsnaam."""
    clients = load_clients()
    return {c["bedrijfsnaam"]: c for c in clients}


def _regenerate_prompt(post: dict, client: dict) -> str:
    opmerking = post.get("opmerkingen", "").strip()
    return f"""De volgende social media post voor {client.get('bedrijfsnaam','')} werd afgewezen.

Originele post:
Platform: {post.get('platform','')}
Dag: {post.get('dag','')} ({post.get('publicatiedatum','')})
Tekst: {post.get('caption','')}
Hashtags: {post.get('hashtags','')}

Reden van afwijzing: {opmerking or 'Geen reden opgegeven — verbeter de kwaliteit en relevantie.'}

Klantprofiel:
- Toon: {client.get('toon','')}
- Doelgroep: {client.get('doelgroep','')}
- Kernthema's: {client.get('kernthemas','')}
- Vaste hashtags: {client.get('vaste_hashtags','')}
- Vermijd: {client.get('vermijd','')}

Schrijf een nieuwe, verbeterde versie die de feedback adresseert.
Regels: geen koppeltekens (-) in de tekst. CTA linkt naar een relevante pagina op {client.get('website_url','de website')}.

Geef alleen valide JSON terug:
{{"caption": "...", "hashtags": "..."}}"""


def regenerate_rejected(all_posts: list[dict], client_dict: dict, api_key: str,
                        spreadsheet_id: str, tab_name: str, sa_info_json: str,
                        filter_bedrijfsnaam: str | None = None) -> tuple[int, str]:
    """
    Regenereert afgewezen posts via Claude API en schrijft ze terug naar de sheet.
    Geeft (aantal_verwerkt, foutmelding) terug.
    Rij-indices worden berekend op de volledige lijst zodat sheet-nummers kloppen.
    """
    import anthropic

    rejected = [
        (i + 2, p) for i, p in enumerate(all_posts)
        if p.get("status") == "afgewezen"
        and (filter_bedrijfsnaam is None or p.get("bedrijfsnaam") == filter_bedrijfsnaam)
    ]
    if not rejected:
        return 0, ""

    try:
        ac = anthropic.Anthropic(api_key=api_key)
        sa_info = json.loads(sa_info_json)
        gc = _get_write_client(sa_info)
        worksheet = gc.open_by_key(spreadsheet_id).worksheet(tab_name)

        updates = []
        for row_idx, post in rejected:
            client = client_dict.get(post.get("bedrijfsnaam", ""), {})
            prompt = _regenerate_prompt(post, client)

            msg = ac.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system="Je bent een professionele social media contentschrijver. Retourneer uitsluitend valide JSON.",
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1].lstrip("json").strip()
            raw = raw.rstrip("```").strip()
            new_post = json.loads(raw)

            updates.append({
                "range": f"F{row_idx}:H{row_idx}",
                "values": [[new_post.get("caption", ""), new_post.get("hashtags", ""), "concept"]],
            })

        if updates:
            worksheet.batch_update(updates, value_input_option="RAW")

        return len(rejected), ""

    except Exception as e:
        return 0, str(e)


def regenerate_single_post(post: dict, client_dict: dict, api_key: str,
                           spreadsheet_id: str, tab_name: str, sa_info_json: str,
                           row_idx: int) -> tuple[dict | None, str]:
    """
    Genereert direct een nieuw concept voor één afgewezen post (op basis van de
    opgegeven reden) en schrijft het meteen terug naar de sheet (status -> concept).
    Geeft (nieuwe_post_velden | None, foutmelding) terug.
    """
    import anthropic

    try:
        ac = anthropic.Anthropic(api_key=api_key)
        client = client_dict.get(post.get("bedrijfsnaam", ""), {})
        prompt = _regenerate_prompt(post, client)

        msg = ac.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system="Je bent een professionele social media contentschrijver. Retourneer uitsluitend valide JSON.",
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        raw = raw.rstrip("```").strip()
        new_post = json.loads(raw)

        new_caption  = new_post.get("caption", "")
        new_hashtags = new_post.get("hashtags", "")

        sa_info = json.loads(sa_info_json)
        gc = _get_write_client(sa_info)
        worksheet = gc.open_by_key(spreadsheet_id).worksheet(tab_name)
        worksheet.batch_update([{
            "range": f"F{row_idx}:H{row_idx}",
            "values": [[new_caption, new_hashtags, "concept"]],
        }], value_input_option="RAW")

        return {"caption": new_caption, "hashtags": new_hashtags}, ""
    except Exception as e:
        return None, str(e)


def _build_approved_docx(bedrijfsnaam: str, approved_posts: list[dict]) -> bytes:
    """Bouwt een Word-document met alleen de goedgekeurde posts."""
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    for section in doc.sections:
        section.top_margin    = Pt(50)
        section.bottom_margin = Pt(50)
        section.left_margin   = Pt(70)
        section.right_margin  = Pt(70)

    title = doc.add_heading(f"{bedrijfsnaam} — Definitieve Social Media Posts", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT

    sub = doc.add_paragraph(f"Gegenereerd op {datetime.now().strftime('%d-%m-%Y %H:%M')} · Alleen goedgekeurde posts")
    sub.runs[0].font.color.rgb = RGBColor(0x88, 0x88, 0x88)
    sub.runs[0].font.size = Pt(10)
    doc.add_paragraph()

    for platform in ("instagram", "linkedin", "facebook"):
        platform_posts = [p for p in approved_posts if p.get("platform") == platform]
        if not platform_posts:
            continue

        label = PLATFORM_LABELS_EXPORT[platform]
        r, g, b = PLATFORM_COLORS_EXPORT[platform]
        color = RGBColor(r, g, b)

        heading = doc.add_heading(f"{label} — {len(platform_posts)} post{'s' if len(platform_posts) > 1 else ''}", level=2)
        for run in heading.runs:
            run.font.color.rgb = color

        for post in platform_posts:
            dag_p = doc.add_paragraph()
            dag_run = dag_p.add_run(f"📅 {post.get('dag','')} — {post.get('publicatiedatum','')}")
            dag_run.bold = True
            dag_run.font.size = Pt(11)

            beeldtitel = post.get("beeldtitel", "")
            if beeldtitel:
                bt_p = doc.add_paragraph()
                bt_p.add_run("🖼️ Beeldtitel: ").bold = True
                bt_run = bt_p.add_run(beeldtitel)
                bt_run.font.color.rgb = color
                bt_run.font.size = Pt(11)

            doc.add_paragraph(post.get("caption", ""))

            ht_p = doc.add_paragraph()
            ht_run = ht_p.add_run(post.get("hashtags", ""))
            ht_run.font.color.rgb = color
            ht_run.font.size = Pt(10)
            doc.add_paragraph()

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_export_zip(posts: list[dict], tab_name: str) -> bytes:
    """Genereert een zip met één Word-document per klant (alleen goedgekeurde posts)."""
    clients_posts: dict[str, list[dict]] = {}
    for post in posts:
        if post.get("status") != "goedgekeurd":
            continue
        name = post.get("bedrijfsnaam", "Onbekend")
        clients_posts.setdefault(name, []).append(post)

    week_label = tab_name.replace("Posts_", "").replace("_W", "_Week")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, client_posts in clients_posts.items():
            docx_bytes = _build_approved_docx(name, client_posts)
            filename = f"{name} - Definitief {week_label}.docx"
            zf.writestr(filename, docx_bytes)
    return buf.getvalue()


def _sa_info_json() -> str | None:
    b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_B64") or st.secrets.get("GOOGLE_SERVICE_ACCOUNT_B64")
    if not b64:
        p1 = st.secrets.get("GOOGLE_SA_B64_1", "")
        p2 = st.secrets.get("GOOGLE_SA_B64_2", "")
        b64 = p1 + p2 if p1 and p2 else None
    if b64:
        return json.dumps(json.loads(base64.b64decode(b64).decode()))
    sa = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    return sa if sa else None


def _eff_status(cur_updates, row_idx, post):
    ov = cur_updates.get(row_idx)
    return ov[0] if ov else post.get("status", "concept")


def _eff_note(cur_updates, row_idx, post):
    ov = cur_updates.get(row_idx)
    return ov[1] if ov else post.get("opmerkingen", "")


@st.fragment
def _render_post_card(selected_tab, row_idx, post, color, client_dict, spreadsheet_id, sa_json):
    """Eigen mini-fragment per post: een klik op ✅/❌ rerendert alleen dít kaartje,
    niet de hele klantweergave (metrics, navigator, alle andere posts)."""
    state_key    = f"updates_{selected_tab}"
    pending_key  = f"pending_{selected_tab}"
    titles_key   = f"titles_{selected_tab}"
    ptitles_key  = f"ptitles_{selected_tab}"
    regen_key    = f"regen_{selected_tab}"
    cur_updates    = st.session_state[state_key]
    pending        = st.session_state[pending_key]
    cur_titles     = st.session_state[titles_key]
    pending_titles = st.session_state[ptitles_key]
    if regen_key not in st.session_state:
        st.session_state[regen_key] = {}
    regen_overrides = st.session_state[regen_key]

    cur_status = _eff_status(cur_updates, row_idx, post)

    # Toon eventueel net geregenereerde tekst i.p.v. de originele post-inhoud
    overridden  = regen_overrides.get(row_idx)
    disp_caption  = overridden["caption"]  if overridden else post.get("caption", "")
    disp_hashtags = overridden["hashtags"] if overridden else post.get("hashtags", "")

    col_post, col_ctrl = st.columns([5, 3])

    with col_post:
        if overridden:
            st.caption("🔄 Nieuw concept gegenereerd op basis van je feedback")
        st.markdown(
            f'<p style="font-weight:600;font-size:13px;margin:4px 0 2px 0;">'
            f'📅 {post.get("dag","")} — {post.get("publicatiedatum","")}</p>'
            f'<div style="background:#f8f8f8;border-left:3px solid {color};'
            f'padding:8px 12px;border-radius:0 8px 8px 0;font-size:13px;white-space:pre-wrap;">'
            f'{disp_caption}</div>'
            f'<p style="font-size:11px;color:{color};margin:3px 0 4px 0;">'
            f'{disp_hashtags}</p>',
            unsafe_allow_html=True,
        )
        current_title = cur_titles.get(row_idx) or post.get("beeldtitel", "")
        new_title = st.text_input(
            "Beeldtitel",
            value=current_title,
            key=f"title_{row_idx}",
            placeholder="Max 6 woorden voor de afbeelding...",
            label_visibility="collapsed",
        )
        word_count = len(new_title.split()) if new_title.strip() else 0
        if word_count > 6:
            st.caption(f"⚠️ {word_count}/6 woorden — wordt ingekort bij opslaan")
        elif new_title.strip():
            st.caption(f"🖼️ {word_count}/6 woorden")
        if new_title != current_title:
            cur_titles[row_idx]    = new_title
            pending_titles[row_idx] = " ".join(new_title.split()[:6])

    with col_ctrl:
        # Gekleurde status-badge
        badge = {
            "goedgekeurd": ("#22c55e", "✅ Goedgekeurd"),
            "afgewezen":   ("#ef4444", "❌ Afgewezen"),
            "concept":     ("#f59e0b", "⏳ Concept"),
        }.get(cur_status, ("#999", cur_status))
        st.markdown(
            f'<div style="background:{badge[0]};color:#fff;font-weight:700;'
            f'text-align:center;border-radius:8px;padding:5px 8px;'
            f'font-size:12px;margin-bottom:8px;">{badge[1]}</div>',
            unsafe_allow_html=True,
        )
        col_ok, col_rej_btn = st.columns(2)
        with col_ok:
            if st.button("✅", key=f"ok_{row_idx}", use_container_width=True,
                         disabled=cur_status == "goedgekeurd"):
                cur_updates[row_idx] = ("goedgekeurd", "")
                pending[row_idx]     = ("goedgekeurd", "")
                st.rerun(scope="fragment")
        with col_rej_btn:
            if st.button("❌", key=f"rej_{row_idx}", use_container_width=True,
                         disabled=cur_status == "afgewezen"):
                cur_updates[row_idx] = ("afgewezen", _eff_note(cur_updates, row_idx, post))
                pending[row_idx]     = ("afgewezen", _eff_note(cur_updates, row_idx, post))
                st.rerun(scope="fragment")

        if cur_status == "afgewezen":
            typed = st.text_input(
                "Reden",
                value=_eff_note(cur_updates, row_idx, post),
                key=f"note_{row_idx}",
                placeholder="Wat moet er anders?",
                label_visibility="collapsed",
            )
            cur_updates[row_idx] = ("afgewezen", typed)
            pending[row_idx]     = ("afgewezen", typed)

            if st.button(
                "🔄 Genereer nieuw concept",
                key=f"autoregen_{row_idx}",
                use_container_width=True,
                disabled=not typed.strip(),
                help="Schrijft direct een nieuwe versie op basis van je feedback en zet de status terug naar concept"
                     if typed.strip() else "Vul eerst een reden in zodat de AI weet wat er anders moet",
            ):
                api_key = os.getenv("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY", "")
                if not api_key:
                    st.error("ANTHROPIC_API_KEY ontbreekt.")
                else:
                    with st.spinner("Nieuw concept genereren..."):
                        post_for_prompt = {**post, "caption": disp_caption,
                                           "hashtags": disp_hashtags, "opmerkingen": typed}
                        new_fields, err = regenerate_single_post(
                            post_for_prompt, client_dict, api_key,
                            spreadsheet_id, selected_tab, sa_json, row_idx,
                        )
                    if err:
                        st.error(f"Fout bij regenereren: {err}")
                    else:
                        regen_overrides[row_idx] = new_fields
                        cur_updates[row_idx] = ("concept", "")
                        pending.pop(row_idx, None)
                        load_posts_from_tab.clear()
                        st.success("✓ Nieuw concept klaar — beoordeel hierboven")
                        st.rerun(scope="fragment")

    st.markdown(
        "<hr style='margin:4px 0 10px 0;border:none;border-top:1px solid #eee;'>",
        unsafe_allow_html=True,
    )


@st.fragment
def render_approval_interface(posts, client_dict, spreadsheet_id, selected_tab, sa_json):
    # Data is al geladen buiten de fragment — geen API-calls bij klikken

    if not posts:
        st.warning("Geen posts gevonden in dit tabblad.")
        return

    # ── Groepeer per klant ────────────────────────────────────────────────────
    clients_in_week: dict[str, list] = {}
    for i, post in enumerate(posts, start=2):
        name = post.get("bedrijfsnaam", "Onbekend")
        clients_in_week.setdefault(name, []).append((i, post))

    # ── Session state: statussen + beeldtitels ───────────────────────────────
    state_key    = f"updates_{selected_tab}"
    pending_key  = f"pending_{selected_tab}"
    titles_key   = f"titles_{selected_tab}"
    ptitles_key  = f"ptitles_{selected_tab}"
    if state_key   not in st.session_state: st.session_state[state_key]   = {}
    if pending_key not in st.session_state: st.session_state[pending_key] = {}
    if titles_key  not in st.session_state: st.session_state[titles_key]  = {}
    if ptitles_key not in st.session_state: st.session_state[ptitles_key] = {}
    cur_updates   = st.session_state[state_key]
    pending       = st.session_state[pending_key]
    cur_titles    = st.session_state[titles_key]
    pending_titles = st.session_state[ptitles_key]

    def _eff(row_idx, post):
        ov = cur_updates.get(row_idx)
        return ov[0] if ov else post.get("status", "concept")

    def _note_val(row_idx, post):
        ov = cur_updates.get(row_idx)
        return ov[1] if ov else post.get("opmerkingen", "")

    def _progress(rows):
        statuses = [_eff(ri, p) for ri, p in rows]
        approved = sum(1 for s in statuses if s == "goedgekeurd")
        if approved == len(statuses):
            return 100, "Klaar", "#22c55e"
        elif any(s != "concept" for s in statuses):
            return 66, "In review", "#f59e0b"
        return 0, "Niet gestart", "#ef4444"

    # ── Urgentie ──────────────────────────────────────────────────────────────
    is_urgent = datetime.now().weekday() in (3, 4)

    # ── Metrics ───────────────────────────────────────────────────────────────
    total_posts  = len(posts)
    approved_all = sum(_eff(i + 2, p) == "goedgekeurd" for i, p in enumerate(posts))
    rejected_all = sum(_eff(i + 2, p) == "afgewezen"   for i, p in enumerate(posts))
    pending_all  = total_posts - approved_all - rejected_all
    done_clients = sum(1 for rows in clients_in_week.values() if _progress(rows)[0] == 100)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Klanten klaar", f"{done_clients}/{len(clients_in_week)}")
    c2.metric("Posts totaal", total_posts)
    c3.metric("✅ Goedgekeurd", approved_all)
    c4.metric("❌ Afgewezen", rejected_all)
    c5.metric("⏳ Concept", pending_all)

    overall_pct = int(approved_all / total_posts * 100) if total_posts else 0
    st.markdown(
        f'<div style="background:#e5e7eb;border-radius:99px;height:8px;margin:8px 0 16px 0;">'
        f'<div style="background:#22c55e;width:{overall_pct}%;height:8px;border-radius:99px;"></div></div>'
        f'<p style="font-size:12px;color:#666;margin-top:-8px;">{overall_pct}% van alle posts goedgekeurd</p>',
        unsafe_allow_html=True,
    )

    # ── Urgentie-banner ───────────────────────────────────────────────────────
    if is_urgent:
        incomplete = [n for n, rows in clients_in_week.items() if _progress(rows)[0] < 100]
        if incomplete:
            clr = "#ef4444" if datetime.now().weekday() == 4 else "#f59e0b"
            dag = "vrijdag" if datetime.now().weekday() == 4 else "donderdag"
            st.markdown(
                f'<div style="background:{clr}18;border:1.5px solid {clr};border-radius:10px;'
                f'padding:12px 16px;margin-bottom:12px;">'
                f'<span style="font-weight:700;color:{clr};">⚠️ Het is {dag} — '
                f'{len(incomplete)} klant{"en" if len(incomplete)>1 else ""} nog niet klaar.</span></div>',
                unsafe_allow_html=True,
            )

    # ── Statusoverzicht per klant ──────────────────────────────────────────────
    def _client_stats(rows):
        n_app = sum(1 for ri, p in rows if _eff(ri, p) == "goedgekeurd")
        n_rej = sum(1 for ri, p in rows if _eff(ri, p) == "afgewezen")
        n_con = len(rows) - n_app - n_rej
        return n_app, n_rej, n_con

    not_started, almost_done, waiting_regen = [], [], []
    for name, rows in clients_in_week.items():
        n_app, n_rej, n_con = _client_stats(rows)
        if n_app == 0 and n_rej == 0:
            not_started.append(name)
        elif n_rej > 0:
            waiting_regen.append((name, n_rej))
        elif n_app < len(rows):
            almost_done.append((name, n_app, len(rows)))

    with st.expander(
        f"📊 Statusoverzicht — {len(not_started)} nog niet gestart · "
        f"{len(waiting_regen)} met afgewezen posts · {len(almost_done)} bijna klaar",
        expanded=is_urgent,
    ):
        ov1, ov2, ov3 = st.columns(3)
        with ov1:
            st.markdown("**🔴 Nog niet gestart**")
            if not_started:
                for n in not_started:
                    st.markdown(f"- {n}")
            else:
                st.caption("Niemand — top!")
        with ov2:
            st.markdown("**🟠 Wacht op regeneratie**")
            if waiting_regen:
                for n, n_rej in waiting_regen:
                    st.markdown(f"- {n} _({n_rej} afgewezen)_")
            else:
                st.caption("Geen afgewezen posts open.")
        with ov3:
            st.markdown("**🟡 Bijna klaar**")
            if almost_done:
                for n, n_app, total in almost_done:
                    st.markdown(f"- {n} _({n_app}/{total} goedgekeurd)_")
            else:
                st.caption("Niets in dit overzicht.")

    st.divider()

    # ── Layout: navigator links, review rechts ────────────────────────────────
    # Volgorde eenmalig bepalen per tab zodat de lijst niet springt tijdens review
    sort_key = f"sort_{selected_tab}"
    if sort_key not in st.session_state:
        st.session_state[sort_key] = sorted(
            clients_in_week,
            key=lambda n: (_progress(clients_in_week[n])[0], n),
        )
    sorted_names = [n for n in st.session_state[sort_key] if n in clients_in_week]

    col_nav, col_review = st.columns([1, 3], gap="large")

    with col_nav:
        st.markdown("**Klanten**")
        nav_filter = st.selectbox(
            "Filter",
            ["Alle", "Nog niet gestart", "Heeft afgewezen posts", "In review", "Klaar"],
            label_visibility="collapsed",
            key=f"navfilter_{selected_tab}",
        )

        def _matches_filter(name):
            if nav_filter == "Alle":
                return True
            r = clients_in_week[name]
            n_app, n_rej, n_con = _client_stats(r)
            if nav_filter == "Nog niet gestart":
                return n_app == 0 and n_rej == 0
            if nav_filter == "Heeft afgewezen posts":
                return n_rej > 0
            if nav_filter == "In review":
                return 0 < n_app < len(r)
            if nav_filter == "Klaar":
                return n_app == len(r)
            return True

        filtered_names = [n for n in sorted_names if _matches_filter(n)]

        if not filtered_names:
            st.caption("Geen klanten in dit filter.")
            selected_client = sorted_names[0]
        else:
            radio_key = f"radio_client_{selected_tab}"
            current = st.session_state.get(radio_key)
            if current not in filtered_names:
                # Voorkom StreamlitAPIException wanneer de bewaarde selectie
                # niet meer in de gefilterde lijst voorkomt (filter gewijzigd)
                st.session_state.pop(radio_key, None)
            selected_client = st.radio(
                "Klant",
                filtered_names,
                format_func=lambda n: (
                    f"✅ {n}" if _progress(clients_in_week[n])[0] == 100
                    else f"{'🔴' if is_urgent else '⏳'} {n}"
                ),
                label_visibility="collapsed",
                key=radio_key,
            )

    with col_review:
        rows = clients_in_week[selected_client]

        # ── Auto-genereer beeldtitels voor posts zonder titel (eenmalig) ────
        api_key = os.getenv("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY", "")
        gen_flag = f"titles_generated_{selected_tab}_{selected_client}"
        if gen_flag not in st.session_state:
            st.session_state[gen_flag] = True
            if api_key:
                missing = [(ri, p) for ri, p in rows
                           if not cur_titles.get(ri) and not p.get("beeldtitel", "")]
                if missing:
                    with st.spinner("Beeldtitels genereren..."):
                        generated = generate_image_titles(missing, api_key)
                        save_titles(spreadsheet_id, selected_tab, generated, sa_json)
                        load_posts_from_tab.clear()
                    for ri, title in generated.items():
                        cur_titles[ri] = title

        pct, pct_label, pct_color = _progress(rows)
        n_app = sum(1 for ri, p in rows if _eff(ri, p) == "goedgekeurd")
        n_rej = sum(1 for ri, p in rows if _eff(ri, p) == "afgewezen")

        # Klant-header
        st.markdown(
            f'<div style="margin-bottom:14px;">'
            f'<div style="font-size:20px;font-weight:700;color:#18181b;">{selected_client}</div>'
            f'<div style="display:flex;align-items:center;gap:10px;margin-top:6px;">'
            f'<div style="flex:1;background:#e5e7eb;border-radius:99px;height:5px;">'
            f'<div style="background:{pct_color};width:{pct}%;height:5px;border-radius:99px;"></div></div>'
            f'<span style="font-size:12px;font-weight:700;color:{pct_color};">'
            f'{n_app}/{len(rows)} goedgekeurd · {pct_label}</span></div></div>',
            unsafe_allow_html=True,
        )

        # ── Posts per platform ────────────────────────────────────────────────
        for platform in ("instagram", "linkedin", "facebook"):
            platform_rows = [(ri, p) for ri, p in rows if p.get("platform") == platform]
            if not platform_rows:
                continue

            color = PLATFORM_COLORS[platform]
            icon  = PLATFORM_ICON_HTML[platform]
            st.markdown(
                f'<p style="font-weight:700;color:{color};margin:16px 0 8px 0;">'
                f'{icon}{PLATFORM_LABELS[platform]}</p>',
                unsafe_allow_html=True,
            )

            for row_idx, post in platform_rows:
                _render_post_card(selected_tab, row_idx, post, color, client_dict, spreadsheet_id, sa_json)

        # ── Actieknoppen onderaan de review ───────────────────────────────────
        client_row_indices = {ri for ri, _ in rows}
        client_pending        = {ri: v for ri, v in pending.items()        if ri in client_row_indices}
        client_pending_titles = {ri: v for ri, v in pending_titles.items() if ri in client_row_indices}
        has_pending = bool(client_pending or client_pending_titles)

        col_save, col_gen, col_regen, col_dl, col_mail = st.columns(5)

        with col_save:
            if st.button(
                f"💾 Opslaan ({len(client_pending) + len(client_pending_titles)})" if has_pending else "💾 Opgeslagen",
                key=f"save_{selected_client}",
                disabled=not has_pending,
                use_container_width=True,
                type="primary",
            ):
                if client_pending:
                    save_statuses(spreadsheet_id, selected_tab, client_pending, sa_json)
                    for ri in client_pending:
                        pending.pop(ri, None)
                if client_pending_titles:
                    save_titles(spreadsheet_id, selected_tab, client_pending_titles, sa_json)
                    for ri in client_pending_titles:
                        pending_titles.pop(ri, None)
                st.success("✓ Opgeslagen naar Google Sheets")

        with col_gen:
            if st.button(
                "🎨 Vernieuw titels",
                key=f"gen_titles_{selected_client}",
                use_container_width=True,
                help="Laat Claude nieuwe beeldtitels schrijven voor alle posts",
            ):
                api_key = os.getenv("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY", "")
                if not api_key:
                    st.error("ANTHROPIC_API_KEY ontbreekt.")
                else:
                    with st.spinner("Titels genereren..."):
                        generated = generate_image_titles(rows, api_key)
                        save_titles(spreadsheet_id, selected_tab, generated, sa_json)
                        load_posts_from_tab.clear()
                    for ri, title in generated.items():
                        cur_titles[ri] = title
                    st.success(f"✓ {len(generated)} titels vernieuwd en opgeslagen")

        with col_regen:
            if st.button(
                f"🔄 Regenereer ({n_rej})",
                key=f"regen_{selected_client}",
                disabled=n_rej == 0,
                use_container_width=True,
            ):
                api_key = os.getenv("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY", "")
                if not api_key:
                    st.error("ANTHROPIC_API_KEY ontbreekt.")
                else:
                    if client_pending:
                        save_statuses(spreadsheet_id, selected_tab, client_pending, sa_json)
                        for ri in client_pending:
                            pending.pop(ri, None)
                    load_posts_from_tab.clear()
                    fresh = load_posts_from_tab(spreadsheet_id, selected_tab, sa_json)
                    with st.spinner(f"{n_rej} posts regenereren..."):
                        count, err = regenerate_rejected(
                            fresh, client_dict, api_key,
                            spreadsheet_id, selected_tab, sa_json,
                            filter_bedrijfsnaam=selected_client,
                        )
                        load_posts_from_tab.clear()
                        # Ververs de posts in session state na regeneratie
                        st.session_state[f"posts_{selected_tab}"] = load_posts_from_tab(
                            spreadsheet_id, selected_tab, sa_json
                        )
                        st.session_state[state_key]   = {}
                        st.session_state[pending_key] = {}
                    if err:
                        st.error(f"Fout: {err}")
                    else:
                        st.success(f"✓ {count} posts herschreven")

        with col_dl:
            client_posts = [p for _, p in rows]
            approved_posts = [
                {**p, "beeldtitel": cur_titles.get(ri) or p.get("beeldtitel", "")}
                for ri, p in rows if _eff(ri, p) == "goedgekeurd"
            ]
            if not approved_posts:
                st.button("📄 Download", key=f"dl_{selected_client}", disabled=True, use_container_width=True)
            else:
                docx_bytes = _build_approved_docx(selected_client, approved_posts)
                week_label = selected_tab.replace("Posts_", "").replace("_W", "_Week")
                st.download_button(
                    label=f"📄 Download ({len(approved_posts)})",
                    data=docx_bytes,
                    file_name=f"{selected_client} - Definitief {week_label}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key=f"dl_btn_{selected_client}",
                    use_container_width=True,
                )

        with col_mail:
            from urllib.parse import quote as _quote
            week_label_mail = selected_tab.replace("Posts_", "").replace("_W", " week ")
            subject  = _quote(f"{selected_client} | Je kunt aan de slag met de afbeeldingen")
            body_txt = _quote(
                f"Hey,\n\n"
                f"We hebben de teksten voor {selected_client} voor {week_label_mail} goedgekeurd. "
                f"Kun je aan de slag met de afbeeldingen voor deze klant?\n\n"
                f"Alvast bedankt!"
            )
            mailto = f"mailto:studio@topmediagroep.nl?subject={subject}&body={body_txt}"

            mail_approved = [
                {**p, "beeldtitel": cur_titles.get(ri) or p.get("beeldtitel", "")}
                for ri, p in rows if _eff(ri, p) == "goedgekeurd"
            ]
            if mail_approved:
                docx_b64 = base64.b64encode(
                    _build_approved_docx(selected_client, mail_approved)
                ).decode()
                filename = f"{selected_client} - Definitief {week_label_mail}.docx"
                components.html(f"""
                <button onclick="(function(){{
                    var a=document.createElement('a');
                    a.href='data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,{docx_b64}';
                    a.download='{filename}';
                    a.click();
                    setTimeout(function(){{window.location.href='{mailto}';}},600);
                }})()" style="
                    width:100%;padding:6px 10px;font-size:14px;font-weight:400;
                    background:#fff;color:#31333f;border:1px solid rgba(49,51,63,.2);
                    border-radius:8px;cursor:pointer;font-family:sans-serif;
                    white-space:nowrap;
                ">📧 Mail studio</button>
                """, height=40)
            else:
                components.html("""
                <button disabled style="
                    width:100%;padding:6px 10px;font-size:14px;font-weight:400;
                    background:#f0f0f0;color:#aaa;border:1px solid #ddd;
                    border-radius:8px;cursor:not-allowed;font-family:sans-serif;
                ">📧 Mail studio</button>
                """, height=40)


with tab_goedkeuring:
    st.subheader("Posts goedkeuren per week")

    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID") or st.secrets.get("GOOGLE_SHEETS_SPREADSHEET_ID")
    sa_json = _sa_info_json()

    if not spreadsheet_id or not sa_json:
        st.error("Credentials ontbreken.")
    else:
        tabs = load_post_tabs(spreadsheet_id, sa_json)
        if not tabs:
            st.info("Nog geen posts beschikbaar. Voer eerst de pipeline uit.")
        else:
            selected_tab = st.selectbox(
                "Selecteer een week",
                tabs,
                format_func=lambda t: t.replace("Posts_", "").replace("_W", " · Week "),
            )
            # Laad posts — gebruik session state cache na regeneratie
            posts_ss_key = f"posts_{selected_tab}"
            if posts_ss_key in st.session_state:
                posts = st.session_state.pop(posts_ss_key)
            else:
                posts = load_posts_from_tab(spreadsheet_id, selected_tab, sa_json)

            client_dict = load_client_dict(spreadsheet_id, sa_json)
            render_approval_interface(posts, client_dict, spreadsheet_id, selected_tab, sa_json)

