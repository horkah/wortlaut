"""Das Fehlerprotokoll - Warnungen und Fehler von Webdienst und Trainer, sieben Tage.

In „hören" wie `api/system.py`: Jede App stellt ihre übergreifenden Fragen an
die Wurzel der Domain. Geschrieben wird es in `wortlaut/fehlerlog.py`.

Lesen dürfen Aufsicht und Verwaltung - und wer den Trainerschlüssel vorlegt:
Wer trainieren lässt, soll sehen, warum ein Lauf scheiterte. Ein Sprecher
nicht; im Protokoll stehen Pfade und Kennungen anderer.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from wortlaut import fehlerlog

from ..config import einstellungen
from ..deps import _pruefe_verwaltung

router = APIRouter(tags=["Fehlerprotokoll"])


class Eintrag(BaseModel):
    zeit: str
    # `warnung` oder `fehler`.
    stufe: str
    # Woher: `app`, `trainer` (der Läufer) oder `training` (ein Lauf).
    dienst: str
    # Der Logger, etwa `uvicorn.error` oder `py.warnings`.
    quelle: str
    text: str
    ausnahme: str = ""


class Antwort(BaseModel):
    eintraege: list[Eintrag]
    # Wie weit das Protokoll zurückreicht, in Tagen.
    tage: int


def _darf_lesen(authorization: str | None, x_trainer_key: str | None) -> None:
    """Trainerschlüssel, sonst Verwaltung oder Aufsicht (`deps._pruefe_verwaltung`)."""
    erwartet = einstellungen().trainer_key
    vorgelegt = (x_trainer_key or "").encode("utf-8")
    if erwartet and vorgelegt and secrets.compare_digest(vorgelegt, erwartet.encode("utf-8")):
        return
    try:
        _pruefe_verwaltung(authorization)
    except HTTPException as ursache:
        raise HTTPException(
            status_code=401,
            detail="Das Fehlerprotokoll sehen Aufsicht, Verwaltung und wer den "
            "Trainerschlüssel vorlegt.",
        ) from ursache


@router.get("/api/fehlerlog", response_model=Antwort)
def fehlerlog_lesen(
    authorization: Annotated[str | None, Header()] = None,
    x_trainer_key: Annotated[str | None, Header()] = None,
) -> Antwort:
    """Die Einträge der letzten sieben Tage, jüngster zuerst."""
    _darf_lesen(authorization, x_trainer_key)
    return Antwort(
        eintraege=[Eintrag(**zeile) for zeile in fehlerlog.lies(einstellungen().data_dir)],
        tage=fehlerlog.AUFBEWAHRUNG.days,
    )
