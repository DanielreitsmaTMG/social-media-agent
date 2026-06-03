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
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

import gspread
import requests
import streamlit as st
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials as WriteCredentials
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

PLATFORM_COLORS = {
    "instagram": "#E1306C",
    "linkedin":  "#0077B5",
    "facebook":  "#1877F2",
}

PLATFORM_ICON_HTML = {
    "instagram": '<img src="https://cdn.simpleicons.org/instagram/E1306C" width="16" height="16" style="vertical-align:middle;margin-right:6px;">',
    "linkedin":  '<img src="https://cdn.simpleicons.org/linkedin/0077B5" width="16" height="16" style="vertical-align:middle;margin-right:6px;">',
    "facebook":  '<img src="https://cdn.simpleicons.org/facebook/1877F2" width="16" height="16" style="vertical-align:middle;margin-right:6px;">',
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


@st.cache_data(ttl=3600)  # Cache 1 uur — afbeeldingen veranderen zelden
def get_profile_image(linkedin_url: str, website_url: str) -> str:
    """Haalt profielfoto op: LinkedIn og:image → website og:image → favicon."""

    def scrape_og_image(url: str) -> str:
        try:
            r = requests.get(url, headers=SCRAPE_HEADERS, timeout=8, allow_redirects=True)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                tag = soup.find("meta", property="og:image")
                if tag and tag.get("content"):
                    return tag["content"]
        except Exception:
            pass
        return ""

    if linkedin_url:
        img = scrape_og_image(linkedin_url)
        if img:
            return img

    if website_url:
        img = scrape_og_image(website_url)
        if img:
            return img
        domain = urlparse(website_url).netloc
        if domain:
            return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"

    return ""


def _extract_handle(url: str) -> str:
    """Haalt de gebruikersnaam/paginanaam uit een social media URL."""
    if not url:
        return ""
    parts = [p for p in urlparse(url).path.strip("/").split("/") if p]
    return parts[0] if parts else ""


def _fetch_page_text(url: str) -> str:
    """Haalt og:description of meta description op van een URL."""
    if not url:
        return ""
    try:
        r = requests.get(url, headers=SCRAPE_HEADERS, timeout=8, allow_redirects=True)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for attr, name in [("property", "og:description"), ("name", "description")]:
                tag = soup.find("meta", {attr: name})
                if tag and tag.get("content"):
                    return tag["content"]
    except Exception:
        pass
    return ""


def _parse_follower_count(text: str) -> str:
    """Extraheert volgersaantal uit tekst."""
    if not text:
        return ""
    for p in [
        r"([\d.,]+[KkMm]?)\s*(?:followers|volgers|abonnees|subscribers)",
        r"([\d.,]+[KkMm]?)\s*(?:likes|vind-ik-leuks|fans)",
    ]:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return ""


def _socialblade_count(platform: str, handle: str) -> str:
    """Haalt volgersaantal op via Social Blade als fallback."""
    if not handle:
        return ""
    paths = {"instagram": "instagram/user", "facebook": "facebook/page"}
    path = paths.get(platform)
    if not path:
        return ""
    try:
        r = requests.get(
            f"https://socialblade.com/{path}/{handle}",
            headers=SCRAPE_HEADERS,
            timeout=10,
        )
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            # Social Blade zet volgers in een <span> naast het label
            text = soup.get_text(" ", strip=True)
            m = re.search(r"([\d,]+)\s*(?:Followers|Subscriber)", text, re.IGNORECASE)
            if m:
                # Converteer 1,234 → 1.234 (NL-stijl)
                return m.group(1).replace(",", ".")
    except Exception:
        pass
    return ""


@st.cache_data(ttl=3600)
def get_follower_counts(instagram_url: str, linkedin_url: str, facebook_url: str) -> dict:
    """Haalt volgersaantallen op: eerst direct, dan via Social Blade."""
    counts = {"instagram": "—", "linkedin": "—", "facebook": "—"}

    # LinkedIn — werkt direct via og:description
    if linkedin_url:
        count = _parse_follower_count(_fetch_page_text(linkedin_url))
        counts["linkedin"] = count or "—"

    # Instagram — direct geblokkeerd, gebruik Social Blade
    if instagram_url:
        count = _parse_follower_count(_fetch_page_text(instagram_url))
        if not count:
            handle = _extract_handle(instagram_url)
            count = _socialblade_count("instagram", handle)
        counts["instagram"] = count or "—"

    # Facebook — direct geblokkeerd, gebruik Social Blade
    if facebook_url:
        count = _parse_follower_count(_fetch_page_text(facebook_url))
        if not count:
            handle = _extract_handle(facebook_url)
            count = _socialblade_count("facebook", handle)
        counts["facebook"] = count or "—"

    return counts


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


# ── Globale CSS ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* Card-stijl voor elke klant */
.client-card {
    display: flex;
    align-items: stretch;
    border: 1px solid #e4e4e7;
    border-radius: 12px;
    margin-bottom: 10px;
    overflow: hidden;
    background: #ffffff;
    box-shadow: 0 1px 3px rgba(0,0,0,.06);
    transition: box-shadow .15s;
}
.client-card:hover {
    box-shadow: 0 3px 10px rgba(0,0,0,.1);
}

/* Logo-blok links */
.client-logo-block {
    width: 64px;
    min-width: 64px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f4f4f5;
    border-right: 1px solid #e4e4e7;
    padding: 12px 8px;
}
.client-logo-block img {
    width: 44px;
    height: 44px;
    border-radius: 8px;
    object-fit: cover;
}
.client-logo-placeholder {
    width: 44px;
    height: 44px;
    border-radius: 8px;
    background: #d4d4d8;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
}

/* Koptekst rechts van het logo */
.client-header-content {
    flex: 1;
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 4px;
}
.client-name {
    font-size: 15px;
    font-weight: 700;
    color: #18181b;
    line-height: 1.2;
}
.client-meta {
    font-size: 13px;
    color: #71717a;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
}
.client-meta img {
    vertical-align: middle;
    margin-right: 3px;
}

/* Verberg de Streamlit expander-knop stijl binnen kaarten */
.card-expander [data-testid="stExpander"] {
    border: none !important;
    box-shadow: none !important;
    border-radius: 0 !important;
}
.card-expander [data-testid="stExpander"] summary {
    padding: 14px 16px !important;
    border-bottom: 1px solid #f0f0f0;
}
</style>
""", unsafe_allow_html=True)

# ── Layout ────────────────────────────────────────────────────────────────────

st.title("📱 Social Media Agent")
st.caption("Live overzicht van actieve klanten en geplande contentruns")


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
        img_url   = get_profile_image(
            client.get("linkedin_url", ""),
            client.get("website_url", ""),
        )
        followers = get_follower_counts(
            client.get("instagram_url", ""),
            client.get("linkedin_url", ""),
            client.get("facebook_url", ""),
        )

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
    "https://www.googleapis.com/auth/drive",
]

STATUS_OPTIONS  = ["concept", "goedgekeurd", "afgewezen"]
STATUS_COLORS   = {"concept": "#f59e0b", "goedgekeurd": "#22c55e", "afgewezen": "#ef4444"}
STATUS_LABELS   = {"concept": "⏳ Concept", "goedgekeurd": "✅ Goedgekeurd", "afgewezen": "❌ Afgewezen"}


def _get_write_client(sa_info: dict):
    creds = WriteCredentials.from_service_account_info(sa_info, scopes=WRITE_SCOPES)
    return gspread.authorize(creds)


@st.cache_data(ttl=60)
def load_post_tabs(spreadsheet_id: str, sa_info_json: str) -> list[str]:
    """Geeft alle tabbladen terug die beginnen met 'Posts_'."""
    sa_info = json.loads(sa_info_json)
    gc = _get_write_client(sa_info)
    spreadsheet = gc.open_by_key(spreadsheet_id)
    return sorted(
        [ws.title for ws in spreadsheet.worksheets() if ws.title.startswith("Posts_")],
        reverse=True,
    )


@st.cache_data(ttl=30)
def load_posts_from_tab(spreadsheet_id: str, tab_name: str, sa_info_json: str) -> list[dict]:
    """Laadt alle posts uit een specifiek tabblad."""
    sa_info = json.loads(sa_info_json)
    gc = _get_write_client(sa_info)
    worksheet = gc.open_by_key(spreadsheet_id).worksheet(tab_name)
    return worksheet.get_all_records(default_blank="")


def save_statuses(spreadsheet_id: str, tab_name: str, updates: dict, sa_info_json: str):
    """Schrijft statuswijzigingen terug naar het tabblad. updates = {row_index: (status, opmerking)}"""
    sa_info = json.loads(sa_info_json)
    gc = _get_write_client(sa_info)
    worksheet = gc.open_by_key(spreadsheet_id).worksheet(tab_name)
    batch = []
    for row_idx, (status, opmerking) in updates.items():
        batch.append({"range": f"H{row_idx}:I{row_idx}", "values": [[status, opmerking]]})
    worksheet.batch_update(batch, value_input_option="RAW")


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


with tab_goedkeuring:
    st.subheader("Posts goedkeuren per week")

    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID") or st.secrets.get("GOOGLE_SHEETS_SPREADSHEET_ID")
    sa_json = _sa_info_json()

    if not spreadsheet_id or not sa_json:
        st.error("Credentials ontbreken.")
    else:
        tabs = load_post_tabs(spreadsheet_id, sa_json)

        if not tabs:
            st.info("Nog geen posts beschikbaar. Voer eerst de pipeline uit zodat posts naar Google Sheets worden geüpload.")
        else:
            # Weekkiezer
            selected_tab = st.selectbox(
                "Selecteer een week",
                tabs,
                format_func=lambda t: t.replace("Posts_", "").replace("_W", " · Week "),
            )

            posts = load_posts_from_tab(spreadsheet_id, selected_tab, sa_json)

            if not posts:
                st.warning("Geen posts gevonden in dit tabblad.")
            else:
                # Voortgangsoverzicht
                total   = len(posts)
                approved = sum(1 for p in posts if p.get("status") == "goedgekeurd")
                rejected = sum(1 for p in posts if p.get("status") == "afgewezen")
                pending  = total - approved - rejected

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Totaal posts", total)
                c2.metric("✅ Goedgekeurd", approved)
                c3.metric("❌ Afgewezen", rejected)
                c4.metric("⏳ Concept", pending)

                st.divider()

                # Groepeer per klant
                clients_in_week = {}
                for i, post in enumerate(posts, start=2):  # rij 2 = eerste datarij
                    name = post.get("bedrijfsnaam", "Onbekend")
                    if name not in clients_in_week:
                        clients_in_week[name] = []
                    clients_in_week[name].append((i, post))

                # Session state voor wijzigingen
                state_key = f"updates_{selected_tab}"
                if state_key not in st.session_state:
                    st.session_state[state_key] = {}

                for bedrijfsnaam, rows in clients_in_week.items():
                    statuses = [r[1].get("status", "concept") for r in rows]
                    all_ok   = all(s == "goedgekeurd" for s in statuses)
                    any_rej  = any(s == "afgewezen" for s in statuses)
                    badge    = "✅" if all_ok else ("❌" if any_rej else "⏳")

                    with st.expander(f"{badge} {bedrijfsnaam} — {len(rows)} posts", expanded=not all_ok):
                        for platform in ("instagram", "linkedin", "facebook"):
                            platform_rows = [(i, p) for i, p in rows if p.get("platform") == platform]
                            if not platform_rows:
                                continue

                            color = PLATFORM_COLORS[platform]
                            icon  = PLATFORM_ICON_HTML[platform]
                            st.markdown(
                                f'<p style="font-weight:700;color:{color};margin:12px 0 6px 0;">'
                                f'{icon}{PLATFORM_LABELS[platform]}</p>',
                                unsafe_allow_html=True,
                            )

                            for row_idx, post in platform_rows:
                                dag   = post.get("dag", "")
                                datum = post.get("publicatiedatum", "")
                                current_status = st.session_state[state_key].get(
                                    row_idx, (post.get("status", "concept"), post.get("opmerkingen", ""))
                                )[0]

                                with st.container():
                                    st.markdown(
                                        f'<p style="font-weight:600;margin:8px 0 2px 0;">📅 {dag} — {datum}</p>',
                                        unsafe_allow_html=True,
                                    )
                                    st.markdown(
                                        f'<div style="background:#f8f8f8;border-left:3px solid {color};'
                                        f'padding:10px 14px;border-radius:0 8px 8px 0;'
                                        f'font-size:14px;margin-bottom:4px;white-space:pre-wrap;">'
                                        f'{post.get("caption","")}</div>',
                                        unsafe_allow_html=True,
                                    )
                                    st.caption(post.get("hashtags", ""))

                                    col_s, col_o = st.columns([2, 4])
                                    with col_s:
                                        new_status = st.selectbox(
                                            "Status",
                                            STATUS_OPTIONS,
                                            index=STATUS_OPTIONS.index(current_status),
                                            key=f"status_{row_idx}",
                                            label_visibility="collapsed",
                                        )
                                    with col_o:
                                        current_note = st.session_state[state_key].get(
                                            row_idx, (post.get("status", "concept"), post.get("opmerkingen", ""))
                                        )[1]
                                        new_note = st.text_input(
                                            "Opmerking",
                                            value=current_note,
                                            placeholder="Optionele opmerking...",
                                            key=f"note_{row_idx}",
                                            label_visibility="collapsed",
                                        )

                                    # Sla lokaal op in session state
                                    st.session_state[state_key][row_idx] = (new_status, new_note)
                                    st.markdown("<hr style='margin:8px 0;border:none;border-top:1px solid #eee;'>", unsafe_allow_html=True)

                # Opslaan knop
                st.divider()
                col_btn, col_info = st.columns([2, 8])
                with col_btn:
                    if st.button("💾 Wijzigingen opslaan", type="primary", use_container_width=True):
                        updates = st.session_state.get(state_key, {})
                        if updates:
                            with st.spinner("Opslaan..."):
                                save_statuses(spreadsheet_id, selected_tab, updates, sa_json)
                                load_posts_from_tab.clear()
                            st.success(f"{len(updates)} posts opgeslagen in Google Sheets.")
                        else:
                            st.info("Geen wijzigingen om op te slaan.")
                with col_info:
                    st.caption("Wijzigingen worden direct opgeslagen in het Google Sheets-tabblad.")
