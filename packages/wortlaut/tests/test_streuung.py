"""Die Zusagen, auf denen die Vertrauensbereiche stehen.

Wenige Tests, aber genau die, deren Bruch niemand am Ergebnis sähe: Ein
Bereich, der bei jedem Aufruf ein wenig anders ausfällt, sieht aus wie ein
Bereich. Einer, der den Mittelwert verschiebt, auch.
"""

from __future__ import annotations

import random

from wortlaut import streuung


def _messreihe(aufnahmen: int = 40, fassungen: int = 4) -> list[tuple[str, float]]:
    """Eine Reihe mit dem Zuschnitt dieses Projekts: je Aufnahme vier Fassungen.

    Die Fassungen einer Aufnahme liegen dicht beieinander - genau das macht sie
    abhängig und ist der Grund für die blockweise Ziehung.
    """
    wuerfel = random.Random(4711)
    reihe = []
    for nummer in range(aufnahmen):
        niveau = max(0.0, wuerfel.gauss(0.15, 0.1))
        for _ in range(fassungen):
            reihe.append((f"rec{nummer:03d}", max(0.0, niveau + wuerfel.gauss(0.0, 0.01))))
    return reihe


def test_mittel_bleibt_der_mittelwert():
    """Der Bootstrap schätzt die Streuung - er rechnet die Zahl nicht neu.

    Die wichtigste Zusage überhaupt: Alles, was diese Datei tut, ist eine
    Zugabe. Verschöbe sie den Mittelwert auch nur in der sechsten Stelle,
    stünden in der Modelltabelle plötzlich andere Zahlen als vorher.
    """
    reihe = _messreihe()
    ergebnis = streuung.intervall(streuung.bilde(reihe))
    schlicht = round(sum(wert for _kennung, wert in reihe) / len(reihe), streuung.STELLEN)
    assert ergebnis is not None
    assert ergebnis.mittel == schlicht
    assert ergebnis.unten <= ergebnis.mittel <= ergebnis.oben


def test_derselbe_bereich_bei_jedem_aufruf():
    """Zwei Blicke auf dieselbe Messung ergeben dieselbe Zahl - auch die Ränder.

    Und zwar unabhängig davon, in welcher Reihenfolge die Zeilen gelesen
    wurden: `bilde` sortiert, sonst träfen dieselben Ziehungen andere Werte.
    """
    reihe = _messreihe()
    erst = streuung.intervall(streuung.bilde(reihe))
    nochmal = streuung.intervall(streuung.bilde(list(reversed(reihe))))
    assert erst == nochmal


def test_blockweise_ist_breiter_als_naiv():
    """Vier Fassungen einer Aufnahme sind vier Messungen an einem Gegenstand.

    Wer sie einzeln zieht, bekommt einen zu schmalen Bereich - und damit einen
    Vorsprung, den es nicht gibt. Das ist der ganze Grund für `BLOCK_AUFNAHME`.
    """
    reihe = _messreihe()
    blockweise = streuung.intervall(
        streuung.bilde(reihe, streuung.BLOCK_AUFNAHME),
        streuung.Verfahren(blockart=streuung.BLOCK_AUFNAHME),
    )
    naiv = streuung.intervall(
        streuung.bilde(reihe, streuung.BLOCK_EINHEIT),
        streuung.Verfahren(blockart=streuung.BLOCK_EINHEIT),
    )
    assert blockweise is not None and naiv is not None
    assert blockweise.breite > naiv.breite


def test_ohne_unterschied_kein_belegter_unterschied():
    """Zwei fast gleiche Reihen: Der Bereich muss die Null enthalten."""
    reihe = _messreihe()
    wuerfel = random.Random(9)
    drillinge = [(k, wert, wert + wuerfel.gauss(0.0, 0.0005)) for k, wert in reihe]
    ergebnis = streuung.unterschied(streuung.bilde_paare(drillinge))
    assert ergebnis is not None
    assert not ergebnis.belegt
    assert ergebnis.p > 0.05


def test_klarer_unterschied_wird_belegt():
    """Eine Reihe durchgehend besser: Der Bereich schließt die Null aus."""
    reihe = _messreihe()
    drillinge = [(k, wert, wert + 0.05) for k, wert in reihe]
    ergebnis = streuung.unterschied(streuung.bilde_paare(drillinge))
    assert ergebnis is not None
    assert ergebnis.belegt
    assert ergebnis.oben < 0.0
    # Nie genau null: gemessen wurde „kleiner als eine Ziehung", nicht Gewissheit.
    assert ergebnis.p > 0.0


def test_zu_wenig_ergibt_keine_auskunft():
    """Unter zwei Blöcken lieber nichts sagen als etwas, das wie eine Zahl aussieht."""
    assert streuung.intervall(streuung.bilde([("a", 0.2)])) is None
    assert streuung.intervall([]) is None
    assert streuung.unterschied(streuung.bilde_paare([("a", 0.2, 0.3)])) is None


def test_marke_nennt_das_verfahren():
    """Jede Zahl trägt mit, wie sie entstand - sonst ist sie nicht nachvollziehbar."""
    ergebnis = streuung.intervall(streuung.bilde(_messreihe()))
    assert ergebnis is not None
    assert ergebnis.als_dict()["marke"] == (
        f"bootstrap/aufnahme/{streuung.ZIEHUNGEN}/{streuung.NIVEAU}/{streuung.KEIM}"
    )
