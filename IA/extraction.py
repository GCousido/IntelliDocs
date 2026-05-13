from fastapi import FastAPI, UploadFile, File
import pytesseract
from PIL import Image
import io
from pdf2image import convert_from_bytes
import re

app = FastAPI()


@app.post("/process")
async def process(file: UploadFile = File(...)):
    content = await file.read()
    text = ""
    try:
        if file.filename.lower().endswith(".pdf"):
            images = convert_from_bytes(content)
            img = images[0]
            text = pytesseract.image_to_string(img)
        else:
            image = Image.open(io.BytesIO(content))
            text = pytesseract.image_to_string(image)
    except Exception:
        pass

    fechas = re.findall(r"\d{2}[/-]\d{2}[/-]\d{4}", text)
    totales = re.findall(r"(?:total importe|suma)[\s\:\$€]*([\d\.\,]+)", text.lower())

    return {
        "fecha": fechas[0] if fechas else None,
        "total": totales[0] if totales else None,
    }
