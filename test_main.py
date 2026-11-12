"""
Pytest tests for OpenWebUI Document Loader API using Azure AI Content Understanding.
"""
import io
import pytest
from types import SimpleNamespace
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from azure.core.exceptions import HttpResponseError
from main import app, extract_text_from_pdf


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_azure_client():
    """Mock Azure Content Understanding client."""
    with patch('main.get_azure_client') as mock_get_client:
        mock_client_instance = Mock()
        mock_get_client.return_value = mock_client_instance
        yield mock_client_instance


def create_test_pdf_bytes() -> bytes:
    """Create simple test PDF bytes."""
    return b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >> endobj
4 0 obj << /Length 44 >> stream
BT /F1 12 Tf 100 700 Td (Test PDF) Tj ET
endstream endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000214 00000 n 
trailer << /Size 5 /Root 1 0 R >>
startxref
308
%%EOF"""


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_root_endpoint(self, client):
        """Test root endpoint returns service info and health status."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "OpenWebUI Document Loader"
        assert "azure_configured" in data
    
    def test_health_endpoint(self, client):
        """Test health endpoint returns status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "azure_configured" in data


class TestProcessEndpoint:
    """Test document processing endpoint."""
    
    def test_process_endpoint_without_credentials(self, client):
        """Test that endpoint returns HTTP 500 when Azure credentials are not configured."""
        pdf_data = create_test_pdf_bytes()
        
        with patch('main.AZURE_ENDPOINT', None), patch('main.AZURE_KEY', None):
            response = client.put(
                "/process",
                content=pdf_data,
                headers={
                    "Content-Type": "application/pdf",
                    "X-Filename": "test.pdf"
                }
            )
            assert response.status_code == 500
            assert "credentials not configured" in response.json()["detail"].lower()
    
    def test_process_endpoint_with_mock_azure(self, client, mock_azure_client):
        """Test successful document processing with mocked Azure Content Understanding client."""
        mock_result = Mock()
        mock_content = Mock()
        mock_content.markdown = "# Test Document\n\nThis is extracted text with layout."
        mock_result.contents = [mock_content]
        
        mock_poller = Mock()
        mock_poller.result.return_value = mock_result
        mock_azure_client.begin_analyze_binary.return_value = mock_poller
        
        pdf_data = create_test_pdf_bytes()
        response = client.put(
            "/process",
            content=pdf_data,
            headers={
                "Content-Type": "application/pdf",
                "X-Filename": "spec.pdf"
            }
        )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "page_content" in data
        assert "# Test Document" in data["page_content"]
        assert "This is extracted text with layout." in data["page_content"]
        assert data["metadata"]["filename"] == "spec.pdf"
        assert data["metadata"]["content_type"] == "application/pdf"
        assert data["metadata"]["engine"] == "azure-content-understanding"
        
        mock_azure_client.begin_analyze_binary.assert_called_once()
    
    def test_process_endpoint_non_pdf(self, client):
        """Test that endpoint rejects non-PDF files."""
        text_data = b"This is not a PDF file"
        
        response = client.put(
            "/process",
            content=text_data,
            headers={
                "Content-Type": "text/plain",
                "X-Filename": "test.txt"
            }
        )
        
        assert response.status_code == 400
        assert "Only PDF files are supported" in response.json()["detail"]
    
    def test_process_endpoint_no_filename(self, client, mock_azure_client):
        """Test processing without X-Filename header uses default 'document.pdf'."""
        mock_result = Mock()
        mock_content = Mock()
        mock_content.markdown = "Default document content"
        mock_result.contents = [mock_content]
        
        mock_poller = Mock()
        mock_poller.result.return_value = mock_result
        mock_azure_client.begin_analyze_binary.return_value = mock_poller
        
        pdf_data = create_test_pdf_bytes()
        response = client.put(
            "/process",
            content=pdf_data,
            headers={"Content-Type": "application/pdf"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["metadata"]["filename"] == "document.pdf"
        assert data["page_content"] == "Default document content"
    
    def test_process_endpoint_empty_body(self, client):
        """Test that endpoint rejects empty request body."""
        response = client.put(
            "/process",
            content=b"",
            headers={
                "Content-Type": "application/pdf",
                "X-Filename": "test.pdf"
            }
        )
        
        assert response.status_code == 400
        assert "No file data provided" in response.json()["detail"]
    
    def test_process_endpoint_with_authorization(self, client, mock_azure_client):
        """Test that endpoint accepts Authorization header."""
        mock_result = Mock()
        mock_content = Mock()
        mock_content.markdown = "Authorized content extraction"
        mock_result.contents = [mock_content]
        
        mock_poller = Mock()
        mock_poller.result.return_value = mock_result
        mock_azure_client.begin_analyze_binary.return_value = mock_poller
        
        pdf_data = create_test_pdf_bytes()
        response = client.put(
            "/process",
            content=pdf_data,
            headers={
                "Content-Type": "application/pdf",
                "X-Filename": "test.pdf",
                "Authorization": "Bearer test-token-12345"
            }
        )
        
        assert response.status_code == 200
        assert response.json()["page_content"] == "Authorized content extraction"


class TestLayoutAndMarkdownExtraction:
    """Test layout, table, and multi-content extraction."""
    
    def test_table_markdown_extraction(self, client, mock_azure_client):
        """Test that markdown tables are properly preserved in page_content."""
        table_markdown = """# Technical Specification

| Parameter | Value | Unit |
| :--- | :--- | :--- |
| Voltage | 230 | V |
| Current | 16 | A |
| Frequency | 50 | Hz |
"""
        mock_result = Mock()
        mock_content = Mock()
        mock_content.markdown = table_markdown
        mock_result.contents = [mock_content]
        
        mock_poller = Mock()
        mock_poller.result.return_value = mock_result
        mock_azure_client.begin_analyze_binary.return_value = mock_poller
        
        pdf_data = create_test_pdf_bytes()
        response = client.put(
            "/process",
            content=pdf_data,
            headers={"Content-Type": "application/pdf"}
        )
        
        assert response.status_code == 200
        content = response.json()["page_content"]
        assert "| Parameter | Value | Unit |" in content
        assert "| Voltage | 230 | V |" in content
    
    def test_multiple_contents(self, client, mock_azure_client):
        """Test processing document returning multiple content segments."""
        mock_result = Mock()
        mock_c1 = Mock()
        mock_c1.markdown = "# Section 1\nContent for section 1"
        mock_c2 = Mock()
        mock_c2.markdown = "# Section 2\nContent for section 2"
        mock_result.contents = [mock_c1, mock_c2]
        
        mock_poller = Mock()
        mock_poller.result.return_value = mock_result
        mock_azure_client.begin_analyze_binary.return_value = mock_poller
        
        pdf_data = create_test_pdf_bytes()
        response = client.put(
            "/process",
            content=pdf_data,
            headers={"Content-Type": "application/pdf"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "Section 1" in data["page_content"]
        assert "Section 2" in data["page_content"]
    
    def test_azure_api_error_handling(self, client, mock_azure_client):
        """Test proper error handling when Azure API returns HttpResponseError."""
        mock_azure_client.begin_analyze_binary.side_effect = HttpResponseError(
            message="Azure Service Unavailable"
        )
        
        pdf_data = create_test_pdf_bytes()
        response = client.put(
            "/process",
            content=pdf_data,
            headers={"Content-Type": "application/pdf"}
        )
        
        assert response.status_code == 500
        assert "Azure API error" in response.json()["detail"]


class TestDirectExtractionFunction:
    """Test helper extraction from file path on disk."""
    
    def test_extract_text_from_pdf_file(self, mock_azure_client, tmp_path):
        """Test extract_text_from_pdf with a file path."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(create_test_pdf_bytes())
        
        mock_result = Mock()
        mock_content = Mock()
        mock_content.markdown = "# Extracted File Content"
        mock_result.contents = [mock_content]
        
        mock_poller = Mock()
        mock_poller.result.return_value = mock_result
        mock_azure_client.begin_analyze_binary.return_value = mock_poller
        
        result = extract_text_from_pdf(str(test_file))
        assert result == "# Extracted File Content"


class TestStructuredExtraction:
    """The structure payload exposes tables as cell grids (row/column indices,
    cell kind, page attribution) so clients can bind columns deterministically."""

    def _mock_result_with_structure(self):
        pages = [
            SimpleNamespace(page_number=1, spans=[SimpleNamespace(offset=0, length=50)]),
            SimpleNamespace(page_number=2, spans=[SimpleNamespace(offset=50, length=60)]),
        ]
        cells = [
            SimpleNamespace(
                row_index=0, column_index=0, row_span=1, column_span=1,
                kind=None, content="Policennummer",
                span=SimpleNamespace(offset=0, length=10),
            ),
            SimpleNamespace(
                row_index=0, column_index=1, row_span=1, column_span=1,
                kind=None, content="Betrag",
                span=SimpleNamespace(offset=55, length=6),
            ),
        ]
        table = SimpleNamespace(
            row_count=1, column_count=2,
            span=SimpleNamespace(offset=0, length=110), cells=cells,
        )
        content = SimpleNamespace(
            markdown="| Policennummer | Betrag |\n| --- | --- |\n| A1 | 10,00 |",
            pages=pages, tables=[table],
            start_page_number=1, end_page_number=2,
        )
        result = SimpleNamespace(contents=[content])
        poller = Mock()
        poller.result.return_value = result
        client = Mock()
        client.begin_analyze_binary.return_value = poller
        return client

    def test_process_endpoint_includes_structure(self, client):
        """Tables, cells and per-cell page attribution travel in the response."""
        with patch("main.get_azure_client") as mock_get_client:
            mock_get_client.return_value = self._mock_result_with_structure()
            response = client.put(
                "/process",
                content=create_test_pdf_bytes(),
                headers={"Content-Type": "application/pdf", "X-Filename": "test.pdf"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["page_count"] == 2
        contents = data["structure"]["contents"]
        assert len(contents) == 1
        assert contents[0]["start_page_number"] == 1
        assert contents[0]["end_page_number"] == 2

        tables = contents[0]["tables"]
        assert len(tables) == 1
        table = tables[0]
        assert table["row_count"] == 1
        assert table["column_count"] == 2
        assert table["page_number"] == 1

        cell_pages = {cell["column_index"]: cell["page_number"] for cell in table["cells"]}
        assert cell_pages == {0: 1, 1: 2}
        assert all(cell["kind"] == "content" for cell in table["cells"])
        assert table["cells"][0]["content"] == "Policennummer"

    def test_process_endpoint_tolerates_non_iterable_structure(self, client, mock_azure_client):
        """Contents whose pages/tables are not real collections (mocked tests,
        optional SDK fields) must not break the response."""
        mock_result = Mock()
        mock_content = Mock()
        mock_content.markdown = "Plain content without structure"
        mock_result.contents = [mock_content]

        mock_poller = Mock()
        mock_poller.result.return_value = mock_result
        mock_azure_client.begin_analyze_binary.return_value = mock_poller

        response = client.put(
            "/process",
            content=create_test_pdf_bytes(),
            headers={"Content-Type": "application/pdf"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["page_content"] == "Plain content without structure"
        assert data["structure"]["contents"] == [{"pages": [], "tables": [], "start_page_number": None, "end_page_number": None}]
        assert data["page_count"] == 0
