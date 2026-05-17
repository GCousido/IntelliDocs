from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
import os
import json
import io
from minio import Minio

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio-service:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "password123")
BUCKET_NAME = "documentos"

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

try:
    if not minio_client.bucket_exists(BUCKET_NAME):
        minio_client.make_bucket(BUCKET_NAME)
except Exception:
    pass

OCR_URL = "http://ocr-service:8001/process"
LAYOUT_URL = "http://layout-service:8002/process"
CLASSIFICATION_URL = "http://classification-service:8003/process"
EXTRACTION_URL = "http://extraction-service:8004/process"

DEFAULT_TIMEOUT = httpx.Timeout(
    connect=30.0,
    read=240.0,
    write=240.0,
    pool=30.0,
)

async def post_file(client: httpx.AsyncClient, url: str, filename: str, content: bytes, content_type: str | None):
    files = {"file": (filename, content, content_type or "application/octet-stream")}
    response = await client.post(url, files=files)
    response.raise_for_status()
    return response.json()

async def post_json(client: httpx.AsyncClient, url: str, payload: dict):
    response = await client.post(url, json=payload)
    response.raise_for_status()
    return response.json()

@app.get("/documents")
async def get_documents():
    documents = []
    try:
        objects = minio_client.list_objects(BUCKET_NAME, prefix="metadata/", recursive=True)
        for obj in objects:
            response = minio_client.get_object(BUCKET_NAME, obj.object_name)
            metadata = json.loads(response.read().decode('utf-8'))
            documents.append(metadata)
            response.close()
            response.release_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error MinIO: {str(e)}")
    return {"items": documents}

@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo no valido")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacio")

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            ocr_task = post_file(client, OCR_URL, file.filename, content, file.content_type)
            layout_task = post_file(client, LAYOUT_URL, file.filename, content, file.content_type)
            ocr_res, layout_res = await asyncio.gather(ocr_task, layout_task)

            ocr_text = (ocr_res.get("text") or "").strip()
            if not ocr_text or ocr_text == "Sin texto detectado":
                raise HTTPException(status_code=422, detail="El OCR no devolvio texto util para clasificar")

            class_res = await post_json(client, CLASSIFICATION_URL, {"text": ocr_text})
            ext_res = await post_json(client, EXTRACTION_URL, {
                "text": ocr_text,
                "label": class_res.get("label", "Documento General"),
                "layout": layout_res,
            })

        doc = {
            "id": file.filename,
            "filename": file.filename,
            "status": "completado",
            "content_type": file.content_type or "application/octet-stream",
            "storage_path": f"minio://{BUCKET_NAME}/uploads/{file.filename}",
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

        file_stream = io.BytesIO(content)
        minio_client.put_object(
            BUCKET_NAME,
            f"uploads/{file.filename}",
            file_stream,
            length=len(content),
            content_type=file.content_type or "application/octet-stream"
        )

        doc_json = json.dumps(doc).encode('utf-8')
        json_stream = io.BytesIO(doc_json)
        minio_client.put_object(
            BUCKET_NAME,
            f"metadata/{file.filename}.json",
            json_stream,
            length=len(doc_json),
            content_type="application/json"
        )

        return {"message": "OK", "document": doc}

    except httpx.HTTPStatusError as e:
        detail = e.response.text if e.response is not None else str(e)
        raise HTTPException(status_code=502, detail=f"Error HTTP interno: {detail}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout en servicios internos")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Error de red interno: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error general: {str(e)}")
