"""Für wen dieser Browser eingestellt ist.

Ein einziger Weg, und er ist zugleich seine eigene Antwort: Die Kennung kommt
aus dem vorgelegten Zugang (`deps.py`), nicht aus einem Parameter. Die
Oberfläche braucht ihn, um den Namen in der Kopfzeile zu zeigen und um zu
merken, dass hier noch kein Zugang liegt — dann führt sie zum persönlichen
Link statt in ein Diktat, das ohnehin abgewiesen würde.

Denselben Weg gibt es in „hören" (`GET /api/zugang`), mit derselben Antwort.
Beide Apps lesen denselben Zugang aus demselben Browser; eine App, die dieselbe
Frage anders beantwortete, wäre eine Fehlerquelle.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..deps import Wer

router = APIRouter(tags=["Zugang"])


class WerAntwort(BaseModel):
    art: str  # hier immer „sprecher" — alles andere ist ein 401
    sprecher_id: str
    name: str


@router.get("/api/zugang", response_model=WerAntwort)
def wer_ruft(wer: Wer) -> WerAntwort:
    return WerAntwort(art="sprecher", sprecher_id=wer.sprecher_id, name=wer.name)
