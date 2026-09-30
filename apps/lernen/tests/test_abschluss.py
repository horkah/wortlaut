"""Welche Zwischenstände für die Mittelung auf der Platte bleiben.

Die besten nach der Steuergröße, nicht die jüngsten: Nach dem Early Stopping
sind die jüngsten die am stärksten überangepassten.
"""

from __future__ import annotations

from pathlib import Path

from apps.lernen.training.abschluss import zu_loeschen

# Die Validierung dreht nach dem zweiten Durchgang - wie im Decoder-Lauf, der
# über die Durchgänge 2, 6 und 7 mittelte.
PROTOKOLL = [
    {"loss": 3.2, "step": 20},
    *(
        {"eval_loss": verlust, "step": 25 * durchgang}
        for durchgang, verlust in enumerate(
            [2.32, 1.238, 1.279, 1.388, 1.385, 1.517, 1.535], start=1
        )
    ),
]


def _staende(*schritte: int) -> list[Path]:
    return [Path(f"/arbeit/checkpoint-{schritt}") for schritt in schritte]


def test_es_bleiben_die_besten_nicht_die_juengsten() -> None:
    weg = zu_loeschen(PROTOKOLL, _staende(25, 50, 75, 100, 125, 150, 175), 3)
    # Es bleiben die Durchgänge 2, 3 und 5.
    assert {pfad.name for pfad in weg} == {
        "checkpoint-25",
        "checkpoint-100",
        "checkpoint-150",
        "checkpoint-175",
    }


def test_nach_jedem_sichern_nur_das_noetige() -> None:
    # Nach dem zweiten Durchgang liegt noch nichts zu viel da.
    assert zu_loeschen(PROTOKOLL, _staende(25, 50), 3) == []
    # Ohne Mittelung bleibt nur der beste.
    assert [pfad.name for pfad in zu_loeschen(PROTOKOLL, _staende(50, 75), 1)] == [
        "checkpoint-75"
    ]


def test_bei_gleichstand_bleibt_der_fruehere() -> None:
    protokoll = [{"eval_loss": 1.0, "step": 10}, {"eval_loss": 1.0, "step": 20}]
    assert [pfad.name for pfad in zu_loeschen(protokoll, _staende(10, 20), 1)] == [
        "checkpoint-20"
    ]


def test_ohne_steuergroesse_bleibt_ein_stand() -> None:
    weg = zu_loeschen(PROTOKOLL, [*_staende(50, 75), Path("/arbeit/checkpoint-999")], 1)
    assert [pfad.name for pfad in weg] == ["checkpoint-75"]


def test_bei_wer_zaehlt_die_wer() -> None:
    protokoll = [
        {"eval_loss": 1.0, "eval_wer": 0.30, "step": 10},
        {"eval_loss": 2.0, "eval_wer": 0.20, "step": 20},
    ]
    assert [pfad.name for pfad in zu_loeschen(protokoll, _staende(10, 20), 1, "wer")] == [
        "checkpoint-10"
    ]
