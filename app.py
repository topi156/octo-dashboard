"""
OCTO FUND DASHBOARD v8.4 - app.py
UI Optimization: M-based formatting, 0.5M steps, and reduced font sizes
"""

import streamlit as st
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
    # Logic to show as M for dashboard clarity while keeping exact values available
    if amount >= 1_000_000:
        return f"{currency_sym}{amount/1_000_000:,.2f}M"
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
    return "\n".join(pages_text)

# --- AI FUNCTIONS (PDF Analysis) ---
def analyze_pdf_with_ai(pdf_bytes: bytes) -> dict:
    pdf_text = extract_pdf_text(pdf_bytes)
    prompt = f"Analyze this PE fund deck and return JSON with keys: fund_name, manager, strategy, fund_size_target (in millions), currency, target_return_moic_low, target_return_moic_high, target_irr_gross, vintage_year, mgmt_fee_pct, carried_interest_pct, preferred_return_pct, geographic_focus, sector_focus, key_highlights. Text: {pdf_text[:12000]}"
    payload = {"model": "anthropic/claude-3.5-sonnet", "messages": [{"role": "user", "content": prompt}], "max_tokens": 2000}
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=90)
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if "```" in content: content = content.split("```")[1].replace("json\n", "")
    return json.loads(content.strip())

def analyze_capital_call_pdf_with_ai(pdf_bytes: bytes) -> dict:
    pdf_text = extract_pdf_text(pdf_bytes)
    prompt = f"Extract Capital Call details to JSON: call_date, payment_date, amount, investments, mgmt_fee, fund_expenses. Text: {pdf_text[:10000]}"
    payload = {"model": "anthropic/claude-3.5-sonnet", "messages": [{"role": "user", "content": prompt}], "max_tokens": 1000}
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=90)
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if "```" in content: content = content.split("```")[1].replace("json\n", "")
    return json.loads(content.strip())

def analyze_quarterly_report_with_ai(report_text: str) -> dict:
    prompt = f"Extract Quarterly Report data to JSON: year, quarter, report_date, nav, tvpi, dpi, rvpi, irr. Text: {report_text[:12000]}"
    payload = {"model": "anthropic/claude-3.5-sonnet", "messages": [{"role": "user", "content": prompt}], "max_tokens": 1000}
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=90)
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if "```" in content: content = content.split("```")[1].replace("json\n", "")
    return json.loads(content.strip())

st.set_page_config(page_title="ALT Group | Octo Dashboard", page_icon="📊", layout="wide")

# CSS: REDUCED FONT SIZES
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;700&display=swap');
    * { font-family: 'Inter', sans-serif; }
    
    h1 { font-size: 1.5rem !important; }
    h2 { font-size: 1.3rem !important; }
    h3 { font-size: 1.1rem !important; }
    
    .stApp { background-color: #0f1117; color: #e2e8f0; }
    
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460; border-radius: 10px; padding: 10px;
    }
    [data-testid="stMetricValue"] { 
        font-size: 0.95rem !important; /* Smaller fonts for metrics */
        font-weight: 700;
    }
    [data-testid="stMetricLabel"] { font-size: 0.75rem !important; }

    [data-testid="stExpander"] { background: #1a1a2e; border: 1px solid #0f3460; border-radius: 8px; }
    .dashboard-header { background: linear-gradient(90deg, #1a1a2e, #0f3460); padding: 15px 25px; border-radius: 10px; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)

# --- DB HELPERS ---
def get_supabase() -> Client:
    if "sb_client" not in st.session_state:
        st.session_state.sb_client = create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])
    return st.session_state.sb_client

def clear_cache_and_rerun():
    st.cache_data.clear()
    st.rerun()

# --- FETCH FUNCTIONS ---
@st.cache_data(ttl=600)
def fetch_funds(_sb): return _sb.table("funds").select("*").order("name").execute().data or []
@st.cache_data(ttl=600)
def fetch_calls(_sb): return _sb.table("capital_calls").select("*").order("call_number").execute().data or []
@st.cache_data(ttl=600)
def fetch_dists(_sb): return _sb.table("distributions").select("*").order("dist_date").execute().data or []
@st.cache_data(ttl=600)
def fetch_reps(_sb): return _sb.table("quarterly_reports").select("*").order("year,quarter").execute().data or []
@st.cache_data(ttl=600)
def fetch_pipe(_sb): return _sb.table("pipeline_funds").select("*").order("target_close_date").execute().data or []
@st.cache_data(ttl=600)
def fetch_tasks(_sb): return _sb.table("gantt_tasks").select("*").order("start_date").execute().data or []
@st.cache_data(ttl=600)
def fetch_invs(_sb): return _sb.table("investors").select("*").execute().data or []
@st.cache_data(ttl=600)
def fetch_lpc(_sb): return _sb.table("lp_calls").select("*").order("call_date").execute().data or []
@st.cache_data(ttl=600)
def fetch_pay(_sb): return _sb.table("lp_payments").select("*").execute().data or []

# --- LOGIN ---
def show_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 📊 Octo Fund Dashboard")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Secure Login", type="primary", use_container_width=True):
            try:
                get_supabase().auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.logged_in = True
                st.session_state.username = email.split("@")[0]
                st.rerun()
            except Exception as e: st.error(f"Login Error: {e}")

if not st.session_state.get("logged_in"):
    show_login()
    st.stop()

# --- MAIN APP ---
sb = get_supabase()
with st.sidebar:
    st.markdown("## 📊 Octo Dashboard")
    page = st.radio("Menu", ["🏠 Overview", "📁 Portfolio", "👥 Investors", "🔍 Pipeline", "📈 Reports"])
    st.divider()
    if st.button("🔄 Refresh Data", use_container_width=True): clear_cache_and_rerun()
    if st.button("🚪 Logout", use_container_width=True):
        sb.auth.sign_out()
        st.session_state.clear()
        st.rerun()

# --- PAGES ---
if page == "🏠 Overview":
    st.markdown('<div class="dashboard-header"><h1>📊 Dashboard Overview</h1></div>', unsafe_allow_html=True)
    funds = fetch_funds(sb)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Funds", len(funds))
    c2.metric("Pipeline Funds", len(fetch_pipe(sb)))
    
    st.divider()
    st.subheader("Funds Status")
    if funds:
        data = []
        for f in funds:
            calls = [c for c in fetch_calls(sb) if c["fund_id"] == f["id"] and not c.get("is_future")]
            total_called = sum(c["amount"] for c in calls)
            data.append({"Fund": f["name"], "Strategy": f["strategy"], "Commitment": format_currency(f["commitment"]), "Called": format_currency(total_called), "Status": f["status"].upper()})
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

elif page == "📁 Portfolio":
    st.title("📁 Portfolio Management")
    with st.expander("➕ Add New Fund"):
        with st.form("add_f"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Fund Name")
            manager = c1.text_input("Manager")
            # Step set to 500,000 for half-million increments
            commit = c2.number_input("Commitment Amount", min_value=0.0, step=500000.0, format="%.0f")
            curr = c2.selectbox("Currency", ["USD", "EUR"])
            if st.form_submit_button("Save Fund"):
                sb.table("funds").insert({"name": name, "manager": manager, "commitment": commit, "currency": curr, "status": "active"}).execute()
                clear_cache_and_rerun()

elif page == "👥 Investors":
    st.title("👥 Investors & LP Calls")
    invs = fetch_invs(sb)
    with st.expander("➕ Add Investor"):
        name = st.text_input("Investor Name")
        # Step set to 500,000
        commit = st.number_input("Commitment", min_value=0.0, step=500000.0, format="%.0f")
        if st.button("Save Investor"):
            sb.table("investors").insert({"name": name, "commitment": commit}).execute()
            clear_cache_and_rerun()

elif page == "🔍 Pipeline":
    st.title("🔍 Fund Pipeline")
    pipe = fetch_pipe(sb)
    
    with st.expander("📄 Upload Deck (AI Analysis)"):
        up = st.file_uploader("Upload PDF", type="pdf")
        if up and st.button("🤖 Analyze with AI"):
            with st.spinner("Analyzing..."):
                res = analyze_pdf_with_ai(up.read())
                st.session_state.pdf_res = res
                st.success("Done!")

    with st.expander("➕ Add Manually"):
        with st.form("add_p"):
            c1, c2 = st.columns(2)
            # Use data from AI if available
            p_res = st.session_state.get("pdf_res", {})
            name = c1.text_input("Fund Name", value=p_res.get("fund_name", ""))
            # Target Commitment with 0.5M steps
            target = c2.number_input("Target Commitment", min_value=0.0, step=500000.0, format="%.0f")
            close = c2.date_input("Target Close Date")
            if st.form_submit_button("Create Pipeline Entry"):
                r = sb.table("pipeline_funds").insert({"name": name, "target_commitment": target, "target_close_date": str(close)}).execute()
                sb.rpc("create_default_gantt_tasks", {"p_fund_id": r.data[0]["id"]}).execute()
                clear_cache_and_rerun()

    for p in pipe:
        with st.expander(f"{p['name']} | Target: {format_currency(p['target_commitment'])}"):
            st.markdown(f"**Closing Date:** {p['target_close_date']}")
            tasks = [t for t in fetch_tasks(sb) if t["pipeline_fund_id"] == p["id"]]
            if tasks:
                st.info(f"Progress: {len([t for t in tasks if t['status']=='done'])}/{len(tasks)} tasks completed.")
            if st.button("🗑️ Delete Fund", key=f"del_{p['id']}"):
                sb.table("pipeline_funds").delete().eq("id", p["id"]).execute()
                clear_cache_and_rerun()

elif page == "📈 Reports":
    st.title("📈 Performance Reports")
    funds = fetch_funds(sb)
    if funds:
        sel = st.selectbox("Select Fund", [f["name"] for f in funds])
        f_id = [f["id"] for f in funds if f["name"] == sel][0]
        reps = [r for r in fetch_reps(sb) if r["fund_id"] == f_id]
        if reps:
            st.dataframe(pd.DataFrame(reps), use_container_width=True, hide_index=True)
        else: st.info("No reports yet.")
