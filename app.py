"""
OCTO FUND DASHBOARD v9.4.16 - app.py
Master Version: Fixed Indentations, Fully Integrated Fund Expenses & Net IRR
"""

import streamlit as st
import hashlib
import pandas as pd
import json
import requests
import io
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
from collections import defaultdict
from supabase import create_client, Client

OPENROUTER_API_KEY = st.secrets.get("OPENROUTER_API_KEY", "")
HARDCODED_ALLOWED_EMAILS = set()

def get_allowed_emails() -> set[str]:
    allowed_emails = set(HARDCODED_ALLOWED_EMAILS)
    auth_secrets = st.secrets.get("auth", {})
    secret_emails = auth_secrets.get("allowed_emails", []) if auth_secrets else []
    allowed_emails.update(str(email).strip().lower() for email in secret_emails if str(email).strip())
    return allowed_emails

def is_email_allowed(email: str) -> bool:
    return email.strip().lower() in get_allowed_emails()

def format_currency(amount: float, currency_sym: str = "$") -> str:
    if amount is None or amount == 0:
        return "—"
    if 0 < amount <= 1000: 
        return f"{currency_sym}{amount:,.2f}M"
    if amount >= 1_000_000:
        return f"{currency_sym}{amount/1_000_000:,.2f}M"
    formatted = f"{currency_sym}{amount:,.0f}"
    return formatted

def calculate_xirr(cash_flows):
    """Calculates XIRR for an array of (date, amount) tuples."""
    if not cash_flows: return None
    
    cf_dict = defaultdict(float)
    for d, amt in cash_flows:
        cf_dict[d] += amt
    
    cf_list = [(d, a) for d, a in cf_dict.items() if abs(a) > 0.01]
    if not cf_list: return None
    
    has_pos = any(a > 0 for _, a in cf_list)
    has_neg = any(a < 0 for _, a in cf_list)
    if not (has_pos and has_neg): return None
    
    cf_list.sort(key=lambda x: x[0])
    d0 = cf_list[0][0]
    
    # PE Industry Standard: If portfolio is younger than 1 year, IRR is Not Meaningful (NM)
    if (date.today() - d0).days < 365:
        return "NM"
    
    def xnpv(rate):
        if rate <= -1.0: return float('inf')
        return sum([a / ((1.0 + rate) ** ((d - d0).days / 365.25)) for d, a in cf_list])
        
    rate = 0.1
    for _ in range(100):
        val = xnpv(rate)
        val_delta = xnpv(rate + 0.0001)
        deriv = (val_delta - val) / 0.0001
        if deriv == 0: break
        rate_next = rate - val / deriv
        if abs(rate_next - rate) < 1e-6:
            return rate_next
        rate = rate_next
    return None

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

IMPORTANT: Fund size in billions -> convert to millions. E.g. $2.5B = 2500.
Return ONLY the JSON, no markdown, no extra text.

FUND PRESENTATION TEXT:
{pdf_text}"""

    payload = {
        "model": "anthropic/claude-sonnet-4",
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

def calculate_fund_metrics(fund, calls, dists):
    commitment = float(fund.get("commitment") or 0)
    if 0 < commitment <= 1000:
        commitment *= 1_000_000
    
    total_called = 0
    total_equalisation_interest = 0
    total_dist = sum(float(d.get("amount") or 0) for d in dists)
    
    for c in calls:
        if c.get("is_future"):
            continue
            
        tx_type = c.get("transaction_type", "call")
        amount = float(c.get("amount") or 0)
        investments = float(c.get("investments") or 0)
        eq_interest = float(c.get("equalisation_interest") or 0)
        
        affects_called = c.get("affects_called")
        if affects_called is None:
            affects_called = (tx_type == "repayment")
            
        impact = investments if investments > 0 else amount
            
        if tx_type == "call":
            total_called += impact
            total_equalisation_interest += eq_interest
        elif tx_type == "repayment":
            if affects_called:
                total_called -= impact
        elif tx_type == "distribution":
            total_dist += amount
            if affects_called:
                total_called -= impact
    
    uncalled = commitment - total_called
    
    return {
        "commitment": commitment,
        "total_called": total_called,
        "total_distributed": total_dist,
        "uncalled": uncalled,
        "equalisation_interest": total_equalisation_interest
    }

CAPITAL_CALL_COMPONENT_TYPES = [
    "Gross capital call",
    "Recallable repayment",
    "Non-recallable distribution",
    "Realised gain distribution",
    "Equalisation interest outside commitment"
]
BUNDLE_COMPONENT_ROW_LIMIT = 15

def normalize_amount(value) -> float:
    if value is None:
        return 0.0
    try:
        text = str(value).replace(",", "").replace("$", "").replace("€", "").strip()
        if text.startswith("(") and text.endswith(")"):
            text = text[1:-1]
        return abs(float(text))
    except Exception:
        return 0.0

def parse_ai_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value).split("T")[0], "%Y-%m-%d").date()
    except Exception:
        return None

def normalize_ai_notice_type(value: str) -> str:
    notice_type = str(value or "simple_capital_call").strip().lower().replace("-", "_").replace(" ", "_")
    if notice_type in ["net_capital_call", "equalisation_bundle", "net_capital_call_equalisation_bundle"]:
        return "net_capital_call_bundle"
    if notice_type not in ["simple_capital_call", "distribution", "net_capital_call_bundle"]:
        return "simple_capital_call"
    return notice_type

def normalize_ai_component_type(value: str) -> str:
    component_type = str(value or "").strip()
    if component_type in CAPITAL_CALL_COMPONENT_TYPES:
        return component_type
    lookup = {
        "gross call": "Gross capital call",
        "capital call": "Gross capital call",
        "gross capital call": "Gross capital call",
        "recallable repayment": "Recallable repayment",
        "recallable distribution": "Recallable repayment",
        "non-recallable distribution": "Non-recallable distribution",
        "non recallable distribution": "Non-recallable distribution",
        "realised gain distribution": "Realised gain distribution",
        "realized gain distribution": "Realised gain distribution",
        "equalisation interest": "Equalisation interest outside commitment",
        "equalization interest": "Equalisation interest outside commitment",
        "equalisation interest outside commitment": "Equalisation interest outside commitment",
        "equalization interest outside commitment": "Equalisation interest outside commitment"
    }
    return lookup.get(component_type.lower(), "Gross capital call")

def ai_result_mentions_retained_amount(ai_result: dict) -> bool:
    retained_terms = ["retained", "retain", "withheld", "offset", "netted"]
    text_parts = [str(w) for w in ai_result.get("warnings", []) if w]
    reconciliation = ai_result.get("reconciliation", {})
    if isinstance(reconciliation, dict):
        text_parts.extend(str(value) for value in reconciliation.values() if value)
    components = ai_result.get("components", [])
    if isinstance(components, list):
        for component in components:
            if isinstance(component, dict):
                text_parts.append(str(component.get("description") or ""))
                text_parts.append(str(component.get("component_type") or ""))
    combined_text = " ".join(text_parts).lower()
    return any(term in combined_text for term in retained_terms)

def ai_result_maps_retained_amount(ai_result: dict) -> bool:
    components = ai_result.get("components", [])
    if not isinstance(components, list):
        return False
    for component in components:
        if isinstance(component, dict) and "retain" in str(component.get("description") or "").lower():
            return True
    return False

def apply_capital_call_ai_prefill(fund, calls, ai_result: dict) -> list[str]:
    fund_id = fund["id"]
    warnings = [str(w) for w in ai_result.get("warnings", []) if str(w).strip()]
    notice_type = normalize_ai_notice_type(ai_result.get("notice_type"))
    call_number = int(normalize_amount(ai_result.get("call_number")) or (len(calls) + 1))
    call_date = parse_ai_date(ai_result.get("call_date")) or date.today()
    payment_date = parse_ai_date(ai_result.get("payment_date")) or date.today()

    if notice_type == "net_capital_call_bundle":
        st.session_state[f"call_entry_mode_{fund_id}"] = "Net Capital Call / Equalisation Bundle"
        st.session_state[f"cc_ai_result_{fund_id}"] = {}
        st.session_state[f"bundle_call_num_{fund_id}"] = call_number
        st.session_state[f"bundle_call_date_{fund_id}"] = call_date
        st.session_state[f"bundle_payment_date_{fund_id}"] = payment_date
        st.session_state[f"bundle_expected_wire_{fund_id}"] = normalize_amount(ai_result.get("final_wire_amount"))
        st.session_state[f"bundle_ai_expected_wire_set_{fund_id}"] = ai_result.get("final_wire_amount") is not None
        fund_name = str(fund.get("name") or "").strip()
        prefix = "Net Capital Call / Equalisation Bundle"
        st.session_state[f"bundle_note_prefix_{fund_id}"] = f"{prefix} - {fund_name}" if fund_name else prefix

        components = ai_result.get("components", [])
        if not isinstance(components, list):
            components = []
        if len(components) > BUNDLE_COMPONENT_ROW_LIMIT:
            warnings.append(f"AI extracted more than {BUNDLE_COMPONENT_ROW_LIMIT} components. The first {BUNDLE_COMPONENT_ROW_LIMIT} were prefilled; enter remaining components manually.")
        if ai_result_mentions_retained_amount(ai_result) and not ai_result_maps_retained_amount(ai_result):
            warnings.append("Retained or netted amounts were detected but not clearly mapped to a component. Review the net distribution amounts before saving.")

        for row_idx in range(BUNDLE_COMPONENT_ROW_LIMIT):
            component = components[row_idx] if row_idx < len(components) and isinstance(components[row_idx], dict) else None
            component_type = normalize_ai_component_type(component.get("component_type")) if component else CAPITAL_CALL_COMPONENT_TYPES[0]
            cash_amount = normalize_amount(component.get("cash_amount")) if component else 0.0
            commitment_impact = normalize_amount(component.get("commitment_impact")) if component else 0.0
            if component_type != "Gross capital call":
                commitment_impact = 0.0
            if component_type == "Equalisation interest outside commitment":
                cash_amount = 0.0
            st.session_state[f"bundle_enabled_{fund_id}_{row_idx}"] = component is not None
            st.session_state[f"bundle_type_{fund_id}_{row_idx}"] = component_type
            st.session_state[f"bundle_desc_{fund_id}_{row_idx}"] = str(component.get("description") or "").strip() if component else ""
            st.session_state[f"bundle_cash_{fund_id}_{row_idx}"] = cash_amount
            st.session_state[f"bundle_commit_{fund_id}_{row_idx}"] = commitment_impact
            st.session_state[f"bundle_eq_{fund_id}_{row_idx}"] = normalize_amount(component.get("equalisation_interest")) if component else 0.0

        return warnings

    simple = ai_result.get("simple", {})
    if not isinstance(simple, dict):
        simple = {}
    if not simple and any(key in ai_result for key in ["amount", "investments", "mgmt_fee", "fund_expenses"]):
        simple = ai_result

    transaction_type = str(simple.get("transaction_type") or "call").strip().lower()
    if notice_type == "distribution":
        transaction_type = "distribution"
    elif transaction_type not in ["call", "repayment", "distribution"]:
        transaction_type = "call"

    final_wire_amount = normalize_amount(ai_result.get("final_wire_amount"))
    amount = final_wire_amount if notice_type == "distribution" and final_wire_amount else normalize_amount(simple.get("amount"))
    investments = 0.0 if notice_type == "distribution" else normalize_amount(simple.get("investments"))
    mgmt_fee = normalize_amount(simple.get("mgmt_fee"))
    base_fund_expenses = normalize_amount(simple.get("fund_expenses"))
    gp_deemed_contribution = normalize_amount(simple.get("gp_deemed_contribution"))
    other_contributions = normalize_amount(simple.get("other_contributions"))
    other_fees_or_expenses = normalize_amount(simple.get("other_fees_or_expenses"))
    extra_expenses = gp_deemed_contribution + other_contributions + other_fees_or_expenses
    fund_expenses = base_fund_expenses + extra_expenses
    if transaction_type == "call" and extra_expenses > 0 and amount > 0:
        implied_expenses = amount - investments - mgmt_fee
        if abs(base_fund_expenses - implied_expenses) <= 1 and abs(fund_expenses - implied_expenses) > 1:
            fund_expenses = base_fund_expenses

    notes_parts = [str(simple.get("notes") or notice_type.replace("_", " ")).strip()]
    if gp_deemed_contribution > 0:
        notes_parts.append(f"Includes GP deemed contribution of {gp_deemed_contribution:g}.")
    if other_contributions > 0:
        notes_parts.append(f"Includes other contributions of {other_contributions:g}.")
    if other_fees_or_expenses > 0:
        notes_parts.append(f"Includes other fees or expenses of {other_fees_or_expenses:g}.")
    notes = " ".join(part for part in notes_parts if part)

    notes_text = str(simple.get("notes") or "")
    is_recallable = bool(simple.get("is_recallable")) or "recallable" in notes_text.lower()
    explicit_reduction = bool(simple.get("reduces_called_capital") or simple.get("restores_unfunded_commitment"))
    if transaction_type == "call":
        affects_called = False
    elif transaction_type == "repayment":
        affects_called = explicit_reduction or is_recallable
    else:
        affects_called = explicit_reduction or is_recallable

    if transaction_type == "call" and amount > 0:
        component_sum = investments + mgmt_fee + fund_expenses
        if abs(amount - component_sum) > 1:
            warnings.append(
                f"Simple call components differ from cash amount by {abs(amount - component_sum):,.2f}. "
                "Review amount, investments, fees, and expenses before saving."
            )

    st.session_state[f"call_entry_mode_{fund_id}"] = "Simple Capital Call"
    st.session_state[f"bundle_ai_expected_wire_set_{fund_id}"] = False
    st.session_state[f"cc_ai_result_{fund_id}"] = {
        "call_number": call_number,
        "call_date": str(call_date),
        "payment_date": str(payment_date),
        "amount": amount,
        "investments": investments,
        "mgmt_fee": mgmt_fee,
        "fund_expenses": fund_expenses,
        "equalisation_interest": normalize_amount(simple.get("equalisation_interest")),
        "transaction_type": transaction_type,
        "affects_called": affects_called,
        "notes": notes
    }
    return warnings

def analyze_capital_call_pdf_with_ai(pdf_bytes: bytes) -> dict:
    pdf_text = extract_pdf_text(pdf_bytes)
    prompt = f"""You are an expert private equity fund accountant. Carefully analyze this capital call, distribution, or net capital call/equalisation notice.

Classify the notice as exactly one of:
1. simple_capital_call
2. distribution
3. net_capital_call_bundle

Return ONLY a valid JSON object using this exact root schema. Use null for missing dates or unknown scalar values, [] for no rows, and 0 for missing amounts:
{{
    "notice_type": "simple_capital_call | distribution | net_capital_call_bundle",
    "confidence": number from 0 to 1,
    "call_number": number or null,
    "call_date": "YYYY-MM-DD" or null,
    "payment_date": "YYYY-MM-DD" or null,
    "currency": "USD | EUR | GBP | other" or null,
    "final_wire_amount": number,
    "wire_direction": "pay_to_fund | receive_from_fund | netted",
    "simple": {{
        "amount": number,
        "investments": number,
        "mgmt_fee": number,
        "fund_expenses": number,
        "gp_deemed_contribution": number,
        "other_contributions": number,
        "other_fees_or_expenses": number,
        "equalisation_interest": number,
        "transaction_type": "call | distribution | repayment",
        "affects_called": boolean,
        "is_recallable": boolean,
        "reduces_called_capital": boolean,
        "restores_unfunded_commitment": boolean,
        "notes": string
    }},
    "components": [
        {{
            "component_type": "Gross capital call | Recallable repayment | Non-recallable distribution | Realised gain distribution | Equalisation interest outside commitment",
            "description": string,
            "cash_amount": number,
            "commitment_impact": number,
            "equalisation_interest": number
        }}
    ],
    "reconciliation": {{
        "gross_calls": number,
        "repayments": number,
        "distributions": number,
        "equalisation_interest": number,
        "calculated_net_wire": number,
        "difference_to_final_wire": number
    }},
    "warnings": [string]
}}

For net_capital_call_bundle components, use ONLY these exact component_type labels:
- Gross capital call
- Recallable repayment
- Non-recallable distribution
- Realised gain distribution
- Equalisation interest outside commitment

Bundle extraction rules:
- Extract equalisation interest as its own "Equalisation interest outside commitment" component. Do not combine it into gross capital call, repayment, or distribution rows.
- Set commitment_impact to 0 for every component except "Gross capital call".
- For "Gross capital call", cash_amount is the cash called and commitment_impact is the amount that increases called capital.
- For recallable repayments and distributions, use cash_amount only; component type determines that it subtracts from net wire.
- Never invent adjustment rows merely to reconcile to final_wire_amount.
- Only extract retained, withheld, offset, or netted components if they are explicitly stated in the notice.
- If a retained/withheld/netted amount is explicitly linked to a gross distribution or realised gain distribution, use the cash-effective net amount in that component cash_amount.
- Include the gross amount and retained/withheld/netted amount in that component description or in warnings.
- If a distribution is partially retained, prefer cash-effective amounts only when the notice explicitly provides enough information to calculate them.
- If the notice shows gross amounts and retained/netted/offset amounts but the cash-effective mapping is ambiguous, do not force reconciliation.
- If retained, withheld, offset, or netted amounts are visible but cannot be mapped with confidence, add a warning containing the word "retained" that explains the user must review and adjust manually.
- The component list should reconcile to final_wire_amount only when the notice explicitly provides enough information using: gross capital calls + equalisation interest - recallable repayments - distributions.
- Put explicitly stated reconciliation-critical rows and equalisation interest before lower-priority detail rows so they appear in the first 15 components.

Simple capital call extraction rules:
- For a normal capital call notice, set notice_type to "simple_capital_call", transaction_type to "call", affects_called to false, reduces_called_capital to false, and restores_unfunded_commitment to false.
- A normal capital call increases called capital and reduces unfunded commitment; it does NOT reduce total called capital.
- Only set affects_called true when the notice is a recallable repayment, clawback, or explicitly reduces called capital/restores unfunded commitment.
- For repayment notices, set transaction_type to "repayment"; set is_recallable and affects_called true only if the repayment is recallable or explicitly restores unfunded commitment.
- For distribution notices, set transaction_type to "distribution"; set affects_called false unless the notice explicitly says it is recallable or reduces called capital.
- Map Capital Call for Investments, Investment Contribution, or Investment Capital Contribution to simple.investments.
- Map Management Fees or Mgmt Fee to simple.mgmt_fee.
- Map Fund Expenses, Partnership Expenses, Organizational Expenses, Other Expenses, or similar expense lines to simple.fund_expenses.
- Extract GP Deemed Contribution, Deemed Contribution, GP Contribution, or similar lines to simple.gp_deemed_contribution, not simple.fund_expenses.
- Extract Other Contribution or Other Capital Contribution lines to simple.other_contributions, not simple.fund_expenses.
- Extract other fee/expense lines that do not fit management fee or fund expenses to simple.other_fees_or_expenses.
- For simple capital calls, amount should be the total cash amount due. The components should reconcile as amount = investments + mgmt_fee + fund_expenses + gp_deemed_contribution + other_contributions + other_fees_or_expenses whenever the notice provides those details.
- If a GP Deemed Contribution is present, mention it in simple.notes.

Amounts must be positive numbers without commas. Component type determines whether the amount adds to or subtracts from the net wire.
IMPORTANT: Return ONLY the JSON, no markdown, no extra text.

NOTICE TEXT:
{pdf_text}"""

    payload = {
        "model": "anthropic/claude-sonnet-4",
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

def analyze_quarterly_report_with_ai(report_text: str) -> dict:
    prompt = f"""You are an expert private equity fund accountant. Carefully analyze this quarterly report, financial statement, or capital account statement and extract the financial performance metrics.
Pay special attention to tables like "Fund Performance: Investments" or "Gross returns" which have columns such as "Capital invested", "Realised", "Unrealised", "Total", "Multiple", "IRR".

Return ONLY a valid JSON object with these exact keys (use null if a specific metric is not found):
{{
    "year": number (e.g., 2025, derived from the report date),
    "quarter": number (1, 2, 3, or 4),
    "report_date": "YYYY-MM-DD",
    "nav": number (The Fund's Total Value or Net Asset Value. Ensure it is the FULL absolute number, e.g., if it says 1,498.3m, return 1498300000 without commas),
    "tvpi": number (Total Value to Paid-In, Gross MOIC, or Multiple, e.g., 1.70),
    "dpi": number (Distributions to Paid-In. IF NOT EXPLICITLY STATED, calculate by dividing Total Distributions by Paid-In Capital),
    "rvpi": number (Residual Value to Paid-In. IF NOT EXPLICITLY STATED, calculate by dividing Net Asset Value (NAV) by Paid-In Capital),
    "irr": number (Internal Rate of Return percentage, usually found under Gross IRR. e.g., 88% -> 88.0)
}}

CRITICAL: Return ONLY the JSON object. No markdown code blocks, no backticks, no explanation text before or after. Just the raw JSON starting with {{ and ending with }}.

REPORT TEXT:
{report_text}"""

    payload = {
        "model": "anthropic/claude-sonnet-4",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://octo-dashboard.streamlit.app"
    }
    
    try:
        resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=90)
        if resp.status_code != 200:
            raise Exception(f"OpenRouter error {resp.status_code}: {resp.text[:300]}")
        
        content = resp.json()["choices"][0]["message"]["content"].strip()
        
        if "```" in content:
            parts = content.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{") and part.endswith("}"):
                    content = part
                    break
        
        content = content.strip()
        
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            content = content[start:end]
        
        result = json.loads(content)
        return result
        
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse AI response as JSON: {str(e)}. Response was: {content[:200]}")
    except Exception as e:
        raise Exception(f"AI analysis failed: {str(e)}")

st.set_page_config(
    page_title="ALT Group | Octo Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;700&display=swap');
    * { font-family: 'Inter', sans-serif; }
    h1 { font-size: 24px !important; margin-bottom: 0.5rem !important; }
    h2 { font-size: 20px !important; }
    h3 { font-size: 18px !important; }
    p, label, h1, h2, h3, h4, h5, h6, a, li, input, textarea, button, [data-testid="stMetricValue"] {
        font-family: 'Inter', sans-serif !important;
    }
    [data-testid="stExpander"] summary p { font-family: 'Inter', sans-serif !important; }
    [data-testid="stExpanderToggleIcon"], [data-testid="stExpanderToggleIcon"] *,
    [data-testid="stIconMaterial"], .material-symbols-rounded, .material-icons, i, svg {
        font-family: 'Material Symbols Rounded', 'Material Icons' !important;
        font-feature-settings: 'liga' !important;
        -webkit-font-feature-settings: 'liga' !important;
        text-transform: none !important; letter-spacing: normal !important;
    }
    [data-testid="stExpanderToggleIcon"] { max-width: 24px !important; overflow: hidden !important; white-space: nowrap !important; }
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"], section[data-testid="stSidebar"] + div { 
        background-color: #0f1117 !important; color: #e2e8f0 !important;
    }
    p, span, label, div { color: #e2e8f0; }
    [data-testid="stExpander"] summary { 
        color: #e2e8f0 !important; display: flex !important;
        align-items: center !important; gap: 8px !important;
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
    [data-testid="metric-container"] label, [data-testid="metric-container"] div { 
        color: #94a3b8 !important; font-size: 13px !important;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] { 
        font-size: 0.95rem !important; 
    }
    [data-testid="stMetricValue"] {
        color: #ffffff !important; font-weight: 700 !important; 
        white-space: nowrap !important;
        overflow: visible !important;
        line-height: 1.2 !important;
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

def get_supabase() -> Client:
    if "sb_client" not in st.session_state:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        st.session_state.sb_client = create_client(url, key)
    return st.session_state.sb_client

def get_saved_fx_rate():
    try:
        res = get_supabase().table("settings").select("value").eq("key", "eur_usd_rate").execute()
        if res.data:
            return float(res.data[0]["value"])
    except:
        pass
    return 1.0800

def update_saved_fx_rate(new_rate):
    try:
        get_supabase().table("settings").upsert({"key": "eur_usd_rate", "value": new_rate}).execute()
    except Exception as e:
        st.error(f"Failed to save FX rate: {e}")

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
        all_calls = get_capital_calls()
        all_dists = get_distributions()
        
        if funds:
            funds_list = []
            for f in funds:
                calls = [c for c in all_calls if c["fund_id"] == f["id"]]
                dists = [d for d in all_dists if d["fund_id"] == f["id"]]
                metrics = calculate_fund_metrics(f, calls, dists)
                total_called = metrics["total_called"]
                funds_list.append({
                    "Fund Name": f.get("name"),
                    "Manager": f.get("manager"),
                    "Strategy": f.get("strategy"),
                    "Currency": f.get("currency"),
                    "Commitment": f.get("commitment"),
                    "Total Called": total_called,
                    "Status": f.get("status")
                })
            pd.DataFrame(funds_list).to_excel(writer, index=False, sheet_name='Funds Portfolio')
        else:
            pd.DataFrame([{"Message": "No funds in the system"}]).to_excel(writer, index=False, sheet_name='Funds Portfolio')
        
        investors = get_investors()
        lp_calls = get_lp_calls()
        payments = get_lp_payments()
        if investors:
            data = []
            for inv in investors:
                row = {
                    "Investor Name": inv["name"],
                    "Commitment": inv.get("commitment", 0)
                }
                for c in lp_calls:
                    col_name = f"{c['call_date']} ({c['call_pct']}%)"
                    payment = next((p for p in payments if p["lp_call_id"] == c["id"] and p["investor_id"] == inv["id"]), None)
                    row[col_name] = "Paid" if (payment and payment["is_paid"]) else "Unpaid"
                data.append(row)
            pd.DataFrame(data).to_excel(writer, index=False, sheet_name='Investors & Calls')
        else:
            pd.DataFrame([{"Message": "No investors defined"}]).to_excel(writer, index=False, sheet_name='Investors & Calls')
            
        pipeline = get_pipeline_funds()
        if pipeline:
            pipe_list = []
            for p in pipeline:
                pipe_list.append({
                    "Fund Name": p.get("name"),
                    "Manager": p.get("manager"),
                    "Strategy": p.get("strategy"),
                    "Target Commitment": p.get("target_commitment"),
                    "Currency": p.get("currency"),
                    "Target Close Date": p.get("target_close_date"),
                    "Priority": p.get("priority")
                })
            pd.DataFrame(pipe_list).to_excel(writer, index=False, sheet_name='Pipeline')
        else:
            pd.DataFrame([{"Message": "No pipeline funds"}]).to_excel(writer, index=False, sheet_name='Pipeline')
            
    return output.getvalue()

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

def current_cache_user_key():
    return st.session_state.get("user_email") or st.session_state.get("username") or "anonymous"

@st.cache_data(ttl=600)
def fetch_all_funds(_sb, user_key):
    try: return _sb.table("funds").select("*").order("name").execute().data or []
    except Exception as e: st.error(f"Error loading funds: {e}"); return []

def get_funds():
    return fetch_all_funds(get_supabase(), current_cache_user_key())

@st.cache_data(ttl=600)
def fetch_all_capital_calls(_sb, user_key):
    try: return _sb.table("capital_calls").select("*").order("call_number").execute().data or []
    except: return []

def get_capital_calls(fund_id=None):
    data = fetch_all_capital_calls(get_supabase(), current_cache_user_key())
    if fund_id: return [d for d in data if d["fund_id"] == fund_id]
    return data

@st.cache_data(ttl=600)
def fetch_all_distributions(_sb, user_key):
    try: return _sb.table("distributions").select("*").order("dist_date").execute().data or []
    except: return []

def get_distributions(fund_id=None):
    data = fetch_all_distributions(get_supabase(), current_cache_user_key())
    if fund_id: return [d for d in data if d["fund_id"] == fund_id]
    return data

@st.cache_data(ttl=600)
def fetch_all_quarterly_reports(_sb, user_key):
    try: return _sb.table("quarterly_reports").select("*").order("year,quarter").execute().data or []
    except: return []

def get_quarterly_reports(fund_id=None):
    data = fetch_all_quarterly_reports(get_supabase(), current_cache_user_key())
    if fund_id: return [d for d in data if d["fund_id"] == fund_id]
    return data

@st.cache_data(ttl=600)
def fetch_all_pipeline_funds(_sb, user_key):
    try: return _sb.table("pipeline_funds").select("*").order("target_close_date").execute().data or []
    except: return []

def get_pipeline_funds():
    return fetch_all_pipeline_funds(get_supabase(), current_cache_user_key())

@st.cache_data(ttl=600)
def fetch_all_gantt_tasks(_sb, user_key):
    try: return _sb.table("gantt_tasks").select("*").order("start_date").execute().data or []
    except: return []

def get_gantt_tasks(pipeline_fund_id=None):
    data = fetch_all_gantt_tasks(get_supabase(), current_cache_user_key())
    if pipeline_fund_id: return [d for d in data if d["pipeline_fund_id"] == pipeline_fund_id]
    return data

@st.cache_data(ttl=600)
def fetch_all_investors(_sb, user_key):
    try: return _sb.table("investors").select("*").execute().data or []
    except: return []

def get_investors():
    return fetch_all_investors(get_supabase(), current_cache_user_key())

@st.cache_data(ttl=600)
def fetch_all_lp_calls(_sb, user_key):
    try: return _sb.table("lp_calls").select("*").order("call_date").execute().data or []
    except: return []

def get_lp_calls():
    return fetch_all_lp_calls(get_supabase(), current_cache_user_key())

@st.cache_data(ttl=600)
def fetch_all_lp_payments(_sb, user_key):
    try: return _sb.table("lp_payments").select("*").execute().data or []
    except: return []

def get_lp_payments():
    return fetch_all_lp_payments(get_supabase(), current_cache_user_key())

@st.cache_data(ttl=600)
def fetch_all_audit_logs(_sb, user_key):
    try: return _sb.table("audit_logs").select("*").order("created_at", desc=True).limit(100).execute().data or []
    except: return []

def get_audit_logs():
    return fetch_all_audit_logs(get_supabase(), current_cache_user_key())

@st.cache_data(ttl=600)
def fetch_all_operating_expenses(_sb, user_key):
    try: return _sb.table("fund_operating_expenses").select("*").order("expense_date", desc=True).execute().data or []
    except: return []

def get_operating_expenses():
    return fetch_all_operating_expenses(get_supabase(), current_cache_user_key())

def check_and_show_alerts():
    if "dismissed_banners" not in st.session_state:
        st.session_state.dismissed_banners = set()
    if "shown_toasts" not in st.session_state:
        st.session_state.shown_toasts = set()

    today = date.today()
    funds_dict = {f["id"]: f for f in get_funds()}
    pipe_dict = {f["id"]: f["name"] for f in get_pipeline_funds()}

    upcoming_fund_events = {}
    for cc in get_capital_calls():
        if not cc.get("payment_date"): continue
        try:
            deadline = datetime.strptime(str(cc["payment_date"]).split("T")[0], "%Y-%m-%d").date()
            if deadline >= today:
                key = (cc["fund_id"], deadline)
                if key not in upcoming_fund_events:
                    upcoming_fund_events[key] = {
                        "fund_name": funds_dict.get(cc["fund_id"], {}).get("name", "Unknown Fund"),
                        "currency": funds_dict.get(cc["fund_id"], {}).get("currency", "USD"),
                        "net_wire": 0.0,
                        "days_left": (deadline - today).days
                    }
                
                tx_type = cc.get("transaction_type", "call")
                amt = float(cc.get("amount", 0))
                interest = float(cc.get("equalisation_interest", 0))
                
                if tx_type == "call":
                    upcoming_fund_events[key]["net_wire"] += (amt + interest)
                else: 
                    upcoming_fund_events[key]["net_wire"] -= amt
        except: continue

    for key, data in upcoming_fund_events.items():
        days_left = data["days_left"]
        if 0 <= days_left <= 14:
            fname = data["fund_name"]
            sym = "€" if data["currency"] == "EUR" else "$"
            amt = format_currency(data["net_wire"], sym)
            
            if days_left in [0, 1]:
                alert_id = f"net_banner_{key[0]}_{key[1]}"
                if alert_id not in st.session_state.dismissed_banners:
                    c1, c2 = st.columns([15, 1])
                    with c1:
                        if days_left == 0:
                            st.error(f"🚨 **Today!** Capital Call deadline for **{fname}** amounting to **{amt}**.")
                        else:
                            st.warning(f"⚠️ **Tomorrow!** Capital Call deadline for **{fname}** amounting to **{amt}**.")
                    with c2:
                        if st.button("✖", key=f"btn_{alert_id}", help="Dismiss Alert"):
                            st.session_state.dismissed_banners.add(alert_id)
                            st.rerun()
            else:
                alert_id = f"net_toast_{key[0]}_{key[1]}_{days_left}"
                if alert_id not in st.session_state.shown_toasts:
                    st.toast(f"🔔 Upcoming: Capital Call for {fname} in {days_left} days. Wire: {amt}", icon="💸")
                    st.session_state.shown_toasts.add(alert_id)

    for lpc in get_lp_calls():
        if not lpc.get("call_date"): continue
        try:
            deadline = datetime.strptime(str(lpc["call_date"]).split("T")[0], "%Y-%m-%d").date()
            days_left = (deadline - today).days
        except: continue

        if 0 <= days_left <= 14:
            if days_left in [0, 1]:
                alert_id = f"lpc_banner_{lpc['id']}_{days_left}"
                if alert_id not in st.session_state.dismissed_banners:
                    c1, c2 = st.columns([15, 1])
                    with c1:
                        if days_left == 0:
                            st.error(f"🚨 **Today!** Target date for LP capital collection ({lpc.get('call_pct')}% call).")
                        else:
                            st.warning(f"⚠️ **Tomorrow!** Target date for LP capital collection ({lpc.get('call_pct')}% call).")
                    with c2:
                        if st.button("✖", key=f"btn_{alert_id}", help="Dismiss Alert"):
                            st.session_state.dismissed_banners.add(alert_id)
                            st.rerun()
            else:
                alert_id = f"lpc_toast_{lpc['id']}_{days_left}"
                if alert_id not in st.session_state.shown_toasts:
                    st.toast(f"🔔 Upcoming: LP Collection target in {days_left} days.", icon="👥")
                    st.session_state.shown_toasts.add(alert_id)

    all_tasks = get_gantt_tasks()
    active_tasks = [t for t in all_tasks if t.get("status") != "done"]
    for t in active_tasks:
        if not t.get("due_date"): continue
        try:
            deadline = datetime.strptime(str(t["due_date"]).split("T")[0], "%Y-%m-%d").date()
            days_left = (deadline - today).days
        except: continue

        if 0 <= days_left <= 14:
            alert_id = f"gantt_toast_{t['id']}_{days_left}"
            if alert_id not in st.session_state.shown_toasts:
                p_name = pipe_dict.get(t.get("pipeline_fund_id"), "Pipeline Fund")
                day_str = "Today" if days_left == 0 else "Tomorrow" if days_left == 1 else f"in {days_left} days"
                st.toast(f"🗓️ Task for {p_name}: {t['task_name']} is due {day_str}!", icon="🎯")
                st.session_state.shown_toasts.add(alert_id)

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
                sb = get_supabase()
                res = sb.auth.sign_in_with_password({"email": email, "password": password})
                user_email = getattr(getattr(res, "user", None), "email", None) or email
                user_email = user_email.strip().lower()
                if not is_email_allowed(user_email):
                    st.error("This user is not authorized to access this app.")
                    try:
                        sb.auth.sign_out()
                    except Exception:
                        pass
                    return
                st.session_state.logged_in = True
                st.session_state.user_email = user_email
                st.session_state.username = user_email.split("@")[0]
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Login Error: {str(e)}")

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
        page = st.radio("Navigation", [
            "🏠 Overview",
            "📁 Portfolio",
            "👥 Investors",
            "🔍 Pipeline",
            "📈 Reports",
            "💼 Fund Expenses",
            "📋 Audit Logs"
        ], label_visibility="collapsed")
        
        st.divider()
        st.markdown("### 💱 FX Rate")
        
        if "eur_usd_rate" not in st.session_state:
            st.session_state.eur_usd_rate = get_saved_fx_rate()

        new_rate = st.number_input(
            "EUR to USD Rate", 
            value=st.session_state.eur_usd_rate, 
            min_value=0.0001, 
            step=0.0001, 
            format="%.4f"
        )

        if new_rate != st.session_state.eur_usd_rate:
            st.session_state.eur_usd_rate = new_rate
            update_saved_fx_rate(new_rate)
            st.rerun()

        st.divider()
        st.caption(f"User: {st.session_state.get('username', '')}")
        st.caption("Version 9.4.16 | Fixed Indents & Full Analytics")
        st.divider()
        
        if st.button("🔄 Refresh Data", use_container_width=True, help="Pull latest data from the server"):
            clear_cache_and_rerun()
            
        st.divider()
        st.markdown("<small>📥 Data Export</small>", unsafe_allow_html=True)
        master_excel = generate_master_excel_bytes()
        st.download_button(
            label="Download Master Report (Excel)",
            data=master_excel,
            file_name=f"Octo_Master_Report_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        st.divider()
        
        if st.button("🚪 Logout", use_container_width=True):
            try:
                get_supabase().auth.sign_out()
            except:
                pass
            st.cache_data.clear()
            st.session_state.clear()
            st.rerun()

    if "Overview" in page: show_overview()
    elif "Portfolio" in page: show_portfolio()
    elif "Investors" in page: show_investors()
    elif "Pipeline" in page: show_pipeline()
    elif "Reports" in page: show_reports()
    elif "Fund Expenses" in page: show_fund_expenses()
    elif "Audit Logs" in page: show_audit_logs()

def show_audit_logs():
    st.title("📋 System Audit Logs")
    st.markdown("View a history of all changes and deletions made in the system.")
    
    logs = get_audit_logs()
    if not logs:
        st.info("No audit logs recorded yet.")
        return
        
    for log in logs:
        dt_str = log["created_at"].replace("T", " ")[:16]
        icon = "🔴" if log["action"] == "DELETE" else "🟡" if log["action"] == "UPDATE" else "⚪"
        
        with st.expander(f"{icon} {dt_str} | User: {log['username']} | {log['details']}"):
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Action Type:** {log['action']}")
            with col2:
                st.write(f"**Target Table:** {log['table_name']}")
            
            if log.get("old_data") and log["old_data"] != {}:
                st.write("**Data before change/deletion (for manual restore):**")
                st.json(log["old_data"])

def show_overview():
    check_and_show_alerts()

    st.markdown("""
    <div class="dashboard-header">
    <h1 style="color:white;margin:0;">📊 Octo Fund Dashboard</h1>
    <p style="color:#94a3b8;margin:4px 0 0 0;">ALT Group | Alternative Capital Management</p>
    </div>
    """, unsafe_allow_html=True)

    funds = get_funds()
    all_calls = get_capital_calls()
    all_dists = get_distributions()
    all_reports = get_quarterly_reports(None)

    latest_reports = {}
    if all_reports:
        for r in all_reports:
            fid = r["fund_id"]
            if fid not in latest_reports:
                latest_reports[fid] = r
            else:
                curr = latest_reports[fid]
                if r["year"] > curr["year"] or (r["year"] == curr["year"] and r["quarter"] > curr["quarter"]):
                    latest_reports[fid] = r

    total_commit_usd = 0
    total_called_basis_usd = 0
    total_uncalled_usd = 0
    
    total_paid_in_cash_usd = 0
    total_dist_cash_usd = 0
    total_nav_usd = 0
    
    portfolio_cash_flows = []

    for f in funds:
        rate = st.session_state.eur_usd_rate if f.get("currency") == "EUR" else 1.0
        
        c_val = float(f.get("commitment") or 0)
        if 0 < c_val <= 1000:
            c_val *= 1_000_000
        total_commit_usd += c_val * rate
        
        f_calls = [c for c in all_calls if c["fund_id"] == f["id"]]
        f_dists = [d for d in all_dists if d["fund_id"] == f["id"]]
        
        metrics = calculate_fund_metrics(f, f_calls, f_dists)
        called = metrics["total_called"]
        total_called_basis_usd += called * rate
        total_uncalled_usd += metrics["uncalled"] * rate
        
        fund_paid_in = 0
        fund_dist = 0
        
        for c in f_calls:
            if c.get("is_future"): continue
            p_date_str = c.get("payment_date") or c.get("call_date")
            if not p_date_str: continue
            try:
                p_date = datetime.strptime(str(p_date_str).split("T")[0], "%Y-%m-%d").date()
                tx_type = c.get("transaction_type", "call")
                
                amt = float(c.get("amount") or 0) * rate
                eq = float(c.get("equalisation_interest") or 0) * rate
                
                if tx_type == "call":
                    flow = amt + eq
                    fund_paid_in += flow
                    portfolio_cash_flows.append((p_date, -flow))
                elif tx_type == "repayment":
                    fund_paid_in -= amt
                    portfolio_cash_flows.append((p_date, amt))
                elif tx_type == "distribution":
                    fund_dist += amt
                    fund_paid_in -= amt
                    portfolio_cash_flows.append((p_date, amt))
            except: pass
            
        for d in f_dists:
            d_date_str = d.get("dist_date")
            if not d_date_str: continue
            try:
                d_date = datetime.strptime(str(d_date_str).split("T")[0], "%Y-%m-%d").date()
                amt = float(d.get("amount") or 0) * rate
                fund_dist += amt
                portfolio_cash_flows.append((d_date, amt))
            except: pass
            
        total_paid_in_cash_usd += fund_paid_in
        total_dist_cash_usd += fund_dist

        # --- SIMPLE & ROBUST NAV CALCULATION ---
        fund_nav_local = 0
        if f["id"] in latest_reports:
            rep = latest_reports[f["id"]]
            rvpi = float(rep.get('rvpi') or 0.0)
            tvpi = float(rep.get('tvpi') or 1.0)
            rep_nav = rep.get("nav")
            rep_date_str = rep.get("report_date")
            
            try:
                if rep_nav is None or rep_nav == "" or not rep_date_str:
                    raise ValueError("Missing report NAV or date")
                    
                rep_date = datetime.strptime(str(rep_date_str).split("T")[0], "%Y-%m-%d").date()
                fund_nav_local = float(rep_nav)
                
                for c in f_calls:
                    if c.get("is_future"):
                        continue
                    tx_type = c.get("transaction_type", "call")
                    c_date_str = c.get("payment_date") or c.get("call_date")
                    if not c_date_str:
                        continue
                    try:
                        c_date = datetime.strptime(str(c_date_str).split("T")[0], "%Y-%m-%d").date()
                    except:
                        continue
                    if c_date <= rep_date:
                        continue
                        
                    if tx_type == "call":
                        amount = c.get("investments") if c.get("investments") is not None else c.get("amount")
                        fund_nav_local += float(amount or 0)
                    elif tx_type == "distribution":
                        fund_nav_local -= float(c.get("amount") or 0)
                        
                for d in f_dists:
                    d_date_str = d.get("dist_date")
                    if not d_date_str:
                        continue
                    try:
                        d_date = datetime.strptime(str(d_date_str).split("T")[0], "%Y-%m-%d").date()
                    except:
                        continue
                    if d_date > rep_date:
                        fund_nav_local -= float(d.get("amount") or 0)
            except:
                if rvpi > 0:
                    fund_nav_local = called * rvpi
                else:
                    fund_nav_local = (called * tvpi) - metrics["total_distributed"]
        else:
            fund_nav_local = called
            
        fund_nav = fund_nav_local * rate
        f["calculated_nav_local"] = fund_nav_local
        total_nav_usd += fund_nav

    # ADD FUND OPERATING EXPENSES
    operating_expenses = get_operating_expenses()
    total_operating_expenses_cash_usd = 0
    for exp in operating_expenses:
        exp_date_str = exp.get("expense_date")
        if not exp_date_str: continue
        try:
            exp_date = datetime.strptime(str(exp_date_str).split("T")[0], "%Y-%m-%d").date()
            rate = st.session_state.eur_usd_rate if exp.get("currency") == "EUR" else 1.0
            amt = float(exp.get("amount", 0)) * rate
            portfolio_cash_flows.append((exp_date, -amt)) 
            total_operating_expenses_cash_usd += amt
        except: pass
        
    total_paid_in_cash_usd += total_operating_expenses_cash_usd

    # Process Portfolio Level Analytics
    portfolio_cash_flows.append((date.today(), total_nav_usd))
    portfolio_irr = calculate_xirr(portfolio_cash_flows)
    portfolio_tvpi = (total_dist_cash_usd + total_nav_usd) / total_called_basis_usd if total_called_basis_usd > 0 else 0

    irr_display = "—"
    if isinstance(portfolio_irr, float):
        irr_display = f"{portfolio_irr * 100:.1f}%"
    elif portfolio_irr == "NM":
        irr_display = "NM (<1 Year)"

    def format_overview_currency(amount, currency_sym="$"):
        return f"{currency_sym}{float(amount or 0):,.1f}"

    st.markdown("""
    <style>
        [data-testid="stMetric"] label,
        [data-testid="metric-container"] label,
        [data-testid="metric-container"] div {
            font-size: 0.72rem !important;
            line-height: 1.15 !important;
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
        }
        [data-testid="stMetricValue"],
        [data-testid="metric-container"] [data-testid="stMetricValue"] {
            font-size: 0.95rem !important;
            line-height: 1.15 !important;
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
        }
        [data-testid="metric-container"] {
            padding: 8px 10px !important;
            min-height: 0 !important;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("##### 🏛️ Legal & Commitment (Basis)")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Active Funds", len(funds))
    with c2:
        st.metric("Total Commitments (USD Eqv)", format_overview_currency(total_commit_usd, "$"))
    with c3:
        st.metric("Total Called (Basis)", format_overview_currency(total_called_basis_usd, "$"))
    with c4:
        st.metric("Uncalled Balance", format_overview_currency(total_uncalled_usd, "$"))

    st.markdown("##### 🚀 Cash & Performance (Net LP)")
    c5, c6, c7, c8 = st.columns(4)
    with c5:
        st.metric("Total Paid-In (Cash Out)", format_overview_currency(total_paid_in_cash_usd, "$"))
    with c6:
        st.metric("Octo True NAV (USD Eqv)", format_overview_currency(total_nav_usd, "$"))
    with c7:
        st.metric("Portfolio TVPI", f"{portfolio_tvpi:.2f}x" if portfolio_tvpi > 0 else "—")
    with c8:
        st.metric("Portfolio Net IRR", irr_display)

    st.divider()
    col1 = st.container()
    col2 = st.container()

    with col1:
        st.subheader("📋 Funds Status")
        if funds:
            rows = []
            for f in funds:
                f_calls = [c for c in all_calls if c["fund_id"] == f["id"]]
                f_dists = get_distributions(f["id"])
                f_metrics = calculate_fund_metrics(f, f_calls, f_dists)
                total_called = f_metrics["total_called"]
                cash_paid = 0.0
                for c in f_calls:
                    tx_type = c.get("transaction_type", "call")
                    amount = float(c.get("amount") or 0)
                    eq_interest = float(c.get("equalisation_interest") or 0)
                    if tx_type == "call":
                        cash_paid += amount + eq_interest
                    elif tx_type in ["repayment", "distribution"]:
                        cash_paid -= amount
                cash_paid -= sum(float(d.get("amount") or 0) for d in f_dists)
                
                c_val = float(f.get("commitment") or 0)
                if 0 < c_val <= 1000:
                    c_val *= 1_000_000
                    
                pct = f"{total_called/c_val*100:.1f}%" if c_val > 0 else "—"
                currency_sym = "€" if f.get("currency") == "EUR" else "$"
                
                octo_nav = f.get("calculated_nav_local", total_called)
                    
                rows.append({
                    "Fund": f["name"],
                    "Currency": f.get("currency", "USD"),
                    "Commitment": format_currency(c_val, currency_sym),
                    "Total Called": format_currency(total_called, currency_sym) if total_called > 0 else "—",
                    "Cash Paid": format_currency(cash_paid, currency_sym) if abs(cash_paid) > 0 else "—",
                    "Called %": pct,
                    "Octo NAV": format_currency(octo_nav, currency_sym) if octo_nav > 0 else "—",
                    "Status": f.get("status", "active").capitalize(),
                })
                
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        else:
            st.info("No funds in the system") 

    with col2:
        st.subheader("🔔 Upcoming Events")
        today = date.today()
        upcoming_events = {}
        
        for f in funds:
            f_calls = [c for c in all_calls if c["fund_id"] == f["id"]]
            for c in f_calls:
                if not c.get("payment_date"): continue
                try:
                    p_date = datetime.strptime(str(c.get("payment_date")).split("T")[0], "%Y-%m-%d").date()
                    if p_date >= today:
                        key = (f["id"], p_date)
                        if key not in upcoming_events:
                            upcoming_events[key] = {
                                "fund_name": f["name"],
                                "currency": f.get("currency", "USD"),
                                "net_wire": 0.0,
                                "calls_included": []
                            }
                        
                        tx_type = c.get("transaction_type", "call")
                        amt = float(c.get("amount", 0))
                        interest = float(c.get("equalisation_interest", 0))
                        
                        if tx_type == "call":
                            upcoming_events[key]["net_wire"] += (amt + interest)
                        else:
                            upcoming_events[key]["net_wire"] -= amt
                            
                        upcoming_events[key]["calls_included"].append(str(c.get("call_number")))
                except:
                    pass
        
        if upcoming_events:
            for key, data in sorted(upcoming_events.items(), key=lambda x: x[0][1]):
                sym = "€" if data["currency"] == "EUR" else "$"
                net_wire = data["net_wire"]
                date_str = key[1].strftime("%Y-%m-%d")
                calls_str = ", ".join(data["calls_included"])
                
                st.markdown(f"""
                <div style="background:#1a3a1a;border-radius:8px;padding:12px;margin-bottom:8px;border-left:4px solid #4ade80;">
                    <small style="color:#4ade80">Payment Due: {date_str}</small><br>
                    <strong>{data['fund_name']}</strong><br>
                    <span style="color:#94a3b8">Included items: {calls_str}</span><br>
                    <span style="font-size:16px; font-weight:bold; color:white;">Net Wire: {format_currency(net_wire, sym)}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("💡 No upcoming capital calls (based on Payment Date).")

    st.divider()
    st.subheader("📊 FOF Collection Summary")

    investors = get_investors()
    lp_calls = get_lp_calls()
    payments = get_lp_payments()
    currency_sym = "$" 
    total_fund_commitment = sum(float(inv.get("commitment", 0)) for inv in investors)

    col_sum1, col_sum2 = st.columns([1, 3])
    with col_sum1:
        st.metric("Total LP Commitments", format_currency(total_fund_commitment, currency_sym))

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
                        paid_commit += float(inv.get("commitment", 0))

                total_paid_amount = paid_commit * call_pct
                outstanding = total_called_amount - total_paid_amount

                summary_data.append({
                    "Call": f"{c['call_date']} ({c['call_pct']}%)",
                    "Total Required": format_currency(total_called_amount, currency_sym),
                    "Total Received": format_currency(total_paid_amount, currency_sym),
                    "Outstanding Balance": format_currency(outstanding, currency_sym)
                })
            st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)
        else:
            st.info("No active capital calls yet.")

def show_fund_expenses():
    st.title("💼 Fund Operating Expenses")
    
    st.markdown("""
    <div class="dashboard-header">
    <h1 style="color:white;margin:0;">💼 Octo Fund Operating Expenses</h1>
    <p style="color:#94a3b8;margin:4px 0 0 0;">Track all operational expenses (Management, Legal, Accounting, etc.)</p>
    </div>
    """, unsafe_allow_html=True)
    
    sb = get_supabase()
    expenses = get_operating_expenses()
    
    # Summary metrics
    total_expenses_usd = 0
    expenses_by_category = {}
    
    for exp in expenses:
        rate = st.session_state.eur_usd_rate if exp.get("currency") == "EUR" else 1.0
        amt = float(exp.get("amount", 0)) * rate
        total_expenses_usd += amt
        
        cat = exp.get("category", "Other")
        expenses_by_category[cat] = expenses_by_category.get(cat, 0) + amt
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Operating Expenses", format_currency(total_expenses_usd, "$"))
    with col2:
        st.metric("Number of Expenses", len(expenses))
    with col3:
        if expenses_by_category:
            top_cat = max(expenses_by_category, key=expenses_by_category.get)
            st.metric("Top Category", f"{top_cat}")
    
    st.divider()
    
    # Add new expense
    with st.expander("➕ Add Operating Expense"):
        with st.form("add_expense_form"):
            col1, col2 = st.columns(2)
            with col1:
                exp_date = st.date_input("Expense Date")
                category_options = [
                    "Management Fee (ALT Group)", 
                    "Legal (Walkers, Arnon Segev etc.)", 
                    "Accounting (SAP, Nurit etc.)", 
                    "Tax (KPMG)", 
                    "Government Fees (Registrar)",
                    "Fund Admin (Zur)",
                    "Setup Fees",
                    "Other Professional Fees"
                ]
                category = st.selectbox("Category", category_options)
                description = st.text_input("Description (Optional)")
            
            with col2:
                amount = st.number_input("Amount", min_value=0.0, step=100.0)
                currency = st.selectbox("Currency", ["USD", "EUR", "ILS"])
                is_one_time = st.checkbox("One-time expense")
            
            if st.form_submit_button("💾 Save Expense", type="primary"):
                try:
                    sb.table("fund_operating_expenses").insert({
                        "expense_date": str(exp_date),
                        "category": category,
                        "description": description,
                        "amount": amount,
                        "currency": currency,
                        "is_one_time": is_one_time
                    }).execute()
                    log_action("INSERT", "fund_operating_expenses", f"Added expense: {category} - {description}", {})
                    st.success("✅ Expense added!")
                    clear_cache_and_rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
    
    st.divider()
    
    # Expenses table
    if expenses:
        st.markdown("### 📋 All Operating Expenses")
        
        exp_data = []
        for exp in expenses:
            if exp.get("currency") == "EUR": sym = "€"
            elif exp.get("currency") == "ILS": sym = "₪"
            else: sym = "$"
            
            exp_data.append({
                "id": exp["id"],
                "Date": exp.get("expense_date", ""),
                "Category": exp.get("category", ""),
                "Description": exp.get("description", ""),
                "Amount": format_currency(float(exp.get("amount", 0)), sym),
                "One-time": "Yes" if exp.get("is_one_time") else "No"
            })
        
        df = pd.DataFrame(exp_data)
        
        # Export button
        col_export, col_space = st.columns([1, 5])
        with col_export:
            excel_data = convert_df_to_excel(df.drop(columns=["id"], errors="ignore"))
            st.download_button(
                label="📥 Export Excel",
                data=excel_data,
                file_name=f"Operating_Expenses_{date.today()}.xlsx",
                use_container_width=True
            )
        
        st.dataframe(df.drop(columns=["id"]), use_container_width=True, hide_index=True)
        
        # Delete expenses
        st.markdown("#### ⚙️ Manage Expenses")
        for idx, row in df.iterrows():
            exp_id = row["id"]
            with st.expander(f"{row['Category']} - {row['Date']} ({row['Amount']})", expanded=False):
                col_del = st.columns([5, 1])
                with col_del[1]:
                    if st.button("🗑️ Delete", key=f"del_exp_{exp_id}"):
                        st.session_state[f"confirm_del_exp_{exp_id}"] = True
                
                if st.session_state.get(f"confirm_del_exp_{exp_id}"):
                    st.warning("Delete this expense?")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅ Yes", key=f"yes_exp_{exp_id}"):
                            try:
                                exp = next(e for e in expenses if e["id"] == exp_id)
                                log_action("DELETE", "fund_operating_expenses", f"Deleted expense: {row['Category']}", exp)
                                sb.table("fund_operating_expenses").delete().eq("id", exp_id).execute()
                                st.session_state.pop(f"confirm_del_exp_{exp_id}", None)
                                clear_cache_and_rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                    with c2:
                        if st.button("❌ Cancel", key=f"no_exp_{exp_id}"):
                            st.session_state.pop(f"confirm_del_exp_{exp_id}", None)
                            st.rerun()
    else:
        st.info("No operating expenses recorded yet.")
    
    # Breakdown by category
    if expenses_by_category:
        st.divider()
        st.markdown("### 📊 Expenses by Category")
        
        fig = px.pie(
            values=list(expenses_by_category.values()),
            names=list(expenses_by_category.keys()),
            title="Operating Expenses Breakdown (USD Eqv)"
        )
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='white'
        )
        st.plotly_chart(fig, use_container_width=True)

def show_portfolio():
    st.title("📁 Portfolio")
    
    with st.expander("➕ Add New Fund to Portfolio"):
        with st.form("add_new_fund_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("Fund Name")
                new_manager = st.text_input("Manager")
                strategy_opts = ["Growth", "VC", "Tech", "Niche", "Special Situations", "Mid-Market Buyout"]
                new_strategy = st.selectbox("Strategy", strategy_opts)
                new_geo = st.text_input("Geographic Focus")
            with col2:
                new_commitment = st.number_input("Commitment Amount", min_value=0.0, step=500000.0)
                new_currency = st.selectbox("Currency", ["USD", "EUR"])
                new_date = st.date_input("Investment Date")
                status_opts = ["active", "closed", "exited"]
                new_status = st.selectbox("Status", status_opts)
                
            if st.form_submit_button("💾 Save New Fund", type="primary"):
                try:
                    get_supabase().table("funds").insert({
                        "name": new_name,
                        "manager": new_manager,
                        "strategy": new_strategy,
                        "geographic_focus": new_geo,
                        "commitment": new_commitment,
                        "currency": new_currency,
                        "vintage_year": new_date.year,
                        "investment_date": str(new_date),
                        "status": new_status
                    }).execute()
                    st.success("✅ New fund successfully added! It now appears in the tabs below.")
                    clear_cache_and_rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    funds = get_funds()
    if not funds:
        st.info("No funds in the system")
        return

    selected_fund_id = st.session_state.get("portfolio_selected_fund_id")
    if selected_fund_id not in [f["id"] for f in funds]:
        selected_fund_id = funds[0]["id"]
        st.session_state.portfolio_selected_fund_id = selected_fund_id

    selected_index = next((idx for idx, f in enumerate(funds) if f["id"] == selected_fund_id), 0)
    selected_fund = st.selectbox(
        "Select Fund",
        funds,
        index=selected_index,
        format_func=lambda f: f["name"],
        key="portfolio_selected_fund"
    )
    st.session_state.portfolio_selected_fund_id = selected_fund["id"]
    show_fund_detail(selected_fund)

def show_fund_detail(fund):
    calls = get_capital_calls(fund["id"])
    dists = get_distributions(fund["id"])
    reports = get_quarterly_reports(fund["id"])

    metrics = calculate_fund_metrics(fund, calls, dists)
    
    commitment = metrics["commitment"]
    total_called = metrics["total_called"]
    total_dist = metrics["total_distributed"]
    uncalled = metrics["uncalled"]
    currency_sym = "€" if fund.get("currency") == "EUR" else "$"

    col_spacer, col_edit, col_del = st.columns([9.2,0.4,0.4])
    with col_edit:
        if st.button("✏️", key=f"edit_fund_{fund['id']}", help="Edit fund details"):
            st.session_state[f"editing_fund_{fund['id']}"] = True
    with col_del:
        if st.button("🗑️", key=f"del_fund_{fund['id']}", help="Delete fund"):
            st.session_state[f"confirm_del_fund_{fund['id']}"] = True

    if st.session_state.get(f"confirm_del_fund_{fund['id']}"):
        st.warning(f"⚠️ Delete '{fund['name']}'? All associated Calls, Distributions, and Reports will also be deleted.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Yes, Delete All", key=f"yes_fund_{fund['id']}", type="primary"):
                try:
                    sb = get_supabase()
                    log_action("DELETE", "funds", f"Deleted fund '{fund['name']}' including all its data", fund)
                    sb.table("capital_calls").delete().eq("fund_id", fund["id"]).execute()
                    sb.table("distributions").delete().eq("fund_id", fund["id"]).execute()
                    sb.table("quarterly_reports").delete().eq("fund_id", fund["id"]).execute()
                    sb.table("funds").delete().eq("id", fund["id"]).execute()
                    st.success("Deleted!")
                    st.session_state.pop(f"confirm_del_fund_{fund['id']}", None)
                    clear_cache_and_rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        with c2:
            if st.button("❌ Cancel", key=f"no_fund_{fund['id']}"):
                st.session_state.pop(f"confirm_del_fund_{fund['id']}", None)
                st.rerun()

    if st.session_state.get(f"editing_fund_{fund['id']}"):
        with st.form(f"edit_fund_form_{fund['id']}"):
            st.markdown("**✏️ Edit Fund Details**")
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("Fund Name", value=fund.get("name",""))
                new_manager = st.text_input("Manager", value=fund.get("manager","") or "")
                strategy_opts = ["Growth", "VC", "Tech", "Niche", "Special Situations", "Mid-Market Buyout"]
                cur_s = fund.get("strategy","Growth")
                new_strategy = st.selectbox("Strategy", strategy_opts,
                    index=strategy_opts.index(cur_s) if cur_s in strategy_opts else 0)
                new_geo = st.text_input("Geographic Focus", value=fund.get("geographic_focus","") or "")
            with col2:
                new_commitment = st.number_input("Commitment", value=float(commitment), min_value=0.0, step=500000.0)
                
                cur_cur = fund.get("currency","USD")
                new_currency = st.selectbox("Currency", ["USD","EUR"], index=0 if cur_cur=="USD" else 1)
                status_opts = ["active","closed","exited"]
                cur_st = fund.get("status","active")
                new_status = st.selectbox("Status", status_opts,
                    index=status_opts.index(cur_st) if cur_st in status_opts else 0)
                
                cur_date = fund.get("investment_date")
                try:
                    default_date = datetime.fromisoformat(str(cur_date)).date() if cur_date else date(int(fund.get("vintage_year") or 2020), 1, 1)
                except:
                    default_date = date.today()
                new_inv_date = st.date_input("Investment Date", value=default_date)

            c1, c2 = st.columns(2)
            with c1:
                if st.form_submit_button("💾 Save", type="primary"):
                    try:
                        log_action("UPDATE", "funds", f"Updated fund details: {fund['name']}", fund)
                        get_supabase().table("funds").update({
                            "name": new_name, "manager": new_manager,
                            "strategy": new_strategy, "commitment": new_commitment,
                            "currency": new_currency, "status": new_status,
                            "vintage_year": new_inv_date.year,
                            "geographic_focus": new_geo,
                            "investment_date": str(new_inv_date)
                        }).eq("id", fund["id"]).execute()
                        st.success("✅ Updated!")
                        st.session_state.pop(f"editing_fund_{fund['id']}", None)
                        clear_cache_and_rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
            with c2:
                if st.form_submit_button("❌ Cancel"):
                    st.session_state.pop(f"editing_fund_{fund['id']}", None)
                    st.rerun()

    posted_calls = [c for c in calls if not c.get("is_future")]
    actual_cash_paid = 0.0
    total_mgmt_fees = 0.0
    total_fund_expenses = 0.0
    total_equalisation_interest = 0.0

    for c in posted_calls:
        tx_type = c.get("transaction_type", "call")
        amount = float(c.get("amount") or 0)
        eq_interest = float(c.get("equalisation_interest") or 0)

        total_mgmt_fees += float(c.get("mgmt_fee") or 0)
        total_fund_expenses += float(c.get("fund_expenses") or 0)
        total_equalisation_interest += eq_interest

        if tx_type == "call":
            actual_cash_paid += amount + eq_interest
        elif tx_type in ["repayment", "distribution"]:
            actual_cash_paid -= amount

    actual_cash_paid -= sum(float(d.get("amount") or 0) for d in dists)

    def fmt_fund_amount(value, dash_zero=False):
        value = float(value or 0)
        if dash_zero and abs(value) < 0.05:
            return "&mdash;"
        return f"{currency_sym}{value:,.1f}"

    called_pct = f"{total_called / commitment * 100:.1f}%" if commitment > 0 else "&mdash;"
    fund_metric_rows = [
        ("Commitment", fmt_fund_amount(commitment)),
        ("Total Called / Basis", fmt_fund_amount(total_called)),
        ("Called %", called_pct),
        ("Actual Cash Paid", fmt_fund_amount(actual_cash_paid)),
        ("Uncalled Balance", fmt_fund_amount(uncalled)),
        ("Total Distributed", fmt_fund_amount(total_dist, dash_zero=True)),
        ("Management Fees", fmt_fund_amount(total_mgmt_fees, dash_zero=True)),
        ("Fund Expenses & Other", fmt_fund_amount(total_fund_expenses, dash_zero=True)),
        ("Equalisation / Late Interest", fmt_fund_amount(total_equalisation_interest, dash_zero=True))
    ]
    fund_metric_table_rows = "".join(
        f"<tr><td>{label}</td><td>{value}</td></tr>" for label, value in fund_metric_rows
    )
    fund_metric_html = f"""
<style>
    .fund-metrics-wrap {{
        max-width: 560px;
        margin: -6px 0 6px 0;
    }}
    .fund-metrics-title {{
        font-size: 0.95rem;
        font-weight: 700;
        color: #f8fafc;
        margin-bottom: 6px;
    }}
    .fund-metrics-table {{
        width: 100%;
        border-collapse: collapse;
        border: 1px solid #334155;
        background: #111827;
    }}
    .fund-metrics-table td {{
        padding: 6px 10px;
        border-bottom: 1px solid #1f2937;
        font-size: 0.86rem;
        line-height: 1.25;
    }}
    .fund-metrics-table tr:last-child td {{
        border-bottom: 0;
    }}
    .fund-metrics-table td:first-child {{
        color: #94a3b8;
        width: 58%;
    }}
    .fund-metrics-table td:last-child {{
        color: #f8fafc;
        text-align: right;
        font-variant-numeric: tabular-nums;
        font-weight: 600;
    }}
</style>
<div class="fund-metrics-wrap">
    <div class="fund-metrics-title">Fund Metrics</div>
    <table class="fund-metrics-table">
        <tbody>{fund_metric_table_rows}</tbody>
    </table>
</div>
"""

    st.markdown(fund_metric_html, unsafe_allow_html=True)

    st.divider()
    tab1, tab2, tab3 = st.tabs(["📞 Capital Calls", "💰 Distributions", "📊 Performance"])

    with tab1:
        if calls:
            st.markdown("**Capital Calls List**")
            for c in calls:
                tx_icons = {
                    "call": "💰",
                    "repayment": "🔄",
                    "distribution": "📤"
                }
                tx_type = c.get("transaction_type", "call")
                icon = "🔮" if c.get("is_future") else tx_icons.get(tx_type, "💰")
                
                total_cash = float(c.get("amount", 0)) + float(c.get("equalisation_interest", 0))
                
                with st.expander(
                    f"{icon} Call #{c.get('call_number')} | {c.get('payment_date','')} | "
                    f"Wire/Amount: {format_currency(total_cash, currency_sym)} "
                    f"{'🔮' if c.get('is_future') else '✅'}", 
                    expanded=False
                ):
                    col1, col2, col3 = st.columns([2,2,1])
                    with col1:
                        st.write(f"**Type:** {tx_type.capitalize()}")
                        st.write(f"Call Date: {c.get('call_date','')}")
                        st.write(f"Payment Date: {c.get('payment_date','')}")
                        st.write(f"Cash Amount: {format_currency(float(c.get('amount',0)), currency_sym)}")
                        inv_val = float(c.get('investments') or 0)
                        if inv_val > 0:
                            st.write(f"Commitment Impact: {format_currency(inv_val, currency_sym)}")
                    with col2:
                        mgmt = float(c.get('mgmt_fee', 0))
                        exp = float(c.get('fund_expenses', 0))
                        if mgmt > 0:
                            st.write(f"Mgmt Fee: {format_currency(mgmt, currency_sym)}")
                        if exp > 0:
                            st.write(f"Fund Expenses / Other: {format_currency(exp, currency_sym)}")
                            
                        affects = c.get("affects_called")
                        affects_text = "Yes" if (affects or (affects is None and tx_type == "repayment")) else "No"
                        st.write(f"Reduces Total Called: {affects_text}")
                        
                        eq_interest = float(c.get('equalisation_interest', 0))
                        if eq_interest > 0:
                            st.write(f"⚠️ Equalisation Interest: {format_currency(eq_interest, currency_sym)}")
                        
                        if c.get('notes'):
                            st.write(f"Notes: {c.get('notes')}")
                    with col3:
                        if st.button("🗑️", key=f"del_call_{c['id']}", help="Delete Call"):
                            st.session_state[f"confirm_del_call_{c['id']}"] = True
                        
                    if st.session_state.get(f"confirm_del_call_{c['id']}"):
                        st.warning("Delete this Call?")
                        cc1, cc2 = st.columns(2)
                        with cc1:
                            if st.button("✅ Delete", key=f"yes_call_{c['id']}"):
                                try:
                                    log_action("DELETE", "capital_calls", f"Deleted Capital Call #{c.get('call_number')} from {fund['name']}", c)
                                    get_supabase().table("capital_calls").delete().eq("id", c["id"]).execute()
                                    clear_cache_and_rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")
                        with cc2:
                            if st.button("❌ Cancel", key=f"no_call_{c['id']}"):
                                st.session_state.pop(f"confirm_del_call_{c['id']}", None)
                                st.rerun()

            chart_data = [c for c in calls if not c.get("is_future") and c.get("transaction_type") == "call" and (c.get("amount") or c.get("investments"))]
            if chart_data:
                fig = px.bar(
                    x=[f"Call #{c['call_number']}" for c in chart_data],
                    y=[float(c.get("investments") if float(c.get("investments",0)) > 0 else c.get("amount",0)) for c in chart_data],
                    labels={"x": "Call", "y": f"Commitment Impact ({fund.get('currency','USD')})"},
                    title="Capital Calls History (Commitment Usage)",
                    color_discrete_sequence=["#0f3460"]
                )
                fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='white')
                st.plotly_chart(fig, use_container_width=True, key=f"calls_chart_{fund['id']}")
        else:
            st.info("No Capital Calls yet")

        st.divider()
        st.markdown("**🤖 Add Capital Call from PDF (AI Extraction)**")
        uploaded_cc_pdf = st.file_uploader("Upload Capital Call Notice (PDF)", type=["pdf"], key=f"cc_uploader_{fund['id']}")
        
        if uploaded_cc_pdf:
            if st.button("Analyze Document Now", type="primary", key=f"cc_analyze_btn_{fund['id']}"):
                with st.spinner("Claude is analyzing the document..."):
                    try:
                        cc_bytes = uploaded_cc_pdf.read()
                        ai_result = analyze_capital_call_pdf_with_ai(cc_bytes)
                        prefill_warnings = apply_capital_call_ai_prefill(fund, calls, ai_result)
                        st.session_state[f"cc_ai_prefill_warnings_{fund['id']}"] = prefill_warnings
                        st.success("✅ Data extracted successfully! Please review and confirm in the form below.")
                        for warning in prefill_warnings:
                            st.warning(warning)
                    except Exception as e:
                        st.error(f"Error analyzing document: {e}")
        
        st.divider()
        st.markdown("**➕ Or Enter Details Manually**")
        
        entry_mode = st.radio(
            "Entry Mode",
            ["Simple Capital Call", "Net Capital Call / Equalisation Bundle"],
            horizontal=True,
            key=f"call_entry_mode_{fund['id']}"
        )

        for warning in st.session_state.get(f"cc_ai_prefill_warnings_{fund['id']}", []):
            st.warning(warning)

        if entry_mode == "Simple Capital Call":
            ai_data = st.session_state.get(f"cc_ai_result_{fund['id']}", {})
        
            def_call_date = parse_ai_date(ai_data.get("call_date")) or date.today()
            def_pay_date = parse_ai_date(ai_data.get("payment_date")) or date.today()
            def_call_num = int(normalize_amount(ai_data.get("call_number")) or (len(calls) + 1))
            tx_options = ["call", "repayment", "distribution"]
            def_tx_type = str(ai_data.get("transaction_type") or "call").strip().lower()
            if def_tx_type not in tx_options:
                def_tx_type = "call"

            with st.form(f"add_call_{fund['id']}"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    call_num = st.number_input("Call Number", min_value=1, value=def_call_num)
                    call_date = st.date_input("Call Date", value=def_call_date)
                    payment_date = st.date_input("Payment Date", value=def_pay_date)
                
                    tx_type = st.selectbox(
                        "Transaction Type",
                        tx_options,
                        index=tx_options.index(def_tx_type),
                        format_func=lambda x: {
                            "call": "💰 Capital Call",
                            "repayment": "🔄 Capital Repayment (Recallable)",
                            "distribution": "📤 Capital Distribution (Non-recallable)"
                        }[x]
                    )
                
                with col2:
                    amount = st.number_input("Cash Amount (Net Call)", min_value=0.0, value=normalize_amount(ai_data.get("amount")))
                    investments = st.number_input("Investments (Commitment Impact)", min_value=0.0, value=normalize_amount(ai_data.get("investments")))
                    mgmt_fee = st.number_input("Mgmt Fee", min_value=0.0, value=normalize_amount(ai_data.get("mgmt_fee")))
                
                with col3:
                    fund_expenses = st.number_input("Fund Expenses & Other", min_value=0.0, value=normalize_amount(ai_data.get("fund_expenses")))
                
                    default_recall = bool(ai_data.get("affects_called", tx_type == "repayment"))
                    is_recallable = st.checkbox(
                        "Reduces Total Called", 
                        value=default_recall,
                        help="Check if this amount reduces the Total Called (usually True for Repayment, False for Distribution)"
                    )
                
                    equalisation_interest = st.number_input(
                        "Equalisation Interest", 
                        min_value=0.0, 
                        value=normalize_amount(ai_data.get("equalisation_interest")),
                        help="Interest paid by late entrants - does NOT count toward Total Called"
                    )
                
                    is_future = st.checkbox("Future Call (Show Alert)")
                    notes = st.text_input("Notes", value=str(ai_data.get("notes") or ""))
                
                if st.form_submit_button("Save Call to System", type="primary"):
                    try:
                        get_supabase().table("capital_calls").insert({
                            "fund_id": fund["id"], 
                            "call_number": call_num,
                            "call_date": str(call_date), 
                            "payment_date": str(payment_date),
                            "transaction_type": tx_type,
                            "amount": amount, 
                            "investments": investments,
                            "mgmt_fee": mgmt_fee, 
                            "fund_expenses": fund_expenses,
                            "is_recallable": is_recallable,
                            "affects_called": is_recallable,
                            "equalisation_interest": equalisation_interest,
                            "is_future": is_future, 
                            "notes": notes
                        }).execute()
                                
                        st.session_state.pop(f"cc_ai_result_{fund['id']}", None)
                        st.success("✅ Saved!")
                        clear_cache_and_rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

        else:
            st.markdown("**Net Capital Call / Equalisation Bundle**")
            fund_name_for_bundle = str(fund.get("name") or "").strip()
            st.info(f"You are entering a bundle for: {fund_name_for_bundle or 'Unnamed fund'} ({fund.get('currency', 'USD')})")
            valid_bundle_fund = bool(fund_name_for_bundle)
            if not valid_bundle_fund:
                st.error("Cannot save bundle for an unnamed fund. Please select a valid fund.")

            b_col1, b_col2, b_col3 = st.columns(3)
            with b_col1:
                bundle_call_num = st.number_input(
                    "Bundle Call Number",
                    min_value=1,
                    value=len(calls) + 1,
                    key=f"bundle_call_num_{fund['id']}"
                )
                bundle_call_date = st.date_input(
                    "Bundle Call Date",
                    value=date.today(),
                    key=f"bundle_call_date_{fund['id']}"
                )
            with b_col2:
                bundle_payment_date = st.date_input(
                    "Bundle Payment Date",
                    value=date.today(),
                    key=f"bundle_payment_date_{fund['id']}"
                )
                bundle_is_future = st.checkbox(
                    "Bundle Future Call",
                    key=f"bundle_future_{fund['id']}"
                )
            with b_col3:
                bundle_note_prefix = st.text_input(
                    "Shared Note Prefix",
                    value="Net Capital Call / Equalisation Bundle",
                    key=f"bundle_note_prefix_{fund['id']}"
                )
                expected_wire = st.number_input(
                    "Optional Expected Wire Amount",
                    value=0.0,
                    key=f"bundle_expected_wire_{fund['id']}"
                )

            component_types = CAPITAL_CALL_COMPONENT_TYPES

            component_rows = []
            st.markdown("**Components**")
            h_enabled, h_type, h_desc, h_cash, h_commit, h_eq = st.columns([0.7, 2.2, 2.6, 1.4, 1.4, 1.4])
            h_enabled.markdown("Use")
            h_type.markdown("Component Type")
            h_desc.markdown("Description")
            h_cash.markdown("Cash Amount")
            h_commit.markdown("Commitment Impact")
            h_eq.markdown("Equalisation Interest")
            for row_idx in range(BUNDLE_COMPONENT_ROW_LIMIT):
                c_enabled, c_type, c_desc, c_cash, c_commit, c_eq = st.columns([0.7, 2.2, 2.6, 1.4, 1.4, 1.4])
                with c_enabled:
                    enabled = st.checkbox("Use", key=f"bundle_enabled_{fund['id']}_{row_idx}")
                with c_type:
                    component_type = st.selectbox(
                        "Component Type",
                        component_types,
                        key=f"bundle_type_{fund['id']}_{row_idx}",
                        label_visibility="collapsed"
                    )
                with c_desc:
                    description = st.text_input(
                        "Description",
                        key=f"bundle_desc_{fund['id']}_{row_idx}",
                        label_visibility="collapsed"
                    )
                with c_cash:
                    cash_amount = st.number_input(
                        "Cash Amount",
                        min_value=0.0,
                        value=0.0,
                        key=f"bundle_cash_{fund['id']}_{row_idx}",
                        label_visibility="collapsed"
                    )
                with c_commit:
                    commitment_impact = st.number_input(
                        "Commitment Impact",
                        min_value=0.0,
                        value=0.0,
                        key=f"bundle_commit_{fund['id']}_{row_idx}",
                        label_visibility="collapsed"
                    )
                with c_eq:
                    row_eq_interest = st.number_input(
                        "Equalisation Interest",
                        min_value=0.0,
                        value=0.0,
                        key=f"bundle_eq_{fund['id']}_{row_idx}",
                        label_visibility="collapsed"
                    )

                if enabled:
                    component_rows.append({
                        "component_type": component_type,
                        "description": description,
                        "cash_amount": cash_amount,
                        "commitment_impact": commitment_impact,
                        "equalisation_interest": row_eq_interest
                    })

            validation_errors = []
            preview_rows = []
            rows_to_insert = []
            net_wire = 0.0

            if not component_rows:
                validation_errors.append("Add at least one enabled component.")

            for idx, row in enumerate(component_rows, start=1):
                component_type = row["component_type"]
                cash_amount = float(row["cash_amount"] or 0)
                commitment_impact = float(row["commitment_impact"] or 0)
                row_eq_interest = float(row["equalisation_interest"] or 0)
                description = row["description"].strip()

                if cash_amount < 0 or commitment_impact < 0 or row_eq_interest < 0:
                    validation_errors.append(f"Component {idx}: amounts cannot be negative.")

                transaction_type = "call"
                amount = cash_amount
                investments = commitment_impact
                affects_called = False
                eq_interest = 0.0
                component_note = description or component_type

                if component_type == "Gross capital call":
                    if row_eq_interest > 0:
                        validation_errors.append(f"Component {idx}: use a separate equalisation interest component for interest outside commitment.")
                    if cash_amount <= 0:
                        validation_errors.append(f"Component {idx}: gross capital call requires a cash amount.")
                    if commitment_impact <= 0:
                        validation_errors.append(f"Component {idx}: gross capital call requires a commitment impact.")
                elif component_type == "Recallable repayment":
                    transaction_type = "repayment"
                    amount = cash_amount
                    investments = 0.0
                    affects_called = True
                    if commitment_impact > 0 or row_eq_interest > 0:
                        validation_errors.append(f"Component {idx}: recallable repayment should only use cash amount.")
                    if cash_amount <= 0:
                        validation_errors.append(f"Component {idx}: recallable repayment requires a cash amount.")
                elif component_type == "Non-recallable distribution":
                    transaction_type = "distribution"
                    amount = cash_amount
                    investments = 0.0
                    if commitment_impact > 0 or row_eq_interest > 0:
                        validation_errors.append(f"Component {idx}: non-recallable distribution should only use cash amount.")
                    if cash_amount <= 0:
                        validation_errors.append(f"Component {idx}: non-recallable distribution requires a cash amount.")
                elif component_type == "Realised gain distribution":
                    transaction_type = "distribution"
                    amount = cash_amount
                    investments = 0.0
                    if commitment_impact > 0 or row_eq_interest > 0:
                        validation_errors.append(f"Component {idx}: realised gain distribution should only use cash amount.")
                    if cash_amount <= 0:
                        validation_errors.append(f"Component {idx}: realised gain distribution requires a cash amount.")
                    if "realised gain" not in component_note.lower():
                        component_note = f"Realised gain - {component_note}"
                elif component_type == "Equalisation interest outside commitment":
                    amount = 0.0
                    investments = 0.0
                    eq_interest = row_eq_interest
                    if cash_amount > 0 or commitment_impact > 0:
                        validation_errors.append(f"Component {idx}: equalisation interest outside commitment should only use equalisation interest.")
                    if row_eq_interest <= 0:
                        validation_errors.append(f"Component {idx}: equalisation interest component requires an interest amount.")

                if transaction_type == "call":
                    net_wire += amount + eq_interest
                else:
                    net_wire -= amount

                note = f"{bundle_note_prefix}: {component_note}" if bundle_note_prefix else component_note
                preview_rows.append({
                    "Component": component_type,
                    "Transaction Type": transaction_type,
                    "Amount": amount,
                    "Investments": investments,
                    "Equalisation Interest": eq_interest,
                    "Affects Called": affects_called,
                    "Notes": note
                })
                rows_to_insert.append({
                    "fund_id": fund["id"],
                    "call_number": bundle_call_num,
                    "call_date": str(bundle_call_date),
                    "payment_date": str(bundle_payment_date),
                    "transaction_type": transaction_type,
                    "amount": amount,
                    "investments": investments,
                    "mgmt_fee": 0.0,
                    "fund_expenses": 0.0,
                    "is_recallable": affects_called,
                    "affects_called": affects_called,
                    "equalisation_interest": eq_interest,
                    "is_future": bundle_is_future,
                    "notes": note
                })

            if preview_rows:
                st.markdown("**Preview Rows to Insert**")
                st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

            st.metric("Calculated Net Wire Amount", format_currency(net_wire, currency_sym))
            expected_wire_supplied = expected_wire != 0 or st.session_state.get(f"bundle_ai_expected_wire_set_{fund['id']}", False)
            if expected_wire_supplied and abs(net_wire - expected_wire) > 0.01:
                st.warning(
                    f"Expected wire differs by {format_currency(abs(net_wire - expected_wire), currency_sym)}. "
                    "Review the components before saving."
                )

            if validation_errors:
                for err in validation_errors:
                    st.error(err)

            confirm_bundle_fund = False
            if valid_bundle_fund:
                confirm_bundle_fund = st.checkbox(
                    "I confirm this notice belongs to the selected fund.",
                    key=f"confirm_bundle_fund_{fund['id']}"
                )

            if valid_bundle_fund and st.button("Save Bundle Components", type="primary", key=f"save_bundle_{fund['id']}"):
                if validation_errors or not confirm_bundle_fund:
                    if not confirm_bundle_fund:
                        st.error("Confirm this notice belongs to the selected fund before saving.")
                    st.error("Bundle was not saved. Fix validation errors above and try again.")
                else:
                    try:
                        get_supabase().table("capital_calls").insert(rows_to_insert).execute()
                        st.success("✅ Bundle components saved!")
                        clear_cache_and_rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    with tab2:
        if dists:
            st.markdown("**Distributions List**")
            for d in dists:
                with st.expander(f"Dist #{d.get('dist_number')} | {d.get('dist_date','')} | {format_currency(float(d.get('amount',0)), currency_sym)}", expanded=False):
                    col1, col2 = st.columns([4,1])
                    with col1:
                        st.write(f"Type: {d.get('dist_type','').capitalize()} | Amount: {format_currency(float(d.get('amount',0)), currency_sym)}")
                    with col2:
                        if st.button("🗑️", key=f"del_dist_{d['id']}", help="Delete Distribution"):
                            st.session_state[f"confirm_del_dist_{d['id']}"] = True
                    if st.session_state.get(f"confirm_del_dist_{d['id']}"):
                        st.warning("Delete this Distribution?")
                        dc1, dc2 = st.columns(2)
                        with dc1:
                            if st.button("✅ Delete", key=f"yes_dist_{d['id']}"):
                                try:
                                    log_action("DELETE", "distributions", f"Deleted distribution #{d.get('dist_number')} from {fund['name']}", d)
                                    get_supabase().table("distributions").delete().eq("id", d["id"]).execute()
                                    clear_cache_and_rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")
                        with dc2:
                            if st.button("❌ Cancel", key=f"no_dist_{d['id']}"):
                                st.session_state.pop(f"confirm_del_dist_{d['id']}", None)
                                st.rerun()
        else:
            st.info("No distributions yet")

        st.divider()
        st.markdown("**➕ Add Distribution**")
        with st.form(f"add_dist_{fund['id']}"):
            col1, col2 = st.columns(2)
            with col1:
                dist_num = st.number_input("Number", min_value=1, value=len(dists)+1)
                dist_date = st.date_input("Date")
            with col2:
                dist_amount = st.number_input("Amount", min_value=0.0)
                dist_type = st.selectbox("Type", ["income", "capital", "recycle"])
            if st.form_submit_button("Save", type="primary"):
                try:
                    get_supabase().table("distributions").insert({
                        "fund_id": fund["id"], "dist_number": dist_num,
                        "dist_date": str(dist_date), "amount": dist_amount, "dist_type": dist_type.lower()
                    }).execute()
                    st.success("✅ Saved!")
                    clear_cache_and_rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    with tab3:
        if reports:
            st.markdown("**Quarterly Reports**")
            for r in reports:
                with st.expander(f"Q{r['quarter']}/{r['year']} | TVPI: {r.get('tvpi','—')} | IRR: {r.get('irr','—')}%", expanded=False):
                    col1, col_edit, col_del = st.columns([3, 1, 1])
                    with col1:
                        st.write(f"NAV (Fund): {format_currency(float(r.get('nav',0)), currency_sym)} | DPI: {r.get('dpi','—')} | RVPI: {r.get('rvpi','—')}")
                        if r.get('notes'):
                            st.write(f"Notes: {r.get('notes')}")
                    with col_edit:
                        if st.button("✏️ Edit", key=f"edit_rep_btn_{r['id']}"):
                            st.session_state[f"editing_rep_{r['id']}"] = True
                    with col_del:
                        if st.button("🗑️ Delete", key=f"del_rep_btn_{r['id']}"):
                            st.session_state[f"confirm_del_rep_{r['id']}"] = True
                            
                    if st.session_state.get(f"confirm_del_rep_{r['id']}"):
                        st.warning("Delete this report?")
                        rc1, rc2 = st.columns(2)
                        with rc1:
                            if st.button("✅ Yes, Delete", key=f"yes_rep_{r['id']}"):
                                try:
                                    log_action("DELETE", "quarterly_reports", f"Deleted report Q{r['quarter']}/{r['year']} of {fund['name']}", r)
                                    get_supabase().table("quarterly_reports").delete().eq("id", r["id"]).execute()
                                    st.session_state.pop(f"confirm_del_rep_{r['id']}", None)
                                    clear_cache_and_rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")
                        with rc2:
                            if st.button("❌ Cancel", key=f"no_rep_{r['id']}"):
                                st.session_state.pop(f"confirm_del_rep_{r['id']}", None)
                                st.rerun()

                    if st.session_state.get(f"editing_rep_{r['id']}"):
                        with st.form(f"edit_rep_form_{r['id']}"):
                            st.markdown("**✏️ Edit Report Details**")
                            e_c1, e_c2, e_c3 = st.columns(3)
                            with e_c1:
                                edit_year = st.number_input("Year", value=int(r['year']), min_value=2020, max_value=2030)
                                edit_quarter = st.selectbox("Quarter", [1, 2, 3, 4], index=[1,2,3,4].index(int(r['quarter'])))
                                try:
                                    def_rep_date = datetime.fromisoformat(str(r['report_date'])).date() if r.get('report_date') else date.today()
                                except:
                                    def_rep_date = date.today()
                                edit_rep_date = st.date_input("Report Date", value=def_rep_date)
                            with e_c2:
                                edit_nav = st.number_input("NAV (Fund Level)", value=float(r.get('nav') or 0.0), min_value=0.0)
                                edit_tvpi = st.number_input("TVPI", value=float(r.get('tvpi') or 0.0), step=0.01, format="%.2f")
                                edit_dpi = st.number_input("DPI", value=float(r.get('dpi') or 0.0), step=0.01, format="%.2f")
                            with e_c3:
                                edit_rvpi = st.number_input("RVPI", value=float(r.get('rvpi') or 0.0), step=0.01, format="%.2f")
                                edit_irr = st.number_input("IRR %", value=float(r.get('irr') or 0.0), step=0.1, format="%.1f")
                                edit_notes = st.text_area("Notes", value=r.get('notes') or "")
                            
                            save_c1, save_c2 = st.columns(2)
                            with save_c1:
                                if st.form_submit_button("💾 Save Changes", type="primary"):
                                    try:
                                        log_action("UPDATE", "quarterly_reports", f"Updated report Q{r['quarter']}/{r['year']}", r)
                                        get_supabase().table("quarterly_reports").update({
                                            "year": edit_year, "quarter": edit_quarter,
                                            "report_date": str(edit_rep_date), "nav": edit_nav,
                                            "tvpi": edit_tvpi, "dpi": edit_dpi, "rvpi": edit_rvpi, 
                                            "irr": edit_irr, "notes": edit_notes
                                        }).eq("id", r["id"]).execute()
                                        st.session_state.pop(f"editing_rep_{r['id']}", None)
                                        clear_cache_and_rerun()
                                    except Exception as e:
                                        st.error(f"Error: {e}")
                            with save_c2:
                                if st.form_submit_button("❌ Close"):
                                    st.session_state.pop(f"editing_rep_{r['id']}", None)
                                    st.rerun()

            if len(reports) > 1:
                labels = [f"Q{r['quarter']}/{r['year']}" for r in reports]
                fig = go.Figure()
                if any(r.get("tvpi") for r in reports):
                    fig.add_trace(go.Scatter(x=labels, y=[float(r.get("tvpi")) for r in reports], name="TVPI", line=dict(color="#4ade80")))
                if any(r.get("dpi") for r in reports):
                    fig.add_trace(go.Scatter(x=labels, y=[float(r.get("dpi")) for r in reports], name="DPI", line=dict(color="#60a5fa")))
                fig.update_layout(title="Performance Over Time", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='white')
                st.plotly_chart(fig, use_container_width=True, key=f"perf_chart_{fund['id']}")
        else:
            st.info("No quarterly reports for this fund yet.")

        st.divider()
        st.markdown("**🤖 Add Quarterly Report from File (AI Extraction)**")
        uploaded_rep_file = st.file_uploader("Upload Quarterly Report (PDF / Excel / CSV)", type=["pdf", "xlsx", "xls", "csv"], key=f"rep_uploader_{fund['id']}")
        
        if uploaded_rep_file:
            if st.button("Analyze Document Now", type="primary", key=f"rep_analyze_btn_{fund['id']}"):
                with st.spinner("Claude is analyzing the report..."):
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
                        st.success("✅ Data extracted successfully! Please review and confirm in the form below.")
                    except Exception as e:
                        st.error(f"Error analyzing document: {e}. (If Excel, ensure openpyxl is in requirements.txt)")

        st.divider()
        st.markdown("**➕ Or Enter Details Manually**")
        
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
                year = st.number_input("Year", value=def_year, min_value=2020, max_value=2030)
                quarter = st.selectbox("Quarter", [1, 2, 3, 4], index=[1,2,3,4].index(def_quarter))
                report_date = st.date_input("Report Date", value=def_rep_date)
            with col2:
                nav = st.number_input("NAV (Fund Level)", min_value=0.0, value=float(ai_rep.get("nav") or 0.0))
                tvpi = st.number_input("TVPI", min_value=0.0, step=0.01, format="%.2f", value=float(ai_rep.get("tvpi") or 0.0))
                dpi = st.number_input("DPI", min_value=0.0, step=0.01, format="%.2f", value=float(ai_rep.get("dpi") or 0.0))
            with col3:
                rvpi = st.number_input("RVPI", min_value=0.0, step=0.01, format="%.2f", value=float(ai_rep.get("rvpi") or 0.0))
                irr = st.number_input("IRR %", step=0.1, format="%.1f", value=float(ai_rep.get("irr") or 0.0))
                notes = st.text_area("Notes")
                
            if st.form_submit_button("Save Report", type="primary"):
                try:
                    get_supabase().table("quarterly_reports").upsert({
                        "fund_id": fund["id"], "year": year, "quarter": quarter,
                        "report_date": str(report_date), "nav": nav,
                        "tvpi": tvpi, "dpi": dpi, "rvpi": rvpi, "irr": irr, "notes": notes
                    }).execute()
                    
                    st.session_state.pop(f"rep_ai_result_{fund['id']}", None)
                    st.success("✅ Saved!")
                    clear_cache_and_rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

def show_investors():
    st.title("👥 Manage Investors & FOF Calls")
    
    currency_sym = "$" 
    sb = get_supabase()

    investors = get_investors()
    lp_calls = get_lp_calls()
    payments = get_lp_payments()

    col_add_inv, col_manage_inv = st.columns(2)
    
    with col_add_inv:
        with st.expander("➕ Add Investor(s) to FOF"):
            tab_manual, tab_bulk = st.tabs(["Manual Entry", "Excel Upload"])
            with tab_manual:
                with st.form("add_lp_form"):
                    c1, c2 = st.columns(2)
                    with c1:
                        inv_name = st.text_input("Investor Name")
                    with c2:
                        inv_commit = st.number_input(f"Commitment Amount ({currency_sym})", min_value=0.0, step=500000.0)
                    if st.form_submit_button("Save Investor", type="primary"):
                        try:
                            sb.table("investors").insert({"name": inv_name, "commitment": inv_commit}).execute()
                            log_action("INSERT", "investors", f"Added new investor: {inv_name}", {"commitment": inv_commit})
                            st.success("Investor added!")
                            clear_cache_and_rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
            with tab_bulk:
                st.markdown("<small>Upload file with 2 columns: Column A = <b>Investor Name</b>, Column B = <b>Commitment Amount</b></small>", unsafe_allow_html=True)
                uploaded_inv_file = st.file_uploader("Select File (Excel / CSV)", type=["xlsx", "xls", "csv"], key="inv_uploader")
                if uploaded_inv_file:
                    if st.button("Load Investors to System", type="primary", use_container_width=True):
                        with st.spinner("Loading investors..."):
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
                                        
                                        commit_str = str(row.iloc[1]).replace(',', '').replace('$', '').replace('€', '').strip()
                                        try:
                                            commit_val = float(commit_str)
                                        except:
                                            commit_val = 0.0
                                        
                                        sb.table("investors").insert({"name": name_val, "commitment": commit_val}).execute()
                                        count += 1
                                    
                                    log_action("INSERT", "investors", f"Bulk uploaded {count} investors", {})
                                    st.success(f"✅ {count} investors successfully added!")
                                    clear_cache_and_rerun()
                                else:
                                    st.error("File must contain at least 2 columns.")
                            except Exception as e:
                                st.error(f"Error reading file: {e}")

    with col_manage_inv:
        with st.expander("⚙️ Manage Existing Investors (Edit / Delete)"):
            if not investors:
                st.write("No investors in the system.")
            for inv in investors:
                c1, c2, c3, c4 = st.columns([4, 3, 1, 1])
                with c1:
                    st.write(f"**{inv['name']}**")
                with c2:
                    st.write(format_currency(float(inv.get("commitment", 0)), currency_sym))
                with c3:
                    if st.button("✏️", key=f"edit_inv_btn_{inv['id']}", help="Edit Investor"):
                        st.session_state[f"editing_inv_{inv['id']}"] = True
                with c4:
                    if st.button("🗑️", key=f"del_inv_btn_{inv['id']}", help="Delete Investor"):
                        st.session_state[f"confirm_del_inv_{inv['id']}"] = True
                
                if st.session_state.get(f"confirm_del_inv_{inv['id']}"):
                    st.warning(f"Delete '{inv['name']}'?")
                    cd1, cd2 = st.columns(2)
                    with cd1:
                        if st.button("✅ Yes", key=f"yes_del_inv_{inv['id']}"):
                            try:
                                log_action("DELETE", "investors", f"Deleted investor: {inv['name']}", inv)
                                sb.table("investors").delete().eq("id", inv["id"]).execute()
                                st.session_state.pop(f"confirm_del_inv_{inv['id']}", None)
                                clear_cache_and_rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                    with cd2:
                        if st.button("❌ Cancel", key=f"no_del_inv_{inv['id']}"):
                            st.session_state.pop(f"confirm_del_inv_{inv['id']}", None)
                            st.rerun()

                if st.session_state.get(f"editing_inv_{inv['id']}"):
                    with st.form(f"edit_inv_form_{inv['id']}"):
                        new_name = st.text_input("Investor Name", value=inv["name"])
                        new_commit = st.number_input("Commitment", value=float(inv.get("commitment", 0)), step=500000.0)
                        ce1, ce2 = st.columns(2)
                        with ce1:
                            if st.form_submit_button("💾 Save Changes"):
                                try:
                                    log_action("UPDATE", "investors", f"Updated investor: {inv['name']} to {new_name}", inv)
                                    sb.table("investors").update({"name": new_name, "commitment": new_commit}).eq("id", inv["id"]).execute()
                                    st.session_state.pop(f"editing_inv_{inv['id']}", None)
                                    clear_cache_and_rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")
                        with ce2:
                            if st.form_submit_button("❌ Close"):
                                st.session_state.pop(f"editing_inv_{inv['id']}", None)
                                st.rerun()
                    st.divider()

    st.divider()
    
    col_t_hdr, col_t_export = st.columns([4, 1])
    with col_t_hdr:
        st.markdown("### 📋 Investor Payments Status (Check box for paid)")
    
    if not investors:
        st.info("No investors defined. Add an investor above.")
        return

    data = []
    col_mapping = {}
    total_fund_commitment = 0
    
    for inv in investors:
        inv_commit = float(inv.get("commitment", 0))
        total_fund_commitment += inv_commit
        row = {
            "id": inv["id"],
            "Investor Name": inv["name"],
            "Commitment": format_currency(inv_commit, currency_sym)
        }
        for c in lp_calls:
            col_name = f"{c['call_date']} ({c['call_pct']}%)"
            col_mapping[col_name] = c
            payment = next((p for p in payments if p["lp_call_id"] == c["id"] and p["investor_id"] == inv["id"]), None)
            row[col_name] = payment["is_paid"] if payment else False
        data.append(row)

    df = pd.DataFrame(data)
    
    with col_t_export:
        excel_data = convert_df_to_excel(df.drop(columns=["id"], errors="ignore"))
        st.download_button(
            label="📥 Export to Excel", 
            data=excel_data, 
            file_name=f"LP_Payments_Status_{date.today()}.xlsx", 
            use_container_width=True
        )
    
    edited_df = st.data_editor(
        df,
        column_config={"id": None},
        disabled=["Investor Name", "Commitment"],
        hide_index=True,
        use_container_width=True,
        key="lp_global_editor"
    )

    if st.button("💾 Save Payment Statuses", type="primary"):
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
            st.success("✅ Payment statuses successfully updated!")
            clear_cache_and_rerun()
        except Exception as e:
            st.error(f"Update error: {e}")

    st.divider()
    st.markdown("### 📊 FOF Collection Summary")
    
    col_sum1, col_sum2 = st.columns([1, 3])
    with col_sum1:
        st.metric("Total LP Commitments", format_currency(total_fund_commitment, currency_sym))
    
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
                        paid_commit += float(inv.get("commitment", 0))
                
                total_paid_amount = paid_commit * call_pct
                outstanding = total_called_amount - total_paid_amount
                
                summary_data.append({
                    "Call": f"{c['call_date']} ({c['call_pct']}%)",
                    "Total Required": format_currency(total_called_amount, currency_sym),
                    "Total Received": format_currency(total_paid_amount, currency_sym),
                    "Outstanding Balance": format_currency(outstanding, currency_sym)
                })
            st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)
        else:
            st.info("No active capital calls yet.")

    st.divider()
    st.markdown("### ➕ Manage LP Capital Calls")
    
    col_call_add, col_call_manage = st.columns([1, 1])
    
    with col_call_add:
        with st.form("new_global_lp_call"):
            st.markdown("**Create New LP Call**")
            new_call_date = st.date_input("Call Date")
            new_call_pct = st.number_input("Percentage of Commitment (%)", min_value=0.0, max_value=100.0, step=0.1)
            if st.form_submit_button("Add LP Call", use_container_width=True):
                try:
                    sb.table("lp_calls").insert({
                        "call_date": str(new_call_date),
                        "call_pct": new_call_pct
                    }).execute()
                    st.success("✅ New LP Call added to the table!")
                    clear_cache_and_rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    with col_call_manage:
        with st.expander("⚙️ Existing LP Calls (Edit / Delete)"):
            if not lp_calls:
                st.write("No existing LP calls.")
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
                    st.warning("Delete this LP call?")
                    d_c1, d_c2 = st.columns(2)
                    with d_c1:
                        if st.button("✅ Yes", key=f"yes_del_lpc_{c['id']}"):
                            try:
                                log_action("DELETE", "lp_calls", f"Deleted LP capital call: {c['call_date']}", c)
                                sb.table("lp_calls").delete().eq("id", c["id"]).execute()
                                st.session_state.pop(f"confirm_del_lpc_{c['id']}", None)
                                clear_cache_and_rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                    with d_c2:
                        if st.button("❌ Cancel", key=f"no_del_lpc_{c['id']}"):
                            st.session_state.pop(f"confirm_del_lpc_{c['id']}", None)
                            st.rerun()

                if st.session_state.get(f"editing_lpc_{c['id']}"):
                    with st.form(f"edit_lpc_form_{c['id']}"):
                        try:
                            def_date = datetime.fromisoformat(str(c['call_date'])).date()
                        except:
                            def_date = date.today()
                        edit_date = st.date_input("Date", value=def_date)
                        edit_pct = st.number_input("Percentage", value=float(c['call_pct']))
                        e_c1, e_c2 = st.columns(2)
                        with e_c1:
                            if st.form_submit_button("💾 Save"):
                                try:
                                    log_action("UPDATE", "lp_calls", f"Updated LP capital call: {c['call_date']}", c)
                                    sb.table("lp_calls").update({"call_date": str(edit_date), "call_pct": edit_pct}).eq("id", c["id"]).execute()
                                    st.session_state.pop(f"editing_lpc_{c['id']}", None)
                                    clear_cache_and_rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")
                        with e_c2:
                            if st.form_submit_button("❌ Close"):
                                st.session_state.pop(f"editing_lpc_{c['id']}", None)
                                st.rerun()
                    st.divider()

def show_reports():
    st.title("📈 Reports & Analytics")
    
    st.markdown("""
    <div class="dashboard-header">
    <h1 style="color:white;margin:0;">📈 Portfolio Reports & Analytics</h1>
    <p style="color:#94a3b8;margin:4px 0 0 0;">Comprehensive view of all fund performance metrics</p>
    </div>
    """, unsafe_allow_html=True)
    
    sb = get_supabase()
    funds = get_funds()
    all_reports = get_quarterly_reports(None)
    
    st.divider()
    col_add, col_summary = st.columns([1, 1])
    
    with col_add:
        with st.expander("➕ Add / Upload Quarterly Reports"):
            fund_options = {f["name"]: f["id"] for f in funds}
            if not fund_options:
                st.warning("No funds in portfolio. Add a fund first.")
            else:
                tab_manual, tab_upload = st.tabs(["Manual Entry", "Upload & AI Extract"])
                
                with tab_manual:
                    with st.form("manual_report_form"):
                        st.markdown("**Add Report Manually**")
                        selected_fund = st.selectbox("Select Fund", list(fund_options.keys()))
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            year = st.number_input("Year", min_value=2020, max_value=2030, value=2025)
                            quarter = st.selectbox("Quarter", [1, 2, 3, 4])
                            report_date = st.date_input("Report Date")
                        with col2:
                            nav = st.number_input("NAV (Fund Level)", min_value=0.0)
                            tvpi = st.number_input("TVPI", min_value=0.0, step=0.01, format="%.2f")
                            dpi = st.number_input("DPI", min_value=0.0, step=0.01, format="%.2f")
                        
                        col3, col4 = st.columns(2)
                        with col3:
                            rvpi = st.number_input("RVPI", min_value=0.0, step=0.01, format="%.2f")
                        with col4:
                            irr = st.number_input("IRR %", step=0.1, format="%.1f")
                        
                        notes = st.text_area("Notes")
                        
                        if st.form_submit_button("💾 Save Report", type="primary"):
                            try:
                                fund_id = fund_options[selected_fund]
                                sb.table("quarterly_reports").insert({
                                    "fund_id": fund_id,
                                    "year": year,
                                    "quarter": quarter,
                                    "report_date": str(report_date),
                                    "nav": nav,
                                    "tvpi": tvpi,
                                    "dpi": dpi,
                                    "rvpi": rvpi,
                                    "irr": irr,
                                    "notes": notes
                                }).execute()
                                log_action("INSERT", "quarterly_reports", f"Added Q{quarter}/{year} report for {selected_fund}", {})
                                st.success("✅ Report saved!")
                                clear_cache_and_rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                
                with tab_upload:
                    st.markdown("**Upload Report File (PDF/Excel/CSV)**")
                    selected_fund_upload = st.selectbox("Select Fund", list(fund_options.keys()), key="upload_fund")
                    uploaded_file = st.file_uploader("Upload File", type=["pdf", "xlsx", "xls", "csv"])
                    
                    if uploaded_file:
                        if st.button("🤖 Analyze with AI", type="primary"):
                            with st.spinner("Claude is analyzing..."):
                                try:
                                    file_bytes = uploaded_file.read()
                                    file_name = uploaded_file.name
                                    
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
                                    st.session_state.report_ai_result = ai_result
                                    st.success("✅ Extracted! Review below and save:")
                                    
                                    with st.form("ai_report_confirm"):
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            year_ai = st.number_input("Year", value=int(ai_result.get("year") or 2025))
                                            quarter_ai = st.selectbox("Quarter", [1,2,3,4], index=[1,2,3,4].index(int(ai_result.get("quarter") or 1)))
                                            nav_ai = st.number_input("NAV", value=float(ai_result.get("nav") or 0.0))
                                        with col2:
                                            tvpi_ai = st.number_input("TVPI", value=float(ai_result.get("tvpi") or 0.0), step=0.01, format="%.2f")
                                            dpi_ai = st.number_input("DPI", value=float(ai_result.get("dpi") or 0.0), step=0.01, format="%.2f")
                                            rvpi_ai = st.number_input("RVPI", value=float(ai_result.get("rvpi") or 0.0), step=0.01, format="%.2f")
                                        
                                        irr_ai = st.number_input("IRR %", value=float(ai_result.get("irr") or 0.0), step=0.1, format="%.1f")
                                        
                                        if st.form_submit_button("💾 Confirm & Save", type="primary"):
                                            try:
                                                fund_id = fund_options[selected_fund_upload]
                                                sb.table("quarterly_reports").insert({
                                                    "fund_id": fund_id,
                                                    "year": year_ai,
                                                    "quarter": quarter_ai,
                                                    "report_date": str(date.today()),
                                                    "nav": nav_ai,
                                                    "tvpi": tvpi_ai,
                                                    "dpi": dpi_ai,
                                                    "rvpi": rvpi_ai,
                                                    "irr": irr_ai
                                                }).execute()
                                                st.success("✅ Report saved!")
                                                st.session_state.pop("report_ai_result", None)
                                                clear_cache_and_rerun()
                                            except Exception as e:
                                                st.error(f"Error: {e}")
                                except Exception as e:
                                    st.error(f"Analysis error: {e}")
    
    with col_summary:
        with st.expander("📊 Portfolio Summary Statistics"):
            if all_reports:
                latest_reports = {}
                for r in all_reports:
                    fid = r["fund_id"]
                    if fid not in latest_reports:
                        latest_reports[fid] = r
                    else:
                        curr = latest_reports[fid]
                        if r["year"] > curr["year"] or (r["year"] == curr["year"] and r["quarter"] > curr["quarter"]):
                            latest_reports[fid] = r
                
                avg_tvpi = sum(float(r.get("tvpi") or 0) for r in latest_reports.values()) / len(latest_reports) if latest_reports else 0
                avg_dpi = sum(float(r.get("dpi") or 0) for r in latest_reports.values()) / len(latest_reports) if latest_reports else 0
                avg_irr = sum(float(r.get("irr") or 0) for r in latest_reports.values()) / len(latest_reports) if latest_reports else 0
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Avg TVPI", f"{avg_tvpi:.2f}x")
                with col2:
                    st.metric("Avg DPI", f"{avg_dpi:.2f}x")
                with col3:
                    st.metric("Avg IRR", f"{avg_irr:.1f}%")
            else:
                st.info("No reports yet")
    
    st.divider()
    
    if not all_reports:
        st.info("📊 No quarterly reports. Add reports above to see analytics.")
        return
    
    st.markdown("### 📋 All Quarterly Reports")
    reports_data = []
    for r in all_reports:
        fund = next((f for f in funds if f["id"] == r["fund_id"]), None)
        if fund:
            reports_data.append({
                "id": r["id"],
                "Fund": fund["name"],
                "Quarter": f"Q{r['quarter']}/{r['year']}",
                "Report Date": r.get("report_date", ""),
                "NAV": format_currency(float(r.get("nav") or 0), "€" if fund.get("currency") == "EUR" else "$"),
                "TVPI": f"{float(r.get('tvpi') or 0):.2f}x",
                "DPI": f"{float(r.get('dpi') or 0):.2f}x",
                "RVPI": f"{float(r.get('rvpi') or 0):.2f}x",
                "IRR": f"{float(r.get('irr') or 0):.1f}%"
            })
    
    if reports_data:
        df = pd.DataFrame(reports_data)
        col_export, col_space = st.columns([1, 5])
        with col_export:
            excel_data = convert_df_to_excel(df.drop(columns=["id"], errors="ignore"))
            st.download_button(
                label="📥 Export Excel",
                data=excel_data,
                file_name=f"Portfolio_Reports_{date.today()}.xlsx",
                use_container_width=True
            )
        
        st.dataframe(df.drop(columns=["id"]), use_container_width=True, hide_index=True)
        
        st.markdown("#### ⚙️ Manage Reports")
        for idx, row in df.iterrows():
            report_id = row["id"]
            with st.expander(f"{row['Fund']} - {row['Quarter']}", expanded=False):
                col_edit, col_del = st.columns([5, 1])
                with col_del:
                    if st.button("🗑️ Delete", key=f"del_rep_{report_id}"):
                        st.session_state[f"confirm_del_report_{report_id}"] = True
                
                if st.session_state.get(f"confirm_del_report_{report_id}"):
                    st.warning("Delete this report?")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅ Yes", key=f"yes_rep_{report_id}"):
                            try:
                                rep = next(r for r in all_reports if r["id"] == report_id)
                                log_action("DELETE", "quarterly_reports", f"Deleted {row['Quarter']} report for {row['Fund']}", rep)
                                sb.table("quarterly_reports").delete().eq("id", report_id).execute()
                                st.session_state.pop(f"confirm_del_report_{report_id}", None)
                                clear_cache_and_rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                    with c2:
                        if st.button("❌ Cancel", key=f"no_rep_{report_id}"):
                            st.session_state.pop(f"confirm_del_report_{report_id}", None)
                            st.rerun()
    
    st.divider()
    st.markdown("### 📈 Performance Trends")
    latest_reports = {}
    for r in all_reports:
        fid = r["fund_id"]
        if fid not in latest_reports:
            latest_reports[fid] = r
        else:
            curr = latest_reports[fid]
            if r["year"] > curr["year"] or (r["year"] == curr["year"] and r["quarter"] > curr["quarter"]):
                latest_reports[fid] = r
    
    fund_names = [f["name"] for f in funds if f["id"] in latest_reports]
    if fund_names:
        tabs = st.tabs(fund_names)
        for i, f in enumerate([fund for fund in funds if fund["id"] in latest_reports]):
            with tabs[i]:
                fund_reports = [r for r in all_reports if r["fund_id"] == f["id"]]
                fund_reports = sorted(fund_reports, key=lambda x: (x["year"], x["quarter"]))
                
                if len(fund_reports) > 1:
                    labels = [f"Q{r['quarter']}/{r['year']}" for r in fund_reports]
                    
                    fig = go.Figure()
                    if any(r.get("tvpi") for r in fund_reports):
                        fig.add_trace(go.Scatter(x=labels, y=[float(r.get("tvpi") or 0) for r in fund_reports], name="TVPI", line=dict(color="#4ade80", width=3), mode='lines+markers'))
                    if any(r.get("dpi") for r in fund_reports):
                        fig.add_trace(go.Scatter(x=labels, y=[float(r.get("dpi") or 0) for r in fund_reports], name="DPI", line=dict(color="#60a5fa", width=3), mode='lines+markers'))
                    if any(r.get("rvpi") for r in fund_reports):
                        fig.add_trace(go.Scatter(x=labels, y=[float(r.get("rvpi") or 0) for r in fund_reports], name="RVPI", line=dict(color="#fbbf24", width=3), mode='lines+markers'))
                    
                    fig.update_layout(title=f"{f['name']} - Multiples Over Time", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#0f172a', font=dict(color='#e2e8f0', size=14, family='Inter'), xaxis=dict(gridcolor='#1e293b'), yaxis=dict(gridcolor='#1e293b', title="Multiple (x)"), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), hovermode='x unified')
                    st.plotly_chart(fig, use_container_width=True)
                    
                    if any(r.get("irr") for r in fund_reports):
                        fig_irr = go.Figure()
                        fig_irr.add_trace(go.Scatter(x=labels, y=[float(r.get("irr") or 0) for r in fund_reports], name="IRR", line=dict(color="#a78bfa", width=3), mode='lines+markers', fill='tozeroy'))
                        fig_irr.update_layout(title=f"{f['name']} - IRR Trend", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#0f172a', font=dict(color='#e2e8f0', size=14, family='Inter'), xaxis=dict(gridcolor='#1e293b'), yaxis=dict(gridcolor='#1e293b', title="IRR (%)"), showlegend=False, hovermode='x unified')
                        st.plotly_chart(fig_irr, use_container_width=True)
                else:
                    st.info("Need at least 2 quarterly reports to show trends.")
# הוסף את הקוד הזה לפני if __name__ == "__main__": (בערך שורה 2341)

def show_pipeline():
    st.title("🔍 Pipeline Funds")
    pipeline = get_pipeline_funds()

    col1, col2, col3 = st.columns([2, 1, 1])
    with col2:
        if st.button("➕ Add Manually", use_container_width=True):
            st.session_state.show_add_pipeline = True
            st.session_state.show_pdf_upload = False
    with col3:
        if st.button("📄 Upload PDF", type="primary", use_container_width=True):
            st.session_state.show_pdf_upload = True
            st.session_state.show_add_pipeline = False

    if st.session_state.get("show_pdf_upload"):
        st.divider()
        st.markdown("### 📄 Automatic PDF Analysis")
        uploaded_pdf = st.file_uploader("Upload Fund Pitch Deck (PDF)", type=["pdf"], key="pdf_uploader")
        if uploaded_pdf:
            if st.button("🤖 Analyze with AI", type="primary"):
                with st.spinner("Claude is analyzing the presentation... (30-60 seconds)"):
                    try:
                        pdf_bytes = uploaded_pdf.read()
                        result = analyze_pdf_with_ai(pdf_bytes)
                        st.session_state.pdf_result = result
                        st.success("✅ Analysis complete!")
                    except Exception as e:
                        st.error(f"Error: {e}")
        if st.session_state.get("pdf_result"):
            r = st.session_state.pdf_result
            st.divider()
            st.markdown("### 📋 Extracted Details – Review and Confirm")
            if r.get("key_highlights"):
                st.info(f"💡 {r.get('key_highlights')}")
            with st.form("pdf_pipeline_form"):
                col1, col2 = st.columns(2)
                with col1:
                    fund_name = st.text_input("Fund Name", value=r.get("fund_name") or "")
                    manager = st.text_input("Manager", value=r.get("manager") or "")
                    strategy_options = ["Growth", "VC", "Tech", "Niche", "Special Situations", "Mid-Market Buyout"]
                    ai_strategy = r.get("strategy", "Growth")
                    strategy_idx = strategy_options.index(ai_strategy) if ai_strategy in strategy_options else 0
                    strategy = st.selectbox("Strategy", strategy_options, index=strategy_idx)
                    geographic = st.text_input("Geographic Focus", value=r.get("geographic_focus") or "")
                    sector = st.text_input("Sector Focus", value=r.get("sector_focus") or "")
                with col2:
                    fund_size = r.get("fund_size_target") or 0
                    target_commitment = st.number_input("Our Target Commitment", min_value=0.0, value=0.0, step=500000.0)
                    currency = st.selectbox("Currency", ["USD", "EUR"], index=0 if r.get("currency") == "USD" else 1)
                    target_close = st.date_input("Target Close Date")
                    
                    priority_opts = ["High", "Medium", "Low"]
                    priority_ui = st.selectbox("Priority", priority_opts, index=1)
                    
                st.divider()
                st.markdown("**📊 Fund Metrics (For Documentation)**")
                col3, col4, col5 = st.columns(3)
                with col3:
                    st.metric("Target Size", f"${fund_size:,.0f}M" if fund_size else "—")
                    hard_cap = r.get("fund_size_hard_cap")
                    st.metric("Hard Cap", f"${hard_cap:,.0f}M" if hard_cap else "—")
                with col4:
                    moic_low = r.get("target_return_moic_low")
                    moic_high = r.get("target_return_moic_high")
                    st.metric("Target MOIC", f"{moic_low}x-{moic_high}x" if moic_low and moic_high else "—")
                    irr = r.get("target_irr_gross")
                    st.metric("Target Gross IRR", f"{irr}%" if irr else "—")
                with col5:
                    mgmt = r.get("mgmt_fee_pct")
                    carry = r.get("carried_interest_pct")
                    hurdle = r.get("preferred_return_pct")
                    st.metric("Mgmt Fee", f"{mgmt}%" if mgmt else "—")
                    st.metric("Carry / Hurdle", f"{carry}% / {hurdle}%" if carry and hurdle else "—")
                
                aum_str = f" | Manager AUM: ${r.get('aum_manager')}B" if r.get("aum_manager") else ""
                irr_str = f" | IRR: {r.get('target_irr_gross')}%" if r.get("target_irr_gross") else ""
                moic_str = f" | MOIC: {r.get('target_return_moic_low')}x-{r.get('target_return_moic_high')}x" if r.get("target_return_moic_low") else ""
                notes_default = f"Fund Size: ${fund_size:,.0f}M{moic_str}{irr_str}{aum_str}" if fund_size else ""
                notes = st.text_area("Notes", value=notes_default)
                
                if st.form_submit_button("✅ Create Pipeline Fund + Gantt", type="primary"):
                    try:
                        sb = get_supabase()
                        res = sb.table("pipeline_funds").insert({
                            "name": fund_name, "manager": manager, "strategy": strategy,
                            "target_commitment": target_commitment,
                            "currency": currency, "target_close_date": str(target_close),
                            "priority": priority_ui.lower(), "notes": notes
                        }).execute()
                        fund_id = res.data[0]["id"]
                        try:
                            sb.rpc("create_default_gantt_tasks", {"p_fund_id": fund_id}).execute()
                        except:
                            pass
                        st.success(f"✅ Fund '{fund_name}' created!")
                        st.session_state.pdf_result = None
                        st.session_state.show_pdf_upload = False
                        clear_cache_and_rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    if st.session_state.get("show_add_pipeline"):
        st.divider()
        with st.form("add_pipeline_manual"):
            st.markdown("### ➕ Manual Addition")
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Fund Name")
                manager = st.text_input("Manager")
                strategy = st.selectbox("Strategy", ["Growth", "VC", "Tech", "Niche", "Special Situations", "Mid-Market Buyout"])
            with col2:
                target_commitment_input = st.number_input("Target Commitment", min_value=0.0, value=0.0, step=500000.0)
                currency = st.selectbox("Currency", ["USD", "EUR"])
                target_close = st.date_input("Closing Date")
                
                priority_opts = ["High", "Medium", "Low"]
                priority_ui = st.selectbox("Priority", priority_opts, index=1)
                
            notes = st.text_area("Notes")
            if st.form_submit_button("Create Fund + Gantt", type="primary"):
                try:
                    sb = get_supabase()
                    res = sb.table("pipeline_funds").insert({
                        "name": name, "manager": manager, "strategy": strategy,
                        "target_commitment": target_commitment_input, "currency": currency,
                        "target_close_date": str(target_close), "priority": priority_ui.lower(), "notes": notes
                    }).execute()
                    fund_id = res.data[0]["id"]
                    try:
                        sb.rpc("create_default_gantt_tasks", {"p_fund_id": fund_id}).execute()
                    except:
                        pass
                    st.success(f"✅ Fund '{name}' created!")
                    st.session_state.show_add_pipeline = False
                    clear_cache_and_rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    st.divider()

    if not pipeline:
        st.info("No pipeline funds. Click 'Upload PDF' or 'Add Manually'.")
        return

    for fund in pipeline:
        fid = fund["id"]
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(fund.get("priority",""), "⚪")
        with st.expander(f"{priority_emoji} {fund['name']} | {fund.get('strategy','')} | Close: {fund.get('target_close_date','')}", expanded=False):
            col_a, col_b, col_c = st.columns([1, 1, 4])
            with col_a:
                if st.button("✏️ Edit", key=f"edit_btn_{fid}"):
                    st.session_state[f"editing_{fid}"] = True
            with col_b:
                if st.button("🗑️ Delete", key=f"del_btn_{fid}"):
                    st.session_state[f"confirm_delete_{fid}"] = True

            if st.session_state.get(f"confirm_delete_{fid}"):
                st.warning(f"⚠️ Delete '{fund['name']}'? This action will also delete all associated Gantt tasks.")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("✅ Yes, delete", key=f"yes_btn_{fid}", type="primary"):
                        try:
                            sb = get_supabase()
                            log_action("DELETE", "pipeline_funds", f"Deleted pipeline fund: {fund['name']}", fund)
                            sb.table("gantt_tasks").delete().eq("pipeline_fund_id", fid).execute()
                            sb.table("pipeline_funds").delete().eq("id", fid).execute()
                            st.success("Deleted!")
                            st.session_state.pop(f"confirm_delete_{fid}", None)
                            clear_cache_and_rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
                with col_no:
                    if st.button("❌ Cancel", key=f"no_btn_{fid}"):
                        st.session_state.pop(f"confirm_delete_{fid}", None)
                        st.rerun()

            if st.session_state.get(f"editing_{fid}"):
                with st.form(f"edit_form_{fid}"):
                    st.markdown("**✏️ Edit Fund Details**")
                    col1, col2 = st.columns(2)
                    with col1:
                        new_name = st.text_input("Fund Name", value=fund.get("name",""))
                        new_manager = st.text_input("Manager", value=fund.get("manager",""))
                        strategy_opts = ["Growth", "VC", "Tech", "Niche", "Special Situations", "Mid-Market Buyout"]
                        cur_strat = fund.get("strategy","Growth")
                        new_strategy = st.selectbox("Strategy", strategy_opts,
                            index=strategy_opts.index(cur_strat) if cur_strat in strategy_opts else 0)
                        new_geo = st.text_input("Geographic Focus", value=fund.get("geographic_focus","") or "")
                    with col2:
                        cur_commit = float(fund.get("target_commitment") or 0)
                        if 0 < cur_commit <= 1000:
                            cur_commit *= 1_000_000
                        new_commitment_input = st.number_input("Target Commitment", value=cur_commit, step=500000.0)
                        
                        cur_currency = fund.get("currency","USD")
                        new_currency = st.selectbox("Currency", ["USD","EUR"], index=0 if cur_currency=="USD" else 1)
                        
                        priority_opts = ["High", "Medium", "Low"]
                        cur_priority = fund.get("priority","medium").capitalize()
                        new_priority_ui = st.selectbox("Priority", priority_opts,
                            index=priority_opts.index(cur_priority) if cur_priority in priority_opts else 1)
                        
                        cur_date = fund.get("target_close_date")
                        try:
                            default_date = datetime.fromisoformat(str(cur_date)).date() if cur_date else date.today()
                        except:
                            default_date = date.today()
                        new_close = st.date_input("Closing Date", value=default_date)
                    new_notes = st.text_area("Notes", value=fund.get("notes","") or "")
                    col_save, col_cancel = st.columns(2)
                    with col_save:
                        if st.form_submit_button("💾 Save Changes", type="primary"):
                            try:
                                log_action("UPDATE", "pipeline_funds", f"Updated pipeline fund details: {fund['name']}", fund)
                                get_supabase().table("pipeline_funds").update({
                                    "name": new_name, "manager": new_manager,
                                    "strategy": new_strategy, "target_commitment": new_commitment_input,
                                    "currency": new_currency, "priority": new_priority_ui.lower(),
                                    "target_close_date": str(new_close), "notes": new_notes
                                }).eq("id", fid).execute()
                                st.success("✅ Updated!")
                                st.session_state.pop(f"editing_{fid}", None)
                                clear_cache_and_rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                    with col_cancel:
                        if st.form_submit_button("❌ Cancel"):
                            st.session_state.pop(f"editing_{fid}", None)
                            st.rerun()
            else:
                col1, col2, col3 = st.columns(3)
                currency_sym = "€" if fund.get("currency") == "EUR" else "$"
                with col1:
                    commitment = float(fund.get("target_commitment") or 0)
                    st.metric("Target Commitment", format_currency(commitment, currency_sym))
                with col2:
                    st.metric("Closing Date", str(fund.get("target_close_date", "")))
                with col3:
                    st.metric("Priority", fund.get("priority", "").upper())
                
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
        "todo":        {"icon": "⬜", "label": "To Do",       "color": "#64748b"},
        "in_progress": {"icon": "🔄", "label": "In Progress", "color": "#3b82f6"},
        "done":        {"icon": "✅", "label": "Done",        "color": "#22c55e"},
        "blocked":     {"icon": "🚫", "label": "Blocked",     "color": "#ef4444"},
    }
    
    STATUS_LIST = ["todo", "in_progress", "done", "blocked"]
    UI_STATUS_LIST = [STATUS_CONFIG[s]["label"] for s in STATUS_LIST]

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
            <span style="color:#94a3b8;font-size:13px;">Overall Progress</span>
            <span style="color:#4ade80;font-weight:700;font-size:18px;">{pct}%</span>
        </div>
        <div style="background:#0f172a;border-radius:6px;height:8px;overflow:hidden;">
            <div style="background:linear-gradient(90deg,#16a34a,#4ade80);width:{pct}%;height:100%;border-radius:6px;transition:width 0.5s;"></div>
        </div>
        <div style="display:flex;gap:20px;margin-top:12px;">
            <span style="color:#4ade80;font-size:12px;">✅ Done: {done_n}</span>
            <span style="color:#3b82f6;font-size:12px;">🔄 In Progress: {in_prog}</span>
            <span style="color:#ef4444;font-size:12px;">🚫 Blocked: {blocked_n}</span>
            <span style="color:#64748b;font-size:12px;">⬜ To Do: {total - done_n - in_prog - blocked_n}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_hdr1, col_hdr2 = st.columns([3, 1])
    with col_hdr1:
        st.markdown("##### 📊 Gantt Chart View")
    with col_hdr2:
        show_done = st.toggle("Show completed tasks", value=True, key=f"show_done_toggle_{fid}")

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
                textfont=dict(color="white", size=13, family="Inter"),
                hovertemplate=f"<b>{t['RawName']}</b><br>{t['Start']} → {t['Finish']}<br>Status: {t['Status']}<extra></extra>",
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
            text="Today", showarrow=False,
            font=dict(color="#f59e0b", size=13, family="Inter"),
            yanchor="bottom"
        )
        
        fig.update_layout(
            height=max(350, len(sorted_tasks) * 45 + 100),
            barmode="overlay",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#0f172a",
            font=dict(color="#e2e8f0", size=14, family="Inter"),
            margin=dict(l=10, r=20, t=40, b=40),
            xaxis=dict(type="date", gridcolor="#1e293b", tickformat="%d/%m/%y", tickfont=dict(size=13)),
            yaxis=dict(gridcolor="#1e293b", tickfont=dict(size=14), automargin=True),
        )
        st.plotly_chart(fig, use_container_width=True, key=f"gantt_chart_{fid}")
    else:
        st.info("No tasks to display in this chart currently.")

    st.markdown("##### 📋 Edit Tasks")
    
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
            current_status = t.get("status", "todo")
            scfg = STATUS_CONFIG.get(current_status, STATUS_CONFIG["todo"])
            current_ui_label = scfg["label"]
            
            try:
                current_start = datetime.fromisoformat(t["start_date"]).date() if t.get("start_date") else date.today()
                current_due = datetime.fromisoformat(t["due_date"]).date() if t.get("due_date") else date.today()
            except:
                current_start, current_due = date.today(), date.today()

            col_icon, col_name, col_start, col_due, col_status, col_del = st.columns([0.5, 3, 2, 2, 2, 0.5])
            with col_icon:
                st.markdown(f"<div style='margin-top:5px; font-size:18px;'>{scfg['icon']}</div>", unsafe_allow_html=True)
            with col_name:
                new_name = st.text_input("Task Name", value=t["task_name"], key=f"name_{fid}_{t['id']}", label_visibility="collapsed")
            with col_start:
                new_start = st.date_input("Start", value=current_start, key=f"start_{fid}_{t['id']}", label_visibility="collapsed")
            with col_due:
                new_due = st.date_input("End", value=current_due, key=f"due_{fid}_{t['id']}", label_visibility="collapsed")
            with col_status:
                new_ui_label = st.selectbox(
                    "Status",
                    UI_STATUS_LIST,
                    index=UI_STATUS_LIST.index(current_ui_label) if current_ui_label in UI_STATUS_LIST else 0,
                    key=f"status_{fid}_{t['id']}",
                    label_visibility="collapsed"
                )
            
            new_status_mapped = [k for k, v in STATUS_CONFIG.items() if v["label"] == new_ui_label][0]

            with col_del:
                if st.button("🗑️", key=f"del_{fid}_{t['id']}", help="Delete Task"):
                    try:
                        log_action("DELETE", "gantt_tasks", f"Deleted Gantt task: {t['task_name']}", t)
                        sb.table("gantt_tasks").delete().eq("id", t["id"]).execute()
                        clear_cache_and_rerun()
                    except Exception as e:
                        st.error(f"Delete Error: {e}")
                
            if new_status_mapped != current_status or str(new_start) != t.get("start_date") or str(new_due) != t.get("due_date") or new_name != t["task_name"]:
                try:
                    sb.table("gantt_tasks").update({
                        "task_name": new_name,
                        "status": new_status_mapped,
                        "start_date": str(new_start),
                        "due_date": str(new_due)
                    }).eq("id", t["id"]).execute()
                    clear_cache_and_rerun()
                except Exception as e:
                    st.error(f"Update Task Error: {e}")

    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("➕ Add New Task to Gantt"):
        with st.form(f"add_new_task_{fid}"):
            c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
            with c1:
                new_t_name = st.text_input("Task Name")
            with c2:
                new_t_cat = st.selectbox("Category", ["Analysis", "IC", "DD", "Legal", "Tax", "Admin"])
            with c3:
                new_t_start = st.date_input("Start Date", value=date.today())
            with c4:
                new_t_due = st.date_input("Due Date", value=date.today())
            
            if st.form_submit_button("Save Task", type="primary"):
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
                        st.success("Task successfully added!")
                        clear_cache_and_rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.error("Please enter a task name")
def show_reports():
    st.title("📈 Reports & Analytics")
    
    st.markdown("""
    <div class="dashboard-header">
    <h1 style="color:white;margin:0;">📈 Portfolio Reports & Analytics</h1>
    <p style="color:#94a3b8;margin:4px 0 0 0;">Comprehensive view of all fund performance metrics</p>
    </div>
    """, unsafe_allow_html=True)
    
    sb = get_supabase()
    funds = get_funds()
    all_reports = get_quarterly_reports(None)
    
    # Add/Upload Section
    st.divider()
    col_add, col_summary = st.columns([1, 1])
    
    with col_add:
        with st.expander("➕ Add / Upload Quarterly Reports"):
            fund_options = {f["name"]: f["id"] for f in funds}
            if not fund_options:
                st.warning("No funds in portfolio. Add a fund first.")
            else:
                tab_manual, tab_upload = st.tabs(["Manual Entry", "Upload & AI Extract"])
                
                with tab_manual:
                    with st.form("manual_report_form"):
                        st.markdown("**Add Report Manually**")
                        selected_fund = st.selectbox("Select Fund", list(fund_options.keys()))
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            year = st.number_input("Year", min_value=2020, max_value=2030, value=2025)
                            quarter = st.selectbox("Quarter", [1, 2, 3, 4])
                            report_date = st.date_input("Report Date")
                        with col2:
                            nav = st.number_input("NAV (Fund Level)", min_value=0.0)
                            tvpi = st.number_input("TVPI", min_value=0.0, step=0.01, format="%.2f")
                            dpi = st.number_input("DPI", min_value=0.0, step=0.01, format="%.2f")
                        
                        col3, col4 = st.columns(2)
                        with col3:
                            rvpi = st.number_input("RVPI", min_value=0.0, step=0.01, format="%.2f")
                        with col4:
                            irr = st.number_input("IRR %", step=0.1, format="%.1f")
                        
                        notes = st.text_area("Notes")
                        
                        if st.form_submit_button("💾 Save Report", type="primary"):
                            try:
                                fund_id = fund_options[selected_fund]
                                sb.table("quarterly_reports").insert({
                                    "fund_id": fund_id,
                                    "year": year,
                                    "quarter": quarter,
                                    "report_date": str(report_date),
                                    "nav": nav,
                                    "tvpi": tvpi,
                                    "dpi": dpi,
                                    "rvpi": rvpi,
                                    "irr": irr,
                                    "notes": notes
                                }).execute()
                                log_action("INSERT", "quarterly_reports", f"Added Q{quarter}/{year} report for {selected_fund}", {})
                                st.success("✅ Report saved!")
                                clear_cache_and_rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                
                with tab_upload:
                    st.markdown("**Upload Report File (PDF/Excel/CSV)**")
                    selected_fund_upload = st.selectbox("Select Fund", list(fund_options.keys()), key="upload_fund")
                    uploaded_file = st.file_uploader("Upload File", type=["pdf", "xlsx", "xls", "csv"])
                    
                    if uploaded_file:
                        if st.button("🤖 Analyze with AI", type="primary"):
                            with st.spinner("Claude is analyzing..."):
                                try:
                                    file_bytes = uploaded_file.read()
                                    file_name = uploaded_file.name
                                    
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
                                    st.session_state.report_ai_result = ai_result
                                    st.success("✅ Extracted! Review below and save:")
                                    
                                    with st.form("ai_report_confirm"):
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            year_ai = st.number_input("Year", value=int(ai_result.get("year") or 2025))
                                            quarter_ai = st.selectbox("Quarter", [1,2,3,4], index=[1,2,3,4].index(int(ai_result.get("quarter") or 1)))
                                            nav_ai = st.number_input("NAV", value=float(ai_result.get("nav") or 0.0))
                                        with col2:
                                            tvpi_ai = st.number_input("TVPI", value=float(ai_result.get("tvpi") or 0.0), step=0.01, format="%.2f")
                                            dpi_ai = st.number_input("DPI", value=float(ai_result.get("dpi") or 0.0), step=0.01, format="%.2f")
                                            rvpi_ai = st.number_input("RVPI", value=float(ai_result.get("rvpi") or 0.0), step=0.01, format="%.2f")
                                        
                                        irr_ai = st.number_input("IRR %", value=float(ai_result.get("irr") or 0.0), step=0.1, format="%.1f")
                                        
                                        if st.form_submit_button("💾 Confirm & Save", type="primary"):
                                            try:
                                                fund_id = fund_options[selected_fund_upload]
                                                sb.table("quarterly_reports").insert({
                                                    "fund_id": fund_id,
                                                    "year": year_ai,
                                                    "quarter": quarter_ai,
                                                    "report_date": str(date.today()),
                                                    "nav": nav_ai,
                                                    "tvpi": tvpi_ai,
                                                    "dpi": dpi_ai,
                                                    "rvpi": rvpi_ai,
                                                    "irr": irr_ai
                                                }).execute()
                                                st.success("✅ Report saved!")
                                                st.session_state.pop("report_ai_result", None)
                                                clear_cache_and_rerun()
                                            except Exception as e:
                                                st.error(f"Error: {e}")
                                except Exception as e:
                                    st.error(f"Analysis error: {e}")
    
    with col_summary:
        with st.expander("📊 Portfolio Summary Statistics"):
            if all_reports:
                latest_reports = {}
                for r in all_reports:
                    fid = r["fund_id"]
                    if fid not in latest_reports:
                        latest_reports[fid] = r
                    else:
                        curr = latest_reports[fid]
                        if r["year"] > curr["year"] or (r["year"] == curr["year"] and r["quarter"] > curr["quarter"]):
                            latest_reports[fid] = r
                
                avg_tvpi = sum(float(r.get("tvpi") or 0) for r in latest_reports.values()) / len(latest_reports) if latest_reports else 0
                avg_dpi = sum(float(r.get("dpi") or 0) for r in latest_reports.values()) / len(latest_reports) if latest_reports else 0
                avg_irr = sum(float(r.get("irr") or 0) for r in latest_reports.values()) / len(latest_reports) if latest_reports else 0
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Avg TVPI", f"{avg_tvpi:.2f}x")
                with col2:
                    st.metric("Avg DPI", f"{avg_dpi:.2f}x")
                with col3:
                    st.metric("Avg IRR", f"{avg_irr:.1f}%")
            else:
                st.info("No reports yet")
    
    st.divider()
    
    # Reports Table
    if not all_reports:
        st.info("📊 No quarterly reports. Add reports above to see analytics.")
        return
    
    st.markdown("### 📋 All Quarterly Reports")
    
    # Build reports table
    reports_data = []
    for r in all_reports:
        fund = next((f for f in funds if f["id"] == r["fund_id"]), None)
        if fund:
            reports_data.append({
                "id": r["id"],
                "Fund": fund["name"],
                "Quarter": f"Q{r['quarter']}/{r['year']}",
                "Report Date": r.get("report_date", ""),
                "NAV": format_currency(float(r.get("nav") or 0), "€" if fund.get("currency") == "EUR" else "$"),
                "TVPI": f"{float(r.get('tvpi') or 0):.2f}x",
                "DPI": f"{float(r.get('dpi') or 0):.2f}x",
                "RVPI": f"{float(r.get('rvpi') or 0):.2f}x",
                "IRR": f"{float(r.get('irr') or 0):.1f}%"
            })
    
    if reports_data:
        df = pd.DataFrame(reports_data)
        
        # Export button
        col_export, col_space = st.columns([1, 5])
        with col_export:
            excel_data = convert_df_to_excel(df.drop(columns=["id"], errors="ignore"))
            st.download_button(
                label="📥 Export Excel",
                data=excel_data,
                file_name=f"Portfolio_Reports_{date.today()}.xlsx",
                use_container_width=True
            )
        
        # Display table
        st.dataframe(df.drop(columns=["id"]), use_container_width=True, hide_index=True)
        
        # Edit/Delete for each report
        st.markdown("#### ⚙️ Manage Reports")
        for idx, row in df.iterrows():
            report_id = row["id"]
            with st.expander(f"{row['Fund']} - {row['Quarter']}", expanded=False):
                col_edit, col_del = st.columns([5, 1])
                with col_del:
                    if st.button("🗑️ Delete", key=f"del_rep_{report_id}"):
                        st.session_state[f"confirm_del_report_{report_id}"] = True
                
                if st.session_state.get(f"confirm_del_report_{report_id}"):
                    st.warning("Delete this report?")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅ Yes", key=f"yes_rep_{report_id}"):
                            try:
                                rep = next(r for r in all_reports if r["id"] == report_id)
                                log_action("DELETE", "quarterly_reports", f"Deleted {row['Quarter']} report for {row['Fund']}", rep)
                                sb.table("quarterly_reports").delete().eq("id", report_id).execute()
                                st.session_state.pop(f"confirm_del_report_{report_id}", None)
                                clear_cache_and_rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                    with c2:
                        if st.button("❌ Cancel", key=f"no_rep_{report_id}"):
                            st.session_state.pop(f"confirm_del_report_{report_id}", None)
                            st.rerun()
    
    st.divider()
    
    # Performance Trends
    st.markdown("### 📈 Performance Trends")
    
    latest_reports = {}
    for r in all_reports:
        fid = r["fund_id"]
        if fid not in latest_reports:
            latest_reports[fid] = r
        else:
            curr = latest_reports[fid]
            if r["year"] > curr["year"] or (r["year"] == curr["year"] and r["quarter"] > curr["quarter"]):
                latest_reports[fid] = r
    
    fund_names = [f["name"] for f in funds if f["id"] in latest_reports]
    if fund_names:
        tabs = st.tabs(fund_names)
        
        for i, f in enumerate([fund for fund in funds if fund["id"] in latest_reports]):
            with tabs[i]:
                fund_reports = [r for r in all_reports if r["fund_id"] == f["id"]]
                fund_reports = sorted(fund_reports, key=lambda x: (x["year"], x["quarter"]))
                
                if len(fund_reports) > 1:
                    labels = [f"Q{r['quarter']}/{r['year']}" for r in fund_reports]
                    
                    # Multiples Chart
                    fig = go.Figure()
                    if any(r.get("tvpi") for r in fund_reports):
                        fig.add_trace(go.Scatter(x=labels, y=[float(r.get("tvpi") or 0) for r in fund_reports], 
                                                name="TVPI", line=dict(color="#4ade80", width=3), mode='lines+markers'))
                    if any(r.get("dpi") for r in fund_reports):
                        fig.add_trace(go.Scatter(x=labels, y=[float(r.get("dpi") or 0) for r in fund_reports], 
                                                name="DPI", line=dict(color="#60a5fa", width=3), mode='lines+markers'))
                    if any(r.get("rvpi") for r in fund_reports):
                        fig.add_trace(go.Scatter(x=labels, y=[float(r.get("rvpi") or 0) for r in fund_reports], 
                                                name="RVPI", line=dict(color="#fbbf24", width=3), mode='lines+markers'))
                    
                    fig.update_layout(
                        title=f"{f['name']} - Multiples Over Time",
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#0f172a',
                        font=dict(color='#e2e8f0', size=14, family='Inter'),
                        xaxis=dict(gridcolor='#1e293b'), yaxis=dict(gridcolor='#1e293b', title="Multiple (x)"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        hovermode='x unified'
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # IRR Chart
                    if any(r.get("irr") for r in fund_reports):
                        fig_irr = go.Figure()
                        fig_irr.add_trace(go.Scatter(
                            x=labels, y=[float(r.get("irr") or 0) for r in fund_reports],
                            name="IRR", line=dict(color="#a78bfa", width=3),
                            mode='lines+markers', fill='tozeroy'
                        ))
                        fig_irr.update_layout(
                            title=f"{f['name']} - IRR Trend",
                            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#0f172a',
                            font=dict(color='#e2e8f0', size=14, family='Inter'),
                            xaxis=dict(gridcolor='#1e293b'), yaxis=dict(gridcolor='#1e293b', title="IRR (%)"),
                            showlegend=False, hovermode='x unified'
                        )
                        st.plotly_chart(fig_irr, use_container_width=True)
                else:
                    st.info("Need at least 2 quarterly reports to show trends.")
                    
if __name__ == "__main__":
    main()
