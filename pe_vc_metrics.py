import math


NULL_TEXT_VALUES = {"", "-", "\u2014", "\u2013", "n/a", "na", "none", "null"}


def parse_report_amount(value, default=None, signed=True):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return default
        return float(value) if signed else abs(float(value))

    text = str(value).strip()
    if text.lower() in NULL_TEXT_VALUES:
        return default

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]

    text = (
        text.replace(",", "")
        .replace("$", "")
        .replace("\u20ac", "")
        .replace("x", "")
        .replace("%", "")
        .strip()
    )

    try:
        amount = float(text)
    except Exception:
        return default
    if negative:
        amount = -abs(amount)
    return amount if signed else abs(amount)


def first_number(data, keys, default=None, signed=True):
    for key in keys:
        if key in data:
            value = parse_report_amount(data.get(key), default=None, signed=signed)
            if value is not None:
                return value
    return default


def is_missing_metric(value):
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in NULL_TEXT_VALUES:
        return True
    return False


def normalize_quarterly_report_metrics(result):
    data = dict(result or {})
    warnings = list(data.get("validation_warnings") or data.get("warnings") or [])

    nav = first_number(
        data,
        ["nav", "ending_capital_account_balance", "ending_capital_account", "capital_account_balance"],
        default=None,
        signed=True,
    )
    paid_in_capital = first_number(
        data,
        ["paid_in_capital", "capital_contributions", "capital contributions", "contributions_to_date", "total_invested"],
        default=None,
        signed=False,
    )
    investment_contributions = first_number(
        data,
        ["investment_contributions", "contributions_for_investments"],
        default=None,
        signed=False,
    )
    expense_contributions = first_number(
        data,
        ["expense_contributions", "contributions_for_expenses"],
        default=None,
        signed=False,
    )
    distributions = first_number(data, ["distributions", "total_realized", "realized_value"], default=0.0, signed=False)
    unrealized_gain_loss = first_number(
        data,
        ["unrealized_gain_loss", "unrealized_gain", "unrealized_gain_or_loss"],
        default=None,
        signed=True,
    )
    special_reallocation = first_number(
        data,
        ["special_reallocation", "special_reallocations_amount"],
        default=None,
        signed=True,
    )

    if nav is not None:
        data["nav"] = nav
    if paid_in_capital is not None:
        data["paid_in_capital"] = paid_in_capital
        data["total_invested"] = paid_in_capital
    if investment_contributions is not None:
        data["investment_contributions"] = investment_contributions
    if expense_contributions is not None:
        data["expense_contributions"] = expense_contributions
    data["distributions"] = distributions
    data["total_realized"] = distributions

    if unrealized_gain_loss is not None:
        data["unrealized_gain_loss"] = unrealized_gain_loss
    if special_reallocation is not None:
        data["special_reallocation"] = special_reallocation

    total_value = first_number(data, ["total_value"], default=None, signed=True)
    if (total_value is None or total_value == 0) and nav is not None:
        total_value = nav + distributions
    if total_value is not None:
        data["total_value"] = total_value

    # For LP reporting, residual/unrealized value is NAV unless a separate residual value was provided.
    residual_value = first_number(data, ["residual_value", "unrealized_value", "total_unrealized"], default=None, signed=True)
    if (residual_value is None or residual_value == 0) and nav is not None:
        residual_value = nav
    if residual_value is not None:
        data["total_unrealized"] = residual_value
        data["rvpi"] = residual_value / paid_in_capital if paid_in_capital else data.get("rvpi")

    if paid_in_capital and paid_in_capital > 0:
        dpi = parse_report_amount(data.get("dpi"), default=None, signed=True)
        if dpi is None or (dpi == 0 and distributions == 0):
            dpi = distributions / paid_in_capital
        data["dpi"] = dpi

        tvpi = parse_report_amount(data.get("tvpi"), default=None, signed=True)
        if total_value is not None and (tvpi is None or tvpi == 0):
            tvpi = total_value / paid_in_capital
            warnings.append("TVPI was missing or zero and was recalculated from NAV + distributions over paid-in capital.")
        if tvpi is not None:
            data["tvpi"] = tvpi

        net_moic = parse_report_amount(data.get("net_moic"), default=None, signed=True)
        if total_value is not None and (net_moic is None or net_moic == 0):
            net_moic = tvpi
        if net_moic is not None:
            data["net_moic"] = net_moic

    # Missing IRRs are not zero. Keep gross metrics blank unless explicitly supplied.
    for key in ["irr", "net_irr", "gross_irr"]:
        if parse_report_amount(data.get(key), default=None, signed=True) == 0 and not data.get(f"{key}_explicit"):
            data[key] = None
        elif is_missing_metric(data.get(key)):
            data[key] = None

    if parse_report_amount(data.get("gross_moic"), default=None, signed=True) == 0 and not data.get("gross_moic_explicit"):
        data["gross_moic"] = None

    beginning = first_number(data, ["beginning_capital_account_balance", "beginning_capital_account"], default=0.0, signed=True)
    investment_income = first_number(data, ["investment_income"], default=0.0, signed=True)
    management_fee = first_number(data, ["management_fee"], default=0.0, signed=True)
    organizational_costs = first_number(data, ["organizational_costs", "organizational_cost"], default=0.0, signed=True)
    other_expenses = first_number(data, ["other_expenses", "other_expense"], default=0.0, signed=True)
    realized_gain_loss = first_number(data, ["realized_gain_loss", "realized_gain_or_loss"], default=0.0, signed=True)

    if nav is not None and paid_in_capital is not None:
        reconciled = (
            beginning
            + paid_in_capital
            - distributions
            + investment_income
            + management_fee
            + organizational_costs
            + other_expenses
            + realized_gain_loss
            + (unrealized_gain_loss or 0.0)
            + (special_reallocation or 0.0)
        )
        data["capital_account_reconciliation"] = reconciled
        data["capital_account_reconciliation_difference"] = nav - reconciled
        if abs(nav - reconciled) > 1.0:
            warnings.append(f"Capital account balance does not reconcile; difference is {nav - reconciled:,.2f}.")

    data["validation_warnings"] = list(dict.fromkeys(warnings))
    return data
