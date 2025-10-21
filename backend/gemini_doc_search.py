from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import google.generativeai as genai
import numpy as np
from typing import List, Dict
import os

# Initialize router
router = APIRouter()

# Configure Gemini API
# Set your API key as an environment variable: GEMINI_API_KEY
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)


class DocumentSearchRequest(BaseModel):
    """Request model for document search"""
    documents: List[str]
    query: str


class DocumentSearchResponse(BaseModel):
    """Response model for document search"""
    results: List[Dict[str, any]]


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    vec1_np = np.array(vec1)
    vec2_np = np.array(vec2)
    
    dot_product = np.dot(vec1_np, vec2_np)
    norm1 = np.linalg.norm(vec1_np)
    norm2 = np.linalg.norm(vec2_np)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return float(dot_product / (norm1 * norm2))


def get_embedding(text: str) -> List[float]:
    """Get embedding for text using Gemini API"""
    try:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document"
        )
        return result['embedding']
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding generation failed: {str(e)}")


@router.post("/api/gemini-doc-search", response_model=DocumentSearchResponse)
async def gemini_doc_search(request: DocumentSearchRequest):
    """
    Search documents using Gemini embeddings and cosine similarity.
    
    This endpoint takes a list of documents and a query, generates embeddings
    for each using Google's Gemini API, and returns documents ranked by 
    cosine similarity to the query.
    
    Args:
        request: DocumentSearchRequest containing documents list and query string
    
    Returns:
        DocumentSearchResponse with ranked results containing document text,
        index, and similarity score
    """
    if not gemini_api_key:
        raise HTTPException(
            status_code=500, 
            detail="GEMINI_API_KEY environment variable not set. Please configure your API key."
        )
    
    if not request.documents:
        raise HTTPException(status_code=400, detail="Documents list cannot be empty")
    
    if not request.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    try:
        # Get query embedding
        query_embedding = get_embedding(request.query)
        
        # Get document embeddings and calculate similarities
        results = []
        for idx, doc in enumerate(request.documents):
            doc_embedding = get_embedding(doc)
            similarity = cosine_similarity(query_embedding, doc_embedding)
            
            results.append({
                "document": doc,
                "index": idx,
                "similarity_score": similarity
            })
        
        # Sort by similarity score (highest first)
        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        
        return DocumentSearchResponse(results=results)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Document search failed: {str(e)}"
        )
