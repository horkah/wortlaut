"""Das Fenster des Encoders - im Training so lang wie nötig, ausgeliefert 30 Sekunden.

Whisper füllt jede Aufnahme auf 30 Sekunden auf (3000 Merkmalsrahmen, 1500
Positionen im Encoder). Bei Sätzen von drei bis fünf Sekunden rechnet der
Encoder damit zum größten Teil Stille, und seine Aufmerksamkeit wächst mit
dem Quadrat der Länge.

**Gekürzt wird nur im Training** (`laeufe.FENSTER_GEKUERZT`): Merkmale auf die
längste Aufnahme des Laufs samt Zuschlag, die Positionseinbettung des Encoders
auf ihre ersten Einträge. Die Einbettung ist bei Whisper fest (sinusförmig,
ohne Gradient), gekürzt ist sie also derselbe Anfang derselben Tabelle. Vor
dem Sichern kommt die volle Tabelle zurück: CTranslate2 und faster-whisper
erwarten die 30-Sekunden-Geometrie, und gemessen wird der Stand so, wie er
ausgeliefert wird - mit Auffüllung, die er im Training nie gesehen hat. Ob
das schadet, zeigt die Tafel.

Die Rechnung der Länge ohne torch, damit sie sich prüfen lässt.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from wortlaut import laeufe, tempo

# Merkmalsrahmen je Sekunde (Schrittweite 10 ms) und das volle Fenster.
RAHMEN_JE_S = 100
VOLL = 3000
# Zuschlag auf die längste Aufnahme, wenn das Rezept nichts sagt.
ZUSCHLAG_S = 1.0


def rahmen_fuer(
    zeilen: Iterable[dict[str, Any]],
    faktor: float,
    rezept: dict[str, Any],
    abwandlung: str,
) -> int:
    """Wie viele Merkmalsrahmen das gekürzte Fenster braucht - höchstens `VOLL`.

    Die längste Aufnahme, vorgespult kürzer (`faktor`), mit der
    Tempo-Abwandlung länger (`augmentierung.tempo_faktor`, nur Stufe `voll`),
    dazu der Zuschlag, auf ganze Sekunden aufgerundet. Fehlt einer Zeile die
    Dauer, bleibt das Fenster voll: Abgeschnittene Sprache hieße falsche
    Beschriftung.
    """
    dauern = []
    for zeile in zeilen:
        dauer = zeile.get("dauer_s")
        if not dauer:
            return VOLL
        dauern.append(float(dauer))
    if not dauern:
        return VOLL
    laengste = max(dauern)
    if tempo.vorspulen_noetig(faktor):
        laengste /= faktor
    if abwandlung == laeufe.AUG_VOLL:
        langsamste = min((rezept.get("augmentierung") or {}).get("tempo_faktor") or [1.0])
        laengste /= max(0.1, float(langsamste))
    sekunden = math.ceil(laengste + float(rezept.get("fenster_zuschlag_s", ZUSCHLAG_S)))
    return min(VOLL, sekunden * RAHMEN_JE_S)


def kuerze(modell, rahmen: int) -> Any:
    """Den Encoder auf `rahmen` Merkmalsrahmen stellen; gibt zurück, was `stelle_her` braucht.

    Die Positionen sind halb so viele wie die Rahmen - die zweite Faltung des
    Encoders schreitet um zwei. Die Konfiguration teilen Encoder und Modell;
    nach ihr prüft Whisper die Länge der Eingabe und `generate`, ob sie kurz ist.
    """
    import torch

    encoder = modell.get_encoder()
    alt = encoder.embed_positions
    positionen = rahmen // 2
    neu = torch.nn.Embedding(
        positionen, alt.embedding_dim, dtype=alt.weight.dtype, device=alt.weight.device
    )
    with torch.no_grad():
        neu.weight.copy_(alt.weight[:positionen])
    neu.requires_grad_(False)
    encoder.embed_positions = neu
    urspruenglich = (alt, encoder.config.max_source_positions)
    encoder.config.max_source_positions = positionen
    encoder.max_source_positions = positionen
    return urspruenglich


def stelle_her(modell, urspruenglich: Any) -> None:
    """Die volle Einbettung und Länge zurück - vor dem Sichern."""
    encoder = modell.get_encoder()
    alt, positionen = urspruenglich
    encoder.embed_positions = alt.to(encoder.embed_positions.weight.device)
    encoder.config.max_source_positions = positionen
    encoder.max_source_positions = positionen
