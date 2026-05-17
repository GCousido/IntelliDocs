from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

documents_db = []

OCR_URL = "http://ocr-service:8001/process"
LAYOUT_URL = "http://layout-service:8002/process"
CLASSIFICATION_URL = "http://classification-service:8003/process"
EXTRACTION_URL = "http://extraction-service:8004/process"

DEFAULT_TIMEOUT = httpx.Timeout(
    connect=10.0,
    read=120.0,
    write=120.0,
    pool=10.0,
)

async def post_file(
    client: httpx.AsyncClient,
    url: str,
    filename: str,
    content: bytes,
    content_type: str | None,
):
    files = {
        "file": (
            filename,
            content,
            content_type or "application/octet-stream",
        )
    }
    response = await client.post(url, files=files)
    response.raise_for_status()
    return response.json()

async def post_json(
    client: httpx.AsyncClient,
    url: str,
    payload: dict,
):
    response = await client.post(url, json=payload)
    response.raise_for_status()
    return response.json()

@app.get("/documents")
async def get_documents():
    return {"items": documents_db}

@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo no válido")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            ocr_task = post_file(
                client,
                OCR_URL,
                file.filename,
                content,
                file.content_type,
            )
            layout_task = post_file(
                client,
                LAYOUT_URL,
                file.filename,
                content,
                file.content_type,
            )

            ocr_res, layout_res = await asyncio.gather(ocr_task, layout_task)

            ocr_text = (ocr_res.get("text") or "").strip()
            if not ocr_text or ocr_text == "Sin texto detectado":
                raise HTTPException(
                    status_code=422,
                    detail="El OCR no devolvió texto útil para clasificar",
                )

            class_res = await post_json(
                client,
                CLASSIFICATION_URL,
                {"text": ocr_text},
            )

            ext_res = await post_json(
                client,
                EXTRACTION_URL,
                {
                    "text": ocr_text,
                    "label": class_res.get("label", "Documento General"),
                    "layout": layout_res,
                },
            )

        doc = {
            "id": f"doc-{len(documents_db) + 1}",
            "filename": file.filename,
            "status": "completado",
            "content_type": file.content_type or "application/octet-stream",
            "storage_path": f"minio://uploads/{file.filename}",
            "ocr": ocr_res,
            "layout": layout_res,
            "classification": class_res,
            "extraction": ext_res,
            "pipeline": {
                "steps": [
                    {"name": "ocr", "status": "completado"},
                    {"name": "layout", "status": "completado"},
                    {"name": "classification_from_ocr", "status": "completado"},
                    {"name": "extraction_from_ocr_label_layout", "status": "completado"},
                ],
                "status": "completado",
            },
        }

        documents_db.insert(0, doc)

        return {
            "message": "OK",
            "document": doc,
        }

    except httpx.HTTPStatusError as e:
        detail = e.response.text if e.response is not None else str(e)
        raise HTTPException(
            status_code=502,
            detail=f"Error HTTP en servicios internos: {detail}"
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Timeout en servicios internos"
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error llamando a servicios internos: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error general en pipeline: {str(e)}"
        )