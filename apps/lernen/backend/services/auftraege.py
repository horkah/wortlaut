"""Einen Trainingslauf beauftragen - und nachsehen, was daraus geworden ist.

Ein Auftrag ist ein Verzeichnis (`wortlaut/laeufe.py`), kein Funktionsaufruf.
Diese Datei schreibt es und liest es wieder; gerechnet wird anderswo, in einem
Container mit Karte.

**Was im Verzeichnis steht, bevor der Trainer es anfasst:** der Auftrag und
das Manifest - jede Probe mit Pfad, Text, Herkunft und Faltung. Das Manifest
ist der Schnappschuss: Weitere Aufnahmen ändern nicht, worauf ein Modell
gelernt hat.

**Jede Zeile trägt ihre Faltung** (`services/aufteilung.py`): Sie misst in
dieser und lernt in den anderen fünf.

**Je Fassung eine Zeile, immer alle** (`wortlaut/augmentierung.py`). Ob die
Abwandlung mitlernt, entscheidet der Trainer am Auftrag (`daten`); gemessen
wird auf allen Fassungen, wie in der Auswertung von „hören" - sonst wäre die
Baseline ein anderer Versuch.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session
from wortlaut import augmentierung, corpus, ids, laeufe, registry

from apps.hoeren.backend.db.models import Textquelle
from apps.hoeren.backend.services import zuschnitt
from apps.lernen.backend.config import einstellungen
from apps.schreiben.backend import config as schreiben_ablage
from apps.lernen.backend.services import aufteilung, kernauswahl
from apps.lernen.backend.services.aufteilung import Probe
from apps.lernen.backend.services.kernauswahl import Kernauswahl

# Womit eine Probe zählt. Korrekturen stammen aus „schreiben": Ihr Text ist
# keine Vorgabe, sondern eine vom Menschen abgenickte Maschinenausgabe. Wer sie
# gleichrangig einspeist, trainiert dem Modell seine eigenen Fehler an - wie
# viel weniger, ist eine Achse (`laeufe.KORREKTURGEWICHTE`). Selbst
# beschriftetes Audio hat nicht einmal ein Nicken.
GEWICHTE = {"vorlage": 1.0, "korrektur": 0.5, laeufe.QUELLE_SELBST: 0.25}

# `verlauf`: das Gewicht einer Korrektur nach ihren Anläufen in „schreiben".
# Unverändert bestätigt heißt, das Modell hatte recht - es gibt wenig zu
# lernen, und ob jemand genau hingesehen hat, weiß niemand. Nachgesprochen
# heißt, die Person hat genau diesen Abschnitt geprüft und durchgesetzt.
# Ohne Zahl gilt die Vorgabe.
GEWICHT_UNVERAENDERT = 0.25
GEWICHT_NACHGESPROCHEN = 0.75


def gewicht_fuer(quelle: str, korrekturgewicht: str, anlaeufe: int | None = None) -> float:
    """Womit eine Probe im Training zählt (`Probe.gewicht` in `training/daten.py`)."""
    if quelle != "korrektur":
        return GEWICHTE.get(quelle, 1.0)
    if korrekturgewicht != laeufe.GEWICHT_VERLAUF:
        return float(korrekturgewicht)
    if anlaeufe is None:
        return float(laeufe.GEWICHT_VORGABE)
    return GEWICHT_UNVERAENDERT if anlaeufe <= 1 else GEWICHT_NACHGESPROCHEN


@dataclass(frozen=True)
class Auftrag:
    """Was bestellt wurde - die Felder, die `auftrag.json` trägt."""

    sprecher_id: str
    methode: str
    daten: str
    basismodell: str
    # Die Sprache des Profils, im Auftrag statt in der Umgebung. Ohne Vorgabe:
    # Ein vergessenes Feld fiele sonst still auf Deutsch zurück.
    sprache: str
    # Die Achsen (`wortlaut/laeufe.py`), jede mit ihrer Vorgabe.
    lora_ziele: str = laeufe.ZIELE_QV
    lora_rang: str = laeufe.RANG_VORGABE
    abschluss: str = laeufe.ABSCHLUSS_BESTER
    augmentierung: str = laeufe.AUG_KEINE
    dauer: str = laeufe.DAUER_FEST
    steuerung: str = laeufe.STEUERUNG_VERLUST
    fenster: str = laeufe.FENSTER_VOLL
    tempowahl: str = laeufe.TEMPO_AUS
    kontext: str = laeufe.KONTEXT_AUS
    # Leer: das unveränderte `basismodell`.
    ausgangsstand: str = ""
    auswahl: str = laeufe.AUSWAHL_ALLE
    korrekturgewicht: str = laeufe.GEWICHT_VORGABE
    selbsttraining: str = laeufe.SELBST_AUS


def _quelle_von(korpus: Session, probe: Probe) -> str:
    """`vorlage` oder `korrektur` - woher der Text stammt, nicht die Aufnahme."""
    quelle = korpus.get(Textquelle, probe.vorlage.source_id)
    return "korrektur" if quelle is not None and quelle.art == "korrektur" else "vorlage"


def _manifestzeile(
    probe: Probe,
    variante: str,
    quelle: str,
    sprecher_id: str,
    korrekturgewicht: str = laeufe.GEWICHT_VORGABE,
) -> dict[str, Any]:
    # Relativ zum Korpus, damit sich ein Schnappschuss kopieren lässt.
    innerhalb = corpus.sprecher_relpfad(sprecher_id)
    # Die Arbeitsdatei: Ein Zuschnitt gilt hier wie überall
    # (`hoeren/services/zuschnitt.py`).
    voll = (
        zuschnitt.arbeitsblob(probe.aufnahme)
        if variante == augmentierung.ORIGINAL
        else corpus.variante_relpfad(sprecher_id, probe.aufnahme.id, variante)
    )
    anlaeufe = probe.aufnahme.anlaeufe
    return {
        "audio": voll.removeprefix(f"{innerhalb}/"),
        "text": probe.vorlage.text,
        "quelle": quelle,
        "modus": probe.aufnahme.modus,
        "variante": variante,
        "dauer_s": zuschnitt.arbeitsdauer(probe.aufnahme),
        "gewicht": gewicht_fuer(quelle, korrekturgewicht, anlaeufe),
        # Nur bei Korrekturen: wie oft in „schreiben" gesprochen.
        "anlaeufe": anlaeufe,
        "faltung": probe.faltung,
        "recording_id": probe.aufnahme.id,
    }


def unbeschriftete_diktate(datenverzeichnis: Path, sprecher_id: str) -> list[dict[str, Any]]:
    """Die Abschnitte nie bestätigter Diktate aus „schreiben", die noch Audio haben.

    Nur lesend, über SQL - die Diktatdatenbank schreibt „schreiben" allein. Ihr
    Text ist die Ausgabe des Modells von damals und zählt nicht; beschriftet
    wird im Trainer (`training/selbsttraining.py`). Der Pfad steht relativ zum
    Korpus wie jeder im Manifest.
    """
    pfad = datenverzeichnis / schreiben_ablage.sprecher_relpfad(sprecher_id)
    datenbank = pfad / schreiben_ablage.DATENBANKNAME
    if not datenbank.is_file():
        return []
    verbindung = sqlite3.connect(f"file:{datenbank}?mode=ro", uri=True)
    try:
        abschnitte = verbindung.execute(
            "SELECT s.id, s.blob, s.dauer_s FROM segments s "
            "JOIN sessions z ON z.id = s.session_id "
            "WHERE z.status = 'offen' AND s.blob IS NOT NULL "
            "ORDER BY s.erstellt, s.position"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        verbindung.close()
    korpus = datenverzeichnis / corpus.sprecher_relpfad(sprecher_id)
    return [
        {
            "audio": Path(os.path.relpath(datenverzeichnis / blob, korpus)).as_posix(),
            "text": "",
            "quelle": laeufe.QUELLE_SELBST,
            "modus": "frei",
            "variante": augmentierung.ORIGINAL,
            "dauer_s": float(dauer),
            "gewicht": GEWICHTE[laeufe.QUELLE_SELBST],
            # Keine Faltung: gelernt in jeder, gemessen in keiner.
            "faltung": None,
            "recording_id": kennung,
        }
        for kennung, blob, dauer in abschnitte
        if (datenverzeichnis / blob).is_file()
    ]


def schreibe_manifest(
    ziel: Path,
    korpus: Session,
    proben: list[Probe],
    sprecher_id: str,
    daten: str,
    korrekturgewicht: str = laeufe.GEWICHT_VORGABE,
    unbeschriftet: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    """Das Manifest schreiben; gibt zurück, wie viele Zeilen je Faltung entstanden.

    Immer alle Fassungen, unabhängig von `daten` - was gelernt wird, entscheidet
    der Trainer (`training/daten.py`). Unbeschriftetes Audio zählt eigens
    (`selbst`), nicht in `gesamt`.
    """
    gezaehlt = {str(faltung): 0 for faltung in range(laeufe.FALTUNGEN)}
    with ziel.open("w", encoding="utf-8") as datei:
        for probe in proben:
            quelle = _quelle_von(korpus, probe)
            for variante in augmentierung.VARIANTEN:
                zeile = _manifestzeile(probe, variante, quelle, sprecher_id, korrekturgewicht)
                datei.write(json.dumps(zeile, ensure_ascii=False) + "\n")
                gezaehlt[str(probe.faltung)] += 1
        gezaehlt["gesamt"] = sum(gezaehlt.values())
        for zeile in unbeschriftet or []:
            datei.write(json.dumps(zeile, ensure_ascii=False) + "\n")
        if unbeschriftet:
            gezaehlt[laeufe.QUELLE_SELBST] = len(unbeschriftet)
    return gezaehlt


def beauftrage(
    datenverzeichnis: Path,
    korpus: Session,
    proben: list[Probe],
    auftrag: Auftrag,
    kernauswahl: Kernauswahl | None = None,
) -> laeufe.Lauf:
    """Einen Lauf anlegen: Verzeichnis, Marke, Manifest, Auftrag - in dieser Reihenfolge.

    Beim Kern kommt die Kernauswahl dazu, ebenfalls vor dem Auftrag: Der
    Trainer erkennt einen offenen Lauf an `auftrag.json` und fände sonst ein
    halbes Manifest.
    """
    job_id = ids.neue_id("job")
    verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, job_id)
    verzeichnis.mkdir(parents=True, exist_ok=True)

    # Für die Löschung (`scripts/purge_speaker.py`).
    (verzeichnis / laeufe.SPRECHER_MARKE).write_text(
        f"{auftrag.sprecher_id}\n", encoding="utf-8"
    )

    gezaehlt = schreibe_manifest(
        verzeichnis / laeufe.MANIFEST,
        korpus,
        proben,
        auftrag.sprecher_id,
        auftrag.daten,
        auftrag.korrekturgewicht,
        unbeschriftete_diktate(datenverzeichnis, auftrag.sprecher_id)
        if auftrag.selbsttraining == laeufe.SELBST_AN
        else None,
    )

    if auftrag.auswahl == laeufe.AUSWAHL_KERN:
        if kernauswahl is None:
            raise ValueError("Der Kern verlangt eine Kernauswahl.")
        laeufe.schreibe_json(verzeichnis / laeufe.KERNAUSWAHL, kernauswahl.als_dict())

    inhalt = {
        "job_id": job_id,
        "sprecher_id": auftrag.sprecher_id,
        "methode": auftrag.methode,
        "lora_ziele": auftrag.lora_ziele,
        "lora_rang": auftrag.lora_rang,
        "daten": auftrag.daten,
        "auswahl": auftrag.auswahl,
        "korrekturgewicht": auftrag.korrekturgewicht,
        "selbsttraining": auftrag.selbsttraining,
        "abschluss": auftrag.abschluss,
        "augmentierung": auftrag.augmentierung,
        "dauer": auftrag.dauer,
        "steuerung": auftrag.steuerung,
        "fenster": auftrag.fenster,
        "kontext": auftrag.kontext,
        "basismodell": auftrag.basismodell,
        "sprache": auftrag.sprache,
        "tempowahl": auftrag.tempowahl,
        "erstellt": laeufe.jetzt(),
        "zeilen": gezaehlt,
        "aufnahmen": len(proben),
    }
    if auftrag.ausgangsstand:
        inhalt[laeufe.AUSGANGSSTAND] = auftrag.ausgangsstand
    # Die Folge hinter dem Optionscode (`/43`, `/43b`, …), einmal vergeben
    # (`wortlaut/laeufe.py`). Stände zählen mit, falls einer seinen Lauf überlebt hat.
    inhalt[laeufe.FOLGE] = laeufe.naechste_folge(
        inhalt,
        [
            *(lauf.auftrag for lauf in laeufe.alle_laeufe(datenverzeichnis, auftrag.sprecher_id)),
            *registry.alle_staende(datenverzeichnis, auftrag.sprecher_id),
        ],
    )
    laeufe.schreibe_json(verzeichnis / laeufe.AUFTRAG, inhalt)

    lauf = laeufe.lies_lauf(datenverzeichnis, job_id)
    assert lauf is not None  # gerade selbst geschrieben
    return lauf


@dataclass(frozen=True)
class Bestellung:
    """Was jemand bestellt - aus der Oberfläche oder mit `make train`.

    Anders als `Auftrag` noch ungeprüft; `grundmodell` leer heißt: die Vorgabe.
    """

    sprecher_id: str
    sprache: str
    methode: str
    lora_ziele: str = laeufe.ZIELE_QV
    lora_rang: str = laeufe.RANG_VORGABE
    daten: str = laeufe.NUR_ORIGINAL
    auswahl: str = laeufe.AUSWAHL_ALLE
    korrekturgewicht: str = laeufe.GEWICHT_VORGABE
    selbsttraining: str = laeufe.SELBST_AUS
    abschluss: str = laeufe.ABSCHLUSS_BESTER
    augmentierung: str = laeufe.AUG_KEINE
    dauer: str = laeufe.DAUER_FEST
    steuerung: str = laeufe.STEUERUNG_VERLUST
    fenster: str = laeufe.FENSTER_VOLL
    tempowahl: str = laeufe.TEMPO_AUS
    kontext: str = laeufe.KONTEXT_AUS
    grundmodell: str = ""


class Abgelehnt(Exception):
    """Eine Bestellung, die so nicht geht - mit dem HTTP-Status, den die API meldet."""

    def __init__(self, status: int, text: str) -> None:
        super().__init__(text)
        self.status = status


def bestelle(datenverzeichnis: Path, korpus: Session, bestellung: Bestellung) -> laeufe.Lauf:
    """Prüfen und beauftragen - eine Stelle für Oberfläche und Kommandozeile.

    Geprüft wird alles, was sonst erst nach Stunden am Trainer scheiterte:
    jede Achse, das Grundmodell, ob die Methode auf die Karte passt
    (`Einstellungen.methoden_fuer`) und ob es für sechs Faltungen reicht.
    """
    for wert, erlaubt, was in (
        (bestellung.methode, laeufe.METHODEN, "Methode"),
        (bestellung.lora_ziele, laeufe.LORA_ZIELE, "LoRA-Ziele"),
        (bestellung.lora_rang, laeufe.LORA_RAENGE, "LoRA-Rang"),
        (bestellung.daten, laeufe.DATENSAETZE, "Datensatz"),
        (bestellung.auswahl, laeufe.AUSWAHLEN, "Auswahl"),
        (bestellung.korrekturgewicht, laeufe.KORREKTURGEWICHTE, "Korrekturgewicht"),
        (bestellung.selbsttraining, laeufe.SELBSTTRAINING, "Selbsttraining"),
        (bestellung.abschluss, laeufe.ABSCHLUESSE, "Abschluss"),
        (bestellung.augmentierung, laeufe.AUGMENTIERUNGEN, "Augmentierung"),
        (bestellung.dauer, laeufe.DAUERN, "Dauer"),
        (bestellung.steuerung, laeufe.STEUERUNGEN, "Steuergröße"),
        (bestellung.fenster, laeufe.FENSTER, "Fenster"),
        (bestellung.tempowahl, laeufe.TEMPI, "Tempowahl"),
        (bestellung.kontext, laeufe.KONTEXTE, "Kontext"),
    ):
        if wert not in erlaubt:
            raise Abgelehnt(400, f"Unbekannt ({was}): {wert}. Zur Wahl: {', '.join(erlaubt)}.")
    if bestellung.methode != laeufe.LORA and (
        bestellung.lora_ziele != laeufe.ZIELE_QV or bestellung.lora_rang != laeufe.RANG_VORGABE
    ):
        raise Abgelehnt(400, "LoRA-Ziele und -Rang gibt es nur mit LoRA.")

    konfiguration = einstellungen()
    grundmodell = bestellung.grundmodell or konfiguration.lernen_basismodell
    # Nur Whisper-Modelle. Ein Ausgangsstand (`Auftrag.ausgangsstand`,
    # `training/ausgangsstand.py`) kann der Trainer, angeboten wird er nicht.
    if grundmodell not in konfiguration.grundmodelle():
        raise Abgelehnt(
            400,
            f"Unbekanntes Grundmodell: {grundmodell}. Zur Wahl: "
            f"{', '.join(konfiguration.grundmodelle())} (WORTLAUT_LERNEN_GRUNDMODELLE).",
        )
    # Scheiterte sonst erst am Speicher der Karte.
    if bestellung.methode == laeufe.LORA and (
        f"{bestellung.lora_ziele}/{bestellung.lora_rang}" not in konfiguration.lora_fuer(grundmodell)
    ):
        raise Abgelehnt(
            400,
            f"LoRA an „{bestellung.lora_ziele}“ mit Rang {bestellung.lora_rang} passt mit "
            f"{laeufe.kurzname(grundmodell)} nicht auf diese Karte.",
        )
    erlaubte = konfiguration.methoden_fuer(grundmodell)
    if bestellung.methode not in erlaubte:
        raise Abgelehnt(
            400,
            f"{laeufe.kurzname(grundmodell)} lässt sich auf dieser Karte nur mit "
            f"{', '.join(erlaubte) or 'nichts'} trainieren - volles Feintuning sprengt "
            "ihren Speicher.",
        )
    proben = aufteilung.proben(korpus)
    if not aufteilung.genug(proben):
        raise Abgelehnt(
            409,
            f"Für sechsfache Kreuzvalidierung braucht es mindestens "
            f"{laeufe.FALTUNGEN} brauchbare Aufnahmen - vorhanden sind {len(proben)}.",
        )

    kern = None
    if bestellung.auswahl == laeufe.AUSWAHL_KERN:
        try:
            kern = kernauswahl.waehle(datenverzeichnis, korpus, bestellung.sprecher_id, proben)
        except kernauswahl.KeinKern as ursache:
            raise Abgelehnt(409, str(ursache)) from ursache

    return beauftrage(
        datenverzeichnis,
        korpus,
        proben,
        Auftrag(
            sprecher_id=bestellung.sprecher_id,
            methode=bestellung.methode,
            lora_ziele=bestellung.lora_ziele,
            lora_rang=bestellung.lora_rang,
            daten=bestellung.daten,
            auswahl=bestellung.auswahl,
            korrekturgewicht=bestellung.korrekturgewicht,
            selbsttraining=bestellung.selbsttraining,
            abschluss=bestellung.abschluss,
            augmentierung=bestellung.augmentierung,
            dauer=bestellung.dauer,
            steuerung=bestellung.steuerung,
            fenster=bestellung.fenster,
            kontext=bestellung.kontext,
            tempowahl=bestellung.tempowahl,
            basismodell=grundmodell,
            # Für Whispers Sprachmarken und die Bewertung (`wortlaut/sprachen.py`).
            sprache=bestellung.sprache,
        ),
        kernauswahl=kern,
    )


def halte_an(datenverzeichnis: Path, job_id: str) -> bool:
    """Einen Lauf anhalten - einen wartenden sofort, einen rechnenden über den Trainer.

    Ein wartender wird sofort `abgebrochen`. Bei einem rechnenden legt diese
    App den Wunsch ins Verzeichnis (`laeufe.HALT`), und der Läufer im
    Trainer-Container beendet den Prozess (`training/laeufer.py`). Ein
    hängender (`Lauf.haengt`) wird ebenfalls sofort `abgebrochen`; ein doch
    noch lebender Prozess findet denselben Wunsch.

    `False`: Der Lauf ist schon zu Ende.
    """
    lauf = laeufe.lies_lauf(datenverzeichnis, job_id)
    if lauf is None or lauf.status not in (laeufe.WARTET, laeufe.LAEUFT):
        return False
    laeufe.verlange_anhalten(lauf.verzeichnis)
    if lauf.offen or lauf.haengt:
        laeufe.schreibe_json(
            lauf.verzeichnis / laeufe.ZUSTAND,
            {**lauf.zustand, "status": laeufe.ABGEBROCHEN, "beendet": laeufe.jetzt()},
        )
    return True


# Was ein Neustart übernimmt: Schnappschuss und Kernauswahl - nicht, was schiefging.
UEBERNOMMEN = (laeufe.SPRECHER_MARKE, laeufe.MANIFEST, laeufe.KERNAUSWAHL)
NEU_STARTBAR = (laeufe.GESCHEITERT, laeufe.ABGEBROCHEN)


def starte_neu(datenverzeichnis: Path, sprecher_id: str, job_id: str) -> laeufe.Lauf:
    """Einen gescheiterten oder angehaltenen Lauf noch einmal rechnen lassen.

    Derselbe Auftrag auf demselben Schnappschuss; verworfene Aufnahmen fallen
    heraus wie immer (`laeufe.zeilen_fuer_faltung`). Wer den heutigen Korpus
    will, beauftragt neu.

    Der neue Lauf bekommt eine eigene Kennung und die Folge (`/43b`) des
    alten; der alte geht samt Stand (`loesche`).
    """
    alt = laeufe.lies_lauf(datenverzeichnis, job_id)
    if alt is None or alt.sprecher_id != sprecher_id:
        raise LookupError(job_id)
    if alt.status not in NEU_STARTBAR:
        raise RuntimeError(
            "Neu starten lässt sich nur ein gescheiterter oder angehaltener Lauf."
        )

    neu_id = ids.neue_id("job")
    verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, neu_id)
    verzeichnis.mkdir(parents=True, exist_ok=True)
    for name in UEBERNOMMEN:
        if (alt.verzeichnis / name).is_file():
            shutil.copy2(alt.verzeichnis / name, verzeichnis / name)
    # Der Auftrag zuletzt, wie in `beauftrage`: Erst mit ihm ist der Lauf offen.
    laeufe.schreibe_json(
        verzeichnis / laeufe.AUFTRAG,
        {**alt.auftrag, "job_id": neu_id, "erstellt": laeufe.jetzt(), "neu_von": job_id},
    )
    loesche(datenverzeichnis, sprecher_id, job_id)

    lauf = laeufe.lies_lauf(datenverzeichnis, neu_id)
    assert lauf is not None  # gerade selbst geschrieben
    return lauf


@dataclass(frozen=True)
class Geloescht:
    """Was beim Löschen eines Laufs verschwunden ist - für die Rückmeldung."""

    job_id: str
    # Die Version des Modellstands, der mit ihm ging; leer, wenn keiner da war.
    version: str = ""
    war_freigegeben: bool = False


def loesche(datenverzeichnis: Path, sprecher_id: str, job_id: str) -> Geloescht:
    """Einen Lauf ersatzlos entfernen - samt dem Modell, das aus ihm entstand.

    Ohne Lauf wäre nicht mehr nachzusehen, worauf ein Stand gelernt hat - sein
    Manifest liegt dort. Die Oberfläche nennt vorher, ob der Stand freigegeben
    ist (`api/laeufe.py`). Der Korpus bleibt.
    """
    lauf = laeufe.lies_lauf(datenverzeichnis, job_id)
    if lauf is None or lauf.sprecher_id != sprecher_id:
        raise LookupError(job_id)
    if lauf.status == laeufe.LAEUFT and not lauf.haengt:
        # Sonst entstünde ein halb geschriebener Stand. Ein hängender Lauf
        # (`wortlaut/laeufe.py`) behauptet `laeuft` nur noch - sein Prozess
        # starb mit Container oder Maschine; ihn zu löschen ist erlaubt.
        raise RuntimeError(
            "Dieser Lauf rechnet gerade. Erst wenn er durch ist, lässt er sich löschen."
        )

    stand = registry.stand_zu_lauf(datenverzeichnis, sprecher_id, job_id)
    ergebnis = Geloescht(job_id=job_id)
    if stand is not None:
        kennung = str(stand.get("id", "/"))
        version = kennung.split("/", 1)[-1]
        war_freigegeben = registry.freigegeben(datenverzeichnis, sprecher_id) == kennung
        ergebnis = Geloescht(
            job_id=job_id, version=version, war_freigegeben=war_freigegeben
        )
        # Sonst zeigte die Freigabe in „schreiben" ins Leere.
        if war_freigegeben:
            registry.gib_frei(datenverzeichnis, sprecher_id, "")
        registry.loesche_stand(datenverzeichnis, sprecher_id, version)

    # Zuletzt: Ein Abbruch hinterlässt einen Lauf ohne Stand, nie umgekehrt.
    shutil.rmtree(lauf.verzeichnis, ignore_errors=True)
    return ergebnis


def lernkurve(lauf: laeufe.Lauf) -> dict[str, list[dict[str, float]]]:
    """Was die Kurven zeigen: der Verlust je Schritt, die Prüfung je Durchgang.

    Der Verlust fällt auch beim Auswendiglernen weiter; die Validierung zeigt,
    wann es anfängt.
    """
    schritte = []
    pruefungen = []
    for zeile in laeufe.lies_zeilen(lauf.verzeichnis / laeufe.FORTSCHRITT):
        art = zeile.get("art")
        if art == "schritt":
            schritte.append(zeile)
        elif art == "validierung":
            pruefungen.append(zeile)
    return {"training": schritte, "validierung": pruefungen}
