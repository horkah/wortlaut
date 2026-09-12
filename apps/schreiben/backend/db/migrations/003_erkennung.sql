-- Wie die Erkennung dieses Sprechers läuft - Modell und Aufbereitung.
--
-- Die Tabelle hieß `modellwahl` und hielt genau eine Sache: welchen Stand
-- dieser Sprecher gewählt hat (`002_modellwahl.sql`). Jetzt kommt eine zweite
-- dazu, und sie ist keine Modellwahl: ob das Diktat vor dem Erkennen
-- ausgesteuert wird. Ein Feld `aussteuern` in einer Tabelle namens
-- `modellwahl` wäre eine Zeile, über die jeder spätere Leser stolpert.
--
-- Also der ehrlichere Name. `erkennung` umfasst beides - womit gehört wird und
-- wie das Gehörte vorher aufbereitet ist -, und was später an Stellschrauben
-- dazukommt, findet hier seinen Platz, ohne dass die Tabelle noch einmal
-- umzieht.
--
-- **Warum Aussteuern die Vorgabe ist.** Der Aufnahmepegel eines Browsers hängt
-- am Gerät, am Abstand und an der Stimme; bei leisen Aufnahmen schöpft
-- Whisper den Wertebereich nicht aus, den seine Merkmalsberechnung erwartet.
-- Das Verfahren dagegen ist das schlichteste denkbare - ein einziger Faktor
-- über die ganze Aufnahme, bis die Spitze knapp unter dem Anschlag steht
-- (`wortlaut/augmentierung.py`, Abwandlung `pegel`). Es ändert nichts daran,
-- *wie* gesprochen wurde, nur daran, wie weit der Regler aufgedreht war - und
-- gerade die kleineren Modelle hören damit merklich besser.
--
-- Abschaltbar bleibt es trotzdem: Wer eine gut ausgesteuerte Kette hat, gewinnt
-- nichts mehr und soll die Aufbereitung nicht aufgedrängt bekommen.
CREATE TABLE erkennung (
    -- Genau eine Zeile je Datenbank, und je Sprecher gibt es eine Datenbank.
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    -- Was geladen wird: ein Grundmodell (`base`, `small`, …) oder ein Stand aus
    -- der Registry als `<sprecher_id>/<version>`. Leer heißt: keine eigene
    -- Wahl, es gilt die Vorgabe.
    modell_ref TEXT NOT NULL DEFAULT '',
    -- 1 = vor dem Erkennen aussteuern. Die Vorgabe, auch für Sprecher, die nie
    -- etwas eingestellt haben: Eine fehlende Zeile gilt als `1` (siehe
    -- `services/erkennung.py`) - sonst hinge das Verhalten daran, ob jemand
    -- die Modellwahl schon einmal angefasst hat.
    aussteuern INTEGER NOT NULL DEFAULT 1,
    geaendert  TEXT NOT NULL
);

-- Was schon gewählt war, bleibt gewählt. Das Aussteuern kommt auf die Vorgabe -
-- für eine bestehende Zeile gab es die Frage bisher nicht.
INSERT INTO erkennung (id, modell_ref, aussteuern, geaendert)
SELECT 1, ref, 1, gewaehlt FROM modellwahl WHERE id = 1;

DROP TABLE modellwahl;
