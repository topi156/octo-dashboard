"""
OCTO FUND DASHBOARD v3 - app.py
Full Supabase integration + PDF AI Analysis via OpenRouter
"""

import streamlit as st
import hashlib
import pandas as pd
import json
import requests
from supabase import create_client, Client

OPENROUTER_API_KEY = st.secrets.get("OPENROUTER_API_KEY", "")

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
  "strategy": "one of: PE, Credit, Infrastructure, Real Estate, Hedge, Venture",
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

st.set_page_config(
    page_title="ALT Group | Octo Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;700&display=swap');
    * { font-family: 'Heebo', sans-serif !important; }
    .main { direction: rtl; }
    .stMarkdown, .stText, h1, h2, h3, p { direction: rtl; text-align: right; }
    .stApp { background-color: #0f1117 !important; }
    [data-testid="stAppViewContainer"] { background-color: #0f1117 !important; }
    [data-testid="stHeader"] { background-color: #0f1117 !important; }
    section[data-testid="stSidebar"] + div { background-color: #0f1117 !important; }
    .stApp, .main, [data-testid="stAppViewContainer"] { color: #e2e8f0 !important; }
    p, span, label, div { color: #e2e8f0; }

    /* Expander */
    [data-testid="stExpander"] summary { 
        color: #e2e8f0 !important;
        direction: rtl !important;
        display: flex !important;
        flex-direction: row-reverse !important;
        align-items: center !important;
        gap: 8px !important;
    }
    [data-testid="stExpander"] summary p,
    [data-testid="stExpander"] summary span { color: #e2e8f0 !important; }
    [data-testid="stExpander"] summary svg { flex-shrink: 0; }
    [data-testid="stExpander"] { 
        background: #1a1a2e !important; 
        border: 1px solid #0f3460 !important;
        border-radius: 10px !important;
        margin-bottom: 8px !important;
    }

    /* ═══ Selectbox + Dropdown - COMPREHENSIVE DARK FIX ═══ */
    /* Box itself */
    [data-testid="stSelectbox"] > div > div,
    [data-testid="stSelectbox"] > div > div > div,
    [data-testid="stSelectbox"] span { 
        background-color: #1e293b !important;
        color: #e2e8f0 !important;
        border-color: #334155 !important;
    }
    /* BaseWeb popover container */
    [data-baseweb="popover"],
    [data-baseweb="popover"] > div,
    [data-baseweb="popover"] > div > div {
        background-color: #1e293b !important;
    }
    /* BaseWeb select menu */
    [data-baseweb="select"] > div,
    [data-baseweb="menu"],
    [data-baseweb="menu"] > div,
    [data-baseweb="menu"] ul {
        background-color: #1e293b !important;
        border: 1px solid #334155 !important;
    }
    [data-baseweb="menu"] * { color: #e2e8f0 !important; }
    /* Virtual listbox */
    ul[data-testid="stSelectboxVirtualDropdown"],
    [role="listbox"],
    [role="listbox"] > div,
    [role="listbox"] li { 
        background-color: #1e293b !important;
        border-color: #334155 !important;
    }
    /* Option items */
    [role="option"] { 
        background-color: #1e293b !important; 
        color: #e2e8f0 !important; 
    }
    [role="option"]:hover,
    [role="option"][aria-selected="true"] { 
        background-color: #0f3460 !important;
    }
    [role="option"] * { 
        color: #e2e8f0 !important; 
        background-color: transparent !important; 
    }
    /* Catch-all for any remaining white backgrounds in dropdowns */
    li[class*="option"],
    div[class*="option"] {
        background-color: #1e293b !important;
        color: #e2e8f0 !important;
    }

    /* Metric cards */
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460;
        border-radius: 12px;
        padding: 16px;
    }
    [data-testid="metric-container"] label,
    [data-testid="metric-container"] div { color: #94a3b8 !important; }
    [data-testid="metric-container"] [data-testid="stMetricValue"] { color: #ffffff !important; font-weight: 700 !important; }

    /* Sidebar */
    [data-testid="stSidebar"] { background: #0f1117 !important; }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }

    /* Tabs */
    [data-testid="stTabs"] [role="tab"] { color: #94a3b8 !important; }
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] { color: #ffffff !important; border-bottom-color: #3b82f6 !important; }

    /* Inputs */
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stTextArea"] textarea { 
        background: #1e293b !important; 
        color: #e2e8f0 !important;
        border-color: #334155 !important;
    }

    [data-testid="stDataFrame"] { color: #e2e8f0 !important; }
    [data-testid="stCaptionContainer"] { color: #94a3b8 !important; }
    hr { border-color: #1e293b !important; }

    .dashboard-header {
        background: linear-gradient(90deg, #1a1a2e, #0f3460);
        padding: 20px 30px;
        border-radius: 12px;
        margin-bottom: 24px;
    }
    [data-testid="stToggle"] label { color: #94a3b8 !important; }
    [data-testid="stMultiSelect"] span { color: #e2e8f0 !important; }
    [data-testid="stAlert"] { color: #e2e8f0 !important; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_supabase() -> Client:
    url = "https://lyaxipwsvlnsymdbkokq.supabase.co"
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx5YXhpcHdzdmxuc3ltZGJrb2txIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIwMjQzNTQsImV4cCI6MjA4NzYwMDM1NH0.6LyuFmRi6ApaWbgy_acQxEsp6r96dkG8xYJZKFpB6aQ"
    return create_client(url, key)

def get_funds():
    try:
        sb = get_supabase()
        res = sb.table("funds").select("*").order("name").execute()
        return res.data or []
    except Exception as e:
        st.error(f"שגיאה בטעינת קרנות: {e}")
        return []

def get_capital_calls(fund_id):
    try:
        sb = get_supabase()
        res = sb.table("capital_calls").select("*").eq("fund_id", fund_id).order("call_number").execute()
        return res.data or []
    except Exception as e:
        st.error(f"שגיאה: {e}")
        return []

def get_distributions(fund_id):
    try:
        sb = get_supabase()
        res = sb.table("distributions").select("*").eq("fund_id", fund_id).order("dist_date").execute()
        return res.data or []
    except:
        return []

def get_quarterly_reports(fund_id):
    try:
        sb = get_supabase()
        res = sb.table("quarterly_reports").select("*").eq("fund_id", fund_id).order("year,quarter").execute()
        return res.data or []
    except:
        return []

def get_pipeline_funds():
    try:
        sb = get_supabase()
        res = sb.table("pipeline_funds").select("*").order("target_close_date").execute()
        return res.data or []
    except:
        return []

def get_gantt_tasks(pipeline_fund_id):
    try:
        sb = get_supabase()
        res = sb.table("gantt_tasks").select("*").eq("pipeline_fund_id", pipeline_fund_id).order("start_date").execute()
        return res.data or []
    except:
        return []

USERS = {
    "liron": "octo2026",
    "alex": "octo2026",
    "team": "altgroup2026",
}

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
            "🔍 Pipeline",
            "📈 דוחות רבעוניים",
        ], label_visibility="collapsed")
        st.divider()
        st.caption(f"משתמש: {st.session_state.get('username', '')}")
        st.caption("גרסה 2.0 | פברואר 2026")
        st.divider()
        if st.button("🚪 התנתק", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()

    if "סקירה כללית" in page:
        show_overview()
    elif "תיק השקעות" in page:
        show_portfolio()
    elif "Pipeline" in page:
        show_pipeline()
    elif "דוחות" in page:
        show_reports()

def show_overview():
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
        st.metric("התחייבויות USD", f"${total_commitment_usd:,.0f}")
    with col3:
        st.metric("התחייבויות EUR", f"€{total_commitment_eur:,.0f}")
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
                    "התחייבות": f"{currency_sym}{commitment:,.0f}" if commitment else "—",
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
                    <span style="color:#94a3b8">Call #{c.get('call_number')} | ${c.get('amount',0):,.0f}</span>
                </div>
                """, unsafe_allow_html=True)
        if not future_calls_found:
            st.info("💡 הוסף Calls עתידיים כדי לראות תחזית כאן")

def show_portfolio():
    st.title("📁 תיק השקעות")
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

    commitment = fund.get("commitment") or 0
    total_called = sum(c.get("amount") or 0 for c in calls if not c.get("is_future"))
    total_dist = sum(d.get("amount") or 0 for d in dists)
    uncalled = commitment - total_called
    currency_sym = "€" if fund.get("currency") == "EUR" else "$"

    col1, col2, col3, col4, col_edit, col_del = st.columns([2,2,2,2,1,1])
    with col1:
        st.metric("התחייבות", f"{currency_sym}{commitment:,.0f}" if commitment else "—")
    with col2:
        pct = f"{total_called/commitment*100:.1f}%" if commitment > 0 else "—"
        st.metric("סה״כ נקרא", f"{currency_sym}{total_called:,.0f}", pct)
    with col3:
        st.metric("יתרה לא נקראה", f"{currency_sym}{uncalled:,.0f}" if commitment else "—")
    with col4:
        st.metric("סה״כ חולק", f"{currency_sym}{total_dist:,.0f}")
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
                strategy_opts = ["PE","Credit","Infrastructure","Real Estate","Hedge","Venture"]
                cur_s = fund.get("strategy","PE")
                new_strategy = st.selectbox("אסטרטגיה", strategy_opts,
                    index=strategy_opts.index(cur_s) if cur_s in strategy_opts else 0)
            with col2:
                new_commitment = st.number_input("התחייבות", value=float(commitment), min_value=0.0)
                cur_cur = fund.get("currency","USD")
                new_currency = st.selectbox("מטבע", ["USD","EUR"], index=0 if cur_cur=="USD" else 1)
                status_opts = ["active","closed","exited"]
                cur_st = fund.get("status","active")
                new_status = st.selectbox("סטטוס", status_opts,
                    index=status_opts.index(cur_st) if cur_st in status_opts else 0)
                new_vintage = st.number_input("ויינטג'", value=int(fund.get("vintage_year") or 2020), min_value=2000, max_value=2030)
            c1, c2 = st.columns(2)
            with c1:
                if st.form_submit_button("💾 שמור", type="primary"):
                    try:
                        get_supabase().table("funds").update({
                            "name": new_name, "manager": new_manager,
                            "strategy": new_strategy, "commitment": new_commitment,
                            "currency": new_currency, "status": new_status,
                            "vintage_year": new_vintage
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
                with st.expander(f"Call #{c.get('call_number')} | {c.get('payment_date','')} | {currency_sym}{c.get('amount',0):,.0f} {'🔮' if c.get('is_future') else '✅'}", expanded=False):
                    col1, col2, col3 = st.columns([2,2,1])
                    with col1:
                        st.write(f"תאריך קבלה: {c.get('call_date','')}")
                        st.write(f"תאריך תשלום: {c.get('payment_date','')}")
                        st.write(f"סכום: {currency_sym}{c.get('amount',0):,.0f}")
                    with col2:
                        st.write(f"השקעות: {currency_sym}{c.get('investments',0):,.0f}" if c.get('investments') else "השקעות: —")
                        st.write(f"דמי ניהול: {currency_sym}{c.get('mgmt_fee',0):,.0f}" if c.get('mgmt_fee') else "דמי ניהול: —")
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
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("אין Capital Calls עדיין")

        st.divider()
        st.markdown("**➕ הוסף Capital Call**")
        with st.form(f"add_call_{fund['id']}"):
            col1, col2, col3 = st.columns(3)
            with col1:
                call_num = st.number_input("מספר קריאה", min_value=1, value=len(calls)+1)
                call_date = st.date_input("תאריך קבלה")
                payment_date = st.date_input("תאריך תשלום")
            with col2:
                amount = st.number_input("סכום כולל", min_value=0.0)
                investments = st.number_input("השקעות", min_value=0.0)
                mgmt_fee = st.number_input("דמי ניהול", min_value=0.0)
            with col3:
                fund_expenses = st.number_input("הוצאות קרן", min_value=0.0)
                gp_contribution = st.number_input("GP Contribution", min_value=0.0)
                is_future = st.checkbox("קריאה עתידית")
                notes = st.text_input("הערות")
            if st.form_submit_button("שמור", type="primary"):
                try:
                    get_supabase().table("capital_calls").insert({
                        "fund_id": fund["id"], "call_number": call_num,
                        "call_date": str(call_date), "payment_date": str(payment_date),
                        "amount": amount, "investments": investments,
                        "mgmt_fee": mgmt_fee, "fund_expenses": fund_expenses,
                        "gp_contribution": gp_contribution, "is_future": is_future, "notes": notes
                    }).execute()
                    st.success("✅ נשמר!")
                    st.rerun()
                except Exception as e:
                    st.error(f"שגיאה: {e}")

    with tab2:
        if dists:
            st.markdown("**רשימת Distributions**")
            for d in dists:
                with st.expander(f"Dist #{d.get('dist_number')} | {d.get('dist_date','')} | {currency_sym}{d.get('amount',0):,.0f}", expanded=False):
                    col1, col2 = st.columns([4,1])
                    with col1:
                        st.write(f"סוג: {d.get('dist_type','')} | סכום: {currency_sym}{d.get('amount',0):,.0f}")
                    with col2:
                        if st.button("🗑️", key=f"del_dist_{d['id']}", help="מחק Distribution"):
                            st.session_state[f"confirm_del_dist_{d['id']}"] = True
                    if st.session_state.get(f"confirm_del_dist_{d['id']}"):
                        st.warning("למחוק Distribution זה?")
                        dc1, dc2 = st.columns(2)
                        with dc1:
                            if st.button("✅ מחק", key=f"yes_dist_{d['id']}"):
                                try:
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
                        st.write(f"NAV: {currency_sym}{r.get('nav',0):,.0f} | DPI: {r.get('dpi','—')} | RVPI: {r.get('rvpi','—')}")
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
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("אין דוחות רבעוניים עדיין")

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
                    strategy_options = ["PE", "Credit", "Infrastructure", "Real Estate", "Hedge", "Venture"]
                    ai_strategy = r.get("strategy", "PE")
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
                notes_default = f"גודל קרן: ${fund_size:,.0f}M | MOIC: {moic_low}x-{moic_high}x | IRR: {irr}% | מנהל AUM: ${r.get('aum_manager', 0)}B" if fund_size else ""
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
                strategy = st.selectbox("אסטרטגיה", ["PE", "Credit", "Infrastructure", "Real Estate", "Hedge", "Venture"])
            with col2:
                target_commitment = st.number_input("יעד השקעה", min_value=0.0)
                currency = st.selectbox("מטבע", ["USD", "EUR"])
                target_close = st.date_input("תאריך סגירה")
                priority = st.selectbox("עדיפות", ["high", "medium", "low"])
            notes = st.text_area("הערות")
            if st.form_submit_button("צור קרן + גאנט", type="primary"):
                try:
                    sb = get_supabase()
                    res = sb.table("pipeline_funds").insert({
                        "name": name, "manager": manager, "strategy": strategy,
                        "target_commitment": target_commitment, "currency": currency,
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
                if st.button("✏️ עריכה", key=f"edit_{fid}"):
                    st.session_state[f"editing_{fid}"] = True
            with col_b:
                if st.button("🗑️ מחיקה", key=f"del_{fid}"):
                    st.session_state[f"confirm_delete_{fid}"] = True

            if st.session_state.get(f"confirm_delete_{fid}"):
                st.warning(f"⚠️ למחוק את '{fund['name']}'? פעולה זו תמחק גם את כל משימות הגאנט.")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("✅ כן, מחק", key=f"yes_{fid}", type="primary"):
                        try:
                            sb = get_supabase()
                            sb.table("gantt_tasks").delete().eq("pipeline_fund_id", fid).execute()
                            sb.table("pipeline_funds").delete().eq("id", fid).execute()
                            st.success("נמחק!")
                            st.session_state.pop(f"confirm_delete_{fid}", None)
                            st.rerun()
                        except Exception as e:
                            st.error(f"שגיאה: {e}")
                with col_no:
                    if st.button("❌ ביטול", key=f"no_{fid}"):
                        st.session_state.pop(f"confirm_delete_{fid}", None)
                        st.rerun()

            if st.session_state.get(f"editing_{fid}"):
                with st.form(f"edit_form_{fid}"):
                    st.markdown("**✏️ עריכת פרטי קרן**")
                    col1, col2 = st.columns(2)
                    with col1:
                        new_name = st.text_input("שם הקרן", value=fund.get("name",""))
                        new_manager = st.text_input("מנהל", value=fund.get("manager",""))
                        strategy_opts = ["PE", "Credit", "Infrastructure", "Real Estate", "Hedge", "Venture"]
                        cur_strat = fund.get("strategy","PE")
                        new_strategy = st.selectbox("אסטרטגיה", strategy_opts,
                            index=strategy_opts.index(cur_strat) if cur_strat in strategy_opts else 0)
                        new_geo = st.text_input("מיקוד גיאוגרפי", value=fund.get("geographic_focus","") or "")
                    with col2:
                        cur_commit = float(fund.get("target_commitment") or 0)
                        new_commitment = st.number_input("יעד השקעה ($M)", value=cur_commit/1_000_000 if cur_commit > 1000 else cur_commit, step=0.5)
                        cur_currency = fund.get("currency","USD")
                        new_currency = st.selectbox("מטבע", ["USD","EUR"], index=0 if cur_currency=="USD" else 1)
                        priority_opts = ["high","medium","low"]
                        cur_priority = fund.get("priority","medium")
                        new_priority = st.selectbox("עדיפות", priority_opts,
                            index=priority_opts.index(cur_priority) if cur_priority in priority_opts else 1)
                        import datetime
                        cur_date = fund.get("target_close_date")
                        try:
                            default_date = datetime.date.fromisoformat(str(cur_date)) if cur_date else datetime.date.today()
                        except:
                            default_date = datetime.date.today()
                        new_close = st.date_input("תאריך סגירה", value=default_date)
                    new_notes = st.text_area("הערות", value=fund.get("notes","") or "")
                    col_save, col_cancel = st.columns(2)
                    with col_save:
                        if st.form_submit_button("💾 שמור שינויים", type="primary"):
                            try:
                                get_supabase().table("pipeline_funds").update({
                                    "name": new_name, "manager": new_manager,
                                    "strategy": new_strategy, "target_commitment": new_commitment,
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
                    commitment = fund.get("target_commitment") or 0
                    st.metric("יעד השקעה", f"{currency_sym}{commitment:,.0f}" if commitment else "—")
                with col2:
                    st.metric("תאריך סגירה", str(fund.get("target_close_date", "")))
                with col3:
                    st.metric("עדיפות", fund.get("priority", "").upper())
                if fund.get("notes"):
                    st.caption(f"📝 {fund['notes']}")
                tasks = get_gantt_tasks(fund["id"])
                if tasks:
                    show_gantt(tasks, fund)

def show_gantt(tasks, fund):
    import plotly.graph_objects as go
    from datetime import datetime, date

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

    gantt_tasks_data = []
    today = date.today()
    for t in tasks:
        if t.get("start_date") and t.get("due_date"):
            cat = t.get("category", "Admin")
            cfg = CAT_CONFIG.get(cat, CAT_CONFIG["Admin"])
            status = t.get("status", "todo")
            if status == "done":
                bar_color = "#22c55e"
            elif status == "blocked":
                bar_color = "#ef4444"
            elif status == "in_progress":
                bar_color = "#3b82f6"
            else:
                bar_color = cfg["color"]
            gantt_tasks_data.append({
                "Task": f"{cfg['icon']} {t['task_name']}",
                "Start": t["start_date"],
                "Finish": t["due_date"],
                "Color": bar_color,
                "Category": cat,
                "Status": STATUS_CONFIG.get(status, {}).get("label", status),
            })

    if gantt_tasks_data:
        fig = go.Figure()
        for i, t in enumerate(reversed(gantt_tasks_data)):
            start_dt = datetime.fromisoformat(t["Start"])
            finish_dt = datetime.fromisoformat(t["Finish"])
            duration = (finish_dt - start_dt).days
            fig.add_trace(go.Bar(
                x=[duration],
                y=[t["Task"]],
                base=[t["Start"]],
                orientation="h",
                marker=dict(color=t["Color"], opacity=0.85, line=dict(width=0)),
                hovertemplate=f"<b>{t['Task']}</b><br>{t['Start']} → {t['Finish']}<br>סטטוס: {t['Status']}<extra></extra>",
                showlegend=False,
            ))
        fig.add_shape(
            type="line",
            x0=str(today), x1=str(today),
            y0=0, y1=1, yref="paper",
            line=dict(color="#f59e0b", width=1.5, dash="dash"),
        )
        fig.add_annotation(
            x=str(today), y=1, yref="paper",
            text="היום", showarrow=False,
            font=dict(color="#f59e0b", size=11),
            yanchor="bottom"
        )
        fig.update_layout(
            height=max(300, len(gantt_tasks_data) * 28 + 80),
            barmode="overlay",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#0f172a",
            font=dict(color="#e2e8f0", size=11, family="Heebo"),
            margin=dict(l=10, r=20, t=20, b=30),
            xaxis=dict(type="date", gridcolor="#1e293b", tickformat="%d/%m/%y", tickfont=dict(size=10)),
            yaxis=dict(gridcolor="#1e293b", tickfont=dict(size=11), automargin=True),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("##### 📋 משימות לפי קטגוריה")
    col_f1, col_f2 = st.columns([3, 1])
    with col_f2:
        show_done = st.toggle("הצג הושלם", value=False, key=f"show_done_{fid}")

    cats_order = ["Analysis", "IC", "DD", "Legal", "Tax", "Admin"]
    for cat in cats_order:
        cat_tasks = [t for t in tasks if t.get("category","") == cat]
        if not cat_tasks:
            continue
        visible = cat_tasks if show_done else [t for t in cat_tasks if t.get("status") != "done"]
        if not visible:
            continue

        cfg = CAT_CONFIG.get(cat, CAT_CONFIG["Admin"])
        done_c = sum(1 for t in cat_tasks if t.get("status") == "done")
        cat_pct = int(done_c / len(cat_tasks) * 100)

        st.markdown(f"""
        <div style="background:{cfg['bg']};border-left:3px solid {cfg['color']};
                    border-radius:8px;padding:10px 14px;margin:8px 0 4px 0;
                    display:flex;justify-content:space-between;align-items:center;">
            <span style="color:{cfg['color']};font-weight:600;">{cfg['icon']} {cat}</span>
            <span style="color:#94a3b8;font-size:12px;">{done_c}/{len(cat_tasks)} · {cat_pct}%</span>
        </div>
        """, unsafe_allow_html=True)

        for t in visible:
            status = t.get("status", "todo")
            scfg = STATUS_CONFIG.get(status, STATUS_CONFIG["todo"])
            due = t.get("due_date", "")

            col1, col2, col3 = st.columns([4, 1, 1])
            with col1:
                st.markdown(
                    f'<div style="padding:4px 0;color:{"#64748b" if status=="done" else "#e2e8f0"};">'
                    f'{scfg["icon"]} {t["task_name"]}</div>',
                    unsafe_allow_html=True
                )
            with col2:
                st.caption(due)
            with col3:
                # FIX: label must not be empty - use label_visibility="collapsed" to hide it visually
                new_status = st.selectbox(
                    "סטטוס",
                    STATUS_LIST,
                    index=STATUS_LIST.index(status) if status in STATUS_LIST else 0,
                    key=f"task_{t['id']}",
                    label_visibility="collapsed"
                )
                if new_status != status:
                    try:
                        sb.table("gantt_tasks").update({"status": new_status}).eq("id", t["id"]).execute()
                        st.rerun()
                    except Exception as e:
                        st.error(f"שגיאה: {e}")

def show_reports():
    st.title("📈 דוחות רבעוניים")
    funds = get_funds()
    if not funds:
        st.info("אין קרנות")
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

    st.divider()
    st.markdown("**➕ הוסף דוח רבעוני**")
    with st.form("add_report"):
        col1, col2, col3 = st.columns(3)
        with col1:
            year = st.number_input("שנה", value=2025, min_value=2020, max_value=2030)
            quarter = st.selectbox("רבעון", [1, 2, 3, 4])
            report_date = st.date_input("תאריך דוח")
        with col2:
            nav = st.number_input("NAV", min_value=0.0)
            tvpi = st.number_input("TVPI", min_value=0.0, step=0.01, format="%.2f")
            dpi = st.number_input("DPI", min_value=0.0, step=0.01, format="%.2f")
        with col3:
            rvpi = st.number_input("RVPI", min_value=0.0, step=0.01, format="%.2f")
            irr = st.number_input("IRR %", step=0.1, format="%.1f")
            notes = st.text_area("הערות")
        if st.form_submit_button("שמור", type="primary"):
            try:
                get_supabase().table("quarterly_reports").upsert({
                    "fund_id": fund_id, "year": year, "quarter": quarter,
                    "report_date": str(report_date), "nav": nav,
                    "tvpi": tvpi, "dpi": dpi, "rvpi": rvpi, "irr": irr, "notes": notes
                }).execute()
                st.success("✅ דוח נשמר!")
                st.rerun()
            except Exception as e:
                st.error(f"שגיאה: {e}")


if __name__ == "__main__":
    main()
