"""Einen Trainingslauf beauftragen - und nachsehen, was daraus geworden ist.

Ein Auftrag ist ein Verzeichnis (`wortlaut/laeufe.py`), kein Funktionsaufruf.
Diese Datei schreibt es und liest es wieder; gerechnet wird anderswo, in einem
Container mit Karte.

**Was im Verzeichnis steht, bevor der Trainer es anfasst.** Der Auftrag - wer,
womit, wie - und das Manifest: jede Probe mit ihrem Pfad, ihrem Text, ihrer
Herkunft und ihrer Faltung. Das Manifest ist der Schnappschuss:
Ab hier steht fest, womit trainiert wird, auch wenn derselbe Mensch in der
nächsten Stunde zwanzig weitere Aufnahmen macht. Ohne diesen Schnitt wäre
hinterher nicht mehr zu sagen, worauf ein Modell eigentlich gelernt hat.

**Warum jede Aufnahme ihre Faltung trägt.** Gemessen wird mit sechsfacher
Kreuzvalidierung über den ganzen Korpus (`services/aufteilung.py`): Je Faltung
läuft ein Training, das auf den anderen fünf Sechsteln lernt und auf diesem
einen misst. Die Faltung einer Zeile sagt also beides - in welchem der sechs
Läufe sie gelernt wird und in welchem sie zählt.

**Warum kein Testdrittel mehr.** Es stand bis September 2026 hier, und der
Gedanke war richtig: ungesehene Aufnahmen, an denen gemessen wird. Die
Ausführung trug nicht. Bei neun Aufnahmen bestand der Test aus dreien, die
Validierung aus einer - Zahlen über drei Aufnahmen sind keine Auskunft. Die
Kreuzvalidierung beantwortet dieselbe Frage über alle Aufnahmen. Wirklich
unabhängige Testaufnahmen sind damit nicht ersetzt; sie werden eigens
aufgenommen werden.

**Warum je Fassung eine Zeile - und zwar immer alle.** „hören" legt neben jede
Aufnahme eine abgewandelte Fassung (`wortlaut/augmentierung.py`). Ob sie
mittrainiert wird, steht im Auftrag (`daten`) und entscheidet der Trainer beim
Lesen. Ins Manifest gehören trotzdem alle: **Gemessen** wird immer auf allen
Fassungen - dieselben, die in der Auswertung von „hören" schon gemessen
wurden. Nur so ist die Baseline eine Baseline und kein anderer Versuch.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session
from wortlaut import augmentierung, corpus, ids, laeufe, registry

from apps.hoeren.backend.db.models import Textquelle
from apps.lernen.backend.services.aufteilung import Probe

# Womit eine Probe zählt. Korrekturen stammen aus „schreiben": Ihr Text ist
# keine Vorgabe, sondern eine vom Menschen abgenickte Maschinenausgabe. Wer sie
# gleichrangig einspeist, trainiert dem Modell seine eigenen Fehler an.
GEWICHTE = {"vorlage": 1.0, "korrektur": 0.5}


@dataclass(frozen=True)
class Auftrag:
    """Was bestellt wurde - die Felder, die `auftrag.json` trägt."""

    sprecher_id: str
    methode: str
    daten: str
    basismodell: str
    # Die Sprache des Profils. Sie steht im Auftrag und nicht in der Umgebung,
    # weil ein Lauf nachvollziehbar sein soll: In `auftrag.json` ist später zu
    # lesen, wofür trainiert wurde, und der Trainer muss es nicht raten.
    #
    # Ohne Vorgabe, und das mit Absicht. `finetune.py` und `bewerten.py` lasen
    # den Schlüssel schon immer - geschrieben hat ihn nie jemand, also griff
    # dort stets der Rückfall auf Deutsch. Ein spanisches Profil hätte deutsche
    # erzwungene Marken bekommen und wäre als Deutsch bewertet worden, ohne
    # dass irgendwo ein Fehler gestanden hätte. Ein Feld ohne Vorgabe kann
    # nicht wieder vergessen werden.
    sprache: str
    # Was am Ende mit den Gewichten geschieht (`wortlaut/laeufe.py`). Mit
    # Vorgabe, und die ist das Verfahren von vorher: Ein Auftrag von einem
    # Aufrufer, der diese Achse nicht kennt, bleibt derselbe Auftrag.
    abschluss: str = laeufe.ABSCHLUSS_BESTER
    # Womit die Trainingsproben beim Laden abgewandelt werden. Auch hier mit
    # Vorgabe: `keine` ist das Verfahren von vorher.
    augmentierung: str = laeufe.AUG_KEINE
    # Wie lange trainiert wird. `fest` ist die Zahl aus dem Rezept und das
    # Verfahren von vorher.
    dauer: str = laeufe.DAUER_FEST
    # Ob die Geschwindigkeit gesucht wird oder die des Profils gilt.
    # `wie_eingestellt` ist das Verfahren von vorher.
    tempowahl: str = laeufe.TEMPO_AUS


def _quelle_von(korpus: Session, probe: Probe) -> str:
    """`vorlage` oder `korrektur` - woher der Text stammt, nicht die Aufnahme."""
    quelle = korpus.get(Textquelle, probe.vorlage.source_id)
    return "korrektur" if quelle is not None and quelle.art == "korrektur" else "vorlage"


def _manifestzeile(
    probe: Probe, variante: str, quelle: str, sprecher_id: str
) -> dict[str, Any]:
    # Der Pfad steht relativ zum Korpus dieses Sprechers und nicht absolut:
    # Ein Schnappschuss soll sich auf eine andere Maschine kopieren lassen,
    # ohne dass jemand Pfade darin ersetzt.
    innerhalb = corpus.sprecher_relpfad(sprecher_id)
    voll = (
        probe.aufnahme.blob
        if variante == augmentierung.ORIGINAL
        else corpus.variante_relpfad(sprecher_id, probe.aufnahme.id, variante)
    )
    return {
        "audio": voll.removeprefix(f"{innerhalb}/"),
        "text": probe.vorlage.text,
        "quelle": quelle,
        "modus": probe.aufnahme.modus,
        "variante": variante,
        "dauer_s": probe.aufnahme.dauer_s,
        "gewicht": GEWICHTE.get(quelle, 1.0),
        # In welcher der sechs Faltungen diese Aufnahme gemessen wird - und
        # damit in welchen fünf sie gelernt wird.
        "faltung": probe.faltung,
        "recording_id": probe.aufnahme.id,
    }


def schreibe_manifest(
    ziel: Path, korpus: Session, proben: list[Probe], sprecher_id: str, daten: str
) -> dict[str, int]:
    """Das Manifest schreiben; gibt zurück, wie viele Zeilen je Faltung entstanden.

    `daten` steht hier nicht mehr im Weg: Geschrieben werden immer alle
    Fassungen, und welche davon gelernt werden dürfen, entscheidet der Trainer
    am Auftrag (`training/daten.py`). Das Manifest ist damit für jeden Lauf
    dasselbe und bleibt, was es sein soll - der Schnappschuss des Korpus, nicht
    die Anweisung an den Trainer.
    """
    gezaehlt = {str(faltung): 0 for faltung in range(laeufe.FALTUNGEN)}
    with ziel.open("w", encoding="utf-8") as datei:
        for probe in proben:
            quelle = _quelle_von(korpus, probe)
            for variante in augmentierung.VARIANTEN:
                zeile = _manifestzeile(probe, variante, quelle, sprecher_id)
                datei.write(json.dumps(zeile, ensure_ascii=False) + "\n")
                gezaehlt[str(probe.faltung)] += 1
    gezaehlt["gesamt"] = sum(gezaehlt.values())
    return gezaehlt


def beauftrage(
    datenverzeichnis: Path,
    korpus: Session,
    proben: list[Probe],
    auftrag: Auftrag,
) -> laeufe.Lauf:
    """Einen Lauf anlegen: Verzeichnis, Marke, Manifest, Auftrag - in dieser Reihenfolge.

    Der Auftrag zuletzt, und das ist die ganze Verriegelung: Der Trainer
    erkennt einen offenen Lauf an `auftrag.json`. Läge die Datei zuerst da,
    könnte er ein halbes Manifest erwischen.
    """
    job_id = ids.neue_id("job")
    verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, job_id)
    verzeichnis.mkdir(parents=True, exist_ok=True)

    # Die Zusage an die Löschung - ohne sie findet `scripts/purge_speaker.py`
    # diesen Schnappschuss nicht und meldet ihn zur Prüfung von Hand.
    (verzeichnis / laeufe.SPRECHER_MARKE).write_text(
        f"{auftrag.sprecher_id}\n", encoding="utf-8"
    )

    gezaehlt = schreibe_manifest(
        verzeichnis / laeufe.MANIFEST, korpus, proben, auftrag.sprecher_id, auftrag.daten
    )

    laeufe.schreibe_json(
        verzeichnis / laeufe.AUFTRAG,
        {
            "job_id": job_id,
            "sprecher_id": auftrag.sprecher_id,
            "methode": auftrag.methode,
            "daten": auftrag.daten,
            "abschluss": auftrag.abschluss,
            "augmentierung": auftrag.augmentierung,
            "dauer": auftrag.dauer,
            "basismodell": auftrag.basismodell,
            # Die Sprache des Profils. Sie steht hier, weil `finetune.py` und
            # `bewerten.py` sie genau hier lesen - und weil in `auftrag.json`
            # nachvollziehbar sein soll, wofür trainiert wurde.
            "sprache": auftrag.sprache,
            # Ob der Trainer diesen Faktor benutzt oder sich einen sucht. Der
            # eingefrorene Wert darüber bleibt trotzdem stehen: Er ist der
            # Ausgangspunkt, gegen den sich eine Suche messen lassen muss.
            "tempowahl": auftrag.tempowahl,
            "erstellt": laeufe.jetzt(),
            "zeilen": gezaehlt,
            "aufnahmen": len(proben),
        },
    )

    lauf = laeufe.lies_lauf(datenverzeichnis, job_id)
    assert lauf is not None  # gerade selbst geschrieben
    return lauf


def brich_ab(datenverzeichnis: Path, job_id: str) -> bool:
    """Einen wartenden Lauf zurücknehmen. Ein laufender bleibt, was er ist.

    Einen laufenden abzubrechen hieße, in einen fremden Container hineinzugreifen
    - das kann diese App nicht, und so zu tun als ob wäre schlimmer als der
    fehlende Knopf. Wer einen laufenden stoppen will, stoppt den Trainer.
    """
    lauf = laeufe.lies_lauf(datenverzeichnis, job_id)
    if lauf is None or not lauf.offen:
        return False
    laeufe.schreibe_json(
        lauf.verzeichnis / laeufe.ZUSTAND,
        {"status": laeufe.ABGEBROCHEN, "beendet": laeufe.jetzt()},
    )
    return True


@dataclass(frozen=True)
class Geloescht:
    """Was beim Löschen eines Laufs verschwunden ist - für die Rückmeldung."""

    job_id: str
    # Die Version des Modellstands, der mit ihm ging; leer, wenn keiner da war.
    version: str = ""
    war_freigegeben: bool = False


def loesche(datenverzeichnis: Path, sprecher_id: str, job_id: str) -> Geloescht:
    """Einen Lauf ersatzlos entfernen - samt dem Modell, das aus ihm entstand.

    **Warum das Modell mitgeht.** Ein Modellstand trägt die Kennung des Laufs,
    aus dem er stammt (`job_id` im Manifest). Bliebe er stehen, zeigte er auf
    ein Verzeichnis, das es nicht mehr gibt: Die Ansicht böte einen Weg „Zum
    Lauf" ins Leere, und die Frage, worauf dieses Modell eigentlich trainiert
    wurde, wäre nicht mehr zu beantworten - das Manifest, das es sagt, liegt
    im gelöschten Lauf. Ein Modell, dessen Herkunft niemand mehr nachsehen
    kann, ist genau das, wogegen diese App gebaut ist.

    Deshalb ist das Löschen eines Laufs das Löschen von allem, was aus ihm
    hervorging. Die Oberfläche sagt das vorher, ausdrücklich und samt der
    Angabe, ob der Stand gerade freigegeben ist (siehe `api/laeufe.py`).

    **Was nicht mitgeht: der Korpus.** Er gehört „hören" und nicht diesem Lauf.
    Die Faltungen hängen an ihm und werden beim nächsten Auftrag neu gerechnet;
    gespeichert ist daran nichts (`services/aufteilung.py`).
    """
    lauf = laeufe.lies_lauf(datenverzeichnis, job_id)
    if lauf is None or lauf.sprecher_id != sprecher_id:
        raise LookupError(job_id)
    if lauf.status == laeufe.LAEUFT and not lauf.haengt:
        # In das Verzeichnis schreibt gerade ein anderer Container. Es unter
        # ihm wegzuziehen hieße, einen laufenden Prozess ins Leere greifen zu
        # lassen - und das Ergebnis wäre ein halb geschriebener Modellstand.
        #
        # `und not haengt` ist der Unterschied zwischen einem Wächter und einer
        # Falle. Der Zustand `laeuft` ist eine Behauptung des rechnenden
        # Prozesses, und sie bleibt stehen, wenn er sie nicht mehr
        # zurücknehmen kann - weil sein Container neu gestartet wurde, weil die
        # Maschine neu gestartet ist, weil der Kern ihn erschlagen hat. Vorher
        # war so ein Lauf für immer unlöschbar: Er rechnete nicht, sagte aber,
        # er rechne, und niemand kam an ihn heran.
        #
        # Eine Viertelstunde ohne ein geschriebenes Byte ist keine Rechnung
        # mehr (`wortlaut/laeufe.py`). Falls doch noch ein Prozess daran hängt,
        # greift er nach dem Löschen ins Leere und stirbt - das ist der Preis,
        # und er ist kleiner als ein Verzeichnis, das niemand loswird.
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
        # War dieses Modell freigegeben, geht die Freigabe mit: Eine, die auf
        # ein gelöschtes Verzeichnis zeigt, wäre in „schreiben" eine Zeile
        # „Modellstand nicht gefunden" statt einer Antwort - und niemand käme
        # auf den Gedanken, dass sie hier entstand.
        if war_freigegeben:
            registry.gib_frei(datenverzeichnis, sprecher_id, "")
        registry.loesche_stand(datenverzeichnis, sprecher_id, version)

    # Zuletzt das Laufverzeichnis, und in dieser Reihenfolge: Bräche das
    # Löschen dazwischen ab, bliebe ein Lauf ohne Modell stehen - lästig, aber
    # widerspruchsfrei. Andersherum bliebe ein Modell ohne Lauf, und genau das
    # soll es nicht geben.
    shutil.rmtree(lauf.verzeichnis, ignore_errors=True)
    return ergebnis


def lernkurve(lauf: laeufe.Lauf) -> dict[str, list[dict[str, float]]]:
    """Was die Kurven zeigen: der Verlust je Schritt, die Prüfung je Durchgang.

    Zwei Reihen und nicht eine. Der Trainingsverlust sagt, ob überhaupt etwas
    passiert; er fällt auch dann weiter, wenn das Modell nur noch auswendig
    lernt. Erst die Validierung daneben zeigt, wann das anfängt - sie ist die
    Reihe, die wieder steigt, während die andere sinkt.
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
