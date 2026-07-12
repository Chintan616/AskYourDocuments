from fastapi import APIRouter, HTTPException
from app.models.schemas import AskQuestionRequest, AskQuestionResponse
from app.services.rag import retrieve_relevant_context, generate_llm_response
from app.services.state import APP_STATE, APP_WEB_STATE, AI_NO_ANSWER_POLICY
from app.services.database import get_or_create_collection_cached
from app.services.parser import sanitize_chromadb_collection_name
from loguru import logger

router = APIRouter()

@router.post("/ask", response_model=AskQuestionResponse)
async def ask_question(request: AskQuestionRequest):
    user_query = request.query
    active_documents = request.active_documents
    
    if not user_query:
        raise HTTPException(status_code=400, detail="No query provided")
        
    collections_to_query_names = []
    query_scope_description = "all processed documents"

    if active_documents:
        valid_collections = []
        all_active_docs_found = True
        for fname in active_documents:
            coll_name = APP_WEB_STATE["processed_collections"].get(fname)
            if coll_name:
                valid_collections.append(coll_name)
            else:
                all_active_docs_found = False
                break
                
        if all_active_docs_found and valid_collections:
            collections_to_query_names = valid_collections
            if len(active_documents) == 1:
                query_scope_description = f"document '{active_documents[0]}'"
            else:
                query_scope_description = f"documents: {', '.join(active_documents)}"
        else:
            collections_to_query_names = list(APP_WEB_STATE["processed_collections"].values())
    else:
        collections_to_query_names = list(APP_WEB_STATE["processed_collections"].values())

    if not collections_to_query_names:
        if not APP_WEB_STATE["processed_collections"]:
            raise HTTPException(status_code=400, detail="No documents have been processed yet.")
        else:
            raise HTTPException(status_code=500, detail="Internal state error: No collections to query.")

    try:
        is_aboutness_type_query = any(
            phrase in user_query.lower() for phrase in ["about this document", "summarize", "overview", "main idea", "tell me about"]
        )

        retrieval_results = retrieve_relevant_context(
            user_query,
            collections_to_query_names,
            use_reranking=(APP_STATE.get("reranker_model") is not None)
        )

        formatted_context = retrieval_results.get("formatted_context_for_llm", "")
        source_chunks = retrieval_results.get("source_chunks_retrieved", [])
        
        logger.info(f"DEBUG: collections_to_query_names = {collections_to_query_names}")
        logger.info(f"DEBUG: active_documents = {active_documents}")
        logger.info(f"DEBUG: retrieval payload = {retrieval_results}")

        if "Error:" in formatted_context or not source_chunks:
            logger.warning(f"Context retrieval yielded no usable chunks or an error: {formatted_context[:200]}")

        llm_generation_output = generate_llm_response(
            user_query,
            formatted_context,
            source_chunks,
            default_doc_name=query_scope_description,
            is_aboutness_query_flag=is_aboutness_type_query
        )
        
        final_answer_text = llm_generation_output.get("answer_text", "Error: AI response generation failed or produced no text.")
        error_message_from_llm = llm_generation_output.get("error_message")
        
        if final_answer_text == AI_NO_ANSWER_POLICY or not final_answer_text.strip() or "Error: AI" in final_answer_text:
            final_answer_text = "I'm sorry, I couldn't find specific information to answer your question in the provided document(s)."

        return AskQuestionResponse(
            answer_text=final_answer_text,
            parsed_citations=llm_generation_output.get("parsed_citations", [])
        )
    except Exception as e:
        logger.error(f"Error during /ask: {e}")
        raise HTTPException(status_code=500, detail=str(e))
