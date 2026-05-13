from fastapi import FastAPI, UploadFile, File
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


@app.get("/documents")
async def get_documents():
    return {"items": documents_db}


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    content = await file.read()

    async def call_service(url, filename, file_content, content_type):
        async with httpx.AsyncClient() as client:
            try:
                files = {"file": (filename, file_content, content_type)}
                response = await client.post(url, files=files, timeout=120.0)
                return response.json()
            except Exception:
                return {"error": "servicio inalcanzable"}

    ocr_task = call_service(
        "http://ocr-service:8001/process",
        file.filename,
        content,
        file.content_type,
    )
    layout_task = call_service(
        "http://layout-service:8002/process",
        file.filename,
        content,
        file.content_type,
    )
    class_task = call_service(
        "http://classification-service:8003/process",
        file.filename,
        content,
        file.content_type,
    )
    ext_task = call_service(
        "http://extraction-service:8004/process",
        file.filename,
        content,
        file.content_type,
    )

    ocr_res, layout_res, class_res, ext_res = await asyncio.gather(
        ocr_task, layout_task, class_task, ext_task
    )

    doc = {
        "id": f"doc-{len(documents_db) + 1}",
        "filename": file.filename,
        "status": "completado",
        "content_type": file.content_type,
        "storage_path": f"minio://uploads/{file.filename}",
        "ocr": ocr_res,
        "layout": layout_res,
        "classification": class_res,
        "extraction": ext_res,
        "pipeline": {"status": "completado"},
    }
    documents_db.insert(0, doc)
    return {"message": "OK", "document": doc}
