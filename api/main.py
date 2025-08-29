from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Literal


class Compound(BaseModel):
    id: str
    name: str


class Interaction(BaseModel):
    id: str
    a: str
    b: str
    severity: Literal['None','Mild','Moderate','Severe']
    evidence: Literal['A','B','C','D']
    effect: str
    action: str


app = FastAPI()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/search")
def search(q: str):
    # Return an empty list of compounds for now
    return []


@app.get("/api/interaction")
def get_interaction(a: str, b: str):
    # Return a placeholder interaction example
    return {
        "id": "example",
        "a": a,
        "b": b,
        "severity": "Mild",
        "evidence": "C",
        "effect": "Example",
        "action": "Monitor",
    }


@app.post("/api/stack/check")
def stack_check(stack: List[str]):
    # Return an empty matrix placeholder
    return {"matrix": []}
