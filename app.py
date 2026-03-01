"""
OCTO FUND DASHBOARD v8.2 - app.py
Full English UI, LTR Alignment, Exact Currency Formatting & Smaller Metric Fonts
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
    # עיצוב מלא עם פסיקים (ללא M ו-K)
    formatted = f"{currency_sym}{amount:,.2f}"
    if formatted.endswith(".00"):
        formatted = formatted[:-3]
    return formatted

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
Return ONLY a valid JSON object with these exact keys (use null only if truly not found anywhere):
{{
"fund_name": "full fund name including fund number",
"manager": "management company name",
"strategy": "one of: Growth, VC, Tech, Niche, Special Situations, Mid-Market Buyout",
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

IMPORTANT: Fund size in billions -> convert to millions. E.g. $2.5B = 2500. Return ONLY JSON.
FUND PRESENTATION TEXT:
{pdf_text}"""

    payload = {
        "model": "anthropic/claude-3.5-sonnet",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000
    }
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=90)
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if "```" in content: content = content.split("```")[1].replace("json\n", "")
    return json.loads(content.strip())

def analyze_capital_call_pdf_with_ai(pdf_bytes: bytes) -> dict:
    pdf_text = extract_pdf_text(pdf_bytes)
    prompt = f"""You are an expert private equity fund accountant. Carefully analyze this Capital Call Notice and extract the financial details.
Return ONLY a valid JSON object with these exact keys (use 0 if not found, use null for missing dates):
{{
    "call_date": "YYYY-MM-DD",
    "payment_date": "YYYY-MM-DD",
    "amount": total amount requested (number),
    "investments": amount allocated to investments (number),
    "mgmt_fee": amount allocated to management fees (number),
    "fund_expenses": amount allocated to fund expenses (number)
}}
IMPORTANT: Return ONLY JSON. Ensure amounts are numbers without commas.
CAPITAL CALL TEXT:
{pdf_text}"""
    payload = {"model": "anthropic/claude-3.5-sonnet", "messages": [{"role": "user", "content": prompt}], "max_tokens": 1000}
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=90)
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if "```" in content: content = content.split("```")[1].replace("json\n", "")
    return json.loads(content.strip())

def analyze_quarterly_report_with_ai(report_text: str) -> dict:
    prompt = f"""You are an expert private equity fund accountant. Analyze this quarterly report and extract metrics.
Return ONLY a valid JSON object with these exact keys:
{{
    "year": number (e.g. 2025),
    "quarter": number (1, 2, 3, or 4),
    "report_date": "YYYY-MM-DD",
    "nav": number (without commas),
    "tvpi": number (e.g. 1.52),
    "dpi": number,
    "rvpi": number,
    "irr": number (percentage e.g. 15.5)
}}
Return ONLY JSON.
REPORT TEXT:
{report_text}"""
    payload = {"model": "anthropic/claude-3.5-sonnet", "messages": [{"role": "user", "content": prompt}], "max_tokens": 1000}
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=90)
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if "```" in content: content = content.split("```")[1].replace("json\n", "")
    return json.loads(content.strip())

st.set_page_config(page_title="ALT Group | Octo Dashboard", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;700&display=swap');
    * { font-family: 'Inter', sans-serif; }
    .stApp { background-color: #0f1117 !important; color: #e2e8f0 !important; }
    p, span, label, div { color: #e2e8f0; }

    [data-testid="stExpander"] summary { color: #e2e8f0 !important; display: flex !important; align-items: center !important; gap: 8px !important; }
    [data-testid="stExpander"] { background: #1a1a2e !important; border: 1px solid #0f3460 !important; border-radius: 10px !important; margin-bottom: 8px !important; }

    [data-testid="stSelectbox"] > div > div, [data-testid="stSelectbox"] span { background-color: #1e293b !important; color: #e2e8f0 !important; border-color: #334155 !important; }
    
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460; border-radius: 12px; padding: 12px;
    }
    [data-testid="metric-container"] label { color: #94a3b8 !important; }
    [data-testid="metric-container"] [data-testid="stMetricValue"] { 
        color: #ffffff !important; font-weight: 700 !important; 
        font-size: 1.05rem !important; /* הוקטן כדי להתאים למספרים מלאים וארוכים */
        word-wrap: break-word !important; 
    }

    [data-testid="stSidebar"] { background: #0f1117 !important; }
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] { color: #ffffff !important; border-bottom-color: #3b82f6 !important; }
    [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input, [data-testid="stDateInput"] input { background: #1e293b !important; color: #e2e8f0 !important; border-color: #334155 !important; }
    .dashboard-header { background: linear-gradient(90deg, #1a1a2e, #0f3460); padding: 20px 30px; border-radius: 12px; margin-bottom: 24px; }
</style>
""", unsafe_allow_html=True)

def get_supabase() -> Client:
    if "sb_client" not in st.session_state:
        st.session_state.sb_client = create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])
    return st.session_state.sb_client

def clear_cache_and_rerun():
    st.cache_data.clear()
    st.rerun()

def convert_df_to_excel(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Data')
    return output.getvalue()

def generate_master_excel_bytes() -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        funds = get_funds()
        if funds:
            funds_list = []
            for f in funds:
                calls = get_capital_calls(f["id"])
                total_called = sum(c.get("amount") or 0 for c in calls)
                funds_list.append({
                    "Fund Name": f.get("name"), "Manager": f.get("manager"), "Strategy": f.get("strategy"),
                    "Currency": f.get("currency"), "Commitment": f.get("commitment"),
                    "Total Called": total_called, "Status": f.get("status")
                })
            pd.DataFrame(funds_list).to_excel(writer, index=False, sheet_name='Funds Portfolio')
        else: pd.DataFrame([{"Message": "No funds in the system"}]).to_excel(writer, index=False, sheet_name='Funds Portfolio')
        
        investors = get_investors()
        lp_calls = get_lp_calls()
        payments = get_lp_payments()
        if investors:
            data = []
            for inv in investors:
                row = {"Investor Name": inv["name"], "Commitment": inv.get("commitment", 0)}
                for c in lp_calls:
                    col_name = f"{c['call_date']} ({c['call_pct']}%)"
                    payment = next((p for p in payments if p["lp_call_id"] == c["id"] and p["investor_id"] == inv["id"]), None)
                    row[col_name] = "Paid" if (payment and payment["is_paid"]) else "Unpaid"
                data.append(row)
            pd.DataFrame(data).to_excel(writer, index=False, sheet_name='Investors & Calls')
        
        pipeline = get_pipeline_funds()
        if pipeline:
            pipe_list = []
            for p in pipeline:
                pipe_list.append({
                    "Fund Name": p.get("name"), "Manager": p.get("manager"), "Strategy": p.get("strategy"),
                    "Target Commitment": p.get("target_commitment"), "Currency": p.get("currency"),
                    "Target Close Date": p.get("target_close_date"), "Priority": p.get("priority")
                })
            pd.DataFrame(pipe_list).to_excel(writer, index=False, sheet_name='Pipeline')
    return output.getvalue()

def log_action(action: str, table_name: str, details: str, old_data: dict = None):
    try:
        get_supabase().table("audit_logs").insert({
            "username": st.session_state.get("username", "system"),
            "action": action, "table_name": table_name, "details": details, "old_data": old_data or {}
        }).execute()
    except: pass

@st.cache_data(ttl=600)
def fetch_all_funds(_sb): return _sb.table("funds").select("*").order("name").execute().data or []
def get_funds(): return fetch_all_funds(get_supabase())

@st.cache_data(ttl=600)
def fetch_all_capital_calls(_sb): return _sb.table("capital_calls").select("*").order("call_number").execute().data or []
def get_capital_calls(fund_id=None):
    data = fetch_all_capital_calls(get_supabase())
    return [d for d in data if d["fund_id"] == fund_id] if fund_id else data

@st.cache_data(ttl=600)
def fetch_all_distributions(_sb): return _sb.table("distributions").select("*").order("dist_date").execute().data or []
def get_distributions(fund_id=None):
    data = fetch_all_distributions(get_supabase())
    return [d for d in data if d["fund_id"] == fund_id] if fund_id else data

@st.cache_data(ttl=600)
def fetch_all_quarterly_reports(_sb): return _sb.table("quarterly_reports").select("*").order("year,quarter").execute().data or []
def get_quarterly_reports(fund_id=None):
    data = fetch_all_quarterly_reports(get_supabase())
    return [d for d in data if d["fund_id"] == fund_id] if fund_id else data

@st.cache_data(ttl=600)
def fetch_all_pipeline_funds(_sb): return _sb.table("pipeline_funds").select("*").order("target_close_date").execute().data or []
def get_pipeline_funds(): return fetch_all_pipeline_funds(get_supabase())

@st.cache_data(ttl=600)
def fetch_all_gantt_tasks(_sb): return _sb.table("gantt_tasks").select("*").order("start_date").execute().data or []
def get_gantt_tasks(pipeline_fund_id=None):
    data = fetch_all_gantt_tasks(get_supabase())
    return [d for d in data if d["pipeline_fund_id"] == pipeline_fund_id] if pipeline_fund_id else data

@st.cache_data(ttl=600)
def fetch_all_investors(_sb): return _sb.table("investors").select("*").execute().data or []
def get_investors(): return fetch_all_investors(get_supabase())

@st.cache_data(ttl=600)
def fetch_all_lp_calls(_sb): return _sb.table("lp_calls").select("*").order("call_date").execute().data or []
def get_lp_calls(): return fetch_all_lp_calls(get_supabase())

@st.cache_data(ttl=600)
def fetch_all_lp_payments(_sb): return _sb.table("lp_payments").select("*").execute().data or []
def get_lp_payments(): return fetch_all_lp_payments(get_supabase())

@st.cache_data(ttl=600)
def fetch_all_audit_logs(_sb): return _sb.table("audit_logs").select("*").order("created_at", desc=True).limit(100).execute().data or []
def get_audit_logs(): return fetch_all_audit_logs(get_supabase())

def check_and_show_alerts():
    if "dismissed_banners" not in st.session_state: st.session_state.dismissed_banners = set()
    if "shown_toasts" not in st.session_state: st.session_state.shown_toasts = set()
    today = date.today()
    funds_dict = {f["id"]: f for f in get_funds()}
    pipe_dict = {f["id"]: f["name"] for f in get_pipeline_funds()}

    for cc in get_capital_calls():
        if not cc.get("payment_date"): continue
        try:
            days_left = (datetime.strptime(str(cc["payment_date"]).split("T")[0], "%Y-%m-%d").date() - today).days
            if days_left in [0, 1, 3, 7]:
                fname = funds_dict.get(cc.get("fund_id"), {}).get("name", "Unknown Fund")
                curr = "€" if funds_dict.get(cc.get("fund_id"), {}).get("currency") == "EUR" else "$"
                amt = format_currency(cc.get("amount", 0), curr)
                if days_left in [0, 1]:
                    alert_id = f"cc_banner_{cc['id']}_{days_left}"
                    if alert_id not in st.session_state.dismissed_banners:
                        c1, c2 = st.columns([15, 1])
                        with c1: st.error(f"🚨 **Today!** Capital Call due for {fname}: {amt}") if days_left == 0 else st.warning(f"⚠️ **Tomorrow!** Capital Call due for {fname}: {amt}")
                        with c2: 
                            if st.button("✖", key=f"btn_{alert_id}"): st.session_state.dismissed_banners.add(alert_id); st.rerun()
                else:
                    if f"cc_toast_{cc['id']}_{days_left}" not in st.session_state.shown_toasts:
                        st.toast(f"🔔 Upcoming: Capital Call for {fname} in {days_left} days.", icon="💸")
                        st.session_state.shown_toasts.add(f"cc_toast_{cc['id']}_{days_left}")
        except: pass

def show_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 📊 Octo Fund Dashboard")
        st.markdown("**ALT Group** | Private Capital")
        st.divider()
        email = st.text_input("Email", placeholder="name@altgroup.co.il")
        password = st.text_input("Password", type="password")
        if st.button("Secure Login", type="primary", use_container_width=True):
            try:
                res = get_supabase().auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.logged_in = True
                st.session_state.username = email.split("@")[0]
                st.rerun()
            except Exception as e:
                st.error(f"Login Error: {str(e)}")

def require_login():
    if not st.session_state.get("logged_in"): show_login(); st.stop()

def main():
    require_login()
    with st.sidebar:
        st.markdown("## 📊 Octo Dashboard")
        st.markdown("**ALT Group** | Private Capital")
        st.divider()
        page = st.radio("Navigation", ["🏠 Overview", "📁 Portfolio", "👥 Investors", "🔍 Pipeline", "📈 Reports", "📋 Audit Logs"], label_visibility="collapsed")
        st.divider()
        st.caption(f"User: {st.session_state.get('username', '')}")
        st.caption("Version 8.2 | English & Adjusted Fonts")
        st.divider()
        if st.button("🔄 Refresh Data", use_container_width=True): clear_cache_and_rerun()
        st.divider()
        st.download_button("📥 Download Master Excel", data=generate_master_excel_bytes(), file_name=f"Octo_Master_Report_{date.today()}.xlsx", use_container_width=True)
        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            try: get_supabase().auth.sign_out()
            except: pass
            st.session_state.clear()
            st.rerun()

    if "Overview" in page: show_overview()
    elif "Portfolio" in page: show_portfolio()
    elif "Investors" in page: show_investors()
    elif "Pipeline" in page: show_pipeline()
    elif "Reports" in page: show_reports()
    elif "Audit Logs" in page: show_audit_logs()

def show_audit_logs():
    st.title("📋 System Audit Logs")
    logs = get_audit_logs()
    if not logs: st.info("No audit logs recorded yet."); return
    for log in logs:
        with st.expander(f"{log['created_at'][:16]} | User: {log['username']} | {log['details']}"):
            st.write(f"**Action:** {log['action']} | **Table:** {log['table_name']}")
            if log.get("old_data"): st.json(log["old_data"])

def show_overview():
    check_and_show_alerts()
    st.markdown('<div class="dashboard-header"><h1 style="color:white;margin:0;">📊 Octo Fund Dashboard</h1><p style="color:#94a3b8;margin:4px 0 0 0;">ALT Group | Alternative Capital Management</p></div>', unsafe_allow_html=True)

    funds = get_funds()
    total_commitment_usd = sum(f.get("commitment") or 0 for f in funds if f.get("currency") == "USD")
    total_commitment_eur = sum(f.get("commitment") or 0 for f in funds if f.get("currency") == "EUR")

    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Active Funds", len(funds))
    with col2: st.metric("USD Commitments", format_currency(total_commitment_usd, "$"))
    with col3: st.metric("EUR Commitments", format_currency(total_commitment_eur, "€"))
    with col4: st.metric("Pipeline Funds", len(get_pipeline_funds()))

    st.divider()
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("📋 Funds Status")
        if funds:
            rows = []
            for f in funds:
                calls = get_capital_calls(f["id"])
                total_called = sum(c.get("amount") or 0 for c in calls)
                commitment = f.get("commitment") or 0
                pct = f"{total_called/commitment*100:.1f}%" if commitment > 0 else "—"
                sym = "€" if f.get("currency") == "EUR" else "$"
                rows.append({"Fund": f["name"], "Currency": f.get("currency"), "Commitment": format_currency(commitment, sym), "Total Called": format_currency(total_called, sym), "Called %": pct, "Status": f.get("status", "").capitalize()})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    with col2:
        st.subheader("🔔 Upcoming Events")
        for f in funds:
            for c in [x for x in get_capital_calls(f["id"]) if x.get("is_future")]:
                st.markdown(f"<div style='background:#1a3a1a;border-radius:8px;padding:12px;margin-bottom:8px;'><small style='color:#4ade80'>{c.get('payment_date','')}</small><br><strong>{f['name']}</strong><br><span style='color:#94a3b8'>Call #{c.get('call_number')} | {format_currency(c.get('amount',0), '$')}</span></div>", unsafe_allow_html=True)

    st.divider()
    st.subheader("📊 FOF Collection Summary")
    investors, lp_calls, payments = get_investors(), get_lp_calls(), get_lp_payments()
    total_fund_commitment = sum(inv.get("commitment", 0) for inv in investors)
    col_sum1, col_sum2 = st.columns([1, 3])
    with col_sum1: st.metric("Total LP Commitments", format_currency(total_fund_commitment, "$"))
    with col_sum2:
        if lp_calls:
            summary_data = []
            for c in lp_calls:
                total_called_amount = total_fund_commitment * (c["call_pct"] / 100.0)
                paid_commit = sum(inv.get("commitment", 0) for inv in investors if next((p for p in payments if p["lp_call_id"] == c["id"] and p["investor_id"] == inv["id"]), {}).get("is_paid"))
                total_paid_amount = paid_commit * (c["call_pct"] / 100.0)
                summary_data.append({"Call": f"{c['call_date']} ({c['call_pct']}%)", "Required": format_currency(total_called_amount, "$"), "Received": format_currency(total_paid_amount, "$"), "Outstanding": format_currency(total_called_amount - total_paid_amount, "$")})
            st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)

def show_investors():
    st.title("👥 Manage Investors & FOF Calls")
    sb = get_supabase()
    investors, lp_calls, payments = get_investors(), get_lp_calls(), get_lp_payments()

    col_add, col_manage = st.columns(2)
    with col_add:
        with st.expander("➕ Add Investor"):
            inv_name = st.text_input("Name")
            inv_commit = st.number_input("Commitment ($)", min_value=0.0)
            if st.button("Save Investor"):
                sb.table("investors").insert({"name": inv_name, "commitment": inv_commit}).execute()
                clear_cache_and_rerun()
    with col_manage:
        with st.expander("⚙️ Manage Existing"):
            for inv in investors:
                c1, c2, c3 = st.columns([3, 2, 1])
                with c1: st.write(inv['name'])
                with c2: st.write(format_currency(inv.get("commitment", 0), "$"))
                with c3:
                    if st.button("🗑️", key=f"del_{inv['id']}"):
                        sb.table("investors").delete().eq("id", inv["id"]).execute()
                        clear_cache_and_rerun()

    st.divider()
    st.markdown("### 📋 Investor Payments Status")
    if investors:
        data, col_mapping = [], {}
        for inv in investors:
            row = {"id": inv["id"], "Investor": inv["name"], "Commitment": format_currency(inv.get("commitment", 0), "$")}
            for c in lp_calls:
                col_name = f"{c['call_date']} ({c['call_pct']}%)"
                col_mapping[col_name] = c
                payment = next((p for p in payments if p["lp_call_id"] == c["id"] and p["investor_id"] == inv["id"]), None)
                row[col_name] = payment["is_paid"] if payment else False
            data.append(row)
        
        edited_df = st.data_editor(pd.DataFrame(data), column_config={"id": None}, disabled=["Investor", "Commitment"], hide_index=True, use_container_width=True)
        if st.button("💾 Save Payment Statuses", type="primary"):
            for _, row in edited_df.iterrows():
                inv_id = row["id"]
                for col_name, c in col_mapping.items():
                    if col_name in row:
                        is_paid = bool(row[col_name])
                        existing = [p for p in payments if p["lp_call_id"] == c["id"] and p["investor_id"] == inv_id]
                        if existing: sb.table("lp_payments").update({"is_paid": is_paid}).eq("id", existing[0]["id"]).execute()
                        else: sb.table("lp_payments").insert({"lp_call_id": c["id"], "investor_id": inv_id, "is_paid": is_paid}).execute()
            clear_cache_and_rerun()

    st.divider()
    st.markdown("### ➕ Manage LP Capital Calls")
    with st.form("new_lp_call"):
        c1, c2 = st.columns(2)
        with c1: new_call_date = st.date_input("Call Date")
        with c2: new_call_pct = st.number_input("Percentage (%)", min_value=0.0)
        if st.form_submit_button("Add LP Call"):
            sb.table("lp_calls").insert({"call_date": str(new_call_date), "call_pct": new_call_pct}).execute()
            clear_cache_and_rerun()

def show_portfolio():
    st.title("📁 Portfolio")
    with st.expander("➕ Add New Fund"):
        with st.form("add_fund"):
            c1, c2 = st.columns(2)
            with c1:
                new_name = st.text_input("Name")
                new_manager = st.text_input("Manager")
                new_strategy = st.selectbox("Strategy", ["Growth", "VC", "Tech", "Niche", "Special Situations", "Mid-Market Buyout"])
            with c2:
                new_commitment = st.number_input("Commitment ($/€ Exact Amount)", min_value=0.0)
                new_currency = st.selectbox("Currency", ["USD", "EUR"])
                new_date = st.date_input("Date")
            if st.form_submit_button("Save"):
                get_supabase().table("funds").insert({"name": new_name, "manager": new_manager, "strategy": new_strategy, "commitment": new_commitment, "currency": new_currency, "investment_date": str(new_date), "status": "active"}).execute()
                clear_cache_and_rerun()

    funds = get_funds()
    if funds:
        tabs = st.tabs([f["name"] for f in funds])
        for i, fund in enumerate(funds):
            with tabs[i]: show_fund_detail(fund)

def show_fund_detail(fund):
    calls = get_capital_calls(fund["id"])
    dists = get_distributions(fund["id"])
    commitment = float(fund.get("commitment") or 0)
    total_called = sum(c.get("amount") or 0 for c in calls if not c.get("is_future"))
    total_dist = sum(d.get("amount") or 0 for d in dists)
    sym = "€" if fund.get("currency") == "EUR" else "$"

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Commitment", format_currency(commitment, sym))
    with c2: st.metric("Total Called", format_currency(total_called, sym), f"{total_called/commitment*100:.1f}%" if commitment else "—")
    with c3: st.metric("Uncalled", format_currency(commitment - total_called, sym))
    with c4: st.metric("Distributed", format_currency(total_dist, sym))

    t1, t2, t3 = st.tabs(["📞 Calls", "💰 Distributions", "📊 Performance"])
    with t1:
        for c in calls:
            with st.expander(f"Call #{c['call_number']} | {c.get('payment_date','')} | {format_currency(c.get('amount',0), sym)}"):
                st.write(f"Investments: {format_currency(c.get('investments',0), sym)}")
                if st.button("Delete", key=f"d_c_{c['id']}"): get_supabase().table("capital_calls").delete().eq("id", c["id"]).execute(); clear_cache_and_rerun()
        with st.form(f"add_call_{fund['id']}"):
            call_num = st.number_input("Number", min_value=1)
            call_date = st.date_input("Date")
            amount = st.number_input("Amount", min_value=0.0)
            if st.form_submit_button("Save"):
                get_supabase().table("capital_calls").insert({"fund_id": fund["id"], "call_number": call_num, "call_date": str(call_date), "amount": amount}).execute()
                clear_cache_and_rerun()
    with t2:
        for d in dists:
            with st.expander(f"Dist #{d['dist_number']} | {d.get('dist_date','')} | {format_currency(d.get('amount',0), sym)}"):
                if st.button("Delete", key=f"d_d_{d['id']}"): get_supabase().table("distributions").delete().eq("id", d["id"]).execute(); clear_cache_and_rerun()
        with st.form(f"add_dist_{fund['id']}"):
            dist_num = st.number_input("Number", min_value=1)
            dist_date = st.date_input("Date")
            amount = st.number_input("Amount", min_value=0.0)
            dist_type = st.selectbox("Type", ["Income", "Capital"])
            if st.form_submit_button("Save"):
                get_supabase().table("distributions").insert({"fund_id": fund["id"], "dist_number": dist_num, "dist_date": str(dist_date), "amount": amount, "dist_type": dist_type.lower()}).execute()
                clear_cache_and_rerun()

def show_pipeline():
    st.title("🔍 Pipeline")
    with st.expander("➕ Add Pipeline Fund"):
        with st.form("add_pipe"):
            name = st.text_input("Name")
            target = st.number_input("Target Commitment", min_value=0.0)
            currency = st.selectbox("Currency", ["USD", "EUR"])
            if st.form_submit_button("Save"):
                res = get_supabase().table("pipeline_funds").insert({"name": name, "target_commitment": target, "currency": currency}).execute()
                try: get_supabase().rpc("create_default_gantt_tasks", {"p_fund_id": res.data[0]["id"]}).execute()
                except: pass
                clear_cache_and_rerun()

    for p in get_pipeline_funds():
        with st.expander(f"{p['name']} | Target: {format_currency(p.get('target_commitment',0), '$' if p['currency']=='USD' else '€')}"):
            tasks = get_gantt_tasks(p["id"])
            if tasks:
                import plotly.graph_objects as go
                STATUS_CFG = {"todo": "⬜ To Do", "in_progress": "🔄 In Progress", "done": "✅ Done", "blocked": "🚫 Blocked"}
                
                # Render tasks UI
                for t in tasks:
                    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
                    with c1: new_name = st.text_input("Task", value=t["task_name"], key=f"t_{t['id']}")
                    with c2: st.write(t["start_date"])
                    with c3: new_ui_status = st.selectbox("Status", list(STATUS_CFG.values()), index=list(STATUS_CFG.keys()).index(t.get("status", "todo")), key=f"s_{t['id']}")
                    with c4:
                        if st.button("🗑️", key=f"del_t_{t['id']}"): get_supabase().table("gantt_tasks").delete().eq("id", t["id"]).execute(); clear_cache_and_rerun()
                    
                    new_status = list(STATUS_CFG.keys())[list(STATUS_CFG.values()).index(new_ui_status)]
                    if new_status != t.get("status") or new_name != t["task_name"]:
                        get_supabase().table("gantt_tasks").update({"status": new_status, "task_name": new_name}).eq("id", t["id"]).execute()
                        clear_cache_and_rerun()

def show_reports():
    st.title("📈 Reports")
    funds = get_funds()
    if funds:
        f_dict = {f["name"]: f["id"] for f in funds}
        sel = st.selectbox("Select Fund", list(f_dict.keys()))
        reps = get_quarterly_reports(f_dict[sel])
        st.dataframe(pd.DataFrame(reps) if reps else pd.DataFrame([{"Message": "No reports"}]), hide_index=True)

if __name__ == "__main__": main()
