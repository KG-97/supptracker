"""
Pydantic models defining the request and response schemas for the Supplement
Interaction API.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class CompoundHit(BaseModel):
    """A single compound hit returned by the search endpoint."""
    id: str = Field(..., description="Unique identifier for the compound")
    name: str = Field(..., description="Human readable compound name")
    synonyms: List[str] = Field(default_factory=list, description="Alternative names")


class CompoundDetail(BaseModel):
    """Full compound metadata returned by the /compounds endpoint."""
    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Human readable name")
    synonyms: List[str] = Field(default_factory=list)
    compound_class: str = Field("", description="Pharmacological/nutritional class")
    route: str = Field("", description="Administration route")
    common_dose: str = Field("", description="Typical dosage range")
    qt_risk: str = Field("", description="QT prolongation risk level")
    notes: str = Field("", description="Additional notes")


class SearchResponse(BaseModel):
    """Response model for the /search endpoint."""
    compounds: List[CompoundHit] = Field(default_factory=list)


class CompoundsResponse(BaseModel):
    """Response model for the /compounds endpoint."""
    compounds: List[CompoundDetail] = Field(default_factory=list)


class InteractionSource(BaseModel):
    """Metadata describing a source from which an interaction was derived."""
    id: str = Field(..., description="Unique identifier for the source")
    title: Optional[str] = Field(None)
    citation: Optional[str] = Field(None)
    identifier: Optional[str] = Field(None, description="DOI, PMID, etc.")
    date: Optional[str] = Field(None)
    extra: Optional[Dict[str, Any]] = Field(default=None)


class InteractionDetail(BaseModel):
    """Detailed information about an interaction between two compounds."""
    compound_a: str
    compound_b: str
    severity: Optional[str] = Field(None)
    evidence_grade: Optional[str] = Field(None)
    mechanism_tags: Optional[str] = Field(None)
    effect_summary: Optional[str] = Field(None, description="Plain-language explanation of the interaction")
    source_ids: Optional[str] = Field(None)
    # Computed fields
    score: float
    bucket: str
    action_resolved: str
    sources: List[InteractionSource] = Field(default_factory=list)


class InteractionPair(BaseModel):
    """Wrapper describing the pair of compounds in an interaction query."""
    a: str
    b: str


class InteractionResponse(BaseModel):
    """Response model for the /interaction endpoint."""
    pair: InteractionPair
    interaction: Optional[InteractionDetail] = Field(None)
    found: bool = Field(True, description="Whether an interaction record was found for this pair")


class StackCell(BaseModel):
    """A single cell within the interaction matrix."""
    a: str
    b: str
    score: float
    bucket: str
    action: str
    effect_summary: Optional[str] = Field(None)


class StackCheckRequest(BaseModel):
    """Request model for the /stack/check endpoint."""
    items: List[str] = Field(..., min_length=1)


class StackCheckResponse(BaseModel):
    """Response model for the /stack/check endpoint."""
    items: List[str]
    matrix: List[List[Optional[float]]]
    cells: List[StackCell] = Field(default_factory=list)