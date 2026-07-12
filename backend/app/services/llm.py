import os
import subprocess
import sys
import os
import shutil
import subprocess
import sys
import time
import os
import os
import shutil
import base64
import io
import json
import logging
import os
import re
import shutil
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional
import os
import psycopg2
from pgvector.psycopg2 import register_vector
import fitz
import numpy as np
import pdfplumber
import pytesseract
import torch
import tiktoken

from langchain.chains.summarize import \
    load_summarize_chain
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from loguru import logger
from pdf2image import convert_from_path
from PIL import Image, UnidentifiedImageError
from openai import OpenAI
from langchain_openai import ChatOpenAI
import cv2
from docx import Document as DocxDocument
from openpyxl import load_workbook

from loguru import logger

from .state import APP_STATE, AZURE_LLM_MODEL_NAME, AZURE_EMBEDDING_MODEL_NAME, VISION_MODEL_ID_CONFIG, AZURE_LLM_API_KEY_SECRET, AZURE_EMBEDDING_API_KEY_SECRET, AZURE_EMBEDDING_ENDPOINT, RERANKER_MODEL_NAME, AZURE_LLM_ENDPOINT, HF_API_TOKEN_SECRET, RERANKER_MAX_TOKENS
from sentence_transformers import CrossEncoder
def initialize_hf_client_from_parser():
    global APP_STATE
    if APP_STATE["vision_client_initialized"]:
        return True
    if not APP_STATE["hf_api_token"]:
        logger.warning("HF_TOKEN not found. Vision features disabled.")
        return False
    if VISION_MODEL_ID_CONFIG == "YOUR_NOVITA_SUPPORTED_VISION_MODEL_ID_PLACEHOLDER":
        logger.error(f"VISION_MODEL_ID_CONFIG is placeholder. Vision disabled.")
        return False
    try:
        APP_STATE["hf_vision_client"] = OpenAI(
            base_url="https://router.huggingface.co/v1",
            api_key=HF_API_TOKEN_SECRET
        )
        logger.success(f"HF Router client for {VISION_MODEL_ID_CONFIG} initialized.")
        APP_STATE["vision_client_initialized"] = True
    except Exception as e:
        logger.error(f"HF client init error: {e}", exc_info=True)
        APP_STATE["hf_vision_client"] = None
        APP_STATE["vision_client_initialized"] = False
    return APP_STATE["vision_client_initialized"]

def initialize_llm_model():
    global APP_STATE
    if APP_STATE["llm_initialized"]:
        return True
    if not AZURE_LLM_API_KEY_SECRET:
        logger.critical("GITHUB_TOKEN missing for LLM/embeddings!")
        return False
    try:
        APP_STATE["azure_llm_client"] = OpenAI(
            base_url=AZURE_LLM_ENDPOINT,
            api_key=AZURE_LLM_API_KEY_SECRET,
        )
        logger.success(f"OpenAI client for '{AZURE_LLM_MODEL_NAME}' initialized.")

        APP_STATE["langchain_llm"] = ChatOpenAI(
            model=AZURE_LLM_MODEL_NAME,
            openai_api_base=AZURE_LLM_ENDPOINT,
            openai_api_key=AZURE_LLM_API_KEY_SECRET,
            temperature=0.25,
            max_tokens=1000,
        )
        logger.success(
            f"LangChain LLM wrapper for '{AZURE_LLM_MODEL_NAME}' initialized for potential summarization."
        )
        APP_STATE["llm_initialized"] = True
    except Exception as e:
        logger.critical(f"OpenAI LLM init FAILED: {e}", exc_info=True)
        APP_STATE["llm_initialized"] = False
    return APP_STATE["llm_initialized"]

def initialize_rag_models_from_kb():
    global APP_STATE
    if APP_STATE["rag_models_loaded"]:
        return True
    try:
        APP_STATE["tokenizer"] = tiktoken.get_encoding("cl100k_base")
        logger.success("Tiktoken 'cl00k_base' OK.")
    except Exception as e:
        logger.warning(f"Tiktoken fail: {e}. Using len().")
        APP_STATE["tokenizer"] = None

    device = "cuda" if torch.cuda.is_available() else "cpu"
    models_ok = True

    # Initialize Azure Embeddings Client
    if not APP_STATE.get("azure_embedding_client"):
        try:
            logger.info(f"Loading GitHub embeddings client: {AZURE_EMBEDDING_MODEL_NAME}...")
            APP_STATE["azure_embedding_client"] = OpenAI(
                base_url=AZURE_EMBEDDING_ENDPOINT,
                api_key=AZURE_EMBEDDING_API_KEY_SECRET
            )
            APP_STATE["embedding_model"] = APP_STATE["azure_embedding_client"]
            logger.success(f"GitHub embeddings client for '{AZURE_EMBEDDING_MODEL_NAME}' initialized.")
        except Exception as e:
            logger.critical(f"Azure Embeddings client load FAILED: {e}", exc_info=True)
            models_ok = False

    if not APP_STATE.get("reranker_model"):
        try:
            logger.info(f"Loading reranker: {RERANKER_MODEL_NAME} ({device})...")
            APP_STATE["reranker_model"] = CrossEncoder(
                RERANKER_MODEL_NAME,
                device=device,
                trust_remote_code=True,
                max_length=RERANKER_MAX_TOKENS,
            )
            logger.success("Reranker OK.")
        except Exception as e:
            logger.warning(f"Reranker load FAIL: {e}. Reranking off.")
            APP_STATE["reranker_model"] = None
    APP_STATE["rag_models_loaded"] = models_ok and APP_STATE["embedding_model"] is not None
    if not APP_STATE["rag_models_loaded"]:
        logger.error("Essential RAG models FAILED to load.")
    return APP_STATE["rag_models_loaded"]

