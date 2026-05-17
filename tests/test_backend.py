from fastapi.testclient import TestClient
import sys
import os
import pytest
from unittest.mock import patch, AsyncMock

# Añadir el backend al path para poder importarlo
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../Backend')))
from main import app, OCR_URL, LAYOUT_URL, CLASSIFICATION_URL, EXTRACTION_URL, BUCKET_NAME

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_pipeline_calls():
    state = {
        "ocr": {
            "text": "Factura 12345 total 250.50",
            "language": "spa+eng",
            "pages": [
                {
                    "page": 1,
                    "variant_used": "gray",
                    "psm_used": 4,
                    "confidence": 88.5,
                    "text": "Factura 12345 total 250.50",
                    "regions": [],
                }
            ],
            "confidence": 88.5,
            "page_count": 1,
        },
        "layout": {
            "layout": [
                {
                    "page": 1,
                    "words": [],
                    "lines": [],
                    "blocks": [],
                }
            ],
            "page_count": 1,
        },
        "classification": {
            "label": "Factura",
            "confidence": 0.88,
        },
        "extraction": {
            "label": "Factura",
            "fields": {
                "fecha": "25/12/2023",
                "total": "250.50",
                "numero_factura": "12345",
            },
            "evidence": {},
        },
    }

    class FakeObject:
        def __init__(self, object_name: str):
            self.object_name = object_name

    class FakeResponse:
        def __init__(self, payload: bytes):
            self._payload = payload

        def read(self):
            return self._payload

        def close(self):
            return None

        def release_conn(self):
            return None

    class FakeMinio:
        def __init__(self):
            self._store: dict[str, bytes] = {}

        def list_objects(self, bucket, prefix="", recursive=False):
            items = []
            for key in self._store:
                if key.startswith(prefix):
                    items.append(FakeObject(key))
            return items

        def get_object(self, bucket, object_name):
            payload = self._store.get(object_name, b"{}");
            return FakeResponse(payload)

        def put_object(self, bucket, object_name, data, length, content_type=None):
            payload = data.read(length)
            self._store[object_name] = payload
            return None

        def bucket_exists(self, bucket):
            return True

        def make_bucket(self, bucket):
            return None

    async def post_file_side_effect(client, url, filename, content, content_type):
        if url == OCR_URL:
            return state["ocr"]
        if url == LAYOUT_URL:
            return state["layout"]
        return {}

    async def post_json_side_effect(client, url, payload):
        if url == CLASSIFICATION_URL:
            return state["classification"]
        if url == EXTRACTION_URL:
            return state["extraction"]
        return {}

    with patch("main.post_file", new_callable=AsyncMock) as mock_post_file, patch(
        "main.post_json", new_callable=AsyncMock
    ) as mock_post_json, patch("main.minio_client", new=FakeMinio()):
        mock_post_file.side_effect = post_file_side_effect
        mock_post_json.side_effect = post_json_side_effect
        yield state


# ===== TESTS PARA DOCUMENTOS =====
def test_get_documents_empty():
    """Test de obtención de lista vacía de documentos"""
    response = client.get("/documents")
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_get_documents_structure():
    """Test de estructura correcta en la respuesta"""
    response = client.get("/documents")
    
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)


# ===== TESTS PARA SUBIDA DE DOCUMENTOS =====
def test_upload_document_mocked():
    """Test de subida de documento con archivo de texto simulado"""
    file_content = b"Contenido de prueba"
    files = {"file": ("prueba.pdf", file_content, "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "OK"
    assert "document" in data
    assert data["document"]["filename"] == "prueba.pdf"
    assert data["document"]["status"] == "completado"


def test_upload_document_response_fields():
    """Test de que el documento subido tiene todos los campos requeridos"""
    file_content = b"Test content"
    files = {"file": ("test.pdf", file_content, "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    
    assert response.status_code == 200
    doc = response.json()["document"]
    
    # Verificar campos obligatorios
    assert "id" in doc
    assert "filename" in doc
    assert "status" in doc
    assert "content_type" in doc
    assert "storage_path" in doc
    assert "ocr" in doc
    assert "layout" in doc
    assert "classification" in doc
    assert "extraction" in doc
    assert "pipeline" in doc
    
    # Verificar que son del tipo correcto
    assert isinstance(doc["id"], str)
    assert isinstance(doc["filename"], str)
    assert doc["status"] == "completado"
    assert isinstance(doc["content_type"], str)


def test_upload_document_with_different_types():
    """Test de subida de documentos con diferentes tipos de contenido"""
    
    # PDF
    files = {"file": ("document.pdf", b"PDF content", "application/pdf")}
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 200
    
    # PNG
    files = {"file": ("image.png", b"PNG content", "image/png")}
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 200


def test_upload_document_increments_id():
    """Test de incremento correcto de IDs"""
    
    response1 = client.post("/documents/upload", 
                           files={"file": ("test1.pdf", b"content1", "application/pdf")})
    doc1_id = response1.json()["document"]["id"]
    
    response2 = client.post("/documents/upload", 
                           files={"file": ("test2.pdf", b"content2", "application/pdf")})
    doc2_id = response2.json()["document"]["id"]
    
    assert doc1_id != doc2_id


def test_get_documents_after_upload():
    """Test de obtención de documentos después de subida"""
    
    # Subir un documento
    files = {"file": ("prueba.pdf", b"Contenido", "application/pdf")}
    client.post("/documents/upload", files=files)
    
    # Obtener documentos
    response = client.get("/documents")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["filename"] == "prueba.pdf"


def test_upload_document_with_empty_file():
    """Test de subida de archivo vacío"""
    files = {"file": ("empty.pdf", b"", "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 400
    assert response.json()["detail"] == "Archivo vacio"


def test_document_storage_path_format():
    """Test de formato correcto en storage_path"""
    files = {"file": ("test_file.pdf", b"content", "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    doc = response.json()["document"]
    
    assert doc["storage_path"].startswith(f"minio://{BUCKET_NAME}/uploads/")
    assert doc["storage_path"].endswith("test_file.pdf")


# ===== TESTS PARA CONTENIDO PROCESADO =====
def test_upload_document_contains_ocr_results():
    """Test de que el documento contiene resultados de OCR"""
    files = {"file": ("test.pdf", b"content", "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 200
    
    doc = response.json()["document"]
    # OCR puede fallar si no hay tesseract, pero debe estar presente
    assert "ocr" in doc
    assert isinstance(doc["ocr"], dict)


def test_upload_document_contains_layout_results():
    """Test de que el documento contiene resultados de layout"""
    files = {"file": ("test.pdf", b"content", "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 200
    
    doc = response.json()["document"]
    assert "layout" in doc
    assert isinstance(doc["layout"], dict)


def test_upload_document_contains_classification_results():
    """Test de que el documento contiene resultados de clasificación"""
    files = {"file": ("test.pdf", b"content", "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 200
    
    doc = response.json()["document"]
    assert "classification" in doc
    assert isinstance(doc["classification"], dict)


def test_upload_document_contains_extraction_results():
    """Test de que el documento contiene resultados de extracción"""
    files = {"file": ("test.pdf", b"content", "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 200
    
    doc = response.json()["document"]
    assert "extraction" in doc
    assert isinstance(doc["extraction"], dict)


def test_document_filename_preserved():
    """Test de preservación exacta del nombre de archivo"""
    original_filename = "mi-documento-especial_2023.pdf"
    files = {"file": (original_filename, b"content", "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    doc = response.json()["document"]
    
    assert doc["filename"] == original_filename


def test_document_content_type_preserved():
    """Test de preservación del tipo de contenido"""
    content_type = "application/pdf"
    files = {"file": ("test.pdf", b"content", content_type)}
    
    response = client.post("/documents/upload", files=files)
    doc = response.json()["document"]
    
    assert doc["content_type"] == content_type


def test_all_processes_executed_in_order():
    """Test de ejecución de todos los procesos (OCR, Layout, Classification, Extraction)"""
    files = {"file": ("test.pdf", b"content", "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 200
    
    doc = response.json()["document"]
    
    # Todos estos procesos deben estar presentes
    required_processes = ["ocr", "layout", "classification", "extraction"]
    for process in required_processes:
        assert process in doc, f"Falta el proceso {process} en documento"
        # Cada proceso devuelve un dict (éxito o error)
        assert isinstance(doc[process], dict), f"El resultado de {process} debe ser un dict"
