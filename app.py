def show_reports():
    st.title("📈 Quarterly Reports")
    funds = get_funds()
    if not funds:
        st.info("No funds in the system")
        return

    # --- הוספת טבלת סיכום שערוכים ---
    st.subheader("📊 Portfolio Valuations Summary")
    all_reports = get_quarterly_reports()
    if all_reports:
        # איתור הדוח האחרון ביותר של כל קרן
        latest_reports = {}
        for r in all_reports:
            fid = r["fund_id"]
            if fid not in latest_reports:
                latest_reports[fid] = r
            else:
                curr = latest_reports[fid]
                if r["year"] > curr["year"] or (r["year"] == curr["year"] and r["quarter"] > curr["quarter"]):
                    latest_reports[fid] = r
        
        summary_data = []
        for f in funds:
            if f["id"] in latest_reports:
                rep = latest_reports[f["id"]]
                sym = "€" if f.get("currency") == "EUR" else "$"
                nav = rep.get("nav") or 0
                
                tvpi_str = f"{float(rep['tvpi']):.2f}x" if rep.get("tvpi") is not None else "—"
                dpi_str = f"{float(rep['dpi']):.2f}x" if rep.get("dpi") is not None else "—"
                irr_str = f"{float(rep['irr']):.1f}%" if rep.get("irr") is not None else "—"
                
                summary_data.append({
                    "Fund Name": f["name"],
                    "Latest Report": f"Q{rep['quarter']}/{rep['year']}",
                    "NAV": format_currency(nav, sym),
                    "TVPI": tvpi_str,
                    "DPI": dpi_str,
                    "IRR": irr_str
                })
        if summary_data:
            st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)
        else:
            st.info("No valuation data available yet.")
    else:
        st.info("No reports have been uploaded yet.")

    st.divider()
    st.markdown("### 🔍 Detailed Fund Reports")

    fund_options = {f["name"]: f["id"] for f in funds}
    selected_fund_name = st.selectbox("Select Fund", list(fund_options.keys()))
    fund_id = fund_options[selected_fund_name]
    reports = get_quarterly_reports(fund_id)

    if reports:
        col_hdr1, col_hdr2 = st.columns([4, 1])
        with col_hdr1:
            st.subheader(f"Reports – {selected_fund_name}")
        with col_hdr2:
            df_rep = pd.DataFrame([{"Year": r["year"], "Quarter": f"Q{r['quarter']}", "NAV": r.get("nav"),
                                    "TVPI": r.get("tvpi"), "DPI": r.get("dpi"), "RVPI": r.get("rvpi"),
                                    "IRR %": r.get("irr"), "Notes": r.get("notes","")} for r in reports])
            excel_data = convert_df_to_excel(df_rep)
            st.download_button("📥 Export to Excel", data=excel_data, file_name=f"Reports_{selected_fund_name}_{date.today()}.xlsx", use_container_width=True)
            
        st.dataframe(df_rep, use_container_width=True, hide_index=True)
    else:
        st.info("No quarterly reports for this fund yet.")

    st.divider()
    st.markdown("**🤖 Add Quarterly Report from File (AI Extraction)**")
    uploaded_rep_file = st.file_uploader("Upload Quarterly Report (PDF / Excel / CSV)", type=["pdf", "xlsx", "xls", "csv"], key="global_rep_uploader")
    
    if uploaded_rep_file:
        if st.button("Analyze Document Now", type="primary", key="global_rep_analyze_btn"):
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
                    st.session_state["global_rep_ai_result"] = ai_result
                    st.success("✅ Data extracted successfully! Please review and confirm in the form below.")
                except Exception as e:
                    st.error(f"Error analyzing document: {e}. (If Excel, ensure openpyxl is in requirements.txt)")

    st.divider()
    st.markdown("**➕ Or Enter Details Manually**")
    
    ai_rep = st.session_state.get("global_rep_ai_result", {})
    
    def_year = int(ai_rep.get("year")) if ai_rep.get("year") else 2025
    def_quarter = int(ai_rep.get("quarter")) if ai_rep.get("quarter") in [1,2,3,4] else 1
    
    def_rep_date = date.today()
    if ai_rep.get("report_date"):
        try: def_rep_date = datetime.strptime(ai_rep["report_date"], "%Y-%m-%d").date()
        except: pass

    with st.form("add_report"):
        col1, col2, col3 = st.columns(3)
        with col1:
            year = st.number_input("Year", value=def_year, min_value=2020, max_value=2030)
            quarter = st.selectbox("Quarter", [1, 2, 3, 4], index=[1,2,3,4].index(def_quarter))
            report_date = st.date_input("Report Date", value=def_rep_date)
        with col2:
            nav = st.number_input("NAV", min_value=0.0, value=float(ai_rep.get("nav") or 0.0))
            tvpi = st.number_input("TVPI", min_value=0.0, step=0.01, format="%.2f", value=float(ai_rep.get("tvpi") or 0.0))
            dpi = st.number_input("DPI", min_value=0.0, step=0.01, format="%.2f", value=float(ai_rep.get("dpi") or 0.0))
        with col3:
            rvpi = st.number_input("RVPI", min_value=0.0, step=0.01, format="%.2f", value=float(ai_rep.get("rvpi") or 0.0))
            irr = st.number_input("IRR %", step=0.1, format="%.1f", value=float(ai_rep.get("irr") or 0.0))
            notes = st.text_area("Notes")
        if st.form_submit_button("Save Report", type="primary"):
            try:
                get_supabase().table("quarterly_reports").upsert({
                    "fund_id": fund_id, "year": year, "quarter": quarter,
                    "report_date": str(report_date), "nav": nav,
                    "tvpi": tvpi, "dpi": dpi, "rvpi": rvpi, "irr": irr, "notes": notes
                }).execute()
                st.session_state.pop("global_rep_ai_result", None)
                st.success("✅ Report saved!")
                clear_cache_and_rerun()
            except Exception as e:
                st.error(f"Error: {e}")
