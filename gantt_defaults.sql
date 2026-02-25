-- ============================================
-- GANTT DEFAULT TASKS - לשימוש בכל קרן pipeline חדשה
-- מריצים כ-function כשמוסיפים קרן
-- ============================================

-- Legal Tasks
-- 1. בחינה ראשונית של מסמכי הקרן
-- 2. קריאת LPA מלאה
-- 3. בחינת side letter
-- 4. KYC על המנהל
-- 5. AML screening
-- 6. מכתב מצג (Subscription Agreement)
-- 7. חתימה סופית

-- Tax Tasks (מול KPMG)
-- 1. בחינת מבנה הקרן
-- 2. בחינת blockers (ECI / UBTI)
-- 3. בחינת מס ישראלי - סיווג ההשקעה
-- 4. חוות דעת KPMG
-- 5. הגשת טפסים

-- Internal Analysis
-- 1. קריאת IM / Deck ראשונית
-- 2. ניתוח אסטרטגיה
-- 3. ניתוח track record
-- 4. peer comparison
-- 5. מודל תזרים (cash flow model)
-- 6. IC memo
-- 7. הצבעת IC

-- יצירת function לsupabase שמוסיפה את כל המשימות אוטומטית:
CREATE OR REPLACE FUNCTION create_default_gantt_tasks(
    p_fund_id UUID,
    p_start_date DATE DEFAULT CURRENT_DATE
)
RETURNS void AS $$
DECLARE
    tasks JSONB := '[
        {"category": "legal", "task_name": "בחינה ראשונית של מסמכי הקרן", "days_from_start": 0, "duration": 3, "priority": "high"},
        {"category": "legal", "task_name": "קריאת LPA מלאה", "days_from_start": 3, "duration": 7, "priority": "high"},
        {"category": "legal", "task_name": "בחינת Side Letter", "days_from_start": 10, "duration": 5, "priority": "medium"},
        {"category": "legal", "task_name": "KYC על המנהל", "days_from_start": 0, "duration": 10, "priority": "high"},
        {"category": "legal", "task_name": "AML Screening", "days_from_start": 0, "duration": 7, "priority": "high"},
        {"category": "legal", "task_name": "בחינת Subscription Agreement", "days_from_start": 14, "duration": 5, "priority": "high"},
        {"category": "legal", "task_name": "חתימה סופית", "days_from_start": 55, "duration": 1, "priority": "high"},
        {"category": "tax", "task_name": "בחינת מבנה הקרן - KPMG", "days_from_start": 7, "duration": 10, "priority": "high"},
        {"category": "tax", "task_name": "בחינת Blockers (ECI/UBTI)", "days_from_start": 10, "duration": 7, "priority": "high"},
        {"category": "tax", "task_name": "ניתוח מס ישראלי - סיווג ההשקעה", "days_from_start": 14, "duration": 7, "priority": "medium"},
        {"category": "tax", "task_name": "קבלת חוות דעת KPMG", "days_from_start": 25, "duration": 14, "priority": "high"},
        {"category": "tax", "task_name": "הגשת טפסים ואישורים", "days_from_start": 45, "duration": 10, "priority": "medium"},
        {"category": "analysis", "task_name": "קריאת IM / Deck ראשונית", "days_from_start": 0, "duration": 3, "priority": "high"},
        {"category": "analysis", "task_name": "ניתוח אסטרטגיה והשוק", "days_from_start": 3, "duration": 7, "priority": "high"},
        {"category": "analysis", "task_name": "ניתוח Track Record", "days_from_start": 7, "duration": 7, "priority": "high"},
        {"category": "analysis", "task_name": "Peer Comparison", "days_from_start": 14, "duration": 5, "priority": "medium"},
        {"category": "analysis", "task_name": "מודל תזרים (Cash Flow Model)", "days_from_start": 14, "duration": 10, "priority": "high"},
        {"category": "analysis", "task_name": "כתיבת IC Memo", "days_from_start": 28, "duration": 7, "priority": "high"},
        {"category": "analysis", "task_name": "הצגה והצבעת IC", "days_from_start": 42, "duration": 3, "priority": "high"}
    ]';
    task JSONB;
BEGIN
    FOR task IN SELECT * FROM jsonb_array_elements(tasks)
    LOOP
        INSERT INTO gantt_tasks (
            pipeline_fund_id, category, task_name,
            start_date, due_date, status, priority
        ) VALUES (
            p_fund_id,
            task->>'category',
            task->>'task_name',
            p_start_date + (task->>'days_from_start')::INTEGER,
            p_start_date + (task->>'days_from_start')::INTEGER + (task->>'duration')::INTEGER,
            'todo',
            task->>'priority'
        );
    END LOOP;
END;
$$ LANGUAGE plpgsql;
