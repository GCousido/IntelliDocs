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
            img = images[0]
            text = pytesseract.image_to_string(img, lang="spa+eng")
        else:
            image = Image.open(io.BytesIO(content))
            text = pytesseract.image_to_string(image, lang="spa+eng")
    except Exception:
        text = "Error procesando documento"

    return {"text": text.strip() if text else "Sin texto detectado"}
