"""Welche Sprachen dieses System anbietet - eine Auskunft, kein Zustand.

Die Liste steht in `wortlaut/sprachen.py`; die Oberfläche bietet sie beim
Anlegen eines Profils an. Kein Wächter: Welche Sprachen das System kann, sagt
nichts über einen Menschen.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from wortlaut import sprachen as sprachdienst

router = APIRouter(tags=["Sprachen"])


class SpracheAntwort(BaseModel):
    kuerzel: str
    name: str
    # Die Vorauswahl - dieselbe wie auf dem Server.
    vorgabe: bool


@router.get("/api/sprachen", response_model=list[SpracheAntwort])
def liste() -> list[SpracheAntwort]:
    return [
        SpracheAntwort(kuerzel=kuerzel, name=name, vorgabe=kuerzel == sprachdienst.VORGABE)
        for kuerzel, name in sprachdienst.UNTERSTUETZT.items()
    ]
