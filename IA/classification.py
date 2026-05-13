from fastapi import FastAPI, UploadFile, File
import pytesseract
from PIL import Image
import io
from pdf2image import convert_from_bytes

app = FastAPI()


@app.post("/process")
async def process(file: UploadFile = File(...)):
    content = await file.read()
    text = ""
    try:
        if file.filename.lower().endswith(".pdf"):
            images = convert_from_bytes(content)
            text = pytesseract.image_to_string(images[0]).lower()
        else:
            image = Image.open(io.BytesIO(content))
            text = pytesseract.image_to_string(image).lower()
    except Exception:
        pass

    if "factura" in text or "invoice" in text:
        return {"label": "Factura", "confidence": 0.95}
    elif "ticket" in text or "recibo" in text:
        return {"label": "Ticket", "confidence": 0.88}
    elif "dni" in text or "identidad" in text:
        return {"label": "Documento Identidad", "confidence": 0.90}
    else:
        return {"label": "Documento General", "confidence": 0.60}
