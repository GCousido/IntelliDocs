from fastapi import FastAPI, UploadFile, File
import pytesseract
from PIL import Image
import io
from pdf2image import convert_from_bytes

app = FastAPI()


@app.post("/process")
async def process(file: UploadFile = File(...)):
    content = await file.read()
    layout_data = []
    try:
        if file.filename.lower().endswith(".pdf"):
            images = convert_from_bytes(content)
            img = images[0]
        else:
            img = Image.open(io.BytesIO(content))

        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        for i in range(len(data["level"])):
            if data["text"][i].strip():
                layout_data.append(
                    {
                        "type": "word",
                        "box": [
                            data["left"][i],
                            data["top"][i],
                            data["width"][i],
                            data["height"][i],
                        ],
                        "text": data["text"][i],
                    }
                )
    except Exception:
        pass
    return {"layout": layout_data[:20]}
