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
from pyngrok import conf, ngrok
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

from .state import APP_STATE, AZURE_LLM_API_KEY_SECRET
from .database import initialize_chromadb_from_kb
from .llm import initialize_llm_model, initialize_rag_models_from_kb, initialize_hf_client_from_parser
def perform_initial_setup():
    logger.info("FastAPI App: Performing one-time initial setup for AI/DB systems...")
    if not AZURE_LLM_API_KEY_SECRET:
        logger.critical("AZURE_LLM_API_KEY_SECRET MISSING. APP CANNOT FUNCTION.")
        return False

    models_ok = initialize_rag_models_from_kb()
    llm_ok = initialize_llm_model()
    db_ok = initialize_chromadb_from_kb()
    hf_ok = initialize_hf_client_from_parser()

    if models_ok and llm_ok and db_ok and hf_ok:
        logger.success("FastAPI App: All critical AI/DB systems initialized.")
    else:
        logger.error("FastAPI App: CRITICAL - One or more essential AI/DB system initializations FAILED.")
    return models_ok and llm_ok and db_ok

APP_SYSTEMS_READY = perform_initial_setup()

