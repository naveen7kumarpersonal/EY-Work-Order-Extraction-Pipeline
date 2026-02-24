# src/llm_fallback.py
"""
LLM fallback: cleans up and fills gaps left by rule-based extraction.
Sends only the most information-dense pages to save tokens.
Merges LLM output carefully — never overwrites confident rule-based values.
"""

import json
import re
from typing import Any, Dict

from src.azure_openai import client, OPENAI_DEPLOYMENT, EXTRACTION_PROMPT, SYSTEM_PROMPT
from src.cleaner import clean_full_document_text


# Fields considered "mandatory" — if any are empty we trigger LLM
_MANDATORY_HEADER_FIELDS = {
    "Order Number", "Order Date", "Validity From", "Validity To",
    "Vendor Code", "Payment Terms",
}

_MANDATORY_PRICING_FIELDS = {
    "Diesel Component %", "Base HSD (INR/L)", "Gross Price (INR)",
}


def should_use_llm(extracted_data: Dict[str, Any]) -> bool:
    """
    Trigger LLM only when rule-based extraction is meaningfully incomplete.
    Avoids unnecessary API calls (and cost) when rules worked well.
    """
    header  = extracted_data.get("header", {})
    pricing = extracted_data.get("pricing", {})
    services = extracted_data.get("services", [])

    missing_header  = [f for f in _MANDATORY_HEADER_FIELDS  if not header.get(f)]
    missing_pricing = [f for f in _MANDATORY_PRICING_FIELDS if not pricing.get(f)]

    if missing_header or missing_pricing:
        print(f"  → Missing header fields:  {missing_header}")
        print(f"  → Missing pricing fields: {missing_pricing}")
        return True

    if not services:
        print("  → No service items extracted — triggering LLM")
        return True

    return False


def _smart_truncate(text: str, max_chars: int = 12000) -> str:
    """
    Keep the most information-dense part of the document.
    The header + service items + pricing are always in the first ~8 pages.
    Change orders are near the end. Skip the middle safety/legal boilerplate.
    """
    if len(text) <= max_chars:
        return text

    # First 8000 chars = header, services, pricing, scope
    head = text[:8000]

    # Last 2000 chars = change orders, footer
    tail = text[-2000:]

    combined = head + "\n\n[... middle section omitted for brevity ...]\n\n" + tail
    return combined


def _parse_llm_json(raw: str) -> Dict[str, Any]:
    """Parse JSON from LLM response, handling markdown fences and partial wrapping."""
    # Strip markdown code fences if present
    raw = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.M)
    raw = re.sub(r'```\s*$', '', raw.strip(), flags=re.M)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract the JSON object
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end])
        raise ValueError("LLM response contained no valid JSON block")


def _merge(rule_data: Dict, llm_data: Dict, key: str) -> Dict:
    """
    Merge LLM section into rule_data section.
    Rule values win if non-empty; LLM fills gaps.
    """
    rule_section = rule_data.get(key, {})
    llm_section  = llm_data.get(key, {})

    if not isinstance(llm_section, dict):
        return rule_section

    merged = dict(llm_section)  # start with LLM
    for k, v in rule_section.items():
        if v:  # rule value wins when non-empty
            merged[k] = v

    return merged


def enhance_with_llm(full_text: str, existing_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a token-efficient slice of the document to the LLM.
    Fill gaps in existing_data without overwriting confident rule values.
    """
    print("  → Cleaning and truncating text for LLM...")
    cleaned  = clean_full_document_text(full_text)
    truncated = _smart_truncate(cleaned, max_chars=12000)

    prompt = EXTRACTION_PROMPT.replace("{text}", truncated)

    print("  → Calling Azure OpenAI...")
    try:
        response = client.chat.completions.create(
            model=OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.0,
            max_tokens=3000,
            top_p=1.0,
        )
        raw = response.choices[0].message.content.strip()
        llm_output = _parse_llm_json(raw)
        print("  → LLM extraction successful")

    except Exception as e:
        print(f"  ⚠ LLM call failed: {e}")
        return existing_data

    # Merge — rule values always win over LLM values
    merged = dict(existing_data)
    merged["header"]  = _merge(existing_data, llm_output, "header")
    merged["pricing"] = _merge(existing_data, llm_output, "pricing")

    # For text blocks, LLM is usually better (it can clean OCR noise in long text)
    if llm_output.get("text_blocks"):
        llm_tb   = llm_output["text_blocks"]
        rule_tb  = existing_data.get("text_blocks", {})
        merged["text_blocks"] = {**llm_tb, **{k: v for k, v in rule_tb.items() if v}}

    # Services: use LLM if rules found nothing, otherwise keep rules
    if not existing_data.get("services") and llm_output.get("services"):
        merged["services"] = llm_output["services"]

    # Change orders: merge both lists (rules pattern-match better for C/O blocks)
    rule_co = existing_data.get("change_orders", [])
    llm_co  = llm_output.get("change_orders", [])
    if rule_co:
        merged["change_orders"] = rule_co
    elif llm_co:
        merged["change_orders"] = llm_co

    return merged