"""Läufe beauftragen und ihnen zusehen.

* `GET  /lernen/api/laeufe`          die Liste, abgefragt im Takt - ohne Kurven.
* `GET  /lernen/api/laeufe/{id}`     ein Lauf: Kurven, Bewertung, Baseline.
* `POST /lernen/api/laeufe`          beauftragen - mit Trainerschlüssel.
* `POST /lernen/api/laeufe/{id}/abbruch`  anhalten.
* `POST /lernen/api/laeufe/{id}/neustart` neu starten - mit Trainerschlüssel.
* `DELETE /lernen/api/laeufe/{id}`   löschen, samt Stand.

Gerechnet wird im Trainer-Container; hier entsteht nur das Verzeichnis
(`wortlaut/laeufe.py`).
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from wortlaut import kartenplan, laeufe as lauf_layout, registry, schluessel

from ..config import einstellungen
from ..deps import Korpus, Sprache, SprecherId
from ..services import aufteilung, auftraege, vergleich

router = APIRouter(prefix="/lernen/api/laeufe", tags=["Läufe"])

def _pruefe_trainerschluessel(
    vorgelegt: Annotated[str | None, Header(alias=schluessel.TRAINER.kopf)] = None,
) -> None:
    """Wächter der Wege, die die Karte belegen - und des Löschens von Läufen samt Modell.

    Der Sprecherzugang sagt „wessen Modell", nicht „wer darf rechnen lassen".
    Wer trainieren darf, darf auch wegwerfen; alle anderen sehen nur zu.
    """
    schluessel.TRAINER.verlange(einstellungen().trainer_key, vorgelegt)


def _gewichtstext(gewicht: float) -> str:
    """`0.25` → `0,25`."""
    return f"{gewicht:g}".replace(".", ",")


class WahlAntwort(BaseModel):
    """Eine Wahlmöglichkeit beim Beauftragen - Schlüssel, Name, Kurzbeschreibung.

    `code` ist ihr Glied im Optionscode (`lauf_layout.optionscode`), leer bei
    der Vorgabe einer Achse.
    """

    schluessel: str
    name: str
    erklaerung: str
    code: str = ""


METHODEN = [
    WahlAntwort(
        schluessel=lauf_layout.VOLL,
        name="Volles Feintuning",
        erklaerung="Alle Gewichte trainierbar.",
        code=lauf_layout.CODE_METHODE[lauf_layout.VOLL],
    ),
    WahlAntwort(
        schluessel=lauf_layout.LORA,
        name="LoRA",
        erklaerung="Low-Rank-Adapter, Grundmodell eingefroren.",
        code=lauf_layout.CODE_METHODE[lauf_layout.LORA],
    ),
]

# Nur bei LoRA (`training/adapter.py`).
LORA_ZIELE = [
    WahlAntwort(
        schluessel=lauf_layout.ZIELE_QV,
        name="q, v",
        erklaerung="q_proj und v_proj der Aufmerksamkeit, in Encoder und Decoder.",
        code=lauf_layout.CODE_LORA_ZIELE[lauf_layout.ZIELE_QV],
    ),
    WahlAntwort(
        schluessel=lauf_layout.ZIELE_ALLE,
        name="Alle Projektionen",
        erklaerung="q, k, v, out_proj, fc1, fc2 in Encoder und Decoder.",
        code=lauf_layout.CODE_LORA_ZIELE[lauf_layout.ZIELE_ALLE],
    ),
    WahlAntwort(
        schluessel=lauf_layout.ZIELE_ENCODER,
        name="Nur Encoder",
        erklaerung="Alle Projektionen, nur im Encoder - die Aussprache.",
        code=lauf_layout.CODE_LORA_ZIELE[lauf_layout.ZIELE_ENCODER],
    ),
    WahlAntwort(
        schluessel=lauf_layout.ZIELE_DECODER,
        name="Nur Decoder",
        erklaerung="Alle Projektionen, nur im Decoder - der Wortschatz.",
        code=lauf_layout.CODE_LORA_ZIELE[lauf_layout.ZIELE_DECODER],
    ),
]

LORA_RAENGE = [
    WahlAntwort(
        schluessel=rang,
        name=f"Rang {rang}",
        erklaerung={
            lauf_layout.RANG_VORGABE: "",
            "8": "Kleiner Zusatz, weniger Freiheit.",
            "64": "Größerer Zusatz, näher am vollen Training.",
        }.get(rang, ""),
        code=lauf_layout.CODE_LORA_RANG[rang],
    )
    for rang in lauf_layout.LORA_RAENGE
]

AUSWAHLEN = [
    WahlAntwort(
        schluessel=lauf_layout.AUSWAHL_ALLE,
        name="Alle Aufnahmen",
        erklaerung="",
        code=lauf_layout.CODE_AUSWAHL[lauf_layout.AUSWAHL_ALLE],
    ),
    WahlAntwort(
        schluessel=lauf_layout.AUSWAHL_KERN,
        name="Kernauswahl",
        erklaerung=(
            f"Gelernt nur auf den besten {round(lauf_layout.KERN_ANTEIL * 100)} % "
            "nach WER des freigegebenen Modells. Die übrigen sieht der Lauf nicht; "
            "sie hört erst das Endmodell in der Auswertung von „hören“."
        ),
        code=lauf_layout.CODE_AUSWAHL[lauf_layout.AUSWAHL_KERN],
    ),
]


KORREKTURGEWICHTE = [
    WahlAntwort(
        schluessel=gewicht,
        name=f"Gewicht {gewicht.replace('.', ',')}",
        erklaerung="Korrekturen zählen wie Vorlagen." if gewicht == "1.0" else "",
        code=lauf_layout.CODE_KORREKTURGEWICHT[gewicht],
    )
    for gewicht in lauf_layout.KORREKTURGEWICHTE
    if gewicht != lauf_layout.GEWICHT_VERLAUF
] + [
    WahlAntwort(
        schluessel=lauf_layout.GEWICHT_VERLAUF,
        name="Aus dem Verlauf",
        erklaerung=(
            f"Unverändert bestätigt {_gewichtstext(auftraege.GEWICHT_UNVERAENDERT)}, "
            f"nachgesprochen {_gewichtstext(auftraege.GEWICHT_NACHGESPROCHEN)}."
        ),
        code=lauf_layout.CODE_KORREKTURGEWICHT[lauf_layout.GEWICHT_VERLAUF],
    )
]


SELBSTTRAININGE = [
    WahlAntwort(
        schluessel=lauf_layout.SELBST_AUS,
        name="Aus",
        erklaerung="",
        code=lauf_layout.CODE_SELBSTTRAINING[lauf_layout.SELBST_AUS],
    ),
    WahlAntwort(
        schluessel=lauf_layout.SELBST_AN,
        name="Unbestätigte Diktate",
        erklaerung=(
            "Das freigegebene Modell beschriftet sie; was es sicher hört, lernt mit "
            f"Gewicht {_gewichtstext(auftraege.GEWICHTE[lauf_layout.QUELLE_SELBST])} mit."
        ),
        code=lauf_layout.CODE_SELBSTTRAINING[lauf_layout.SELBST_AN],
    ),
]


ABSCHLUESSE = [
    WahlAntwort(
        schluessel=lauf_layout.ABSCHLUSS_BESTER,
        name="Bester Checkpoint",
        erklaerung="Bester Wert der Steuergröße.",
        code=lauf_layout.CODE_ABSCHLUSS[lauf_layout.ABSCHLUSS_BESTER],
    ),
    WahlAntwort(
        schluessel=lauf_layout.ABSCHLUSS_MITTEL,
        name="Checkpoint-Mittel",
        erklaerung="Die besten Checkpoints elementweise gemittelt (Model Soup).",
        code=lauf_layout.CODE_ABSCHLUSS[lauf_layout.ABSCHLUSS_MITTEL],
    ),
    WahlAntwort(
        schluessel=lauf_layout.ABSCHLUSS_INTERPOLIERT,
        name="WiSE-FT",
        erklaerung="α·θ_Grund + (1−α)·θ_fein, α auf der Validierung gewählt.",
        code=lauf_layout.CODE_ABSCHLUSS[lauf_layout.ABSCHLUSS_INTERPOLIERT],
    ),
    WahlAntwort(
        schluessel=lauf_layout.ABSCHLUSS_BEIDES,
        name="Checkpoint-Mittel + WiSE-FT",
        erklaerung="",
        code=lauf_layout.CODE_ABSCHLUSS[lauf_layout.ABSCHLUSS_BEIDES],
    ),
]


AUGMENTIERUNGEN = [
    WahlAntwort(
        schluessel=lauf_layout.AUG_KEINE,
        name="Keine",
        erklaerung="",
        code=lauf_layout.CODE_AUGMENTIERUNG[lauf_layout.AUG_KEINE],
    ),
    WahlAntwort(
        schluessel=lauf_layout.AUG_MASKEN,
        name="SpecAugment",
        erklaerung="Zeit- und Frequenzmasken im Spektrogramm.",
        code=lauf_layout.CODE_AUGMENTIERUNG[lauf_layout.AUG_MASKEN],
    ),
    WahlAntwort(
        schluessel=lauf_layout.AUG_UMGEBUNG,
        name="+ Raum + Rauschen",
        erklaerung="Dazu Nachhall und Hintergrundrauschen auf der Welle.",
        code=lauf_layout.CODE_AUGMENTIERUNG[lauf_layout.AUG_UMGEBUNG],
    ),
    WahlAntwort(
        schluessel=lauf_layout.AUG_VOLL,
        name="+ Tempo-Perturbation",
        erklaerung="Dazu Abspieltempo 0,9–1,1×.",
        code=lauf_layout.CODE_AUGMENTIERUNG[lauf_layout.AUG_VOLL],
    ),
]


DAUERN = [
    WahlAntwort(
        schluessel=lauf_layout.DAUER_FEST,
        name="Feste Epochenzahl",
        erklaerung="Epochen laut Rezept.",
        code=lauf_layout.CODE_DAUER[lauf_layout.DAUER_FEST],
    ),
    WahlAntwort(
        schluessel=lauf_layout.DAUER_GEDULDIG,
        name="Early Stopping",
        erklaerung="Höhere Obergrenze, Abbruch ohne Verbesserung der Validierung.",
        code=lauf_layout.CODE_DAUER[lauf_layout.DAUER_GEDULDIG],
    ),
]


STEUERUNGEN = [
    WahlAntwort(
        schluessel=lauf_layout.STEUERUNG_VERLUST,
        name="Validierungsverlust",
        erklaerung="Geprüft je Durchgang.",
        code=lauf_layout.CODE_STEUERUNG[lauf_layout.STEUERUNG_VERLUST],
    ),
    WahlAntwort(
        schluessel=lauf_layout.STEUERUNG_WER,
        name="WER",
        erklaerung="Frei dekodiert, geprüft je Drittel eines Durchgangs.",
        code=lauf_layout.CODE_STEUERUNG[lauf_layout.STEUERUNG_WER],
    ),
]


FENSTER = [
    WahlAntwort(
        schluessel=lauf_layout.FENSTER_VOLL,
        name="30 Sekunden",
        erklaerung="",
        code=lauf_layout.CODE_FENSTER[lauf_layout.FENSTER_VOLL],
    ),
    WahlAntwort(
        schluessel=lauf_layout.FENSTER_GEKUERZT,
        name="Gekürzt",
        erklaerung=(
            "Im Training auf die längste Aufnahme gekürzt; ausgeliefert und gemessen "
            "mit 30 Sekunden."
        ),
        code=lauf_layout.CODE_FENSTER[lauf_layout.FENSTER_GEKUERZT],
    ),
]


TEMPI = [
    WahlAntwort(
        schluessel=lauf_layout.TEMPO_AUS,
        name="Aus",
        erklaerung="",
        code=lauf_layout.CODE_TEMPO[lauf_layout.TEMPO_AUS],
    ),
    WahlAntwort(
        schluessel=lauf_layout.TEMPO_GESCHAETZT,
        name="Geschätzt",
        erklaerung="Aufnahmedauer / geschätzte Sprechdauer, je Faltung, auf 0,25 gerundet.",
        code=lauf_layout.CODE_TEMPO[lauf_layout.TEMPO_GESCHAETZT],
    ),
    WahlAntwort(
        schluessel=lauf_layout.TEMPO_OPTIMAL,
        name="Gesucht",
        erklaerung="WER-Minimum über 0,75–4,0× am Grundmodell, je Faltung.",
        code=lauf_layout.CODE_TEMPO[lauf_layout.TEMPO_OPTIMAL],
    ),
]


KONTEXTE = [
    WahlAntwort(
        schluessel=lauf_layout.KONTEXT_AUS,
        name="Aus",
        erklaerung="",
        code=lauf_layout.CODE_KONTEXT[lauf_layout.KONTEXT_AUS],
    ),
    WahlAntwort(
        schluessel=lauf_layout.KONTEXT_VOKABULAR,
        name="Vokabular",
        erklaerung=(
            "Startprompt mit den seltenen Wörtern der Lerntexte - je Faltung nur ihren; "
            "gilt überall, wo der Stand hört."
        ),
        code=lauf_layout.CODE_KONTEXT[lauf_layout.KONTEXT_VOKABULAR],
    ),
]


class GrundmodellAntwort(BaseModel):
    """Ein Grundmodell zur Wahl - und was es verträgt.

    `methoden`, damit die Oberfläche nichts anbietet, was am Speicher der
    Karte scheitert (volles Feintuning von `medium`).
    """

    schluessel: str
    name: str
    erklaerung: str
    methoden: list[str]
    # Die LoRA-Zusätze, die passen, als `ziele/rang` (`kartenplan.lora_passt`).
    lora: list[str]
    code: str


def _grundmodelle() -> list[GrundmodellAntwort]:
    konfiguration = einstellungen()
    antworten = []
    for modell in konfiguration.grundmodelle():
        kurz = lauf_layout.kurzname(modell)
        antworten.append(
            GrundmodellAntwort(
                schluessel=modell,
                name=f"whisper-{kurz}",
                # Welche Methoden passen, steht daneben - auf dieser Karte.
                erklaerung=f"{kartenplan.parameter(kurz) / 1e6:.0f} M Parameter.",
                methoden=list(konfiguration.methoden_fuer(modell)),
                lora=konfiguration.lora_fuer(modell),
                code=lauf_layout.grundmodellcode(modell),
            )
        )
    return antworten


class Bestellung(BaseModel):
    methode: str
    # Nur bei LoRA; bei vollem Training die Vorgaben.
    lora_ziele: str = lauf_layout.ZIELE_QV
    lora_rang: str = lauf_layout.RANG_VORGABE
    # Die übrigen Achsen mit ihren Vorgaben.
    abschluss: str = lauf_layout.ABSCHLUSS_BESTER
    augmentierung: str = lauf_layout.AUG_KEINE
    dauer: str = lauf_layout.DAUER_FEST
    steuerung: str = lauf_layout.STEUERUNG_VERLUST
    fenster: str = lauf_layout.FENSTER_VOLL
    tempowahl: str = lauf_layout.TEMPO_AUS
    kontext: str = lauf_layout.KONTEXT_AUS
    # Leer: die Vorgabe des Servers.
    grundmodell: str = ""
    auswahl: str = lauf_layout.AUSWAHL_ALLE
    korrekturgewicht: str = lauf_layout.GEWICHT_VORGABE
    selbsttraining: str = lauf_layout.SELBST_AUS


class StandHinweis(BaseModel):
    """Was mit einem Lauf verschwände - für die Sicherheitsabfrage, ohne Nachfrage."""

    version: str
    freigegeben: bool


class LaufAntwort(BaseModel):
    job_id: str
    sprecher_id: str
    # Der Titel des Laufs: alle Achsen als Optionscode, dahinter die Folge
    # (`/43b`, `lauf_layout.titel`).
    code: str
    methode: str
    # Ob der Lauf auch auf Rauschkopien lernte (`lauf_layout.MIT_RAUSCHKOPIE`).
    rauschkopie: bool = False
    # Die Achsen; fehlt eine im Auftrag, galt ihre Vorgabe.
    lora_ziele: str = lauf_layout.ZIELE_QV
    lora_rang: str = lauf_layout.RANG_VORGABE
    auswahl: str = lauf_layout.AUSWAHL_ALLE
    korrekturgewicht: str = lauf_layout.GEWICHT_VORGABE
    selbsttraining: str = lauf_layout.SELBST_AUS
    abschluss: str
    augmentierung: str
    dauer: str
    steuerung: str = lauf_layout.STEUERUNG_VERLUST
    fenster: str = lauf_layout.FENSTER_VOLL
    tempowahl: str = lauf_layout.TEMPO_AUS
    kontext: str = lauf_layout.KONTEXT_AUS
    # Das Tempo, mit dem gerechnet wurde; `null`, solange die Suche läuft.
    tempo: float | None = None
    # Während der Suche der Median des bisher Gefundenen - dann `false`.
    tempo_endgueltig: bool = True
    # Das Whisper-Modell darunter - gegen das misst die Baseline.
    basismodell: str
    erstellt: str
    status: str
    # Woran gerade gearbeitet wird: laden, tempowahl, training, abschluss,
    # sichern, umwandeln, bewerten.
    stufe: str
    # Die Faltung, die gerade rechnet (ab 0); `null`: das Endmodell.
    faltung: int | None = None
    faltungen_gesamt: int = lauf_layout.FALTUNGEN
    # 0 bis 1; `null`, solange die Schrittzahl unbekannt ist.
    anteil: float | None
    aufnahmen: int
    zeilen: dict[str, int]
    # Worauf gelernt wird (`lauf_layout.umfang`). Beim Kern vor der Wahl
    # geschätzt - dann `trainingsproben_geschaetzt`.
    trainingsproben: int = 0
    trainingsproben_geschaetzt: bool = False
    # Beim Kern: auf wie vielen Aufnahmen, schon vor der Wahl
    # (`services/kernauswahl.py`); `null`: auf allen.
    kern_aufnahmen: int | None = None
    # Was der Trainer vor der Wahl nachmessen muss.
    kern_offen: int = 0
    version: str | None
    # Der kurze Code seines Standes (`registry.kurzkennung`).
    kennung: str | None = None
    fehler: str | None
    # Der Stand aus diesem Lauf; ginge beim Löschen mit.
    stand: StandHinweis | None
    # Nicht, solange er rechnet; ein hängender schon.
    loeschbar: bool
    # Sagt `laeuft`, rührt sich aber nicht (`wortlaut/laeufe.py`).
    haengt: bool
    # Sekunden ohne Schreiben, nur bei `laeuft`.
    stillstand_s: float | None
    # Anhalten verlangt, der Prozess läuft noch.
    wird_angehalten: bool = False
    neu_startbar: bool = False


class PunktAntwort(BaseModel):
    schritt: int
    epoche: float
    verlust: float | None = None
    lernrate: float | None = None
    wer: float | None = None


class GegenueberAntwort(BaseModel):
    mass: str
    baseline: float | None
    trainiert: float | None
    besser: bool | None
    anzahl: int


class EinzelAntwort(BaseModel):
    lauf: LaufAntwort
    # Jede Achse benannt, auch die auf Vorgabe (`steckbrief`).
    steckbrief: list[SteckbriefZeile]
    methoden: list[WahlAntwort]
    lora_ziele: list[WahlAntwort]
    lora_raenge: list[WahlAntwort]
    auswahlen: list[WahlAntwort]
    korrekturgewichte: list[WahlAntwort]
    selbsttraininge: list[WahlAntwort]
    abschluesse: list[WahlAntwort]
    augmentierungen: list[WahlAntwort]
    dauern: list[WahlAntwort]
    steuerungen: list[WahlAntwort]
    fenster: list[WahlAntwort]
    tempi: list[WahlAntwort]
    kontexte: list[WahlAntwort]
    grundmodelle: list[GrundmodellAntwort]
    kurve_training: list[PunktAntwort]
    kurve_validierung: list[PunktAntwort]
    # je Maß Baseline und trainiert
    vergleich: list[GegenueberAntwort]
    protokoll: str


class ListeAntwort(BaseModel):
    laeufe: list[LaufAntwort]
    methoden: list[WahlAntwort]
    lora_ziele: list[WahlAntwort]
    lora_raenge: list[WahlAntwort]
    auswahlen: list[WahlAntwort]
    korrekturgewichte: list[WahlAntwort]
    selbsttraininge: list[WahlAntwort]
    abschluesse: list[WahlAntwort]
    augmentierungen: list[WahlAntwort]
    dauern: list[WahlAntwort]
    steuerungen: list[WahlAntwort]
    fenster: list[WahlAntwort]
    tempi: list[WahlAntwort]
    kontexte: list[WahlAntwort]
    grundmodelle: list[GrundmodellAntwort]
    basismodell: str
    # Vom Server, damit die Oberfläche die Zahl nicht selbst kennt.
    faltungen: int
    # Ob beauftragt werden kann, sonst warum nicht: zu wenige Aufnahmen oder
    # kein Trainerschlüssel.
    bereit: bool
    hinweis: str
    # Brauchbare Aufnahmen, und wie viele der jüngste fertige Lauf nicht
    # kannte - zeigt, wann ein Lauf sich lohnt. Von selbst trainiert wird nie:
    # Wer rechnen lassen will, sagt es.
    aufnahmen_jetzt: int
    aufnahmen_neu: int


# Grobe Anteile der Stufen an einem Training, in ihrer Reihenfolge -
# geschätzt: Für einen gleichmäßigen Balken genügen Größenordnungen.
STUFENFOLGE: tuple[tuple[str, float], ...] = (
    ("laden", 0.10),
    ("tempowahl", 0.15),
    ("training", 0.50),
    ("abschluss", 0.10),
    ("sichern", 0.03),
    ("umwandeln", 0.05),
    ("bewerten", 0.07),
)

# Das Endmodell trainiert nicht, es mittelt die Faltungen (`training/endmodell.py`).
ENDSTUFEN: tuple[tuple[str, float], ...] = (
    ("mitteln", 0.4),
    ("umwandeln", 0.2),
    ("bewerten", 0.4),
)

# Stufen, die in sich weiterzählen; bei den übrigen steht der Balken am Anfang der Stufe.
MIT_SCHRITTEN = frozenset({"training", "tempowahl"})


def _anteil(lauf: lauf_layout.Lauf) -> float | None:
    """Wie weit der **ganze Lauf** ist - von 0 bis 1, und nie rückwärts.

    Ein Lauf rechnet sechs Faltungen, jede mit eigenem Schrittzähler, und
    mittelt sie zum Endmodell. Jede Faltung und das Endmodell bekommen
    denselben Anteil, darin die Stufen nach `STUFENFOLGE` bzw. `ENDSTUFEN`;
    was eine Faltung nicht durchläuft (Tempowahl), fällt heraus, damit der
    Balken nicht springt.

    Monoton, weil `finetune.py` die Stufen in dieser Reihenfolge aufruft. Ein
    unbekannter Stufenname zählt als „noch nicht begonnen".
    """
    zustand = lauf.zustand
    if lauf.status == lauf_layout.FERTIG:
        return 1.0
    if lauf.status != lauf_layout.LAEUFT:
        return None

    trainings = lauf_layout.FALTUNGEN + 1
    # Ohne Schlüssel hat keine Faltung begonnen; `None` ist das Endmodell.
    endmodell = "faltung" in zustand and zustand.get("faltung") is None
    nummer = trainings - 1 if endmodell else int(zustand.get("faltung") or 0)

    sucht = lauf_layout.tempowahl_aus(lauf.auftrag) == lauf_layout.TEMPO_OPTIMAL
    stufen = (
        list(ENDSTUFEN)
        if endmodell
        else [
            (name, gewicht)
            for name, gewicht in STUFENFOLGE
            if name != "tempowahl" or sucht
        ]
    )
    summe = sum(gewicht for _name, gewicht in stufen)

    jetzt = str(zustand.get("stufe", ""))
    davor = 0.0
    innen = 0.0
    for name, gewicht in stufen:
        if name != jetzt:
            davor += gewicht
            continue
        if name in MIT_SCHRITTEN:
            gesamt = float(zustand.get("schritte_gesamt") or 0)
            schritt = float(zustand.get("schritt") or 0)
            innen = gewicht * min(1.0, schritt / gesamt) if gesamt else 0.0
        break
    else:
        # Unbekannte Stufe („vorbereiten" etwa): am Anfang.
        davor = 0.0

    im_training = (davor + innen) / summe if summe else 0.0
    return min(1.0, (nummer + im_training) / trainings)


def _stand_zu(lauf: lauf_layout.Lauf) -> StandHinweis | None:
    datenverzeichnis = einstellungen().data_dir
    stand = registry.stand_zu_lauf(datenverzeichnis, lauf.sprecher_id, lauf.job_id)
    if stand is None:
        return None
    return StandHinweis(
        version=str(stand.get("id", "/")).split("/", 1)[-1],
        # Die Freigabedatei sagt, was gilt (`wortlaut/registry.py`).
        freigegeben=registry.freigegeben(datenverzeichnis, lauf.sprecher_id)
        == str(stand.get("id", "")),
    )


def _marke(pfad: Path) -> float:
    try:
        return pfad.stat().st_mtime
    except OSError:
        return 0.0


@lru_cache(maxsize=256)
def _umfang_gemerkt(
    verzeichnis: Path, auswahl: str, _marken: tuple[float, ...]
) -> lauf_layout.Umfang | None:
    return lauf_layout.umfang(verzeichnis, {"auswahl": auswahl})


def _umfang(lauf: lauf_layout.Lauf, auswahl: str | None = None) -> lauf_layout.Umfang | None:
    """`lauf_layout.umfang`, gemerkt, bis sich Manifest, Kern oder Selbstbeschriftung ändern.

    Die Übersicht fragt ihn für jeden Lauf bei jedem Abruf.
    """
    marken = tuple(
        _marke(lauf.verzeichnis / name)
        for name in (lauf_layout.MANIFEST, lauf_layout.KERNAUSWAHL, lauf_layout.SELBSTBESCHRIFTUNG)
    )
    return _umfang_gemerkt(
        lauf.verzeichnis, auswahl or lauf_layout.auswahl_aus(lauf.auftrag), marken
    )


def _kernumfang(lauf: lauf_layout.Lauf) -> dict[str, int]:
    """Auf wie vielen Aufnahmen ein Kernlauf lernt - leer bei allen."""
    if lauf_layout.auswahl_aus(lauf.auftrag) != lauf_layout.AUSWAHL_KERN:
        return {}
    inhalt = lauf_layout.lies_json(lauf.verzeichnis / lauf_layout.KERNAUSWAHL) or {}
    aufnahmen = int(lauf.auftrag.get("aufnahmen", 0))
    if "kern" in inhalt:
        anzahl = len(inhalt["kern"])
    else:
        anzahl = int(inhalt.get("anzahl") or lauf_layout.kern_anzahl(aufnahmen))
    return {
        "kern_aufnahmen": anzahl,
        "kern_offen": 0 if "kern" in inhalt else len(inhalt.get("offen") or []),
    }


def _trainingsproben(lauf: lauf_layout.Lauf) -> dict[str, int | bool]:
    """Worauf gelernt wird - beim Kern vor der Wahl anteilig aus allen geschätzt."""
    umfang = _umfang(lauf)
    if umfang is not None:
        return {"trainingsproben": umfang.lernproben}
    alle = _umfang(lauf, lauf_layout.AUSWAHL_ALLE)
    aufnahmen = int(lauf.auftrag.get("aufnahmen", 0))
    anzahl = int(_kernumfang(lauf).get("kern_aufnahmen", aufnahmen))
    return {
        "trainingsproben": alle.lernproben * anzahl // aufnahmen if alle and aufnahmen else 0,
        "trainingsproben_geschaetzt": True,
    }


def _als_antwort(lauf: lauf_layout.Lauf) -> LaufAntwort:
    return LaufAntwort(
        job_id=lauf.job_id,
        sprecher_id=lauf.sprecher_id,
        code=lauf_layout.titel(lauf.auftrag),
        methode=str(lauf.auftrag.get("methode", "")),
        rauschkopie=lauf_layout.mit_rauschkopie(lauf.auftrag),
        lora_ziele=lauf_layout.lora_ziele_aus(lauf.auftrag),
        lora_rang=lauf_layout.lora_rang_aus(lauf.auftrag),
        auswahl=lauf_layout.auswahl_aus(lauf.auftrag),
        korrekturgewicht=lauf_layout.korrekturgewicht_aus(lauf.auftrag),
        selbsttraining=lauf_layout.selbsttraining_aus(lauf.auftrag),
        abschluss=str(lauf.auftrag.get("abschluss") or lauf_layout.ABSCHLUSS_BESTER),
        augmentierung=str(lauf.auftrag.get("augmentierung") or lauf_layout.AUG_KEINE),
        dauer=str(lauf.auftrag.get("dauer") or lauf_layout.DAUER_FEST),
        steuerung=lauf_layout.steuerung_aus(lauf.auftrag),
        fenster=lauf_layout.fenster_aus(lauf.auftrag),
        tempowahl=lauf_layout.tempowahl_aus(lauf.auftrag),
        kontext=lauf_layout.kontext_aus(lauf.auftrag),
        tempo=_tempo_des_laufs(lauf),
        tempo_endgueltig=bool(lauf.zustand.get("tempo_endgueltig", True)),
        basismodell=str(lauf.auftrag.get("basismodell", "")),
        erstellt=str(lauf.auftrag.get("erstellt", "")),
        status=lauf.status,
        stufe=str(lauf.zustand.get("stufe", "")),
        faltung=lauf.zustand.get("faltung"),
        faltungen_gesamt=int(lauf.zustand.get("faltungen_gesamt", lauf_layout.FALTUNGEN)),
        anteil=_anteil(lauf),
        aufnahmen=int(lauf.auftrag.get("aufnahmen", 0)),
        zeilen=dict(lauf.auftrag.get("zeilen", {})),
        **_trainingsproben(lauf),
        **_kernumfang(lauf),
        version=lauf.zustand.get("version"),
        kennung=(
            registry.kurzkennung(str(lauf.zustand["version"]))
            if lauf.zustand.get("version")
            else None
        ),
        fehler=lauf.zustand.get("fehler"),
        stand=_stand_zu(lauf),
        loeschbar=lauf.status != lauf_layout.LAEUFT or lauf.haengt,
        wird_angehalten=lauf.status == lauf_layout.LAEUFT
        and lauf_layout.anhalten_verlangt(lauf.verzeichnis),
        neu_startbar=lauf.status in auftraege.NEU_STARTBAR,
        haengt=lauf.haengt,
        stillstand_s=(
            round(lauf.stillstand_s) if lauf.status == lauf_layout.LAEUFT else None
        ),
    )


class SteckbriefZeile(BaseModel):
    """Ein Feld des Steckbriefs: Begriff, Wert, und wo nötig eine Erläuterung."""

    begriff: str
    wert: str
    # Einheit, Herkunft oder Vorbehalt.
    hinweis: str = ""
    # `zeit`: `wert` ist ISO 8601, die Ansicht formatiert in der Zeitzone des
    # Lesers (`packages/ui/zeit.ts`).
    art: str = ""


def _dauer_lesbar(von: str, bis: str) -> str:
    """`2026-09-14T08:52:23+00:00` bis `…10:15:36+00:00` → `1 h 23 min`."""
    try:
        anfang = datetime.fromisoformat(von)
        ende = datetime.fromisoformat(bis)
    except (TypeError, ValueError):
        return ""
    return lauf_layout.dauer_text((ende - anfang).total_seconds())


def _wahlname(liste: list[WahlAntwort], schluessel: str) -> str:
    """Der Name einer Achsenwahl, sonst der Schlüssel."""
    for wahl in liste:
        if wahl.schluessel == schluessel:
            return wahl.name
    return schluessel


# Was eine Augmentierungsstufe tut. Die Wahlnamen („+ Tempo") beschreiben den
# Schritt zur Stufe darunter; im Steckbrief steht eine allein
# (`training/klangwandel.py`).
AUGMENTIERUNG_GRIFFE = {
    lauf_layout.AUG_KEINE: "keine",
    lauf_layout.AUG_MASKEN: "SpecAugment",
    lauf_layout.AUG_UMGEBUNG: "SpecAugment + Raum + Rauschen",
    lauf_layout.AUG_VOLL: "SpecAugment + Raum + Rauschen + Tempo",
}


def _manifest_zu(lauf: lauf_layout.Lauf) -> dict:
    """Das Manifest des Standes, der aus diesem Lauf entstand - oder leer.

    Dort steht, womit gerechnet wurde; im Lauf nur, was bestellt war.
    """
    version = str(lauf.zustand.get("version") or "")
    if not version:
        return {}
    try:
        return registry.lies_stand(einstellungen().data_dir, lauf.sprecher_id, version)
    except (OSError, ValueError):
        return {}


def _zahl(wert: float | int | None, stellen: int = 2) -> str:
    """Eine Zahl deutsch geschrieben, ohne überflüssige Nullen: `1,75`, `12`."""
    if wert is None:
        return ""
    text = f"{float(wert):.{stellen}f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _abschlusstext(manifest: dict) -> str:
    """Was der Abschluss **getan** hat - nicht, wie die Achse heißt.

    Über wie viele Stände gemittelt, welches α gewählt, oder zurückgenommen.
    """
    bericht = manifest.get("abschluss_bericht") or {}
    art = str(bericht.get("art") or manifest.get("abschluss") or lauf_layout.ABSCHLUSS_BESTER)
    if bericht.get("zurueckgenommen"):
        return "zurückgenommen - der beste Durchgang war besser"
    if art == lauf_layout.ABSCHLUSS_BESTER:
        return "bester Durchgang"

    teile = []
    staende = list(bericht.get("staende") or [])
    if staende:
        teile.append(f"Mittel aus {len(staende)} Ständen")
    alpha = bericht.get("alpha")
    if alpha is not None:
        teile.append(f"α = {_zahl(alpha)} Grundmodell")
    return ", ".join(teile) or _wahlname(ABSCHLUESSE, art)


def _auswahl_im_steckbrief(lauf: lauf_layout.Lauf) -> tuple[str, str]:
    """Die Auswahl als Wert und Hinweis: beim Kern wie viele, nach wem, bis wohin."""
    auswahl = lauf_layout.auswahl_aus(lauf.auftrag)
    name = _wahlname(AUSWAHLEN, auswahl)
    if auswahl != lauf_layout.AUSWAHL_KERN:
        return name, ""
    inhalt = lauf_layout.lies_json(lauf.verzeichnis / lauf_layout.KERNAUSWAHL) or {}
    alle = len(inhalt.get("wer") or {}) + len(inhalt.get("offen") or [])
    modell = str(inhalt.get("modell") or "")
    offen = len(inhalt.get("offen") or [])
    nachgemessen = len(inhalt.get("nachgemessen") or [])
    if "kern" in inhalt:
        umfang = f"{len(inhalt['kern'])} von {alle} Aufnahmen"
    else:
        umfang = f"{inhalt.get('anzahl', 0)} von {alle} Aufnahmen"
    teile = [
        umfang if alle else "",
        f"nach {registry.beschriftung(modell)}" if modell else "",
        f"WER bis {_zahl(inhalt['schwelle'])}" if inhalt.get("schwelle") is not None else "",
        f"{offen} vor dem Training nachzumessen" if offen else "",
        f"{nachgemessen} davon nachgemessen" if nachgemessen else "",
    ]
    return name, " · ".join(teil for teil in teile if teil)


def _endmodell_im_steckbrief(manifest: dict) -> tuple[str, str]:
    """Wie viele Faltungen gemittelt sind - und welche warum fehlen."""
    befund = dict(manifest.get("endmodell") or {})
    if not befund:
        return "", ""
    gemittelt = list(befund.get("faltungen") or [])
    ausgelassen = list(befund.get("ausgelassen") or [])
    GRUENDE = {
        "abgebrochen": "abgebrochen",
        "ausgefranst": "ausgefranst",
        "ausreisser": "weit hinter den anderen, gemessen am Grundmodell",
    }
    return (
        f"Mittel aus {len(gemittelt)} von {len(gemittelt) + len(ausgelassen)} Faltungen",
        "; ".join(
            f"ohne Faltung {int(eintrag['faltung']) + 1} ({GRUENDE.get(eintrag['grund'], eintrag['grund'])})"
            for eintrag in ausgelassen
        ),
    )


def _anzahl(zahl: int, eins: str, mehr: str) -> str:
    return f"{zahl} {eins if zahl == 1 else mehr}"


def _training_im_steckbrief(umfang: lauf_layout.Umfang) -> tuple[str, str]:
    """Worauf gelernt wurde, nach Herkunft - und in wie vielen Faltungen."""
    vorlagen = umfang.lernen.get(lauf_layout.GEMESSENE_QUELLE, 0)
    korrekturen = umfang.lernen.get("korrektur", 0)
    selbst = umfang.lernen.get(lauf_layout.QUELLE_SELBST, 0)
    faltungen = lauf_layout.FALTUNGEN
    teile = [
        f"{_anzahl(vorlagen, 'Vorlage', 'Vorlagen')} in {faltungen - 1} von {faltungen} Faltungen"
        if vorlagen
        else "",
        f"{_anzahl(korrekturen, 'Korrektur', 'Korrekturen')} in allen" if korrekturen else "",
        f"{selbst} selbst beschriftet in allen" if selbst else "",
    ]
    return (
        f"{_anzahl(umfang.lernproben, 'Probe', 'Proben')} aus "
        f"{_anzahl(umfang.lern_aufnahmen, 'Aufnahme', 'Aufnahmen')}",
        " · ".join(teil for teil in teile if teil),
    )


def _messung_im_steckbrief(umfang: lauf_layout.Umfang) -> tuple[str, str]:
    """Woran gemessen wurde - und was nicht, mit Grund."""
    nicht = [
        name
        for quelle, name in (("korrektur", "Korrekturen"), (lauf_layout.QUELLE_SELBST, "Selbstbeschriftetes"))
        if umfang.lernen.get(quelle)
    ]
    teile = [
        "nur Vorlagen, jede einmal von der Faltung, die sie nicht kannte",
        f"{' und '.join(nicht)} nicht: ihr Text stammt von der Erkennung selbst" if nicht else "",
    ]
    return (
        f"{_anzahl(umfang.messen, 'Probe', 'Proben')} aus "
        f"{_anzahl(umfang.mess_aufnahmen, 'Aufnahme', 'Aufnahmen')}",
        " · ".join(teil for teil in teile if teil),
    )


def _selbst_im_steckbrief(lauf: lauf_layout.Lauf) -> tuple[str, str]:
    """Das Selbsttraining als Wert und Hinweis: wie viele aufgenommen, nach wem."""
    wahl = lauf_layout.selbsttraining_aus(lauf.auftrag)
    name = _wahlname(SELBSTTRAININGE, wahl)
    if wahl != lauf_layout.SELBST_AN:
        return name, ""
    kandidaten = int(dict(lauf.auftrag.get("zeilen") or {}).get(lauf_layout.QUELLE_SELBST, 0))
    inhalt = lauf_layout.lies_json(lauf.verzeichnis / lauf_layout.SELBSTBESCHRIFTUNG)
    if inhalt is None:
        return name, f"{kandidaten} Abschnitte, noch nicht beschriftet"
    zeilen = dict(inhalt.get("zeilen") or {})
    aufgenommen = sum(1 for zeile in zeilen.values() if zeile.get("aufgenommen"))
    modell = str(inhalt.get("modell") or "")
    teile = [
        f"{aufgenommen} von {len(zeilen)} Abschnitten aufgenommen",
        f"nach {registry.beschriftung(modell)}" if modell else "",
        f"ab Sicherheit {_zahl(inhalt['schwelle'])}" if inhalt.get("schwelle") is not None else "",
    ]
    return name, " · ".join(teil for teil in teile if teil)


def steckbrief(lauf: lauf_layout.Lauf) -> list[SteckbriefZeile]:
    """Was diesen Lauf ausmacht - in Zahlen, nicht in Sätzen.

    Jede Achse steht da, auch die auf Vorgabe; fehlt sie im Auftrag, galt die
    Vorgabe. Ein Hinweis nur, wo er etwas trägt, das nicht im Wert steckt.
    """
    auftrag = lauf.auftrag
    zustand = lauf.zustand
    manifest = _manifest_zu(lauf)
    kv = dict(manifest.get("kreuzvalidierung") or {})
    zeilen: list[SteckbriefZeile] = []

    def dazu(begriff: str, wert: object, hinweis: str = "", art: str = "") -> None:
        if wert not in (None, ""):
            zeilen.append(
                SteckbriefZeile(begriff=begriff, wert=str(wert), hinweis=hinweis, art=art)
            )

    version = str(zustand.get("version") or "")
    if version:
        dazu("Kennung", registry.kurzkennung(version))
        dazu("Stand", version)

    # ── Was gelernt wurde ───────────────────────────────────────────────────
    dazu("Grundmodell", str(auftrag.get("basismodell", "")))

    rezept = dict(manifest.get("rezept") or {})
    methode = str(auftrag.get("methode", ""))
    if methode == lauf_layout.LORA:
        # Rang und α aus dem Manifest, solange er rechnet aus dem Auftrag.
        rang = rezept.get("lora_rang") or lauf_layout.lora_rang_aus(auftrag)
        alpha = rezept.get("lora_alpha")
        ziele = lauf_layout.lora_ziele_aus(auftrag)
        wo = " und ".join(rezept.get("lora_teile") or [])
        dazu(
            "Methode",
            f"LoRA · Rang {rang}" + (f", α {alpha}" if alpha else ""),
            ", ".join(rezept.get("lora_ziele") or []) + (f" in {wo}" if wo else "")
            or _wahlname(LORA_ZIELE, ziele),
        )
    else:
        dazu("Methode", _wahlname(METHODEN, methode))

    if lauf_layout.mit_rauschkopie(auftrag):
        dazu(
            "Rauschkopien",
            "mitgelernt",
            "je Aufnahme eine Kopie mit weißem Rauschen, 20 dB unter dem Signal - "
            "gezählt und gemessen sind nur die Aufnahmen",
        )
    dazu("Auswahl", *_auswahl_im_steckbrief(lauf))
    dazu(
        "Korrekturen",
        _wahlname(KORREKTURGEWICHTE, lauf_layout.korrekturgewicht_aus(auftrag)),
        "Vorlagen zählen 1",
    )
    dazu("Selbsttraining", *_selbst_im_steckbrief(lauf))
    # Was wofür: Beim Kern stehen die Zahlen erst nach der Wahl fest.
    umfang = _umfang(lauf)
    if umfang is not None:
        dazu("Training", *_training_im_steckbrief(umfang))
        dazu("Messung", *_messung_im_steckbrief(umfang))

    stufe = str(auftrag.get("augmentierung") or lauf_layout.AUG_KEINE)
    dazu(
        "Augmentierung",
        AUGMENTIERUNG_GRIFFE.get(stufe, _wahlname(AUGMENTIERUNGEN, stufe)),
        "nur auf den Trainingsproben, je Durchgang neu gewürfelt"
        if stufe != lauf_layout.AUG_KEINE
        else "",
    )

    faktor = _tempo_des_laufs(lauf)
    gesucht = lauf_layout.tempowahl_aus(auftrag)
    endgueltig = bool(zustand.get("tempo_endgueltig", True))
    if faktor is None:
        dazu("Vorspulen", "wird gesucht", "noch keine Faltung durch")
    elif gesucht != lauf_layout.TEMPO_AUS:
        laeuft = zustand.get("faltung")
        woher = (
            f"gesucht, Minimum der {lauf_layout.FALTUNGEN} zusammengelegten Kurven"
            if gesucht == lauf_layout.TEMPO_OPTIMAL
            else f"geschätzt, Mittel aus {lauf_layout.FALTUNGEN} Faltungen"
        )
        dazu(
            "Vorspulen",
            f"{_zahl(faktor)}×" + ("" if endgueltig else " (vorläufig)"),
            woher
            if endgueltig
            else f"noch offen, gerade Faltung {int(laeuft) + 1}"
            if laeuft is not None
            else "noch offen",
        )
    else:
        dazu("Vorspulen", f"{_zahl(faktor)}×")

    # ── Wie gelernt wurde ───────────────────────────────────────────────────
    if rezept.get("lernrate") is not None:
        warm = rezept.get("warmlauf_schritte")
        dazu(
            "Lernrate",
            f"{float(rezept['lernrate']):.0e}".replace("e-0", "e-"),
            f"Warmlauf {warm} Schritte" if warm else "",
        )
    # Wie der Lauf auf die Karte kam (`wortlaut/kartenplan.py`): aus dem
    # Manifest, solange er rechnet aus dem Zustand.
    zuschnitt = dict(manifest.get("zuschnitt") or zustand.get("zuschnitt") or {})
    if rezept.get("stapel"):
        dazu(
            "Stapel",
            f"{rezept['stapel']} wirksam",
            (
                f"je Schritt {zuschnitt['stapel']} × {zuschnitt['akkumulation']}"
                + (", Gradientensparen" if zuschnitt.get("gradientensparsam") else "")
            )
            if zuschnitt.get("stapel")
            else "",
        )
    if zuschnitt.get("genauigkeit"):
        karte = dict(zuschnitt.get("karte") or {})
        dazu(
            "Karte",
            f"{karte['name']}, {float(karte['speicher_mb']) / 1000:.0f} GB" if karte else "Prozessor",
            f"{zuschnitt['genauigkeit']}, {zuschnitt.get('aufmerksamkeit', 'sdpa')}"
            + (", Grundmodell halb" if zuschnitt.get("halbe_grundgewichte") else ""),
        )

    gelaufen = kv.get("durchgaenge")
    obergrenze = (
        rezept.get("epochen_hoechstens")
        if str(auftrag.get("dauer")) == lauf_layout.DAUER_GEDULDIG
        else rezept.get("epochen")
    )
    geduldig = str(auftrag.get("dauer")) == lauf_layout.DAUER_GEDULDIG
    if gelaufen is not None:
        # Die Obergrenze nur aus dem Manifest - die Rezeptdatei kann sich
        # seit dem Lauf geändert haben.
        grenze = f" von höchstens {obergrenze}" if obergrenze else ""
        geduld = rezept.get("geduld")
        dazu(
            "Durchgänge",
            f"{_zahl(gelaufen, 1)}{grenze}",
            f"Median der Faltungen · Geduld {geduld}" if geduldig and geduld else "Median der Faltungen",
        )
    else:
        dazu("Dauer", _wahlname(DAUERN, str(auftrag.get("dauer") or lauf_layout.DAUER_FEST)))
    steuerung = lauf_layout.steuerung_aus(auftrag)
    dazu(
        "Steuergröße",
        _wahlname(STEUERUNGEN, steuerung),
        "wählt Checkpoint, Abbruch und α",
    )
    if lauf_layout.fenster_aus(auftrag) == lauf_layout.FENSTER_GEKUERZT:
        sekunden = zustand.get("fenster_s")
        dazu(
            "Fenster",
            f"{_zahl(sekunden, 1)} s im Training" if sekunden else _wahlname(FENSTER, "gekuerzt"),
            "ausgeliefert und gemessen mit 30 s",
        )

    dazu("Abschluss", _abschlusstext(manifest))
    dazu("Endmodell", *_endmodell_im_steckbrief(manifest))
    if lauf_layout.kontext_aus(auftrag) == lauf_layout.KONTEXT_VOKABULAR:
        woerter = [wort for wort in str(manifest.get("startprompt") or "").split(", ") if wort]
        dazu(
            "Startprompt",
            f"{len(woerter)} Wörter" if manifest else _wahlname(KONTEXTE, "vokabular"),
            "die seltenen Wörter der Lerntexte, vor jeder Erkennung",
        )

    # ── Was dabei herauskam ─────────────────────────────────────────────────
    gemessen = dict(zustand.get("metriken") or {})
    einheiten = gemessen.get("test_einheiten")
    dazu(
        "Gemessen",
        f"{einheiten} Einheiten" if einheiten else "",
        "jede von einem Modell, das sie nicht kannte",
    )
    dazu("Rechenwerk", gemessen.get("rechenwerk"))

    # Vor dem Rechnen der Zeitpunkt der Bestellung.
    begonnen = str(zustand.get("begonnen", ""))
    if begonnen:
        spanne = _dauer_lesbar(begonnen, str(zustand.get("beendet", "")))
        dazu(
            "Gerechnet",
            begonnen,
            f"{spanne}, {lauf_layout.FALTUNGEN} Faltungen und das Endmodell" if spanne else "",
            art="zeit",
        )
    else:
        dazu("Beauftragt", str(auftrag.get("erstellt", "")), art="zeit")
    return zeilen


def _tempo_des_laufs(lauf: lauf_layout.Lauf) -> float | None:
    """Mit welcher Geschwindigkeit dieser Lauf wirklich gerechnet hat.

    Ohne Tempowahl der Wert des Profils, eingefroren im Auftrag. Mit Tempowahl
    der Median der Faltungen (wie Durchgänge und α); `None`, solange keiner
    feststeht.
    """
    gewaehlt = lauf.zustand.get("tempo")
    if gewaehlt is not None:
        return float(gewaehlt)
    if lauf_layout.tempowahl_aus(lauf.auftrag) != lauf_layout.TEMPO_AUS:
        return None
    return float(lauf.auftrag.get("tempo", 1.0))


def _hole(sprecher: str, job_id: str) -> lauf_layout.Lauf:
    lauf = lauf_layout.lies_lauf(einstellungen().data_dir, job_id)
    # Ein fremder Lauf ist unbekannt - nicht einmal seine Existenz wird verraten.
    if lauf is None or lauf.sprecher_id != sprecher:
        raise HTTPException(status_code=404, detail="Unbekannter Lauf.")
    return lauf


@router.get("", response_model=ListeAntwort)
def liste(korpus: Korpus, sprecher: SprecherId) -> ListeAntwort:
    konfiguration = einstellungen()
    proben = aufteilung.proben(korpus)
    genug = aufteilung.genug(proben)
    # Ohne Schlüssel eine Leseseite.
    erlaubt = bool(konfiguration.trainer_key)
    alle = lauf_layout.alle_laeufe(konfiguration.data_dir, sprecher)

    # Nur ein fertiger Lauf sagt, was ein Modell kennt.
    fertige = [lauf for lauf in alle if lauf.status == lauf_layout.FERTIG]
    zuletzt = int(fertige[-1].auftrag.get("aufnahmen", 0)) if fertige else 0

    return ListeAntwort(
        laeufe=[_als_antwort(lauf) for lauf in reversed(alle)],
        aufnahmen_jetzt=len(proben),
        # Nie negativ, auch nach Löschungen.
        aufnahmen_neu=max(0, len(proben) - zuletzt),
        methoden=METHODEN,
        lora_ziele=LORA_ZIELE,
        lora_raenge=LORA_RAENGE,
        auswahlen=AUSWAHLEN,
        korrekturgewichte=KORREKTURGEWICHTE,
        selbsttraininge=SELBSTTRAININGE,
        abschluesse=ABSCHLUESSE,
        augmentierungen=AUGMENTIERUNGEN,
        dauern=DAUERN,
        steuerungen=STEUERUNGEN,
        fenster=FENSTER,
        tempi=TEMPI,
        kontexte=KONTEXTE,
        grundmodelle=_grundmodelle(),
        basismodell=konfiguration.lernen_basismodell,
        faltungen=lauf_layout.FALTUNGEN,
        bereit=genug and erlaubt,
        # Der Schlüssel zuerst - ohne ihn helfen auch mehr Aufnahmen nicht.
        hinweis=(
            ""
            if genug and erlaubt
            else "Auf diesem Server ist kein Trainerschlüssel hinterlegt - "
            "hier lässt sich kein Training anstoßen."
            if not erlaubt
            else f"Sechsfache Kreuzvalidierung braucht mindestens "
            f"{lauf_layout.FALTUNGEN} Aufnahmen - sie kommen aus \u201ehören\u201c."
        ),
    )


@router.post(
    "",
    response_model=LaufAntwort,
    status_code=201,
    dependencies=[Depends(_pruefe_trainerschluessel)],
)
def beauftrage(
    bestellung: Bestellung, korpus: Korpus, sprecher: SprecherId, sprache: Sprache
) -> LaufAntwort:
    """Einen Lauf beauftragen.

    Der Trainerschlüssel wird vor allem anderen geprüft: Wer nicht trainieren
    darf, erfährt nichts über Korpus oder Methoden. Was bestellt werden kann,
    prüft `auftraege.bestelle` - dieselbe Stelle für `make train`.
    """
    try:
        lauf = auftraege.bestelle(
            einstellungen().data_dir,
            korpus,
            auftraege.Bestellung(
                sprecher_id=sprecher,
                sprache=sprache,
                methode=bestellung.methode,
                lora_ziele=bestellung.lora_ziele,
                lora_rang=bestellung.lora_rang,
                auswahl=bestellung.auswahl,
                korrekturgewicht=bestellung.korrekturgewicht,
                selbsttraining=bestellung.selbsttraining,
                abschluss=bestellung.abschluss,
                augmentierung=bestellung.augmentierung,
                dauer=bestellung.dauer,
                steuerung=bestellung.steuerung,
                fenster=bestellung.fenster,
                tempowahl=bestellung.tempowahl,
                kontext=bestellung.kontext,
                grundmodell=bestellung.grundmodell,
            ),
        )
    except auftraege.Abgelehnt as ursache:
        raise HTTPException(status_code=ursache.status, detail=str(ursache)) from ursache
    return _als_antwort(lauf)


@router.get("/{job_id}", response_model=EinzelAntwort)
def einzeln(job_id: str, korpus: Korpus, sprecher: SprecherId) -> EinzelAntwort:
    """Kurven, Bewertung und Vergleich zu einem Lauf."""
    lauf = _hole(sprecher, job_id)
    kurven = auftraege.lernkurve(lauf)
    protokoll = lauf.verzeichnis / lauf_layout.PROTOKOLL
    return EinzelAntwort(
        lauf=_als_antwort(lauf),
        steckbrief=steckbrief(lauf),
        methoden=METHODEN,
        lora_ziele=LORA_ZIELE,
        lora_raenge=LORA_RAENGE,
        auswahlen=AUSWAHLEN,
        korrekturgewichte=KORREKTURGEWICHTE,
        selbsttraininge=SELBSTTRAININGE,
        abschluesse=ABSCHLUESSE,
        augmentierungen=AUGMENTIERUNGEN,
        dauern=DAUERN,
        steuerungen=STEUERUNGEN,
        fenster=FENSTER,
        tempi=TEMPI,
        kontexte=KONTEXTE,
        grundmodelle=_grundmodelle(),
        kurve_training=[PunktAntwort(**_punkt(zeile)) for zeile in kurven["training"]],
        kurve_validierung=[PunktAntwort(**_punkt(zeile)) for zeile in kurven["validierung"]],
        vergleich=[
            GegenueberAntwort(
                mass=eintrag.mass,
                baseline=eintrag.baseline,
                trainiert=eintrag.trainiert,
                besser=eintrag.besser,
                anzahl=eintrag.anzahl,
            )
            for eintrag in vergleich.gegenueber(lauf, korpus)
        ],
        # Nur das Ende - dort steht, woran es scheiterte.
        protokoll=protokoll.read_text(encoding="utf-8")[-4000:] if protokoll.is_file() else "",
    )


def _punkt(zeile: dict) -> dict:
    """Nur die Felder, die die Kurve kennt - der Trainer darf mehr schreiben."""
    return {
        "schritt": int(zeile.get("schritt", 0)),
        "epoche": float(zeile.get("epoche", 0.0)),
        "verlust": zeile.get("verlust"),
        "lernrate": zeile.get("lernrate"),
        "wer": zeile.get("wer"),
    }


class GeloeschtAntwort(BaseModel):
    job_id: str
    # Die Version des mitgelöschten Stands, sonst leer.
    version: str
    war_freigegeben: bool


@router.delete(
    "/{job_id}",
    response_model=GeloeschtAntwort,
    dependencies=[Depends(_pruefe_trainerschluessel)],
)
def loeschen(job_id: str, sprecher: SprecherId) -> GeloeschtAntwort:
    """Einen Lauf ersatzlos entfernen - samt dem Modell, das aus ihm entstand.

    Ohne Papierkorb; die Sicherheitsabfrage nennt vorher, was verschwindet
    (`frontend/src/routes/Training.svelte`). Warum der Stand mitgeht:
    `services/auftraege.loesche`.
    """
    _hole(sprecher, job_id)  # 404, wenn er einem anderen gehört
    try:
        geloescht = auftraege.loesche(einstellungen().data_dir, sprecher, job_id)
    except LookupError as ursache:
        raise HTTPException(status_code=404, detail="Unbekannter Lauf.") from ursache
    except RuntimeError as ursache:
        raise HTTPException(status_code=409, detail=str(ursache)) from ursache

    return GeloeschtAntwort(
        job_id=geloescht.job_id,
        version=geloescht.version,
        war_freigegeben=geloescht.war_freigegeben,
    )


@router.post("/{job_id}/abbruch", response_model=LaufAntwort)
def abbrechen(job_id: str, sprecher: SprecherId) -> LaufAntwort:
    """Anhalten - einen wartenden sofort, einen rechnenden über den Trainer.

    Ohne Trainerschlüssel: Anhalten gibt die Karte frei.
    """
    _hole(sprecher, job_id)
    if not auftraege.halte_an(einstellungen().data_dir, job_id):
        raise HTTPException(
            status_code=409,
            detail="Dieser Lauf ist schon zu Ende - anhalten lässt sich nur ein "
            "wartender oder rechnender.",
        )
    return _als_antwort(_hole(sprecher, job_id))


@router.post(
    "/{job_id}/neustart",
    response_model=LaufAntwort,
    status_code=201,
    dependencies=[Depends(_pruefe_trainerschluessel)],
)
def neu_starten(job_id: str, sprecher: SprecherId) -> LaufAntwort:
    """Einen gescheiterten oder angehaltenen Lauf noch einmal rechnen lassen.

    Mit Trainerschlüssel (`services/auftraege.starte_neu`).
    """
    _hole(sprecher, job_id)
    try:
        lauf = auftraege.starte_neu(einstellungen().data_dir, sprecher, job_id)
    except LookupError as ursache:
        raise HTTPException(status_code=404, detail="Unbekannter Lauf.") from ursache
    except RuntimeError as ursache:
        raise HTTPException(status_code=409, detail=str(ursache)) from ursache
    return _als_antwort(lauf)
