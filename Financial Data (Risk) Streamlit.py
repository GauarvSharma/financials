import streamlit as st
import pandas as pd
import io
import os

# --- CONFIG ---
st.set_page_config(page_title="Loan Portfolio", layout="centered")

# Secret for owner authentication
OWNER_PASSWORD = st.secrets.get("OWNER_PASSWORD", "")

# Path where we’ll save the last output
OUTPUT_PATH = "Loan_Portfolio.xlsx"

st.title("Loan Portfolio")

# --- AUTHENTICATION ---
password = st.sidebar.text_input("Owner Password", type="password")
is_owner = (password == OWNER_PASSWORD)

if is_owner:
    st.sidebar.success("Authenticated as owner ✅")
elif password:
    st.sidebar.error("Incorrect password ❌")

# Keep track of whether processing just happened
if "just_processed" not in st.session_state:
    st.session_state.just_processed = False

# --- OWNER VIEW: Upload & Process ---
if is_owner:
    st.markdown("### 📂 Owner: Upload & Process Files")
    loan_file = st.file_uploader("Loan Portfolio File", type=["xlsx","xls"])
    arc_file  = st.file_uploader("ARC Finance File",   type=["xlsx","xls"])
    lms_file  = st.file_uploader("LMS053 Voucher MIS File", type=["xlsx","xls"])

    if loan_file and arc_file and lms_file and st.button("Process & Save"):
        try:
            # — Load & Filter Loan Portfolio —
            loan_df = pd.read_excel(loan_file)
            loan_df = loan_df[loan_df['accounting_writeoff'].fillna('').str.lower() != 'yes']
            loan_df = loan_df[loan_df['loan_status'].fillna('').str.lower() == 'active']

            # — Keep only specified columns —
            keep_cols = [
                "loan_account_number","customer_name","cibil","product_code","product_name",
                "interest_rate","original_tenure","ltv","login_date","sourcing_channel",
                "dsa_name","dealer_code","dealer_name","collateral_type","model",
                "model_year","registration_number","chasis_no","engine_no","sanction_date",
                "sanctioned_amount","interest_start_date","repayment_start_date","maturity_date",
                "installment_amount","disbursal_date","disbursal_amount","pending_amount",
                "disbursal_status","principal_outstanding","total_excess_money","dpd","dpd_wise",
                "asset_classification","credit_manager_id","credit_manager_name","sourcing_rm_id",
                "sourcing_rm_name","branch_id","branch_code","branch_name","state","repayment_mode",
                "nach_status","loan_status"
            ]
            loan_df = loan_df[[c for c in keep_cols if c in loan_df.columns]]

            # — ARC Lookup & filter —
            arc_df = pd.read_excel(arc_file)
            arc_df.columns = arc_df.columns.str.strip()
            arc_col = next((c for c in arc_df.columns if 'loan_account_number' in c.lower()), None)
            if not arc_col:
                st.error("ARC Finance file needs a loan_account_number column."); st.stop()
            loan_df['ARC Lookup'] = loan_df['loan_account_number'].apply(
                lambda v: v if v in arc_df[arc_col].values else None
            )
            loan_df = loan_df[loan_df['ARC Lookup'].isna()].drop(columns=['ARC Lookup'])

            # — LMS053 accrual processing —
            lms_df = pd.read_excel(lms_file)
            lms_df.columns = lms_df.columns.str.strip()
            if 'Gl Desc' not in lms_df.columns:
                st.error("LMS053 needs a 'Gl Desc' column."); st.stop()
            lms_df = lms_df[lms_df['Gl Desc'].str.upper()=='ACCRUAL INCOME']
            if not all(c in lms_df.columns for c in ['Loan Account Number','Debit Amount']):
                st.error("LMS053 needs 'Loan Account Number' & 'Debit Amount'."); st.stop()
            accrual = (
                lms_df[['Loan Account Number','Debit Amount']]
                .groupby('Loan Account Number')['Debit Amount']
                .sum().reset_index()
                .rename(columns={'Loan Account Number':'loan_account_number','Debit Amount':'Accrul_Amount'})
            )
            loan_df = loan_df.merge(accrual, on='loan_account_number', how='left')
            loan_df['Accrul_Amount'] = loan_df['Accrul_Amount'].fillna(0)

            # — AUM calculation —
            cols = loan_df.columns.tolist()
            try:
                AB, AD, AE, AT = cols[27], cols[29], cols[30], cols[45]
            except IndexError:
                st.error("Not enough columns to calculate AUM."); st.stop()
            loan_df['AUM'] = loan_df.apply(
                lambda r: max(r[AD] - (r[AB] + r[AE]), 0) + r[AT], axis=1
            )

            # — Write to server disk —
            loan_df.to_excel(OUTPUT_PATH, index=False, sheet_name="Loan Portfolio")
            st.success("Processing complete and saved to server!")
            st.session_state.just_processed = True

        except Exception as e:
            st.error(f"Error: {e}")

# --- DOWNLOAD SECTION: Only show AFTER processing ---
if st.session_state.just_processed and os.path.exists(OUTPUT_PATH):
    st.markdown("---")
    st.markdown("### 📥 Loan Portfolio")
    with open(OUTPUT_PATH, "rb") as f:
        data = f.read()
    st.download_button(
        label="Download Excel File",
        data=data,
        file_name="Loan_Portfolio.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
