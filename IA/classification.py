import re
import unicodedata
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


app = FastAPI()


CANDIDATE_LABELS = [
    "Factura",
    "Ticket",
    "Documento Identidad",
    "Documento General",
]


class ClassificationRequest(BaseModel):
    text: str


def normalize_text(value: str) -> str:
    value = value.strip().lower()
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = re.sub(r"\s+", " ", value)
    return value


def has_any(text: str, patterns: list[str]) -> int:
    score = 0
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            score += 1
    return score


def classify_document(text: str) -> dict:
    t = normalize_text(text)

    scores = {
        "Factura": 0,
        "Ticket": 0,
        "Documento Identidad": 0,
        "Documento General": 0,
    }

    factura_patterns = [
        r"\bfactura\b",
        r"\binvoice\b",
        r"\bfactura simplificada\b",
        r"\bbase imponible\b",
        r"\biva\b",
        r"\bcif\b",
        r"\bnif\b",
        r"\btotal a pagar\b",
        r"\bnumero factura\b",
        r"\binvoice number\b",
        r"\bemisor\b",
        r"\bproveedor\b",
    ]

    ticket_patterns = [
        r"\bticket\b",
        r"\brecibo\b",
        r"\breceipt\b",
        r"\bcomercio\b",
        r"\btienda\b",
        r"\bcambio\b",
        r"\bcaja\b",
        r"\btpv\b",
        r"\barticulos?\b",
        r"\bunidades?\b",
        r"\ba pagar\b",
    ]

    identidad_patterns = [
        r"\bdni\b",
        r"\bnie\b",
        r"\bpasaporte\b",
        r"\bpassport\b",
        r"\bdocumento nacional de identidad\b",
        r"\bidentidad\b",
        r"\bfecha de nacimiento\b",
        r"\bfecha de caducidad\b",
        r"\bnacionalidad\b",
        r"\bsexo\b",
        r"\bapellidos\b",
        r"\bnombre\b",
        r"\b[xyz]\d{7}[a-z]\b",
        r"\b\d{8}[a-z]\b",
    ]

    scores["Factura"] += has_any(t, factura_patterns) * 1.2
    scores["Ticket"] += has_any(t, ticket_patterns) * 1.1
    scores["Documento Identidad"] += has_any(t, identidad_patterns) * 1.4

    if re.search(r"\b(total|importe total|amount due)\b", t) and re.search(r"\b(iva|cif|nif|factura|invoice)\b", t):
        scores["Factura"] += 2.0

    if re.search(r"\b(total|importe|suma|a pagar)\b", t) and re.search(r"\b(ticket|recibo|receipt|cambio|tpv)\b", t):
        scores["Ticket"] += 2.0

    if re.search(r"\b\d{8}[a-z]\b", t, flags=re.IGNORECASE):
        scores["Documento Identidad"] += 2.5

    if re.search(r"\b[xyz]\d{7}[a-z]\b", t, flags=re.IGNORECASE):
        scores["Documento Identidad"] += 2.5

    if max(scores.values()) == 0:
        scores["Documento General"] = 1.0

    best_label, best_score = max(scores.items(), key=lambda x: x[1])

    total_score = sum(max(v, 0) for v in scores.values()) or 1.0
    confidence = round(best_score / total_score, 2)

    if best_score < 1.5:
        best_label = "Documento General"
        confidence = 0.6

    return {
        "label": best_label,
        "confidence": confidence,
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "mode": "rule-based",
        "labels": CANDIDATE_LABELS,
    }


@app.post("/process")
async def process(payload: ClassificationRequest):
    text = payload.text.strip()

    if not text:
        raise HTTPException(status_code=400, detail="Texto OCR vacío")

    try:
        return classify_document(text[:8000])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error clasificando documento: {str(e)}"
        )