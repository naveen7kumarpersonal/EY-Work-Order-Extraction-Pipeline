# src/rule_extractor.py
"""
Rule-based extraction for Indian coal transportation work order PDFs.
Full text comes from pdf_extractor (all 51 pages). Azure DI used only for KV pairs.
"""

import re
from typing import Any, Dict, List
from datetime import datetime

from azure.ai.documentintelligence.models import AnalyzeResult
from src.cleaner import clean_raw_paragraph, clean_text
from src.pdf_extractor import extract_text_from_pdf, get_two_col_headers


def _find(pattern: str, text: str, group: int = 1, flags: int = re.I) -> str:
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else ""


def _build_kvp_map(result: AnalyzeResult) -> Dict[str, str]:
    kvps: Dict[str, str] = {}
    for kvp in result.key_value_pairs or []:
        if kvp.key and kvp.value and kvp.key.content and kvp.value.content:
            k = clean_text(kvp.key.content).lower().strip()
            v = clean_text(kvp.value.content).strip()
            if k and v:
                kvps[k] = v
    return kvps


def _kvp_get(kvps: Dict[str, str], *keywords: str) -> str:
    for k, v in kvps.items():
        if any(kw in k for kw in keywords):
            return v
    return ""


# ─────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────

def _extract_header(full_text: str, kvps: Dict[str, str]) -> Dict[str, str]:
    h: Dict[str, str] = {}

    # Priority: two-column page-1 resolver > KV pairs > regex
    two_col = get_two_col_headers()

    h["Order Number"] = (
        two_col.get("Order Number")
        or _kvp_get(kvps, "order no", "contract number", "order number")
        or _find(r':[-\s]+Test\s+Order\s+No\.?', full_text, group=0)
    )
    h["Order Date"] = (
        two_col.get("Order Date")
        or _kvp_get(kvps, "order date")
        or _find(r'Order\s+Date\s*:-?\s*(\d{2}\.\d{2}\.\d{4})', full_text)
    )
    h["Release Date"] = (
        two_col.get("Release Date")
        or _kvp_get(kvps, "release date")
        or _find(r'Release\s+Date\s*:-?\s*(\d{2}\.\d{2}\.\d{4})', full_text)
    )

    vm = re.search(r'Order\s+Valid\s+from\s+(\d{2}\.\d{2}\.\d{4})\s+to\s+(\d{2}\.\d{2}\.\d{4})', full_text, re.I)
    if vm:
        h["Validity From"] = vm.group(1)
        h["Validity To"]   = vm.group(2)

    h["Vendor Code"] = (
        _kvp_get(kvps, "vendor code")
        or _find(r'Vendor\s+Code\s*:-?\s*(<[^>]+>|[A-Z0-9\-]+)', full_text)
    )
    h["Vendor Name"] = _kvp_get(kvps, "vendor name") or _find(r'(<VENDOR\s*NAME>)', full_text)
    h["Payment Terms"] = (
        _kvp_get(kvps, "payment")
        or _find(r'Payment\s+Terms?\s*:\s*(\d+\s*[Dd]ays?)', full_text)
    )

    gm = re.search(r'((?:All\s+)?(?:CGST|SGST|IGST)[^\n|]*@\s*\d+%[^\n|]*?Creditable)', full_text, re.I)
    h["GST Info"] = gm.group(1).strip() if gm else ""

    h["Contact Email"] = (
        two_col.get("Contact Email")
        or _find(r'E-Mail\s*:-?\s*\|?\s*(@?<[^>]+>[^\s|]*)', full_text)
    )

    h["Order Ceiling Value (INR)"] = (
        _find(r'Order\s+Ceiling\s+Value\s*:\s*([\d,]+(?:\.\d+)?)\s*INR', full_text)
        or _find(r'Order\s+Ceiling\s+Value\s*:\s*([\d,]+(?:\.\d+)?)', full_text)
    )

    return {k: v for k, v in h.items() if v}


# ─────────────────────────────────────────────────────────────
# Services
# ─────────────────────────────────────────────────────────────

def _extract_services(full_text: str) -> List[Dict[str, str]]:
    item_hdr_pat = re.compile(
        r'\b(\d{1,2})\s+(\d{2})\s+(MS\d+)\s+((?:TRANSPORTATION|LOADING|HANDLING|LIFTING)[^|]{5,80})',
        re.I
    )
    rate_pat = re.compile(r'Total\s+Price\s+([\d,]+\.?\d*)\s*/\s*([\w\s]+?)\s+INR', re.I)
    long_pat = re.compile(
        r'Service\s+Long\s+Text\s*:?\s*\|?\s*(.*?)(?=Contract\s+Item\s+Service\s+Conditions|Total\s+Price)',
        re.I | re.DOTALL
    )

    headers   = list(item_hdr_pat.finditer(full_text))
    rates     = list(rate_pat.finditer(full_text))
    long_txts = list(long_pat.finditer(full_text))

    if not headers:
        return []

    services = []
    for idx, hm in enumerate(headers):
        sr_no  = hm.group(1)
        srv_ln = hm.group(2)
        srv_no = hm.group(3)
        # FIX: strip "Service Long Text" noise that gets appended to brief description
        brief = re.sub(r'\s*Service\s+Long\s+Text.*$', '', hm.group(4), flags=re.I).strip()
        brief = re.sub(r'\s*\|.*$', '', brief).strip()

        hdr_end  = hm.end()
        next_hdr = headers[idx + 1].start() if idx + 1 < len(headers) else len(full_text)

        long_text = ""
        for lt in long_txts:
            if hdr_end <= lt.start() < next_hdr:
                raw_lt = lt.group(1)
                # FIX: strip two-column header noise that pypdf inserts between
                # "Service Long Text :" and the actual prose on the next page
                _noise = re.compile(
                    r'^(?:Vendor\s+Code|<VENDOR|<>$|Order\s+No\.|Order\s+Date|'
                    r'Release\s+Date|Contact\s+Person|E-Mail|Box\s+No|Phone\s+No|'
                    r'Fax\s+No|Quotation|Order\s+Valid\s+from|:-)',
                    re.I
                )
                good_segs = [
                    s.strip() for s in raw_lt.split('|')
                    if s.strip() and not _noise.match(s.strip()) and len(s.strip()) > 10
                ]
                long_text = re.sub(r'\s+', ' ', ' '.join(good_segs)).strip()
                break

        rate = unit = ""
        for r in rates:
            if hdr_end <= r.start() < next_hdr:
                rate = r.group(1)
                unit = r.group(2).strip()
                break

        services.append({
            "Sr No": sr_no, "SrvLnNo": srv_ln, "SrvNo": srv_no,
            "Brief Description": brief, "Long Text": long_text,
            "Rate": rate, "Unit": unit,
        })

    seen: set = set()
    return [s for s in services if not (s["SrvNo"] in seen or seen.add(s["SrvNo"]))]


# ─────────────────────────────────────────────────────────────
# Pricing
# ─────────────────────────────────────────────────────────────

def _extract_pricing(full_text: str) -> Dict[str, str]:
    p: Dict[str, str] = {}

    p["Diesel Component %"] = _find(r'Diesel\s+component\s+(?:in\s+PVC\s*)?:\s*(\d+)\s*%', full_text)

    hm = re.search(r'Base\s+HSD\s+reference\s*:\s*INR\s*([\d.]+)\s*/\s*L.*?(\d{2}\.\d{2}\.\d{4})', full_text, re.I | re.DOTALL)
    if hm:
        p["Base HSD (INR/L)"]   = hm.group(1)
        p["HSD Reference Date"] = hm.group(2)

    p["HSD Source"]        = _find(r'Ref\s*:\s*([^;|()]+?)\s*(?:as\s+on|;|\))', full_text)
    p["Gross Price (INR)"] = _find(r'Gross\s+Price\s+([\d,]+\.?\d*)\s*INR', full_text)

    for i, rm in enumerate(re.finditer(r'Total\s+Price\s+([\d,]+\.?\d*)\s*/\s*([\w\s]+?)\s+INR', full_text, re.I), 1):
        p[f"Item {i} Rate"] = rm.group(1)
        p[f"Item {i} Unit"] = rm.group(2).strip()

    p["Order Ceiling Value (INR)"] = (
        _find(r'Order\s+Ceiling\s+Value\s*:\s*([\d,]+(?:\.\d+)?)\s*INR', full_text)
        or _find(r'Order\s+Ceiling\s+Value\s*:\s*([\d,]+(?:\.\d+)?)', full_text)
    )
    p["Total Order Value (INR)"] = _find(
        r'TOTAL\s+ORDER\s+VALUE\s+PAYABLE[^:]*:\s*([\d,]+(?:\.\d+)?)\s*INR', full_text, flags=re.I
    )

    return {k: v for k, v in p.items() if v}


# ─────────────────────────────────────────────────────────────
# Text blocks
# ─────────────────────────────────────────────────────────────

def _extract_text_blocks(full_text: str) -> Dict[str, str]:
    blocks: Dict[str, str] = {}

    # Scope of Work
    # FIX: "Header text:" is followed by a pipe then "RAW COAL..." — anchor correctly
    sm = re.search(
        r'Header\s+text\s*:.*?\|\s*(RAW\s+COAL.*?)'
        r'(?:\|\s*(?:Diesel\s+component|Base\s+HSD))',
        full_text, re.I | re.DOTALL
    )
    if sm:
        blocks["Scope of Work"] = re.sub(r'\s+', ' ', re.sub(r'\s*\|\s*', ' ', sm.group(1))).strip()[:2000]

    # Safety Norms
    # FIX: "COMPLIANCETO" has no space (OCR) — use \s* between COMPLIANCE and TO
    # Cap at 3000 chars (the dedicated safety section on page 15)
    safm = re.search(r'COMPLIANCE\s*TO\s+SAFETY[,\s&]+(?:ENVIRONMENTAL|STATUATORY|STATUTORY)', full_text, re.I)
    if safm:
        raw_s = full_text[safm.start():safm.start() + 3200]
        # Snap to last pipe before 3000 chars for a clean cut
        cut = raw_s.rfind('|', 0, 3000)
        raw_s = raw_s[:cut] if cut > 0 else raw_s[:3000]
        blocks["Safety Norms"] = re.sub(r'\s+', ' ', re.sub(r'\s*\|\s*', ' ', raw_s)).strip()
    else:
        sents = re.findall(r'[^.|]*(?:DGMS|statutory\s+(?:norm|compliance)|safety\s+norms?)[^.|]*[.|]', full_text, re.I)
        if sents:
            blocks["Safety Norms"] = " ".join(s.strip() for s in sents[:10])

    # Exit Clause — section 9 in the document
    exm = re.search(
        r'((?:9\.0\s+)?(?:Temporary\s+Suspension\s+and\s+)?Cancellation\s+or\s+Termination\s+of\s+Contract.*?)'
        r'(?=\|\s*(?:10\.|Force\s+Majeure|Payment|NOTE\s*:))',
        full_text, re.I | re.DOTALL
    )
    if not exm:
        exm = re.search(r'(Exit\s+clause.*?)(?=\|\s*(?:Payment|COMPLIANCE|NOTE\s*:))', full_text, re.I | re.DOTALL)
    if exm:
        blocks["Exit Clause"] = re.sub(r'\s+', ' ', re.sub(r'\s*\|\s*', ' ', exm.group(1))).strip()[:2000]
    else:
        blocks["Exit Clause"] = _find(r'(liberty\s+to\s+terminate[^.]+\d+\s+days[^.]+\.)', full_text, flags=re.I | re.DOTALL) or "Not found"

    # Payment Terms Detail — "Payment Term : 100% within 60 days..."
    pym = re.search(
        r'(Payment\s+Term\s*:.*?)(?=\|\s*(?:Order\s+Ceiling|TOTAL\s+ORDER|Collection|SPECIAL))',
        full_text, re.I | re.DOTALL
    )
    if pym:
        blocks["Payment Terms Detail"] = re.sub(r'\s+', ' ', re.sub(r'\s*\|\s*', ' ', pym.group(1))).strip()[:1500]

    return {k: v for k, v in blocks.items() if v}


# ─────────────────────────────────────────────────────────────
# Change Orders
# ─────────────────────────────────────────────────────────────

def _extract_change_orders(full_text: str) -> List[Dict[str, str]]:
    orders = []
    for block in re.split(r'(?=NOTE\s*:\s*C/O\s+DATED)', full_text, flags=re.I):
        dm = re.search(r'C/O\s+DATED\s+(\d{2}[.\-/]\d{2}[.\-/]\d{4})', block, re.I)
        if not dm:
            continue

        desc_m = re.search(
            r'={3,}\s*(.*?)(?=NOTE\s*:\s*C/O|\|\s*(?:Delivery|Payment|Order\s+Ceiling|NOTE\s*:|TOTAL|Collection)|\Z)',
            block, re.I | re.DOTALL
        )
        desc = ""
        if desc_m:
            desc = re.sub(r'\s*\|\s*', ' ', desc_m.group(1))
            desc = re.sub(r'\s+', ' ', desc).strip()
            # Strip any "Order No." noise that bleeds in
            desc = re.sub(r'\s+Order\s+No\..*$', '', desc, flags=re.I).strip()

        atype = (
            "Validity Extension"   if re.search(r'validity\s+extended|extended\s+till', desc, re.I) else
            "Ceiling Value Change"  if re.search(r'ceiling|increase|value', desc, re.I) else
            "Amendment"
        )
        new_val   = _find(r'till\s+(\d{2}[-./]\d{2}[-./]\d{4})', desc)
        ceil_chng = (
            _find(r'from\s+[\d.]+\s*CR\s+to\s+([\d.]+\s*CR)', desc, flags=re.I)
            or _find(r'by\s+Rs\.?\s*([\d.,]+\s*(?:Cr|CR|Lakh|Lakhs))', desc, flags=re.I)
            or _find(r'([\d.,]+\s*(?:Cr|CR|Lakh|Lakhs))', desc, flags=re.I)
        )

        orders.append({
            "C/O Date": dm.group(1), "Amendment Type": atype,
            "Description": desc, "New Validity": new_val, "Ceiling Change": ceil_chng,
        })
    return orders


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────

def extract_workorder(result: AnalyzeResult, pdf_path: str) -> Dict[str, Any]:
    """
    Args:
        result   : Azure DI AnalyzeResult (KV pairs from structured pages 1-2)
        pdf_path : PDF file path — used for direct pypdf text extraction
    """
    full_text = extract_text_from_pdf(pdf_path)  # All 51 pages
    kvps      = _build_kvp_map(result)            # KV pairs from DI pages 1-2

    return {
        "header":        _extract_header(full_text, kvps),
        "services":      _extract_services(full_text),
        "pricing":       _extract_pricing(full_text),
        "text_blocks":   _extract_text_blocks(full_text),
        "change_orders": _extract_change_orders(full_text),
        "metadata": {
            "pages":        result.pages[-1].page_number if result.pages else 0,
            "paragraphs":   len(result.paragraphs or []),
            "kv_pairs":     len(result.key_value_pairs or []),
            "tables":       len(result.tables or []),
            "model":        "prebuilt-layout",
            "extracted_at": datetime.now().isoformat(),
        }
    }