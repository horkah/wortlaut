/**
 * Der einzige Ort, an dem diese App mit dem Backend spricht.
 *
 * Den Sprecher nennt keine Anfrage mehr: Der Server leitet ihn aus dem
 * vorgelegten Zugang ab (siehe backend/deps.py). Der Zugang ist entweder der
 * eines Sprechers - `<sprecher_id>.<geheimnis>`, gekommen über einen Link -,
 * der Verwaltertoken oder der Aufsichtstoken.
 *
 * Genau eine Ausnahme gibt es: Die Wege unter `/api/admin/…` nennen ihren
 * Sprecher in der Adresse. Sie gehören der Aufsicht, und die hat keinen
 * eigenen - sie sieht über alle hinweg (siehe backend/api/admin.py).
 */

import { alsJson, api } from '$ui/api';
// Wer der Server in diesem Browser sieht - die Form steht in `$ui/wer`, weil
// alle drei Apps dieselbe Antwort lesen.
import type { Wer } from '$ui/wer';

// Die Wege dieser App liegen auf der Wurzel - sie ist der Einstieg (siehe
// `APPS` in `$ui/apps`). Wie eine Anfrage hinausgeht und wie ein Fehlschlag
// aussieht, steht in `$ui/api` und damit einmal für alle drei Apps.
const { hole, anfrage } = api('/api');

export type Sprecher = {
  id: string;
  name: string;
  sprache: string;
  erstellt: string;
  /** Wann der geltende Zugang ausgegeben wurde; null heißt: noch keiner da. */
  zugang_erneuert: string | null;
};


/** Ein frisch ausgegebener Zugang - im Klartext nur genau hier. */
export type NeuerZugang = { sprecher_id: string; zugang: string; erneuert: string };

export type Einheit = { id: string; text: string; dauer_geschaetzt_s: number };

export type Naechste = {
  vorher: Einheit | null;
  aktuell: Einheit | null;
  nachher: Einheit | null;
  erledigt: number;
  gesamt: number;
};

export type Aufnahme = {
  id: string;
  prompt_id: string;
  dauer_s: number;
  pegel_dbfs: number;
  modus: string;
  status: string;
  hinweise: string[];
};

export type Quelle = {
  id: string;
  art: string;
  titel: string;
  einheiten: number;
  aktiv: boolean;
  erstellt: string;
};

export type Fortschritt = {
  sekunden: number;
  aufnahmen: number;
  offene_einheiten: number;
  nach_modus: Record<string, number>;
  nach_quelle: Record<string, number>;
  marke_brauchbar_s: number;
  marke_gut_s: number;
};

// Wo der Zugang liegt und wie er an eine Anfrage kommt, steht in `$ui/zugang`:
// Alle drei Apps lesen denselben Eintrag desselben Browsers (siehe dort).
export { setzeZugang, zugang } from '$ui/zugang';

// ── Wer ruft ────────────────────────────────────────────────────────────────

/** Für wen dieser Browser eingestellt ist - die Antwort kommt vom Server. */

// ── Verwaltung ──────────────────────────────────────────────────────────────

export const sprecherListe = () => anfrage<Sprecher[]>('/speakers');

export const sprecherAnlegen = (eingabe: { name: string; sprache: string }) =>
  anfrage<Sprecher>('/speakers', alsJson(eingabe));

/** Eine Sprache, die dieses System führt (`wortlaut/sprachen.py`). */
export type Sprachwahl = {
  kuerzel: string;
  name: string;
  vorgabe: boolean;
};

/**
 * Welche Sprachen zur Wahl stehen - vom Server und nicht aus einer Liste hier.
 *
 * Im Auswahlfeld stand einmal eine fest eingetragene Sprache. Wer eine zweite
 * hinzufügt, sollte dafür die Bibliothek ändern und nicht drei Dateien.
 */
export const sprachen = () => anfrage<Sprachwahl[]>('/sprachen');


/** Neuen Zugang ausgeben. Ein vorhandener gilt danach nicht mehr. */
export const zugangAusgeben = (sprecher: string) =>
  anfrage<NeuerZugang>(`/speakers/${sprecher}/zugang`, { method: 'POST' });

export const zugangZurueckziehen = (sprecher: string) =>
  anfrage<void>(`/speakers/${sprecher}/zugang`, { method: 'DELETE' });

// ── Textquellen ─────────────────────────────────────────────────────────────

export const quellen = () => anfrage<Quelle[]>('/sources');

export const quelleAusLLM = (auftrag: { thema: string; altersspanne: string; umfang: number }) =>
  anfrage<Quelle>('/sources/llm', alsJson(auftrag));

export function quelleAusDatei(datei: File) {
  const formular = new FormData();
  formular.append('datei', datei);
  return anfrage<Quelle>('/sources/upload', { method: 'POST', body: formular });
}

export const quelleLoeschen = (quelle: string) =>
  anfrage<void>(`/sources/${quelle}`, { method: 'DELETE' });

/** Stilllegen oder wieder aufnehmen; gibt die Quelle im neuen Zustand zurück. */
export const quelleUmstellen = (quelle: string, aktiv: boolean) =>
  anfrage<Quelle>(`/sources/${quelle}`, alsJson({ aktiv }, 'PATCH'));

/**
 * Der geschnittene Text einer Quelle als Klartext.
 *
 * Über `hole` statt `anfrage`, weil hier kein JSON zurückkommt. Ein
 * `window.open` auf die Adresse ginge nicht: Die API verlangt einen Zugang im
 * Kopf der Anfrage und liefe sonst in ein 401.
 */
export async function quelleText(quelle: string): Promise<string> {
  return (await hole(`/sources/${quelle}/text`)).text();
}

// ── Aufnehmen ───────────────────────────────────────────────────────────────

export const sitzungBeginnen = () =>
  anfrage<{ id: string; begonnen: string }>('/sessions', { method: 'POST' });

export const naechsteEinheit = (sitzung: string | null, zufall = false) => {
  const suche = new URLSearchParams();
  if (sitzung) suche.set('session', sitzung);
  if (zufall) suche.set('zufall', 'true');
  const anhang = suche.toString();
  return anfrage<Naechste>(`/prompts/next${anhang ? `?${anhang}` : ''}`);
};

export function aufnahmeSenden(eingabe: {
  audio: Blob;
  prompt_id: string;
  modus: string;
  session: string | null;
}) {
  const formular = new FormData();
  formular.append('audio', eingabe.audio, 'aufnahme.webm');
  formular.append('prompt_id', eingabe.prompt_id);
  formular.append('modus', eingabe.modus);
  if (eingabe.session) formular.append('session', eingabe.session);
  return anfrage<Aufnahme>('/recordings', { method: 'POST', body: formular });
}

export const aufnahmeVerwerfen = (aufnahme: string) =>
  anfrage<void>(`/recordings/${aufnahme}`, { method: 'DELETE' });

/**
 * Eine eigene Aufnahme anhören - für „Meine Daten" und die Auswertung.
 *
 * `fassung` wählt zwischen dem Original und den drei Abwandlungen (siehe
 * `varianten` in der Auswertung). Ausgelassen heißt Original; das ist der Fall
 * in „Meine Daten", wo es nur die gesprochene Aufnahme gibt.
 *
 * Als Blob und nicht als Adresse im `src`: Die Datei hängt am Zugang, und ein
 * `<audio src>` schickt keine Kopfzeilen mit.
 */
export const meineAufnahmeAudio = (aufnahme: string, fassung?: string) =>
  blob(`/recordings/${aufnahme}/audio${fassung ? `?fassung=${encodeURIComponent(fassung)}` : ''}`);

// ── Vorlesen ────────────────────────────────────────────────────────────────

/** Eine Stimme, die der Server sprechen kann. Leere Liste ist der Normalfall. */
export type Servestimme = {
  schluessel: string;
  name: string;
  erklaerung: string;
  sprache: string;
};

export const servestimmen = () => anfrage<Servestimme[]>('/vorlesen/stimmen');

/**
 * Vorgelesenes kann sich unter derselben Adresse ändern.
 *
 * Die Adresse nennt Vorlage und Stimme, nicht aber, wann gerechnet wurde. Wird
 * eine Stimme neu gesprochen, bleibt sie dieselbe und der Inhalt ist ein
 * anderer. Der Server sagt das mit `Cache-Control: no-cache`; für alles, was
 * ein Browser **vorher** abgelegt hat, gilt aber noch die alte Regel - und die
 * hat er sich selbst geraten. `cache: 'no-cache'` an der Anfrage räumt auch
 * das ab: Nachgefragt wird in jedem Fall, übertragen nur, was neu ist.
 *
 * Ohne das spielte Safari auf dem iPhone eine alte Aufnahme weiter, über das
 * Neuladen der Seite hinweg, und die Anfrage kam am Server gar nicht erst an.
 */
const FRISCH: RequestInit = { cache: 'no-cache' };

/** Ein fester Satz in dieser Stimme - zum Vergleichen, bevor man wählt. */
export const stimmprobe = (stimme: string) =>
  blob(`/vorlesen/probe?stimme=${encodeURIComponent(stimme)}`, FRISCH);

/**
 * Eine Vorlage in einer Servestimme - als Blob, wie jedes Audio hier.
 *
 * Der Server rechnet sie, falls sie noch nicht vorliegt; beim zweiten Mal
 * kommt sie aus der Ablage (`services/vorlesen.py`). Eine 404 heißt „nimm die
 * Browserstimme" und ist kein Fehler, den jemand lesen müsste.
 */
export const vorlageVorgelesen = (vorlage: string, stimme: string) =>
  blob(`/prompts/${vorlage}/vorlesung?stimme=${encodeURIComponent(stimme)}`, FRISCH);

// ── Fortschritt ─────────────────────────────────────────────────────────────

export const fortschritt = () => anfrage<Fortschritt>('/progress');

// ── Aufsicht ────────────────────────────────────────────────────────────────
//
// Alles hier hängt am `WORTLAUT_ADMIN_TOKEN` des Servers. Ohne ihn antwortet
// jeder dieser Wege mit 401 - auch in der Entwicklung.

export type Kennzahlen = {
  aufnahmen: number;
  verworfen: number;
  sekunden: number;
  quellen: number;
  einheiten: number;
  sitzungen: number;
  bytes_audio: number;
};

export type Uebersicht = Sprecher & { pin_gesetzt: boolean; kennzahlen: Kennzahlen };

export type AufsichtQuelle = {
  id: string;
  art: string;
  titel: string;
  parameter: Record<string, unknown>;
  aktiv: boolean;
  einheiten: number;
  erstellt: string;
};

export type AufsichtSitzung = {
  id: string;
  begonnen: string;
  zuletzt_aktiv: string;
  aufnahmen: number;
};

export type AufsichtAufnahme = {
  id: string;
  prompt_id: string;
  text: string;
  quelle_art: string;
  dauer_s: number;
  pegel_dbfs: number;
  modus: string;
  status: string;
  hinweise: string[];
  externe_id: string | null;
  audio_vorhanden: boolean;
  erstellt: string;
};

export type Einsicht = {
  sprecher: Uebersicht;
  quellen: AufsichtQuelle[];
};

export type Aufnahmenseite = { gesamt: number; ab: number; aufnahmen: AufsichtAufnahme[] };
export type Sitzungenseite = { gesamt: number; ab: number; sitzungen: AufsichtSitzung[] };

export const alleSprecher = () => anfrage<Uebersicht[]>('/admin/speakers');

export const einsicht = (sprecher: string) => anfrage<Einsicht>(`/admin/speakers/${sprecher}`);

export const aufsichtSitzungen = (sprecher: string, ab = 0, anzahl = 10) =>
  anfrage<Sitzungenseite>(`/admin/speakers/${sprecher}/sessions?ab=${ab}&anzahl=${anzahl}`);

export const aufsichtAufnahmen = (sprecher: string, ab = 0, anzahl = 10) =>
  anfrage<Aufnahmenseite>(`/admin/speakers/${sprecher}/recordings?ab=${ab}&anzahl=${anzahl}`);

export const sprecherUmbenennen = (sprecher: string, name: string) =>
  anfrage<Uebersicht>(`/admin/speakers/${sprecher}`, alsJson({ name }, 'PATCH'));

/** Ob eine PIN gesetzt ist - nie die PIN selbst; siehe `Uebersicht.pin_gesetzt`. */
export type PinStand = { gesetzt: boolean };

/**
 * Die PIN einer Person setzen, ändern oder (mit `pin: null`) wegnehmen - ohne
 * die alte zu kennen. Die Aufsicht ist der Rückweg, wenn jemand seine PIN
 * vergessen hat.
 */
export const pinSetzenAdmin = (sprecher: string, pin: string | null) =>
  anfrage<PinStand>(`/admin/speakers/${sprecher}/pin`, alsJson({ pin }, 'PATCH'));

/**
 * Löschen verlangt die Kennung ein zweites Mal - einmal als Ziel, einmal als
 * Absicht. Der Server prüft das; hier steht es, damit kein Aufruf ohne
 * gebaut werden kann.
 */
export const aufnahmeLoeschen = (sprecher: string, aufnahme: string) =>
  anfrage<void>(`/admin/speakers/${sprecher}/recordings/${aufnahme}`, { method: 'DELETE' });

export const alleAufnahmenLoeschen = (sprecher: string) =>
  anfrage<{ geloescht: number }>(
    `/admin/speakers/${sprecher}/recordings?bestaetigung=${encodeURIComponent(sprecher)}`,
    { method: 'DELETE' },
  );

export const sprecherLoeschen = (sprecher: string) =>
  anfrage<{ geloescht: string[]; zu_pruefen: string[] }>(
    `/admin/speakers/${sprecher}?bestaetigung=${encodeURIComponent(sprecher)}`,
    { method: 'DELETE' },
  );

/** Die Adresse einer Aufnahme zum Abhören - mit Zugang, deshalb über `blob()`. */
export const aufnahmeAudio = (sprecher: string, aufnahme: string) =>
  blob(`/admin/speakers/${sprecher}/recordings/${aufnahme}/audio`);

// ── Ausleiten ───────────────────────────────────────────────────────────────

/**
 * Eine Datei vom Server holen und dem Browser zum Speichern geben.
 *
 * Warum nicht schlicht ein Link: Diese Wege verlangen einen Zugang im Kopf der
 * Anfrage, und ein `window.open` schickte keinen mit - es liefe in ein 401.
 * Also wird geholt, in einen Blob gelegt und ein unsichtbarer Verweis
 * angeklickt.
 *
 * Der Preis: Die Datei liegt kurz im Arbeitsspeicher des Browsers. Für einen
 * Korpus von einigen hundert Megabyte geht das; wer einen sehr großen Bestand
 * wegsichert, nimmt besser `curl` (siehe docs/betrieb.md).
 */
export async function lade(pfad: string, optionen: RequestInit = {}): Promise<void> {
  const [inhalt, dateiname] = await blobMitNamen(pfad, optionen);
  const adresse = URL.createObjectURL(inhalt);
  const verweis = document.createElement('a');
  verweis.href = adresse;
  verweis.download = dateiname;
  verweis.click();
  // Erst freigeben, wenn der Browser den Download übernommen hat.
  setTimeout(() => URL.revokeObjectURL(adresse), 10_000);
}

export const sicherungSprecher = (sprecher: string) =>
  lade(`/admin/speakers/${sprecher}/sicherung`);

export const datensatzSprecher = (sprecher: string) =>
  lade(`/admin/speakers/${sprecher}/datensatz`);

export const sicherungGesamt = () => lade('/admin/sicherung');

/** Wie `anfrage`, aber für alles, was kein JSON ist. */
async function blob(pfad: string, optionen: RequestInit = {}): Promise<Blob> {
  return (await blobMitNamen(pfad, optionen))[0];
}

async function blobMitNamen(pfad: string, optionen: RequestInit = {}): Promise<[Blob, string]> {
  const antwort = await hole(pfad, optionen);
  // Den Namen bestimmt der Server (er kennt die Zeitmarke); ohne Angabe bleibt
  // der letzte Teil des Pfades.
  const angabe = antwort.headers.get('content-disposition') ?? '';
  const treffer = angabe.match(/filename="?([^";]+)"?/);
  return [await antwort.blob(), treffer?.[1] ?? (pfad.split('/').pop() || 'wortlaut')];
}

// ── Konto ───────────────────────────────────────────────────────────────────
//
// Ein Sprecher sieht sich selbst - dieselben Formen wie oben bei der Aufsicht
// (`Uebersicht`, `AufsichtQuelle`, `Sitzungenseite`, `Aufnahmenseite`), denn
// der Server füllt sie über dieselbe Zählung (`services/uebersicht.py`). Nur
// der Weg ist ein anderer: keine Kennung in der Adresse, sie steckt im
// vorgelegten Zugang. Anhören und Verwerfen einer Aufnahme laufen weiter über
// `meineAufnahmeAudio` und `aufnahmeVerwerfen` weiter oben.
//
// Ist eine PIN gesetzt, verlangen die drei lesenden Wege sie zusätzlich als
// `X-Pin`-Kopfzeile - deshalb der optionale `pin`-Parameter unten. `pinStand`
// selbst bleibt ungeschützt: Er beantwortet ja gerade die Frage, ob überhaupt
// nach einer PIN gefragt werden muss.

export type Konto = { sprecher: Uebersicht; quellen: AufsichtQuelle[] };

function mitPin(pin?: string): RequestInit {
  return pin ? { headers: { 'X-Pin': pin } } : {};
}

export const pinStand = () => anfrage<PinStand>('/konto/pin');

export const pinSetzen = (pin: string | null) =>
  anfrage<PinStand>('/konto/pin', alsJson({ pin }, 'PATCH'));

export const meinKonto = (pin?: string) => anfrage<Konto>('/konto', mitPin(pin));

export const meineSitzungen = (ab = 0, anzahl = 10, pin?: string) =>
  anfrage<Sitzungenseite>(`/konto/sessions?ab=${ab}&anzahl=${anzahl}`, mitPin(pin));

export const meineAufnahmen = (ab = 0, anzahl = 10, pin?: string) =>
  anfrage<Aufnahmenseite>(`/konto/recordings?ab=${ab}&anzahl=${anzahl}`, mitPin(pin));

/** Sich selbst umbenennen - dieselbe Beschriftung, die die Aufsicht ändert. */
export const michUmbenennen = (name: string, pin?: string) =>
  anfrage<Uebersicht>('/konto', {
    ...alsJson({ name }, 'PATCH'),
    // Die PIN kommt zu den Kopfzeilen von `alsJson` hinzu, nicht an ihre
    // Stelle: Ohne `Content-Type` läse FastAPI den Rumpf nicht als JSON.
    headers: { 'Content-Type': 'application/json', ...(pin ? { 'X-Pin': pin } : {}) },
  });

/**
 * Die eigenen Daten mitnehmen - dieselben zwei Dateien, die die Aufsicht zieht
 * (der Server packt sie über denselben Dienst, siehe `services/ausleitung.py`).
 */
export const meineSicherung = (pin?: string) => lade('/konto/sicherung', mitPin(pin));

export const meinDatensatz = (pin?: string) => lade('/konto/datensatz', mitPin(pin));

// ── Auswertung ──────────────────────────────────────────────────────────────
//
// Wie gut verschiedene Modelle diesem Sprecher zuhören, gemessen an seinen
// eigenen Aufnahmen und drei Abwandlungen davon (`backend/api/auswertung.py`). Zwei Auskünfte, absichtlich
// getrennt: `auswertung()` liefert die Zahlen für die Kurve und wird abgefragt,
// solange die Seite offen ist; `vergleich()` liefert die Texte einer einzelnen
// Aufnahme und erst auf Klick. Die Texte in jede Abfrage zu packen hieße, bei
// jedem Takt ein Vielfaches der Zahlen zu übertragen, die gemeint sind.

export type Metrik = {
  schluessel: string;
  name: string;
  erklaerung: string;
  /** Ob ein hoher Wert der bessere ist - die Fehlerraten sind andersherum. */
  hoch_ist_gut: boolean;
  einheit: string;
  /** Feste Obergrenze der Achse; `null` heißt: nach den Daten richten. */
  obergrenze: number | null;
};

export type Laufstand = {
  laeuft: boolean;
  erledigt: number;
  gesamt: number;
  uebersprungen: number;
  aktuell: string;
  fehler: string | null;
  /** Es rechnet gerade jemand anderes - es läuft immer nur ein Lauf. */
  fremder_lauf: boolean;
};

/** Eine Fassung der Aufnahme: das Original oder eine seiner Abwandlungen. */
export type Variante = {
  schluessel: string;
  name: string;
  erklaerung: string;
};

export type Punkt = {
  nummer: number;
  aufnahme_id: string;
  dauer_s: number;
  erstellt: string;
  /**
   * modell → fassung → maß → Wert. Fehlt ein Eintrag, ist er noch nicht
   * gerechnet. Der Server rechnet hier nichts zusammen: Welche Zahl die Kurve
   * zeigt, hängt am gewählten Maß, und die Tabelle zeigt ohnehin jede.
   */
  werte: Record<string, Record<string, Record<string, number>>>;
};

export type Auswertung = {
  modelle: string[];
  varianten: Variante[];
  metriken: Metrik[];
  stand: Laufstand;
  punkte: Punkt[];
};

export type Erkennung = {
  modell: string;
  variante: string;
  text: string;
  wer: number;
  cer: number;
  mer: number;
  wil: number;
  genauigkeit: number;
  rechenzeit_s: number;
};

export type Vergleich = {
  nummer: number;
  aufnahme_id: string;
  referenz: string;
  dauer_s: number;
  erkennungen: Erkennung[];
};

export const auswertung = () => anfrage<Auswertung>('/auswertung');

export const vergleich = (aufnahme: string) => anfrage<Vergleich>(`/auswertung/${aufnahme}`);

export const auswertungStarten = () =>
  anfrage<Laufstand>('/auswertung/start', { method: 'POST' });

export const auswertungStoppen = () =>
  anfrage<Laufstand>('/auswertung/stopp', { method: 'POST' });
