"""Ein Trainingslauf als Verzeichnis - die Nahtstelle zwischen „lernen" und dem Trainer.

Der Trainer läuft in einem eigenen Container mit torch und CUDA; der Webdienst
soll in Sekunden neu starten. Zwischen beiden liegt keine Aufrufkette, sondern
ein Verzeichnis je Auftrag:

    data/snapshots/<job_id>/
    ├── sprecher.txt          die Sprecher-ID - die Zusage an die Löschung
    ├── manifest.jsonl        der Schnappschuss: je Zeile eine Probe in einer Fassung
    ├── kernauswahl.json      nur bei Kernauswahl
    ├── auftrag.json          was zu tun ist - zuletzt geschrieben
    ├── zustand.json          was daraus geworden ist - vom Trainer
    ├── fortschritt.jsonl     je Zeile ein Ereignis: Schritt, Verlust, Stufe
    ├── bewertung.jsonl       je Zeile eine Messung einer Faltung
    ├── protokoll.txt         die rohe Ausgabe
    ├── halt                  der Wunsch, anzuhalten
    └── arbeitsstand/, gewichte/, vorgespult/, ausgang/   nur während des Laufs

Keine Tabelle daneben: Was der Trainer tut, steht dort, wo er schreibt - eine
Zeile, die „läuft" sagt, während nichts mehr läuft, kann es so nicht geben.
Der Schnappschuss macht den Lauf reproduzierbar, während weiter aufgenommen
wird, und Auftrag, Daten und Ergebnis sind eine löschbare Einheit.

Offen ist ein Auftrag ohne `zustand.json` - das ist die ganze Warteschlange.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wortlaut import augmentierung, kartenplan, registry

SCHNAPPSCHUESSE = "snapshots"
SPRECHER_MARKE = "sprecher.txt"

AUFTRAG = "auftrag.json"
MANIFEST = "manifest.jsonl"
ZUSTAND = "zustand.json"
FORTSCHRITT = "fortschritt.jsonl"
BEWERTUNG = "bewertung.jsonl"
PROTOKOLL = "protokoll.txt"
# Der Wunsch, einen Lauf anzuhalten. Die Oberfläche legt die Datei hin, der
# Läufer beendet den Prozess (`apps/lernen/training/laeufer.py`). Sie bleibt
# liegen, damit der Lauf nicht wieder anläuft.
HALT = "halt"

# Was nur während eines Laufs gebraucht wird und Gigabyte wiegen kann (siehe
# `raeume_zwischenstaende_auf`): der Arbeitsstand des Trainers samt Optimierer,
# die Rohgewichte vor der Umwandlung, die vorgespulten Fassungen
# (`wortlaut/tempo.py`) und die zurückgerechneten Gewichte eines
# Ausgangsstands (`training/ausgangsstand.py`).
ARBEITSSTAND = "arbeitsstand"
GEWICHTE = "gewichte"
VORGESPULT = "vorgespult"
AUSGANG = "ausgang"
ZWISCHENSTAENDE = (ARBEITSSTAND, GEWICHTE, VORGESPULT, AUSGANG)

# ── Die Faltungen ───────────────────────────────────────────────────────────
#
# Sechsfache Kreuzvalidierung über alle Aufnahmen: Je Faltung lernt ein Modell
# auf fünf Sechsteln und wird am sechsten gemessen; danach ist jede Aufnahme
# einmal von einem Modell gehört, das sie nie gelernt hat. Kein unabhängiger
# Test - der wäre eigens aufzunehmen.
#
# **Die Faltung hängt an der Kennung**, nicht an der Reihenfolge: ein Hash des
# Stamms, modulo sechs. Neue und gelöschte Aufnahmen verschieben keine andere,
# und eine Aufnahme misst in jedem Lauf in derselben Faltung. Teile und
# Kopien aus „Editieren" tragen den Stamm ihres Originals und bleiben bei ihm
# (`aufteilung.py` in „lernen").
#
# Ein Hash verteilt erst bei vielen Stämmen gleichmäßig. Bliebe eine Faltung
# leer, ließe sich nicht kreuzvalidieren - dann gehen die Stämme reihum, in
# der Reihenfolge ihres Hashs. Das trifft nur sehr kleine Korpora.
FALTUNGEN = 6


def _hash(stamm: str) -> int:
    return int.from_bytes(hashlib.sha256(stamm.encode("utf-8")).digest()[:8], "big")


def verteile(staemme: Iterable[str]) -> list[int]:
    """Die Faltung (ab 0) jedes Stamms, in der Reihenfolge der `staemme`."""
    staemme = list(staemme)
    vergeben = [_hash(stamm) % FALTUNGEN for stamm in staemme]
    if len(set(vergeben)) == FALTUNGEN:
        return vergeben
    rang = {stamm: nummer for nummer, stamm in enumerate(sorted(staemme, key=_hash))}
    return [rang[stamm] % FALTUNGEN for stamm in staemme]


# ── Methode und Datensatz ───────────────────────────────────────────────────
#
# Zwei Achsen: wie trainiert wird (alle Gewichte oder ein LoRA-Zusatz) und
# womit (nur Originale oder auch die gemessenen Fassungen).
VOLL = "full"
LORA = "lora"
METHODEN = (VOLL, LORA)

# ── Grundmodelle ────────────────────────────────────────────────────────────
#
# Worauf feingetunt wird. `small` ist die Vorgabe: die kleinste Stufe, die
# ganze Sätze trifft. Welche Methode mit welchem Modell geht, entscheidet die
# Karte (`methoden_fuer`, `kartenplan.py`).
def kurzname(basismodell: str) -> str:
    """`openai/whisper-medium` → `medium` - so heißt es überall in den Tabellen."""
    return basismodell.rsplit("/", 1)[-1].removeprefix("whisper-")


# Ein Lauf kann auf einem trainierten Stand aufsetzen statt auf einem
# Grundmodell. Der Trainer kann das, angeboten wird es nicht - weiterzulernen
# brachte keinen Gewinn. Im Auftrag bleibt `basismodell` das Whisper-Modell,
# auf dem jener Stand gewachsen ist (Zerteiler, Rezept, Speicher), und
# `ausgangsstand` nennt die Gewichte, mit denen begonnen wird.
AUSGANGSSTAND = "ausgangsstand"


def grundmodell_aus(auftrag: dict[str, Any]) -> str:
    """Worauf dieser Lauf aufsetzt, so wie es zur Wahl stand.

    Der Ausgangsstand (`spr_…/<version>`), wenn es einen gibt, sonst das
    Grundmodell (`openai/whisper-small`).
    """
    return str(auftrag.get(AUSGANGSSTAND) or auftrag.get("basismodell") or "")


def methoden_fuer(
    basismodell: str,
    karte: kartenplan.Karte | None = kartenplan.VORGABE,
    reserve_mb: float = kartenplan.RESERVE_MB,
) -> tuple[str, ...]:
    """Welche Methoden mit diesem Grundmodell auf diese Karte passen.

    Auf der 11-GB-Karte, für die wortlaut gebaut ist: `small` voll und mit
    LoRA, die großen nur mit LoRA. Auf 40 GB auch `large-v3` voll.
    """
    return kartenplan.methoden(kurzname(basismodell), karte, reserve_mb)


# ── Der LoRA-Zusatz ─────────────────────────────────────────────────────────
#
# Nur bei LoRA: wo der Zusatz sitzt und wie groß er ist
# (`training/adapter.py`). Abweichende Aussprache ist eher ein Encoder-,
# abweichender Wortschatz eher ein Decoder-Problem - `encoder` und `decoder`
# trennen beides.
#
# `qv`       q_proj und v_proj der Aufmerksamkeit, in Encoder und Decoder.
# `alle`     q, k, v, out_proj und fc1, fc2, in Encoder und Decoder.
# `encoder`  Wie `alle`, nur im Encoder.
# `decoder`  Wie `alle`, nur im Decoder (Selbst- und Kreuzaufmerksamkeit).
ZIELE_QV = "qv"
ZIELE_ALLE = "alle"
ZIELE_ENCODER = "encoder"
ZIELE_DECODER = "decoder"
LORA_ZIELE = (ZIELE_QV, ZIELE_ALLE, ZIELE_ENCODER, ZIELE_DECODER)
# Der Rang; α wächst mit, damit die Skalierung α/r bleibt.
RANG_VORGABE = "32"
LORA_RAENGE = (RANG_VORGABE, "8", "64")


def lora_ziele_aus(auftrag: dict[str, Any]) -> str:
    """Wo der Zusatz eines Auftrags sitzt - `qv`, wenn das Feld fehlt."""
    return str(auftrag.get("lora_ziele") or ZIELE_QV)


def lora_rang_aus(auftrag: dict[str, Any]) -> str:
    """Der Rang eines Auftrags - die Vorgabe, wenn das Feld fehlt."""
    return str(auftrag.get("lora_rang") or RANG_VORGABE)


NUR_ORIGINAL = "original"
MIT_VARIANTEN = "augmentiert"
DATENSAETZE = (NUR_ORIGINAL, MIT_VARIANTEN)

# ── Die Auswahl ─────────────────────────────────────────────────────────────
#
# Worauf gelernt wird: auf allen Aufnahmen - oder nur auf dem **Kern**, den
# Aufnahmen, die das freigegebene Modell am besten verstanden hat. Gedacht
# für einen Korpus, in dem viele Aufnahmen fehlerhaft oder verrauscht sind:
# Ein Modell, das nur auf dem sauberen Teil lernt, soll ein stabiler Kern
# werden, auf dem sich später aufbauen lässt.
#
# **Der Kern ist für den Lauf der ganze Korpus.** Die Aufnahmen außerhalb
# kommen in ihm nicht vor - weder zum Lernen noch zum Steuern noch zum Messen
# der Faltungen. Die Kreuzvalidierung läuft über den Kern allein, auf eigens
# über ihn verteilten Faltungen (`verteile_kern`), damit jede gleich viel
# trägt. Die übrigen hört erst das fertige Endmodell, in der Auswertung von
# „hören": Für einen Kernstand gelten nur die Kernaufnahmen als gehört
# (`hoeren/services/auswertung._gehoert_im_lauf`), alles andere ist für ihn
# eine neue Aufnahme wie jede, die nach dem Training dazukam.
#
# **Wie viele, steht beim Auftrag fest; welche, vor dem ersten Training.** Der
# Server sammelt beim Auftrag die Werte des freigegebenen Modells
# (`apps/lernen/backend/services/kernauswahl.py`) und schreibt sie neben das
# Manifest (`KERNAUSWAHL`). Fehlen welche - Aufnahmen, die das Modell noch nie
# gehört hat -, stehen sie dort als `offen`, und der Trainer lässt sie vor der
# ersten Faltung von genau diesem Modell hören (`training/bewerten.py`,
# `vervollstaendige_kern`). Erst dann wird gewählt, nach derselben Regel an
# beiden Stellen (`waehle_kern`, `mit_kern`), und erst dann gelernt. Die
# Freigabe und die Messungen von „hören" kennt der Trainer dabei nicht: Er
# bekommt das Modell und die fehlenden Aufnahmen genannt.
AUSWAHL_ALLE = "alle"
AUSWAHL_KERN = "kern"
AUSWAHLEN = (AUSWAHL_ALLE, AUSWAHL_KERN)
# Welcher Anteil der Aufnahmen den Kern bildet, gezählt vom besten Wert an.
KERN_ANTEIL = 0.7
# Die Kernauswahl eines Laufs: welche Aufnahmen, nach welchem Modell, mit
# welchem Wert - jede Aufnahme mit ihrer WER, auch die außerhalb des Kerns.
KERNAUSWAHL = "kernauswahl.json"


def kern_anzahl(aufnahmen: int) -> int:
    """Wie viele Aufnahmen den Kern bilden.

    Aufgerundet: Bei zehn Aufnahmen sind es sieben, bei neun ebenfalls sieben
    und nicht sechs - lieber eine Aufnahme mehr gelernt als eine weniger.
    """
    return math.ceil(aufnahmen * KERN_ANTEIL)


def waehle_kern(wer: dict[str, float]) -> list[str]:
    """Die besten `kern_anzahl` Aufnahmen nach ihrer WER, die beste zuerst.

    Bei gleicher WER entscheidet die Kennung, damit derselbe Korpus immer
    denselben Kern ergibt.
    """
    rangfolge = sorted(wer, key=lambda kennung: (wer[kennung], kennung))
    return rangfolge[: kern_anzahl(len(wer))]


# ── Die Korrekturen ─────────────────────────────────────────────────────────
#
# Eine Korrektur aus „schreiben" ist eine abgenickte Maschinenausgabe; wie
# stark sie zählt, ist eine Achse (`services/auftraege.gewicht_fuer` in
# „lernen"):
#
# `0.5`, `0.25`, `0.75`, `1.0`   Ein festes Gewicht für jede Korrektur.
# `verlauf`   Aus der Zahl der Anläufe in „schreiben": unverändert bestätigt
#             zählt wenig, nachgesprochen viel.
GEWICHT_VORGABE = "0.5"
GEWICHT_VERLAUF = "verlauf"
KORREKTURGEWICHTE = (GEWICHT_VORGABE, "0.25", "0.75", "1.0", GEWICHT_VERLAUF)


def korrekturgewicht_aus(auftrag: dict[str, Any]) -> str:
    """Wie ein Auftrag Korrekturen gewichtet - `0.5`, wenn das Feld fehlt."""
    return str(auftrag.get("korrekturgewicht") or GEWICHT_VORGABE)


# ── Selbsttraining ──────────────────────────────────────────────────────────
#
# Unbeschriftetes Audio - Diktate, die in „schreiben" nie bestätigt wurden -
# beschriftet das freigegebene Modell vor der ersten Faltung; was es sicher
# genug hört, lernt gewichtet mit (`training/selbsttraining.py`). Gemessen
# wird es nie, und die Beschriftung steht in `SELBSTBESCHRIFTUNG`.
SELBST_AUS = "aus"
SELBST_AN = "an"
SELBSTTRAINING = (SELBST_AUS, SELBST_AN)
# Die Herkunft solcher Zeilen im Manifest, neben `vorlage` und `korrektur`.
QUELLE_SELBST = "selbst"
SELBSTBESCHRIFTUNG = "selbstbeschriftung.json"


def selbsttraining_aus(auftrag: dict[str, Any]) -> str:
    """Ob ein Auftrag selbst beschriftet - `aus`, wenn das Feld fehlt."""
    return str(auftrag.get("selbsttraining") or SELBST_AUS)


def selbstbeschriftung_aus(verzeichnis: Path) -> dict[str, str]:
    """Audio → Text der aufgenommenen Selbstbeschriftungen eines Laufs; leer ohne Datei."""
    inhalt = lies_json(verzeichnis / SELBSTBESCHRIFTUNG) or {}
    return {
        str(audio): str(zeile["text"])
        for audio, zeile in dict(inhalt.get("zeilen") or {}).items()
        if zeile.get("aufgenommen") and str(zeile.get("text") or "").strip()
    }


def auswahl_aus(auftrag: dict[str, Any]) -> str:
    """Die Auswahl eines Auftrags - `alle`, wenn das Feld fehlt."""
    return str(auftrag.get("auswahl") or AUSWAHL_ALLE)


def verteile_kern(kern: Iterable[str], staemme: dict[str, str]) -> dict[str, int]:
    """Die Faltung jeder Kernaufnahme - dieselbe Regel wie beim Auftrag (`verteile`).

    Je Stamm; `staemme` nennt jede Aufnahme mit ihrem Stamm. Eine Kernaufnahme
    misst damit in derselben Faltung wie im ganzen Korpus - außer der Kern ist
    so klein, dass eine Faltung leer bliebe.
    """
    im_kern = set(kern)
    gruppen: dict[str, list[str]] = {}
    for kennung, stamm in staemme.items():
        if kennung in im_kern:
            gruppen.setdefault(stamm, []).append(kennung)
    vergeben = verteile(gruppen)
    return {
        kennung: faltung
        for gruppe, faltung in zip(gruppen.values(), vergeben, strict=True)
        for kennung in gruppe
    }


def mit_kern(inhalt: dict[str, Any]) -> dict[str, Any]:
    """Die Kernauswahl mit gewähltem Kern - aus ihren Werten, ohne `offen`.
    Server und Trainer wählen hier, also gleich."""
    wer = {str(kennung): float(wert) for kennung, wert in dict(inhalt.get("wer") or {}).items()}
    kern = waehle_kern(wer)
    ergebnis = {schluessel: wert for schluessel, wert in inhalt.items() if schluessel != "offen"}
    ergebnis.update(
        anzahl=len(kern),
        wer=wer,
        kern=kern,
        schwelle=max((wer[kennung] for kennung in kern), default=0.0),
        faltungen=verteile_kern(kern, dict(inhalt.get("staemme") or {})),
    )
    return ergebnis


def kern_aus(verzeichnis: Path, auftrag: dict[str, Any]) -> set[str] | None:
    """Die Aufnahmen des Kerns - `None`, wenn auf allen gelernt wird.

    Fehlt die Datei oder ist noch nicht gewählt, ist das ein Fehler, kein
    Rückfall auf alle - der Lauf hieße sonst `K` und wäre etwas anderes.
    """
    if auswahl_aus(auftrag) != AUSWAHL_KERN:
        return None
    inhalt = lies_json(verzeichnis / KERNAUSWAHL)
    if inhalt is None:
        raise RuntimeError(f"Der Auftrag verlangt den Kern, aber {KERNAUSWAHL} fehlt.")
    if "kern" not in inhalt:
        raise RuntimeError(f"Der Kern ist noch nicht gewählt ({KERNAUSWAHL}).")
    return {str(kennung) for kennung in inhalt.get("kern", [])}


def kernfaltungen_aus(verzeichnis: Path, auftrag: dict[str, Any]) -> dict[str, int] | None:
    """Jede Kernaufnahme mit ihrer Faltung - `None`, wenn auf allen gelernt wird.

    Trägt die Kernauswahl keine eigenen Faltungen, gelten die des Manifests,
    eingeschränkt auf den Kern - ungleichmäßiger, aber Verwandte bleiben
    zusammen.
    """
    kern = kern_aus(verzeichnis, auftrag)
    if kern is None:
        return None
    inhalt = lies_json(verzeichnis / KERNAUSWAHL) or {}
    if inhalt.get("faltungen"):
        return {
            str(kennung): int(faltung)
            for kennung, faltung in dict(inhalt["faltungen"]).items()
            if kennung in kern
        }
    return {
        str(zeile["recording_id"]): int(zeile.get("faltung", -1))
        for zeile in manifestzeilen(verzeichnis)
        if str(zeile.get("recording_id")) in kern
    }

# ── Die Geschwindigkeit ─────────────────────────────────────────────────────
#
# Dysarthrische Sprache ist oft verlangsamt, und Whisper versteht sie
# vorgespult besser - wie viel, hängt am Sprecher:
#
# * `aus` - nicht vorspulen.
# * `geschaetzt` - Aufnahmedauer gegen die Sprechdauer der Texte bei
#   gewöhnlichem Tempo, ohne Erkennung (`training/tempowahl.aus_dauern`).
# * `optimal` - gesucht an Stützstellen am unveränderten Grundmodell, rund
#   eine Minute je Faltung.
#
# Beide Verfahren beantworten verschiedene Fragen - wie weit dieser Mensch von
# der Norm abweicht, und wo das Modell ihn am besten versteht -; welcher
# Faktor besser ist, zeigt die Tafel.
TEMPO_AUS = "aus"
TEMPO_GESCHAETZT = "geschaetzt"
TEMPO_OPTIMAL = "optimal"
TEMPI = (TEMPO_AUS, TEMPO_GESCHAETZT, TEMPO_OPTIMAL)


def tempowahl_aus(auftrag: dict[str, Any]) -> str:
    """Welches Verfahren dieser Auftrag bestellt hat; jeder andere Wert heißt `aus`."""
    gewaehlt = str(auftrag.get("tempowahl") or TEMPO_AUS)
    return gewaehlt if gewaehlt in (TEMPO_GESCHAETZT, TEMPO_OPTIMAL) else TEMPO_AUS

# ── Der Abschluss ───────────────────────────────────────────────────────────
#
# Was am Ende mit den Gewichten geschieht - eine Achse und keine stille
# Verbesserung, damit die Tafel zeigt, was gewirkt hat
# (`training/abschluss.py`):
#
# `bester`        Der beste Zwischenstand der Validierung.
# `mittel`        Die besten Zwischenstände elementweise gemittelt („Model Soup").
# `interpoliert`  θ = α·θ_grund + (1−α)·θ_fein (WiSE-FT), α an der Validierung gewählt.
# `beides`        Erst mitteln, dann interpolieren.
ABSCHLUSS_BESTER = "bester"
ABSCHLUSS_MITTEL = "mittel"
ABSCHLUSS_INTERPOLIERT = "interpoliert"
ABSCHLUSS_BEIDES = "beides"
ABSCHLUESSE = (
    ABSCHLUSS_BESTER,
    ABSCHLUSS_MITTEL,
    ABSCHLUSS_INTERPOLIERT,
    ABSCHLUSS_BEIDES,
)


# ── Der Kontext beim Dekodieren ─────────────────────────────────────────────
#
# Die einzige Achse ohne Einfluss aufs Training (`training/kontext.py`):
#
# `aus`         Whisper dekodiert ohne Vorgabe.
# `vokabular`   Ein Startprompt mit den seltenen Wörtern der Lerntexte. Er
#               liegt als `startprompt.txt` beim Stand und gilt überall, wo
#               der Stand hört - je Faltung nur aus ihren Lerntexten.
KONTEXT_AUS = "aus"
KONTEXT_VOKABULAR = "vokabular"
KONTEXTE = (KONTEXT_AUS, KONTEXT_VOKABULAR)


def kontext_aus(auftrag: dict[str, Any]) -> str:
    """Der Kontext eines Auftrags - `aus`, wenn das Feld fehlt."""
    return str(auftrag.get("kontext") or KONTEXT_AUS)


def mittelt(abschluss: str) -> bool:
    """Ob dieser Abschluss mehrere Zwischenstände mittelt."""
    return abschluss in (ABSCHLUSS_MITTEL, ABSCHLUSS_BEIDES)


def interpoliert(abschluss: str) -> bool:
    """Ob dieser Abschluss gegen das Grundmodell interpoliert."""
    return abschluss in (ABSCHLUSS_INTERPOLIERT, ABSCHLUSS_BEIDES)


# ── Die Augmentierung im Training ───────────────────────────────────────────
#
# Was mit einer Lernprobe beim Laden geschieht, gewürfelt und nirgends
# abgelegt (`training/klangwandel.py`). `daten` dagegen sagt, welche Fassungen
# überhaupt gelernt werden.
#
# `keine`      Die Probe, wie sie im Manifest steht.
# `masken`     SpecAugment: Zeit- und Frequenzbalken ins Spektrogramm.
# `umgebung`   Dazu Raum und Rauschen auf der Welle.
# `voll`       Dazu Tempo - bei dysarthrischer Sprache ein Merkmal, das
#              verwürfelt auch schaden kann, deshalb eine eigene Stufe.
AUG_KEINE = "keine"
AUG_MASKEN = "masken"
AUG_UMGEBUNG = "umgebung"
AUG_VOLL = "voll"
AUGMENTIERUNGEN = (AUG_KEINE, AUG_MASKEN, AUG_UMGEBUNG, AUG_VOLL)


# ── Wie lange trainiert wird ────────────────────────────────────────────────
#
# `fest`       Die Zahl der Durchgänge aus dem Rezept.
# `geduldig`   Eine weit höhere Obergrenze; Schluss, wenn die Validierung
#              mehrere Prüfungen lang nicht besser wird. Ausgeliefert wird
#              ohnehin der beste Durchgang - Geduld kostet nur Rechenzeit.
DAUER_FEST = "fest"
DAUER_GEDULDIG = "geduldig"
DAUERN = (DAUER_FEST, DAUER_GEDULDIG)


# ── Wonach ausgewählt wird ──────────────────────────────────────────────────
#
# Die Steuergröße, an der bester Zwischenstand, Abbruch und α gewählt werden
# (`training/finetune.py`, `training/abschluss.py`):
#
# `verlust`   Der gewichtete Validierungsverlust, geprüft je Durchgang.
# `wer`       Die WER nach freier Dekodierung, geprüft je Drittel eines
#             Durchgangs - das, woran der Stand gemessen wird. Kostet eine
#             Dekodierung je Prüfung.
STEUERUNG_VERLUST = "verlust"
STEUERUNG_WER = "wer"
STEUERUNGEN = (STEUERUNG_VERLUST, STEUERUNG_WER)


def steuerung_aus(auftrag: dict[str, Any]) -> str:
    """Die Steuergröße eines Auftrags - `verlust`, wenn das Feld fehlt."""
    return str(auftrag.get("steuerung") or STEUERUNG_VERLUST)


# ── Das Fenster des Encoders ────────────────────────────────────────────────
#
# Whisper hört immer 30 Sekunden; bei Sätzen von drei bis fünf Sekunden geht
# der größte Teil der Encoder-Rechnung auf Stille (`training/fenster.py`):
#
# `voll`      30 Sekunden, wie ausgeliefert.
# `gekuerzt`  Nur im Training auf die längste Aufnahme des Laufs gekürzt;
#             gesichert, umgewandelt und gemessen wird wieder mit 30 Sekunden.
FENSTER_VOLL = "voll"
FENSTER_GEKUERZT = "gekuerzt"
FENSTER = (FENSTER_VOLL, FENSTER_GEKUERZT)


def fenster_aus(auftrag: dict[str, Any]) -> str:
    """Das Encoder-Fenster eines Auftrags - `voll`, wenn das Feld fehlt."""
    return str(auftrag.get("fenster") or FENSTER_VOLL)


# ── Der Optionscode ─────────────────────────────────────────────────────────
#
# Alle Achsen eines Auftrags in einer Zeichenkette, etwa `ML-A-K-SRP-Ts-C`.
# Mit der Folge dahinter (`titel`, siehe unten) ist er der Titel eines Laufs und
# eines Standes - in „Training", in der Modelltafel und in der Einzelansicht.
#
# Vorn stehen immer Grundmodell und Methode, denn sie haben keinen Nullwert.
# Dahinter je gewählter Achse ein Glied, in der Reihenfolge der Wahlfelder;
# eine Achse auf ihrer Vorgabe fehlt. Die Buchstaben der Glieder sind
# untereinander verschieden, damit sich jedes für sich lesen lässt.
CODE_METHODE = {VOLL: "V", LORA: "L"}
# Z = Ziele des Zusatzes, R = Rang.
CODE_LORA_ZIELE = {ZIELE_QV: "", ZIELE_ALLE: "Z", ZIELE_ENCODER: "Ze", ZIELE_DECODER: "Zd"}
CODE_LORA_RANG = {rang: "" if rang == RANG_VORGABE else f"R{rang}" for rang in LORA_RAENGE}
CODE_DATENSATZ = {NUR_ORIGINAL: "", MIT_VARIANTEN: "A"}
CODE_AUSWAHL = {AUSWAHL_ALLE: "", AUSWAHL_KERN: "K"}
# Q = Gewicht der Korrekturen (in Hundertsteln, `v` = aus dem Verlauf), U = unbeschriftet.
CODE_KORREKTURGEWICHT = {
    GEWICHT_VORGABE: "",
    "0.25": "Q25",
    "0.75": "Q75",
    "1.0": "Q100",
    GEWICHT_VERLAUF: "Qv",
}
CODE_SELBSTTRAINING = {SELBST_AUS: "", SELBST_AN: "U"}
CODE_DAUER = {DAUER_FEST: "", DAUER_GEDULDIG: "E"}
CODE_STEUERUNG = {STEUERUNG_VERLUST: "", STEUERUNG_WER: "W"}
CODE_FENSTER = {FENSTER_VOLL: "", FENSTER_GEKUERZT: "F"}
# Kumulativ: S = SpecAugment, R = Raum + Rauschen, P = Tempo-Perturbation.
CODE_AUGMENTIERUNG = {AUG_KEINE: "", AUG_MASKEN: "S", AUG_UMGEBUNG: "SR", AUG_VOLL: "SRP"}
CODE_TEMPO = {TEMPO_AUS: "", TEMPO_GESCHAETZT: "Tg", TEMPO_OPTIMAL: "Ts"}
# C = Checkpoint-Mittel, I = Interpolation mit dem Grundmodell (WiSE-FT).
CODE_ABSCHLUSS = {
    ABSCHLUSS_BESTER: "",
    ABSCHLUSS_MITTEL: "C",
    ABSCHLUSS_INTERPOLIERT: "I",
    ABSCHLUSS_BEIDES: "CI",
}


# X = Kontext beim Dekodieren.
CODE_KONTEXT = {KONTEXT_AUS: "", KONTEXT_VOKABULAR: "X"}


def grundmodellcode(basismodell: str) -> str:
    """`openai/whisper-medium` → `M`, `…-large-v3` → `L3`, `…-large-v3-turbo` → `L3T`."""
    teile = [teil for teil in kurzname(basismodell).split("-") if teil]
    if not teile:
        return "?"
    code = teile[0][0].upper()
    for teil in teile[1:]:
        code += teil[1:] if teil[0] == "v" and teil[1:].isdigit() else teil[0].upper()
    return code


def optionscode(auftrag: dict[str, Any]) -> str:
    """Der Optionscode eines Auftrags oder Manifests - die einzige Stelle, die ihn bildet.

    Ein fehlendes Feld zählt als Vorgabe, ein unbekannter Wert wird `?`.
    """

    def glied(tafel: dict[str, str], wert: object, vorgabe: str) -> str:
        return tafel.get(str(wert or vorgabe), "?")

    methode = glied(CODE_METHODE, auftrag.get("methode"), "?")
    ausgang = str(auftrag.get(AUSGANGSSTAND) or "")
    # Auf einem Stand steht dessen Kennung vorn, abgesetzt: `C6G67-L-…`. Ohne
    # den Strich läse sich der Buchstabe der Methode als Teil der Kennung.
    kopf = (
        f"{registry.beschriftung(ausgang)}-{methode}"
        if ausgang
        else grundmodellcode(str(auftrag.get("basismodell") or "")) + methode
    )
    glieder = (
        glied(CODE_LORA_ZIELE, auftrag.get("lora_ziele"), ZIELE_QV),
        glied(CODE_LORA_RANG, auftrag.get("lora_rang"), RANG_VORGABE),
        glied(CODE_DATENSATZ, auftrag.get("daten"), NUR_ORIGINAL),
        glied(CODE_AUSWAHL, auftrag.get("auswahl"), AUSWAHL_ALLE),
        glied(CODE_KORREKTURGEWICHT, auftrag.get("korrekturgewicht"), GEWICHT_VORGABE),
        glied(CODE_SELBSTTRAINING, auftrag.get("selbsttraining"), SELBST_AUS),
        glied(CODE_DAUER, auftrag.get("dauer"), DAUER_FEST),
        glied(CODE_STEUERUNG, auftrag.get("steuerung"), STEUERUNG_VERLUST),
        glied(CODE_FENSTER, auftrag.get("fenster"), FENSTER_VOLL),
        glied(CODE_AUGMENTIERUNG, auftrag.get("augmentierung"), AUG_KEINE),
        CODE_TEMPO[tempowahl_aus(auftrag)],
        glied(CODE_ABSCHLUSS, auftrag.get("abschluss"), ABSCHLUSS_BESTER),
        glied(CODE_KONTEXT, auftrag.get("kontext"), KONTEXT_AUS),
    )
    return "-".join([kopf, *(teil for teil in glieder if teil)])


# ── Die Folge ───────────────────────────────────────────────────────────────
#
# Hinter dem Optionscode: die Zahl der gelernten Aufnahmen - bei der
# Kernauswahl die des Kerns - und ein Buchstabe, wenn es Code und Zahl schon
# gibt: `/43`, `/43b`, `/43c`, nach `z` weiter mit `aa`.
# Vergeben beim Auftrag, einer über dem höchsten noch vorhandenen Buchstaben,
# und danach nie geändert - sonst zeigte dieselbe Kennung nach einer Löschung
# auf ein anderes Modell.
FOLGE = "folge"


def folgebuchstaben(nummer: int) -> str:
    """0 → „", 1 → „b", 25 → „z", 26 → „aa", 27 → „ab" - der Buchstabe zur laufenden Nummer.

    Die erste Instanz trägt keinen Buchstaben; sie ist das stille `a`. Danach
    zählt es wie Tabellenspalten: `z`, `aa`, `ab`, ….
    """
    if nummer <= 0:
        return ""
    wert = nummer + 1
    zeichen = []
    while wert > 0:
        wert, rest = divmod(wert - 1, 26)
        zeichen.append(chr(ord("a") + rest))
    return "".join(reversed(zeichen))


def folgenummer(buchstaben: str) -> int:
    """Die Umkehrung von `folgebuchstaben`: „" → 0, „b" → 1, „aa" → 26."""
    if not buchstaben:
        return 0
    wert = 0
    for zeichen in buchstaben:
        wert = wert * 26 + (ord(zeichen) - ord("a") + 1)
    return wert - 1


def folgezahl(auftrag: dict[str, Any]) -> int:
    """Wie viele Aufnahmen der Lauf sieht - bei der Kernauswahl nur den Kern."""
    aufnahmen = int(auftrag.get("aufnahmen") or 0)
    return kern_anzahl(aufnahmen) if auswahl_aus(auftrag) == AUSWAHL_KERN else aufnahmen


def naechste_folge(auftrag: dict[str, Any], vorhandene: Iterable[dict[str, Any]]) -> str:
    """Die Folge für diesen Auftrag, gemessen an den `vorhandene` Aufträgen desselben Sprechers.

    Mitgezählt wird nur, wer eine Folge trägt.
    """
    code = optionscode(auftrag)
    zahl = str(folgezahl(auftrag))
    belegt = []
    for anderer in vorhandene:
        folge = str(anderer.get(FOLGE) or "")
        buchstaben = folge.lstrip("0123456789")
        if folge[: len(folge) - len(buchstaben)] == zahl and optionscode(anderer) == code:
            belegt.append(folgenummer(buchstaben))
    return zahl + (folgebuchstaben(max(belegt) + 1) if belegt else "")


def titel(auftrag: dict[str, Any]) -> str:
    """Optionscode und Folge - `ML-E-SRP-Ts-CI/43c`; ohne Folge nur der Code."""
    folge = str(auftrag.get(FOLGE) or "")
    return f"{optionscode(auftrag)}/{folge}" if folge else optionscode(auftrag)


# Der Zustand eines Laufs, wie ihn `zustand.json` nennt.
WARTET = "wartet"
LAEUFT = "laeuft"
FERTIG = "fertig"
GESCHEITERT = "gescheitert"
ABGEBROCHEN = "abgebrochen"

# Ab wann ein Lauf, der `laeuft` sagt, als hängend gilt (`Lauf.haengt`).
STILLSTAND_S = 15 * 60


def jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def wurzel(datenverzeichnis: Path) -> Path:
    return datenverzeichnis / SCHNAPPSCHUESSE


def lauf_verzeichnis(datenverzeichnis: Path, job_id: str) -> Path:
    return wurzel(datenverzeichnis) / job_id


def raeume_zwischenstaende_auf(verzeichnis: Path) -> list[str]:
    """Die Zwischenstände eines Laufs löschen; gibt zurück, was wegging.

    Der rechnende Prozess tut es selbst (`finetune.main`), der Läufer danach
    noch einmal (`laeufer.einmal`) - für einen Prozess, den der Kern erschlagen
    hat und der kein `finally` mehr erreicht. Ein liegen gebliebener
    Arbeitsstand wiegt Gigabyte, und eine volle Platte bringt den nächsten
    Lauf um.
    """
    entfernt: list[str] = []
    for name in ZWISCHENSTAENDE:
        pfad = verzeichnis / name
        if pfad.is_dir():
            shutil.rmtree(pfad, ignore_errors=True)
            entfernt.append(name)
    return entfernt


def lies_json(pfad: Path) -> dict[str, Any] | None:
    """Eine JSON-Datei, oder `None`, wenn sie fehlt oder gerade geschrieben wird."""
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def schreibe_json(pfad: Path, inhalt: dict[str, Any]) -> None:
    """Erst daneben, dann an die Stelle: Ein Leser sieht nie die Hälfte."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    entwurf = pfad.with_suffix(f"{pfad.suffix}.neu")
    entwurf.write_text(json.dumps(inhalt, ensure_ascii=False, indent=2), encoding="utf-8")
    entwurf.replace(pfad)


def haenge_an(pfad: Path, zeile: dict[str, Any]) -> None:
    """Eine Zeile an eine JSONL-Datei - der Weg, auf dem Fortschritt entsteht."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with pfad.open("a", encoding="utf-8") as datei:
        datei.write(json.dumps(zeile, ensure_ascii=False) + "\n")
        # Sonst stünde der Fortschritt im Puffer, und die Oberfläche läse nichts.
        datei.flush()


def lies_zeilen(pfad: Path) -> list[dict[str, Any]]:
    """Eine JSONL-Datei als Liste; unvollständige letzte Zeile wird übergangen."""
    if not pfad.is_file():
        return []
    zeilen = []
    for roh in pfad.read_text(encoding="utf-8").splitlines():
        try:
            zeilen.append(json.loads(roh))
        except ValueError:
            # Die letzte Zeile kann gerade geschrieben werden.
            continue
    return zeilen


@dataclass(frozen=True)
class Lauf:
    """Ein Auftrag samt dem, was daraus geworden ist - alles aus Dateien gelesen."""

    job_id: str
    verzeichnis: Path
    auftrag: dict[str, Any]
    zustand: dict[str, Any]

    @property
    def sprecher_id(self) -> str:
        return str(self.auftrag.get("sprecher_id", ""))

    @property
    def status(self) -> str:
        return str(self.zustand.get("status", WARTET))

    @property
    def offen(self) -> bool:
        """Noch zu rechnen - das ist die ganze Warteschlange."""
        return self.status == WARTET

    @property
    def stillstand_s(self) -> float:
        """Wie lange dieser Lauf nichts geschrieben hat, in Sekunden.

        Der Puls eines Laufs sind seine Dateien - der Prozess steckt in einem
        anderen Container, den der Webdienst nicht sieht. Ohne Fortschritt,
        Protokoll und Zustand zählt das Alter des Auftrags.
        """
        juengste = 0.0
        for name in (FORTSCHRITT, PROTOKOLL, ZUSTAND, AUFTRAG):
            datei = self.verzeichnis / name
            try:
                juengste = max(juengste, datei.stat().st_mtime)
            except OSError:
                continue
        if juengste == 0.0:
            return 0.0
        return max(0.0, time.time() - juengste)

    @property
    def haengt(self) -> bool:
        """Sagt `laeuft`, rührt sich aber nicht mehr - der Prozess ist tot, ohne
        es sagen zu können, oder kommt nicht voran. Von außen ist das dasselbe.

        Die Grenze liegt über der längsten stillen Strecke eines gesunden
        Laufs: Umwandeln und das Warten auf eine belegte Karte schreiben
        minutenlang nichts (`training/bewerten.py`).
        """
        return self.status == LAEUFT and self.stillstand_s > STILLSTAND_S


def anhalten_verlangt(verzeichnis: Path) -> bool:
    """Ob jemand diesen Lauf anhalten will (`HALT`)."""
    return (verzeichnis / HALT).exists()


def verlange_anhalten(verzeichnis: Path) -> None:
    """Den Wunsch hinlegen. Zweimal ist dasselbe wie einmal."""
    (verzeichnis / HALT).write_text(f"{jetzt()}\n", encoding="utf-8")


def lies_lauf(datenverzeichnis: Path, job_id: str) -> Lauf | None:
    verzeichnis = lauf_verzeichnis(datenverzeichnis, job_id)
    auftrag = lies_json(verzeichnis / AUFTRAG)
    if auftrag is None:
        return None
    return Lauf(
        job_id=job_id,
        verzeichnis=verzeichnis,
        auftrag=auftrag,
        # Ohne Zustand hat noch niemand angefangen.
        zustand=lies_json(verzeichnis / ZUSTAND) or {"status": WARTET},
    )


def alle_laeufe(datenverzeichnis: Path, sprecher_id: str = "") -> list[Lauf]:
    """Alle Läufe, älteste zuerst (die Kennung ist zeitlich sortierbar); leerer
    Sprecher heißt: alle."""
    if not wurzel(datenverzeichnis).is_dir():
        return []
    laeufe = (
        lies_lauf(datenverzeichnis, eintrag.name)
        for eintrag in sorted(wurzel(datenverzeichnis).iterdir())
        if eintrag.is_dir()
    )
    return [
        lauf
        for lauf in laeufe
        if lauf is not None and (not sprecher_id or lauf.sprecher_id == sprecher_id)
    ]


def naechster_offener(datenverzeichnis: Path) -> Lauf | None:
    """Der älteste offene Auftrag - einer nach dem anderen, über alle Sprecher."""
    for lauf in alle_laeufe(datenverzeichnis):
        if lauf.offen:
            return lauf
    return None


def manifestzeilen(verzeichnis: Path) -> Iterator[dict[str, Any]]:
    """Die Proben eines Schnappschusses, Zeile für Zeile, als Strom."""
    pfad = verzeichnis / MANIFEST
    if not pfad.is_file():
        return
    with pfad.open(encoding="utf-8") as datei:
        for roh in datei:
            if roh.strip():
                yield json.loads(roh)


# Gemessen wird nur, was nach einer Vorlage gesprochen wurde. Eine Korrektur
# aus „schreiben" trägt als Text eine abgenickte Maschinenausgabe - an ihr
# gemessen, zählte die Erkennung ihre eigenen Fehler als richtig. Sie lernt mit
# (gewichtet, `services/auftraege.GEWICHTE` in „lernen"), in jeder Faltung.
GEMESSENE_QUELLE = "vorlage"


def zeilen_fuer_faltung(
    verzeichnis: Path,
    faltung: int | None,
    daten: str,
    korpus: Path | None = None,
    kern: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Was in dieser Faltung gelernt und was daran gemessen wird.

    Lernzeilen und Messzeilen an einer Stelle, denn hier hängt die Zusage der
    Kreuzvalidierung: Kein Modell hört, woran es gemessen wird.

    `faltung = None` ist das Endmodell: lernt auf allem, misst nichts
    (`training/finetune.py`). Gemessen wird auf allen Fassungen und nur an
    Vorlagen (`GEMESSENE_QUELLE`), gelernt je nach `daten` - Modelle
    unterscheiden sich nur in ihren Trainingsdaten.

    Mit `kern` (Kernaufnahme → Faltung, `kernfaltungen_aus`) ist der Kern der
    ganze Korpus: Der Rest fehlt in Lern- und Messzeilen, die auch das
    Training steuern. Ohne `kern` alle Aufnahmen auf den Faltungen des
    Manifests.

    Selbst beschriftete Zeilen (`QUELLE_SELBST`) lernen in jeder Faltung mit
    ihrem Text aus `SELBSTBESCHRIFTUNG`, auch beim Kern - sie gehören nicht
    zum Korpus. Ohne aufgenommene Beschriftung fehlen sie.
    """
    lern: list[dict[str, Any]] = []
    mess: list[dict[str, Any]] = []
    beschriftet = selbstbeschriftung_aus(verzeichnis)
    for zeile in manifestzeilen(verzeichnis):
        if str(zeile.get("quelle")) == QUELLE_SELBST:
            text = beschriftet.get(str(zeile["audio"]))
            if text and (korpus is None or (korpus / str(zeile["audio"])).is_file()):
                lern.append({**zeile, "text": text})
            continue
        # Seit dem Schnappschuss verworfene Aufnahmen haben kein Audio
        # (`apps/hoeren/backend/api/recordings.py`) - wichtig bei Neustart und
        # `nachziehen.py`.
        if korpus is not None and not (korpus / str(zeile["audio"])).is_file():
            continue
        if kern is None:
            ihre = int(zeile.get("faltung", -1))
        elif (kennung := str(zeile.get("recording_id"))) in kern:
            ihre = kern[kennung]
        else:
            continue
        gemessen = str(zeile.get("quelle", GEMESSENE_QUELLE)) == GEMESSENE_QUELLE
        if faltung is not None and ihre == faltung and gemessen:
            mess.append(zeile)
            continue
        if daten == MIT_VARIANTEN or str(zeile.get("variante")) == augmentierung.ORIGINAL:
            lern.append(zeile)
    return lern, mess
