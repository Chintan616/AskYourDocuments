from fastapi import APIRouter, HTTPException, UploadFile, File
from app.models.schemas import ProcessDocumentRequest, ProcessDocumentResponse
from app.services.state import APP_WEB_STATE, APP_STATE, CHROMA_COLLECTION_NAME_PREFIX
from app.services.rag import ingest_document_into_knowledge_base
from app.services.parser import parse_document_via_profile, sanitize_chromadb_collection_name
from app.services.database import get_or_create_collection_cached
import uuid
import os
import shutil
from loguru import logger
import tempfile
import boto3

# S3 Configuration
AWS_REGION = os.getenv("AWS_REGION")
AWS_S3_BUCKET_NAME = os.getenv("AWS_S3_BUCKET_NAME")

def get_s3_client():
    if not AWS_REGION or not AWS_S3_BUCKET_NAME:
        logger.warning("AWS S3 credentials not fully configured in environment.")
        return None
    try:
        return boto3.client('s3', region_name=AWS_REGION)
    except Exception as e:
        logger.error(f"Failed to initialize S3 client: {e}")
        return None

router = APIRouter()

@router.post("/stage_file")
async def stage_file(file: UploadFile = File(...)):
    try:
        s3_client = get_s3_client()
        if not s3_client:
            raise HTTPException(status_code=500, detail="S3 client not configured.")

        filename = file.filename
        
        # Simple ID logic similar to the original app
        import hashlib
        file_id_hash = hashlib.md5(filename.encode()).hexdigest()[:8]
        clean_name = filename.replace(" ", "_")
        staging_id = f"staged_{file_id_hash}_{clean_name}"
        
        # Upload directly to S3
        s3_client.upload_fileobj(file.file, AWS_S3_BUCKET_NAME, staging_id)
            
        APP_WEB_STATE["staged_files"][staging_id] = {
            "original_filename": filename,
            "s3_key": staging_id
        }
        
        return {"message": "File staged successfully in S3", "staging_id": staging_id, "original_filename": filename}
    except Exception as e:
        logger.error(f"Error staging file to S3: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/process_staged_files", response_model=ProcessDocumentResponse)
async def process_staged_files(request: ProcessDocumentRequest = None):
    # Retrieve staging IDs from APP_WEB_STATE
    staged_ids = request.staging_ids if request and request.staging_ids else list(APP_WEB_STATE["staged_files"].keys())
    
    if not staged_ids:
        return ProcessDocumentResponse(processed_documents=[])
        
    processing_options = request.options if request else {}
    # defaults mimicking legacy
    config_overrides = {
        "use_vision_for_ocr": processing_options.get('ocr', False) or processing_options.get('images', False),
        "use_vision_for_description": processing_options.get('images', False),
        "process_scanned_pages": processing_options.get('ocr', False) or processing_options.get('handwritten', False)
    }

    processed_list = []
    
    for staging_id in staged_ids:
        file_info = APP_WEB_STATE["staged_files"].get(staging_id)
        if not file_info:
            continue
            
        orig_filename = file_info["original_filename"]
        s3_key = file_info["s3_key"]
        
        s3_client = get_s3_client()
        if not s3_client:
            logger.error("S3 client not configured.")
            continue
            
        try:
            # Download from S3 to temp local file for processing
            fd, temp_path = tempfile.mkstemp(suffix=f"_{orig_filename}")
            os.close(fd)
            s3_client.download_file(AWS_S3_BUCKET_NAME, s3_key, temp_path)
            
            profile_to_use = "fastest"
            if processing_options.get("handwritten", False) or processing_options.get("images", False):
                profile_to_use = "comprehensive_vision" if APP_STATE.get("vision_client_initialized") else "digital_plus_ocr"
            elif processing_options.get("ocr", False):
                profile_to_use = "digital_plus_ocr"
            elif not processing_options:
                profile_to_use = "default_fallback"

            logger.info(f"Processing '{orig_filename}' with profile '{profile_to_use}'")
            parsed_blocks = parse_document_via_profile(temp_path, profile_name=profile_to_use)
            
            if parsed_blocks and parsed_blocks[0].get("type") == "error":
                logger.error(f"Parsing failed for {orig_filename}: {parsed_blocks[0].get('content')}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                continue
                
            base_collection_name = f"{CHROMA_COLLECTION_NAME_PREFIX}_{os.path.splitext(orig_filename)[0]}_{uuid.uuid4().hex[:6]}"
            final_collection_name = sanitize_chromadb_collection_name(base_collection_name)
            target_collection_obj = get_or_create_collection_cached(final_collection_name)
            
            if not target_collection_obj:
                logger.error(f"Failed to get/create DB collection {final_collection_name}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                continue

            ingestion_successful = ingest_document_into_knowledge_base(
                parsed_blocks, final_collection_name, orig_filename, target_collection_obj
            )
            
            if ingestion_successful:
                APP_WEB_STATE["processed_collections"][orig_filename] = final_collection_name
                processed_list.append({
                    "filename": orig_filename,
                    "collection_name": final_collection_name,
                    "staging_id": staging_id,
                    "status": "processed"
                })
                
                # cleanup S3 object
                try:
                    s3_client.delete_object(Bucket=AWS_S3_BUCKET_NAME, Key=s3_key)
                except Exception as e:
                    logger.error(f"Failed to delete S3 object {s3_key}: {e}")
            else:
                logger.error(f"Ingestion failed for '{orig_filename}'")
                
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
        except Exception as e:
            logger.error(f"Failed to process {orig_filename}: {e}")
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.remove(temp_path)
            
    # clear staged correctly based on legacy
    # Note: legacy just removes the successfully processed ones, but for now we'll clear all or successful ones
    # Let's just clear the APP_WEB_STATE["staged_files"] to match what was there.
    APP_WEB_STATE["staged_files"].clear()
    
    return ProcessDocumentResponse(processed_documents=processed_list)

@router.get("/list_processed_documents_for_chat")
async def list_processed_docs():
    return {"processed_document_filenames": list(APP_WEB_STATE["processed_collections"].keys())}
