-- Der Tempofaktor am Sprecherprofil fällt, samt allem, was er gemessen hat.
--
-- Er war ein Behelf: ein globaler Schalter (1,0 · 2,0 · 3,0), der den ganzen
-- Korpus in eine Geschwindigkeit versetzte, damit man überhaupt einmal
-- nachsehen konnte, ob Vorspulen einem sehr langsamen Sprecher hilft. Es hilft
-- - das war die Antwort, und sie ist nach wie vor richtig.
--
-- Nur ist der Weg dorthin inzwischen ein besserer. Der Trainer sucht den
-- Faktor selbst, je Faltung, an den Lernzeilen dieser Faltung, und legt die
-- Kurven am Ende übereinander (`training/tempowahl.py`). Er findet damit nicht
-- nur *ob*, sondern *wieviel*, auf eine Viertelstufe genau statt in drei
-- Sprüngen - und er trägt das Ergebnis im Modellstand mit sich, sodass
-- „schreiben" beim Diktieren genauso vorspult.
--
-- **Zwei Wege zu derselben Einstellung sind einer zu viel.** Der Profilfaktor
-- entwertete zusätzlich jede Messung, sobald jemand ihn umstellte - genau das
-- war sein Zweck, und genau das braucht niemand mehr, seit der Faktor am
-- Modell hängt und nicht am Korpus.

-- Die Messungen anderer Geschwindigkeiten gehen mit. Sie sind abgeleitet und
-- jederzeit neu zu rechnen (`005_auswertung.sql`), und sie beschreiben einen
-- Zustand, den es nicht mehr gibt: Die Auswertung misst wieder ausschließlich
-- bei einfacher Geschwindigkeit. Stehen zu lassen, was in keine Abfrage mehr
-- eingeht, hieße den Korpus mit Zeilen zu füllen, die niemand mehr lesen kann.
DELETE FROM erkennungen WHERE tempo <> 1.0;

-- Der eindeutige Index bekommt seine alte Gestalt zurück: je Aufnahme, Modell
-- und Fassung genau eine Zeile. Auf dieser Zusage beruht die
-- Wiederaufnehmbarkeit des Auswertungslaufs (`007_varianten.sql`).
DROP INDEX IF EXISTS erkennungen_je_aufnahme_modell_variante_und_tempo;

CREATE UNIQUE INDEX erkennungen_je_aufnahme_modell_und_variante
    ON erkennungen (recording_id, modell, variante);

-- Die Spalten selbst bleiben stehen, und das ist Absicht.
--
-- SQLite kann sie inzwischen zwar entfernen, aber `speakers` und `erkennungen`
-- hängen an Fremdschlüsseln und Indizes, und ein DROP COLUMN ist hier viel
-- Bewegung für null Gewinn: Eine Spalte, die auf ihrem Vorgabewert steht und
-- die kein Quelltext mehr liest, kostet kein Byte, das ins Gewicht fiele, und
-- kann nichts mehr behaupten. Was sie noch leistet, ist eine Auskunft für den,
-- der später in die Datenbank sieht: Hier stand einmal etwas.
