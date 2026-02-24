# src/azure_openai.py
"""
Azure OpenAI client for structured JSON extraction from noisy work order text.
Uses a system prompt + user prompt split for better instruction following.
"""

from openai import AzureOpenAI
from src.config import OPENAI_ENDPOINT, OPENAI_KEY, OPENAI_DEPLOYMENT, OPENAI_API_VERSION

client = AzureOpenAI(
    azure_endpoint=OPENAI_ENDPOINT,
    api_key=OPENAI_KEY,
    api_version=OPENAI_API_VERSION,
)

SYSTEM_PROMPT = """You are an expert data extractor specializing in Indian coal transportation
work orders issued by large steel/mining companies. These documents are scanned PDFs with
heavy OCR noise: broken words, missing spaces, run-on text, and redacted placeholders like
<VENDOR NAME> and <CLIENT NAME>.

Your job:
1. Extract every field listed in the JSON schema below — do not skip any.
2. Fix all OCR errors (broken words, extra spaces, garbled text) in your output.
3. For redacted placeholders like <VENDOR NAME>, preserve them exactly as-is.
4. Output ONLY valid JSON. No preamble, no explanation, no markdown fences.
5. If a field is not found, use "" (empty string) — never null, never omit the key."""

EXTRACTION_PROMPT = """Extract all fields from the following work order text into this exact JSON structure:

{
  "header": {
    "Order Number": "",
    "Order Date": "DD.MM.YYYY",
    "Release Date": "DD.MM.YYYY",
    "Validity From": "DD.MM.YYYY",
    "Validity To": "DD.MM.YYYY",
    "Vendor Code": "",
    "Vendor Name": "",
    "Payment Terms": "",
    "GST Info": "",
    "Contact Email": "",
    "Order Ceiling Value (INR)": ""
  },
  "services": [
    {
      "Sr No": "",
      "SrvLnNo": "",
      "SrvNo": "",
      "Brief Description": "",
      "Long Text": "",
      "Rate": "",
      "Unit": ""
    }
  ],
  "pricing": {
    "Diesel Component %": "",
    "Base HSD (INR/L)": "",
    "HSD Reference Date": "DD.MM.YYYY",
    "HSD Location": "",
    "Gross Price (INR)": "",
    "Item 1 Rate": "",
    "Item 1 Unit": "",
    "Item 2 Rate": "",
    "Item 2 Unit": "",
    "Order Ceiling Value (INR)": ""
  },
  "text_blocks": {
    "Scope of Work": "",
    "Safety Norms": "",
    "Exit Clause": "",
    "Payment Terms Detail": ""
  },
  "change_orders": [
    {
      "C/O Date": "DD.MM.YYYY",
      "Amendment Type": "",
      "Description": "",
      "New Validity": "",
      "Ceiling Change": ""
    }
  ]
}

DOCUMENT TEXT:
{text}"""