# 📊 Octo Fund Dashboard
### ALT Group | Private Capital Management

---

## 🚀 הקמה מהירה (30 דקות)

### שלב 1 – Supabase (10 דקות)
1. כנס ל-https://supabase.com → **New Project**
2. תן שם: `octo-dashboard`
3. בחר region: **EU West** (Frankfurt)
4. לך ל-**SQL Editor** והרץ:
   - `octo_schema.sql` (מבנה הטבלאות)
   - `gantt_defaults.sql` (פונקציית Gantt)
5. לך ל-**Settings → API** → העתק `URL` ו-`anon key`

### שלב 2 – GitHub (5 דקות)
```bash
git init octo-dashboard
cd octo-dashboard
# העתק את כל הקבצים לתוך התיקייה
git add .
git commit -m "Initial commit"
git push origin main
```

### שלב 3 – Streamlit Cloud (5 דקות)
1. כנס ל-https://share.streamlit.io
2. **New app** → חבר GitHub repo
3. לך ל-**Advanced settings → Secrets** והוסף:
```toml
OPENROUTER_API_KEY = ""

[supabase]
url = "https://xxx.supabase.co"
key = "your-supabase-anon-key"
```
4. Use the Supabase `anon key` unless there is an explicit server-side reason to use `service_role`.
5. Never commit `.streamlit/secrets.toml`.
6. Never commit a Supabase `service_role` key.
7. Streamlit Cloud secrets must use the same TOML structure shown above.
8. **Deploy!**

### שלב 4 – הזנת נתונים (10 דקות)
- כנס לדשבורד
- הוסף נתוני הקרנות הקיימות
- הנתונים מהאקסל כבר מוזנים אוטומטית

---

## 📁 מבנה הפרויקט

```
octo-dashboard/
├── app.py                    ← Main app (נגיעות ראשיות כאן)
├── requirements.txt          ← Dependencies
├── .streamlit/
│   └── secrets.toml          - Local secrets only; never commit
├── sql/
│   ├── octo_schema.sql       ← Database schema
│   └── gantt_defaults.sql    ← Default tasks function
└── .gitignore
```

---

## 🔧 הוספת נתונים

### הוספת Capital Call:
```python
supabase.table('capital_calls').insert({
    'fund_id': 'FUND_UUID',
    'call_number': 2,
    'call_date': '2026-05-01',
    'payment_date': '2026-05-15',
    'amount': 250000,
    'investments': 230000,
    'mgmt_fee': 20000
}).execute()
```

### הוספת קרן Pipeline עם Gantt אוטומטי:
```sql
-- מוסיף קרן
INSERT INTO pipeline_funds (name, target_close_date) 
VALUES ('New Fund Name', '2026-06-30')
RETURNING id;

-- מוסיף את כל משימות הGantt אוטומטית
SELECT create_default_gantt_tasks('FUND_UUID', CURRENT_DATE);
```

---

## 📊 עמודי הדשבורד

| עמוד | תוכן |
|------|------|
| 🏠 סקירה כללית | KPIs, אירועים קרובים, סטטוס כללי |
| 📁 תיק השקעות | כל קרן עם Calls, Distributions, ביצועים |
| 🔍 Pipeline | קרנות עתידיות + גאנט + צ'קליסטים |
| 📈 דוחות רבעוניים | NAV, TVPI, DPI, IRR לכל קרן |

---

## 🤖 Prompts לבניית שלבים הבאים

### לChatGPT – עמוד קרן מלא:
```
Build a complete Streamlit page for a PE fund detail view.
Use supabase-py client. The page should show:
1. Fund header with KPIs (commitment, called%, NAV, TVPI)
2. Capital calls timeline (table + bar chart with plotly)  
3. Distributions table
4. Quarterly performance chart (TVPI, DPI, RVPI over time)
5. Add/edit forms for each section
Include Hebrew RTL CSS. Return complete working Python code.
Tables: capital_calls, distributions, quarterly_reports (see schema in context).
```

### לGemini – צ'קליסט מפורט:
```
Create a comprehensive due diligence checklist for Israeli LP 
investing in a US private equity fund. Include:
1. LPA review (20+ items)
2. KYC/AML per Israeli regulation
3. KPMG tax review (ECI, UBTI, blockers, Israeli tax)
4. Internal investment analysis framework
Format as JSON with: category, task_name, description, required_docs
```

### לClaude – Gantt Chart מתקדם:
```
Build a Streamlit Gantt component using plotly that:
- Shows tasks by category (Legal/Tax/Analysis) with colors
- Has a progress bar showing days to target close date
- Allows drag-to-update status (todo/in_progress/done)
- Shows critical path
Use the gantt_tasks table schema.
```
