"""Der Startprompt - welche Wörter und woraus (`training/kontext.py`)."""

from __future__ import annotations

from wortlaut import laeufe

from apps.lernen.training import kontext


def _teile(wort: str) -> int:
    """Ein Zerteiler zum Nachrechnen: je angefangene vier Zeichen ein Stück."""
    return -(-len(wort.strip()) // 4)


class TestVokabular:
    def test_nur_seltene_woerter_haeufigste_zuerst(self) -> None:
        woerter = kontext.vokabular(
            [
                "Der Physiotherapeut kommt morgen.",
                "Morgen kommt der Physiotherapeut wieder.",
                "Die Logopädin übt mit mir.",
            ],
            _teile,
        )
        # „kommt", „morgen", „wieder" sind kurz - der Zerteiler kennt sie.
        assert woerter == ["Physiotherapeut", "Logopädin"]

    def test_gross_und_klein_zaehlen_zusammen(self) -> None:
        woerter = kontext.vokabular(
            ["Rollstuhlrampe hier.", "Die rollstuhlrampe dort.", "Die Rollstuhlrampe."], _teile
        )
        assert woerter == ["Rollstuhlrampe"]

    def test_das_budget_haelt(self) -> None:
        # Jedes Wort kostet vier Stücke und ein Komma.
        texte = [f"Zusammensetzung{nummer:02d}" for nummer in range(10)]
        woerter = kontext.vokabular(texte, _teile, budget=12)
        assert len(woerter) == 2

    def test_ohne_seltenes_wort_nichts(self) -> None:
        assert kontext.vokabular(["Ich gehe nach Hause."], _teile) == []


class TestTexte:
    def test_je_aufnahme_einmal_und_ohne_selbstbeschriftetes(self) -> None:
        zeilen = [
            {"recording_id": "rec_1", "variante": "original", "text": "Erster Satz"},
            {"recording_id": "rec_1", "variante": "rauschen", "text": "Erster Satz"},
            {"recording_id": "seg_1", "quelle": laeufe.QUELLE_SELBST, "text": "Geraten"},
            {"recording_id": "rec_2", "quelle": "korrektur", "text": "Bestätigt"},
        ]
        assert kontext.texte_fuer(zeilen) == ["Erster Satz", "Bestätigt"]
