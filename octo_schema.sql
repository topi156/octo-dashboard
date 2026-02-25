-- ============================================
-- OCTO FUND DASHBOARD - Supabase Schema
-- ============================================

-- קרנות פעילות (portfolio)
CREATE TABLE funds (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    manager TEXT,
    vintage INTEGER,
    strategy TEXT,  -- PE / Credit / Infrastructure / Real Estate / Hedge
    currency TEXT DEFAULT 'USD',
    commitment NUMERIC,  -- סכום התחייבות
    status TEXT DEFAULT 'active',  -- active / realized / written_off
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- קריאות הון
CREATE TABLE capital_calls (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    fund_id UUID REFERENCES funds(id) ON DELETE CASCADE,
    call_number INTEGER,
    call_date DATE,        -- תאריך קבלה
    payment_date DATE,     -- תאריך תשלום
    amount NUMERIC,
    investments NUMERIC,   -- רכיב השקעות
    fund_expenses NUMERIC, -- הוצאות קרן
    mgmt_fee NUMERIC,      -- דמי ניהול
    gp_contribution NUMERIC, -- GP deemed contribution
    is_future BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- חלוקות
CREATE TABLE distributions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    fund_id UUID REFERENCES funds(id) ON DELETE CASCADE,
    dist_number INTEGER,
    dist_date DATE,
    amount NUMERIC,
    dist_type TEXT,  -- income / capital / recycle
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- דוחות רבעוניים
CREATE TABLE quarterly_reports (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    fund_id UUID REFERENCES funds(id) ON DELETE CASCADE,
    quarter INTEGER,  -- 1-4
    year INTEGER,
    report_date DATE,
    nav NUMERIC,
    tvpi NUMERIC,
    dpi NUMERIC,
    rvpi NUMERIC,
    irr NUMERIC,
    called_to_date NUMERIC,
    distributed_to_date NUMERIC,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(fund_id, quarter, year)
);

-- קרנות pipeline (עתידיות)
CREATE TABLE pipeline_funds (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    manager TEXT,
    strategy TEXT,
    currency TEXT DEFAULT 'USD',
    target_commitment NUMERIC,
    target_close_date DATE,
    fund_size NUMERIC,
    status TEXT DEFAULT 'under_review',  -- under_review / due_diligence / approved / rejected
    priority TEXT DEFAULT 'medium',  -- high / medium / low
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- משימות גאנט לקרנות pipeline
CREATE TABLE gantt_tasks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    pipeline_fund_id UUID REFERENCES pipeline_funds(id) ON DELETE CASCADE,
    category TEXT,  -- legal / tax / analysis / admin
    task_name TEXT NOT NULL,
    assigned_to TEXT,
    start_date DATE,
    due_date DATE,
    completed_date DATE,
    status TEXT DEFAULT 'todo',  -- todo / in_progress / done / blocked
    priority TEXT DEFAULT 'medium',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- נתוני בסיס - הקרנות הקיימות מהאקסל
-- ============================================

INSERT INTO funds (name, manager, currency, commitment, status) VALUES
('Thrive Partners X Growth', 'Thrive Capital', 'USD', 1714286, 'active'),
('Thrive', 'Thrive Capital', 'USD', NULL, 'active'),
('Triton', 'Triton', 'EUR', 5000000, 'active');

-- Call 1 של Thrive Partners X Growth (מהאקסל)
INSERT INTO capital_calls (
    fund_id, call_number, call_date, payment_date,
    amount, investments, fund_expenses, mgmt_fee, gp_contribution
)
SELECT 
    id, 1, '2026-02-09', '2026-02-24',
    292670, 275139, 5503, 6476, 5552
FROM funds WHERE name = 'Thrive Partners X Growth';
