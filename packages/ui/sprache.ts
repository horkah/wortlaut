/**
 * Das Gebiet, in dem die Oberfläche Zahlen und Daten schreibt.
 *
 * **Nicht dasselbe wie die Sprache eines Profils.** Die steht am Sprecher und
 * entscheidet, was Whisper hört und welche Stimme vorliest
 * (`wortlaut/sprachen.py`, `wer.ts`). Diese Konstante hier entscheidet nur, wie
 * die Oberfläche `0,003` schreibt und nicht `0.003` - sie gehört zur
 * Beschriftung und damit zur Sprache der Oberfläche, die heute Deutsch ist.
 *
 * Beides auseinanderzuhalten ist der Punkt: Ein spanisches Profil auf einem
 * Server mit deutscher Oberfläche soll spanisch erkannt und spanisch
 * vorgelesen werden - die Dezimalstelle in der Modelltabelle daneben bleibt
 * deutsch, solange die Tabelle es ist.
 *
 * Wenn die Oberfläche einmal übersetzt wird, wird aus dieser Konstanten ein
 * Wert am Betrachter (siehe `docs/sprachen.md`). Bis dahin steht sie an einer
 * Stelle statt an dreien.
 */
export const ANZEIGE_GEBIET = 'de-DE';
