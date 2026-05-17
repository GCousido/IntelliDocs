import re
import unicodedata
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class ExtractionRequest(BaseModel):
    text: str
    label: str
    layout: dict[str, Any] | None = None

def normalize_text(value: str) -> str:
    value = value.strip().lower()
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = re.sub(r"\s+", " ", value)
    return value

def clean_value(value: str) -> str:
    value = value.strip(" \t\r\n:-|")
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip()

def extract_date(value: str) -> str | None:
    patterns = [
        r"\b\d{2}[/-]\d{2}[/-]\d{4}\b",
        r"\b\d{2}[.]\d{2}[.]\d{4}\b",
        r"\b\d{4}[/-]\d{2}[/-]\d{2}\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, value)
        if m:
            return m.group(0)
    return None

def extract_amount(value: str) -> str | None:
    matches = re.findall(
        r"(?:€|\$)?\s*\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})\b|(?:€|\$)?\s*\d+(?:[.,]\d{2})\b",
        value,
    )
    if matches:
        return clean_value(matches[-1])
    return None

def extract_dni_nif(value: str) -> str | None:
    patterns = [
        r"\b\d{8}[A-Za-z]\b",
        r"\b[A-HJNPQRSUVW]\d{7}[0-9A-J]\b",
        r"\b[XYZ]\d{7}[A-Za-z]\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, value, re.IGNORECASE)
        if m:
            return m.group(0)
    return None

def extract_invoice_number(value: str) -> str | None:
    m = re.search(r"\b[A-Za-z0-9][A-Za-z0-9\-\/]{3,}\b", value)
    return m.group(0) if m else None

def validate_name(value: str) -> str | None:
    value = clean_value(value)
    words = value.split()
    if len(words) < 1:
        return None
    alpha_ratio = sum(ch.isalpha() or ch.isspace() for ch in value) / max(len(value), 1)
    if alpha_ratio < 0.7:
        return None
    return value

def flatten_layout(layout: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not layout:
        return []

    items: list[dict[str, Any]] = []

    if isinstance(layout.get("layout"), list):
        for page_index, page in enumerate(layout["layout"], start=1):
            page_items = page.get("items", [])
            for item in page_items:
                box = item.get("box", {})
                text = clean_value(item.get("text", ""))
                if not text:
                    continue
                items.append(
                    {
                        "page": page_index,
                        "text": text,
                        "left": int(box.get("left", 0)),
                        "top": int(box.get("top", 0)),
                        "width": int(box.get("width", 0)),
                        "height": int(box.get("height", 0)),
                        "line_num": int(item.get("line_num", 0)),
                        "block_num": int(item.get("block_num", 0)),
                    }
                )

    return items

def group_layout_lines(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[int, int, int], list[dict[str, Any]]] = {}

    for item in items:
        key = (item["page"], item["block_num"], item["line_num"])
        groups.setdefault(key, []).append(item)

    lines = []
    for (page, block_num, line_num), group in groups.items():
        group = sorted(group, key=lambda x: (x["left"], x["top"]))
        text = " ".join(x["text"] for x in group).strip()
        left = min(x["left"] for x in group)
        top = min(x["top"] for x in group)
        right = max(x["left"] + x["width"] for x in group)
        bottom = max(x["top"] + x["height"] for x in group)

        if text:
            lines.append(
                {
                    "page": page,
                    "block_num": block_num,
                    "line_num": line_num,
                    "text": text,
                    "box": {
                        "left": left,
                        "top": top,
                        "width": right - left,
                        "height": bottom - top,
                    },
                }
            )

    lines.sort(key=lambda x: (x["page"], x["box"]["top"], x["box"]["left"]))
    return lines

def find_value_near_alias(
    lines: list[dict[str, Any]],
    aliases: list[str],
    validator,
) -> dict[str, Any] | None:
    best = None

    for idx, line in enumerate(lines):
        line_text_raw = line["text"]
        line_text = normalize_text(line_text_raw)

        for alias_order, alias in enumerate(aliases):
            alias_norm = normalize_text(alias)
            if alias_norm not in line_text:
                continue

            candidates = []

            m = re.search(rf"{re.escape(alias_norm)}\s*[:\-–—]?\s*(.+)$", line_text)
            if m:
                suffix_original = line_text_raw[len(line_text_raw) - len(m.group(1)):]
                candidates.append(("same_line", clean_value(suffix_original), 0.90 - alias_order * 0.02))

            if idx + 1 < len(lines) and lines[idx + 1]["page"] == line["page"]:
                candidates.append(("next_line", lines[idx + 1]["text"], 0.72 - alias_order * 0.02))

            for source, raw_value, score in candidates:
                value = validator(raw_value) if validator else clean_value(raw_value)
                if not value:
                    continue

                current = {
                    "value": value,
                    "score": round(score, 3),
                    "source": source,
                    "matched_alias": alias,
                    "line_index": idx,
                }

                if not best or current["score"] > best["score"]:
                    best = current

    return best

def regex_fallbacks(text: str, label: str) -> dict[str, str | None]:
    text_lower = text.lower()

    if label == "Factura":
        return {
            "fecha": extract_date(text),
            "total": next(
                (
                    clean_value(m)
                    for p in [
                        r"(?:total|importe total|total a pagar|amount due)[^\d]{0,12}([\d\.,]+\s*€?)",
                        r"(?:total)[^\d]{0,12}([\d\.,]+\s*€?)",
                    ]
                    for match in re.findall(p, text_lower)
                    for m in [match]
                ),
                None,
            ),
            "dni_nif": extract_dni_nif(text),
            "numero_factura": next(
                (
                    clean_value(m)
                    for p in [
                        r"(?:factura|invoice|n[úu]mero factura|invoice number|invoice no)[^\w]{0,8}([A-Za-z0-9\-\/]+)"
                    ]
                    for match in re.findall(p, text, flags=re.IGNORECASE)
                    for m in [match]
                ),
                None,
            ),
        }

    if label == "Ticket":
        return {
            "fecha": extract_date(text),
            "total": next(
                (
                    clean_value(m)
                    for p in [r"(?:total|importe|suma|a pagar)[^\d]{0,12}([\d\.,]+\s*€?)"]
                    for match in re.findall(p, text_lower)
                    for m in [match]
                ),
                None,
            ),
        }

    if label == "Documento Identidad":
        return {
            "dni": extract_dni_nif(text),
            "fecha_nacimiento": next(
                (
                    clean_value(m)
                    for p in [r"(?:nacimiento|birth)[^\d]{0,12}(\d{2}[/-]\d{2}[/-]\d{4})"]
                    for match in re.findall(p, text, flags=re.IGNORECASE)
                    for m in [match]
                ),
                None,
            ),
            "fecha_caducidad": next(
                (
                    clean_value(m)
                    for p in [r"(?:caducidad|expiry|expiration|validez)[^\d]{0,12}(\d{2}[/-]\d{2}[/-]\d{4})"]
                    for match in re.findall(p, text, flags=re.IGNORECASE)
                    for m in [match]
                ),
                None,
            ),
        }

    return {"fecha": extract_date(text)}

FIELD_SCHEMAS = {
    "Factura": {
        "fecha": {
            "aliases": ["fecha factura", "fecha", "invoice date", "date"],
            "validator": extract_date,
        },
        "total": {
            "aliases": ["importe total", "total a pagar", "total", "amount due"],
            "validator": extract_amount,
        },
        "dni_nif": {
            "aliases": ["nif", "cif", "vat", "tax id", "dni"],
            "validator": extract_dni_nif,
        },
        "numero_factura": {
            "aliases": ["numero factura", "número factura", "invoice number", "invoice no"],
            "validator": extract_invoice_number,
        },
        "proveedor": {
            "aliases": ["proveedor", "emisor", "supplier", "vendor"],
            "validator": lambda v: clean_value(v) if len(clean_value(v)) <= 80 else None,
        },
        "cliente": {
            "aliases": ["cliente", "customer", "bill to"],
            "validator": lambda v: clean_value(v) if len(clean_value(v)) <= 80 else None,
        },
    },
    "Ticket": {
        "fecha": {
            "aliases": ["fecha", "date"],
            "validator": extract_date,
        },
        "total": {
            "aliases": ["total", "importe", "suma", "a pagar"],
            "validator": extract_amount,
        },
        "comercio": {
            "aliases": ["comercio", "tienda", "merchant", "store"],
            "validator": lambda v: clean_value(v) if len(clean_value(v)) <= 80 else None,
        },
    },
    "Documento Identidad": {
        "dni": {
            "aliases": ["dni", "nie", "documento nacional de identidad", "id number", "numero documento"],
            "validator": extract_dni_nif,
        },
        "nombre": {
            "aliases": ["nombre", "name", "given name"],
            "validator": validate_name,
        },
        "apellidos": {
            "aliases": ["apellidos", "surname", "last name"],
            "validator": validate_name,
        },
        "fecha_nacimiento": {
            "aliases": ["fecha de nacimiento", "nacimiento", "birth date"],
            "validator": extract_date,
        },
        "fecha_caducidad": {
            "aliases": ["fecha de caducidad", "caducidad", "expiry", "expiration"],
            "validator": extract_date,
        },
    },
    "Documento General": {
        "fecha": {
            "aliases": ["fecha", "date"],
            "validator": extract_date,
        }
    },
}

@app.post("/process")
async def process(payload: ExtractionRequest):
    try:
        text = payload.text.strip()
        label = payload.label.strip() or "Documento General"

        if not text:
            raise HTTPException(status_code=400, detail="Texto OCR vacío")

        schema = FIELD_SCHEMAS.get(label, FIELD_SCHEMAS["Documento General"])
        layout_items = flatten_layout(payload.layout)
        layout_lines = group_layout_lines(layout_items)

        fields: dict[str, Any] = {}
        evidence: dict[str, Any] = {}

        for field_name, cfg in schema.items():
            candidate = find_value_near_alias(
                lines=layout_lines,
                aliases=cfg["aliases"],
                validator=cfg.get("validator"),
            )

            if candidate:
                fields[field_name] = candidate["value"]
                evidence[field_name] = candidate
            else:
                fields[field_name] = None

        fallback = regex_fallbacks(text, label)
        for field_name, value in fallback.items():
            if value and not fields.get(field_name):
                fields[field_name] = value
                evidence[field_name] = {
                    "value": value,
                    "score": 0.55,
                    "source": "regex_fallback",
                    "matched_alias": None,
                    "line_index": None,
                }

        return {
            "label": label,
            "fields": fields,
            "evidence": evidence,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extrayendo campos: {str(e)}")