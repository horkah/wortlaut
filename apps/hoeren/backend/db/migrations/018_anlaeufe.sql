-- Wie oft eine Korrektur aus „schreiben" gesprochen wurde, bis sie bestätigt war.
--
-- 1: unverändert bestätigt, mehr: so oft eingesprochen. NULL bei allem, was
-- nicht als Korrektur kam, und bei Korrekturen, die die Zahl nicht mitbrachten.
-- „lernen" leitet daraus auf Wunsch das Gewicht der Probe ab
-- (`services/auftraege.gewicht_fuer`).
ALTER TABLE recordings ADD COLUMN anlaeufe INTEGER;
