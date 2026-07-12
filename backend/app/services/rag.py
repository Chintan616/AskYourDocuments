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

from .state import APP_STATE, APP_WEB_STATE, AI_NO_ANSWER_POLICY, AI_PERSONA_NAME, AI_ROLE_DESCRIPTION, AI_CORE_DIRECTIVE, AI_ANSWERING_STYLE_REFINED, AI_CONTEXTUAL_PRIORITIZATION_POLICY, AI_CITATION_POLICY_TEXT, AI_SUMMARIZATION_POLICY, AZURE_LLM_MODEL_NAME, GENERATION_MODEL_NAME, AZURE_EMBEDDING_MODEL_NAME, MAX_TOKENS_FOR_DIRECT_LLM_SUMMARIZATION
from .database import get_or_create_collection_cached
from .parser import sanitize_chromadb_collection_name, parse_document_via_profile, _chunk_parsed_blocks, count_tokens
def _embed_chunks(chunks_to_embed: List[Dict], batch_size: int = 16) -> Optional[List[Dict]]:
    if not APP_STATE.get("rag_models_loaded") or not APP_STATE.get("azure_embedding_client"):
        logger.error("Azure Embedding client not ready.")
        return None

    texts = [c["text_content_for_embedding"] for c in chunks_to_embed]
    if not texts:
        logger.warning("No texts to embed.")
        return []

    logger.info(f"Embedding {len(texts)} chunks using Azure OpenAI '{AZURE_EMBEDDING_MODEL_NAME}'...")
    try:
        response = APP_STATE["azure_embedding_client"].embeddings.create(
            input=texts,
            model=AZURE_EMBEDDING_MODEL_NAME
        )
        embeddings_list = []
        for item in response.data:
            embeddings_list.append(item.embedding)

        embeddings_np = np.array(embeddings_list, dtype=np.float32)

        for c, emb in zip(chunks_to_embed, embeddings_np):
            c["embedding_vector"] = emb.tolist()
        logger.success(f"Embedded {len(texts)} chunks using Azure OpenAI.")
        return chunks_to_embed
    except Exception as e:
        logger.error(f"Azure Embedding FAILED: {e}", exc_info=True)
        return None

def _store_chunks_in_chromadb(
    chunks_with_embeddings: List[Dict], collection
) -> int:
    if not collection:
        logger.error("Collection invalid.")
        return 0

    valid_count = 0
    try:
        with collection.conn.cursor() as cur:
            for chunk in chunks_with_embeddings:
                if "embedding_vector" not in chunk or not chunk.get("metadata", {}).get("chunk_id"):
                    continue

                meta = chunk["metadata"]
                chunk_id = meta["chunk_id"]
                emb = chunk["embedding_vector"]
                doc = chunk["original_chunk_text"]

                clean_meta = {}
                for k, v in meta.items():
                    if k == "bbox" and isinstance(v, (list, tuple)):
                        try: clean_meta[k] = json.dumps(v)
                        except TypeError: clean_meta[k] = str(v)
                    elif isinstance(v, (str, int, float, bool)) or v is None:
                        clean_meta[k] = v
                    else:
                        clean_meta[k] = str(v)
                
                cur.execute("""
                    INSERT INTO embeddings (id, collection_name, embedding, document, metadata)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        document = EXCLUDED.document,
                        metadata = EXCLUDED.metadata
                """, (chunk_id, collection.name, emb, doc, json.dumps(clean_meta)))
                valid_count += 1
                
        logger.success(f"Stored {valid_count} chunks. Collection '{collection.name}' total: {collection.count()}.")
        return valid_count
    except Exception as e:
        logger.error(f"Neon upsert FAILED for '{collection.name}': {e}", exc_info=True)
        return 0

def ingest_document_into_knowledge_base(
    parsed_blocks: List[Dict], collection_name: str, original_filename: str,
    target_collection
) -> bool:
    start_time = time.time()
    logger.info(f"Ingesting '{original_filename}' into collection: {collection_name}")

    if not APP_STATE.get("rag_models_loaded") or not target_collection:
        logger.error(
            f"Ingest prereqs FAIL. RAG loaded: {APP_STATE.get('rag_models_loaded')}, "
            f"Collection valid: {target_collection is not None}."
        )
        return False

    chunks_for_embedding = _chunk_parsed_blocks(parsed_blocks, collection_name, original_filename)
    if not chunks_for_embedding:
        logger.error(f"Chunking for '{original_filename}' FAIL.")
        return False

    chunks_with_vectors = _embed_chunks(chunks_for_embedding)
    if not chunks_with_vectors:
        logger.error(f"Embedding for '{original_filename}' FAIL.")
        return False

    num_stored = _store_chunks_in_chromadb(chunks_with_vectors, target_collection)
    success = num_stored > 0

    logger.log(
        "SUCCESS" if success else "ERROR",
        f"Ingest '{original_filename}' ({collection_name}) in {time.time()-start_time:.2f}s. "
        f"Stored: {num_stored}."
    )
    return success

def retrieve_relevant_context(
    query_text: str, target_collection_names: List[str],
    k_initial_retrieval: int = 20, k_final_target: int = 12,
    use_reranking: bool = True
) -> Dict:
    retrieval_start_time = time.time()
    payload = {
        "query": query_text,
        "formatted_context_for_llm": "Error: Retrieval fail.",
        "source_chunks_retrieved": [],
        "retrieval_metadata": {
            "collections_queried": target_collection_names,
            "k_initial": k_initial_retrieval,
            "k_final": k_final_target,
        },
    }

    required_keys = ["rag_models_loaded", "db_initialized", "chroma_client", "azure_embedding_client"]
    if not all(APP_STATE.get(k) for k in required_keys):
        payload["retrieval_metadata"]["error"] = "RAG/DB systems not ready (embeddings client missing)."
        logger.error(payload["retrieval_metadata"]["error"])
        return payload

    try:
        query_response = APP_STATE["azure_embedding_client"].embeddings.create(
            input=[query_text],
            model=AZURE_EMBEDDING_MODEL_NAME
        )
        query_emb = query_response.data[0].embedding
    except Exception as e:
        payload["retrieval_metadata"]["error"] = f"Query embed fail: {e}"
        logger.error(f"Query embed fail: {e}")
        return payload

    candidates = []
    noise_types = ["noise_header_footer", "noise_short_irrelevant", "info"]
    is_about_query = any(p in query_text.lower() for p in ["about this document", "summarize", "overview", "main idea", "tell me about"])
    anchors = []

    for coll_name in target_collection_names:
        coll = get_or_create_collection_cached(coll_name)
        if not coll:
            logger.warning(f"Skip collection '{coll_name}' as it's invalid or couldn't be accessed.")
            continue

        current_collection_candidates_map = {}

        try:
            with coll.conn.cursor() as cur:
                cur.execute("""
                    SELECT id, document, metadata, (embedding <=> %s::vector) AS distance
                    FROM embeddings
                    WHERE collection_name = %s
                      AND NOT (metadata->>'type' IN %s)
                    ORDER BY distance ASC
                    LIMIT %s
                """, (query_emb, coll_name, tuple(noise_types), k_initial_retrieval))
                
                for row in cur.fetchall():
                    candidate_id, doc, meta, distance = row
                    current_collection_candidates_map[candidate_id] = {
                        "id": candidate_id,
                        "text_content": doc,
                        "metadata": meta,
                        "retrieval_score_distance": distance,
                        "source_stage": f"S1_Semantic_{coll_name}"
                    }
        except Exception as e:
            logger.error(f"DB S1 semantic query failed for '{coll_name}': {e}")

        if is_about_query and len(target_collection_names) == 1:
            try:
                with coll.conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, document, metadata, (embedding <=> %s::vector) AS distance
                        FROM embeddings
                        WHERE collection_name = %s
                          AND (metadata->>'type' IN %s)
                          AND (metadata->>'page_number')::numeric <= 2
                        ORDER BY distance ASC
                        LIMIT 5
                    """, (query_emb, coll_name, tuple(["title_document", "h1_heading", "pptx_slide_text", "heading_1", "excel_sheet_data", "image_ocr_text", "image_description"])))
                    
                    rows = cur.fetchall()
                    if rows:
                        page_num_key = lambda x: x["metadata"].get("page_number", 999)
                        temp_anchors = []
                        for row in rows:
                            candidate_id, doc, meta, distance = row
                            temp_anchors.append({
                                "id": candidate_id,
                                "text_content": doc,
                                "metadata": meta,
                                "retrieval_score_distance": distance,
                                "source_stage": f"S2_Anchor_{coll_name}"
                            })
                        temp_anchors = sorted(temp_anchors, key=lambda x: (page_num_key(x), x["retrieval_score_distance"]))
                        
                        for anchor_cand in temp_anchors[:min(2, len(temp_anchors))]:
                            current_collection_candidates_map[anchor_cand['id']] = anchor_cand
                            anchors.append(anchor_cand)
            except Exception as e:
                logger.error(f"DB S2 anchor query failed for '{coll_name}': {e}")

        candidates.extend(list(current_collection_candidates_map.values()))

    final_anchors = list({ac['id']: ac for ac in anchors}.values())

    if not candidates:
        payload["formatted_context_for_llm"] = "No relevant context found in the document(s)."
        return payload

    selected_chunks = list(final_anchors)
    general_candidates = [c for c in candidates if c['id'] not in {fa['id'] for fa in final_anchors}]

    slots_left_for_general = k_final_target - len(selected_chunks)

    if slots_left_for_general > 0 and general_candidates:
        if use_reranking and APP_STATE.get("reranker_model"):
            try:
                rerank_pairs = [[query_text, chunk['text_content']] for chunk in general_candidates]

                scores = APP_STATE["reranker_model"].predict(rerank_pairs, show_progress_bar=False)
                for chunk, score in zip(general_candidates, scores):
                    chunk['rerank_score'] = score

                if is_about_query and len(target_collection_names) == 1:
                    for chunk in general_candidates:
                        boost = 0.0
                        meta_type = chunk.get("metadata",{}).get("type")
                        meta_page = chunk.get("metadata",{}).get("page_number", 999)
                        if meta_type == "title_document": boost = 5.0
                        elif meta_type in ["h1_heading", "heading_1", "pptx_slide_text"] and meta_page <= 2: boost = 2.5
                        elif meta_type in ["h2_heading", "heading_2"] and meta_page <= 3: boost = 1.0
                        elif meta_type in ["excel_sheet_data", "image_ocr_text", "image_description"] and meta_page <= 2: boost = 1.5
                        chunk['rerank_score'] = chunk.get('rerank_score', 0) + boost

                general_candidates.sort(key=lambda x: x.get('rerank_score', -float('inf')), reverse=True)
                payload["retrieval_metadata"]["reranked_general_candidates"] = True
            except Exception as e:
                logger.error(f"Reranking FAILED: {e}. Falling back to semantic scores for general candidates.")
                general_candidates.sort(key=lambda x: x.get('retrieval_score_distance', float('inf')))
                payload["retrieval_metadata"]["reranked_general_candidates"] = False
        else:
            general_candidates.sort(key=lambda x: x.get('retrieval_score_distance', float('inf')))
            payload["retrieval_metadata"]["reranked_general_candidates"] = False

        selected_chunks.extend(general_candidates[:slots_left_for_general])

    if not selected_chunks:
        payload["formatted_context_for_llm"] = "No relevant context found after selection and reranking."
        return payload

    def sort_key_final(chunk):
        score = chunk.get('rerank_score', -float('inf')) if use_reranking and APP_STATE.get("reranker_model") else -chunk.get('retrieval_score_distance', float('-inf'))
        page = chunk.get('metadata', {}).get('page_number', 999)
        bbox_str = chunk.get('metadata', {}).get('bbox', None)
        y_order = float('inf')
        if bbox_str:
            try:
                bbox = json.loads(bbox_str) if isinstance(bbox_str, str) else bbox_str
                if isinstance(bbox, (list, tuple)) and len(bbox) >= 2:
                    y_order = bbox[1]
            except:
                pass
        return (score, -page, -y_order)

    selected_chunks.sort(key=sort_key_final, reverse=True)

    formatted_context_parts = []
    for i, chunk in enumerate(selected_chunks):
        meta = chunk['metadata']
        orig_fname = meta.get('original_filename', 'UnknownDocument')
        doc_type = meta.get('document_type', 'document')
        bbox_val = meta.get("bbox", "N/A")

        content_for_llm = chunk.get('text_content', '')

        bbox_str_fmt = "N/A"
        if isinstance(bbox_val, str):
            try:
                parsed_bbox = json.loads(bbox_val)
                bbox_str_fmt = f"({parsed_bbox[0]:.0f},{parsed_bbox[1]:.0f},{parsed_bbox[2]:.0f},{parsed_bbox[3]:.0f})"
            except (json.JSONDecodeError, TypeError, IndexError):
                bbox_str_fmt = bbox_val
        elif isinstance(bbox_val, (list, tuple)) and len(bbox_val) == 4:
            bbox_str_fmt = f"({bbox_val[0]:.0f},{bbox_val[1]:.0f},{bbox_val[2]:.0f},{bbox_val[3]:.0f})"


        header = (
            f"--- Context Source {i+1} (Doc:'{orig_fname}', Type:{doc_type}, SrcStage:{chunk.get('source_stage','N/A')}) ---\n"
            f"Page/Section: {meta.get('page_number','?')}, Type: {meta.get('type','?')}, ChunkID: {meta.get('chunk_id','N/A')}\n"
            f"Font Size: {meta.get('font_size',0):.0f}, Bold: {meta.get('is_bold',False)}, Semantic Heading: {meta.get('is_semantic_heading',False)}\n"
            f"BBox: {bbox_str_fmt}, Distance: {chunk.get('retrieval_score_distance',-1):.4f}"
        )
        if 'rerank_score' in chunk:
            header += f", RerankScore: {chunk['rerank_score']:.4f}"

        formatted_context_parts.append(f"{header}\nContent:\n{content_for_llm}\n--- End Src {i+1} ---")
        payload["source_chunks_retrieved"].append(chunk)

    payload["formatted_context_for_llm"] = "\n\n".join(formatted_context_parts)
    payload["retrieval_metadata"]["final_chunk_count"] = len(selected_chunks)

    logger.success(
        f"Context retrieval for '{query_text[:30]}...' in {time.time()-retrieval_start_time:.2f}s. "
        f"Final chunks: {len(selected_chunks)}."
    )
    return payload

def _generate_llm_messages(
    user_query: str,
    context_str: str,
    document_identifier: str,
    dynamic_role_instructions: Optional[str],
    is_summary_context: bool,
) -> List[Dict]:
    system_content_parts = [
        f"You are {AI_PERSONA_NAME}, {AI_ROLE_DESCRIPTION}",
        AI_CORE_DIRECTIVE.replace("'{document_name}'", f"'{document_identifier}'"),
        AI_ANSWERING_STYLE_REFINED,
        AI_CONTEXTUAL_PRIORITIZATION_POLICY,
        AI_CITATION_POLICY_TEXT,
        AI_NO_ANSWER_POLICY,
    ]

    if is_summary_context:
        system_content_parts.append(AI_SUMMARIZATION_POLICY)
        context_header = "PROVIDED SUMMARY (Answer ONLY from this summary):"
    else:
        context_header = "PROVIDED CONTEXT (Answer ONLY from this):"

    if dynamic_role_instructions and dynamic_role_instructions.strip():
        system_content_parts.extend([
            "\n--- ADDITIONAL ROLE GUIDANCE ---",
            dynamic_role_instructions.strip(),
            "--- END GUIDANCE ---",
            "Strictly adhere to ALL guidance."
        ])

    system_message = {"role": "system", "content": "\n\n".join(system_content_parts).strip()}
    user_message = {"role": "user", "content": f"USER'S QUERY: {user_query.strip()}\n\n{context_header}\n{context_str.strip()}"}

    return [system_message, user_message]

def generate_standard_llm_response(
    user_query: str, formatted_context_from_rag: str,
    source_chunks_from_rag: List[Dict], doc_name_identifier: str,
    dynamic_role_info: Optional[str], response_payload: Dict
) -> Dict:
    messages = _generate_llm_messages(
        user_query, formatted_context_from_rag, doc_name_identifier,
        dynamic_role_info, is_summary_context=False
    )
    response_payload["llm_prompt_sent"] = messages

    try:
        logger.info(f"Sending RAG request to OpenAI ('{GENERATION_MODEL_NAME}'). Query: '{user_query[:70]}...'")
        gen_start_time = time.time()

        if not APP_STATE.get("azure_llm_client"):
            logger.error("OpenAI LLM client instance not available.")
            response_payload.update({"answer_text": "Error: AI model not configured.", "error_message": "AI model not configured."})
            return response_payload

        openai_api_response = APP_STATE["azure_llm_client"].chat.completions.create(
            model=AZURE_LLM_MODEL_NAME,
            messages=messages,
            temperature=0.25,
            max_tokens=1000,
            top_p=1.0,
        )
        response_payload["generation_time_s"] = round(time.time() - gen_start_time, 2)
        logger.success(f"OpenAI LLM response in {response_payload['generation_time_s']:.2f}s.")

        try:
            response_payload["llm_full_response_obj_str"] = str(openai_api_response)
        except Exception:
            response_payload["llm_full_response_obj_str"] = "Could not serialize full OpenAI response object."

        if openai_api_response.choices and openai_api_response.choices[0].message:
            generated_text = openai_api_response.choices[0].message.content.strip()
            response_payload["answer_text"] = generated_text

            citations_found_raw = re.findall(r'(\[Doc:[^\]]+?CkID:[^\]]+?\])', generated_text)
            if citations_found_raw:
                logger.warning(
                    f"LLM included {len(citations_found_raw)} bracketed citations despite instruction. "
                    "These should not be displayed in the final answer if the prompt was followed."
                )
            response_payload["parsed_citations"] = [{"tag": c} for c in citations_found_raw]
        else:
            logger.error("OpenAI API response did not contain expected message content.")
            response_payload.update({
                "answer_text": "Error: Could not parse text from AI response.",
                "error_message": "OpenAI response parsing error: No choices or message found."
            })

    except Exception as e:
        logger.error(f"General error during OpenAI API call: {e}", exc_info=True)
        response_payload.update({
            "answer_text": f"Error: LLM call failed ({type(e).__name__}).",
            "error_message": str(e)
        })

    response_payload.setdefault("answer_text", "Error: Processing failed to produce an answer.")
    response_payload.setdefault("parsed_citations", [])
    return response_payload

def generate_llm_response(
    user_query: str, formatted_context_from_rag: str,
    source_chunks_from_rag: List[Dict], default_doc_name: str = "the document",
    dynamic_role_info: Optional[str] = None, is_aboutness_query_flag: bool = False
) -> Dict:
    response_payload = {
        "answer_text": "Error: LLM response could not be generated.",
        "llm_prompt_sent": "",
        "llm_full_response_obj_str": None,
        "parsed_citations": [],
        "error_message": None,
        "generation_time_s": 0.0,
        "summarization_chain_used": False,
    }

    required_llm_keys = ["llm_initialized", "azure_llm_client", "langchain_llm"]
    if not all(APP_STATE.get(k) for k in required_llm_keys):
        logger.error("LLM systems not initialized (OpenAI client or LangChain LLM missing).")
        response_payload["error_message"] = "LLM systems not initialized."
        return response_payload

    doc_names = sorted(list(set(
        c['metadata'].get('original_filename', default_doc_name)
        for c in source_chunks_from_rag if c.get('metadata')
    )))
    doc_id_for_prompt = default_doc_name
    if doc_names:
        if len(doc_names) == 1:
            doc_id_for_prompt = f"document '{doc_names[0]}'"
        else:
            doc_id_for_prompt = f"documents ({', '.join(doc_names)})"

    context_total_text = "\n\n".join([
        c.get("original_chunk_text", c.get("text_content",""))
        for c in source_chunks_from_rag
    ])
    context_token_count = count_tokens(context_total_text)

    if is_aboutness_query_flag and context_token_count > MAX_TOKENS_FOR_DIRECT_LLM_SUMMARIZATION and source_chunks_from_rag:
        logger.info(
            f"Aboutness query with large context ({context_token_count} tokens > {MAX_TOKENS_FOR_DIRECT_LLM_SUMMARIZATION}). "
            "Attempting LangChain map-reduce summarization."
        )
        response_payload["summarization_chain_used"] = True

        langchain_documents = [
            Document(page_content=chunk.get("original_chunk_text", chunk.get("text_content","")), metadata=chunk.get("metadata", {}))
            for chunk in source_chunks_from_rag if chunk.get("original_chunk_text", chunk.get("text_content","")).strip()
        ]

        if not langchain_documents:
            logger.warning("No valid documents for LangChain summarization. Falling back to standard generation.")
            return generate_standard_llm_response(
                user_query, formatted_context_from_rag, source_chunks_from_rag,
                doc_id_for_prompt, dynamic_role_info, response_payload
            )
        try:
            summarize_chain = load_summarize_chain(
                llm=APP_STATE["langchain_llm"], chain_type="map_reduce", verbose=False
            )
            summarization_question = (
                f"Provide a comprehensive summary of the key information in '{doc_id_for_prompt}' "
                f"that is relevant to the user's query: '{user_query}'"
            )

            start_time_lc_summarize = time.time()
            summary_result = summarize_chain.invoke({
                "input_documents": langchain_documents,
                "question": summarization_question
            })
            response_payload["generation_time_s"] = round(time.time() - start_time_lc_summarize, 2)

            raw_summary_text = summary_result.get("output_text", "Error: Summarization failed to produce text.").strip()
            logger.success(
                f"LangChain summarization completed in {response_payload['generation_time_s']:.2f}s. "
                f"Raw summary length: {len(raw_summary_text)} characters."
            )

            if not raw_summary_text or "Error:" in raw_summary_text or "failed to produce" in raw_summary_text.lower():
                logger.warning("LangChain summary was empty or indicated failure. Falling back to standard generation.")
                return generate_standard_llm_response(
                    user_query, formatted_context_from_rag, source_chunks_from_rag,
                    doc_id_for_prompt, dynamic_role_info, response_payload
                )

            messages_refine = _generate_llm_messages(
                user_query, raw_summary_text, doc_id_for_prompt,
                dynamic_role_info, is_summary_context=True
            )
            response_payload["llm_prompt_sent"] = messages_refine

            start_time_final_refine = time.time()
            final_openai_response = APP_STATE["azure_llm_client"].chat.completions.create(
                model=AZURE_LLM_MODEL_NAME,
                messages=messages_refine,
                temperature=0.25,
                max_tokens=1000,
                top_p=1.0,
            )
            response_payload["generation_time_s"] += round(time.time() - start_time_final_refine, 2)
            response_payload["llm_full_response_obj_str"] = str(final_openai_response)

            if final_openai_response.choices and final_openai_response.choices[0].message:
                refined_answer_text = final_openai_response.choices[0].message.content.strip()
                response_payload["answer_text"] = refined_answer_text + f"\n\n(This answer is based on a summary of {doc_id_for_prompt}.)"
                logger.info("Summary refined by main LLM.")
                response_payload["parsed_citations"] = []
            else:
                logger.error("OpenAI summary refinement response did not contain expected message content.")
                response_payload.update({
                    "answer_text": "Error: Could not parse text from AI's refined summary.",
                    "error_message": "OpenAI summary refinement parsing error: No choices or message found."
                })

        except Exception as e_lc_summarize:
            logger.error(f"LangChain summarization process FAILED: {e_lc_summarize}. Falling back to standard generation.", exc_info=True)
            response_payload.update({
                "error_message": f"Summarization chain error: {str(e_lc_summarize)}. Fallback executed.",
                "summarization_chain_used": False
            })
            return generate_standard_llm_response(
                user_query, formatted_context_from_rag, source_chunks_from_rag,
                doc_id_for_prompt, dynamic_role_info, response_payload
            )
    else:
        return generate_standard_llm_response(
            user_query, formatted_context_from_rag, source_chunks_from_rag,
            doc_id_for_prompt, dynamic_role_info, response_payload
        )

    response_payload.setdefault("answer_text", "Error: Summarization path failed to produce a final answer.")
    response_payload.setdefault("parsed_citations", [])
    return response_payload

