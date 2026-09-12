"""Wie die Erkennung dieses Sprechers läuft: welches Modell, und wie aufbereitet.

Drei Herkünfte laufen hier zusammen, und die Reihenfolge ist die Rangfolge:

1. **Was der Sprecher gewählt hat** (`erkennung.modell_ref`, siehe
   `003_erkennung.sql`).
   Er hat sie ausdrücklich getroffen; sie gilt.
2. **`WORTLAUT_MODELL_REF`**, falls gesetzt - der eine Stand, der für alle
   gilt. Gedacht zum Erproben, nicht für den Betrieb; er sticht die Wahl
   deshalb **nicht**, sondern steht nur an ihrer Stelle, wenn keine getroffen
   wurde. Wäre es andersherum, sähe ein Sprecher eine Auswahl, die nichts tut.
3. **Der freigegebene Stand aus „lernen"** - die Vorgabe für jemanden, der nie
   etwas ausgewählt hat, und der Sinn des Freigebens.

Darunter liegt das unveränderte Grundmodell: Ohne alles davon fängt eine
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

**Warum überhaupt gewählt werden darf.** Eine Person bekommt inzwischen vier
trainierte Stände (zwei Methoden mal zwei Datensätze) und daneben die
unveränderten Grundmodelle. Welcher davon ihr am besten zuhört, beantwortet
keine Kennzahl allein - das beantwortet sich beim Diktieren. Was dabei nicht
aufgegeben wird: Zu jeder Ausgabe steht fest, welches Modell sie erzeugt hat.
Die Kopfzeile nennt es dauerhaft, samt Methode und Datensatz.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session
from wortlaut import registry

from ..config import Einstellungen
from ..db.models import Erkennung, jetzt

# Ein Stand aus der Registry heißt `<sprecher_id>/<version>`; ein Whisper-Name
# enthält keinen Schrägstrich. Daran allein sind beide zu unterscheiden - und
# das ist der Grund, warum beide im selben Feld stehen dürfen.
TRENNER = "/"


@dataclass(frozen=True)
class Wahl:
    """Ein wählbares Modell, wie die Oberfläche es anbietet."""

    ref: str
    name: str
    art: str  # grundmodell | trainiert
    beschriftung: str
    methode: str | None = None
    daten: str | None = None
    erstellt: str | None = None
    wer: float | None = None
    freigegeben: bool = False


def ist_stand(ref: str) -> bool:
    return TRENNER in ref


def aussteuern(db: Session) -> bool:
    """Ob vor dem Erkennen ausgesteuert wird. Ohne Zeile: ja.

    Die Vorgabe steckt hier und nicht nur im `DEFAULT` der Spalte: Wer nie
    etwas eingestellt hat, hat keine Zeile, und dann hinge das Verhalten daran,
    ob er die Modellwahl schon einmal angefasst hat.
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
        zeile = Erkennung(id=1, modell_ref="", aussteuern=True, geaendert=jetzt())
        db.add(zeile)
        db.flush()
    zeile.geaendert = jetzt()
    return zeile


def gewaehlt(db: Session, konfiguration: Einstellungen, sprecher_id: str) -> str:
    """Was der Sprecher gewählt hat; leer heißt: nichts, es gilt die Vorgabe.

    Zeigt die Wahl auf einen Stand, den es nicht mehr gibt, gilt sie als nicht
    getroffen - und die Zeile verschwindet. Das ist kein Verschweigen eines
    Fehlers, sondern die Auflösung eines: „lernen" kann einen Lauf samt seinem
    Modell löschen, und der Mensch, der das tut, ist derselbe, der hier
    diktiert. Ihn danach vor einer App zu lassen, die an einem verschwundenen
    Verzeichnis scheitert, wäre die schlechtere Antwort als „es gilt wieder
    die Vorgabe".

    Anders bei `WORTLAUT_MODELL_REF`: Was dort steht, hat niemand hier
    gewählt, und ein Tippfehler in der Umgebung soll sichtbar bleiben (siehe
    `deps.modellstand`).
    """
    zeile = db.get(Erkennung, 1)
    if zeile is None or not zeile.modell_ref:
        return ""
    if ist_stand(zeile.modell_ref) and not _stand_vorhanden(konfiguration, zeile.modell_ref):
        # Der Stand ist weg - „lernen" kann einen Lauf samt seinem Modell
        # löschen. Die Wahl gilt dann als nicht getroffen, statt die App an
        # einem verschwundenen Verzeichnis scheitern zu lassen.
        zeile.modell_ref = ""
        zeile.geaendert = jetzt()
        db.commit()
        return ""
    return zeile.modell_ref


def _stand_vorhanden(konfiguration: Einstellungen, ref: str) -> bool:
    sprecher_id, version = ref.split(TRENNER, 1)
    return (
        registry.stand_verzeichnis(konfiguration.data_dir, sprecher_id, version)
        / registry.MANIFEST
    ).is_file()


def waehle(db: Session, ref: str) -> None:
    """Die Modellwahl setzen. Leer setzt sie zurück auf die Vorgabe.

    Die Zeile bleibt dabei stehen, auch wenn sie danach nur noch Vorgaben
    trägt: In ihr steht inzwischen mehr als das Modell, und ein Zurücksetzen
    der Modellwahl soll nicht nebenbei das Aussteuern mit zurücksetzen.
    """
    _zeile(db).modell_ref = ref
    db.commit()


def grundmodelle(konfiguration: Einstellungen) -> list[str]:
    namen = [teil.strip() for teil in konfiguration.auswertung_modelle.split(",") if teil.strip()]
    # Das konfigurierte Grundmodell steht immer zur Wahl, auch wenn es nicht in
    # der Messreihe steht - sonst fehlte ausgerechnet das, was ohne jede Wahl
    # läuft.
    if konfiguration.asr_modell not in namen:
        namen.append(konfiguration.asr_modell)
    return namen


def _stand_wahl(manifest: dict) -> Wahl:
    metriken = manifest.get("metriken") or {}
    methode = {"full": "voll", "lora": "LoRA"}.get(str(manifest.get("methode")), "?")
    daten = {"original": "Originale", "augmentiert": "mit Abwandlungen"}.get(
        str(manifest.get("daten")), "?"
    )
    erstellt = str(manifest.get("erstellt", ""))
    grund = str(manifest.get("basismodell", "?")).rsplit("/", 1)[-1]
    return Wahl(
        ref=str(manifest.get("id", "")),
        name=str(manifest.get("id", "")).split(TRENNER, 1)[-1],
        art="trainiert",
        beschriftung=f"{grund} · {methode} · {daten} · {erstellt[:10]}",
        methode=manifest.get("methode"),
        daten=manifest.get("daten"),
        erstellt=erstellt,
        wer=metriken.get("wer"),
        freigegeben=manifest.get("status") == "active",
    )


def auswahl(konfiguration: Einstellungen, sprecher_id: str) -> list[Wahl]:
    """Alles, was dieser Sprecher laden kann - Grundmodelle zuerst.

    Grundmodelle zuerst, weil sie die Grundlinie sind: Wer vergleichen will,
    vergleicht gegen sie. Die trainierten Stände darunter, jüngster zuletzt -
    dieselbe Reihenfolge wie in „lernen", damit dieselbe Liste nicht zweimal
    verschieden aussieht.
    """
    staende = [
        _stand_wahl(manifest)
        for manifest in registry.alle_staende(konfiguration.data_dir, sprecher_id)
    ]
    return [
        *(
            Wahl(
                ref=name,
                name=name,
                art="grundmodell",
                beschriftung=f"whisper-{name} · unverändert",
            )
            for name in grundmodelle(konfiguration)
        ),
        *staende,
    ]
