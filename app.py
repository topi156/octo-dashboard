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
    """Extract text from PDF using pymupdf."""
    import fitz  # pymupdf
    import io
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    # Limit to first 8000 chars to avoid token limits
    return text[:8000]

def analyze_pdf_with_ai(pdf_bytes: bytes) -> dict:
    pdf_text = extract_pdf_text(pdf_bytes)
    
    prompt = f"""You are a private equity analyst. Analyze this fund presentation text and extract key information.
Return ONLY a valid JSON object with these exact keys (use null if not found):
{{
  "fund_name": "full fund name",
  "manager": "management company name",
  "strategy": "one of: PE, Credit, Infrastructure, Real Estate, Hedge, Venture",
  "fund_size_target": null,
  "fund_size_hard_cap": null,
  "currency": "USD",
  "target_return_moic_low": null,
  "target_return_moic_high": null,
  "target_irr_gross": null,
  "vintage_year": null,
  "mgmt_fee_pct": null,
  "carried_interest_pct": null,
  "preferred_return_pct": null,
  "geographic_focus": null,
  "sector_focus": null,
  "portfolio_companies_target": null,
  "aum_manager": null,
  "key_highlights": null
}}
fund_size_target and fund_size_hard_cap are numbers in millions USD.
target_irr_gross is a number like 25 (for 25%).
aum_manager is in billions.
Return ONLY the JSON, no markdown, no extra text.

FUND PRESENTATION TEXT:
{pdf_text}"""

    payload = {
        "model": "anthropic/claude-3.5-sonnet",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1500
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

# Hebrew RTL + styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;700&display=swap');
    * { font-family: 'Heebo', sans-serif; }
    .main { direction: rtl; }
    .stMarkdown, .stText, h1, h2, h3, p { direction: rtl; text-align: right; }
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460;
        border-radius: 12px;
        padding: 16px;
    }
    [data-testid="stSidebar"] { background: #0f1117; }
    .dashboard-header {
        background: linear-gradient(90deg, #1a1a2e, #0f3460);
        padding: 20px 30px;
        border-radius: 12px;
        margin-bottom: 24px;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# SUPABASE CLIENT
# ============================================

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
    except Exception as e:
        return []

def get_quarterly_reports(fund_id):
    try:
        sb = get_supabase()
        res = sb.table("quarterly_reports").select("*").eq("fund_id", fund_id).order("year,quarter").execute()
        return res.data or []
    except Exception as e:
        return []

def get_pipeline_funds():
    try:
        sb = get_supabase()
        res = sb.table("pipeline_funds").select("*").order("target_close_date").execute()
        return res.data or []
    except Exception as e:
        return []

def get_gantt_tasks(pipeline_fund_id):
    try:
        sb = get_supabase()
        res = sb.table("gantt_tasks").select("*").eq("pipeline_fund_id", pipeline_fund_id).order("start_date").execute()
        return res.data or []
    except Exception as e:
        return []

# ============================================
# AUTHENTICATION
# ============================================

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

# ============================================
# MAIN APP
# ============================================

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

# ============================================
# OVERVIEW PAGE
# ============================================

def show_overview():
    st.markdown("""
    <div class="dashboard-header">
        <h1 style="color:white;margin:0;">📊 Octo Fund Dashboard</h1>
        <p style="color:#94a3b8;margin:4px 0 0 0;">ALT Group | ניהול השקעות אלטרנטיביות</p>
    </div>
    """, unsafe_allow_html=True)

    funds = get_funds()
    pipeline = get_pipeline_funds()

    # KPIs
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
        # Show future capital calls
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

# ============================================
# PORTFOLIO PAGE
# ============================================

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

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("התחייבות", f"{currency_sym}{commitment:,.0f}" if commitment else "—")
    with col2:
        pct = f"{total_called/commitment*100:.1f}%" if commitment > 0 else "—"
        st.metric("סה״כ נקרא", f"{currency_sym}{total_called:,.0f}", pct)
    with col3:
        st.metric("יתרה לא נקראה", f"{currency_sym}{uncalled:,.0f}" if commitment else "—")
    with col4:
        st.metric("סה״כ חולק", f"{currency_sym}{total_dist:,.0f}")

    st.divider()

    tab1, tab2, tab3 = st.tabs(["📞 Capital Calls", "💰 Distributions", "📊 ביצועים"])

    # --- CAPITAL CALLS ---
    with tab1:
        if calls:
            rows = []
            for c in calls:
                rows.append({
                    "Call #": c.get("call_number"),
                    "תאריך קבלה": c.get("call_date", ""),
                    "תאריך תשלום": c.get("payment_date", ""),
                    "סכום": f"{currency_sym}{c.get('amount',0):,.0f}",
                    "השקעות": f"{currency_sym}{c.get('investments',0):,.0f}" if c.get("investments") else "—",
                    "דמי ניהול": f"{currency_sym}{c.get('mgmt_fee',0):,.0f}" if c.get("mgmt_fee") else "—",
                    "עתידי": "🔮" if c.get("is_future") else "✅",
                    "הערות": c.get("notes", ""),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            # Bar chart
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
                        "fund_id": fund["id"],
                        "call_number": call_num,
                        "call_date": str(call_date),
                        "payment_date": str(payment_date),
                        "amount": amount,
                        "investments": investments,
                        "mgmt_fee": mgmt_fee,
                        "fund_expenses": fund_expenses,
                        "gp_contribution": gp_contribution,
                        "is_future": is_future,
                        "notes": notes
                    }).execute()
                    st.success("✅ נשמר!")
                    st.rerun()
                except Exception as e:
                    st.error(f"שגיאה: {e}")

    # --- DISTRIBUTIONS ---
    with tab2:
        if dists:
            rows = [{"Dist #": d.get("dist_number"), "תאריך": d.get("dist_date"), 
                     "סכום": f"{currency_sym}{d.get('amount',0):,.0f}", "סוג": d.get("dist_type","")} for d in dists]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
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
                        "fund_id": fund["id"],
                        "dist_number": dist_num,
                        "dist_date": str(dist_date),
                        "amount": dist_amount,
                        "dist_type": dist_type
                    }).execute()
                    st.success("✅ נשמר!")
                    st.rerun()
                except Exception as e:
                    st.error(f"שגיאה: {e}")

    # --- PERFORMANCE ---
    with tab3:
        if reports:
            rows = [{"שנה": r["year"], "רבעון": f"Q{r['quarter']}", "NAV": r.get("nav"),
                     "TVPI": r.get("tvpi"), "DPI": r.get("dpi"), "IRR %": r.get("irr")} for r in reports]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

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

# ============================================
# PIPELINE PAGE
# ============================================

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

    # PDF UPLOAD & ANALYSIS
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
            
            # Show highlights
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
                            "name": fund_name,
                            "manager": manager,
                            "strategy": strategy,
                            "target_commitment": target_commitment * 1_000_000,
                            "currency": currency,
                            "target_close_date": str(target_close),
                            "priority": priority,
                            "notes": notes
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

    # MANUAL ADD
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
        with st.expander(f"📋 {fund['name']} | {fund.get('strategy','')} | {fund.get('priority','').upper()} | סגירה: {fund.get('target_close_date','')}", expanded=False):
            
            # Action buttons
            col_a, col_b, col_c = st.columns([1, 1, 4])
            with col_a:
                if st.button("✏️ עריכה", key=f"edit_{fid}"):
                    st.session_state[f"editing_{fid}"] = True
            with col_b:
                if st.button("🗑️ מחיקה", key=f"del_{fid}"):
                    st.session_state[f"confirm_delete_{fid}"] = True

            # Confirm delete
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

            # Edit form
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
                                    "name": new_name,
                                    "manager": new_manager,
                                    "strategy": new_strategy,
                                    "target_commitment": new_commitment,
                                    "currency": new_currency,
                                    "priority": new_priority,
                                    "target_close_date": str(new_close),
                                    "notes": new_notes
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
                # Display mode
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
    import plotly.figure_factory as ff
    from datetime import datetime

    categories = {"legal": "🔵 Legal", "tax": "🔴 Tax", "analysis": "🟢 Analysis", "admin": "🟡 Admin"}
    colors = {"🔵 Legal": "#0f3460", "🔴 Tax": "#e94560", "🟢 Analysis": "#0a7c59", "🟡 Admin": "#7c5200"}

    # Status filter
    status_filter = st.multiselect(
        "סטטוס", ["todo", "in_progress", "done", "blocked"],
        default=["todo", "in_progress", "blocked"],
        key=f"filter_{fund['id']}"
    )
    filtered = [t for t in tasks if t.get("status") in status_filter] if status_filter else tasks

    # Gantt
    gantt_tasks = []
    for t in filtered:
        if t.get("start_date") and t.get("due_date"):
            try:
                gantt_tasks.append(dict(
                    Task=t["task_name"],
                    Start=t["start_date"],
                    Finish=t["due_date"],
                    Resource=categories.get(t.get("category",""), t.get("category",""))
                ))
            except:
                pass

    if gantt_tasks:
        try:
            fig = ff.create_gantt(gantt_tasks, colors=colors, index_col="Resource",
                                  show_colorbar=True, group_tasks=False)
            fig.update_layout(height=400, paper_bgcolor='rgba(0,0,0,0)',
                              plot_bgcolor='rgba(0,0,0,0)', font_color='white')
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.warning(f"גאנט לא זמין: {e}")

    # Checklist
    st.markdown("**📋 צ'קליסט משימות**")
    sb = get_supabase()
    for cat, cat_label in categories.items():
        cat_tasks = [t for t in tasks if t.get("category") == cat]
        if not cat_tasks:
            continue
        done = sum(1 for t in cat_tasks if t.get("status") == "done")
        st.markdown(f"**{cat_label}** ({done}/{len(cat_tasks)})")
        for t in cat_tasks:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                status_icon = {"todo": "⬜", "in_progress": "🔄", "done": "✅", "blocked": "🚫"}.get(t.get("status",""), "⬜")
                st.markdown(f"{status_icon} {t['task_name']}")
            with col2:
                st.caption(t.get("due_date", ""))
            with col3:
                new_status = st.selectbox("", ["todo", "in_progress", "done", "blocked"],
                    index=["todo", "in_progress", "done", "blocked"].index(t.get("status","todo")),
                    key=f"task_{t['id']}", label_visibility="collapsed")
                if new_status != t.get("status"):
                    try:
                        sb.table("gantt_tasks").update({"status": new_status}).eq("id", t["id"]).execute()
                        st.rerun()
                    except Exception as e:
                        st.error(f"שגיאה: {e}")

# ============================================
# REPORTS PAGE
# ============================================

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
