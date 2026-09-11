-- `tiny` verschwindet, samt allem, was es gerechnet hat.
--
-- Das kleinste Whisper-Modell stand als unterste Sprosse der Messleiter in
-- `WORTLAUT_AUSWERTUNG_MODELLE` und als dritte Wahl beim Anlegen eines
-- Sprecherprofils. Beides ist weg: Für diesen Anwendungsfall - eine
-- abweichende Aussprache, gemessen an einer bekannten Vorlage - versteht
-- `tiny` so wenig, dass seine Zeilen keine Untergrenze mehr beschreiben,
-- sondern Rauschen. Eine Kurve, deren unterster Verlauf nur aussagt, dass ein
-- zu kleines Modell zu klein ist, macht den Vergleich der übrigen schlechter
-- lesbar, und der Lauf bezahlt sie mit Rechenzeit und Speicher.
--
-- Deshalb löscht diese Migration die Ergebnisse mit, statt sie liegen zu
-- lassen. Sie sind nichts, was verloren ginge: Anders als eine Aufnahme, die
-- ein Mensch gesprochen hat, ist eine Erkennung jederzeit neu zu rechnen -
-- genau darauf beruht schon die Wiederaufnehmbarkeit des Laufs
-- (`005_auswertung.sql`). Was hier fällt, ist abgeleitet und ersetzbar.
DELETE FROM erkennungen WHERE modell = 'tiny';

-- Profile, die auf `whisper-tiny` angelegt wurden, rücken auf `whisper-small`.
-- Das Feld sagt, worauf „lernen" später feintunen soll; ein Wert, den die
-- Verwaltung nicht mehr anbietet, wäre eine Falle, die erst beim ersten
-- Training aufgeht. `small` ist die kleinste Stufe, die dort noch Sinn ergibt,
-- und niemand hat auf diesen Profilen bisher trainiert - es gibt „lernen"
-- noch nicht.
UPDATE speakers
   SET basismodell = 'openai/whisper-small'
 WHERE basismodell = 'openai/whisper-tiny';
