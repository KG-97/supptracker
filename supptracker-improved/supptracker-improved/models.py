"""
Pydantic models defining the request and response schemas for the Supplement
Interaction API. Defining explicit models allows FastAPI to generate
comprehensive OpenAPI documentation and provides strong type checking
throughout the codebase.

These models mirror the structure of the data returned by the backend
functions in ``app.py``. They should be kept in sync with any changes to
those functions.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class CompoundHit(BaseModel):
    """A single compound hit returned by the search endpoint."""

    id: str = Field(..., description="Unique identifier for the compound")
    name: str = Field(..., description="Human readable compound name")
    synonyms: List[str] = Field(
        default_factory=list,
        description="List of alternative names/synonyms for this compound",
    )


class SearchResponse(BaseModel):
    """Response model for the /search endpoint."""

    compounds: List[CompoundHit] = Field(
        default_factory=list, description="List of matching compounds"
    )


class InteractionSource(BaseModel):
    """Metadata describing a source from which an interaction was derived."""

    id: str = Field(..., description="Unique identifier for the source")
    title: Optional[str] = Field(None, description="Human readable title of the source")
    citation: Optional[str] = Field(
        None, description="Short citation or reference for the source"
    )
    identifier: Optional[str] = Field(
        None, description="Unique publication identifier (e.g. DOI, PMID)"
    )
    date: Optional[str] = Field(
        None, description="Publication date or year associated with the source"
    )
    # Additional arbitrary metadata can be captured without validation
    extra: Optional[Dict[str, Any]] = Field(
        default=None, description="Any additional fields associated with this source"
    )


class InteractionDetail(BaseModel):
    """Detailed information about an interaction between two compounds."""

    compound_a: str = Field(..., description="Identifier for compound A")
    compound_b: str = Field(..., description="Identifier for compound B")
    severity: Optional[str] = Field(None, description="Severity classification")
    evidence_grade: Optional[str] = Field(
        None, description="Grade of evidence supporting this interaction"
    )
    mechanism_tags: Optional[str] = Field(
        None, description="Semicolon separated mechanism tags"
    )
    source_ids: Optional[str] = Field(
        None, description="Semicolon separated identifiers for source records"
    )
    # Computed fields
    score: float = Field(..., description="Numeric score for the interaction")
    bucket: str = Field(..., description="Risk bucket label for the interaction")
    action_resolved: str = Field(
        ..., description="Action recommended after resolving bucket and rules"
    )
    sources: List[InteractionSource] = Field(
        default_factory=list, description="List of sources relevant to this interaction"
    )


class InteractionPair(BaseModel):
    """Wrapper describing the pair of compounds supplied in an interaction query."""

    a: str = Field(..., description="Compound A identifier used in the query")
    b: str = Field(..., description="Compound B identifier used in the query")


class InteractionResponse(BaseModel):
    """Response model for the /interaction endpoint."""

    pair: InteractionPair = Field(..., description="Input pair of compounds")
    interaction: InteractionDetail = Field(
        ..., description="Detailed interaction information and score"
    )


class StackCell(BaseModel):
    """A single cell within the interaction matrix returned by /stack/check."""

    a: str = Field(..., description="Compound A identifier in the pair")
    b: str = Field(..., description="Compound B identifier in the pair")
    score: float = Field(..., description="Computed interaction score")
    bucket: str = Field(..., description="Risk bucket label")
    action: str = Field(..., description="Recommended action based on the bucket")


class StackCheckRequest(BaseModel):
    """Request model for the /stack/check endpoint."""

    items: List[str] = Field(
        ..., min_items=1, description="List of compound identifiers in the stack"
    )


class StackCheckResponse(BaseModel):
    """Response model for the /stack/check endpoint."""

    items: List[str] = Field(..., description="List of compounds in the query")
    matrix: List[List[Optional[float]]] = Field(
        ..., description="Matrix of scores for pairwise interactions"
    )
    cells: List[StackCell] = Field(
        default_factory=list,
        description="List of populated cells containing scores and actions",
    )