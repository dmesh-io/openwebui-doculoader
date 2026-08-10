# OpenWebUI Document Loader

External document OCR service for Open Web UI using Azure Document Intelligence. This service provides per-page PDF text extraction compatible with Open Web UI's external document extraction API.

## Features

- **Azure Document Intelligence Integration**: Uses Azure's powerful OCR capabilities via Azure Foundry
- **Per-Page Processing**: Splits PDF into individual page files, sends each page separately to Azure Document Intelligence, and accumulates results
- **Open Web UI Compatible**: Implements the standard external document extraction API format
- **FastAPI Backend**: High-performance async API with automatic documentation
- **Docker Support**: Easy deployment with Docker container
- **Configurable**: Environment-based configuration for Azure credentials and working directory

## Requirements

- Python 3.11+
- Azure Document Intelligence resource (from Azure Foundry)
- Docker (for containerized deployment)

## Setup

### 1. Azure Document Intelligence

1. Create an Azure Document Intelligence resource in Azure Portal or Azure Foundry
2. Note your endpoint URL (e.g., `https://your-resource.cognitiveservices.azure.com/`)
3. Copy your API key from the Azure Portal

### 2. Local Development

```bash
# Clone the repository
git clone https://github.com/jomach/openwebui-doculoader.git
cd openwebui-doculoader

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your Azure credentials

# Run the application
python main.py
```

The service will be available at `http://localhost:8000`

### 3. Docker Deployment

```bash
# Build the Docker image
docker build -t openwebui-doculoader .

# Run the container
docker run -d \
  -p 8000:8000 \
  -e AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT="https://your-resource.cognitiveservices.azure.com/" \
  -e AZURE_DOCUMENT_INTELLIGENCE_KEY="your-api-key" \
  --name doculoader \
  openwebui-doculoader
```

## Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | Azure Document Intelligence endpoint URL | Yes | - |
| `AZURE_DOCUMENT_INTELLIGENCE_KEY` | Azure API key | Yes | - |
| `TEMP_WORK_DIR` | Temporary directory for file processing | No | `/tmp/doculoader` |
| `AZURE_DOCUMENT_INTELLIGENCE_MODEL` | Model used for analysis. `prebuilt-layout` detects tables, headings, figures and selection marks. `prebuilt-read` is cheaper but returns plain text only | No | `prebuilt-layout` |
| `AZURE_DOCUMENT_INTELLIGENCE_OUTPUT_FORMAT` | `markdown` or `text`. Markdown preserves headings and table structure and requires `prebuilt-layout` | No | `markdown` |

#### Table extraction

With the defaults above, tables are returned inside `page_content` as markup rather than
flattened lines. Simple tables come back as markdown pipe tables:

```markdown
| Name | Corp | Remark |
| - | - | - |
| Foo | | |
| Bar | Microsoft | Dummy |
```

Tables with merged cells, captions or complex headers come back as HTML `<table>` markup,
which preserves `rowspan` and `colspan`. Both forms are readable by an LLM, unlike the
line-by-line output of `prebuilt-read`.

Note that `prebuilt-layout` is billed at a higher per-page rate than `prebuilt-read`. Set
`AZURE_DOCUMENT_INTELLIGENCE_MODEL=prebuilt-read` and
`AZURE_DOCUMENT_INTELLIGENCE_OUTPUT_FORMAT=text` to return to the cheaper plain text behaviour.

## API Endpoints

### Health Check

```bash
GET /health
```

Response:
```json
{
  "status": "healthy",
  "azure_configured": true
}
```

### Process Document

```bash
PUT /process
Content-Type: application/pdf
X-Filename: document.pdf (optional)
Authorization: Bearer <token> (optional)
```

**Request Body:** Raw PDF file data

**Response:**
```json
{
  "page_content": "Extracted text from all pages...",
  "metadata": {
    "filename": "document.pdf",
    "content_type": "application/pdf",
    "engine": "azure-document-intelligence"
  }
}
```

### API Documentation

Once running, access interactive API documentation at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Integration with Open Web UI

1. Deploy this service (Docker recommended)
2. In Open Web UI, go to **Settings > Documents**
3. Select **Custom** as the extraction engine
4. Set the extraction URL to your deployment: `http://your-server:8000`
5. Save the configuration

The service will automatically handle PUT requests to `/process` endpoint.

Now when you upload PDF documents to Open Web UI, they will be processed through Azure Document Intelligence with per-page OCR.

## How It Works

1. Client (Open Web UI) sends a PUT request to `/process` with raw PDF data
2. PDF is split into individual page files using pypdf library
3. Each page file is sent separately to Azure Document Intelligence using the `prebuilt-layout` model
4. Markdown content, including table markup, is extracted from each page independently
5. Results from all pages are accumulated and formatted with page markers
6. Complete content is returned in `page_content` field with metadata
7. Temporary files (original PDF and page files) are cleaned up

## Development

### Testing the API

```bash
# Using curl
curl -X PUT "http://localhost:8000/process" \
  -H "Content-Type: application/pdf" \
  -H "X-Filename: test.pdf" \
  --data-binary "@test-document.pdf"

# Using Python
import requests

with open('test-document.pdf', 'rb') as f:
    response = requests.put(
        'http://localhost:8000/process',
        data=f.read(),
        headers={
            'Content-Type': 'application/pdf',
            'X-Filename': 'test.pdf'
        }
    )
    print(response.json())
```

### Logs

The application logs important events including:
- File uploads and processing
- Azure API interactions
- Page processing progress
- Errors and warnings

View logs:
```bash
# Docker
docker logs doculoader

# Local
# Check console output
```

## Troubleshooting

### "Azure Document Intelligence credentials not configured"
- Ensure `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` and `AZURE_DOCUMENT_INTELLIGENCE_KEY` are set
- Check that environment variables are properly loaded

### "Only PDF files are supported"
- This service currently only processes PDF files
- Ensure your file has a `.pdf` extension

### Azure API Errors
- Verify your Azure credentials are correct
- Check that your Azure resource is active and has available quota
- Ensure your endpoint URL is properly formatted

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## Support

For issues and questions:
- Open an issue on GitHub
- Check Azure Document Intelligence documentation: https://learn.microsoft.com/azure/ai-services/document-intelligence/
