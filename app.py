"""
OCTO FUND DASHBOARD - app.py
Main entry point for Streamlit application
"""

import streamlit as st
import hashlib

st.set_page_config(
    page_title="ALT Group | Octo Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# PASSWORD AUTHENTICATION
# ============================================

USERS = {
    "liron": "octo2026",
    "alex": "octo2026",
    "team": "altgroup2026",
}

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_login(username, password):
    username = username.strip().lower()
    if username in USERS and USERS[username] == password:
        return True
    return False

def show_login():
    st.markdown("""
    <style>
        .login-container {
            max-width: 400px;
            margin: 80px auto;
            padding: 40px;
            background: linear-gradient(135deg, #1a1a2e, #16213e);
            border-radius: 16px;
            border: 1px solid #0f3460;
        }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 📊 Octo Fund Dashboard")
        st.markdown("**ALT Group** | Private Capital")
        st.divider()
        username = st.text_input("שם משתמש", placeholder="liron")
        password = st.text_input("סיסמא", type="password", placeholder="••••••••")
        if st.button("כניסה", type="primary", use_container_width=True):
            if check_login(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username.strip().lower()
                st.rerun()
            else:
                st.error("שם משתמש או סיסמא שגויים")

def require_login():
    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        show_login()
        st.stop()

# Hebrew RTL support
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;700&display=swap');
    
    * { font-family: 'Heebo', sans-serif; }
    
    .main { direction: rtl; }
    .stMarkdown, .stText, h1, h2, h3, p { 
        direction: rtl; 
        text-align: right; 
    }
    
    /* Metric cards */
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460;
        border-radius: 12px;
        padding: 16px;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #0f1117;
    }
    
    /* Header */
    .dashboard-header {
        background: linear-gradient(90deg, #1a1a2e, #0f3460);
        padding: 20px 30px;
        border-radius: 12px;
        margin-bottom: 24px;
    }
    
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 500;
    }
    .status-active { background: #1a3a1a; color: #4ade80; }
    .status-pending { background: #3a2a1a; color: #fb923c; }
    .status-done { background: #1a2a3a; color: #60a5fa; }
</style>
""", unsafe_allow_html=True)


def main():
    require_login()

    # Sidebar
    with st.sidebar:
        st.markdown("## 📊 Octo Dashboard")
        st.markdown("**ALT Group** | Private Capital")
        st.divider()
        
        page = st.radio(
            "ניווט",
            [
                "🏠 סקירה כללית",
                "📁 תיק השקעות",
                "🔍 Pipeline",
                "📈 דוחות רבעוניים",
                "⚙️ הגדרות"
            ],
            label_visibility="collapsed"
        )
        
        st.divider()
        st.caption("גרסה 1.0 | פברואר 2026")
        st.divider()
        if st.button("🚪 התנתק", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
    
    # Page routing
    if "סקירה כללית" in page:
        show_overview()
    elif "תיק השקעות" in page:
        show_portfolio()
    elif "Pipeline" in page:
        show_pipeline()
    elif "דוחות" in page:
        show_reports()
    elif "הגדרות" in page:
        show_settings()


def show_overview():
    st.markdown("""
    <div class="dashboard-header">
        <h1 style="color: white; margin: 0;">📊 Octo Fund Dashboard</h1>
        <p style="color: #94a3b8; margin: 4px 0 0 0;">ALT Group | ניהול השקעות אלטרנטיביות</p>
    </div>
    """, unsafe_allow_html=True)
    
    # KPI row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("סה״כ התחייבויות", "$6.7M", help="USD + EUR")
    with col2:
        st.metric("קרנות פעילות", "3")
    with col3:
        st.metric("קרנות Pipeline", "0", help="בתהליך DD")
    with col4:
        st.metric("Calls שבוצעו", "$292K", delta="פברואר 2026")
    
    st.divider()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📋 סטטוס קרנות")
        
        funds_data = [
            {"קרן": "Thrive Partners X Growth", "מטבע": "USD", "התחייבות": "$1,714,286", 
             "נקרא %": "17%", "סטטוס": "פעיל", "תהליך": "הושלם"},
            {"קרן": "Thrive", "מטבע": "USD", "התחייבות": "—", 
             "נקרא %": "—", "סטטוס": "פעיל", "תהליך": "הושלם"},
            {"קרן": "Triton", "מטבע": "EUR", "התחייבות": "€5,000,000", 
             "נקרא %": "0%", "סטטוס": "פעיל", "תהליך": "ממתין"},
        ]
        
        import pandas as pd
        df = pd.DataFrame(funds_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
    
    with col2:
        st.subheader("🔔 אירועים קרובים")
        
        st.markdown("""
        <div style="background:#1a3a1a; border-radius:8px; padding:12px; margin-bottom:8px;">
            <small style="color:#4ade80">24 פברואר 2026</small><br>
            <strong>Thrive Partners X Growth</strong><br>
            <span style="color:#94a3b8">תשלום Call #1 | $292,670</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.info("💡 הוסף תאריכים ל-Calls עתידיים כדי לראות תחזית כאן")


def show_portfolio():
    st.title("📁 תיק השקעות")
    
    fund_tabs = st.tabs([
        "Thrive Partners X Growth",
        "Thrive",
        "Triton"
    ])
    
    with fund_tabs[0]:
        show_fund_detail_thrive()
    
    with fund_tabs[1]:
        st.info("טרם הוזנו נתונים לקרן זו")
    
    with fund_tabs[2]:
        st.info("טרם הוזנו נתונים לקרן זו")


def show_fund_detail_thrive():
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("התחייבות", "$1,714,286")
    with col2:
        st.metric("סה״כ נקרא", "$292,670", "17.1%")
    with col3:
        st.metric("יתרה לא נקראה", "$1,421,616")
    
    st.divider()
    
    tab1, tab2, tab3 = st.tabs(["📞 Capital Calls", "💰 Distributions", "📊 ביצועים"])
    
    with tab1:
        import pandas as pd
        calls_df = pd.DataFrame([{
            "Call #": 1,
            "תאריך קבלה": "09/02/2026",
            "תאריך תשלום": "24/02/2026",
            "סכום": "$292,670",
            "השקעות": "$275,139",
            "הוצאות": "$5,503",
            "דמי ניהול": "$6,476",
            "GP Contribution": "$5,552",
            "סטטוס": "✅ שולם"
        }])
        st.dataframe(calls_df, use_container_width=True, hide_index=True)
        
        st.button("➕ הוסף Capital Call", type="primary")
    
    with tab2:
        st.info("טרם בוצעו חלוקות")
        st.button("➕ הוסף Distribution", type="primary")
    
    with tab3:
        st.info("דוחות רבעוניים יוצגו כאן לאחר הזנה")


def show_pipeline():
    st.title("🔍 קרנות Pipeline")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption("קרנות בתהליך בחינה והשקעה")
    with col2:
        if st.button("➕ הוסף קרן Pipeline", type="primary"):
            st.session_state.show_add_pipeline = True
    
    st.info("אין קרנות pipeline כרגע. לחץ 'הוסף קרן Pipeline' להתחיל.")
    
    # Example of what a pipeline card looks like
    with st.expander("👁️ דוגמה לתצוגת קרן Pipeline"):
        st.markdown("### Example Fund")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("יעד השקעה", "$2,000,000")
        with col2:
            st.metric("תאריך סגירה", "Q2 2026")
        with col3:
            st.metric("התקדמות", "45%")
        
        show_sample_gantt()


def show_sample_gantt():
    import pandas as pd
    import plotly.figure_factory as ff
    from datetime import datetime, timedelta
    
    today = datetime.now()
    
    tasks = [
        dict(Task="קריאת LPA", Start=today, Finish=today+timedelta(days=7), Resource="Legal"),
        dict(Task="KYC/AML", Start=today, Finish=today+timedelta(days=10), Resource="Legal"),
        dict(Task="בחינת מבנה - KPMG", Start=today+timedelta(days=7), Finish=today+timedelta(days=21), Resource="Tax"),
        dict(Task="ניתוח פנימי", Start=today, Finish=today+timedelta(days=14), Resource="Analysis"),
        dict(Task="IC Memo", Start=today+timedelta(days=14), Finish=today+timedelta(days=21), Resource="Analysis"),
        dict(Task="הצבעת IC", Start=today+timedelta(days=21), Finish=today+timedelta(days=23), Resource="Admin"),
        dict(Task="חתימה", Start=today+timedelta(days=35), Finish=today+timedelta(days=37), Resource="Legal"),
    ]
    
    colors = {
        'Legal': '#0f3460',
        'Tax': '#e94560',
        'Analysis': '#0a7c59',
        'Admin': '#7c3f00'
    }
    
    try:
        fig = ff.create_gantt(
            tasks, 
            colors=colors, 
            index_col='Resource',
            show_colorbar=True,
            group_tasks=False,
            title="גאנט - תהליך Due Diligence"
        )
        fig.update_layout(
            height=350,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='white'
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        st.info("גאנט יוצג כאן")


def show_reports():
    st.title("📈 דוחות רבעוניים")
    
    st.info("הוסף דוחות רבעוניים כשיגיעו מהקרנות. המערכת תחשב TVPI, DPI, IRR אוטומטית.")
    
    if st.button("➕ הוסף דוח רבעוני", type="primary"):
        with st.form("add_report"):
            col1, col2 = st.columns(2)
            with col1:
                fund = st.selectbox("קרן", ["Thrive Partners X Growth", "Thrive", "Triton"])
                year = st.number_input("שנה", value=2025, min_value=2020, max_value=2030)
                quarter = st.selectbox("רבעון", [1, 2, 3, 4])
            with col2:
                nav = st.number_input("NAV", min_value=0.0)
                tvpi = st.number_input("TVPI", min_value=0.0, step=0.01)
                irr = st.number_input("IRR %", min_value=-100.0, step=0.1)
            
            if st.form_submit_button("שמור"):
                st.success("הדוח נשמר!")


def show_settings():
    st.title("⚙️ הגדרות")
    
    st.subheader("חיבור Supabase")
    st.text_input("Supabase URL", placeholder="https://xxx.supabase.co", type="password")
    st.text_input("Supabase Key", placeholder="eyJ...", type="password")
    
    if st.button("שמור הגדרות"):
        st.success("✅ הגדרות נשמרו")
    
    st.divider()
    st.subheader("ייצוא נתונים")
    st.button("📥 ייצוא לאקסל")
    st.button("📄 ייצוא ל-PDF")


if __name__ == "__main__":
    main()
