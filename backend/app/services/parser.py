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

from .state import APP_STATE, EFFECTIVE_MAX_CHUNK_TOKENS, PRIMARY_CHUNK_SIZE_TOKENS, PRIMARY_CHUNK_OVERLAP_TOKENS, SEPARATORS_HIERARCHICAL, ATOMIC_BLOCK_NO_SPLIT_THRESHOLD, VISION_MODEL_ID_CONFIG, STAGED_UPLOADS_DIR, IMAGE_OCR_PROMPT_CONFIG, IMAGE_DESCRIPTION_PROMPT_CONFIG
from .llm import initialize_hf_client_from_parser
def count_tokens(text: str) -> int:
    if APP_STATE.get("tokenizer"):
        try:
            return len(APP_STATE["tokenizer"].encode(text, disallowed_special=()))
        except Exception as e:
            logger.warning(f"Tiktoken encode error for text '{text[:30]}...': {e}. Using char count.");
            return len(text)
    return len(text)

def image_to_base64_data_uri(pil_image: Image.Image) -> str:
    buffered = io.BytesIO()
    img_format = pil_image.format if pil_image.format else 'PNG'
    try:
        pil_image.save(buffered, format=img_format)
    except Exception as e:
        logger.warning(f"Warning: Could not save image in format {img_format}, falling back to PNG. Error: {e}")
        img_format = 'PNG'
        pil_image.save(buffered, format=img_format)
    encoded_bytes = base64.b64encode(buffered.getvalue())
    encoded_string = encoded_bytes.decode('utf-8')
    mime_type = Image.MIME.get(img_format.upper(), 'image/png')
    return f"data:{mime_type};base64,{encoded_string}"

def _process_image_with_vision_model(pil_image: Image.Image, prompt_text: str) -> str:
    if not APP_STATE.get("vision_client_initialized") or not APP_STATE.get(
        "hf_vision_client"
    ):
        logger.error("Vision model client not initialized. Cannot process image.")
        return "Error: Vision model client not initialized."
    if VISION_MODEL_ID_CONFIG == "YOUR_NOVITA_SUPPORTED_VISION_MODEL_ID_PLACEHOLDER":
        logger.error(f"Vision model ID is a placeholder: {VISION_MODEL_ID_CONFIG}. Cannot process image.")
        return "Error: Vision model ID is a placeholder."

    base64_image_url = image_to_base64_data_uri(pil_image)
    try:
        completion = APP_STATE["hf_vision_client"].chat.completions.create(
            model=VISION_MODEL_ID_CONFIG,
            messages=[
                {"role": "user", "content": [{"type": "text", "text": prompt_text}, {"type": "image_url", "image_url": {"url": base64_image_url}}]}
            ],
            max_tokens=1500
        )
        if completion.choices and completion.choices[0].message and completion.choices[0].message.content:
            return completion.choices[0].message.content.strip()
        else:
            logger.error(f"Vision model ({VISION_MODEL_ID_CONFIG}) - No content in response. Prompt: {prompt_text[:50]}...")
            return f"Error: No content from vision model {VISION_MODEL_ID_CONFIG}."
    except Exception as e:
        logger.error(f"An unexpected error occurred with the vision model ({VISION_MODEL_ID_CONFIG}): {e}", exc_info=True)
        return f"Error processing image with vision model {VISION_MODEL_ID_CONFIG}: {str(e)}"

def sanitize_chromadb_collection_name(name: str) -> str:
    name = str(name)
    name = re.sub(r'[ \t\n\r\f\v.,;:!?"\'`()\[\]{}<>|/\\]+', '_', name)
    name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
    name = re.sub(r'^_+|-+$', '', name)
    name = re.sub(r'^-+|_+$', '', name)
    if name and not name[0].isalnum():
        name = 'c_' + name
    if name and not name[-1].isalnum():
        name = name + '_c'
    if len(name) < 3:
        name = name + '___'
        name = name[:3]
    if len(name) > 63:
        name = name[:63]
    if name and not name[0].isalnum(): name = 'c' + name[1:]
    if name and len(name) > 1 and not name[-1].isalnum(): name = name[:-1] + 'c'
    elif name and len(name) == 1 and not name[0].isalnum(): name = 'cc'
    if not name or len(name) < 3:
        name = f"coll_{uuid.uuid4().hex[:8]}"
    return name.lower()

def get_font_properties(span_dict: Dict) -> Dict:
    return {
        "size": span_dict.get("size", 0.0),
        "font": span_dict.get("font", "UnknownFont"),
        "color": span_dict.get("color", 0),
        "flags": span_dict.get("flags", 0),
        "origin_x": span_dict.get("bbox", [0, 0, 0, 0])[0],
        "origin_y": span_dict.get("bbox", [0, 0, 0, 0])[1],
    }

def is_likely_header_or_footer(
    block_text: str,
    page_rect: fitz.Rect,
    block_bbox: fitz.Rect,
    page_number: int,
    num_pages: int,
) -> bool:
    block_content = block_text.strip()
    if not block_content or len(block_content) > 150:
        return False
    page_height = page_rect.height
    is_top_zone = block_bbox.y1 < page_rect.y0 + 0.12 * page_height
    is_bottom_zone = block_bbox.y0 > page_rect.y1 - 0.12 * page_height
    if not (is_top_zone or is_bottom_zone):
        return False
    page_num_str = str(page_number)
    num_pages_str = str(num_pages)
    patterns = [
        r"^(Page\s*)?" + re.escape(page_num_str) + r"(\s*(of|-|/)\s*" + re.escape(num_pages_str) + r")?([\s.]*)$",
        r"^(\[?" + re.escape(page_num_str) + r"\]?)$",
        r"^\s*-\s*\d+\s*-\s*$",
        r"^\s*" + re.escape(page_num_str) + r"\s*$",
    ]
    for pattern in patterns:
        if re.fullmatch(pattern, block_content, re.IGNORECASE):
            return True
    if len(block_content.split()) < 7 and len(block_content) < 70:
        if not re.search(r"[.!?]$", block_content):
            if block_content.isupper() or block_content.istitle():
                return True
            if len(block_content) < 10 and len(set(block_content.replace(" ", ""))) < 4:
                return True
    return False

def parse_pdf_content_worker(pdf_path: str, original_filename: str, original_document_type: str, config_dict: dict) -> list:
    logger.info(f"  Worker: Parsing PDF content from '{os.path.basename(pdf_path)}' (originally {original_document_type}) with config: {config_dict}")
    all_content_blocks = []
    doc_block_counter = 0

    use_pdfplumber_tables = config_dict.get("use_pdfplumber_tables", True)
    use_pymupdf_text = config_dict.get("use_pymupdf_text", True)
    process_scanned_pages = config_dict.get("process_scanned_pages", False)
    use_vision_for_ocr_flag = config_dict.get("use_vision_for_ocr", False)
    process_structured_images = config_dict.get("process_structured_images", False)
    use_vision_for_description_flag = config_dict.get("use_vision_for_description", False)
    scan_detection_char_threshold = config_dict.get("scan_detection_char_threshold", 100)
    dpi_for_conversion = config_dict.get("dpi_for_conversion", 200)

    tables_by_page = {}
    if use_pdfplumber_tables:
        logger.debug("  Worker: Attempting table extraction with PdfPlumber...")
        try:
            with pdfplumber.open(pdf_path) as pdf_pl:
                for p_idx, page_pl in enumerate(pdf_pl.pages):
                    page_num_human = p_idx + 1
                    raw_tables = page_pl.find_tables()
                    extracted_tables_data = []
                    if raw_tables:
                        logger.debug(f"    P{page_num_human}: Found {len(raw_tables)} potential tables with PdfPlumber.")
                        for tbl_idx, raw_table in enumerate(raw_tables):
                            md_table = f"[Table {tbl_idx+1} on Page {page_num_human}]\n"
                            data = raw_table.extract()
                            if data:
                                try:
                                    header = data[0]
                                    if header and all(isinstance(c, (str, type(None))) for c in header):
                                        md_table += "| " + " | ".join(str(c).strip().replace("\n", " ") if c is not None else "" for c in header) + " |\n"
                                        md_table += "| " + " | ".join("---" for _ in header) + " |\n"
                                        for row in data[1:]:
                                            if row and all(isinstance(c, (str, type(None))) for c in row):
                                                md_table += f"| {' | '.join(str(c).strip().replace(chr(10),' ') if c is not None else '' for c in row)} |\n"
                                    else:
                                        for row_idx, row in enumerate(data):
                                            if row and all(isinstance(c, (str, type(None))) for c in row):
                                                md_table += ("| " if row_idx == 0 else "") + " | ".join(str(c).strip().replace("\n", " ") if c is not None else "" for c in row) + (" |\n" if row_idx == 0 and len(data) > 1 else "\n")
                                                if row_idx == 0 and len(data) > 1:
                                                    md_table += "| " + " | ".join("---" for _ in row) + " |\n"
                                except TypeError:
                                    md_table += "(Complex table structure, basic markdown conversion failed)\n"
                                    logger.debug(f"    P{page_num_human} T{tbl_idx+1}: TypeError during MD conversion.")
                            else:
                                md_table += "(Table detected, but no data could be extracted or table is empty)\n"
                            extracted_tables_data.append(
                                {"bbox": raw_table.bbox, "markdown_content": md_table, "order": raw_table.bbox[1]}
                            )
                    if extracted_tables_data:
                        tables_by_page[page_num_human] = sorted(
                            extracted_tables_data, key=lambda t: t["order"]
                        )
        except Exception as e:
            logger.error(
                f"  Worker: Pdfplumber table extraction FAILED for '{os.path.basename(pdf_path)}': {e}",
                exc_info=True,
            )

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.critical(f"  Worker: PyMuPDF open FAILED for '{os.path.basename(pdf_path)}': {e}.")
        return [{"block_id":"error_doc_open", "type":"error", "content":f"PDF open fail: {e}", "page_number":0, "document_type": original_document_type}]

    num_pages = len(doc)
    all_font_sizes_doc = []
    logger.debug(f"  Worker: Document '{os.path.basename(pdf_path)}' has {num_pages} pages. Calculating font statistics...")
    for page_fitz_temp in doc:
        try:
            textpage_temp = page_fitz_temp.get_textpage_ocr(flags=0, full=False)
            blocks_dict_temp = textpage_temp.extractDICT().get("blocks", [])
            for block_dict_temp in blocks_dict_temp:
                if block_dict_temp.get("type") == 0:
                    for line_dict_temp in block_dict_temp.get("lines", []):
                        for span_dict_temp in line_dict_temp.get("spans", []):
                            all_font_sizes_doc.append(span_dict_temp.get("size", 0))
        except Exception as e_fs:
            logger.warning(f"    Font size stats extraction error on page {page_fitz_temp.number + 1}: {e_fs}")

    avg_font_size = np.mean([s for s in all_font_sizes_doc if s > 0]) if any(s > 0 for s in all_font_sizes_doc) else 10.0
    std_font_size = np.std([s for s in all_font_sizes_doc if s > 0]) if any(s > 0 for s in all_font_sizes_doc) and len(set(s for s in all_font_sizes_doc if s > 0)) > 1 else 2.0
    if std_font_size < 1.5:
        std_font_size = 1.5
    logger.info(f"  Doc stats: Pages:{num_pages}, AvgFont:{avg_font_size:.1f}, StdFont:{std_font_size:.1f}")

    for page_idx, page_fitz in enumerate(doc):
        page_num_human = page_idx + 1
        logger.debug(f"  Worker: Processing Page {page_num_human}/{num_pages}")
        page_content_elements = []
        current_page_table_bboxes = [
            tuple(t["bbox"]) for t in tables_by_page.get(page_num_human, [])
        ]

        def check_overlap_with_tables(b_bbox_coords, t_bboxes_coords_list, threshold=0.3):
            b_x0,b_y0,b_x1,b_y1 = b_bbox_coords
            b_area=(b_x1-b_x0)*(b_y1-b_y0)
            if b_area == 0: return False
            for t_coords in t_bboxes_coords_list:
                t_x0,t_y0,t_x1,t_y1 = t_coords
                ix0,iy0 = max(b_x0,t_x0), max(b_y0,t_y0)
                ix1,iy1 = min(b_x1,t_x1), min(b_y1,t_y1)
                iarea = max(0,ix1-ix0) * max(0,iy1-iy0)
                if (iarea/b_area) > threshold: return True
            return False

        if use_pymupdf_text:
            try:
                textpage_flags = (
                    fitz.TEXTFLAGS_SEARCH | fitz.TEXTFLAGS_PRESERVE_LIGATURES
                    | fitz.TEXTFLAGS_PRESERVE_IMAGES | fitz.TEXTFLAGS_PRESERVE_WHITESPACE
                )
            except AttributeError:
                textpage_flags = fitz.TEXTFLAGS_SEARCH
                logger.debug(f"    P{page_num_human}: Older PyMuPDF version, using basic text flags.")

            try:
                textpage = page_fitz.get_textpage_ocr(flags=textpage_flags, full=False)
                page_dict = textpage.extractDICT()

                for block_dict in page_dict.get("blocks", []):
                    if block_dict.get("type") == 0:
                        block_text_content, span_font_props_list = "", []
                        for line_dict in block_dict.get("lines", []):
                            line_text_parts = []
                            for span_dict_val in line_dict.get("spans", []):
                                line_text_parts.append(span_dict_val["text"])
                                span_font_props_list.append(get_font_properties(span_dict_val))
                            block_text_content += " ".join(line_text_parts).strip() + "\n"

                        block_text_content = re.sub(r'\s*\n\s*', '\n', block_text_content).strip()
                        block_text_content = re.sub(r' +', ' ', block_text_content)
                        block_bbox_fitz = fitz.Rect(block_dict["bbox"])

                        if not block_text_content or check_overlap_with_tables(tuple(block_bbox_fitz), current_page_table_bboxes):
                            continue

                        current_block_avg_font_size = np.mean([s['size'] for s in span_font_props_list if s['size'] > 0]) if any(s['size'] > 0 for s in span_font_props_list) else avg_font_size
                        is_bold = any(s['flags'] & (1 << 4) for s in span_font_props_list)
                        num_words_first_line = len(block_text_content.split('\n')[0].split())

                        block_sem_type, is_heading_candidate = "text_paragraph", False
                        if is_likely_header_or_footer(block_text_content, page_fitz.rect, block_bbox_fitz, page_num_human, num_pages):
                            block_sem_type = "noise_header_footer"
                        elif len(block_text_content) <= 6 and not re.search(r'[a-zA-Z]{2,}', block_text_content) and \
                             not (current_block_avg_font_size > avg_font_size + 0.8 * std_font_size or is_bold):
                            block_sem_type = "noise_short_irrelevant"
                        else:
                            if page_idx == 0 and current_block_avg_font_size >= avg_font_size + 1.8 * std_font_size and \
                               num_words_first_line < 18 and block_bbox_fitz.y0 < page_fitz.rect.height * 0.3:
                                block_sem_type, is_heading_candidate = "title_document", True
                            elif current_block_avg_font_size >= avg_font_size + 1.4 * std_font_size and \
                                 (is_bold or num_words_first_line < 20 or (page_idx <=1 and num_words_first_line < 28)):
                                block_sem_type, is_heading_candidate = "h1_heading", True
                            elif current_block_avg_font_size >= avg_font_size + 0.7 * std_font_size and \
                                 (is_bold or num_words_first_line < 25):
                                block_sem_type, is_heading_candidate = "h2_heading", True
                            elif (current_block_avg_font_size >= avg_font_size + 0.3 * std_font_size and \
                                  is_bold and num_words_first_line < 30 and not block_text_content.endswith('.')):
                                block_sem_type, is_heading_candidate = "h3_heading", True

                        if is_heading_candidate:
                            logger.trace(f"    P{page_num_human}: Found {block_sem_type} (F:{current_block_avg_font_size:.1f},B:{is_bold}): '{block_text_content[:40]}...'")
                        page_content_elements.append({
                            "type": block_sem_type, "content": block_text_content, "bbox": tuple(block_bbox_fitz),
                            "order": block_bbox_fitz.y0, "is_semantic_heading": is_heading_candidate,
                            "font_size": current_block_avg_font_size, "is_bold": is_bold, "document_type": original_document_type
                        })
            except Exception as e_pymupdf_txt:
                logger.error(f"  Worker: PyMuPDF text extraction error on P{page_num_human}: {e_pymupdf_txt}", exc_info=True)

        for tbl_data in tables_by_page.get(page_num_human, []):
            page_content_elements.append({
                "type": "table_markdown", "content": tbl_data["markdown_content"],
                "bbox": tbl_data["bbox"], "order": tbl_data["order"],
                "is_semantic_heading": False, "font_size": avg_font_size, "is_bold": False, "document_type": original_document_type
            })

        initial_digital_text_len = sum(len(el["content"]) for el in page_content_elements if el["type"] not in ["noise_header_footer", "noise_short_irrelevant"])
        page_might_be_scan = initial_digital_text_len < scan_detection_char_threshold

        structured_images_on_page_meta = []
        if process_scanned_pages or process_structured_images:
            try:
                structured_images_on_page_meta = page_fitz.get_images(full=True)
            except Exception as e:
                logger.warning(f"  Worker: PyMuPDF get_images failed P{page_num_human}: {e}")

        if process_scanned_pages and page_might_be_scan and not structured_images_on_page_meta:
            logger.info(f"  P{page_num_human}: Low digital text ({initial_digital_text_len} chars), no structured images. Candidate for full page OCR.")
            try:
                pil_page_img_list = convert_from_path(
                    pdf_path, dpi=dpi_for_conversion, first_page=page_num_human,
                    last_page=page_num_human, fmt='jpeg', thread_count=1
                )
                if not pil_page_img_list:
                    logger.warning(f"    P{page_num_human}: pdf2image returned no image for full page OCR.")
                    continue
                pil_page_img = pil_page_img_list[0]
                fp_bbox, fp_ocr_text, fp_ocr_type_detail = tuple(page_fitz.rect), "", ""

                if use_vision_for_ocr_flag and APP_STATE.get("hf_vision_client"):
                    logger.debug(f"    P{page_num_human}: Attempting Vision OCR (full page).")
                    fp_ocr_text = _process_image_with_vision_model(pil_page_img, IMAGE_OCR_PROMPT_CONFIG)
                    fp_ocr_type_detail = "vision_ocr (full_page)"

                if not fp_ocr_text.strip() or "Error:" in fp_ocr_text or "No text found" in fp_ocr_text.lower():
                    logger.debug(f"    P{page_num_human}: Vision OCR failed or no text. Fallback/Attempt Tesseract (full page). Vision out: '{fp_ocr_text[:50]}...'")
                    if not use_vision_for_ocr_flag or ("Error:" in fp_ocr_text or "No text found" in fp_ocr_text.lower()):
                        fp_ocr_text = pytesseract.image_to_string(pil_page_img)
                        fp_ocr_type_detail = "tesseract_ocr (full_page)"

                if fp_ocr_text and fp_ocr_text.strip() and "Error:" not in fp_ocr_text and "No text found" not in fp_ocr_text.lower():
                    page_content_elements = [el for el in page_content_elements if el["type"] == "table_markdown"]
                    page_content_elements.append({
                        "type": "full_page_ocr_text", "content": fp_ocr_text.strip(), "bbox": fp_bbox,
                        "order": 0, "is_semantic_heading": False, "font_size": avg_font_size,
                        "is_bold": False, "ocr_source": fp_ocr_type_detail, "document_type": original_document_type
                    })
                    logger.info(f"    P{page_num_human}: Full scan OCR successful via {fp_ocr_type_detail}. Text length: {len(fp_ocr_text)}")
                else:
                    logger.warning(f"    P{page_num_human}: Full page OCR attempt ({fp_ocr_type_detail or 'N/A'}) yielded no usable text.")
            except Exception as e_fp_ocr:
                logger.error(f"    Error during P{page_num_human} full page OCR processing: {e_fp_ocr}", exc_info=True)

        if process_structured_images and structured_images_on_page_meta:
            logger.debug(f"  P{page_num_human}: Processing {len(structured_images_on_page_meta)} structured image regions.")
            for img_idx, img_meta_item in enumerate(structured_images_on_page_meta):
                xref = img_meta_item[0]
                try:
                    base_image = doc.extract_image(xref)
                    if not base_image or "image" not in base_image:
                        logger.warning(f"    P{page_num_human} ImgX{xref}: Could not extract base image data.")
                        continue

                    pil_img = Image.open(io.BytesIO(base_image["image"]))
                    img_placements_rects = page_fitz.get_image_rects(xref)

                    if not img_placements_rects:
                         if len(structured_images_on_page_meta) == 1 and page_might_be_scan:
                             img_placements_rects = [page_fitz.rect]
                             logger.debug("    Single image on scan-like page, using full page rect.")
                         else:
                             logger.warning(f"    P{page_num_human} ImgX{xref}: No placement rectangles found. Skipping image.")
                             continue

                    for rect_idx, fitz_rect_obj in enumerate(img_placements_rects):
                        img_bbox_coords = tuple(fitz_rect_obj)
                        img_filename_ref = f"p{page_num_human}_img{img_idx}_xref{xref}_r{rect_idx}.{base_image.get('ext','png')}"
                        if check_overlap_with_tables(img_bbox_coords, current_page_table_bboxes, 0.7):
                            logger.trace(f"    Skipping image XREF {xref} Rect {rect_idx} due to high table overlap.")
                            continue

                        ocr_from_img_content, desc_from_img_content, vision_ocr_attempted_for_img = "", "", False
                        if use_vision_for_ocr_flag and APP_STATE.get("hf_vision_client"):
                            vision_ocr_attempted_for_img = True
                            ocr_from_img_content = _process_image_with_vision_model(pil_img, IMAGE_OCR_PROMPT_CONFIG)
                            if ocr_from_img_content and "Error:" not in ocr_from_img_content and "No text found" not in ocr_from_img_content.lower():
                                page_content_elements.append({
                                    "type": "image_ocr_text", "content": ocr_from_img_content.strip(),
                                    "bbox": img_bbox_coords, "order": img_bbox_coords[1],
                                    "source_image_filename": img_filename_ref, "is_semantic_heading": False,
                                    "font_size": avg_font_size, "is_bold": False, "document_type": original_document_type
                                })
                            elif "No text found" in ocr_from_img_content.lower(): ocr_from_img_content = ""
                            elif "Error:" in ocr_from_img_content:
                                logger.warning(f"      P{page_num_human},ImgX{xref}R{rect_idx} Vision OCR Error: {ocr_from_img_content}")
                                ocr_from_img_content = ""

                        if process_structured_images and use_vision_for_description_flag and APP_STATE.get("hf_vision_client"):
                            should_describe_img = not (
                                vision_ocr_attempted_for_img and len(ocr_from_img_content) > 75 and
                                not any(k in ocr_from_img_content.lower() for k in ["chart","diagram","graph","figure","table"])
                            )
                            if should_describe_img:
                                desc_from_img_content = _process_image_with_vision_model(pil_img, IMAGE_DESCRIPTION_PROMPT_CONFIG)
                                if desc_from_img_content and "Error:" not in desc_from_img_content and desc_from_img_content.strip():
                                    if not(ocr_from_img_content and desc_from_img_content.strip().lower() == ocr_from_img_content.strip().lower()):
                                        page_content_elements.append({
                                            "type": "image_description", "content": desc_from_img_content.strip(),
                                            "bbox": img_bbox_coords, "order": img_bbox_coords[1] + 0.01,
                                            "source_image_filename": img_filename_ref, "is_semantic_heading": False,
                                            "font_size": avg_font_size, "is_bold": False, "document_type": original_document_type
                                        })
                except UnidentifiedImageError:
                    logger.warning(f"  P{page_num_human}, ImgX{xref}: PIL UnidentifiedImageError. Skipping this image resource.")
                except Exception as e_img_proc:
                    logger.error(f"  Error processing structured image XREF {xref} on P{page_num_human}: {e_img_proc}", exc_info=True)


        page_content_elements.sort(key=lambda item: item.get("order", float('inf')))
        for el_data in page_content_elements:
            content, el_type_str = el_data.get("content", "").strip(), el_data.get("type", "")
            if "noise" in el_type_str or content.lower() == "no text found":
                logger.trace(f"    P{page_num_human}: Final skip of noise block type '{el_type_str}' or 'No text found'.")
                continue
            if content:
                doc_block_counter += 1
                block_to_add = {k: v for k, v in el_data.items() if k not in ["order"]}
                block_to_add.update({"block_id": f"doc_block_{doc_block_counter}", "page_number": page_num_human})
                block_to_add.setdefault("is_semantic_heading", False)
                block_to_add.setdefault("font_size", avg_font_size)
                block_to_add.setdefault("is_bold", False)
                block_to_add.setdefault("document_type", original_document_type)
                all_content_blocks.append(block_to_add)
    try:
        doc.close()
    except Exception as e:
        logger.warning(f"  Worker: Error closing PDF '{os.path.basename(pdf_path)}': {e}")

    if not all_content_blocks:
        all_content_blocks.append({
            "block_id": "fallback_empty_doc", "type": "info",
            "content": f"No content could be extracted from this {original_document_type} file after PDF conversion. It might be empty, purely graphical without OCR, or a protected file.",
            "page_number": 0, "document_type": original_document_type
        })
    logger.info(
        f"  Worker: Finished parsing '{os.path.basename(pdf_path)}' (originally {original_document_type}). Total blocks extracted: {len(all_content_blocks)}"
    )
    return all_content_blocks

def convert_to_pdf(input_path: str, temp_dir: str) -> Optional[Dict]:
    """
    Converts various document types (DOCX, XLSX, PPTX, Image) to PDF using unoconv or Pillow.
    Returns a dictionary with {pdf_path, original_filename, original_extension, original_document_type}.
    """
    original_filename = os.path.basename(input_path)

def convert_to_pdf(input_path: str, temp_dir: str) -> Optional[Dict]:
    """
    Converts various document types (DOCX, XLSX, PPTX, Image) to PDF using unoconv or Pillow.
    Returns a dictionary with {pdf_path, original_filename, original_extension, original_document_type}.
    """
    original_filename = os.path.basename(input_path)
    file_extension = os.path.splitext(original_filename)[1].lower()
    base_name_no_ext = os.path.splitext(original_filename)[0]
    output_pdf_path = os.path.join(temp_dir, f"{base_name_no_ext}_{uuid.uuid4().hex[:6]}.pdf")

    original_doc_type = "unknown"
    if file_extension == ".pdf":
        original_doc_type = "pdf"
    elif file_extension == ".docx":
        original_doc_type = "docx"
    elif file_extension == ".xlsx":
        original_doc_type = "xlsx"
    elif file_extension == ".pptx":
        original_doc_type = "pptx"
    elif file_extension in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff"]:
        original_doc_type = "image"
    elif file_extension == ".xls": # Old Excel format, map to xlsx for parsing
        original_doc_type = "xlsx" # Treat as xlsx for parsing context after conversion
    else:
        logger.error(f"Conversion failed: Unsupported file type for conversion: {file_extension} for '{original_filename}'")
        return {"pdf_path": None, "original_filename": original_filename, "original_extension": file_extension, "original_document_type": "unsupported", "error": f"Unsupported file type: {file_extension}"}

    if file_extension == ".pdf":
        logger.info(f"  File '{original_filename}' is already a PDF. Skipping conversion.")
        return {
            "pdf_path": input_path,
            "original_filename": original_filename,
            "original_extension": file_extension,
            "original_document_type": original_doc_type
        }
    elif original_doc_type == "image":
        try:
            img = Image.open(input_path)
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(output_pdf_path, "PDF")
            logger.info(f"  Converted image '{original_filename}' to PDF at '{output_pdf_path}'.")
            return {
                "pdf_path": output_pdf_path,
                "original_filename": original_filename,
                "original_extension": file_extension,
                "original_document_type": original_doc_type
            }
        except Exception as e:
            logger.error(f"  Failed to convert image '{original_filename}' to PDF using Pillow: {e}", exc_info=True)
            return None
    else: # Use unoconv for DOCX, XLSX, PPTX, and now .xls
        command = f"unoconv -f pdf -o {output_pdf_path} {input_path}"
        logger.info(f"  Attempting to convert '{original_filename}' to PDF using unoconv: {command}")
        try:
            result = os.system(command)
            if result == 0 and os.path.exists(output_pdf_path) and os.path.getsize(output_pdf_path) > 0:
                logger.success(f"  Successfully converted '{original_filename}' to PDF at '{output_pdf_path}'.")
                return {
                    "pdf_path": output_pdf_path,
                    "original_filename": original_filename,
                    "original_extension": file_extension,
                    "original_document_type": original_doc_type
                }
            else:
                logger.error(f"  Unoconv failed or produced empty PDF for '{original_filename}'. Result code: {result}. PDF exists: {os.path.exists(output_pdf_path)}. Output file size: {os.path.getsize(output_pdf_path) if os.path.exists(output_pdf_path) else 'N/A'}")
                return None
        except Exception as e:
            logger.error(f"  Error during unoconv conversion of '{original_filename}': {e}", exc_info=True)
            return None

def parse_document_via_profile(file_path: str, profile_name: str = "default_fallback") -> list:
    logger.info(f"Initiating parsing process for document '{os.path.basename(file_path)}' with profile: '{profile_name}'")

    current_config = {
        "use_pdfplumber_tables": True, "use_pymupdf_text": True, "process_scanned_pages": False,
        "process_structured_images": False, "use_vision_for_ocr": False, "use_vision_for_description": False,
        "scan_detection_char_threshold": 120, "dpi_for_conversion": 220
    }
    if profile_name == "fastest":
        current_config.update({"process_scanned_pages": False, "process_structured_images": False, "use_vision_for_ocr": False, "use_vision_for_description": False})
    elif profile_name == "digital_plus_ocr":
        current_config.update({"process_scanned_pages": True, "use_vision_for_ocr": False, "process_structured_images": True, "use_vision_for_description": False, "scan_detection_char_threshold": 150, "dpi_for_conversion": 200})
    elif profile_name == "comprehensive_vision":
        current_config.update({"process_scanned_pages": True, "use_vision_for_ocr": True, "process_structured_images": True, "use_vision_for_description": True, "scan_detection_char_threshold": 100, "dpi_for_conversion": 250})
    elif profile_name == "default_fallback":
        logger.warning(f"Using 'default_fallback' profile for '{os.path.basename(file_path)}'.")
        current_config.update({"process_scanned_pages": True, "use_vision_for_ocr": True, "process_structured_images": True, "use_vision_for_description": True})
    else:
        logger.error(f"Unexpected profile '{profile_name}'. Using minimal config.")
        current_config = {"use_pdfplumber_tables": True, "use_pymupdf_text": True}

    if not APP_STATE.get("vision_client_initialized", False):
        if current_config.get("use_vision_for_ocr"):
            logger.info(f"Profile '{profile_name}': Vision OCR globally disabled (client not ready).")
            current_config["use_vision_for_ocr"] = False
        if current_config.get("use_vision_for_description"):
            logger.info(f"Profile '{profile_name}': Vision Desc globally disabled (client not ready).")
            current_config["use_vision_for_description"] = False

    logger.info(f"Final config for parsing '{os.path.basename(file_path)}' (profile '{profile_name}'): {current_config}")
    start_time = time.time()

    converted_info = convert_to_pdf(file_path, STAGED_UPLOADS_DIR) # Use staged uploads dir for temp PDFs
    if not converted_info or not converted_info["pdf_path"]:
        error_msg = converted_info.get("error", "Unknown conversion error.")
        logger.error(f"Document conversion failed for '{os.path.basename(file_path)}': {error_msg}")
        return [{"block_id":"conversion_error", "type":"error", "content":f"File conversion to PDF failed: {error_msg}", "page_number":0, "document_type": converted_info.get("original_document_type", "unsupported")}]

    pdf_to_parse_path = converted_info["pdf_path"]
    original_filename = converted_info["original_filename"]
    original_document_type = converted_info["original_document_type"]

    try:
        # Now call the single PDF content parser
        parsed_data = parse_pdf_content_worker(pdf_to_parse_path, original_filename, original_document_type, current_config)

        # Ensure that blocks from non-PDFs have their `document_type` consistently set
        for block in parsed_data:
            block["document_type"] = original_document_type

        logger.success(f"Profile '{profile_name}' parsing for '{original_filename}' (converted from {original_document_type}) in {time.time()-start_time:.2f}s. Blocks: {len(parsed_data)}.")
        return parsed_data
    except Exception as e:
        logger.error(f"Error during PDF content parsing of converted file '{pdf_to_parse_path}' (originally {original_document_type}): {e}", exc_info=True)
        return [{"block_id":"parsing_error", "type":"error", "content":f"Error parsing PDF content after conversion: {e}", "page_number":0, "document_type": original_document_type}]
    finally:
        # Clean up the temporary PDF file if it was created
        if pdf_to_parse_path != file_path: # Only remove if it's a new temp file, not the original if it was already a PDF
            try:
                os.remove(pdf_to_parse_path)
                logger.info(f"  Removed temporary PDF file: '{pdf_to_parse_path}'.")
            except Exception as e:
                logger.warning(f"  Could not remove temporary PDF file '{pdf_to_parse_path}': {e}")

def _prepend_context_to_chunk(original_chunk_text: str, block_metadata: dict) -> str:
    """
    Dynamically prepends contextual information to a chunk based on its type and metadata.
    Refined to use the actual `document_type` metadata.
    """
    orig_filename = APP_STATE.get("original_doc_filename_for_chunking_context", "this document")
    block_type = block_metadata.get("type", "text_paragraph")
    page_num = block_metadata.get("page_number", "N/A")
    doc_type = block_metadata.get("document_type", "document") # Crucial: Get original document type
    font_size = block_metadata.get("font_size", 0) # Only relevant for PDFs originally
    is_bold_str = " (Bold)" if block_metadata.get("is_bold", False) else "" # Only relevant for PDFs originally
    source_img_filename = block_metadata.get("source_image_filename")
    ocr_source = block_metadata.get("ocr_source")

    prefix = ""

    # General document type indicator for clarity in context
    doc_type_label = {
        "pdf": "PDF document",
        "docx": "Word document",
        "xlsx": "Excel document",
        "pptx": "PowerPoint presentation",
        "image": "Image file"
    }.get(doc_type, "document")

    # Specific prefixes for different block types
    if block_type == "table_markdown":
        prefix = f"Context: Data table from {doc_type_label} '{orig_filename}', section/page {page_num}.\nContent:\n"
    elif block_type == "image_ocr_text":
        img_info = f"image '{source_img_filename}'" if source_img_filename else "an image"
        prefix = f"Context: OCR transcription from {img_info} on page {page_num} of {doc_type_label} '{orig_filename}'.\nContent:\n"
    elif block_type == "image_description":
        img_info = f"image '{source_img_filename}'" if source_img_filename else "an image"
        prefix = f"Context: Description of {img_info} on page {page_num} of {doc_type_label} '{orig_filename}'.\nContent:\n"
    elif block_type == "full_page_ocr_text":
        ocr_source_info = f"via {ocr_source}" if ocr_source else ""
        prefix = f"Context: Full page OCR text from scanned page {page_num} of {doc_type_label} '{orig_filename}' {ocr_source_info}.\nContent:\n"
    elif block_type == "title_document":
        prefix = f"Context: Document Title from {doc_type_label} '{orig_filename}'(P{page_num},F{font_size:.0f}{is_bold_str}): \n"
    elif block_type in ["h1_heading", "h2_heading", "h3_heading", "heading_1", "heading_2", "heading_3", "h_candidate_uppercase", "pptx_slide_text"]:
        level_map = {
            "h1_heading": "H1", "h2_heading": "H2", "h3_heading": "H3",
            "heading_1": "Heading 1", "heading_2": "Heading 2", "heading_3": "Heading 3",
            "h_candidate_uppercase": "Potential Heading",
            "pptx_slide_text": "PowerPoint Slide Content" # Special case for PPTX converted content
        }
        level_str = level_map.get(block_type, "Heading")
        prefix = f"Context: {level_str} from {doc_type_label} '{orig_filename}', section/page {page_num} (F{font_size:.0f}{is_bold_str}).\nContent:\n"
    elif block_type == "excel_sheet_data": # For sheets that might have been detected as whole text blocks in PDF
        prefix = f"Context: Data from Excel sheet of {doc_type_label} '{orig_filename}', sheet/page {page_num}.\nContent:\n"
    elif block_type == "docx_paragraph": # For paragraphs from Word docs
        prefix = f"Context: Paragraph from Word document '{orig_filename}', page {page_num}.\nContent:\n"
    else: # Default for generic text paragraphs
        # Heuristic for detecting potential sub-headings within generic text blocks
        lines = original_chunk_text.split('\n', 1)
        first_line = lines[0].strip()
        # Check if first line is short, few words, not ending in punctuation (common for headings)
        if (1 < len(first_line.split()) < 9 and
            count_tokens(first_line) < 40 and
            not first_line.endswith(('.', '?', '!')) and
            (first_line.isupper() or first_line.istitle() or is_bold_str)):
            prefix = f"Context: From {doc_type_label} '{orig_filename}', section/page {page_num}, likely section titled '{first_line}'.\nContent:\n"
        else:
            prefix = f"Context: Text from {doc_type_label} '{orig_filename}', section/page {page_num}.\nContent:\n"

    return prefix + original_chunk_text

def _chunk_parsed_blocks(
    parsed_blocks: List[Dict], collection_name_as_doc_id: str, original_filename_for_meta: str
) -> List[Dict]:
    all_final_chunks = []
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=PRIMARY_CHUNK_SIZE_TOKENS,
        chunk_overlap=PRIMARY_CHUNK_OVERLAP_TOKENS,
        length_function=count_tokens,
        separators=SEPARATORS_HIERARCHICAL,
        keep_separator=False,
    )
    for block_idx, block in enumerate(parsed_blocks):
        original_content = block.get("content", "").strip()
        block_type = block.get("type", "unknown")
        if not original_content or "noise" in block_type or block_type == "error":
            continue

        current_block_metadata = {k:v for k,v in block.items() if k != "content"}
        current_block_metadata.update({"doc_id": collection_name_as_doc_id, "original_filename": original_filename_for_meta})
        current_block_metadata.pop("content", None)

        APP_STATE["original_doc_filename_for_chunking_context"] = original_filename_for_meta
        temp_prefixed_content = _prepend_context_to_chunk(original_content, block)
        APP_STATE["original_doc_filename_for_chunking_context"] = None

        prefixed_token_count = count_tokens(temp_prefixed_content)
        original_token_count = count_tokens(original_content)

        should_split = False
        if prefixed_token_count > EFFECTIVE_MAX_CHUNK_TOKENS:
            logger.warning(f"Block {block.get('block_id', f'b{block_idx}')} (pg:{block.get('page_number')}, type:{block_type}) prefixed form ({prefixed_token_count} tokens) exceeds max {EFFECTIVE_MAX_CHUNK_TOKENS}. Will be split.")
            should_split = True
        elif block_type in ["text_paragraph", "full_page_ocr_text", "docx_paragraph", "excel_sheet_data", "pptx_slide_text", "image_ocr_text", "image_description", "table_markdown"] and original_token_count > PRIMARY_CHUNK_SIZE_TOKENS: # Added table_markdown to types that can be split if too large
            should_split = True
        elif block_type not in ["text_paragraph", "full_page_ocr_text", "docx_paragraph", "excel_sheet_data", "pptx_slide_text", "image_ocr_text", "image_description", "table_markdown"] and original_token_count > ATOMIC_BLOCK_NO_SPLIT_THRESHOLD:
             pass

        if not should_split:
            base_chunk_id = f"{block.get('block_id', f'b{block_idx}')}_chunk0"
            chunk_id = f"{collection_name_as_doc_id}_{base_chunk_id}"
            final_meta = {**current_block_metadata, "chunk_id": chunk_id, "original_block_id": block.get('block_id')}
            all_final_chunks.append({
                "text_content_for_embedding": temp_prefixed_content,
                "original_chunk_text": original_content,
                "metadata": final_meta
            })
        else:
            sub_texts = text_splitter.split_text(original_content)
            logger.debug(f"  Splitting block {block.get('block_id')} ({block_type}, pg {block.get('page_number')}) into {len(sub_texts)} sub-chunks.")
            for i, sub_text_content in enumerate(sub_texts):
                sub_text_content = sub_text_content.strip()
                if not sub_text_content: continue

                APP_STATE["original_doc_filename_for_chunking_context"] = original_filename_for_meta
                final_sub_chunk_for_embedding = _prepend_context_to_chunk(sub_text_content, block)
                APP_STATE["original_doc_filename_for_chunking_context"] = None

                final_sub_chunk_token_count = count_tokens(final_sub_chunk_for_embedding)
                if final_sub_chunk_token_count > EFFECTIVE_MAX_CHUNK_TOKENS:
                    logger.warning(f"    Sub-chunk {i} of {block.get('block_id')} (pg:{block.get('page_number')}) still too large ({final_sub_chunk_token_count} tokens) after splitting. TRUNCATING. Text: '{final_sub_chunk_for_embedding[:100]}...'")
                    tokenizer = APP_STATE.get("tokenizer")
                    if tokenizer:
                        encoded = tokenizer.encode(final_sub_chunk_for_embedding, disallowed_special=())
                        final_sub_chunk_for_embedding = tokenizer.decode(encoded[:EFFECTIVE_MAX_CHUNK_TOKENS])
                    else:
                        final_sub_chunk_for_embedding = final_sub_chunk_for_embedding[:EFFECTIVE_MAX_CHUNK_TOKENS * 4]

                base_chunk_id = f"{block.get('block_id', f'b{block_idx}')}_subchunk{i}"
                chunk_id = f"{collection_name_as_doc_id}_{base_chunk_id}"
                final_meta = {**current_block_metadata, "chunk_id": chunk_id, "original_block_id": block.get('block_id'), "split_index": i}
                all_final_chunks.append({
                    "text_content_for_embedding": final_sub_chunk_for_embedding,
                    "original_chunk_text": sub_text_content,
                    "metadata": final_meta
                })
    logger.info(f"Chunking for '{original_filename_for_meta}': {len(all_final_chunks)} final chunks.")
    return all_final_chunks

