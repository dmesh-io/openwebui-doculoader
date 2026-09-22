import os
import logging
import re
import asyncio
from pathlib import Path
from typing import Optional

from markdownify import markdownify
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="OpenWebUI Document Loader",
    description="External document extraction service using Azure AI Content Understanding",
    version="2.0.0"
)

# Azure Content Understanding configuration
AZURE_ENDPOINT = os.getenv("AZURE_CONTENT_UNDERSTANDING_ENDPOINT")
AZURE_KEY = os.getenv("AZURE_CONTENT_UNDERSTANDING_KEY")
ANALYZER_ID = os.getenv("AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID", "prebuilt-layout")
TEMP_DIR = os.getenv("TEMP_WORK_DIR", "/tmp/doculoader")

# Validate environment variables
if not AZURE_ENDPOINT:
    logger.warning("AZURE_CONTENT_UNDERSTANDING_ENDPOINT not set")
if not AZURE_KEY:
    logger.warning("AZURE_CONTENT_UNDERSTANDING_KEY not set")

# Ensure temp directory exists
Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)


def get_azure_client() -> ContentUnderstandingClient:
    """Create and return Azure Content Understanding client."""
    if not AZURE_ENDPOINT or not AZURE_KEY:
        raise HTTPException(
            status_code=500,
            detail="Azure Content Understanding credentials not configured"
        )
    
    return ContentUnderstandingClient(
        endpoint=AZURE_ENDPOINT,
        credential=AzureKeyCredential(AZURE_KEY)
    )


def convert_html_tables_in_text(text: str) -> str:
    """
    Finds HTML tables in Markdown text and converts them to Markdown pipe tables.
    """
    if "<table" not in text.lower():
        return text
        
    table_pattern = re.compile(r'<table.*?>.*?</table>', re.IGNORECASE | re.DOTALL)
    
    def table_replacer(match):
        table_html = match.group(0)
        return markdownify(table_html)
        
    return table_pattern.sub(table_replacer, text)


def extract_text_from_pdf_bytes(pdf_bytes: bytes, content_type: str = "application/pdf") -> str:
    """
    Extract structured markdown text from PDF bytes using Azure AI Content Understanding.
    
    Args:
        pdf_bytes: Raw binary bytes of the PDF document.
        content_type: MIME type of the document.
        
    Returns:
        Extracted structured markdown text including headings, paragraphs, and tables.
    """
    logger.info(f"Extracting document with analyzer '{ANALYZER_ID}' ({len(pdf_bytes)} bytes)")
    client = get_azure_client()

    try:
        poller = client.begin_analyze_binary(
            analyzer_id=ANALYZER_ID,
            binary_input=pdf_bytes,
            content_type=content_type or "application/pdf"
        )
        result = poller.result()
        
        extracted_parts = []
        if result and getattr(result, "contents", None):
            for content in result.contents:
                if getattr(content, "markdown", None):
                    extracted_parts.append(content.markdown)
        
        final_text = "\n\n".join(extracted_parts)
        final_text = convert_html_tables_in_text(final_text)
        
        logger.info(f"Successfully extracted {len(final_text)} characters")
        return final_text
        
    except HttpResponseError as e:
        logger.error(f"Azure Content Understanding API error: {e}")
        raise HTTPException(status_code=500, detail=f"Azure API error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")


def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract structured markdown from a PDF file on disk using Azure AI Content Understanding.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        Extracted markdown/text content
    """
    with open(file_path, "rb") as f:
        pdf_bytes = f.read()
    return extract_text_from_pdf_bytes(pdf_bytes)


@app.get("/")
async def root():
    """Health check root endpoint."""
    return {
        "status": "healthy",
        "service": "OpenWebUI Document Loader",
        "azure_configured": bool(AZURE_ENDPOINT and AZURE_KEY)
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "azure_configured": bool(AZURE_ENDPOINT and AZURE_KEY)
    }


@app.put("/process")
async def process_document(
    request: Request,
    content_type: Optional[str] = Header(None),
    x_filename: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None)
):
    """
    Process uploaded document using Azure AI Content Understanding.
    Compatible with Open Web UI external document extraction format.
    
    This endpoint expects raw PDF data in the request body (not multipart form).
    
    Args:
        request: FastAPI request object with PDF data in body
        content_type: Content-Type header
        x_filename: X-Filename header with the original filename
        authorization: Authorization header (Bearer token)
        
    Returns:
        JSON response with page_content and metadata
    """
    # Read raw body data
    pdf_data = await request.body()
    
    if not pdf_data:
        raise HTTPException(
            status_code=400,
            detail="No file data provided"
        )
    
    # Extract filename from header or use default
    filename = x_filename or "document.pdf"
    
    # Validate it's a PDF (basic check)
    if not filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported"
        )
    
    extracted_text = await asyncio.to_thread(
        extract_text_from_pdf_bytes,
        pdf_data,
        content_type or "application/pdf"
    )
    
    return JSONResponse(
        content={
            "page_content": extracted_text,
            "metadata": {
                "filename": filename,
                "content_type": content_type or "application/pdf",
                "engine": "azure-content-understanding"
            }
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
