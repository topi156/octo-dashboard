diff --git a/app.py b/app.py
index be459a3..a8149cd 100644
--- a/app.py
+++ b/app.py
@@ -34,6 +34,26 @@ def get_allowed_emails() -> set[str]:
 def is_email_allowed(email: str) -> bool:
     return email.strip().lower() in get_allowed_emails()
 
+def normalize_commitment_amount(value) -> float:
+    """Normalize a raw commitment number that may have been entered in millions
+    (e.g. 1 meaning $1,000,000) instead of raw dollars."""
+    value = float(value or 0)
+    if 0 < value <= 1000:
+        value *= 1_000_000
+    return value
+
+def investor_commitment_value(inv) -> float:
+    """Normalize an investor's commitment amount.
+
+    Mirrors the normalization already applied to funds' `commitment` field
+    (see commitment_value()): some commitments were entered/stored in millions
+    (e.g. 1 meaning $1,000,000) instead of raw dollars. Without this, such
+    values get summed as-is (e.g. 1 instead of 1,000,000), silently
+    undercounting "Total LP Commitments" by ~$1M per affected investor, even
+    though format_currency() displays them as "$1.00M" (looking correct).
+    """
+    return normalize_commitment_amount(inv.get("commitment"))
+
 def format_currency(amount: float, currency_sym: str = "$") -> str:
     if amount is None or amount == 0:
         return "—"
@@ -1182,7 +1202,7 @@ def generate_master_excel_bytes() -> bytes:
             for inv in investors:
                 row = {
                     "Investor Name": inv["name"],
-                    "Commitment": inv.get("commitment", 0)
+                    "Commitment": investor_commitment_value(inv)
                 }
                 for c in lp_calls:
                     col_name = f"{c['call_date']} ({c['call_pct']}%)"
@@ -1771,6 +1791,9 @@ def show_overview():
     </style>
     """, unsafe_allow_html=True)
 
+    _lp_investors_top = get_investors()
+    lp_total_commitment = sum(investor_commitment_value(inv) for inv in _lp_investors_top)
+    fund_called_vs_lp_commit_pct = (total_called_basis_usd / lp_total_commitment * 100) if lp_total_commitment > 0 else 0.0
     st.markdown("##### 🏛️ Legal & Commitment (Basis)")
     c1, c2, c3, c4 = st.columns(4)
     with c1:
@@ -1783,7 +1806,7 @@ def show_overview():
         st.metric("Uncalled Balance", format_overview_currency(total_uncalled_usd, "$"))
 
     st.markdown("##### 🚀 Cash & Performance (Net LP)")
-    c5, c6, c7, c8 = st.columns(4)
+    c5, c6, c7, c8, c9 = st.columns(5)
     with c5:
         st.metric("Total Paid-In (Cash Out)", format_overview_currency(total_paid_in_cash_usd, "$"))
     with c6:
@@ -1792,6 +1815,8 @@ def show_overview():
         st.metric("Portfolio TVPI", f"{portfolio_tvpi:.2f}x" if portfolio_tvpi > 0 else "—")
     with c8:
         st.metric("Portfolio Net IRR", irr_display)
+    with c9:
+        st.metric("Called (Funds) vs LP Commitments", f"{fund_called_vs_lp_commit_pct:.1f}%", f"{format_currency(total_called_basis_usd, '$')} of {format_currency(lp_total_commitment, '$')}")
 
     st.divider()
     col1 = st.container()
@@ -1800,7 +1825,12 @@ def show_overview():
     with col1:
         st.subheader("📋 Funds Status")
         if funds:
-            rows = []
+            fund_data = []
+            total_commitment_usd_sum = 0.0
+            total_called_usd_sum = 0.0
+            total_cash_paid_usd_sum = 0.0
+            total_nav_usd_sum = 0.0
+
             for f in funds:
                 f_calls = [c for c in all_calls if c["fund_id"] == f["id"]]
                 f_dists = get_distributions(f["id"])
@@ -1816,28 +1846,66 @@ def show_overview():
                     elif tx_type in ["repayment", "distribution"]:
                         cash_paid -= amount
                 cash_paid -= sum(float(d.get("amount") or 0) for d in f_dists)
-                
+
                 c_val = float(f.get("commitment") or 0)
                 if 0 < c_val <= 1000:
                     c_val *= 1_000_000
-                    
+
                 pct = f"{total_called/c_val*100:.1f}%" if c_val > 0 else "—"
                 currency_sym = "€" if f.get("currency") == "EUR" else "$"
-                
+                rate = st.session_state.eur_usd_rate if f.get("currency") == "EUR" else 1.0
+
                 octo_nav = f.get("calculated_nav_local", total_called)
-                    
-                rows.append({
+
+                total_commitment_usd_sum += c_val * rate
+                total_called_usd_sum += total_called * rate
+                total_cash_paid_usd_sum += cash_paid * rate
+                total_nav_usd_sum += octo_nav * rate
+
+                fund_data.append({
                     "Fund": f["name"],
                     "Currency": f.get("currency", "USD"),
-                    "Commitment": format_currency(c_val, currency_sym),
-                    "Total Called": format_currency(total_called, currency_sym) if total_called > 0 else "—",
-                    "Cash Paid": format_currency(cash_paid, currency_sym) if abs(cash_paid) > 0 else "—",
+                    "Commitment": c_val,
+                    "Total Called": total_called,
+                    "Cash Paid": cash_paid,
                     "Called %": pct,
-                    "Octo NAV": format_currency(octo_nav, currency_sym) if octo_nav > 0 else "—",
-                    "Status": f.get("status", "active").capitalize(),
+                    "Octo NAV": octo_nav,
+                    "currency_sym": currency_sym,
+                    "nav_usd": octo_nav * rate,
                 })
-                
-            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
+
+            rows = []
+            for fd in fund_data:
+                nav_pct = f"{fd['nav_usd']/total_nav_usd_sum*100:.1f}%" if total_nav_usd_sum > 0 else "—"
+                rows.append({
+                    "Fund": fd["Fund"],
+                    "Currency": fd["Currency"],
+                    "Commitment": format_currency(fd["Commitment"], fd["currency_sym"]),
+                    "Total Called": format_currency(fd["Total Called"], fd["currency_sym"]) if fd["Total Called"] > 0 else "—",
+                    "Cash Paid": format_currency(fd["Cash Paid"], fd["currency_sym"]) if abs(fd["Cash Paid"]) > 0 else "—",
+                    "Called %": fd["Called %"],
+                    "Octo NAV": format_currency(fd["Octo NAV"], fd["currency_sym"]) if fd["Octo NAV"] > 0 else "—",
+                    "% of NAV": nav_pct,
+                })
+
+            overall_called_pct = f"{total_called_usd_sum/total_commitment_usd_sum*100:.1f}%" if total_commitment_usd_sum > 0 else "—"
+            rows.append({
+                "Fund": "TOTAL (USD Eqv)",
+                "Currency": "—",
+                "Commitment": format_currency(total_commitment_usd_sum, "$"),
+                "Total Called": format_currency(total_called_usd_sum, "$") if total_called_usd_sum > 0 else "—",
+                "Cash Paid": format_currency(total_cash_paid_usd_sum, "$") if abs(total_cash_paid_usd_sum) > 0 else "—",
+                "Called %": overall_called_pct,
+                "Octo NAV": format_currency(total_nav_usd_sum, "$") if total_nav_usd_sum > 0 else "—",
+                "% of NAV": "100.0%" if total_nav_usd_sum > 0 else "—",
+            })
+
+            def _highlight_total(row):
+                is_total = row["Fund"] == "TOTAL (USD Eqv)"
+                return ["font-weight: bold; border-top: 2px solid #475569" if is_total else "" for _ in row]
+
+            styled = pd.DataFrame(rows).style.apply(_highlight_total, axis=1)
+            st.dataframe(styled, width="stretch", hide_index=True)
         else:
             st.info("No funds in the system") 
 
@@ -1900,37 +1968,51 @@ def show_overview():
     lp_calls = get_lp_calls()
     payments = get_lp_payments()
     currency_sym = "$" 
-    total_fund_commitment = sum(float(inv.get("commitment", 0)) for inv in investors)
+    total_fund_commitment = sum(investor_commitment_value(inv) for inv in investors)
+
+    summary_data = []
+    total_called_cum = 0.0
+    total_received_cum = 0.0
+    for c in lp_calls:
+        call_pct = c["call_pct"] / 100.0
+        total_called_amount = total_fund_commitment * call_pct
 
-    col_sum1, col_sum2 = st.columns([1, 3])
+        paid_commit = 0
+        for inv in investors:
+            payment = next((p for p in payments if p["lp_call_id"] == c["id"] and p["investor_id"] == inv["id"]), None)
+            if payment and payment["is_paid"]:
+                paid_commit += investor_commitment_value(inv)
+
+        total_paid_amount = paid_commit * call_pct
+        outstanding = total_called_amount - total_paid_amount
+        total_called_cum += total_called_amount
+        total_received_cum += total_paid_amount
+
+        summary_data.append({
+            "Call": f"{c['call_date']} ({c['call_pct']}%)",
+            "Total Required": format_currency(total_called_amount, currency_sym),
+            "Total Received": format_currency(total_paid_amount, currency_sym),
+            "Outstanding Balance": format_currency(outstanding, currency_sym)
+        })
+
+    total_outstanding_cum = total_called_cum - total_received_cum
+    called_pct_overall = (total_called_cum / total_fund_commitment * 100) if total_fund_commitment > 0 else 0.0
+    received_pct_overall = (total_received_cum / total_fund_commitment * 100) if total_fund_commitment > 0 else 0.0
+
+    col_sum1, col_sum2, col_sum3, col_sum4 = st.columns(4)
     with col_sum1:
         st.metric("Total LP Commitments", format_currency(total_fund_commitment, currency_sym))
-
     with col_sum2:
-        if lp_calls:
-            summary_data = []
-            for c in lp_calls:
-                call_pct = c["call_pct"] / 100.0
-                total_called_amount = total_fund_commitment * call_pct
-
-                paid_commit = 0
-                for inv in investors:
-                    payment = next((p for p in payments if p["lp_call_id"] == c["id"] and p["investor_id"] == inv["id"]), None)
-                    if payment and payment["is_paid"]:
-                        paid_commit += float(inv.get("commitment", 0))
-
-                total_paid_amount = paid_commit * call_pct
-                outstanding = total_called_amount - total_paid_amount
-
-                summary_data.append({
-                    "Call": f"{c['call_date']} ({c['call_pct']}%)",
-                    "Total Required": format_currency(total_called_amount, currency_sym),
-                    "Total Received": format_currency(total_paid_amount, currency_sym),
-                    "Outstanding Balance": format_currency(outstanding, currency_sym)
-                })
-            st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)
-        else:
-            st.info("No active capital calls yet.")
+        st.metric("Total Called to Date", format_currency(total_called_cum, currency_sym), f"{called_pct_overall:.1f}% of commitments")
+    with col_sum3:
+        st.metric("Total Received to Date", format_currency(total_received_cum, currency_sym), f"{received_pct_overall:.1f}% of commitments")
+    with col_sum4:
+        st.metric("Outstanding", format_currency(total_outstanding_cum, currency_sym))
+
+    if lp_calls:
+        st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)
+    else:
+        st.info("No active capital calls yet.")
 
 def show_fund_expenses():
     st.title("💼 Fund Operating Expenses")
@@ -3068,8 +3150,9 @@ def show_investors():
                         inv_commit = st.number_input(f"Commitment Amount ({currency_sym})", min_value=0.0, step=500000.0)
                     if st.form_submit_button("Save Investor", type="primary"):
                         try:
-                            sb.table("investors").insert({"name": inv_name, "commitment": inv_commit}).execute()
-                            log_action("INSERT", "investors", f"Added new investor: {inv_name}", {"commitment": inv_commit})
+                            inv_commit_norm = normalize_commitment_amount(inv_commit)
+                            sb.table("investors").insert({"name": inv_name, "commitment": inv_commit_norm}).execute()
+                            log_action("INSERT", "investors", f"Added new investor: {inv_name}", {"commitment": inv_commit_norm})
                             st.success("Investor added!")
                             clear_cache_and_rerun()
                         except Exception as e:
@@ -3098,6 +3181,7 @@ def show_investors():
                                             commit_val = float(commit_str)
                                         except:
                                             commit_val = 0.0
+                                        commit_val = normalize_commitment_amount(commit_val)
                                         
                                         sb.table("investors").insert({"name": name_val, "commitment": commit_val}).execute()
                                         count += 1
@@ -3119,7 +3203,7 @@ def show_investors():
                 with c1:
                     st.write(f"**{inv['name']}**")
                 with c2:
-                    st.write(format_currency(float(inv.get("commitment", 0)), currency_sym))
+                    st.write(format_currency(investor_commitment_value(inv), currency_sym))
                 with c3:
                     if st.button("✏️", key=f"edit_inv_btn_{inv['id']}", help="Edit Investor"):
                         st.session_state[f"editing_inv_{inv['id']}"] = True
@@ -3147,13 +3231,14 @@ def show_investors():
                 if st.session_state.get(f"editing_inv_{inv['id']}"):
                     with st.form(f"edit_inv_form_{inv['id']}"):
                         new_name = st.text_input("Investor Name", value=inv["name"])
-                        new_commit = st.number_input("Commitment", value=float(inv.get("commitment", 0)), step=500000.0)
+                        new_commit = st.number_input("Commitment", value=investor_commitment_value(inv), step=500000.0)
                         ce1, ce2 = st.columns(2)
                         with ce1:
                             if st.form_submit_button("💾 Save Changes"):
                                 try:
                                     log_action("UPDATE", "investors", f"Updated investor: {inv['name']} to {new_name}", inv)
-                                    sb.table("investors").update({"name": new_name, "commitment": new_commit}).eq("id", inv["id"]).execute()
+                                    new_commit_norm = normalize_commitment_amount(new_commit)
+                                    sb.table("investors").update({"name": new_name, "commitment": new_commit_norm}).eq("id", inv["id"]).execute()
                                     st.session_state.pop(f"editing_inv_{inv['id']}", None)
                                     clear_cache_and_rerun()
                                 except Exception as e:
@@ -3179,7 +3264,7 @@ def show_investors():
     total_fund_commitment = 0
     
     for inv in investors:
-        inv_commit = float(inv.get("commitment", 0))
+        inv_commit = investor_commitment_value(inv)
         total_fund_commitment += inv_commit
         row = {
             "id": inv["id"],
@@ -3237,36 +3322,51 @@ def show_investors():
 
     st.divider()
     st.markdown("### 📊 FOF Collection Summary")
-    
-    col_sum1, col_sum2 = st.columns([1, 3])
+
+    summary_data = []
+    total_called_cum = 0.0
+    total_received_cum = 0.0
+    for c in lp_calls:
+        call_pct = c["call_pct"] / 100.0
+        total_called_amount = total_fund_commitment * call_pct
+
+        paid_commit = 0
+        for inv in investors:
+            payment = next((p for p in payments if p["lp_call_id"] == c["id"] and p["investor_id"] == inv["id"]), None)
+            if payment and payment["is_paid"]:
+                paid_commit += investor_commitment_value(inv)
+
+        total_paid_amount = paid_commit * call_pct
+        outstanding = total_called_amount - total_paid_amount
+        total_called_cum += total_called_amount
+        total_received_cum += total_paid_amount
+
+        summary_data.append({
+            "Call": f"{c['call_date']} ({c['call_pct']}%)",
+            "Total Required": format_currency(total_called_amount, currency_sym),
+            "Total Received": format_currency(total_paid_amount, currency_sym),
+            "Outstanding Balance": format_currency(outstanding, currency_sym)
+        })
+
+    total_outstanding_cum = total_called_cum - total_received_cum
+    called_pct_overall = (total_called_cum / total_fund_commitment * 100) if total_fund_commitment > 0 else 0.0
+    received_pct_overall = (total_received_cum / total_fund_commitment * 100) if total_fund_commitment > 0 else 0.0
+
+    col_sum1, col_sum2, col_sum3, col_sum4 = st.columns(4)
     with col_sum1:
         st.metric("Total LP Commitments", format_currency(total_fund_commitment, currency_sym))
-    
     with col_sum2:
-        if lp_calls:
-            summary_data = []
-            for c in lp_calls:
-                call_pct = c["call_pct"] / 100.0
-                total_called_amount = total_fund_commitment * call_pct
-                
-                paid_commit = 0
-                for inv in investors:
-                    payment = next((p for p in payments if p["lp_call_id"] == c["id"] and p["investor_id"] == inv["id"]), None)
-                    if payment and payment["is_paid"]:
-                        paid_commit += float(inv.get("commitment", 0))
-                
-                total_paid_amount = paid_commit * call_pct
-                outstanding = total_called_amount - total_paid_amount
-                
-                summary_data.append({
-                    "Call": f"{c['call_date']} ({c['call_pct']}%)",
-                    "Total Required": format_currency(total_called_amount, currency_sym),
-                    "Total Received": format_currency(total_paid_amount, currency_sym),
-                    "Outstanding Balance": format_currency(outstanding, currency_sym)
-                })
-            st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)
-        else:
-            st.info("No active capital calls yet.")
+        st.metric("Total Called to Date", format_currency(total_called_cum, currency_sym), f"{called_pct_overall:.1f}% of commitments")
+    with col_sum3:
+        st.metric("Total Received to Date", format_currency(total_received_cum, currency_sym), f"{received_pct_overall:.1f}% of commitments")
+    with col_sum4:
+        st.metric("Outstanding", format_currency(total_outstanding_cum, currency_sym))
+
+    if lp_calls:
+        st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)
+    else:
+        st.info("No active capital calls yet.")
+
 
     st.divider()
     st.markdown("### ➕ Manage LP Capital Calls")
