"""Compatibility entry point for the canonical SuppTracker API.

Deployments and local development should use ``api.risk_api:app``.  Keeping
this module as a thin re-export prevents ``uvicorn app:app`` from serving the
older, divergent implementation that had different validation and safety
behaviour.
"""

import os

# Older test and deployment scripts used SUPPTRACKER_DATA.  Preserve that
# configuration spelling while the canonical service uses SUPPTRACKER_DATA_DIR.
if os.getenv("SUPPTRACKER_DATA") and not os.getenv("SUPPTRACKER_DATA_DIR"):
    os.environ["SUPPTRACKER_DATA_DIR"] = os.environ["SUPPTRACKER_DATA"]

from api.risk_api import app

__all__ = ["app"]
