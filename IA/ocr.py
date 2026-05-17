from fastapi import FastAPI, UploadFile, File, HTTPException
from PIL import Image, ImageOps, ImageFilter
from pdf2image import convert_from_bytes
import pytesseract
import io

app = FastAPI()

TESS_LANG = "spa+eng"
PDF_DPI = 300
TESS_TIMEOUT = 40
GLOBAL_PSM_CANDIDATES = [3, 4, 6, 11]
ROI_PSM_CANDIDATES = [4, 6, 11]

def load_pages(filename: str, content: bytes) -> list[Image.Image]:
    if filename.lower().endswith(".pdf"):
        return convert_from_bytes(
            content,
            dpi=PDF_DPI,
            thread_count=2,
            timeout=120,
            grayscale=False,
        )
    return [Image.open(io.BytesIO(content))]

def add_white_border(img: Image.Image, border: int = 20) -> Image.Image:
    w, h = img.size
    out = Image.new("L", (w + border * 2, h + border * 2), 255)
    out.paste(img, (border, border))
    return out

def upscale_if_needed(img: Image.Image) -> Image.Image:
    w, h = img.size
    if max(w, h) < 2200:
        img = img.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
    return img

def rotate_by_osd(img: Image.Image) -> Image.Image:
    try:
        osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
        rotate = int(osd.get("rotate", 0))
        if rotate != 0:
            img = img.rotate(-rotate, expand=True)
    except Exception:
        pass
    return img

def preprocess_variants(img: Image.Image) -> list[tuple[str, Image.Image]]:
    img = ImageOps.exif_transpose(img)
    img = upscale_if_needed(img)

    gray = ImageOps.autocontrast(img.convert("L"))
    gray = rotate_by_osd(gray)
    gray = add_white_border(gray, 20)

    binary_165 = gray.point(lambda p: 255 if p > 165 else 0)
    binary_180 = gray.point(lambda p: 255 if p > 180 else 0)
    sharpen = gray.filter(ImageFilter.SHARPEN)

    return [
        ("gray", gray),
        ("binary_165", binary_165),
        ("binary_180", binary_180),
        ("sharpen", sharpen),
    ]

def clean_text(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    compact = []
    prev_blank = False

    for line in lines:
        if line.strip():
            compact.append(line)
            prev_blank = False
        else:
            if not prev_blank:
                compact.append("")
            prev_blank = True

    return "\n".join(compact).strip()

def extract_text(img: Image.Image, psm: int) -> tuple[str, float]:
    config = f"--oem 3 --psm {psm} -c preserve_interword_spaces=1"

    text = pytesseract.image_to_string(
        img,
        lang=TESS_LANG,
        config=config,
        timeout=TESS_TIMEOUT,
    )
    text = clean_text(text)

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

def choose_best_text(img: Image.Image, psm_candidates: list[int]) -> tuple[str, float, dict]:
    best_text = ""
    best_conf = -1.0
    best_meta = {"variant": None, "psm": None}

    for variant_name, variant_img in preprocess_variants(img):
        for psm in psm_candidates:
            text, avg_conf = extract_text(variant_img, psm)

            text_bonus = min(len(text) / 400.0, 8.0)
            line_bonus = min(len([x for x in text.splitlines() if x.strip()]) / 30.0, 4.0)
            score = avg_conf + text_bonus + line_bonus

            current_best_score = (
                best_conf
                + min(len(best_text) / 400.0, 8.0)
                + min(len([x for x in best_text.splitlines() if x.strip()]) / 30.0, 4.0)
            )

            if score > current_best_score:
                best_text = text
                best_conf = avg_conf
                best_meta = {"variant": variant_name, "psm": psm}

    return best_text, best_conf, best_meta

def detect_text_blocks(img: Image.Image) -> list[dict]:
    gray = ImageOps.autocontrast(ImageOps.exif_transpose(img).convert("L"))
    gray = add_white_border(gray, 20)

    data = pytesseract.image_to_data(
        gray,
        lang=TESS_LANG,
        config="--oem 3 --psm 4",
        output_type=pytesseract.Output.DICT,
        timeout=TESS_TIMEOUT,
    )

    blocks = {}
    n = len(data["text"])

    for i in range(n):
        text = (data["text"][i] or "").strip()
        conf_raw = data["conf"][i]

        try:
            conf = float(conf_raw)
        except Exception:
            conf = -1.0

        if not text or conf < 20:
            continue

        block_num = int(data["block_num"][i])
        left = int(data["left"][i])
        top = int(data["top"][i])
        width = int(data["width"][i])
        height = int(data["height"][i])

        if width < 8 or height < 8:
            continue

        if block_num not in blocks:
            blocks[block_num] = {
                "left": left,
                "top": top,
                "right": left + width,
                "bottom": top + height,
            }
        else:
            blocks[block_num]["left"] = min(blocks[block_num]["left"], left)
            blocks[block_num]["top"] = min(blocks[block_num]["top"], top)
            blocks[block_num]["right"] = max(blocks[block_num]["right"], left + width)
            blocks[block_num]["bottom"] = max(blocks[block_num]["bottom"], top + height)

    result = []
    for block_num, b in blocks.items():
        w = b["right"] - b["left"]
        h = b["bottom"] - b["top"]

        if w < 40 or h < 15:
            continue

        result.append({
            "block_num": block_num,
            "left": max(0, b["left"] - 10),
            "top": max(0, b["top"] - 8),
            "right": b["right"] + 10,
            "bottom": b["bottom"] + 8,
        })

    result.sort(key=lambda x: (x["top"], x["left"]))
    return result

def ocr_blocks(img: Image.Image) -> list[dict]:
    blocks = detect_text_blocks(img)
    out = []

    for b in blocks:
        roi = img.crop((b["left"], b["top"], b["right"], b["bottom"]))
        text, conf, meta = choose_best_text(roi, ROI_PSM_CANDIDATES)

        if text.strip():
            out.append({
                "block_num": b["block_num"],
                "box": {
                    "left": b["left"],
                    "top": b["top"],
                    "width": b["right"] - b["left"],
                    "height": b["bottom"] - b["top"],
                },
                "variant_used": meta["variant"],
                "psm_used": meta["psm"],
                "confidence": conf,
                "text": text,
            })

    return out

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
            global_text, global_conf, global_meta = choose_best_text(raw_img, GLOBAL_PSM_CANDIDATES)
            region_results = ocr_blocks(raw_img)

            region_text = "\n\n".join(r["text"] for r in region_results if r["text"].strip()).strip()

            final_text = region_text if len(region_text) > len(global_text) * 0.7 else global_text
            final_conf = global_conf

            if final_text:
                full_text_parts.append(final_text)
            if final_conf > 0:
                page_confidences.append(final_conf)

            result_pages.append(
                {
                    "page": page_index,
                    "variant_used": global_meta["variant"],
                    "psm_used": global_meta["psm"],
                    "confidence": final_conf if final_conf > 0 else None,
                    "text": final_text,
                    "regions": region_results,
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