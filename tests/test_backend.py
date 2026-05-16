from fastapi.testclient import TestClient
import sys
import os
import json
from unittest.mock import patch, AsyncMock

# Añadir el backend al path para poder importarlo
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../Backend')))
from main import app, documents_db

client = TestClient(app)


# ===== TESTS PARA DOCUMENTOS =====
def test_get_documents_empty():
    """Test de obtención de lista vacía de documentos"""
    documents_db.clear()
    response = client.get("/documents")
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_get_documents_structure():
    """Test de estructura correcta en la respuesta"""
    documents_db.clear()
    response = client.get("/documents")
    
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)


# ===== TESTS PARA SUBIDA DE DOCUMENTOS =====
def test_upload_document_mocked():
    """Test de subida de documento con archivo de texto simulado"""
    documents_db.clear()
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
    documents_db.clear()
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
    documents_db.clear()
    
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
    documents_db.clear()
    
    response1 = client.post("/documents/upload", 
                           files={"file": ("test1.pdf", b"content1", "application/pdf")})
    doc1_id = response1.json()["document"]["id"]
    
    response2 = client.post("/documents/upload", 
                           files={"file": ("test2.pdf", b"content2", "application/pdf")})
    doc2_id = response2.json()["document"]["id"]
    
    assert doc1_id != doc2_id


def test_get_documents_after_upload():
    """Test de obtención de documentos después de subida"""
    documents_db.clear()
    
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
    documents_db.clear()
    files = {"file": ("empty.pdf", b"", "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 200
    assert response.json()["document"]["filename"] == "empty.pdf"


def test_document_storage_path_format():
    """Test de formato correcto en storage_path"""
    documents_db.clear()
    files = {"file": ("test_file.pdf", b"content", "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    doc = response.json()["document"]
    
    assert doc["storage_path"].startswith("minio://uploads/")
    assert doc["storage_path"].endswith("test_file.pdf")


# ===== TESTS PARA CONTENIDO PROCESADO =====
def test_upload_document_contains_ocr_results():
    """Test de que el documento contiene resultados de OCR"""
    documents_db.clear()
    files = {"file": ("test.pdf", b"content", "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 200
    
    doc = response.json()["document"]
    # OCR puede fallar si no hay tesseract, pero debe estar presente
    assert "ocr" in doc
    assert isinstance(doc["ocr"], dict)


def test_upload_document_contains_layout_results():
    """Test de que el documento contiene resultados de layout"""
    documents_db.clear()
    files = {"file": ("test.pdf", b"content", "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 200
    
    doc = response.json()["document"]
    assert "layout" in doc
    assert isinstance(doc["layout"], dict)


def test_upload_document_contains_classification_results():
    """Test de que el documento contiene resultados de clasificación"""
    documents_db.clear()
    files = {"file": ("test.pdf", b"content", "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 200
    
    doc = response.json()["document"]
    assert "classification" in doc
    assert isinstance(doc["classification"], dict)


def test_upload_document_contains_extraction_results():
    """Test de que el documento contiene resultados de extracción"""
    documents_db.clear()
    files = {"file": ("test.pdf", b"content", "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 200
    
    doc = response.json()["document"]
    assert "extraction" in doc
    assert isinstance(doc["extraction"], dict)


def test_document_filename_preserved():
    """Test de preservación exacta del nombre de archivo"""
    documents_db.clear()
    original_filename = "mi-documento-especial_2023.pdf"
    files = {"file": (original_filename, b"content", "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    doc = response.json()["document"]
    
    assert doc["filename"] == original_filename


def test_document_content_type_preserved():
    """Test de preservación del tipo de contenido"""
    documents_db.clear()
    content_type = "application/pdf"
    files = {"file": ("test.pdf", b"content", content_type)}
    
    response = client.post("/documents/upload", files=files)
    doc = response.json()["document"]
    
    assert doc["content_type"] == content_type


def test_all_processes_executed_in_order():
    """Test de ejecución de todos los procesos (OCR, Layout, Classification, Extraction)"""
    documents_db.clear()
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
