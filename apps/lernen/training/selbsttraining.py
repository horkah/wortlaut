"""Selbsttraining - unbeschriftetes Audio, beschriftet vom freigegebenen Modell.

Die Kandidaten legt der Server beim Auftrag ins Manifest: Abschnitte von
Diktaten, die in „schreiben" nie bestätigt wurden (`quelle = selbst`,
`services/auftraege.unbeschriftete_diktate`). Vor der ersten Faltung hört sie
das Modell, mit dem die Person gerade diktiert - freigegebener Stand oder
Grundmodell -, mit seinem Tempo. Aufgenommen wird, was es sicher genug hört
(`selbst_mindestsicherheit` im Rezept); gelernt wird es in jeder Faltung mit
dem kleinen Gewicht aus dem Manifest, gemessen nie
(`laeufe.zeilen_fuer_faltung`).

**Selbsttraining verstärkt eigene Fehler.** Deshalb die Schwelle, das
Gewicht, und deshalb steht die Beschriftung samt Sicherheit je Zeile in
`selbstbeschriftung.json`: Was gelernt wurde, lässt sich nachlesen. Ein
Neustart übernimmt die Datei nicht und beschriftet neu.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from wortlaut import corpus, laeufe, registry, sprachen, tempo

from apps.lernen.backend.config import einstellungen

# Mindestsicherheit, wenn das Rezept nichts sagt (`Transkript.sicherheit`).
MINDESTSICHERHEIT = 0.8


def _modell_und_tempo(datenverzeichnis: Path, auftrag: dict[str, Any]) -> tuple[str, float]:
    """Womit beschriftet wird: das freigegebene Modell samt seinem Tempo, sonst das Grundmodell."""
    sprecher_id = str(auftrag["sprecher_id"])
    modell = registry.freigegeben(datenverzeichnis, sprecher_id)
    if not modell:
        return laeufe.kurzname(str(auftrag.get("basismodell", ""))), tempo.VORGABE
    if not registry.ist_stand(modell):
        return modell, tempo.VORGABE
    besitzer, version = modell.split(registry.TRENNER, 1)
    try:
        faktor = float(registry.lies_stand(datenverzeichnis, besitzer, version).get("tempo") or 1.0)
    except (OSError, ValueError):
        faktor = tempo.VORGABE
    return modell, faktor


def _hoere(erkenner, wav: Path, sprache: str, faktor: float):
    """Eine Datei erkennen, vorgespult wie beim Diktat."""
    with tempfile.TemporaryDirectory() as ablage:
        if tempo.vorspulen_noetig(faktor):
            schnell = Path(ablage) / "vorgespult.wav"
            tempo.spule_vor(wav, schnell, faktor)
            wav = schnell
        return erkenner.transkribiere(wav, sprache=sprache)


def beschrifte(
    verzeichnis: Path,
    datenverzeichnis: Path,
    auftrag: dict[str, Any],
    rezept: dict[str, Any],
    bericht,
    erkenner=None,
) -> None:
    """Die Kandidaten des Manifests beschriften und `selbstbeschriftung.json` schreiben.

    Eine vorhandene Datei bleibt - dieselbe Beschriftung für alle sieben
    Trainings. `erkenner` für die Tests.
    """
    if laeufe.achse(auftrag, "selbsttraining") != laeufe.SELBST_AN:
        return
    pfad = verzeichnis / laeufe.SELBSTBESCHRIFTUNG
    if pfad.is_file():
        return

    korpuswurzel = datenverzeichnis / corpus.sprecher_relpfad(str(auftrag["sprecher_id"]))
    # Was seit dem Auftrag bestätigt oder gelöscht wurde, hat kein Audio mehr.
    zeilen = [
        zeile
        for zeile in laeufe.manifestzeilen(verzeichnis)
        if str(zeile.get("quelle")) == laeufe.QUELLE_SELBST
        and (korpuswurzel / str(zeile["audio"])).is_file()
    ]
    schwelle = float(rezept.get("selbst_mindestsicherheit", MINDESTSICHERHEIT))
    modell, faktor = _modell_und_tempo(datenverzeichnis, auftrag)
    inhalt: dict[str, Any] = {
        "modell": modell,
        "tempo": faktor,
        "schwelle": schwelle,
        "zeilen": {},
    }
    if not zeilen:
        laeufe.schreibe_json(pfad, inhalt)
        bericht.sage("Selbsttraining: kein unbeschriftetes Audio - es lernt nur der Korpus.")
        return

    from .bewerten import _hole_karte

    bericht.stufe("selbsttraining", test_zeilen=len(zeilen))
    bericht.sage(
        f"Selbsttraining: {registry.beschriftung(modell)} beschriftet {len(zeilen)} "
        f"unbestätigte Abschnitte, aufgenommen ab Sicherheit {schwelle:g}"
    )
    eigener = erkenner is None
    if eigener:
        from wortlaut.whisper.local import LokalerTranskriptor

        quelle: str | Path = modell
        if registry.ist_stand(modell):
            quelle = registry.ct2_verzeichnis(datenverzeichnis, modell)
        geraet, rechenart = einstellungen().rechenwerk()
        erkenner = LokalerTranskriptor(str(quelle), geraet=geraet, rechenart=rechenart)
        _hole_karte(erkenner, bericht)
    sprache = str(auftrag.get("sprache") or sprachen.VORGABE)
    try:
        for nummer, zeile in enumerate(zeilen, start=1):
            transkript = _hoere(erkenner, korpuswurzel / str(zeile["audio"]), sprache, faktor)
            sicherheit = transkript.sicherheit
            inhalt["zeilen"][str(zeile["audio"])] = {
                "text": transkript.text,
                "sicherheit": None if sicherheit is None else round(sicherheit, 4),
                "aufgenommen": bool(transkript.text.strip())
                and sicherheit is not None
                and sicherheit >= schwelle,
            }
            bericht.schritt(nummer, len(zeilen))
    finally:
        if eigener:
            erkenner.entlade()

    laeufe.schreibe_json(pfad, inhalt)
    aufgenommen = sum(1 for zeile in inhalt["zeilen"].values() if zeile["aufgenommen"])
    bericht.merke(selbst_aufgenommen=aufgenommen, selbst_kandidaten=len(zeilen))
    bericht.sage(f"Selbsttraining: {aufgenommen} von {len(zeilen)} Abschnitten aufgenommen")
