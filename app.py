"""
OCTO FUND DASHBOARD v4.8 - app.py
Add Bulk Investors Upload via Excel/CSV
"""

import streamlit as st
import hashlib
import pandas as pd
import json
import requests
import io
from datetime import datetime, date, timedelta
from supabase import create_client, Client

OPENROUTER_API_KEY = st.secrets.get("OPENROUTER_API_KEY", "")

def format_currency(amount: float, currency_sym: str = "$") -> str:
    if amount is None or amount == 0:
        return "—"
    if amount >= 1_000_000_000:
        return f"{currency_sym}{amount/1_000_000_000:.2f}B"
    elif amount >= 1_000_000:
        return f"{currency_sym}{amount/1_000_000:.1f}M"
    elif amount >= 1_000:
        return f"{currency_sym}{amount/1_000:.0f}K"
    else:
        return f"{currency_sym}{amount:,.0f}"

def extract_pdf_text(pdf_bytes: bytes) -> str:
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_text = []
    for i, page in enumerate(doc):
        text = page.get_text().strip()
        if text:
            pages_text.append(f"--- Page {i+1} ---\n{text}")
    doc.close()
    full_text = "\n".join(pages_text)
    if len(full_text) <= 12000:
        return full_text
    return full_text[:4000] + "\n\n[...]\n\n" + full_text[-8000:]

def analyze_pdf_with_ai(pdf_bytes: bytes) -> dict:
    pdf_text = extract_pdf_text(pdf_bytes)
    prompt = f"""You are an expert private equity analyst. Carefully analyze this fund presentation and extract ALL available information.
Be thorough - search the entire text for financial terms, fees, returns, geography, and strategy details.

Return ONLY a valid JSON object with these exact keys (use null only if truly not found anywhere):
{{
"fund_name": "full fund name including fund number",
"manager": "management company name",
"strategy": "one of: Growth, VC, Tech, Niche, Special Situations",
"fund_size_target": number in millions USD (e.g. 2500 for $2.5B),
"fund_size_hard_cap": number in millions USD or null,
"currency": "USD or EUR",
"target_return_moic_low": number (e.g. 3.0),
"target_return_moic_high": number (e.g. 5.0),
"target_irr_gross": number as percentage (e.g. 25),
"target_irr_net": number as percentage or null,
"vintage_year": number (year) or null,
"fund_life_years": number or null,
"investment_period_years": number or null,
"mgmt_fee_pct": number (e.g. 2.0),
"carried_interest_pct": number (e.g. 20),
"preferred_return_pct": number (e.g. 8),
"geographic_focus": "specific description e.g. United States, North America, Global",
"sector_focus": "specific sectors e.g. Technology, Healthcare, Consumer, AI",
"portfolio_companies_target": number of investments planned or null,
"max_single_investment_pct": number (e.g. 15) or null,
"aum_manager": number in billions (e.g. 33.3) or null,
"key_highlights": "3-4 sentence summary of the fund investment thesis and differentiators"
}}

IMPORTANT: Fund size in billions -> convert to millions. E.g. $2.5B = 2500.
Return ONLY the JSON, no markdown, no extra text.

FUND PRESENTATION TEXT:
{pdf_text}"""

    payload = {
        "model": "anthropic/claude-3.5-sonnet",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://octo-dashboard.streamlit.app"
    }
    resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=90)
    if resp.status_code != 200:
        raise Exception(f"OpenRouter error {resp.status_code}: {resp.text[:300]}")
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if "```" in content:
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    return json.loads(content.strip())

def analyze_capital_call_pdf_with_ai(pdf_bytes: bytes) -> dict:
    pdf_text = extract_pdf_text(pdf_bytes)
    prompt = f"""You are an expert private equity fund accountant. Carefully analyze this Capital Call Notice and extract the financial details.

Return ONLY a valid JSON object with these exact keys (use 0 if a specific breakdown amount is not found, use null for missing dates):
{{
    "call_date": "YYYY-MM-DD" (The date the notice was issued/written),
    "payment_date": "YYYY-MM-DD" (The due date for the payment/wire),
    "amount": total amount requested from the LP (number, e.g., 158889),
    "investments": amount allocated specifically to investments or capital commitment (number, e.g., 157143),
    "mgmt_fee": amount allocated to management fees (number),
    "fund_expenses": amount allocated to fund expenses or reserve (number, e.g., 1746)
}}

IMPORTANT: Return ONLY the JSON, no markdown, no extra text. Ensure amounts are numbers without commas.

CAPITAL CALL TEXT:
{pdf_text}"""

    payload = {
        "model": "anthropic/claude-3.5-sonnet",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://octo-dashboard.streamlit.app"
    }
    resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=90)
    if resp.status_code != 200:
        raise Exception(f"OpenRouter error {resp.status_code}: {resp.text[:300]}")
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if "```" in content:
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    return json.loads(content.strip())

def analyze_quarterly_report_with_ai(report_text: str) -> dict:
    prompt = f"""You are an expert private equity fund accountant. Carefully analyze this quarterly report, financial statement, or capital account statement and extract the financial performance metrics.

Return ONLY a valid JSON object with these exact keys (use null if a specific metric is not found):
{{
    "year": number (e.g., 2025, derived from the report date or As Of date),
    "quarter": number (1, 2, 3, or 4, derived from the report date, e.g., Sept 30 is Q3),
    "report_date": "YYYY-MM-DD" (The "As of" date or period end date),
    "nav": number (Net Asset Value, Ending Capital Balance, or Total Partners' Capital, without commas. e.g., 2323320330),
    "tvpi": number (Total Value to Paid-In multiple, e.g., 1.52, or null),
    "dpi": number (Distributions to Paid-In multiple, e.g., 0.45, or null),
    "rvpi": number (Residual Value to Paid-In multiple, e.g., 1.07, or null),
    "irr": number (Internal Rate of Return as a percentage, e.g., 15.5, or null)
}}

IMPORTANT: Return ONLY the JSON, no markdown, no extra text. Ensure amounts are numbers without commas. If a value like IRR is 15.5%, return 15.5.

REPORT TEXT:
{report_text}"""

    payload = {
        "model": "anthropic/claude-3.5-sonnet",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://octo-dashboard.streamlit.app"
    }
    resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=90)
    if resp.status_code != 200:
        raise Exception(f"OpenRouter error {resp.status_code}: {resp.text[:300]}")
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if "```" in content:
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    return json.loads(content.strip())


st.set_page_config(
    page_title="ALT Group | Octo Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;700&display=swap');
    
    * { font-family: 'Heebo', sans-serif; }
    p, label, h1, h2, h3, h4, h5, h6, a, li, input, textarea, button, [data-testid="stMetricValue"] {
        font-family: 'Heebo', sans-serif !important;
    }
    [data-testid="stExpander"] summary p { font-family: 'Heebo', sans-serif !important; }

    [data-testid="stExpanderToggleIcon"], [data-testid="stExpanderToggleIcon"] *,
    [data-testid="stIconMaterial"], .material-symbols-rounded, .material-icons, i, svg {
        font-family: 'Material Symbols Rounded', 'Material Icons' !important;
        font-feature-settings: 'liga' !important;
        -webkit-font-feature-settings: 'liga' !important;
        text-transform: none !important; letter-spacing: normal !important;
    }
    [data-testid="stExpanderToggleIcon"] { max-width: 24px !important; overflow: hidden !important; white-space: nowrap !important; }

    .main { direction: rtl; }
    .stMarkdown, .stText, h1, h2, h3, p { direction: rtl; text-align: right; }
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"], section[data-testid="stSidebar"] + div { 
        background-color: #0f1117 !important; color: #e2e8f0 !important;
    }
    p, span, label, div { color: #e2e8f0; }

    [data-testid="stExpander"] summary { 
        color: #e2e8f0 !important; direction: rtl !important; display: flex !important;
        flex-direction: row-reverse !important; align-items: center !important; gap: 8px !important;
    }
    [data-testid="stExpander"] { 
        background: #1a1a2e !important; border: 1px solid #0f3460 !important;
        border-radius: 10px !important; margin-bottom: 8px !important;
    }

    [data-testid="stSelectbox"] > div > div, [data-testid="stSelectbox"] > div > div > div,
    [data-testid="stSelectbox"] span:not(.material-symbols-rounded) { 
        background-color: #1e293b !important; color: #e2e8f0 !important; border-color: #334155 !important;
    }
    [data-baseweb="popover"], [data-baseweb="popover"] > div, [data-baseweb="popover"] > div > div { background-color: #1e293b !important; }
    [data-baseweb="select"] > div, [data-baseweb="menu"], [data-baseweb="menu"] > div, [data-baseweb="menu"] ul {
        background-color: #1e293b !important; border: 1px solid #334155 !important;
    }
    [data-baseweb="menu"] * { color: #e2e8f0 !important; }
    ul[data-testid="stSelectboxVirtualDropdown"], [role="listbox"], [role="listbox"] > div, [role="listbox"] li { 
        background-color: #1e293b !important; border-color: #334155 !important;
    }
    [role="option"] { background-color: #1e293b !important; color: #e2e8f0 !important; }
    [role="option"]:hover, [role="option"][aria-selected="true"] { background-color: #0f3460 !important; }
    [role="option"] * { color: #e2e8f0 !important; background-color: transparent !important; }
    li[class*="option"], div[class*="option"] { background-color: #1e293b !important; color: #e2e8f0 !important; }

    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460; border-radius: 12px; padding: 12px; overflow: hidden;
    }
    [data-testid="metric-container"] label, [data-testid="metric-container"] div { color: #94a3b8 !important; }
    [data-testid="metric-container"] [data-testid="stMetricValue"] { 
        color: #ffffff !important; font-weight: 700 !important; font-size: 1.3rem !important; 
        word-break: break-word !important; white-space: normal !important; line-height: 1.2 !important;
    }

    [data-testid="stSidebar"] { background: #0f1117 !important; }
    [data-testid="stTabs"] [role="tab"] { color: #94a3b8 !important; }
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] { color: #ffffff !important; border-bottom-color: #3b82f6 !important; }

    [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input,
    [data-testid="stTextArea"] textarea, [data-testid="stDateInput"] input { 
        background: #1e293b !important; color: #e2e8f0 !important; border-color: #334155 !important;
    }

    [data-testid="stDataFrame"] { color: #e2e8f0 !important; }
    [data-testid="stCaptionContainer"] { color: #94a3b8 !important; }
    hr { border-color: #1e293b !important; }
    .dashboard-header {
        background: linear-gradient(90deg, #1a1a2e, #0f3460); padding: 20px 30px; border-radius: 12px; margin-bottom: 24px;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_supabase() -> Client:
    url = "https://lyaxipwsvlnsymdbkokq.supabase.co"
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx5YXhpcHdzdmxuc3ltZGJrb2txIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIwMjQzNTQsImV4cCI6MjA4NzYwMDM1NH0.6LyuFmRi6ApaWbgy_acQxEsp6r96dkG8xYJZKFpB6aQ"
    return create_client(url, key)

# --- AUDIT LOGGING FUNCTION ---
def log_action(action: str, table_name: str, details: str, old_data: dict = None):
    try:
        sb = get_supabase()
        username = st.session_state.get("username", "system")
        sb.table("audit_logs").insert({
            "username": username,
            "action": action,
            "table_name": table_name,
            "details": details,
            "old_data": old_data or {}
        }).execute()
    except Exception:
        pass

def get_audit_logs():
    try: return get_supabase().table("audit_logs").select("*").order("created_at", desc=True).limit(100).execute().data or []
    except: return []

# --- DB Functions ---
def get_funds():
    try: return get_supabase().table("funds").select("*").order("name").execute().data or []
    except Exception as e: st.error(f"שגיאה בטעינת קרנות: {e}"); return []

def get_capital_calls(fund_id=None):
    try:
        query = get_supabase().table("capital_calls").select("*").order("call_number")
        if fund_id:
            query = query.eq("fund_id", fund_id)
        return query.execute().data or []
    except: return []

def get_distributions(fund_id):
    try: return get_supabase().table("distributions").select("*").eq("fund_id", fund_id).order("dist_date").execute().data or []
    except: return []

def get_quarterly_reports(fund_id=None):
    try: 
        query = get_supabase().table("quarterly_reports").select("*").order("year,quarter")
        if fund_id:
            query = query.eq("fund_id", fund_id)
        return query.execute().data or []
    except: return []

def get_pipeline_funds():
    try: return get_supabase().table("pipeline_funds").select("*").order("target_close_date").execute().data or []
    except: return []

def get_gantt_tasks(pipeline_fund_id=None):
    try: 
        query = get_supabase().table("gantt_tasks").select("*").order("start_date")
        if pipeline_fund_id:
            query = query.eq("pipeline_fund_id", pipeline_fund_id)
        return query.execute().data or []
    except: return []

def get_investors():
    try: return get_supabase().table("investors").select("*").execute().data or []
    except: return []

def get_lp_calls():
    try: return get_supabase().table("lp_calls").select("*").order("call_date").execute().data or []
    except: return []

def get_lp_payments():
    try: return get_supabase().table("lp_payments").select("*").execute().data or []
    except: return []

# --- SMART ALERTS SYSTEM ---
def check_and_show_alerts():
    if "dismissed_banners" not in st.session_state:
        st.session_state.dismissed_banners = set()
    if "shown_toasts" not in st.session_state:
        st.session_state.shown_toasts = set()

    today = date.today()
    funds_dict = {f["id"]: f for f in get_funds()}
    pipe_dict = {f["id"]: f["name"] for f in get_pipeline_funds()}

    for cc in get_capital_calls():
        if not cc.get("payment_date"): continue
        try:
            deadline = datetime.strptime(str(cc["payment_date"]).split("T")[0], "%Y-%m-%d").date()
            days_left = (deadline - today).days
        except: continue

        if days_left in [0, 1, 3, 7]:
            fund_info = funds_dict.get(cc.get("fund_id"), {})
            fname = fund_info.get("name", "קרן לא ידועה")
            curr = "€" if fund_info.get("currency") == "EUR" else "$"
            amt = format_currency(cc.get("amount", 0), curr)
            
            if days_left in [0, 1]:
                alert_id = f"cc_banner_{cc['id']}_{days_left}"
                if alert_id not in st.session_state.dismissed_banners:
                    c1, c2 = st.columns([15, 1])
                    with c1:
                        if days_left == 0:
                            st.error(f"🚨 **היום!** דדליין תשלום קריאה לכסף בקרן **{fname}** ע\"ס **{amt}**.")
                        else:
                            st.warning(f"⚠️ **מחר!** דדליין תשלום קריאה לכסף בקרן **{fname}** ע\"ס **{amt}**.")
                    with c2:
                        if st.button("✖", key=f"btn_{alert_id}", help="סגור התראה"):
                            st.session_state.dismissed_banners.add(alert_id)
                            st.rerun()
            else:
                alert_id = f"cc_toast_{cc['id']}_{days_left}"
                if alert_id not in st.session_state.shown_toasts:
                    st.toast(f"🔔 מתקרב: קריאה לכסף בקרן {fname} בעוד {days_left} ימים.", icon="💸")
                    st.session_state.shown_toasts.add(alert_id)

    for lpc in get_lp_calls():
        if not lpc.get("call_date"): continue
        try:
            deadline = datetime.strptime(str(lpc["call_date"]).split("T")[0], "%Y-%m-%d").date()
            days_left = (deadline - today).days
        except: continue

        if days_left in [0, 1, 3, 7]:
            if days_left in [0, 1]:
                alert_id = f"lpc_banner_{lpc['id']}_{days_left}"
                if alert_id not in st.session_state.dismissed_banners:
                    c1, c2 = st.columns([15, 1])
                    with c1:
                        if days_left == 0:
                            st.error(f"🚨 **היום!** תאריך יעד לקבלת כספים מהמשקיעים (קריאה של {lpc.get('call_pct')}%)")
                        else:
                            st.warning(f"⚠️ **מחר!** תאריך יעד לקבלת כספים מהמשקיעים (קריאה של {lpc.get('call_pct')}%)")
                    with c2:
                        if st.button("✖", key=f"btn_{alert_id}", help="סגור התראה"):
                            st.session_state.dismissed_banners.add(alert_id)
                            st.rerun()
            else:
                alert_id = f"lpc_toast_{lpc['id']}_{days_left}"
                if alert_id not in st.session_state.shown_toasts:
                    st.toast(f"🔔 מתקרב: יעד גבייה מהמשקיעים בעוד {days_left} ימים.", icon="👥")
                    st.session_state.shown_toasts.add(alert_id)

    all_tasks = get_gantt_tasks()
    active_tasks = [t for t in all_tasks if t.get("status") != "done"]
    for t in active_tasks:
        if not t.get("due_date"): continue
        try:
            deadline = datetime.strptime(str(t["due_date"]).split("T")[0], "%Y-%m-%d").date()
            days_left = (deadline - today).days
        except: continue

        if days_left in [0, 1, 3, 7]:
            alert_id = f"gantt_toast_{t['id']}_{days_left}"
            if alert_id not in st.session_state.shown_toasts:
                p_name = pipe_dict.get(t.get("pipeline_fund_id"), "קרן בבחינה")
                day_str = "היום" if days_left == 0 else "מחר" if days_left == 1 else f"בעוד {days_left} ימים"
                st.toast(f"🗓️ משימה ב-{p_name}: {t['task_name']} מסתיימת {day_str}!", icon="🎯")
                st.session_state.shown_toasts.add(alert_id)

# --- Auth ---
USERS = {"liron": "octo2026", "alex": "octo2026", "team": "altgroup2026"}

def check_login(username, password):
    return USERS.get(username.strip().lower()) == password

def show_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 📊 Octo Fund Dashboard")
        st.markdown("**ALT Group** | Private Capital")
        st.divider()
        username = st.text_input("שם משתמש", placeholder="liron")
        password = st.text_input("סיסמא", type="password")
        if st.button("כניסה", type="primary", use_container_width=True):
            if check_login(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username.strip().lower()
                st.rerun()
            else:
                st.error("שם משתמש או סיסמא שגויים")

def require_login():
    if not st.session_state.get("logged_in"):
        show_login()
        st.stop()

def main():
    require_login()
    with st.sidebar:
        st.markdown("## 📊 Octo Dashboard")
        st.markdown("**ALT Group** | Private Capital")
        st.divider()
        page = st.radio("ניווט", [
            "🏠 סקירה כללית",
            "📁 תיק השקעות",
            "👥 משקיעים",
            "🔍 Pipeline",
            "📈 דוחות רבעוניים",
            "📋 יומן פעולות"
        ], label_visibility="collapsed")
        st.divider()
        st.caption(f"משתמש: {st.session_state.get('username', '')}")
        st.caption("גרסה 4.8 | פברואר 2026")
        st.divider()
        if st.button("🚪 התנתק", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()

    if "סקירה כללית" in page: show_overview()
    elif "תיק השקעות" in page: show_portfolio()
    elif "משקיעים" in page: show_investors()
    elif "Pipeline" in page: show_pipeline()
    elif "דוחות" in page: show_reports()
    elif "יומן" in page: show_audit_logs()

def show_audit_logs():
    st.title("📋 יומן פעולות מערכת (Audit Logs)")
    st.markdown("כאן ניתן לצפות בהיסטוריית שינויים ומחיקות שבוצעו במערכת, ולשחזר נתונים במידת הצורך.")
    
    logs = get_audit_logs()
    if not logs:
        st.info("אין עדיין תיעוד פעולות במערכת.")
        return
        
    for log in logs:
        dt_str = log["created_at"].replace("T", " ")[:16]
        icon = "🔴" if log["action"] == "DELETE" else "🟡" if log["action"] == "UPDATE" else "⚪"
        
        with st.expander(f"{icon} {dt_str} | משתמש: {log['username']} | {log['details']}"):
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**סוג פעולה:** {log['action']}")
            with col2:
                st.write(f"**טבלת יעד:** {log['table_name']}")
            
            if log.get("old_data") and log["old_data"] != {}:
                st.write("**נתונים לפני השינוי/מחיקה (לצורך שחזור ידני):**")
                st.json(log["old_data"])

def show_overview():
    check_and_show_alerts()

    st.markdown("""
    <div class="dashboard-header">
    <h1 style="color:white;margin:0;">📊 Octo Fund Dashboard</h1>
    <p style="color:#94a3b8;margin:4px 0 0 0;">ALT Group | ניהול השקעות אלטרנטיביות</p>
    </div>
    """, unsafe_allow_html=True)

    funds = get_funds()
    pipeline = get_pipeline_funds()

    total_commitment_usd = sum(f.get("commitment") or 0 for f in funds if f.get("currency") == "USD")
    total_commitment_eur = sum(f.get("commitment") or 0 for f in funds if f.get("currency") == "EUR")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("קרנות פעילות", len(funds))
    with col2:
        st.metric("התחייבויות USD", format_currency(total_commitment_usd, "$"))
    with col3:
        st.metric("התחייבויות EUR", format_currency(total_commitment_eur, "€"))
    with col4:
        st.metric("קרנות Pipeline", len(pipeline))

    st.divider()
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("📋 סטטוס קרנות")
        if funds:
            rows = []
            for f in funds:
                calls = get_capital_calls(f["id"])
                total_called = sum(c.get("amount") or 0 for c in calls)
                commitment = f.get("commitment") or 0
                pct = f"{total_called/commitment*100:.1f}%" if commitment > 0 else "—"
                currency_sym = "€" if f.get("currency") == "EUR" else "$"
                rows.append({
                    "קרן": f["name"],
                    "מטבע": f.get("currency", "USD"),
                    "התחייבות": format_currency(commitment, currency_sym) if commitment else "—",
                    "סכום שנקרא": format_currency(total_called, currency_sym) if total_called > 0 else "—",
                    "נקרא %": pct,
                    "סטטוס": "פעיל" if f.get("status") == "active" else f.get("status", ""),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("אין קרנות במערכת")

    with col2:
        st.subheader("🔔 אירועים קרובים")
        future_calls_found = False
        for f in funds:
            calls = get_capital_calls(f["id"])
            future = [c for c in calls if c.get("is_future")]
            for c in future:
                future_calls_found = True
                st.markdown(f"""
                <div style="background:#1a3a1a;border-radius:8px;padding:12px;margin-bottom:8px;">
                    <small style="color:#4ade80">{c.get('payment_date','')}</small><br>
                    <strong>{f['name']}</strong><br>
                    <span style="color:#94a3b8">Call #{c.get('call_number')} | {format_currency(c.get('amount',0), '$')}</span>
                </div>
                """, unsafe_allow_html=True)
        if not future_calls_found:
            st.info("💡 הוסף Calls עתידיים כדי לראות תחזית כאן")

def show_investors():
    st.title("👥 ניהול משקיעים וקריאות להון (Master Fund)")
    
    currency_sym = "$" 
    sb = get_supabase()

    investors = get_investors()
    lp_calls = get_lp_calls()
    payments = get_lp_payments()

    col_add_inv, col_manage_inv = st.columns(2)
    
    with col_add_inv:
        with st.expander("➕ הוסף משקיע/ים לקרן (FOF)"):
            tab_manual, tab_bulk = st.tabs(["הוספה ידנית", "העלאת קובץ אקסל"])
            with tab_manual:
                with st.form("add_lp_form"):
                    c1, c2 = st.columns(2)
                    with c1:
                        inv_name = st.text_input("שם משקיע")
                    with c2:
                        inv_commit = st.number_input(f"סכום התחייבות ({currency_sym})", min_value=0.0)
                    if st.form_submit_button("שמור משקיע", type="primary"):
                        try:
                            sb.table("investors").insert({"name": inv_name, "commitment": inv_commit}).execute()
                            log_action("INSERT", "investors", f"הוסף משקיע חדש: {inv_name}", {"commitment": inv_commit})
                            st.success("משקיע נוסף!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"שגיאה: {e}")
            with tab_bulk:
                st.markdown("<small>העלה קובץ עם 2 עמודות: עמודה א' = <b>שם המשקיע</b>, עמודה ב' = <b>סכום התחייבות</b></small>", unsafe_allow_html=True)
                uploaded_inv_file = st.file_uploader("בחר קובץ (Excel / CSV)", type=["xlsx", "xls", "csv"], key="inv_uploader")
                if uploaded_inv_file:
                    if st.button("טען משקיעים למערכת", type="primary", use_container_width=True):
                        with st.spinner("טוען משקיעים..."):
                            try:
                                if uploaded_inv_file.name.lower().endswith('.csv'):
                                    df = pd.read_csv(uploaded_inv_file)
                                else:
                                    df = pd.read_excel(uploaded_inv_file)
                                
                                if len(df.columns) >= 2:
                                    count = 0
                                    for idx, row in df.iterrows():
                                        name_val = str(row.iloc[0]).strip()
                                        if name_val.lower() == 'nan' or not name_val:
                                            continue
                                        
                                        # נקה פסיקים, רווחים וסימני מטבע כדי לוודא שהמספר יעבור
                                        commit_str = str(row.iloc[1]).replace(',', '').replace('$', '').replace('€', '').strip()
                                        try:
                                            commit_val = float(commit_str)
                                        except:
                                            commit_val = 0.0
                                        
                                        sb.table("investors").insert({"name": name_val, "commitment": commit_val}).execute()
                                        count += 1
                                    
                                    log_action("INSERT", "investors", f"נוספו {count} משקיעים בטעינה מקובץ אקסל", {})
                                    st.success(f"✅ {count} משקיעים נוספו בהצלחה!")
                                    st.rerun()
                                else:
                                    st.error("הקובץ חייב להכיל לפחות 2 עמודות.")
                            except Exception as e:
                                st.error(f"שגיאה בקריאת הקובץ: {e}")

    with col_manage_inv:
        with st.expander("⚙️ ניהול משקיעים קיימים (עריכה / מחיקה)"):
            if not investors:
                st.write("אין משקיעים במערכת.")
            for inv in investors:
                c1, c2, c3, c4 = st.columns([4, 3, 1, 1])
                with c1:
                    st.write(f"**{inv['name']}**")
                with c2:
                    st.write(format_currency(inv.get("commitment", 0), currency_sym))
                with c3:
                    if st.button("✏️", key=f"edit_inv_btn_{inv['id']}", help="עריכת משקיע"):
                        st.session_state[f"editing_inv_{inv['id']}"] = True
                with c4:
                    if st.button("🗑️", key=f"del_inv_btn_{inv['id']}", help="מחיקת משקיע"):
                        st.session_state[f"confirm_del_inv_{inv['id']}"] = True
                
                if st.session_state.get(f"confirm_del_inv_{inv['id']}"):
                    st.warning(f"למחוק את '{inv['name']}'?")
                    cd1, cd2 = st.columns(2)
                    with cd1:
                        if st.button("✅ כן", key=f"yes_del_inv_{inv['id']}"):
                            try:
                                log_action("DELETE", "investors", f"נמחק משקיע: {inv['name']}", inv)
                                sb.table("investors").delete().eq("id", inv["id"]).execute()
                                st.session_state.pop(f"confirm_del_inv_{inv['id']}", None)
                                st.rerun()
                            except Exception as e:
                                st.error(f"שגיאה: {e}")
                    with cd2:
                        if st.button("❌ ביטול", key=f"no_del_inv_{inv['id']}"):
                            st.session_state.pop(f"confirm_del_inv_{inv['id']}", None)
                            st.rerun()

                if st.session_state.get(f"editing_inv_{inv['id']}"):
                    with st.form(f"edit_inv_form_{inv['id']}"):
                        new_name = st.text_input("שם משקיע", value=inv["name"])
                        new_commit = st.number_input("סכום התחייבות", value=float(inv.get("commitment", 0)))
                        ce1, ce2 = st.columns(2)
                        with ce1:
                            if st.form_submit_button("💾 שמור שינויים"):
                                try:
                                    log_action("UPDATE", "investors", f"עודכן משקיע: {inv['name']} ל-{new_name}", inv)
                                    sb.table("investors").update({"name": new_name, "commitment": new_commit}).eq("id", inv["id"]).execute()
                                    st.session_state.pop(f"editing_inv_{inv['id']}", None)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"שגיאה: {e}")
                        with ce2:
                            if st.form_submit_button("❌ סגור"):
                                st.session_state.pop(f"editing_inv_{inv['id']}", None)
                                st.rerun()
                    st.divider()

    st.divider()
    st.markdown("### 📋 טבלת העברות משקיעים (סמן V להעברה)")
    if not investors:
        st.info("אין משקיעים מוגדרים. הוסף משקיע למעלה.")
        return

    data = []
    col_mapping = {}
    total_fund_commitment = 0
    
    for inv in investors:
        inv_commit = inv.get("commitment", 0)
        total_fund_commitment += inv_commit
        row = {
            "id": inv["id"],
            "שם משקיע": inv["name"],
            "התחייבות": format_currency(inv_commit, currency_sym)
        }
        for c in lp_calls:
            col_name = f"{c['call_date']} ({c['call_pct']}%)"
            col_mapping[col_name] = c
            payment = next((p for p in payments if p["lp_call_id"] == c["id"] and p["investor_id"] == inv["id"]), None)
            row[col_name] = payment["is_paid"] if payment else False
        data.append(row)

    df = pd.DataFrame(data)
    
    edited_df = st.data_editor(
        df,
        column_config={"id": None},
        disabled=["שם משקיע", "התחייבות"],
        hide_index=True,
        use_container_width=True,
        key="lp_global_editor"
    )

    if st.button("💾 שמור סטטוס העברות", type="primary"):
        try:
            for index, row in edited_df.iterrows():
                inv_id = row["id"]
                for col_name, c in col_mapping.items():
                    if col_name in row:
                        is_paid = bool(row[col_name])
                        existing = [p for p in payments if p["lp_call_id"] == c["id"] and p["investor_id"] == inv_id]
                        if existing:
                            if existing[0]["is_paid"] != is_paid:
                                sb.table("lp_payments").update({"is_paid": is_paid}).eq("id", existing[0]["id"]).execute()
                        else:
                            sb.table("lp_payments").insert({
                                "lp_call_id": c["id"],
                                "investor_id": inv_id,
                                "is_paid": is_paid
                            }).execute()
            st.success("✅ הסטטוסים עודכנו בהצלחה!")
            st.rerun()
        except Exception as e:
            st.error(f"שגיאה בעדכון: {e}")

    st.divider()
    st.markdown("### 📊 סיכום גביה לקריאות (FOF Level)")
    
    col_sum1, col_sum2 = st.columns([1, 3])
    with col_sum1:
        st.metric("סה״כ התחייבויות (LPs)", format_currency(total_fund_commitment, currency_sym))
    
    with col_sum2:
        if lp_calls:
            summary_data = []
            for c in lp_calls:
                call_pct = c["call_pct"] / 100.0
                total_called_amount = total_fund_commitment * call_pct
                
                paid_commit = 0
                for inv in investors:
                    payment = next((p for p in payments if p["lp_call_id"] == c["id"] and p["investor_id"] == inv["id"]), None)
                    if payment and payment["is_paid"]:
                        paid_commit += inv.get("commitment", 0)
                
                total_paid_amount = paid_commit * call_pct
                outstanding = total_called_amount - total_paid_amount
                
                summary_data.append({
                    "קריאה": f"{c['call_date']} ({c['call_pct']}%)",
                    "סה״כ נדרש": format_currency(total_called_amount, currency_sym),
                    "סה״כ התקבל": format_currency(total_paid_amount, currency_sym),
                    "יתרה חסרה": format_currency(outstanding, currency_sym)
                })
            st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)
        else:
            st.info("אין קריאות פעילות עדיין.")

    st.divider()
    st.markdown("### ➕ ניהול קריאות לכסף (Capital Calls)")
    
    col_call_add, col_call_manage = st.columns([1, 1])
    
    with col_call_add:
        with st.form("new_global_lp_call"):
            st.markdown("**יצירת קריאה חדשה**")
            new_call_date = st.date_input("תאריך קריאה")
            new_call_pct = st.number_input("אחוז מההתחייבות (%)", min_value=0.0, max_value=100.0, step=0.1)
            if st.form_submit_button("הוסף קריאה", use_container_width=True):
                try:
                    sb.table("lp_calls").insert({
                        "call_date": str(new_call_date),
                        "call_pct": new_call_pct
                    }).execute()
                    st.success("✅ קריאה חדשה נוספה לטבלה!")
                    st.rerun()
                except Exception as e:
                    st.error(f"שגיאה: {e}")

    with col_call_manage:
        with st.expander("⚙️ קריאות קיימות (עריכה / מחיקה)"):
            if not lp_calls:
                st.write("אין קריאות קיימות.")
            for c in lp_calls:
                lc1, lc2, lc3, lc4 = st.columns([3, 2, 1, 1])
                with lc1:
                    st.write(c['call_date'])
                with lc2:
                    st.write(f"{c['call_pct']}%")
                with lc3:
                    if st.button("✏️", key=f"edit_lpc_btn_{c['id']}"):
                        st.session_state[f"editing_lpc_{c['id']}"] = True
                with lc4:
                    if st.button("🗑️", key=f"del_lpc_btn_{c['id']}"):
                        st.session_state[f"confirm_del_lpc_{c['id']}"] = True
                
                if st.session_state.get(f"confirm_del_lpc_{c['id']}"):
                    st.warning("למחוק קריאה זו?")
                    d_c1, d_c2 = st.columns(2)
                    with d_c1:
                        if st.button("✅ כן", key=f"yes_del_lpc_{c['id']}"):
                            try:
                                log_action("DELETE", "lp_calls", f"נמחקה קריאת כסף למשקיעים: {c['call_date']}", c)
                                sb.table("lp_calls").delete().eq("id", c["id"]).execute()
                                st.session_state.pop(f"confirm_del_lpc_{c['id']}", None)
                                st.rerun()
                            except Exception as e:
                                st.error(f"שגיאה: {e}")
                    with d_c2:
                        if st.button("❌ ביטול", key=f"no_del_lpc_{c['id']}"):
                            st.session_state.pop(f"confirm_del_lpc_{c['id']}", None)
                            st.rerun()

                if st.session_state.get(f"editing_lpc_{c['id']}"):
                    with st.form(f"edit_lpc_form_{c['id']}"):
                        try:
                            def_date = datetime.fromisoformat(str(c['call_date'])).date()
                        except:
                            def_date = date.today()
                        edit_date = st.date_input("תאריך", value=def_date)
                        edit_pct = st.number_input("אחוז", value=float(c['call_pct']))
                        e_c1, e_c2 = st.columns(2)
                        with e_c1:
                            if st.form_submit_button("💾 שמור"):
                                try:
                                    log_action("UPDATE", "lp_calls", f"עודכנה קריאת כסף למשקיעים: {c['call_date']}", c)
                                    sb.table("lp_calls").update({"call_date": str(edit_date), "call_pct": edit_pct}).eq("id", c["id"]).execute()
                                    st.session_state.pop(f"editing_lpc_{c['id']}", None)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"שגיאה: {e}")
                        with e_c2:
                            if st.form_submit_button("❌ סגור"):
                                st.session_state.pop(f"editing_lpc_{c['id']}", None)
                                st.rerun()
                    st.divider()

def show_portfolio():
    st.title("📁 תיק השקעות")
    
    with st.expander("➕ הוסף קרן חדשה לתיק"):
        with st.form("add_new_fund_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("שם הקרן")
                new_manager = st.text_input("מנהל הקרן")
                strategy_opts = ["Growth", "VC", "Tech", "Niche", "Special Situations"]
                new_strategy = st.selectbox("אסטרטגיה", strategy_opts)
                new_geo = st.text_input("מיקוד גיאוגרפי")
            with col2:
                new_commitment = st.number_input("סכום התחייבות ($M / €M)", min_value=0.0)
                new_currency = st.selectbox("מטבע", ["USD", "EUR"])
                new_date = st.date_input("תאריך השקעה")
                status_opts = ["active", "closed", "exited"]
                new_status = st.selectbox("סטטוס", status_opts)
                
            if st.form_submit_button("💾 שמור קרן חדשה", type="primary"):
                try:
                    final_commit = new_commitment * 1_000_000 if new_commitment < 1000 else new_commitment
                    get_supabase().table("funds").insert({
                        "name": new_name,
                        "manager": new_manager,
                        "strategy": new_strategy,
                        "geographic_focus": new_geo,
                        "commitment": final_commit,
                        "currency": new_currency,
                        "vintage_year": new_date.year,
                        "investment_date": str(new_date),
                        "status": new_status
                    }).execute()
                    st.success("✅ קרן חדשה נוספה בהצלחה! היא מופיעה כעת בלשוניות למטה.")
                    st.rerun()
                except Exception as e:
                    st.error(f"שגיאה: {e}")

    funds = get_funds()
    if not funds:
        st.info("אין קרנות במערכת")
        return
    
    tabs = st.tabs([f["name"] for f in funds])
    for i, fund in enumerate(funds):
        with tabs[i]:
            show_fund_detail(fund)

def show_fund_detail(fund):
    calls = get_capital_calls(fund["id"])
    dists = get_distributions(fund["id"])
    reports = get_quarterly_reports(fund["id"])

    commitment = float(fund.get("commitment") or 0)
    display_commit = commitment * 1_000_000 if 0 < commitment < 1000 else commitment
    
    total_called = sum(c.get("amount") or 0 for c in calls if not c.get("is_future"))
    total_dist = sum(d.get("amount") or 0 for d in dists)
    uncalled = display_commit - total_called
    currency_sym = "€" if fund.get("currency") == "EUR" else "$"

    col1, col2, col3, col4, col_edit, col_del = st.columns([2,2,2,2,1,1])
    with col1:
        st.metric("התחייבות", format_currency(display_commit, currency_sym))
    with col2:
        pct = f"{total_called/display_commit*100:.1f}%" if display_commit > 0 else "—"
        st.metric("סה״כ נקרא", format_currency(total_called, currency_sym), pct)
    with col3:
        st.metric("יתרה לא נקראה", format_currency(uncalled, currency_sym))
    with col4:
        st.metric("סה״כ חולק", format_currency(total_dist, currency_sym))
    with col_edit:
        if st.button("✏️ עריכה", key=f"edit_fund_{fund['id']}"):
            st.session_state[f"editing_fund_{fund['id']}"] = True
    with col_del:
        if st.button("🗑️ מחיקה", key=f"del_fund_{fund['id']}"):
            st.session_state[f"confirm_del_fund_{fund['id']}"] = True

    if st.session_state.get(f"confirm_del_fund_{fund['id']}"):
        st.warning(f"⚠️ למחוק את '{fund['name']}'? יימחקו גם כל ה-Calls, Distributions ודוחות.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ כן, מחק הכל", key=f"yes_fund_{fund['id']}", type="primary"):
                try:
                    sb = get_supabase()
                    log_action("DELETE", "funds", f"מחיקת קרן '{fund['name']}' כולל כל הנתונים שלה", fund)
                    sb.table("capital_calls").delete().eq("fund_id", fund["id"]).execute()
                    sb.table("distributions").delete().eq("fund_id", fund["id"]).execute()
                    sb.table("quarterly_reports").delete().eq("fund_id", fund["id"]).execute()
                    sb.table("funds").delete().eq("id", fund["id"]).execute()
                    st.success("נמחק!")
                    st.session_state.pop(f"confirm_del_fund_{fund['id']}", None)
                    st.rerun()
                except Exception as e:
                    st.error(f"שגיאה: {e}")
        with c2:
            if st.button("❌ ביטול", key=f"no_fund_{fund['id']}"):
                st.session_state.pop(f"confirm_del_fund_{fund['id']}", None)
                st.rerun()

    if st.session_state.get(f"editing_fund_{fund['id']}"):
        with st.form(f"edit_fund_form_{fund['id']}"):
            st.markdown("**✏️ עריכת פרטי קרן**")
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("שם הקרן", value=fund.get("name",""))
                new_manager = st.text_input("מנהל", value=fund.get("manager","") or "")
                strategy_opts = ["Growth", "VC", "Tech", "Niche", "Special Situations"]
                cur_s = fund.get("strategy","Growth")
                new_strategy = st.selectbox("אסטרטגיה", strategy_opts,
                    index=strategy_opts.index(cur_s) if cur_s in strategy_opts else 0)
                new_geo = st.text_input("מיקוד גיאוגרפי", value=fund.get("geographic_focus","") or "")
            with col2:
                input_commit_val = display_commit / 1_000_000 if display_commit >= 1000 else display_commit
                new_commitment = st.number_input("התחייבות ($M / €M)", value=float(input_commit_val), min_value=0.0)
                
                cur_cur = fund.get("currency","USD")
                new_currency = st.selectbox("מטבע", ["USD","EUR"], index=0 if cur_cur=="USD" else 1)
                status_opts = ["active","closed","exited"]
                cur_st = fund.get("status","active")
                new_status = st.selectbox("סטטוס", status_opts,
                    index=status_opts.index(cur_st) if cur_st in status_opts else 0)
                
                cur_date = fund.get("investment_date")
                try:
                    default_date = datetime.fromisoformat(str(cur_date)).date() if cur_date else date(int(fund.get("vintage_year") or 2020), 1, 1)
                except:
                    default_date = date.today()
                new_inv_date = st.date_input("תאריך השקעה", value=default_date)

            c1, c2 = st.columns(2)
            with c1:
                if st.form_submit_button("💾 שמור", type="primary"):
                    try:
                        log_action("UPDATE", "funds", f"עדכון פרטי קרן השקעה: {fund['name']}", fund)
                        final_save_commit = new_commitment * 1_000_000 if new_commitment < 1000 else new_commitment
                        get_supabase().table("funds").update({
                            "name": new_name, "manager": new_manager,
                            "strategy": new_strategy, "commitment": final_save_commit,
                            "currency": new_currency, "status": new_status,
                            "vintage_year": new_inv_date.year,
                            "geographic_focus": new_geo,
                            "investment_date": str(new_inv_date)
                        }).eq("id", fund["id"]).execute()
                        st.success("✅ עודכן!")
                        st.session_state.pop(f"editing_fund_{fund['id']}", None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"שגיאה: {e}")
            with c2:
                if st.form_submit_button("❌ ביטול"):
                    st.session_state.pop(f"editing_fund_{fund['id']}", None)
                    st.rerun()

    st.divider()
    tab1, tab2, tab3 = st.tabs(["📞 Capital Calls", "💰 Distributions", "📊 ביצועים"])

    with tab1:
        if calls:
            st.markdown("**רשימת Calls**")
            for c in calls:
                with st.expander(f"Call #{c.get('call_number')} | {c.get('payment_date','')} | {format_currency(c.get('amount',0), currency_sym)} {'🔮' if c.get('is_future') else '✅'}", expanded=False):
                    col1, col2, col3 = st.columns([2,2,1])
                    with col1:
                        st.write(f"תאריך קבלה: {c.get('call_date','')}")
                        st.write(f"תאריך תשלום: {c.get('payment_date','')}")
                        st.write(f"סכום: {format_currency(c.get('amount',0), currency_sym)}")
                    with col2:
                        st.write(f"השקעות: {format_currency(c.get('investments',0), currency_sym)}" if c.get('investments') else "השקעות: —")
                        st.write(f"דמי ניהול: {format_currency(c.get('mgmt_fee',0), currency_sym)}" if c.get('mgmt_fee') else "דמי ניהול: —")
                        if c.get('notes'):
                            st.write(f"הערות: {c.get('notes')}")
                    with col3:
                        if st.button("🗑️", key=f"del_call_{c['id']}", help="מחק Call"):
                            st.session_state[f"confirm_del_call_{c['id']}"] = True
                    if st.session_state.get(f"confirm_del_call_{c['id']}"):
                        st.warning("למחוק Call זה?")
                        cc1, cc2 = st.columns(2)
                        with cc1:
                            if st.button("✅ מחק", key=f"yes_call_{c['id']}"):
                                try:
                                    log_action("DELETE", "capital_calls", f"מחיקת Capital Call #{c.get('call_number')} מהקרן {fund['name']}", c)
                                    get_supabase().table("capital_calls").delete().eq("id", c["id"]).execute()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"שגיאה: {e}")
                        with cc2:
                            if st.button("❌ ביטול", key=f"no_call_{c['id']}"):
                                st.session_state.pop(f"confirm_del_call_{c['id']}", None)
                                st.rerun()

            import plotly.express as px
            chart_data = [c for c in calls if not c.get("is_future") and c.get("amount")]
            if chart_data:
                fig = px.bar(
                    x=[f"Call #{c['call_number']}" for c in chart_data],
                    y=[c["amount"] for c in chart_data],
                    labels={"x": "קריאה", "y": f"סכום ({fund.get('currency','USD')})"},
                    title="היסטוריית Capital Calls",
                    color_discrete_sequence=["#0f3460"]
                )
                fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='white')
                st.plotly_chart(fig, use_container_width=True, key=f"calls_chart_{fund['id']}")
        else:
            st.info("אין Capital Calls עדיין")

        st.divider()
        st.markdown("**🤖 הוסף Capital Call מתוך PDF (זיהוי אוטומטי)**")
        uploaded_cc_pdf = st.file_uploader("העלה מסמך קריאה לכסף (PDF)", type=["pdf"], key=f"cc_uploader_{fund['id']}")
        
        if uploaded_cc_pdf:
            if st.button("נתח מסמך עכשיו", type="primary", key=f"cc_analyze_btn_{fund['id']}"):
                with st.spinner("Claude מנתח את המסמך ומחלץ נתונים..."):
                    try:
                        cc_bytes = uploaded_cc_pdf.read()
                        ai_result = analyze_capital_call_pdf_with_ai(cc_bytes)
                        st.session_state[f"cc_ai_result_{fund['id']}"] = ai_result
                        st.success("✅ הנתונים חולצו בהצלחה! אנא אשר אותם בטופס למטה.")
                    except Exception as e:
                        st.error(f"שגיאה בניתוח המסמך: {e}")
        
        st.divider()
        st.markdown("**➕ או הזן פרטים ידנית**")
        
        ai_data = st.session_state.get(f"cc_ai_result_{fund['id']}", {})
        
        def_call_date = date.today()
        if ai_data.get("call_date"):
            try: def_call_date = datetime.strptime(ai_data["call_date"], "%Y-%m-%d").date()
            except: pass
            
        def_pay_date = date.today()
        if ai_data.get("payment_date"):
            try: def_pay_date = datetime.strptime(ai_data["payment_date"], "%Y-%m-%d").date()
            except: pass

        with st.form(f"add_call_{fund['id']}"):
            col1, col2, col3 = st.columns(3)
            with col1:
                call_num = st.number_input("מספר קריאה", min_value=1, value=len(calls)+1)
                call_date = st.date_input("תאריך קבלה", value=def_call_date)
                payment_date = st.date_input("תאריך תשלום", value=def_pay_date)
            with col2:
                amount = st.number_input("סכום כולל", min_value=0.0, value=float(ai_data.get("amount", 0)))
                investments = st.number_input("השקעות (Capital Commitment)", min_value=0.0, value=float(ai_data.get("investments", 0)))
                mgmt_fee = st.number_input("דמי ניהול", min_value=0.0, value=float(ai_data.get("mgmt_fee", 0)))
            with col3:
                fund_expenses = st.number_input("הוצאות קרן", min_value=0.0, value=float(ai_data.get("fund_expenses", 0)))
                gp_contribution = st.number_input("GP Contribution", min_value=0.0)
                is_future = st.checkbox("קריאה עתידית")
                notes = st.text_input("הערות")
                
            if st.form_submit_button("שמור קריאה למערכת", type="primary"):
                try:
                    get_supabase().table("capital_calls").insert({
                        "fund_id": fund["id"], "call_number": call_num,
                        "call_date": str(call_date), "payment_date": str(payment_date),
                        "amount": amount, "investments": investments,
                        "mgmt_fee": mgmt_fee, "fund_expenses": fund_expenses,
                        "gp_contribution": gp_contribution, "is_future": is_future, "notes": notes
                    }).execute()
                    
                    st.session_state.pop(f"cc_ai_result_{fund['id']}", None)
                    st.success("✅ נשמר!")
                    st.rerun()
                except Exception as e:
                    st.error(f"שגיאה: {e}")

    with tab2:
        if dists:
            st.markdown("**רשימת Distributions**")
            for d in dists:
                with st.expander(f"Dist #{d.get('dist_number')} | {d.get('dist_date','')} | {format_currency(d.get('amount',0), currency_sym)}", expanded=False):
                    col1, col2 = st.columns([4,1])
                    with col1:
                        st.write(f"סוג: {d.get('dist_type','')} | סכום: {format_currency(d.get('amount',0), currency_sym)}")
                    with col2:
                        if st.button("🗑️", key=f"del_dist_{d['id']}", help="מחק Distribution"):
                            st.session_state[f"confirm_del_dist_{d['id']}"] = True
                    if st.session_state.get(f"confirm_del_dist_{d['id']}"):
                        st.warning("למחוק Distribution זה?")
                        dc1, dc2 = st.columns(2)
                        with dc1:
                            if st.button("✅ מחק", key=f"yes_dist_{d['id']}"):
                                try:
                                    log_action("DELETE", "distributions", f"מחיקת חלוקה #{d.get('dist_number')} מהקרן {fund['name']}", d)
                                    get_supabase().table("distributions").delete().eq("id", d["id"]).execute()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"שגיאה: {e}")
                        with dc2:
                            if st.button("❌ ביטול", key=f"no_dist_{d['id']}"):
                                st.session_state.pop(f"confirm_del_dist_{d['id']}", None)
                                st.rerun()
        else:
            st.info("אין חלוקות עדיין")

        st.divider()
        st.markdown("**➕ הוסף Distribution**")
        with st.form(f"add_dist_{fund['id']}"):
            col1, col2 = st.columns(2)
            with col1:
                dist_num = st.number_input("מספר", min_value=1, value=len(dists)+1)
                dist_date = st.date_input("תאריך")
            with col2:
                dist_amount = st.number_input("סכום", min_value=0.0)
                dist_type = st.selectbox("סוג", ["income", "capital", "recycle"])
            if st.form_submit_button("שמור", type="primary"):
                try:
                    get_supabase().table("distributions").insert({
                        "fund_id": fund["id"], "dist_number": dist_num,
                        "dist_date": str(dist_date), "amount": dist_amount, "dist_type": dist_type
                    }).execute()
                    st.success("✅ נשמר!")
                    st.rerun()
                except Exception as e:
                    st.error(f"שגיאה: {e}")

    with tab3:
        if reports:
            st.markdown("**דוחות רבעוניים**")
            for r in reports:
                with st.expander(f"Q{r['quarter']}/{r['year']} | TVPI: {r.get('tvpi','—')} | IRR: {r.get('irr','—')}%", expanded=False):
                    col1, col2 = st.columns([4,1])
                    with col1:
                        st.write(f"NAV: {format_currency(r.get('nav',0), currency_sym)} | DPI: {r.get('dpi','—')} | RVPI: {r.get('rvpi','—')}")
                        if r.get('notes'):
                            st.write(f"הערות: {r.get('notes')}")
                    with col2:
                        if st.button("🗑️", key=f"del_rep_{r['id']}", help="מחק דוח"):
                            st.session_state[f"confirm_del_rep_{r['id']}"] = True
                    if st.session_state.get(f"confirm_del_rep_{r['id']}"):
                        st.warning("למחוק דוח זה?")
                        rc1, rc2 = st.columns(2)
                        with rc1:
                            if st.button("✅ מחק", key=f"yes_rep_{r['id']}"):
                                try:
                                    log_action("DELETE", "quarterly_reports", f"מחיקת דוח Q{r['quarter']}/{r['year']} של קרן {fund['name']}", r)
                                    get_supabase().table("quarterly_reports").delete().eq("id", r["id"]).execute()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"שגיאה: {e}")
                        with rc2:
                            if st.button("❌ ביטול", key=f"no_rep_{r['id']}"):
                                st.session_state.pop(f"confirm_del_rep_{r['id']}", None)
                                st.rerun()

            import plotly.graph_objects as go
            if len(reports) > 1:
                labels = [f"Q{r['quarter']}/{r['year']}" for r in reports]
                fig = go.Figure()
                if any(r.get("tvpi") for r in reports):
                    fig.add_trace(go.Scatter(x=labels, y=[r.get("tvpi") for r in reports], name="TVPI", line=dict(color="#4ade80")))
                if any(r.get("dpi") for r in reports):
                    fig.add_trace(go.Scatter(x=labels, y=[r.get("dpi") for r in reports], name="DPI", line=dict(color="#60a5fa")))
                fig.update_layout(title="ביצועים לאורך זמן", paper_bgcolor='rgba(0,0,0,0)',
                                  plot_bgcolor='rgba(0,0,0,0)', font_color='white')
                st.plotly_chart(fig, use_container_width=True, key=f"perf_chart_{fund['id']}")
        else:
            st.info("אין דוחות רבעוניים לקרן זו עדיין.")

        st.divider()
        st.markdown("**🤖 הוסף דוח רבעוני מתוך קובץ (זיהוי אוטומטי)**")
        uploaded_rep_file = st.file_uploader("העלה דוח רבעוני (PDF / Excel / CSV)", type=["pdf", "xlsx", "xls", "csv"], key=f"rep_uploader_{fund['id']}")
        
        if uploaded_rep_file:
            if st.button("נתח מסמך עכשיו", type="primary", key=f"rep_analyze_btn_{fund['id']}"):
                with st.spinner("Claude מנתח את הדוח..."):
                    try:
                        file_bytes = uploaded_rep_file.read()
                        file_name = uploaded_rep_file.name
                        if file_name.lower().endswith('.pdf'):
                            rep_text = extract_pdf_text(file_bytes)
                        else:
                            if file_name.lower().endswith('.csv'):
                                df = pd.read_csv(io.BytesIO(file_bytes))
                            else:
                                df = pd.read_excel(io.BytesIO(file_bytes))
                            rep_text = df.to_string(index=False)
                            if len(rep_text) > 12000:
                                rep_text = rep_text[:4000] + "\n[...]\n" + rep_text[-8000:]
                        
                        ai_result = analyze_quarterly_report_with_ai(rep_text)
                        st.session_state[f"rep_ai_result_{fund['id']}"] = ai_result
                        st.success("✅ הנתונים חולצו בהצלחה! אנא אשר אותם בטופס למטה.")
                    except Exception as e:
                        st.error(f"שגיאה בניתוח המסמך: {e}. (במידה ומדובר באקסל, ודא ש-openpyxl מותקן ב-requirements.txt)")

        st.divider()
        st.markdown("**➕ או הזן פרטים ידנית**")
        
        ai_rep = st.session_state.get(f"rep_ai_result_{fund['id']}", {})
        
        def_year = int(ai_rep.get("year")) if ai_rep.get("year") else 2025
        def_quarter = int(ai_rep.get("quarter")) if ai_rep.get("quarter") in [1,2,3,4] else 1
        
        def_rep_date = date.today()
        if ai_rep.get("report_date"):
            try: def_rep_date = datetime.strptime(ai_rep["report_date"], "%Y-%m-%d").date()
            except: pass

        with st.form(f"add_report_{fund['id']}"):
            col1, col2, col3 = st.columns(3)
            with col1:
                year = st.number_input("שנה", value=def_year, min_value=2020, max_value=2030)
                quarter = st.selectbox("רבעון", [1, 2, 3, 4], index=[1,2,3,4].index(def_quarter))
                report_date = st.date_input("תאריך דוח", value=def_rep_date)
            with col2:
                nav = st.number_input("NAV", min_value=0.0, value=float(ai_rep.get("nav") or 0.0))
                tvpi = st.number_input("TVPI", min_value=0.0, step=0.01, format="%.2f", value=float(ai_rep.get("tvpi") or 0.0))
                dpi = st.number_input("DPI", min_value=0.0, step=0.01, format="%.2f", value=float(ai_rep.get("dpi") or 0.0))
            with col3:
                rvpi = st.number_input("RVPI", min_value=0.0, step=0.01, format="%.2f", value=float(ai_rep.get("rvpi") or 0.0))
                irr = st.number_input("IRR %", step=0.1, format="%.1f", value=float(ai_rep.get("irr") or 0.0))
                notes = st.text_area("הערות")
            if st.form_submit_button("שמור דוח", type="primary"):
                try:
                    get_supabase().table("quarterly_reports").upsert({
                        "fund_id": fund["id"], "year": year, "quarter": quarter,
                        "report_date": str(report_date), "nav": nav,
                        "tvpi": tvpi, "dpi": dpi, "rvpi": rvpi, "irr": irr, "notes": notes
                    }).execute()
                    st.session_state.pop(f"rep_ai_result_{fund['id']}", None)
                    st.success("✅ דוח נשמר!")
                    st.rerun()
                except Exception as e:
                    st.error(f"שגיאה: {e}")

def show_pipeline():
    st.title("🔍 קרנות Pipeline")
    pipeline = get_pipeline_funds()

    col1, col2, col3 = st.columns([2, 1, 1])
    with col2:
        if st.button("➕ הוסף ידנית", use_container_width=True):
            st.session_state.show_add_pipeline = True
            st.session_state.show_pdf_upload = False
    with col3:
        if st.button("📄 העלה PDF", type="primary", use_container_width=True):
            st.session_state.show_pdf_upload = True
            st.session_state.show_add_pipeline = False

    if st.session_state.get("show_pdf_upload"):
        st.divider()
        st.markdown("### 📄 ניתוח PDF אוטומטי")
        uploaded_pdf = st.file_uploader("העלה מצגת קרן (PDF)", type=["pdf"], key="pdf_uploader")
        if uploaded_pdf:
            if st.button("🤖 נתח עם AI", type="primary"):
                with st.spinner("Claude מנתח את המצגת... (30-60 שניות)"):
                    try:
                        pdf_bytes = uploaded_pdf.read()
                        result = analyze_pdf_with_ai(pdf_bytes)
                        st.session_state.pdf_result = result
                        st.success("✅ ניתוח הושלם!")
                    except Exception as e:
                        st.error(f"שגיאה: {e}")
        if st.session_state.get("pdf_result"):
            r = st.session_state.pdf_result
            st.divider()
            st.markdown("### 📋 פרטים שנמצאו – אשר ועדכן")
            if r.get("key_highlights"):
                st.info(f"💡 {r.get('key_highlights')}")
            with st.form("pdf_pipeline_form"):
                col1, col2 = st.columns(2)
                with col1:
                    fund_name = st.text_input("שם הקרן", value=r.get("fund_name") or "")
                    manager = st.text_input("מנהל", value=r.get("manager") or "")
                    strategy_options = ["Growth", "VC", "Tech", "Niche", "Special Situations"]
                    ai_strategy = r.get("strategy", "Growth")
                    strategy_idx = strategy_options.index(ai_strategy) if ai_strategy in strategy_options else 0
                    strategy = st.selectbox("אסטרטגיה", strategy_options, index=strategy_idx)
                    geographic = st.text_input("מיקוד גיאוגרפי", value=r.get("geographic_focus") or "")
                    sector = st.text_input("מיקוד סקטור", value=r.get("sector_focus") or "")
                with col2:
                    fund_size = r.get("fund_size_target") or 0
                    target_commitment = st.number_input("יעד השקעה שלנו ($M)", min_value=0.0, value=0.0, step=0.5)
                    currency = st.selectbox("מטבע", ["USD", "EUR"], index=0 if r.get("currency") == "USD" else 1)
                    target_close = st.date_input("תאריך סגירה משוער")
                    priority = st.selectbox("עדיפות", ["high", "medium", "low"])
                st.divider()
                st.markdown("**📊 נתוני הקרן (לתיעוד)**")
                col3, col4, col5 = st.columns(3)
                with col3:
                    st.metric("גודל יעד", f"${fund_size:,.0f}M" if fund_size else "—")
                    hard_cap = r.get("fund_size_hard_cap")
                    st.metric("Hard Cap", f"${hard_cap:,.0f}M" if hard_cap else "—")
                with col4:
                    moic_low = r.get("target_return_moic_low")
                    moic_high = r.get("target_return_moic_high")
                    st.metric("MOIC יעד", f"{moic_low}x-{moic_high}x" if moic_low and moic_high else "—")
                    irr = r.get("target_irr_gross")
                    st.metric("IRR גלמי יעד", f"{irr}%" if irr else "—")
                with col5:
                    mgmt = r.get("mgmt_fee_pct")
                    carry = r.get("carried_interest_pct")
                    hurdle = r.get("preferred_return_pct")
                    st.metric("דמי ניהול", f"{mgmt}%" if mgmt else "—")
                    st.metric("Carry / Hurdle", f"{carry}% / {hurdle}%" if carry and hurdle else "—")
                
                aum_str = f" | מנהל AUM: ${r.get('aum_manager')}B" if r.get("aum_manager") else ""
                irr_str = f" | IRR: {r.get('target_irr_gross')}%" if r.get("target_irr_gross") else ""
                moic_str = f" | MOIC: {r.get('target_return_moic_low')}x-{r.get('target_return_moic_high')}x" if r.get("target_return_moic_low") else ""
                notes_default = f"גודל קרן: ${fund_size:,.0f}M{moic_str}{irr_str}{aum_str}" if fund_size else ""
                notes = st.text_area("הערות", value=notes_default)
                
                if st.form_submit_button("✅ צור קרן Pipeline + גאנט", type="primary"):
                    try:
                        sb = get_supabase()
                        res = sb.table("pipeline_funds").insert({
                            "name": fund_name, "manager": manager, "strategy": strategy,
                            "target_commitment": target_commitment * 1_000_000,
                            "currency": currency, "target_close_date": str(target_close),
                            "priority": priority, "notes": notes
                        }).execute()
                        fund_id = res.data[0]["id"]
                        try:
                            sb.rpc("create_default_gantt_tasks", {"p_fund_id": fund_id}).execute()
                        except:
                            pass
                        st.success(f"✅ קרן '{fund_name}' נוצרה!")
                        st.session_state.pdf_result = None
                        st.session_state.show_pdf_upload = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"שגיאה: {e}")

    if st.session_state.get("show_add_pipeline"):
        st.divider()
        with st.form("add_pipeline_manual"):
            st.markdown("### ➕ הוספה ידנית")
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("שם הקרן")
                manager = st.text_input("מנהל")
                strategy = st.selectbox("אסטרטגיה", ["Growth", "VC", "Tech", "Niche", "Special Situations"])
            with col2:
                target_commitment_input = st.number_input("יעד השקעה ($M)", min_value=0.0)
                currency = st.selectbox("מטבע", ["USD", "EUR"])
                target_close = st.date_input("תאריך סגירה")
                priority = st.selectbox("עדיפות", ["high", "medium", "low"])
            notes = st.text_area("הערות")
            if st.form_submit_button("צור קרן + גאנט", type="primary"):
                try:
                    sb = get_supabase()
                    target_commitment_db = target_commitment_input * 1_000_000
                    res = sb.table("pipeline_funds").insert({
                        "name": name, "manager": manager, "strategy": strategy,
                        "target_commitment": target_commitment_db, "currency": currency,
                        "target_close_date": str(target_close), "priority": priority, "notes": notes
                    }).execute()
                    fund_id = res.data[0]["id"]
                    try:
                        sb.rpc("create_default_gantt_tasks", {"p_fund_id": fund_id}).execute()
                    except:
                        pass
                    st.success(f"✅ קרן '{name}' נוצרה!")
                    st.session_state.show_add_pipeline = False
                    st.rerun()
                except Exception as e:
                    st.error(f"שגיאה: {e}")

    st.divider()

    if not pipeline:
        st.info("אין קרנות pipeline. לחץ 'העלה PDF' או 'הוסף ידנית'.")
        return

    for fund in pipeline:
        fid = fund["id"]
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(fund.get("priority",""), "⚪")
        with st.expander(f"{priority_emoji} {fund['name']} | {fund.get('strategy','')} | סגירה: {fund.get('target_close_date','')}", expanded=False):
            col_a, col_b, col_c = st.columns([1, 1, 4])
            with col_a:
                if st.button("✏️ עריכה", key=f"edit_btn_{fid}"):
                    st.session_state[f"editing_{fid}"] = True
            with col_b:
                if st.button("🗑️ מחיקה", key=f"del_btn_{fid}"):
                    st.session_state[f"confirm_delete_{fid}"] = True

            if st.session_state.get(f"confirm_delete_{fid}"):
                st.warning(f"⚠️ למחוק את '{fund['name']}'? פעולה זו תמחק גם את כל משימות הגאנט.")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("✅ כן, מחק", key=f"yes_btn_{fid}", type="primary"):
                        try:
                            sb = get_supabase()
                            log_action("DELETE", "pipeline_funds", f"מחיקת קרן פייפליין: {fund['name']}", fund)
                            sb.table("gantt_tasks").delete().eq("pipeline_fund_id", fid).execute()
                            sb.table("pipeline_funds").delete().eq("id", fid).execute()
                            st.success("נמחק!")
                            st.session_state.pop(f"confirm_delete_{fid}", None)
                            st.rerun()
                        except Exception as e:
                            st.error(f"שגיאה: {e}")
                with col_no:
                    if st.button("❌ ביטול", key=f"no_btn_{fid}"):
                        st.session_state.pop(f"confirm_delete_{fid}", None)
                        st.rerun()

            if st.session_state.get(f"editing_{fid}"):
                with st.form(f"edit_form_{fid}"):
                    st.markdown("**✏️ עריכת פרטי קרן**")
                    col1, col2 = st.columns(2)
                    with col1:
                        new_name = st.text_input("שם הקרן", value=fund.get("name",""))
                        new_manager = st.text_input("מנהל", value=fund.get("manager",""))
                        strategy_opts = ["Growth", "VC", "Tech", "Niche", "Special Situations"]
                        cur_strat = fund.get("strategy","Growth")
                        new_strategy = st.selectbox("אסטרטגיה", strategy_opts,
                            index=strategy_opts.index(cur_strat) if cur_strat in strategy_opts else 0)
                        new_geo = st.text_input("מיקוד גיאוגרפי", value=fund.get("geographic_focus","") or "")
                    with col2:
                        cur_commit = float(fund.get("target_commitment") or 0)
                        input_commit_val = cur_commit / 1_000_000 if cur_commit >= 1000 else cur_commit
                        new_commitment_input = st.number_input("יעד השקעה ($M)", value=float(input_commit_val), step=0.5)
                        
                        cur_currency = fund.get("currency","USD")
                        new_currency = st.selectbox("מטבע", ["USD","EUR"], index=0 if cur_currency=="USD" else 1)
                        priority_opts = ["high","medium","low"]
                        cur_priority = fund.get("priority","medium")
                        new_priority = st.selectbox("עדיפות", priority_opts,
                            index=priority_opts.index(cur_priority) if cur_priority in priority_opts else 1)
                        
                        cur_date = fund.get("target_close_date")
                        try:
                            default_date = datetime.fromisoformat(str(cur_date)).date() if cur_date else date.today()
                        except:
                            default_date = date.today()
                        new_close = st.date_input("תאריך סגירה", value=default_date)
                    new_notes = st.text_area("הערות", value=fund.get("notes","") or "")
                    col_save, col_cancel = st.columns(2)
                    with col_save:
                        if st.form_submit_button("💾 שמור שינויים", type="primary"):
                            try:
                                log_action("UPDATE", "pipeline_funds", f"עדכון פרטי קרן פייפליין: {fund['name']}", fund)
                                new_commitment_db = new_commitment_input * 1_000_000
                                get_supabase().table("pipeline_funds").update({
                                    "name": new_name, "manager": new_manager,
                                    "strategy": new_strategy, "target_commitment": new_commitment_db,
                                    "currency": new_currency, "priority": new_priority,
                                    "target_close_date": str(new_close), "notes": new_notes
                                }).eq("id", fid).execute()
                                st.success("✅ עודכן!")
                                st.session_state.pop(f"editing_{fid}", None)
                                st.rerun()
                            except Exception as e:
                                st.error(f"שגיאה: {e}")
                    with col_cancel:
                        if st.form_submit_button("❌ ביטול"):
                            st.session_state.pop(f"editing_{fid}", None)
                            st.rerun()
            else:
                col1, col2, col3 = st.columns(3)
                currency_sym = "€" if fund.get("currency") == "EUR" else "$"
                with col1:
                    commitment = float(fund.get("target_commitment") or 0)
                    display_commit = commitment * 1_000_000 if 0 < commitment < 1000 else commitment
                    st.metric("יעד השקעה", format_currency(display_commit, currency_sym))
                with col2:
                    st.metric("תאריך סגירה", str(fund.get("target_close_date", "")))
                with col3:
                    st.metric("עדיפות", fund.get("priority", "").upper())
                
                notes_text = fund.get("notes") or ""
                notes_text = notes_text.replace("NoneB", "").replace("None", "").replace("x-x", "") 
                if notes_text.strip():
                    st.caption(f"📝 {notes_text}")
                
                tasks = get_gantt_tasks(fund["id"])
                if tasks is not None:
                    show_gantt(tasks, fund)

def show_gantt(tasks, fund):
    import plotly.graph_objects as go
    from datetime import timedelta

    CAT_CONFIG = {
        "Analysis": {"icon": "🟢", "color": "#16a34a", "bg": "#052e16"},
        "Legal":    {"icon": "🔵", "color": "#2563eb", "bg": "#0c1a4b"},
        "Tax":      {"icon": "🔴", "color": "#dc2626", "bg": "#3b0a0a"},
        "Admin":    {"icon": "🟡", "color": "#ca8a04", "bg": "#2d2000"},
        "IC":       {"icon": "🟣", "color": "#9333ea", "bg": "#2d0a4b"},
        "DD":       {"icon": "🟠", "color": "#ea580c", "bg": "#3b1a00"},
    }
    STATUS_CONFIG = {
        "todo":        {"icon": "⬜", "label": "ממתין",  "color": "#64748b"},
        "in_progress": {"icon": "🔄", "label": "בביצוע", "color": "#3b82f6"},
        "done":        {"icon": "✅", "label": "הושלם",  "color": "#22c55e"},
        "blocked":     {"icon": "🚫", "label": "חסום",   "color": "#ef4444"},
    }
    STATUS_LIST = ["todo", "in_progress", "done", "blocked"]

    sb = get_supabase()
    fid = fund["id"]

    total = len(tasks)
    done_n = sum(1 for t in tasks if t.get("status") == "done")
    in_prog = sum(1 for t in tasks if t.get("status") == "in_progress")
    blocked_n = sum(1 for t in tasks if t.get("status") == "blocked")
    pct = int(done_n / total * 100) if total else 0

    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);border-radius:12px;padding:16px 20px;margin:12px 0;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <span style="color:#94a3b8;font-size:13px;">התקדמות כללית</span>
            <span style="color:#4ade80;font-weight:700;font-size:18px;">{pct}%</span>
        </div>
        <div style="background:#0f172a;border-radius:6px;height:8px;overflow:hidden;">
            <div style="background:linear-gradient(90deg,#16a34a,#4ade80);width:{pct}%;height:100%;border-radius:6px;transition:width 0.5s;"></div>
        </div>
        <div style="display:flex;gap:20px;margin-top:12px;">
            <span style="color:#4ade80;font-size:12px;">✅ הושלם: {done_n}</span>
            <span style="color:#3b82f6;font-size:12px;">🔄 בביצוע: {in_prog}</span>
            <span style="color:#ef4444;font-size:12px;">🚫 חסום: {blocked_n}</span>
            <span style="color:#64748b;font-size:12px;">⬜ ממתין: {total - done_n - in_prog - blocked_n}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_hdr1, col_hdr2 = st.columns([3, 1])
    with col_hdr1:
        st.markdown("##### 📊 תצוגת גאנט")
    with col_hdr2:
        show_done = st.toggle("הצג משימות שהושלמו", value=True, key=f"show_done_toggle_{fid}")

    visible_tasks = tasks if show_done else [t for t in tasks if t.get("status") != "done"]

    gantt_tasks_data = []
    today_dt = date.today()
    for t in visible_tasks:
        if t.get("start_date") and t.get("due_date"):
            cat = t.get("category", "Admin")
            cfg = CAT_CONFIG.get(cat, CAT_CONFIG["Admin"])
            status = t.get("status", "todo")
            
            if status == "done":
                bar_color = "#22c55e" 
                icon = "✅"
                task_display = f"<s>{t['task_name']}</s>"
            elif status == "blocked":
                bar_color = "#ef4444" 
                icon = cfg['icon']
                task_display = t['task_name']
            elif status == "in_progress":
                bar_color = "#3b82f6" 
                icon = cfg['icon']
                task_display = t['task_name']
            else:
                bar_color = "#475569" 
                icon = cfg['icon']
                task_display = t['task_name']

            gantt_tasks_data.append({
                "Task": f"{icon} {task_display}",
                "RawName": t["task_name"],
                "Start": t["start_date"],
                "Finish": t["due_date"],
                "Color": bar_color,
                "Category": cat,
                "Status": STATUS_CONFIG.get(status, {}).get("label", status),
            })

    if gantt_tasks_data:
        fig = go.Figure()
        sorted_tasks = sorted(gantt_tasks_data, key=lambda x: x["Start"], reverse=True)

        for i, t in enumerate(sorted_tasks):
            start_dt_val = datetime.fromisoformat(t["Start"])
            finish_dt_val = datetime.fromisoformat(t["Finish"]) + timedelta(days=1)
            duration_ms = (finish_dt_val - start_dt_val).total_seconds() * 1000

            fig.add_trace(go.Bar(
                x=[duration_ms],
                y=[t["Task"]],
                base=[t["Start"]],
                orientation="h",
                marker=dict(color=t["Color"], opacity=0.95, line=dict(width=1, color="#0f172a")),
                text=[f" {t['Status']}"],
                textposition="inside",
                insidetextanchor="middle",
                textfont=dict(color="white", size=13, family="Heebo"),
                hovertemplate=f"<b>{t['RawName']}</b><br>{t['Start']} → {t['Finish']}<br>סטטוס: {t['Status']}<extra></extra>",
                showlegend=False,
            ))
            
        fig.add_shape(
            type="line",
            x0=str(today_dt), x1=str(today_dt),
            y0=0, y1=1, yref="paper",
            line=dict(color="#f59e0b", width=2, dash="dash"),
        )
        fig.add_annotation(
            x=str(today_dt), y=1, yref="paper",
            text="היום", showarrow=False,
            font=dict(color="#f59e0b", size=13, family="Heebo"),
            yanchor="bottom"
        )
        
        fig.update_layout(
            height=max(350, len(sorted_tasks) * 45 + 100),
            barmode="overlay",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#0f172a",
            font=dict(color="#e2e8f0", size=14, family="Heebo"),
            margin=dict(l=10, r=20, t=40, b=40),
            xaxis=dict(type="date", gridcolor="#1e293b", tickformat="%d/%m/%y", tickfont=dict(size=13)),
            yaxis=dict(gridcolor="#1e293b", tickfont=dict(size=14), automargin=True),
        )
        st.plotly_chart(fig, use_container_width=True, key=f"gantt_chart_{fid}")
    else:
        st.info("אין משימות להצגה בגרף זה כרגע.")

    st.markdown("##### 📋 עריכת משימות")
    
    cats_order = ["Analysis", "IC", "DD", "Legal", "Tax", "Admin"]
    for cat in cats_order:
        cat_tasks = [t for t in visible_tasks if t.get("category","") == cat]
        if not cat_tasks:
            continue

        cfg = CAT_CONFIG.get(cat, CAT_CONFIG["Admin"])
        all_cat_tasks = [t for t in tasks if t.get("category","") == cat]
        done_c = sum(1 for t in all_cat_tasks if t.get("status") == "done")
        cat_pct = int(done_c / len(all_cat_tasks) * 100)

        st.markdown(f"""
        <div style="background:{cfg['bg']};border-left:3px solid {cfg['color']};
                    border-radius:8px;padding:10px 14px;margin:8px 0 4px 0;
                    display:flex;justify-content:space-between;align-items:center;">
            <span style="color:{cfg['color']};font-weight:600;">{cfg['icon']} {cat}</span>
            <span style="color:#94a3b8;font-size:12px;">{done_c}/{len(all_cat_tasks)} · {cat_pct}%</span>
        </div>
        """, unsafe_allow_html=True)

        for t in cat_tasks:
            status = t.get("status", "todo")
            scfg = STATUS_CONFIG.get(status, STATUS_CONFIG["todo"])
            
            try:
                current_start = datetime.fromisoformat(t["start_date"]).date() if t.get("start_date") else date.today()
                current_due = datetime.fromisoformat(t["due_date"]).date() if t.get("due_date") else date.today()
            except:
                current_start, current_due = date.today(), date.today()

            col_icon, col_name, col_start, col_due, col_status, col_del = st.columns([0.5, 3, 2, 2, 2, 0.5])
            with col_icon:
                st.markdown(f"<div style='margin-top:5px; font-size:18px;'>{scfg['icon']}</div>", unsafe_allow_html=True)
            with col_name:
                new_name = st.text_input("שם משימה", value=t["task_name"], key=f"name_{fid}_{t['id']}", label_visibility="collapsed")
            with col_start:
                new_start = st.date_input("התחלה", value=current_start, key=f"start_{fid}_{t['id']}", label_visibility="collapsed")
            with col_due:
                new_due = st.date_input("סיום", value=current_due, key=f"due_{fid}_{t['id']}", label_visibility="collapsed")
            with col_status:
                new_status = st.selectbox(
                    "סטטוס",
                    STATUS_LIST,
                    index=STATUS_LIST.index(status) if status in STATUS_LIST else 0,
                    key=f"status_{fid}_{t['id']}",
                    label_visibility="collapsed"
                )
            with col_del:
                if st.button("🗑️", key=f"del_{fid}_{t['id']}", help="מחק משימה"):
                    try:
                        log_action("DELETE", "gantt_tasks", f"מחיקת משימת גאנט: {t['task_name']}", t)
                        sb.table("gantt_tasks").delete().eq("id", t["id"]).execute()
                        st.rerun()
                    except Exception as e:
                        st.error(f"שגיאה במחיקה: {e}")
                
            if new_status != status or str(new_start) != t.get("start_date") or str(new_due) != t.get("due_date") or new_name != t["task_name"]:
                try:
                    sb.table("gantt_tasks").update({
                        "task_name": new_name,
                        "status": new_status,
                        "start_date": str(new_start),
                        "due_date": str(new_due)
                    }).eq("id", t["id"]).execute()
                    st.rerun()
                except Exception as e:
                    st.error(f"שגיאה בעדכון משימה: {e}")

    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("➕ הוספת משימה חדשה לגאנט"):
        with st.form(f"add_new_task_{fid}"):
            c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
            with c1:
                new_t_name = st.text_input("שם המשימה")
            with c2:
                new_t_cat = st.selectbox("קטגוריה", ["Analysis", "IC", "DD", "Legal", "Tax", "Admin"])
            with c3:
                new_t_start = st.date_input("תאריך התחלה", value=date.today())
            with c4:
                new_t_due = st.date_input("תאריך סיום", value=date.today())
            
            if st.form_submit_button("שמור משימה", type="primary"):
                if new_t_name:
                    try:
                        sb.table("gantt_tasks").insert({
                            "pipeline_fund_id": fid,
                            "task_name": new_t_name,
                            "category": new_t_cat,
                            "start_date": str(new_t_start),
                            "due_date": str(new_t_due),
                            "status": "todo"
                        }).execute()
                        st.success("משימה נוספה בהצלחה!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"שגיאה: {e}")
                else:
                    st.error("יש להזין שם משימה")


def show_reports():
    st.title("📈 דוחות רבעוניים")
    funds = get_funds()
    if not funds:
        st.info("אין קרנות במערכת")
        return

    fund_options = {f["name"]: f["id"] for f in funds}
    selected_fund_name = st.selectbox("בחר קרן", list(fund_options.keys()))
    fund_id = fund_options[selected_fund_name]
    reports = get_quarterly_reports(fund_id)

    if reports:
        st.subheader(f"דוחות – {selected_fund_name}")
        rows = [{"שנה": r["year"], "רבעון": f"Q{r['quarter']}", "NAV": r.get("nav"),
                 "TVPI": r.get("tvpi"), "DPI": r.get("dpi"), "RVPI": r.get("rvpi"),
                 "IRR %": r.get("irr"), "הערות": r.get("notes","")} for r in reports]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("אין דוחות רבעוניים לקרן זו עדיין.")

    st.divider()
    st.markdown("**🤖 הוסף דוח רבעוני מתוך קובץ (זיהוי אוטומטי)**")
    uploaded_rep_file = st.file_uploader("העלה דוח רבעוני (PDF / Excel / CSV)", type=["pdf", "xlsx", "xls", "csv"], key="global_rep_uploader")
    
    if uploaded_rep_file:
        if st.button("נתח מסמך עכשיו", type="primary", key="global_rep_analyze_btn"):
            with st.spinner("Claude מנתח את הדוח..."):
                try:
                    file_bytes = uploaded_rep_file.read()
                    file_name = uploaded_rep_file.name
                    if file_name.lower().endswith('.pdf'):
                        rep_text = extract_pdf_text(file_bytes)
                    else:
                        if file_name.lower().endswith('.csv'):
                            df = pd.read_csv(io.BytesIO(file_bytes))
                        else:
                            df = pd.read_excel(io.BytesIO(file_bytes))
                        rep_text = df.to_string(index=False)
                        if len(rep_text) > 12000:
                            rep_text = rep_text[:4000] + "\n[...]\n" + rep_text[-8000:]
                    
                    ai_result = analyze_quarterly_report_with_ai(rep_text)
                    st.session_state["global_rep_ai_result"] = ai_result
                    st.success("✅ הנתונים חולצו בהצלחה! אנא אשר אותם בטופס למטה.")
                except Exception as e:
                    st.error(f"שגיאה בניתוח המסמך: {e}. (במידה ומדובר באקסל, ודא ש-openpyxl מותקן ב-requirements.txt)")

    st.divider()
    st.markdown("**➕ או הזן פרטים ידנית**")
    
    ai_rep = st.session_state.get("global_rep_ai_result", {})
    
    def_year = int(ai_rep.get("year")) if ai_rep.get("year") else 2025
    def_quarter = int(ai_rep.get("quarter")) if ai_rep.get("quarter") in [1,2,3,4] else 1
    
    def_rep_date = date.today()
    if ai_rep.get("report_date"):
        try: def_rep_date = datetime.strptime(ai_rep["report_date"], "%Y-%m-%d").date()
        except: pass

    with st.form("add_report"):
        col1, col2, col3 = st.columns(3)
        with col1:
            year = st.number_input("שנה", value=def_year, min_value=2020, max_value=2030)
            quarter = st.selectbox("רבעון", [1, 2, 3, 4], index=[1,2,3,4].index(def_quarter))
            report_date = st.date_input("תאריך דוח", value=def_rep_date)
        with col2:
            nav = st.number_input("NAV", min_value=0.0, value=float(ai_rep.get("nav") or 0.0))
            tvpi = st.number_input("TVPI", min_value=0.0, step=0.01, format="%.2f", value=float(ai_rep.get("tvpi") or 0.0))
            dpi = st.number_input("DPI", min_value=0.0, step=0.01, format="%.2f", value=float(ai_rep.get("dpi") or 0.0))
        with col3:
            rvpi = st.number_input("RVPI", min_value=0.0, step=0.01, format="%.2f", value=float(ai_rep.get("rvpi") or 0.0))
            irr = st.number_input("IRR %", step=0.1, format="%.1f", value=float(ai_rep.get("irr") or 0.0))
            notes = st.text_area("הערות")
        if st.form_submit_button("שמור דוח", type="primary"):
            try:
                get_supabase().table("quarterly_reports").upsert({
                    "fund_id": fund_id, "year": year, "quarter": quarter,
                    "report_date": str(report_date), "nav": nav,
                    "tvpi": tvpi, "dpi": dpi, "rvpi": rvpi, "irr": irr, "notes": notes
                }).execute()
                st.session_state.pop("global_rep_ai_result", None)
                st.success("✅ דוח נשמר!")
                st.rerun()
            except Exception as e:
                st.error(f"שגיאה: {e}")

if __name__ == "__main__":
    main()
