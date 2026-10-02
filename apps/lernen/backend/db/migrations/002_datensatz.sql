-- Welche Läufe auf denselben Daten lernten - der Fingerabdruck ihres Datensatzes.
--
-- Die Wirkung einer Trainingsoption zeigt der gepaarte Vergleich zweier Läufe,
-- die sich nur in dieser Option unterscheiden. Dafür müssen sie dieselben
-- Daten gesehen haben, und das sagt die Zahl hinter dem Optionscode nicht:
-- Gleich viele Aufnahmen können andere sein, oder dieselben mit anderem Text
-- oder Zuschnitt.
--
-- SHA-256 über die Zeilen von `daten` - Aufnahme, Fassung, Faltung, Herkunft,
-- Text und Fingerabdruck der Audiodatei -, sortiert und unabhängig von der
-- Reihenfolge im Manifest (`register.datensatz`). Gewicht und Modus fehlen
-- mit Absicht: Das Gewicht ist eine Achse des Auftrags, kein Datum. Gerechnet
-- aus `daten` und bei jedem Eintragen neu, steht also nur zur Abfrage hier.
ALTER TABLE laeufe ADD COLUMN datensatz TEXT;

DROP VIEW uebersicht;
CREATE VIEW uebersicht AS
SELECT
    l.job_id,
    l.kennung,
    l.titel,
    l.datensatz,
    l.status,
    l.erstellt,
    l.beendet,
    l.entfernt,
    json_extract(l.auftrag, '$.basismodell') AS basismodell,
    json_extract(l.auftrag, '$.methode') AS methode,
    json_extract(l.auftrag, '$.daten') AS daten,
    json_extract(l.zustand, '$.metriken.wer') AS wer,
    json_extract(l.zustand, '$.metriken.cer') AS cer,
    (SELECT count(*) FROM daten d WHERE d.job_id = l.job_id) AS zeilen,
    (SELECT count(*) FROM messungen m WHERE m.job_id = l.job_id) AS messungen
FROM laeufe l;
