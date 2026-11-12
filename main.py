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


def _iter_safely(value) -> list:
    """Iterate SDK collections defensively; mocked attributes in tests are not
    iterable and optional properties may be None."""
    if value is None:
        return []
    try:
        return list(value)
    except TypeError:
        return []


def _int_or(value, default):
    """Only real ints pass through; SDK optionals and mocked attributes must
    never leak into the JSON response."""
    return value if isinstance(value, int) else default


def _str_or_none(value):
    return value if isinstance(value, str) else None


def _span_dict(span) -> dict | None:
    """ContentSpan (offset/length into the content's markdown) as plain dict."""
    offset = getattr(span, "offset", None)
    length = getattr(span, "length", None)
    if offset is None or length is None:
        return None
    return {"offset": offset, "length": length}


def _serialize_pages(content) -> list[dict]:
    """Pages with their spans; the spans index the content's markdown, so cells
    and tables can be attributed to a page by span overlap."""
    pages = []
    for page in _iter_safely(getattr(content, "pages", None)):
        spans = [
            span
            for span in (
                _span_dict(s) for s in _iter_safely(getattr(page, "spans", None))
            )
            if span is not None
        ]
        pages.append({"page_number": _int_or(getattr(page, "page_number", None), None), "spans": spans})
    return pages


def _page_for_span(pages: list[dict], span) -> int | None:
    span = _span_dict(span)
    if span is None:
        return None
    start = span["offset"]
    end = start + span["length"]
    for page in pages:
        for page_span in page["spans"]:
            if start < page_span["offset"] + page_span["length"] and page_span["offset"] < end:
                return page["page_number"]
    return None


def _serialize_tables(content, pages: list[dict]) -> list[dict]:
    """Tables as cell grids: row/column indices, cell kind and text, plus the
    page each cell was read from. This is the deterministic source for column
    binding; the markdown stays available for display and validation."""
    tables = []
    for table in _iter_safely(getattr(content, "tables", None)):
        cells = []
        for cell in _iter_safely(getattr(table, "cells", None)):
            kind = getattr(cell, "kind", None)
            cells.append(
                {
                    "row_index": _int_or(getattr(cell, "row_index", 0), 0),
                    "column_index": _int_or(getattr(cell, "column_index", 0), 0),
                    "row_span": _int_or(getattr(cell, "row_span", 1), 1),
                    "column_span": _int_or(getattr(cell, "column_span", 1), 1),
                    "kind": str(kind).rsplit(".", 1)[-1].lower()
                    if isinstance(kind, str) or hasattr(kind, "value")
                    else "content",
                    "content": _str_or_none(getattr(cell, "content", None)),
                    "page_number": _page_for_span(pages, getattr(cell, "span", None)),
                    "span": _span_dict(getattr(cell, "span", None)),
                }
            )
        tables.append(
            {
                "row_count": _int_or(getattr(table, "row_count", 0), 0),
                "column_count": _int_or(getattr(table, "column_count", 0), 0),
                "page_number": _page_for_span(pages, getattr(table, "span", None)),
                "cells": cells,
            }
        )
    return tables


def extract_document(pdf_bytes: bytes, content_type: str = "application/pdf") -> dict:
    """
    Extract markdown plus the structured layout from PDF bytes using Azure AI
    Content Understanding.

    Args:
        pdf_bytes: Raw binary bytes of the PDF document.
        content_type: MIME type of the document.

    Returns:
        Dict with `page_content` (markdown), `page_count` and `structure`
        (per content: pages and tables as cell grids).
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
        structure_contents = []
        page_count = 0
        for content in _iter_safely(getattr(result, "contents", None) if result else None):
            if getattr(content, "markdown", None):
                extracted_parts.append(content.markdown)
            pages = _serialize_pages(content)
            tables = _serialize_tables(content, pages)
            structure_contents.append(
                {
                    "pages": pages,
                    "tables": tables,
                    "start_page_number": _int_or(getattr(content, "start_page_number", None), None),
                    "end_page_number": _int_or(getattr(content, "end_page_number", None), None),
                }
            )
            end = getattr(content, "end_page_number", None)
            if not isinstance(end, int):
                end = max(
                    (p["page_number"] for p in pages if isinstance(p["page_number"], int)),
                    default=0,
                )
            page_count = max(page_count, end)

        final_text = "\n\n".join(extracted_parts)
        final_text = convert_html_tables_in_text(final_text)

        logger.info(f"Successfully extracted {len(final_text)} characters")
        return {
            "page_content": final_text,
            "page_count": page_count,
            "structure": {"contents": structure_contents},
        }

    except HttpResponseError as e:
        logger.error(f"Azure Content Understanding API error: {e}")
        raise HTTPException(status_code=500, detail=f"Azure API error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")


def extract_text_from_pdf_bytes(pdf_bytes: bytes, content_type: str = "application/pdf") -> str:
    """
    Extract structured markdown text from PDF bytes using Azure AI Content Understanding.

    Args:
        pdf_bytes: Raw binary bytes of the PDF document.
        content_type: MIME type of the document.

    Returns:
        Extracted structured markdown text including headings, paragraphs, and tables.
    """
    return extract_document(pdf_bytes, content_type)["page_content"]


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
        JSON response with page_content, structure (pages and tables as cell
        grids), page_count and metadata
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
    
    extracted = await asyncio.to_thread(
        extract_document,
        pdf_data,
        content_type or "application/pdf"
    )
    
    return JSONResponse(
        content={
            "page_content": extracted["page_content"],
            "page_count": extracted["page_count"],
            "structure": extracted["structure"],
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
