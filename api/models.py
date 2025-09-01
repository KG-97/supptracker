from pydantic import BaseModel
from typing import List, Literal, Optional

# Type aliases
Evidence = Literal['A', 'B', 'C', 'D']
Severity = Literal['None', 'Mild', 'Moderate', 'Severe']


class Compound(BaseModel):
    id: str
    name: str
    synonyms: List[str] = []
    cls: Optional[str] = None
    typical_dose: Optional[dict] = None  # e.g., {'amount': 5, 'unit': 'mg', 'route': 'oral'}


class Interaction(BaseModel):
    id: str
    a: str  # compound id
    b: str  # compound id
    bidirectional: bool = True
    mechanism: List[str] = []
    severity: Severity
    evidence: Evidence
    effect: str
    action: Literal['Avoid', 'Monitor', 'No issue']
    sources: List[str] = []
