from fastapi.testclient import TestClient
import sys
import os

# Añadir el backend al path para poder importarlo
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))
from main import app, documents_db

client = TestClient(app)

def test_get_documents_empty():
    # Limpiar la base de datos en memoria para el test
    documents_db.clear()
    response = client.get("/documents")
    assert response.status_code == 200
    assert response.json() == {"items": []}

def test_upload_document_mocked():
    # Simulamos la subida de un archivo de texto plano para probar el endpoint
    file_content = b"Contenido de prueba"
    files = {"file": ("prueba.pdf", file_content, "application/pdf")}
    
    response = client.post("/documents/upload", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "OK"
    assert "document" in data
    assert data["document"]["filename"] == "prueba.pdf"
    assert data["document"]["status"] == "completado"
