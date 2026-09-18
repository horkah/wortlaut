"""Die Ränder abschneiden, bevor ein Modell zuhört.

**Wofür.** Eine Aufnahme beginnt, wenn jemand den Knopf drückt, und endet,
wenn er ihn wieder drückt. Dazwischen liegt die Äußerung - und davor und
dahinter liegt, wie lange jemand gebraucht hat. Bei Femke sind das im Schnitt
25 Sekunden für einen Satz, der gesprochen sieben dauert; vier ihrer zwanzig
Aufnahmen sprengen sogar Whispers Fenster von 30 Sekunden. In dieser Leere
erfindet Whisper Text - nicht aus Bosheit, sondern weil es auf Sprache
trainiert ist und in Stille nach Sprache sucht.

**Warum es hier keine zweite Stillemessung gibt.** `audio.untersuche` misst die
Randstille jeder Aufnahme längst, und zwar mit einer Schwelle, die relativ zur
Spitze dieser Aufnahme liegt: 35 dB darunter, nach unten begrenzt bei −60 dBFS.
Das ist genau die Robustheit, die hier gebraucht wird - ein Lüfter, eine
Straße, ein Brummen liegen unter dieser Schwelle und zählen als Stille, eine
leise Stimme liegt darüber. Eine zweite Rechnung daneben wäre eine zweite
Wahrheit über dieselbe Sache, und die beiden würden eines Tages auseinandergehen.

**Warum lieber zu wenig als zu viel.** Der Schaden ist einseitig: Ein bisschen
Stille zu viel kostet Rechenzeit, ein abgeschnittener Laut kostet die Aufnahme
und die Vorlage daneben stimmt nicht mehr. Deshalb drei Vorbehalte, und alle
drei in dieselbe Richtung:

* Ein **Rand** bleibt stehen (`RAND_S`) - was die Messung für Stille hält, wird
  nicht bis auf den letzten Rahmen weggenommen.
* Geschnitten wird nur, wenn es sich **lohnt** (`MINDEST_GEWINN_S`) - sonst
  entsteht eine zweite Datei für ein Zehntel Sekunde.
* Was übrig bliebe, darf eine **Untergrenze** nicht unterschreiten
  (`MINDESTDAUER_S`). Bleibt weniger, war die Messung nicht zu trauen, und es
  bleibt bei der ganzen Aufnahme.

Ein Geräusch, das lauter ist als diese Schwelle - eine zuschlagende Tür, ein
Husten -, gilt als Sprache und bleibt stehen. Das ist keine Nachlässigkeit,
sondern dieselbe Richtung: Lieber ein Geräusch zu viel im Ausschnitt als eine
Silbe zu wenig.

**Wer schneidet, muss überall schneiden.** Ein Modell, das auf geschnittenen
Ausschnitten gelernt hat, bekommt beim Diktieren ebenfalls geschnittene - das
regelt `vorbereitung.py`, und die Antwort darauf, ob geschnitten wird, steht im
Manifest des Standes. Stände von vor September 2026 kennen die Frage nicht;
für sie heißt das Fehlen der Angabe „nicht schneiden" (siehe `gilt`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import audio

# Für neue Läufe an. Die Ränder tragen nichts bei, was ein Sprechermodell
# lernen könnte, und bei langsamen Sprechern tragen sie das meiste.
VORGABE = True

# Was von der gemessenen Stille stehen bleibt, je Seite. Ein Viertel einer
# Sekunde ist mehr, als ein Anlaut braucht, und wenig gegen die Sekunden, um
# die es geht.
RAND_S = 0.25

# Ab welchem Gewinn überhaupt geschnitten wird - beide Seiten zusammen.
MINDEST_GEWINN_S = 0.3

# Was auf keinen Fall unterschritten wird. Bliebe weniger übrig, hat die
# Messung etwas anderes gefunden als die Äußerung.
MINDESTDAUER_S = 0.5


def gilt(wert: Any) -> bool:
    """Ob für diesen Lauf oder Stand geschnitten wird.

    **Fehlt die Angabe, wird nicht geschnitten.** Das ist die eine Regel, und
    sie gilt an jeder Stelle gleich: Aufträge und Modellstände von vor
    September 2026 kennen die Frage nicht, ihre Modelle haben ungeschnittene
    Ausschnitte gelernt, und sie müssen ungeschnittene zu hören bekommen. Ein
    Vorgabewert `True` an dieser Stelle würde jedem alten Modell beim Diktieren
    etwas anderes vorlegen, als es kennt - lautlos und ohne dass jemand sähe,
    woran es liegt.
    """
    return wert is True


def grenzen(wav: Path) -> tuple[float, float] | None:
    """Von wo bis wo die Äußerung reicht - oder `None`, wenn nichts zu tun ist.

    Gemessen wird nicht hier, sondern in `audio.untersuche`; hier stehen nur
    die Vorbehalte davor (siehe Kopf).
    """
    try:
        befund = audio.untersuche(wav)
    except audio.AudioFehler:
        # Nicht lesbar heißt: nicht anfassen. Ein Ausschnitt, der aus einer
        # kaputten Datei entsteht, ist nicht besser als die kaputte Datei.
        return None

    von = max(0.0, befund.stille_vorn_s - RAND_S)
    bis = min(befund.dauer_s, befund.dauer_s - befund.stille_hinten_s + RAND_S)
    if bis - von < MINDESTDAUER_S:
        return None
    if (befund.dauer_s - (bis - von)) < MINDEST_GEWINN_S:
        return None
    return von, bis

