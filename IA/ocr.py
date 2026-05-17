from fastapi import FastAPI, UploadFile, File, HTTPException
from PIL import Image, ImageOps
from pdf2image import convert_from_bytes
import pytesseract
import io

app = FastAPI()

TESS_LANG = "spa+eng"
PDF_DPI = 250
TESS_TIMEOUT = 30
PSM_CANDIDATES = [4, 6, 11]

def preprocess_image(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    img = img.convert("L")
    img = ImageOps.autocontrast(img)
    img = img.point(lambda p: 255 if p > 180 else 0)

    w, h = img.size
    if max(w, h) < 1800:
        img = img.resize((w * 2, h * 2))

    return img

def load_pages(filename: str, content: bytes) -> list[Image.Image]:
    if filename.lower().endswith(".pdf"):
        return convert_from_bytes(
            content,
            dpi=PDF_DPI,
            thread_count=2,
            timeout=120,
            grayscale=True,
        )
    return [Image.open(io.BytesIO(content))]

def extract_text(img: Image.Image, psm: int) -> tuple[str, float]:
    config = f"--oem 3 --psm {psm} -c preserve_interword_spaces=1"

    text = pytesseract.image_to_string(
        img,
        lang=TESS_LANG,
        config=config,
        timeout=TESS_TIMEOUT,
    ).strip()

    data = pytesseract.image_to_data(
        img,
        lang=TESS_LANG,
        config=config,
        output_type=pytesseract.Output.DICT,
        timeout=TESS_TIMEOUT,
    )

    confidences = []
    for conf_raw in data["conf"]:
        try:
            conf = float(conf_raw)
        except Exception:
            conf = -1.0
        if conf >= 0:
            confidences.append(conf)

    avg_conf = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    return text, avg_conf

def choose_best_ocr(img: Image.Image) -> tuple[str, float, int]:
    best_text = ""
    best_conf = -1.0
    best_psm = PSM_CANDIDATES[0]

    for psm in PSM_CANDIDATES:
        text, avg_conf = extract_text(img, psm)
        score = avg_conf + min(len(text) / 500.0, 5.0)
        current_best_score = best_conf + min(len(best_text) / 500.0, 5.0)

        if score > current_best_score:
            best_text = text
            best_conf = avg_conf
            best_psm = psm

    return best_text, best_conf, best_psm

@app.post("/process")
async def process(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo no válido")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    try:
        raw_pages = load_pages(file.filename, content)

        result_pages = []
        full_text_parts = []
        page_confidences = []

        for page_index, raw_img in enumerate(raw_pages, start=1):
            img = preprocess_image(raw_img)
            page_text, page_conf, used_psm = choose_best_ocr(img)

            if page_text:
                full_text_parts.append(page_text)
            if page_conf > 0:
                page_confidences.append(page_conf)

            result_pages.append(
                {
                    "page": page_index,
                    "psm_used": used_psm,
                    "confidence": page_conf if page_conf > 0 else None,
                    "text": page_text,
                }
            )

        avg_conf = (
            round(sum(page_confidences) / len(page_confidences), 2)
            if page_confidences
            else None
        )

        full_text = "\n\n".join(part for part in full_text_parts if part).strip()

        return {
            "text": full_text if full_text else "Sin texto detectado",
            "language": TESS_LANG,
            "pages": result_pages,
            "confidence": avg_conf,
            "page_count": len(result_pages),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando OCR: {str(e)}")