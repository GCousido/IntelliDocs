from fastapi.testclient import TestClient
import sys
import os
import io
import re
from PIL import Image
from unittest.mock import patch

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


def assert_confidence_in_range(value: float):
    assert 0.0 <= value <= 1.0


def normalize_amount(value: str | None) -> str:
    return re.sub(r"[^\d.,]", "", value or "")


def make_ocr_data(
    text: str = "Texto",
    conf: str = "85",
    left: int = 10,
    top: int = 5,
    width: int = 50,
    height: int = 20,
    block_num: int = 1,
):
    return {
        "text": [text],
        "conf": [conf],
        "block_num": [block_num],
        "left": [left],
        "top": [top],
        "width": [width],
        "height": [height],
    }


# ===== TESTS PARA CLASSIFICATION =====
def test_classification_invoice():
    """Test de clasificación correcta de una factura"""
    payload = {"text": "Factura numero factura 12345 con IVA y total a pagar"}
    response = class_client.post("/process", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Factura"
    assert_confidence_in_range(data["confidence"])


def test_classification_ticket():
    """Test de clasificación correcta de un ticket"""
    payload = {"text": "Ticket de compra con total a pagar en caja"}
    response = class_client.post("/process", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Ticket"
    assert_confidence_in_range(data["confidence"])


def test_classification_dni_document():
    """Test de clasificación correcta de documento de identidad"""
    payload = {"text": "DNI 12345678Z Documento Nacional de Identidad"}
    response = class_client.post("/process", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Documento Identidad"
    assert_confidence_in_range(data["confidence"])


def test_classification_generic_document():
    """Test de clasificación genérica sin palabras clave"""
    payload = {"text": "Contenido sin palabra clave especifica"}
    response = class_client.post("/process", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Documento General"
    assert_confidence_in_range(data["confidence"])


def test_classification_invoice_keyword_invoice():
    """Test de que 'invoice' en inglés se clasifica como factura"""
    payload = {"text": "This is an invoice document with invoice number 2024-01"}
    response = class_client.post("/process", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Factura"


def test_classification_json_payload_invoice():
    """Test de clasificación por JSON para una factura"""
    payload = {"text": "Factura con total a pagar 100 euros, IVA 21%, numero factura F-123"}
    response = class_client.post("/process", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Factura"
    assert_confidence_in_range(data["confidence"])


# ===== TESTS PARA EXTRACTION =====
def test_extraction_extracts_date_correctly():
    """Test de extracción correcta de fecha del documento"""
    payload = {
        "text": "Documento fechado el 25/12/2023 con total",
        "label": "Documento General",
        "layout": {"layout": []},
    }
    response = ext_client.post("/process", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Documento General"
    assert data["fields"]["fecha"] == "25/12/2023"


def test_extraction_extracts_multiple_dates_first_one():
    """Test de extracción de primera fecha cuando hay varias"""
    payload = {
        "text": "Fecha 01/01/2023 y vencimiento 31/12/2023",
        "label": "Documento General",
        "layout": {"layout": []},
    }
    response = ext_client.post("/process", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["fields"]["fecha"] == "01/01/2023"


def test_extraction_extracts_total_correctly():
    """Test de extracción correcta del total"""
    payload = {
        "text": "Total a pagar 250.50 euros",
        "label": "Factura",
        "layout": {"layout": []},
    }
    response = ext_client.post("/process", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["fields"]["total"] == "250.50"


def test_extraction_extracts_suma_keyword():
    """Test de reconocimiento de 'suma' como palabra clave para total"""
    payload = {
        "text": "Suma€150.75 resto",
        "label": "Ticket",
        "layout": {"layout": []},
    }
    response = ext_client.post("/process", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert normalize_amount(data["fields"]["total"]) in {"150.75", "150,75"}


def test_extraction_json_payload_invoice_fields():
    """Test de extracción por JSON para campos de factura"""
    payload = {
        "text": "Factura: 12345 con total 250.50 y fecha 25/12/2023",
        "label": "Factura",
        "layout": {"layout": []},
    }
    response = ext_client.post("/process", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Factura"
    assert data["fields"]["fecha"] == "25/12/2023"
    assert data["fields"]["total"] == "250.50"
    assert data["fields"]["numero_factura"] == "12345"


def test_extraction_returns_none_when_no_date():
    """Test de devolución de None cuando no hay fecha"""
    payload = {
        "text": "Documento sin fecha",
        "label": "Documento General",
        "layout": {"layout": []},
    }
    response = ext_client.post("/process", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["fields"]["fecha"] is None


def test_extraction_returns_none_when_no_total():
    """Test de devolución de None cuando no hay total"""
    payload = {
        "text": "Documento sin importe",
        "label": "Factura",
        "layout": {"layout": []},
    }
    response = ext_client.post("/process", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["fields"]["total"] is None


# ===== TESTS PARA LAYOUT =====
@patch('layout.pytesseract.image_to_data')
def test_layout_extracts_words_with_positions(mock_ocr_data):
    """Test de extracción de palabras con sus posiciones en layout"""
    mock_ocr_data.return_value = {
        "level": [5, 5, 5],
        "text": ["Texto", "Prueba", "Layout"],
        "left": [10, 20, 30],
        "top": [5, 15, 25],
        "width": [50, 60, 70],
        "height": [20, 20, 20],
        "conf": ["85", "88", "90"],
        "block_num": [1, 1, 1],
        "par_num": [1, 1, 1],
        "line_num": [1, 1, 1],
        "word_num": [1, 2, 3],
    }
    
    img_content = create_test_image()
    files = {"file": ("test.png", img_content, "image/png")}
    response = layout_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["page_count"] == 1
    assert len(data["layout"]) == 1

    page = data["layout"][0]
    assert len(page["words"]) == 3

    # Verificar primera palabra
    assert page["words"][0]["text"] == "Texto"
    assert page["words"][0]["box"] == {"left": 10, "top": 5, "width": 50, "height": 20}
    assert page["words"][0]["type"] == "word"

    assert len(page["lines"]) == 1
    assert page["lines"][0]["text"] == "Texto Prueba Layout"

    assert len(page["blocks"]) == 1
    assert page["blocks"][0]["text"] == "Texto Prueba Layout"


@patch('layout.pytesseract.image_to_data')
def test_layout_skips_empty_text(mock_ocr_data):
    """Test de ignoración de elementos de texto vacío en layout"""
    mock_ocr_data.return_value = {
        "level": [5, 5, 5],
        "text": ["Palabra", "", "Otra"],
        "left": [10, 20, 30],
        "top": [5, 15, 25],
        "width": [50, 60, 70],
        "height": [20, 20, 20],
        "conf": ["85", "-1", "90"],
        "block_num": [1, 1, 1],
        "par_num": [1, 1, 1],
        "line_num": [1, 1, 1],
        "word_num": [1, 2, 3],
    }
    
    img_content = create_test_image()
    files = {"file": ("test.png", img_content, "image/png")}
    response = layout_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()

    page = data["layout"][0]
    assert len(page["words"]) == 2
    assert page["words"][0]["text"] == "Palabra"
    assert page["words"][1]["text"] == "Otra"
    assert page["lines"][0]["text"] == "Palabra Otra"


# ===== TESTS PARA OCR =====
@patch('ocr.pytesseract.image_to_osd')
@patch('ocr.pytesseract.image_to_data')
@patch('ocr.pytesseract.image_to_string')
def test_ocr_extracts_text_correctly(mock_ocr, mock_ocr_data, mock_osd):
    """Test de extracción correcta de texto por OCR"""
    mock_osd.return_value = {"rotate": 0}
    mock_ocr.return_value = "Este es el texto detectado por OCR"
    mock_ocr_data.return_value = make_ocr_data(text="Texto", conf="85")
    
    img_content = create_test_image()
    files = {"file": ("test.png", img_content, "image/png")}
    response = ocr_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "Este es el texto detectado por OCR"
    assert data["language"] == "spa+eng"
    assert data["page_count"] == 1
    assert data["pages"][0]["text"] == "Este es el texto detectado por OCR"


@patch('ocr.pytesseract.image_to_osd')
@patch('ocr.pytesseract.image_to_data')
@patch('ocr.pytesseract.image_to_string')
def test_ocr_strips_whitespace(mock_ocr, mock_ocr_data, mock_osd):
    """Test de eliminación de espacios en blanco inicial/final en OCR"""
    mock_osd.return_value = {"rotate": 0}
    mock_ocr.return_value = "   Texto con espacios   "
    mock_ocr_data.return_value = make_ocr_data(text="Texto", conf="80")
    
    img_content = create_test_image()
    files = {"file": ("test.png", img_content, "image/png")}
    response = ocr_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "Texto con espacios"


@patch('ocr.pytesseract.image_to_osd')
@patch('ocr.pytesseract.image_to_data')
@patch('ocr.pytesseract.image_to_string')
def test_ocr_handles_empty_result(mock_ocr, mock_ocr_data, mock_osd):
    """Test de mensaje de OCR cuando no detecta texto"""
    mock_osd.return_value = {"rotate": 0}
    mock_ocr.return_value = ""
    mock_ocr_data.return_value = make_ocr_data(text="", conf="-1", width=0, height=0)
    
    img_content = create_test_image()
    files = {"file": ("test.png", img_content, "image/png")}
    response = ocr_client.post("/process", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "Sin texto detectado"
