import os
STAGED_UPLOADS_DIR = "colab_staged_uploads_final_nocite"
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

from loguru import logger
EMBEDDING_MODEL_NAME = os.getenv("AZURE_EMBEDDING_MODEL_NAME", "openai/text-embedding-3-large")

AZURE_EMBEDDING_API_KEY_SECRET = os.getenv("GITHUB_TOKEN", globals().get("GITHUB_TOKEN", ""))

HF_API_TOKEN_SECRET = os.getenv("HF_TOKEN", globals().get("HF_TOKEN", ""))

LOG_FILE_PATH = "ask_your_doc_fastapi_app.log"

HF_API_TOKEN_SECRET = os.getenv("HF_TOKEN", "")

AZURE_EMBEDDING_API_KEY_SECRET = os.getenv("GITHUB_TOKEN", globals().get("AZURE_EMBEDDING_API_KEY_SECRET", ""))

AZURE_EMBEDDING_ENDPOINT = os.getenv("GITHUB_MODELS_ENDPOINT", "https://models.github.ai/inference")

AZURE_EMBEDDING_MODEL_NAME = os.getenv("AZURE_EMBEDDING_MODEL_NAME", "openai/text-embedding-3-large")

AZURE_LLM_ENDPOINT = AZURE_EMBEDDING_ENDPOINT # Reusing the endpoint

AZURE_LLM_MODEL_NAME = os.getenv("AZURE_LLM_MODEL_NAME", "openai/gpt-4o-mini")

AZURE_LLM_API_KEY_SECRET = AZURE_EMBEDDING_API_KEY_SECRET # Reusing the token for both

VISION_MODEL_ID_CONFIG = os.getenv("HF_VISION_MODEL_ID", "meta-llama/Llama-3.2-11B-Vision-Instruct:together")

IMAGE_OCR_PROMPT_CONFIG = "You are an advanced OCR model. Transcribe all text from this image accurately. If it's handwritten, do your best to read it. If there is no text, output 'No text found'."

IMAGE_DESCRIPTION_PROMPT_CONFIG = "You are an expert image analyst. Describe this image in detail, focusing on elements relevant to understanding a document (e.g., charts, diagrams, important visual features). If the image primarily contains text, transcribe the text instead of describing it as a visual."

EMBEDDING_MODEL_NAME = AZURE_EMBEDDING_MODEL_NAME # Reflect the new model for logging

EMBEDDING_MODEL_MAX_TOKENS = 8192 # Max input tokens for text-embedding-3-large

RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-12-v2"

RERANKER_MAX_TOKENS = 512 # Max sequence length for reranker.

PRIMARY_CHUNK_SIZE_TOKENS = 1500

PRIMARY_CHUNK_OVERLAP_TOKENS = 150

MIN_CHUNK_SIZE_TOKENS_NO_SPLIT = 75

EFFECTIVE_MAX_CHUNK_TOKENS = EMBEDDING_MODEL_MAX_TOKENS - 5

ATOMIC_BLOCK_NO_SPLIT_THRESHOLD = EFFECTIVE_MAX_CHUNK_TOKENS

SEPARATORS_HIERARCHICAL = ["\n\n\n", "\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]

GENERATION_MODEL_NAME = AZURE_LLM_MODEL_NAME # Reflect the new LLM model for logging

CHROMA_DB_PATH = "./ask_your_doc_chroma_db_merged_flask"

CHROMA_COLLECTION_NAME_PREFIX = "askdocmerged"

MAX_TOKENS_FOR_DIRECT_LLM_SUMMARIZATION = 80000

APP_STATE = {
    "hf_api_token": HF_API_TOKEN_SECRET,
    "hf_vision_client": None,
    "vision_client_initialized": False,
    "langchain_llm": None,
    "llm_initialized": False,
    "azure_llm_client": None,
    "tokenizer": None,
    "embedding_model": None,
    "azure_embedding_client": None,
    "reranker_model": None,
    "rag_models_loaded": False,
    "chroma_client": None,
    "db_initialized": False,
    "chroma_collection_cache": {},
    "original_doc_filename_for_chunking_context": None,
}

APP_WEB_STATE = {
    "staged_files": {},
    "processed_collections": {},
}

AI_PERSONA_NAME = "DocuMind AI"

AI_ROLE_DESCRIPTION = (
    "a meticulous and highly accurate AI assistant, designed to interact with "
    "and answer questions about documents. You are an expert in information "
    "retrieval and text comprehension."
)

AI_CORE_DIRECTIVE = (
    "Your responses must be grounded *exclusively* in the provided context data. "
    "You do not have access to external knowledge or the internet. "
    "You must not invent, assume, or infer information beyond what is explicitly stated in the context. "
    "Accuracy and adherence to the provided context are paramount. "
    "DO NOT invent data columns, values, or statuses that are not explicitly written in the PROVIDED CONTEXT."
)

AI_ANSWERING_STYLE_REFINED = (
    "Provide answers that are factual, precise, and directly supported by the text in "
    "the 'PROVIDED CONTEXT'. Use clear and concise language. If the query asks for "
    "specific data points (e.g., numbers, dates, names), ensure they are extracted "
    "accurately. If the query is more general, synthesize the relevant information "
    "from the context into a coherent response. Avoid jargon unless it's part of the "
    "document's language and relevant to the answer. You are polite, professional, and helpful."
)

AI_CONTEXTUAL_PRIORITIZATION_POLICY = (
    "When multiple context sources are provided, synthesize information if they are "
    "complementary. If they are contradictory, point out the discrepancy if relevant "
    "to the query, or prioritize the most specific or seemingly authoritative source if "
    "a single answer is required and discernable. If context chunks seem to be out of "
    "order, try to make sense of them logically if possible, but do not assume continuity "
    "if it's not evident."
)

AI_CITATION_POLICY_TEXT = (
    "DO NOT include bracketed citations like [Doc: ..., P:..., CkID:...] in your response. "
    "You may refer to 'the document' or specific document names if it's natural for the answer, "
    "but avoid detailed source tagging in the answer text."
)

AI_NO_ANSWER_POLICY = (
    "If the context is insufficient to answer the query, you must state: 'Based on the provided document context, I could not find the information to answer this question.'"
)

AI_SUMMARIZATION_POLICY = (
    "If the query asks for a summary, provide a concise yet comprehensive overview of the main points "
    "from the 'PROVIDED CONTEXT'. The summary should be neutral, "
    "objective, and reflect the key information accurately. Follow the citation policy "
    "(i.e., no bracketed citations). Focus on the core aspects and main themes."
)

