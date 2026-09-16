"""Welche Sprachen dieses System anbietet - eine Auskunft, kein Zustand.

Die Liste steht in `wortlaut/sprachen.py`; hier wird sie nur herausgereicht,
damit die Verwaltung beim Anlegen eines Profils nicht raten muss. Vorher stand
im Auswahlfeld eine fest eingetragene Sprache, und das hieß: Wer eine zweite
hinzufügt, ändert die Bibliothek, den Endpunkt **und** die Oberfläche. Jetzt
ändert er die Bibliothek.

Kein Wächter, so wie bei `GET /api/zugang`: Was dieses System an Sprachen kann,
ist keine Auskunft über einen Menschen. Wer damit etwas anfangen will, braucht
ohnehin den Verwalterzugang, der am Anlegen selbst hängt.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from wortlaut import sprachen as sprachdienst

router = APIRouter(tags=["Sprachen"])


class SpracheAntwort(BaseModel):
    kuerzel: str
    name: str
    # Was ein Profil bekommt, wenn niemand etwas wählt - damit die Oberfläche
    # dieselbe Vorauswahl trifft wie der Server und nicht ihre eigene.
    vorgabe: bool


@router.get("/api/sprachen", response_model=list[SpracheAntwort])
def liste() -> list[SpracheAntwort]:
    return [
        SpracheAntwort(kuerzel=kuerzel, name=name, vorgabe=kuerzel == sprachdienst.VORGABE)
        for kuerzel, name in sprachdienst.UNTERSTUETZT.items()
    ]
