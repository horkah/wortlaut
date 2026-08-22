-- Eine Quelle stilllegen, ohne sie zu verlieren.
--
-- Wer merkt, dass ein erzeugter Text nicht taugt, hat bisher nur die Wahl
-- zwischen „weiter vorsprechen" und gar nichts: Die Einheiten stehen in der
-- Warteschlange, bis sie aufgenommen sind. `aktiv = 0` nimmt eine Quelle aus
-- der Warteschlange, lässt aber alles stehen, was schon zu ihr aufgenommen
-- wurde — der Korpus bleibt vollständig, nur der Nachschub hört auf.
--
-- Vorhandene Quellen sind aktiv; das ist der Zustand, in dem sie bisher waren.
ALTER TABLE text_sources ADD COLUMN aktiv INTEGER NOT NULL DEFAULT 1;
