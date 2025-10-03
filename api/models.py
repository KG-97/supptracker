from pydantic import BaseModel, Field
from typing import Dict, List, Literal, Optional

# Type aliases
Evidence = Literal['A', 'B', 'C', 'D']
Severity = Literal['None', 'Mild', 'Moderate', 'Severe']


class Compound(BaseModel):
    id: str
    name: str
    synonyms: List[str] = Field(default_factory=list)
    cls: Optional[str] = None
    typical_dose: Optional[dict] = None  # e.g., {'amount': 5, 'unit': 'mg', 'route': 'oral'}
    external_ids: Dict[str, str] = Field(default_factory=dict, alias="externalIds")
    reference_urls: Dict[str, str] = Field(default_factory=dict, alias="referenceUrls")

    class Config:
        allow_population_by_field_name = True


class Interaction(BaseModel):
    id: str
    a: str  # compound id
    b: str  # compound id
    bidirectional: bool = True
    mechanism: List[str] = Field(default_factory=list)
    severity: Severity
    evidence: Evidence
    effect: str
    action: Literal['Avoid', 'Monitor', 'No issue']
    sources: List[str] = Field(default_factory=list)
