"""Das Endmodell - das Mittel der Faltungsmodelle, kein siebtes Training.

Jede Faltung hat auf fünf Sechsteln gelernt und ist an ihrem Sechstel
gemessen. Ausgeliefert wird ihr elementweises Mittel („Model Soup"): Jede
Aufnahme steckt in fünf der sechs Modelle, und nichts wird ungeprüft neu
trainiert. Ein siebtes Training auf allem müsste Haltepunkt und α blind aus
den Faltungen übernehmen - und konnte dabei entgleisen, ohne dass es jemand
vor der Prüfung am Ende sah.

**Gemittelt werden die gespeicherten Gewichte.** Bei LoRA sind sie schon
verschmolzen (`finetune.trainiere`, `merge_and_unload`): Jede Faltung ist
Grundmodell plus B·A, ihr Mittel also genau Grundmodell plus das Mittel der
Änderungen. Die Faktoren A und B getrennt zu mitteln wäre falsch - das Produkt
der Mittel ist nicht das Mittel der Produkte.

**Was schiefging, bleibt draußen** (`pruefe_faltungen`): eine Faltung ohne
Gewichte (abgebrochen), eine, die ausfranst (mehr Fehler als Wörter auf einem
Viertel ihrer Aufnahmen), und eine, die gemessen am Grundmodell auf denselben
Aufnahmen weit hinter den anderen liegt. Dieselben Schwellen wie die
Plausibilitätsprüfung (`bewerten.befund_ueber`), die danach trotzdem läuft.
Ihre Messungen bleiben in der Zahl des Laufs - sie beschreibt das Verfahren;
„Modelle“ lässt sie weg (`api/modelle._gemittelte_faltungen`).

Die Prüfung ohne torch, damit sie sich ohne Karte nachrechnen lässt.
"""

from __future__ import annotations

import json
import logging
import shutil
import statistics
from pathlib import Path
from typing import Any

from wortlaut import corpus, laeufe
from wortlaut.whisper.local import STARTPROMPT

from .bewerten import AUSGEFRANST_ANTEIL, PRUEF_SPIELRAUM, _grundzeilen

# Ins Fehlerprotokoll (`wortlaut/fehlerlog.py`).
_log = logging.getLogger("wortlaut.training")

# Ausgefranst erst ab so vielen Zeilen - bei einer winzigen Faltung wäre
# sonst eine einzige missratene Aufnahme ein Viertel.
MINDESTENS_AUSGEFRANST = 2
# Zuschlag auf beide WER im Verhältnis zum Grundmodell.
VERSATZ = 0.01

# Die Gewichte eines gesicherten Standes: eine Datei oder mehrere Teile.
GEWICHTE = "*.safetensors"

def pruefe_faltungen(
    zeilen: list[dict[str, Any]],
    faltungen: list[int],
    vorhanden: set[int],
    grundmodell: dict[str, float] | None = None,
) -> tuple[list[int], list[dict[str, Any]]]:
    """Welche Faltungen ins Mittel gehen - und welche warum nicht.

    `zeilen` sind die Messungen aller Faltungen (`bewerten.bewerte_faltung`),
    `vorhanden` die Faltungen, deren Gewichte daliegen, `grundmodell` die WER
    des unveränderten Grundmodells je Aufnahme aus „hören".

    **Ausreißer am Verhältnis zum Grundmodell, nicht an der WER.** Die WER
    einer Faltung hängt vor allem daran, wie schwer ihre zurückgehaltenen
    Aufnahmen sind; das Grundmodell auf denselben Aufnahmen rechnet das heraus.
    Draußen bleibt eine Faltung, deren Verhältnis über dem Anderthalbfachen
    des Medians liegt und die zugleich schlechter ist als das Grundmodell.
    Ohne Werte des Grundmodells entfällt diese Prüfung.
    """
    wer_je: dict[int, list[float]] = {}
    grund_je: dict[int, list[tuple[float, float]]] = {}
    for zeile in zeilen:
        if zeile.get("faltung") is None:
            continue
        faltung = int(zeile["faltung"])
        wer_je.setdefault(faltung, []).append(float(zeile["wer"]))
        schluessel = str(zeile.get("recording_id"))
        if grundmodell and schluessel in grundmodell:
            grund_je.setdefault(faltung, []).append((float(zeile["wer"]), grundmodell[schluessel]))

    # Wie viel schlechter oder besser als das Grundmodell, auf denselben Aufnahmen.
    # Der kleine Zuschlag hält einen fehlerfreien Grundwert von null aus.
    verhaeltnis = {
        faltung: (statistics.fmean(p[0] for p in paare) + VERSATZ)
        / (statistics.fmean(p[1] for p in paare) + VERSATZ)
        for faltung, paare in grund_je.items()
        if paare
    }
    median = statistics.median(verhaeltnis.values()) if verhaeltnis else None

    behalten: list[int] = []
    ausgelassen: list[dict[str, Any]] = []
    for faltung in faltungen:
        werte = wer_je.get(faltung, [])
        grund = ""
        if faltung not in vorhanden:
            grund = "abgebrochen"
        elif werte and sum(1 for wer in werte if wer > 1.0) >= max(
            MINDESTENS_AUSGEFRANST, round(AUSGEFRANST_ANTEIL * len(werte))
        ):
            grund = "ausgefranst"
        elif (
            median is not None
            and faltung in verhaeltnis
            and verhaeltnis[faltung] > 1.0
            and verhaeltnis[faltung] > median * PRUEF_SPIELRAUM
        ):
            grund = "ausreisser"
        if grund:
            ausgelassen.append(
                {
                    "faltung": faltung,
                    "grund": grund,
                    "wer": round(statistics.fmean(werte), 4) if werte else None,
                    "verhaeltnis": round(verhaeltnis[faltung], 3)
                    if faltung in verhaeltnis
                    else None,
                    "median": round(median, 3) if median is not None else None,
                }
            )
        else:
            behalten.append(faltung)
    return behalten, ausgelassen


def _gewichtsdateien(verzeichnis: Path) -> dict[str, str]:
    """Name jedes Gewichts → die Datei, in der es steht - einfach oder in Teilen."""
    index = verzeichnis / "model.safetensors.index.json"
    if index.is_file():
        return dict(json.loads(index.read_text(encoding="utf-8"))["weight_map"])
    from safetensors import safe_open

    with safe_open(str(verzeichnis / "model.safetensors"), framework="pt") as datei:
        return {name: "model.safetensors" for name in datei.keys()}


def mittle(quellen: list[Path], ziel: Path) -> None:
    """Die Gewichte der `quellen` elementweise mitteln und nach `ziel` schreiben.

    Datei für Datei und Gewicht für Gewicht, in float32 gerechnet und in der
    Genauigkeit der Quelle abgelegt: Im Speicher liegt höchstens ein Modell,
    nie sechs. Alles andere - Konfiguration, Zerteiler, Ausleser, der Index
    geteilter Gewichte - kommt aus der ersten Quelle; es ist überall dasselbe.
    """
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file

    if not quellen:
        raise RuntimeError("Keine Faltung taugt zum Mitteln.")
    ziel.mkdir(parents=True, exist_ok=True)
    erste = quellen[0]
    for datei in erste.iterdir():
        if datei.is_file() and not datei.match(GEWICHTE):
            shutil.copy2(datei, ziel / datei.name)

    karten = [_gewichtsdateien(quelle) for quelle in quellen]
    for quelle, karte in zip(quellen, karten, strict=True):
        if set(karte) != set(karten[0]):
            raise RuntimeError(f"{quelle.name} hat andere Gewichte als {erste.name}.")

    for dateiname in sorted(set(karten[0].values())):
        teil: dict[str, torch.Tensor] = {}
        for name in sorted(n for n, d in karten[0].items() if d == dateiname):
            werte = []
            for quelle, karte in zip(quellen, karten, strict=True):
                with safe_open(str(quelle / karte[name]), framework="pt") as datei:
                    werte.append(datei.get_tensor(name))
            if not torch.is_floating_point(werte[0]):
                # Ganzzahliges (Positionszähler u. Ä.) ist in allen gleich.
                teil[name] = werte[0]
                continue
            summe = torch.zeros_like(werte[0], dtype=torch.float32)
            for wert in werte:
                summe += wert.to(torch.float32)
            teil[name] = (summe / len(werte)).to(werte[0].dtype)
            werte.clear()
        save_file(teil, str(ziel / dateiname), metadata={"format": "pt"})


def _abschlussbild(faltungen: list[dict[str, Any]], art: str) -> dict[str, Any]:
    """Was der Abschluss in den gemittelten Faltungen tat - für Tafel und Steckbrief.

    α als Median: Jede Faltung trägt ihr eigenes, im Mittel steckt keines
    allein. Zurückgenommen heißt: in allen.
    """
    berichte = [dict(k.get("abschluss") or {}) for k in faltungen]
    alphas = sorted(float(b["alpha"]) for b in berichte if b.get("alpha") is not None)
    return {
        "art": art,
        "alpha": statistics.median(alphas) if alphas else None,
        "staende": [],
        "zurueckgenommen": bool(berichte) and all(b.get("zurueckgenommen") for b in berichte),
        "hinweis": f"Median über {len(alphas)} Faltungen" if alphas else "",
        "faltungen": berichte,
    }


def baue(
    verzeichnis: Path,
    datenverzeichnis: Path,
    auftrag: dict[str, Any],
    zeilen: list[dict[str, Any]],
    mitgenommen: dict[str, Any],
    bericht,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    """Das Endmodell mitteln; gibt Gewichte, Befund und Abschlussbild zurück.

    Danach sind die Gewichte der Faltungen weg - der Stand trägt ihr Mittel.
    Beim Kontext `vokabular` bekommt er den Startprompt aus allen Lerntexten
    (`kontext.py`), nicht den der ersten Faltung.
    """
    from .finetune import _name_fuer, _rezept_fuer
    from . import kontext

    bericht.stufe("mitteln")
    faltungen = list(range(laeufe.FALTUNGEN))
    gelernt = [k for k in mitgenommen.get("faltungen", [])]
    vorhanden = {int(k["faltung"]) for k in gelernt}
    grundmodell = {
        schluessel: werte["wer"]
        for schluessel, werte in _grundzeilen(
            datenverzeichnis,
            str(auftrag["sprecher_id"]),
            laeufe.kurzname(str(auftrag.get("basismodell", ""))),
        ).items()
    }
    if not grundmodell:
        bericht.sage(
            "Keine Werte des Grundmodells aus „hören“ - Ausreißer lassen sich nicht erkennen, "
            "geprüft wird nur auf Abbruch und Ausfransen."
        )
    behalten, ausgelassen = pruefe_faltungen(zeilen, faltungen, vorhanden, grundmodell)
    for eintrag in ausgelassen:
        satz = f"Faltung {eintrag['faltung'] + 1} bleibt draußen: {eintrag['grund']}"
        if eintrag["wer"] is not None:
            satz += f" (WER {eintrag['wer']:.2f}"
            if eintrag["verhaeltnis"] is not None:
                satz += (
                    f", {eintrag['verhaeltnis']:.2f}-fach des Grundmodells, "
                    f"Median {eintrag['median']:.2f}"
                )
            satz += ")"
        bericht.sage(satz)
        _log.warning("%s - %s", verzeichnis.name, satz)
    if not behalten:
        raise RuntimeError("Keine Faltung taugt zum Mitteln - jede ist ausgelassen.")

    gewichte = verzeichnis / laeufe.GEWICHTE
    ziel = gewichte / _name_fuer(None)
    bericht.sage(
        f"Gemittelt über {len(behalten)} von {laeufe.FALTUNGEN} Faltungen: "
        + ", ".join(str(faltung + 1) for faltung in behalten)
    )
    mittle([gewichte / _name_fuer(faltung) for faltung in behalten], ziel)

    # Der Startprompt der ersten Faltung kennt nur ihre Lerntexte.
    (ziel / STARTPROMPT).unlink(missing_ok=True)
    if laeufe.achse(auftrag, "kontext") == laeufe.KONTEXT_VOKABULAR:
        from transformers import WhisperTokenizerFast

        korpuswurzel = datenverzeichnis / corpus.sprecher_relpfad(str(auftrag["sprecher_id"]))
        alle, _ = laeufe.zeilen_fuer_faltung(
            verzeichnis, None, korpuswurzel, laeufe.kernfaltungen_aus(verzeichnis, auftrag)
        )
        woerter = kontext.schreibe(
            ziel,
            alle,
            WhisperTokenizerFast.from_pretrained(ziel),
            _rezept_fuer(str(auftrag["methode"]), str(auftrag["basismodell"])),
        )
        bericht.sage(f"Startprompt: {len(woerter)} Wörter aus allen Lerntexten")

    for faltung in faltungen:
        shutil.rmtree(gewichte / _name_fuer(faltung), ignore_errors=True)

    befund = {
        "verfahren": "mittel",
        "faltungen": behalten,
        "ausgelassen": ausgelassen,
        "gescheitert": list(mitgenommen.get("gescheitert") or []),
    }
    bericht.ereignis(art="endmodell", **befund)
    art = laeufe.achse(auftrag, "abschluss")
    return ziel, befund, _abschlussbild([k for k in gelernt if k["faltung"] in behalten], art)
