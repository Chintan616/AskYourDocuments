# AskYourDocuments

AskYourDocuments is a modern, full-stack AI application that allows users to upload documents (PDF, DOCX, TXT, Excel, etc.) and chat with them using Advanced Retrieval-Augmented Generation (RAG). 

The application uses state-of-the-art Large Language Models (LLMs) to retrieve relevant information from your documents and provide precise, context-aware answers.

## 🚀 Features
- **Multi-Document Support:** Upload and chat with multiple documents simultaneously.
- **Advanced RAG Architecture:** Utilizes intelligent chunking, vector similarity search, and cross-encoder reranking to ensure highly accurate answers.
- **Cloud Storage Integration:** Automatically stages and stores uploaded documents securely in Amazon S3.
- **Vector Database:** Uses PostgreSQL with `pgvector` to store and quickly search document embeddings.
- **Beautiful UI:** A stunning, fully responsive frontend featuring dark mode, glassmorphism aesthetics, and smooth animations.
- **Dockerized Deployment:** Ready to be deployed instantly on AWS EC2 or any other cloud provider via Docker Compose.

## 🛠️ Tech Stack
- **Frontend:** HTML, Vanilla JavaScript, Tailwind CSS (via CDN), served by FastAPI/Jinja2
- **Backend:** Python, FastAPI, Uvicorn, Gunicorn
- **AI/ML:** LangChain, OpenAI API (via GitHub Models endpoint), PyTorch (CPU-optimized), Sentence-Transformers (Reranking)
- **Database:** PostgreSQL (with `pgvector` extension)
- **Document Processing:** PyMuPDF (`fitz`), pdfplumber, pytesseract
- **Cloud Infrastructure:** AWS EC2, Amazon S3, Docker

## ⚙️ Local Setup

### 1. Clone the repository
```bash
git clone https://github.com/Chintan616/AskYourDocuments.git
cd AskYourDocuments
```

### 2. Set up Environment Variables
Navigate to the `backend` directory and create a `.env` file:
```bash
cd backend
nano .env
```
Populate it with the following credentials:
```env
# AWS S3 Configuration
AWS_ACCESS_KEY_ID="your_aws_access_key"
AWS_SECRET_ACCESS_KEY="your_aws_secret_key"
AWS_REGION="us-east-1"
AWS_S3_BUCKET_NAME="your_s3_bucket_name"

# Database (Leave as is for Docker Compose)
DATABASE_URL="postgresql://postgres:postgres@pgvector:5432/askyourdocs"

# AI Credentials (GitHub Models / Azure)
AZURE_LLM_API_KEY_SECRET="your_github_or_azure_token"
GITHUB_TOKEN="your_github_or_azure_token"
```

### 3. Run with Docker Compose
To boot up both the FastAPI backend (which serves the frontend UI) and the PostgreSQL Vector Database:
```bash
docker compose up --build -d
```
The application will be available at `http://localhost:5001`.

## ☁️ Deployment (AWS EC2)

1. Provision an **Ubuntu Server (t3.small or larger)** on AWS EC2.
2. Attach an EBS volume of at least **20-30 GB** (PyTorch and Python dependencies require space).
3. Install `docker` and `docker-compose`.
4. Clone this repository onto the server.
5. Create your `.env` file in the `backend` folder.
6. Run `sudo docker compose up --build -d`.

## 📜 License
This project is open-source and available under the MIT License.
