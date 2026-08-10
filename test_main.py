"""
Pytest tests for OpenWebUI Document Loader API.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_azure_and_split():
    """Mock both Azure client and PDF splitting."""
    with patch('main.get_azure_client') as mock_azure, \
         patch('main.split_pdf_by_pages') as mock_split:
        yield mock_azure, mock_split


def create_test_pdf_bytes():
    """Create a simple test PDF in bytes."""
    # Simple PDF structure
    pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test PDF) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000317 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
410
%%EOF"""
    return pdf_content


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_root_endpoint(self, client):
        """Test root endpoint returns health status."""
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
        """Test that endpoint returns error when Azure credentials not configured."""
        pdf_data = create_test_pdf_bytes()
        
        response = client.put(
            "/process",
            content=pdf_data,
            headers={
                "Content-Type": "application/pdf",
                "X-Filename": "test.pdf"
            }
        )
        
        # Should fail due to missing credentials
        assert response.status_code == 500
        assert "credentials" in response.json()["detail"].lower()
    
    def test_process_endpoint_with_mock_azure(self, client, mock_azure_and_split):
        """Test successful document processing with mocked Azure client."""
        mock_azure_client, mock_split = mock_azure_and_split
        
        # Mock PDF splitting to return a single page file
        mock_split.return_value = ["/tmp/page_1.pdf"]
        
        # Mock Azure response for the page
        mock_result = Mock()
        mock_result.content = "Test line 1\nTest line 2"

        mock_poller = Mock()
        mock_poller.result.return_value = mock_result
        
        mock_client_instance = Mock()
        mock_client_instance.begin_analyze_document.return_value = mock_poller
        mock_azure_client.return_value = mock_client_instance
        
        # Mock file operations - need to mock open() for reading page files
        mock_file = Mock()
        mock_file.read.return_value = b"fake pdf data"
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=False)
        
        with patch('builtins.open', return_value=mock_file), \
             patch('os.path.exists', return_value=False):
            # Make request
            pdf_data = create_test_pdf_bytes()
            response = client.put(
                "/process",
                content=pdf_data,
                headers={
                    "Content-Type": "application/pdf",
                    "X-Filename": "test.pdf"
                }
            )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "page_content" in data
        assert "metadata" in data
        assert "Test line 1" in data["page_content"]
        assert "Test line 2" in data["page_content"]
        assert data["metadata"]["filename"] == "test.pdf"
        assert data["metadata"]["engine"] == "azure-document-intelligence"
    
    def test_process_endpoint_non_pdf(self, client):
        """Test that endpoint rejects non-PDF files."""
        text_data = b"This is not a PDF"
        
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
    
    def test_process_endpoint_no_filename(self, client, mock_azure_and_split):
        """Test processing without X-Filename header uses default."""
        mock_azure_client, mock_split = mock_azure_and_split
        
        # Mock PDF splitting
        mock_split.return_value = ["/tmp/page_1.pdf"]
        
        # Mock Azure response
        mock_result = Mock()
        mock_result.content = "Test content"

        mock_poller = Mock()
        mock_poller.result.return_value = mock_result
        
        mock_client_instance = Mock()
        mock_client_instance.begin_analyze_document.return_value = mock_poller
        mock_azure_client.return_value = mock_client_instance
        
        # Mock file operations
        mock_file = Mock()
        mock_file.read.return_value = b"fake pdf"
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=False)
        
        with patch('builtins.open', return_value=mock_file), \
             patch('os.path.exists', return_value=False):
            # Make request without X-Filename
            pdf_data = create_test_pdf_bytes()
            response = client.put(
                "/process",
                content=pdf_data,
                headers={"Content-Type": "application/pdf"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["metadata"]["filename"] == "document.pdf"
    
    def test_process_endpoint_empty_body(self, client):
        """Test that endpoint rejects empty body."""
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
    
    def test_process_endpoint_with_authorization(self, client, mock_azure_and_split):
        """Test that endpoint accepts Authorization header."""
        mock_azure_client, mock_split = mock_azure_and_split
        
        # Mock PDF splitting
        mock_split.return_value = ["/tmp/page_1.pdf"]
        
        # Mock Azure response
        mock_result = Mock()
        mock_result.content = "Test"

        mock_poller = Mock()
        mock_poller.result.return_value = mock_result
        
        mock_client_instance = Mock()
        mock_client_instance.begin_analyze_document.return_value = mock_poller
        mock_azure_client.return_value = mock_client_instance
        
        # Mock file operations
        mock_file = Mock()
        mock_file.read.return_value = b"fake pdf"
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=False)
        
        with patch('builtins.open', return_value=mock_file), \
             patch('os.path.exists', return_value=False):
            # Make request with Authorization header
            pdf_data = create_test_pdf_bytes()
            response = client.put(
                "/process",
                content=pdf_data,
                headers={
                    "Content-Type": "application/pdf",
                    "X-Filename": "test.pdf",
                    "Authorization": "Bearer test-token"
                }
            )
        
        assert response.status_code == 200


class TestMultiPageProcessing:
    """Test multi-page document processing."""
    
    def test_multiple_pages(self, client, mock_azure_and_split):
        """Test processing document with multiple pages."""
        mock_azure_client, mock_split = mock_azure_and_split
        
        # Mock PDF splitting to return 3 page files
        mock_split.return_value = ["/tmp/page_1.pdf", "/tmp/page_2.pdf", "/tmp/page_3.pdf"]
        
        # Mock Azure responses - each page is processed separately
        # We'll create 3 different results for the 3 pages
        def create_mock_result(content):
            mock_result = Mock()
            mock_result.content = content
            return mock_result
        
        # Mock the Azure client to return different content for each call
        call_count = [0]
        page_contents = ["Page 1 content", "Page 2 content", "Page 3 content"]
        
        def mock_analyze(*args, **kwargs):
            mock_poller = Mock()
            mock_poller.result.return_value = create_mock_result(page_contents[call_count[0]])
            call_count[0] += 1
            return mock_poller
        
        mock_client_instance = Mock()
        mock_client_instance.begin_analyze_document.side_effect = mock_analyze
        mock_azure_client.return_value = mock_client_instance
        
        # Mock file operations
        mock_file = Mock()
        mock_file.read.return_value = b"fake pdf"
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=False)
        
        with patch('builtins.open', return_value=mock_file), \
             patch('os.path.exists', return_value=False):
            # Make request
            pdf_data = create_test_pdf_bytes()
            response = client.put(
                "/process",
                content=pdf_data,
                headers={
                    "Content-Type": "application/pdf",
                    "X-Filename": "multi-page.pdf"
                }
            )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "Page 1 content" in data["page_content"]
        assert "Page 2 content" in data["page_content"]
        assert "Page 3 content" in data["page_content"]
        assert "Page 1" in data["page_content"]
        assert "Page 2" in data["page_content"]
        assert "Page 3" in data["page_content"]
