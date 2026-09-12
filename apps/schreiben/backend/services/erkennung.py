"""Wie die Erkennung dieses Sprechers läuft: welches Modell, und wie aufbereitet.

Ein Modell gehört zu genau einem Menschen (Grundentscheidung 3), und wer hier
diktiert, diktiert auf seinem eigenen. Diese Auskunft hängt deshalb am Zugang
und nicht an der Konfiguration.

**Gewählt wird hier nicht.** Welches Modell gilt, entscheidet die eine
Modellübersicht in „lernen": Dort stehen die eigenen Stände und die
unveränderten Grundmodelle in einer Tabelle, an denselben Testaufnahmen
gemessen, und dort wird eines davon freigegeben (siehe
`apps/lernen/backend/api/modelle.py`). Diese App liest die Freigabe und lädt,
was darin steht.

Das war einmal anders: „schreiben" führte eine eigene Auswahlliste, „lernen"
daneben einen Freigabeknopf - zwei Ansichten für dieselbe Entscheidung, und in
keiner von beiden stand, ob das eigene Modell die Grundmodelle überhaupt
schlägt. Eine Wahl, die man nur beim Diktieren treffen kann, war das nie; sie
ließ sich nur nirgends nachschlagen.

Die Rangfolge ist damit kurz:

1. **`WORTLAUT_MODELL_REF`**, falls gesetzt - der eine Stand, der für alle
   gilt. Gedacht zum Erproben, nicht für den Betrieb.
2. **Das freigegebene Modell** dieses Sprechers - ein trainierter Stand oder
   ein unverändertes Grundmodell.
3. Darunter liegt `WORTLAUT_ASR_MODELL`: Ohne alles davon fängt eine
   Installation mit `whisper-small` an.

Daneben steht die zweite Stellschraube, das **Aussteuern**: Vor dem Erkennen
wird das Diktat lauter gerechnet, bis seine Spitze knapp unter dem Anschlag
steht - ein einziger Faktor über die ganze Aufnahme, dieselbe Abwandlung, die
„hören" als `pegel` neben jede Aufnahme legt (`wortlaut/augmentierung.py`).
Der Aufnahmepegel eines Browsers hängt am Gerät, am Abstand und an der Stimme;
bei leisen Aufnahmen schöpft Whisper den Wertebereich nicht aus, den seine
Merkmalsberechnung erwartet, und gerade die kleineren Modelle hören mit
Aussteuerung merklich besser. Deshalb ist es die Vorgabe - und deshalb bleibt
es abschaltbar: Wer eine gut ausgesteuerte Kette hat, gewinnt nichts mehr.

**Aufbereitet wird nur, was Whisper hört.** Abgelegt und später an „hören"
gegeben wird die Aufnahme, wie sie gesprochen wurde. Das ist kein Detail: Aus
einer bestätigten Korrektur wird drüben eine Aufnahme im Korpus, und „hören"
rechnet aus ihr selbst eine ausgesteuerte Fassung. Läge hier schon eine
ausgesteuerte als „Original", wäre die Abwandlung dort ein Nichts - und der
Vergleich der vier Fassungen für genau diese Aufnahmen stillschweigend
entwertet.
"""

from __future__ import annotations

from sqlalchemy.orm import Session
from wortlaut import registry

from ..db.models import Erkennung, jetzt

# Ein Stand aus der Registry heißt `<sprecher_id>/<version>`; ein Whisper-Name
# enthält keinen Schrägstrich. Unterschieden wird das an einer einzigen Stelle -
# in der Registry, weil dort beide Schreibweisen entstehen.
ist_stand = registry.ist_stand


def aussteuern(db: Session) -> bool:
    """Ob vor dem Erkennen ausgesteuert wird. Ohne Zeile: ja.

    Die Vorgabe steckt hier und nicht nur im `DEFAULT` der Spalte: Wer nie
    etwas eingestellt hat, hat keine Zeile, und dann hinge das Verhalten daran,
    ob der Schalter schon einmal angefasst wurde.
    """
    zeile = db.get(Erkennung, 1)
    return True if zeile is None else bool(zeile.aussteuern)


def setze_aussteuern(db: Session, an: bool) -> None:
    _zeile(db).aussteuern = an
    db.commit()


def _zeile(db: Session) -> Erkennung:
    """Die eine Zeile, angelegt, falls es sie noch nicht gibt."""
    zeile = db.get(Erkennung, 1)
    if zeile is None:
        # `modell_ref` bleibt leer: Die Spalte stammt aus der Zeit, als hier
        # gewählt wurde, und wird von nichts mehr gelesen (siehe oben).
        zeile = Erkennung(id=1, modell_ref="", aussteuern=True, geaendert=jetzt())
        db.add(zeile)
        db.flush()
    zeile.geaendert = jetzt()
    return zeile
