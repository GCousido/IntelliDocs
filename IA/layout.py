from fastapi import FastAPI, UploadFile, File, HTTPException
from PIL import Image, ImageOps
from pdf2image import convert_from_bytes
import pytesseract
import io

app = FastAPI()

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
            dpi=250,
            first_page=1,
            last_page=3,
            thread_count=2,
            grayscale=True,
        )
    return [Image.open(io.BytesIO(content))]

@app.post("/process")
async def process(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo no válido")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    try:
        pages = load_pages(file.filename, content)
        layout_pages = []

        for page_index, raw_img in enumerate(pages, start=1):
            img = preprocess_image(raw_img)

            data = pytesseract.image_to_data(
                img,
                lang="spa+eng",
                config="--oem 3 --psm 4",
                output_type=pytesseract.Output.DICT,
            )

            words = []
            line_groups = {}
            block_groups = {}

            n = len(data["level"])
            for i in range(n):
                text = (data["text"][i] or "").strip()
                conf_raw = data["conf"][i]

                try:
                    conf = float(conf_raw)
                except Exception:
                    conf = -1

                item = {
                    "page": page_index,
                    "block_num": int(data["block_num"][i]),
                    "par_num": int(data["par_num"][i]),
                    "line_num": int(data["line_num"][i]),
                    "word_num": int(data["word_num"][i]),
                    "box": {
                        "left": int(data["left"][i]),
                        "top": int(data["top"][i]),
                        "width": int(data["width"][i]),
                        "height": int(data["height"][i]),
                    },
                }

                if text:
                    words.append({
                        "type": "word",
                        "text": text,
                        "confidence": conf if conf >= 0 else None,
                        **item,
                    })

                    line_key = (item["block_num"], item["par_num"], item["line_num"])
                    block_key = item["block_num"]

                    line_groups.setdefault(line_key, []).append({
                        "text": text,
                        **item,
                    })
                    block_groups.setdefault(block_key, []).append({
                        "text": text,
                        **item,
                    })

            lines = []
            for (block_num, par_num, line_num), group in line_groups.items():
                group = sorted(group, key=lambda x: x["box"]["left"])
                left = min(x["box"]["left"] for x in group)
                top = min(x["box"]["top"] for x in group)
                right = max(x["box"]["left"] + x["box"]["width"] for x in group)
                bottom = max(x["box"]["top"] + x["box"]["height"] for x in group)

                lines.append({
                    "type": "line",
                    "page": page_index,
                    "block_num": block_num,
                    "par_num": par_num,
                    "line_num": line_num,
                    "text": " ".join(x["text"] for x in group),
                    "box": {
                        "left": left,
                        "top": top,
                        "width": right - left,
                        "height": bottom - top,
                    },
                })

            blocks = []
            for block_num, group in block_groups.items():
                group = sorted(group, key=lambda x: (x["box"]["top"], x["box"]["left"]))
                left = min(x["box"]["left"] for x in group)
                top = min(x["box"]["top"] for x in group)
                right = max(x["box"]["left"] + x["box"]["width"] for x in group)
                bottom = max(x["box"]["top"] + x["box"]["height"] for x in group)

                blocks.append({
                    "type": "block",
                    "page": page_index,
                    "block_num": block_num,
                    "text": " ".join(x["text"] for x in group),
                    "box": {
                        "left": left,
                        "top": top,
                        "width": right - left,
                        "height": bottom - top,
                    },
                })

            layout_pages.append({
                "page": page_index,
                "words": words,
                "lines": lines,
                "blocks": blocks,
            })

        return {
            "layout": layout_pages,
            "page_count": len(layout_pages),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando layout: {str(e)}")