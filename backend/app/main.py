from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.api.endpoints import chat, documents, frontend
from app.services.setup import perform_initial_setup

app = FastAPI(title="AskYourDocuments Enterprise API", version="1.0.0")

# Read allowed origins from environment variable, default to allow all if not set or local
allowed_origins_env = os.environ.get("ALLOWED_ORIGINS")
allowed_origins = allowed_origins_env.split(",") if allowed_origins_env else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(frontend.router)

# Mount static files
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.on_event("startup")
async def startup_event():
    # Initialize the legacy AI and DB systems from core
    perform_initial_setup()
