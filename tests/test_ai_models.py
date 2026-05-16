from fastapi.testclient import TestClient
import sys
import os
import io
from PIL import Image
from unittest.mock import patch, MagicMock
import re

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../IA')))
from classification import app as class_app
from extraction import app as ext_app
from layout import app as layout_app
from ocr import app as ocr_app

# Clientes para cada servicio
class_client = TestClient(class_app)
ext_client = TestClient(ext_app)
layout_client = TestClient(layout_app)
ocr_client = TestClient(ocr_app)


def create_test_image():
    """Crea una imagen de prueba simple"""
    img = Image.new('RGB', (200, 100), color='white')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes.getvalue()


# ===== TESTS PARA CLASSIFICATION =====
@patch('classification.pytesseract.image_to_string')
@patch('classification.convert_from_bytes')
def test_classification_invoice(mock_pdf, mock_ocr):
    """Test de clasificación correcta de una factura"""
    # Mock de la imagen
    from PIL import Image as PILImage
    img = PILImage.new('RGB', (100, 100))
    mock_pdf.return_value = [img]
    mock_ocr.return_value = "Factura numero 12345 con total 100 euros"
    
    files = {"file": ("test.pdf", b"fake pdf", "application/pdf")}
    response = class_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Factura"
    assert data["confidence"] == 0.95


@patch('classification.pytesseract.image_to_string')
@patch('classification.convert_from_bytes')
def test_classification_ticket(mock_pdf, mock_ocr):
    """Test de clasificación correcta de un ticket"""
    from PIL import Image as PILImage
    img = PILImage.new('RGB', (100, 100))
    mock_pdf.return_value = [img]
    mock_ocr.return_value = "Ticket de compra con recibo numero 999"
    
    files = {"file": ("test.pdf", b"fake pdf", "application/pdf")}
    response = class_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Ticket"
    assert data["confidence"] > 0.8


@patch('classification.pytesseract.image_to_string')
@patch('classification.convert_from_bytes')
def test_classification_dni_document(mock_pdf, mock_ocr):
    """Test de clasificación correcta de documento de identidad"""
    from PIL import Image as PILImage
    img = PILImage.new('RGB', (100, 100))
    mock_pdf.return_value = [img]
    mock_ocr.return_value = "DNI Documento de Identidad Nacional"
    
    files = {"file": ("test.pdf", b"fake pdf", "application/pdf")}
    response = class_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Documento Identidad"
    assert data["confidence"] > 0.8


def test_classification_generic_document():
    """Test de clasificación genérica sin palabras clave"""
    file_content = b"Contenido sin palabra clave especifica"
    files = {"file": ("test.txt", file_content, "text/plain")}
    response = class_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Documento General"
    assert data["confidence"] > 0.5


@patch('classification.pytesseract.image_to_string')
@patch('classification.convert_from_bytes')
def test_classification_invoice_keyword_invoice(mock_pdf, mock_ocr):
    """Test de que 'invoice' en inglés se clasifica como factura"""
    from PIL import Image as PILImage
    img = PILImage.new('RGB', (100, 100))
    mock_pdf.return_value = [img]
    mock_ocr.return_value = "This is an invoice document"
    
    files = {"file": ("test.pdf", b"fake", "application/pdf")}
    response = class_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Factura"


# ===== TESTS PARA EXTRACTION =====
@patch('extraction.pytesseract.image_to_string')
@patch('extraction.convert_from_bytes')
def test_extraction_extracts_date_correctly(mock_pdf, mock_ocr):
    """Test de extracción correcta de fecha del documento"""
    from PIL import Image as PILImage
    img = PILImage.new('RGB', (100, 100))
    mock_pdf.return_value = [img]
    mock_ocr.return_value = "Documento fechado el 25/12/2023 con total"
    
    files = {"file": ("test.pdf", b"fake", "application/pdf")}
    response = ext_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["fecha"] == "25/12/2023"


@patch('extraction.pytesseract.image_to_string')
@patch('extraction.convert_from_bytes')
def test_extraction_extracts_multiple_dates_first_one(mock_pdf, mock_ocr):
    """Test de extracción de primera fecha cuando hay varias"""
    from PIL import Image as PILImage
    img = PILImage.new('RGB', (100, 100))
    mock_pdf.return_value = [img]
    mock_ocr.return_value = "Fecha 01/01/2023 y vencimiento 31/12/2023"
    
    files = {"file": ("test.pdf", b"fake", "application/pdf")}
    response = ext_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["fecha"] == "01/01/2023"


@patch('extraction.pytesseract.image_to_string')
@patch('extraction.convert_from_bytes')
def test_extraction_extracts_total_correctly(mock_pdf, mock_ocr):
    """Test de extracción correcta del total"""
    from PIL import Image as PILImage
    img = PILImage.new('RGB', (100, 100))
    mock_pdf.return_value = [img]
    mock_ocr.return_value = "Total importe: 250.50 euros"
    
    files = {"file": ("test.pdf", b"fake", "application/pdf")}
    response = ext_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == "250.50"


@patch('extraction.pytesseract.image_to_string')
@patch('extraction.convert_from_bytes')
def test_extraction_extracts_suma_keyword(mock_pdf, mock_ocr):
    """Test de reconocimiento de 'suma' como palabra clave para total"""
    from PIL import Image as PILImage
    img = PILImage.new('RGB', (100, 100))
    mock_pdf.return_value = [img]
    mock_ocr.return_value = "Suma€150.75 resto"
    
    files = {"file": ("test.pdf", b"fake", "application/pdf")}
    response = ext_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == "150.75"


@patch('extraction.pytesseract.image_to_string')
def test_extraction_returns_none_when_no_date(mock_ocr):
    """Test de devolución de None cuando no hay fecha"""
    mock_ocr.return_value = "Documento sin fecha"
    
    files = {"file": ("test.pdf", b"fake", "application/pdf")}
    response = ext_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["fecha"] is None


@patch('extraction.pytesseract.image_to_string')
def test_extraction_returns_none_when_no_total(mock_ocr):
    """Test de devolución de None cuando no hay total"""
    mock_ocr.return_value = "Documento sin importe"
    
    files = {"file": ("test.pdf", b"fake", "application/pdf")}
    response = ext_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] is None


# ===== TESTS PARA LAYOUT =====
@patch('layout.pytesseract.image_to_data')
def test_layout_extracts_words_with_positions(mock_ocr_data):
    """Test de extracción de palabras con sus posiciones en layout"""
    mock_ocr_data.return_value = {
        "level": [1, 2, 3],
        "text": ["Texto", "Prueba", "Layout"],
        "left": [10, 20, 30],
        "top": [5, 15, 25],
        "width": [50, 60, 70],
        "height": [20, 20, 20],
    }
    
    img_content = create_test_image()
    files = {"file": ("test.png", img_content, "image/png")}
    response = layout_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["layout"]) == 3
    
    # Verificar primera palabra
    assert data["layout"][0]["text"] == "Texto"
    assert data["layout"][0]["box"] == [10, 5, 50, 20]
    assert data["layout"][0]["type"] == "word"


@patch('layout.pytesseract.image_to_data')
def test_layout_skips_empty_text(mock_ocr_data):
    """Test de ignoración de elementos de texto vacío en layout"""
    mock_ocr_data.return_value = {
        "level": [1, 2, 3],
        "text": ["Palabra", "", "Otra"],
        "left": [10, 20, 30],
        "top": [5, 15, 25],
        "width": [50, 60, 70],
        "height": [20, 20, 20],
    }
    
    img_content = create_test_image()
    files = {"file": ("test.png", img_content, "image/png")}
    response = layout_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()

    assert len(data["layout"]) == 2
    assert data["layout"][0]["text"] == "Palabra"
    assert data["layout"][1]["text"] == "Otra"


# ===== TESTS PARA OCR =====
@patch('ocr.pytesseract.image_to_string')
def test_ocr_extracts_text_correctly(mock_ocr):
    """Test de extracción correcta de texto por OCR"""
    mock_ocr.return_value = "Este es el texto detectado por OCR"
    
    img_content = create_test_image()
    files = {"file": ("test.png", img_content, "image/png")}
    response = ocr_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "Este es el texto detectado por OCR"


@patch('ocr.pytesseract.image_to_string')
def test_ocr_strips_whitespace(mock_ocr):
    """Test de eliminación de espacios en blanco inicial/final en OCR"""
    mock_ocr.return_value = "   Texto con espacios   "
    
    img_content = create_test_image()
    files = {"file": ("test.png", img_content, "image/png")}
    response = ocr_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "Texto con espacios"


@patch('ocr.pytesseract.image_to_string')
def test_ocr_handles_empty_result(mock_ocr):
    """Test de mensaje de OCR cuando no detecta texto"""
    mock_ocr.return_value = ""
    
    img_content = create_test_image()
    files = {"file": ("test.png", img_content, "image/png")}
    response = ocr_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "Sin texto detectado"
