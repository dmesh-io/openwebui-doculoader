# OpenWebUI Document Loader

External document extraction service for Open Web UI using Azure AI Content Understanding. This service provides structured markdown text extraction compatible with Open Web UI's external document extraction API.

## Features

- **Azure AI Content Understanding Integration**: Uses Azure's multimodal generative AI and extraction capabilities via Azure AI Foundry
- **Structured Markdown Output**: Extracts headings, paragraphs, lists, and tables formatted as GitHub-Flavored Markdown for optimal RAG and LLM context
- **Open Web UI Compatible**: Implements the standard external document extraction API format
- **FastAPI Backend**: High-performance async API with automatic documentation
- **Docker Support**: Easy deployment with Docker container
- **Configurable**: Environment-based configuration for Azure credentials, analyzer ID, and working directory

## Requirements

- Python 3.11+
- Azure AI Content Understanding resource (from Azure AI Foundry)
- Docker (for containerized deployment)

## Setup

### 1. Azure AI Content Understanding

1. In the **[Azure Portal](https://portal.azure.com)** or **[Azure AI Foundry](https://ai.azure.com)**, create an **Azure AI Foundry** (or **Azure AI Services**) resource in a supported region (e.g., `Sweden Central`, `West US`, `Australia East`, `East US 2`).
2. Go to **Keys and Endpoint** in your resource overview.
3. Note your endpoint URL (e.g., `https://your-resource.cognitiveservices.azure.com/`).
4. Copy your API key from the Azure Portal.
5. (Optional) Out of the box, Content Understanding uses prebuilt analyzers like `prebuilt-documentSearch` or `prebuilt-layout` without requiring manual model training. You can also configure custom analyzers in Azure AI Foundry.

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
  -e AZURE_CONTENT_UNDERSTANDING_ENDPOINT="https://your-resource.cognitiveservices.azure.com/" \
  -e AZURE_CONTENT_UNDERSTANDING_KEY="your-api-key" \
  -e AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID="prebuilt-documentSearch" \
  --name doculoader \
  openwebui-doculoader
```

## Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `AZURE_CONTENT_UNDERSTANDING_ENDPOINT` | Azure Content Understanding endpoint URL | Yes | - |
| `AZURE_CONTENT_UNDERSTANDING_KEY` | Azure Content Understanding API key | Yes | - |
| `AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID` | Analyzer ID to use | No | `prebuilt-documentSearch` |
| `TEMP_WORK_DIR` | Temporary directory for file processing | No | `/tmp/doculoader` |

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
  "page_content": "Extracted structured markdown text...",
  "metadata": {
    "filename": "document.pdf",
    "content_type": "application/pdf",
    "engine": "azure-content-understanding"
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

Now when you upload PDF documents to Open Web UI, they will be processed through Azure AI Content Understanding with high-quality markdown extraction.

## How It Works

1. Client (Open Web UI) sends a PUT request to `/process` with raw PDF data
2. Document bytes are sent directly to Azure AI Content Understanding using the `prebuilt-documentSearch` analyzer
3. Content Understanding extracts text, layout, tables, and document hierarchy as structured markdown
4. Extracted markdown text is returned in `page_content` field with metadata
5. Temporary processing files are cleaned up

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
- Errors and warnings

View logs:
```bash
# Docker
docker logs doculoader

# Local
# Check console output
```

## Troubleshooting

### "Azure Content Understanding credentials not configured"
- Ensure `AZURE_CONTENT_UNDERSTANDING_ENDPOINT` and `AZURE_CONTENT_UNDERSTANDING_KEY` are set
- Check that environment variables are properly loaded

### "Only PDF files are supported"
- This service currently processes PDF files
- Ensure your file has a `.pdf` extension

### Azure API Errors
- Verify your Azure credentials are correct
- Check that your Azure resource is active and has model deployments configured (e.g. GPT-4o)
- Ensure your endpoint URL is properly formatted

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## Support

For issues and questions:
- Open an issue on GitHub
- Check Azure AI Content Understanding documentation: https://learn.microsoft.com/azure/ai-services/content-understanding/
