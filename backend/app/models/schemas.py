from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ProcessDocumentRequest(BaseModel):
    staging_ids: Optional[List[str]] = []
    options: Optional[Dict[str, Any]] = None

class ProcessDocumentResponse(BaseModel):
    processed_documents: List[Dict[str, Any]]

class AskQuestionRequest(BaseModel):
    query: str
    active_documents: Optional[List[str]] = []
    
class AskQuestionResponse(BaseModel):
    answer_text: str
    parsed_citations: List[Dict[str, Any]]
