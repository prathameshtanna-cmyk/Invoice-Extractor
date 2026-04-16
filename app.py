import streamlit as st
import pdfplumber
import pandas as pd
import requests
import json

# Set up the page
st.set_page_config(page_title="Invoice Extractor", page_icon="🧾", layout="centered")
st.title("🧾 Shiprocket to Tally Converter")
st.write("Upload a Shiprocket invoice PDF to instantly generate a Tally-ready CSV.")

# Ask for the key directly
api_key_input = st.text_input("Enter your API Key:", type="password")

def extract_invoice_data(pdf_file, api_key):
    """Bypasses the SDK and uses a direct REST API call to Gemini."""
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
    
    # Direct API Call Endpoint
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    
    # We force the API to return strictly JSON
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    
    response = requests.post(url, headers=headers, json=payload)
    
    # If Google rejects it, this will tell us exactly WHY on the screen
    if response.status_code != 200:
        raise Exception(f"Google API Error {response.status_code}: {response.text}")
        
    result_json = response.json()
    clean_json = result_json['candidates'][0]['content']['parts'][0]['text']
    return json.loads(clean_json)

def process_and_format_data(extracted_data):
    """Does the math and formats it to the exact Tally CSV structure."""
    freight = float(extracted_data['freight_amount'])
    igst = float(extracted_data['igst_amount'])
    tds = freight * 0.02
    final_bill_amount = (freight + igst) - tds
    
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
if not api_key_input:
    st.warning("Please enter your API key above.")
else:
    uploaded_file = st.file_uploader("Drop your Shiprocket PDF here", type="pdf")

    if uploaded_file is not None:
        with st.spinner("AI is reading the invoice and calculating TDS..."):
            try:
                raw_data = extract_invoice_data(uploaded_file, api_key_input)
                final_df = process_and_format_data(raw_data)
                
                st.success("Data extracted successfully!")
                st.dataframe(final_df)
                
                csv = final_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download Tally CSV",
                    data=csv,
                    file_name=f"Tally_Import_{raw_data['voucher_number']}.csv",
                    mime="text/csv",
                )
            except Exception as e:
                st.error(f"Extraction failed: {e}")
