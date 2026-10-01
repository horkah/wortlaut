"""Die Schlüssel neben dem Zugang - einmal beschrieben, einmal geprüft.

Der Zugang sagt, wer ruft und wessen Daten das sind (`zugang.py`). Zwei Wege
kosten mehr, als ein Zugang auf einem Telefon allein tragen soll, und stehen
deshalb hinter je einem eigenen Geheimnis:

* der **Trainerschlüssel** (`WORTLAUT_TRAINER_KEY`, `X-Trainer-Key`): ein
  Training beauftragen oder neu starten, einen Lauf samt Modell löschen, das
  Fehlerprotokoll lesen;
* der **Bearbeitungsschlüssel** (`WORTLAUT_EDITOR_KEY`, `X-Editor-Key`): jeder
  Weg des Zuschnitts in „hören".

Leer heißt abgeschaltet, nicht offen. Die Wächter der Apps und die Auskunft
in `GET /api/zugang`, welche Rechte ein Browser gerade hat, rechnen beide mit
`Schluessel.stand` - eine Auskunft, die anders urteilte als der Wächter, wäre
schlimmer als keine.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import HTTPException

# Was ein vorgelegter Schlüssel gegenüber dem hinterlegten ist.
AUS = "aus"  # auf diesem Server nicht hinterlegt
FEHLT = "fehlt"
FALSCH = "falsch"
GILT = "gilt"


@dataclass(frozen=True)
class Schluessel:
    name: str
    kopf: str
    umgebung: str
    # Was ohne hinterlegten Schlüssel abgeschaltet ist, als Satzanfang.
    wofuer: str

    def stand(self, erwartet: str, vorgelegt: str | None) -> str:
        """`aus`, `fehlt`, `falsch` oder `gilt` - zeitkonstant über die UTF-8-Bytes verglichen."""
        if not erwartet:
            return AUS
        if not vorgelegt:
            return FEHLT
        gleich = secrets.compare_digest(vorgelegt.encode("utf-8"), erwartet.encode("utf-8"))
        return GILT if gleich else FALSCH

    def verlange(self, erwartet: str, vorgelegt: str | None) -> None:
        """Der Wächter: 401, wenn der Schlüssel nicht gilt."""
        stand = self.stand(erwartet, vorgelegt)
        if stand == AUS:
            # 401 wie beim Zugang: An einer abgeschalteten Tür ist niemand angemeldet.
            raise HTTPException(
                status_code=401,
                detail=(
                    f"{self.wofuer} ist abgeschaltet: Auf diesem Server ist kein "
                    f"{self.name} hinterlegt ({self.umgebung})."
                ),
            )
        if stand != GILT:
            raise HTTPException(status_code=401, detail=f"Falscher oder fehlender {self.name}.")


TRAINER = Schluessel(
    name="Trainerschlüssel",
    kopf="X-Trainer-Key",
    umgebung="WORTLAUT_TRAINER_KEY",
    wofuer="Training",
)
BEARBEITUNG = Schluessel(
    name="Bearbeitungsschlüssel",
    kopf="X-Editor-Key",
    umgebung="WORTLAUT_EDITOR_KEY",
    wofuer="Der Zuschnitt",
)
