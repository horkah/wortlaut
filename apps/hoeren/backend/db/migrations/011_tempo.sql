-- Vorspulen: ein Faktor am Sprecher, und derselbe Faktor im Schlüssel jeder
-- Messung.
--
-- **Wozu.** Dysarthrische Sprache ist oft stark verlangsamt. Ob Whisper einen
-- sehr langsamen Sprecher besser versteht, wenn man ihn vorspult, ist eine
-- Messung und keine Meinung - und sie verlangt, dass alles, was gemessen und
-- trainiert wird, dieselbe Geschwindigkeit gehört hat.
--
-- **Warum am Sprecher und nicht am Lauf.** Weil es keine Achse ist, die man
-- nebeneinanderstellt, sondern ein Zustand, in dem sich der ganze Korpus
-- befindet. Ein Modell, das auf vorgespulter Sprache gelernt hat, muss sie
-- auch beim Diktieren bekommen; ein Vergleich mit der Baseline ist nur gegen
-- eine Baseline derselben Geschwindigkeit einer. Das sind zu viele Stellen,
-- als dass jede sich ihren Faktor selbst aussuchen dürfte.
--
-- **Warum es in den Schlüssel der Messung gehört.** `erkennungen` trägt schon
-- `rechenwerk` (`008_rechenwerk.sql`), und zwar aus genau diesem Grund: Eine
-- Zahl, die unter anderen Bedingungen entstanden ist, ist keine vergleichbare
-- Zahl. Mit `tempo` daneben gilt dasselbe für die Geschwindigkeit, und daraus
-- folgt von selbst, was gewünscht ist:
--
--   * Faktor zurück auf 1,0 - die alten Zeilen tragen 1,0 und zählen wieder
--     als gemessen. Nichts wird neu gerechnet.
--   * Faktor auf 2,0 - es gibt keine Zeile mit 2,0, also wird alles neu
--     gemessen. Die alten Zeilen bleiben unangetastet liegen.
--
-- Entwertet wird also nichts, es gilt nur gerade nicht. Der Preis steht in
-- derselben Rechnung: Wer alle drei Faktoren durchmisst, hat am Ende die
-- dreifache Zeilenzahl. Für eine Erprobungsphase ist das der richtige Handel -
-- Erkennungen sind abgeleitet und jederzeit neu zu rechnen, anders als eine
-- Aufnahme, die ein Mensch gesprochen hat.

-- 1,0 heißt „gar nicht vorspulen" und ist der Zustand, in dem sich jeder
-- Korpus bisher befand. Der Vorgabewert schreibt damit die Vergangenheit
-- richtig fort: Alles, was vor dieser Spalte gemessen wurde, wurde bei
-- einfacher Geschwindigkeit gemessen.
ALTER TABLE speakers ADD COLUMN tempo REAL NOT NULL DEFAULT 1.0;
ALTER TABLE erkennungen ADD COLUMN tempo REAL NOT NULL DEFAULT 1.0;

-- Der eindeutige Index bekommt das Tempo dazu, und darauf kommt es an.
--
-- Bisher durfte je Aufnahme, Modell und Fassung genau **eine** Zeile stehen
-- (`007_varianten.sql`); ein Wechsel des Rechenwerks ersetzte sie deshalb.
-- Für das Tempo wäre das falsch: Wer von 1,0 auf 2,0 geht und zurück, soll
-- seine alten Zahlen wiederfinden und nicht ein zweites Mal stundenlang
-- messen. Also darf je Tempo eine Zeile dastehen - und dieselbe Zusage
-- (genau eine je Kombination, worauf die Wiederaufnehmbarkeit beruht) gilt
-- weiterhin, nur eine Spalte breiter.
--
-- Das Rechenwerk bleibt bewusst **draußen**: Dort ist Ersetzen richtig. Eine
-- Rechenzeit vom Prozessor neben einer von der Karte wären zwei Maßstäbe in
-- einer Spalte, und niemand will zwischen ihnen hin- und herschalten.
DROP INDEX erkennungen_je_aufnahme_modell_und_variante;

CREATE UNIQUE INDEX erkennungen_je_aufnahme_modell_variante_und_tempo
    ON erkennungen (recording_id, modell, variante, tempo);
