import streamlit as st
import pdfplumber
import pandas as pd
import google.generativeai as genai
import json
import io

# Set up the page
st.set_page_config(page_title="Invoice Extractor", page_icon="🧾", layout="centered")
st.title("🧾 Shiprocket to Tally Converter")
st.write("Upload a Shiprocket invoice PDF to instantly generate a Tally-ready CSV.")

# Get API key securely from Streamlit's secrets
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-pro')
except Exception as e:
    st.error("Please configure your Gemini API Key in the settings.")

def extract_invoice_data(pdf_file):
    """Reads the PDF and asks Gemini to extract the core numbers."""
    text = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
            
    prompt = f"""
    You are an expert data extractor. Read this Shiprocket invoice and extract these exact fields:
    1. voucher_date (format: YYYY-MM-DD, derived from Invoice Date)
    2. voucher_number (the exact Invoice No)
    3. supplier_name (the name of the company in the header address)
    4. supplier_address (the full address in the header)
    5. gstin (the supplier GSTIN)
    6. place_of_supply (just the state name)
    7. pincode (extract the 6 digit pincode from the address)
    8. freight_amount (the amount for 'Shiprocket V2 Freight' WITHOUT commas)
    9. igst_amount (the amount for '18.00% IGST' WITHOUT commas)

    Return ONLY a valid JSON object with these keys. No markdown, no explanations.
    Text: {text}
    """
    
    response = model.generate_content(prompt)
    clean_json = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(clean_json)

def process_and_format_data(extracted_data):
    """Does the math and formats it to the exact Tally CSV structure."""
    
    # Do the accounting math
    freight = float(extracted_data['freight_amount'])
    igst = float(extracted_data['igst_amount'])
    tds = freight * 0.02
    final_bill_amount = (freight + igst) - tds
    
    # Create the exact Tally row format you provided
    tally_row = {
        "Voucher Date": extracted_data['voucher_date'],
        "Voucher Type Name": "Journal - Purchase",
        "Voucher Number": extracted_data['voucher_number'],
        "Reference No.": extracted_data['voucher_number'],
        "Reference Date": extracted_data['voucher_date'],
        "Bill Type of Ref": "New Ref",
        "Bill Name": extracted_data['voucher_number'],
        "Bill Amount": round(final_bill_amount, 4),
        "Bill Amount - Dr/Cr": "Cr",
        "Voucher Narration": "BEING TRANSPORTATION CHARGES.",
        "Description of Ledger": "",
        "Buyer/Supplier - Bill to/from": extracted_data['supplier_name'],
        "Buyer/Supplier - Address Type": "Primary",
        "Buyer/Supplier - Mailing Name": extracted_data['supplier_name'],
        "Buyer/Supplier - Address": extracted_data['supplier_address'],
        "Buyer/Supplier - Country": "India",
        "Buyer/Supplier - State": extracted_data['place_of_supply'],
        "Buyer/Supplier - GST Registration Type": "Regular",
        "Buyer/Supplier - GSTIN/UIN": extracted_data['gstin'],
        "Buyer/Supplier - Pincode": extracted_data['pincode'],
        "Buyer/Supplier - Place of Supply": extracted_data['place_of_supply'],
        "GST Registration": f"{extracted_data['place_of_supply']} Registration",
        "Ledger Name": extracted_data['supplier_name'],
        "Ledger Amount": round(final_bill_amount, 4),
        "Ledger Amount Dr/Cr": "Cr",
        "Change Mode": "As Voucher"
    }
    
    return pd.DataFrame([tally_row])

# --- The App UI ---
uploaded_file = st.file_uploader("Drop your Shiprocket PDF here", type="pdf")

if uploaded_file is not None:
    with st.spinner("AI is reading the invoice and calculating TDS..."):
        try:
            # 1. Extract
            raw_data = extract_invoice_data(uploaded_file)
            
            # 2. Format & Calculate
            final_df = process_and_format_data(raw_data)
            
            # 3. Show Success
            st.success("Data extracted successfully!")
            st.dataframe(final_df) # Shows a preview of the data
            
            # 4. Download Button
            csv = final_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Tally CSV",
                data=csv,
                file_name=f"Tally_Import_{raw_data['voucher_number']}.csv",
                mime="text/csv",
            )
        except Exception as e:
            st.error(f"An error occurred: {e}")
