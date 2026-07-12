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

from .state import APP_STATE, APP_WEB_STATE, CHROMA_COLLECTION_NAME_PREFIX
class PGCollection:
    def __init__(self, name, conn):
        self.name = name
        self.conn = conn

    def count(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM embeddings WHERE collection_name = %s", (self.name,))
            return cur.fetchone()[0]

def initialize_chromadb_from_kb():
    global APP_STATE
    if APP_STATE["db_initialized"]:
        return True
    
    neon_url = os.getenv("NEON_DATABASE_URL")
    if not neon_url:
        logger.error("NEON_DATABASE_URL not found in environment.")
        return False
        
    logger.info("Initializing Neon DB (PostgreSQL)")
    try:
        conn = psycopg2.connect(neon_url)
        conn.autocommit = True
        
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            
        register_vector(conn)
        
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    id TEXT PRIMARY KEY,
                    collection_name TEXT NOT NULL,
                    embedding vector(3072),
                    document TEXT,
                    metadata JSONB
                )
            """)
        
        APP_STATE["chroma_client"] = conn
        logger.success("Neon DB initialized OK.")
        APP_STATE["db_initialized"] = True
    except Exception as e:
        logger.error(f"Neon DB init FAIL: {e}")
        APP_STATE["db_initialized"] = False
        return False
    return True

def get_or_create_collection_cached(
    collection_name_str: str,
):
    if not APP_STATE.get("db_initialized") or not APP_STATE.get("chroma_client"):
        logger.error("Neon DB not init.")
        return None
    if collection_name_str in APP_STATE["chroma_collection_cache"]:
        return APP_STATE["chroma_collection_cache"][collection_name_str]
    try:
        collection = PGCollection(collection_name_str, APP_STATE["chroma_client"])
        APP_STATE["chroma_collection_cache"][collection_name_str] = collection
        logger.info(f"Collection '{collection_name_str}' accessed. Items: {collection.count()}")
        return collection
    except Exception as e:
        logger.error(f"FAIL get/create DB collection '{collection_name_str}': {e}")
        return None

