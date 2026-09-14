"""Die Registry: was einen Modellstand ausmacht und wie er heißt."""

from __future__ import annotations

from wortlaut import registry


class TestKurzkennung:
    """Der kurze Code eines Standes: derselbe überall, verschieden je Stand."""

    def test_stabil_ueber_prozesse_hinweg(self) -> None:
        # Nicht `hash()`: Der ist je Prozess anders gesalzen, und eine Kennung,
        # die sich beim Neustart ändert, ist keine. Der Wert steht deshalb hier
        # ausgeschrieben - ändert sich die Rechnung, ändern sich alle Kennungen
        # aller Stände, und das soll niemandem versehentlich passieren.
        assert registry.kurzkennung("20260913T1448-lora-augmentiert-beides-voll-geduldig") == "Z9XAJ"

    def test_laenge_und_alphabet(self) -> None:
        # Keine Null, kein O, keine Eins, kein I, kein L - diese Kennung wird
        # abgetippt und durchgegeben.
        verboten = set("01OIL")
        for nummer in range(500):
            kennung = registry.kurzkennung(f"20260914T{nummer:04d}-lora-original")
            assert len(kennung) == 5
            assert not (set(kennung) & verboten), kennung

    def test_verschiedene_staende_verschiedene_kennungen(self) -> None:
        # Fünfhundert Versionen, wie sie wirklich entstehen: dieselbe Minute,
        # dasselbe Rezept, nur eine Achse anders.
        versionen = [
            f"20260914T{stunde:02d}{minute:02d}-{grund}lora-{daten}-{abschluss}-voll-geduldig"
            for stunde in range(5)
            for minute in (0, 30)
            for grund in ("", "medium-")
            for daten in ("original", "augmentiert")
            for abschluss in ("bester", "mittel", "beides", "interpoliert", "x")
        ]
        kennungen = {registry.kurzkennung(v) for v in versionen}
        assert len(kennungen) == len(versionen), "Zwei Stände teilen sich eine Kennung."
