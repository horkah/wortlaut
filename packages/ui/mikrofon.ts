/**
 * Mikrofon: auswählen, verstärken, messen.
 *
 * Die Aufnahmekette ist überall dieselbe — im Mikrofontest wie in der
 * eigentlichen Aufnahme:
 *
 *     getUserMedia → GainNode → MediaStreamDestination → MediaRecorder
 *                        └→ AnalyserNode (Pegelanzeige)
 *
 * Der Analyser hängt hinter der Verstärkung. Die Anzeige zeigt damit, was
 * aufgezeichnet wird, und nicht, was das Mikrofon liefert; nur so passt sie
 * zu den Messwerten, die der Server später zurückmeldet.
 *
 * Die Kette entsteht auch bei Faktor 1,0. Ein zweiter, verstärkungsfreier
 * Weg wäre schneller zu lesen, aber es gäbe ihn nur, um im Alltag ungenutzt
 * zu bleiben — und er würde sich anders verhalten als der Weg, den der
 * Mikrofontest vorführt.
 *
 * Wichtig: Der Analyser wird bewusst *nicht* mit `kontext.destination`
 * verbunden. Sonst läge das Mikrofon auf den Lautsprechern.
 */

/**
 * Grenzen der Verstärkung. Über 20× wird jedes Mikrofon nur noch rauschen,
 * unter 1 wird gedämpft — auch ein zu heißer Eingang ist ein Fall für den
 * Regler, solange er noch nicht am Anschlag war.
 */
export const VERSTAERKUNG_SPANNE = { min: 0.5, max: 20, schritt: 0.5 };
export const VERSTAERKUNG_VORGABE = 1;

/**
 * Zielspitze beim Einmessen.
 *
 * Eingemessen wird auf die Spitze, nicht auf den Mittelwert: Was einmal
 * am Anschlag war, ist verloren, ein zu leiser Mittelwert dagegen nur
 * ungünstig. −6 dBFS lässt Luft für den Satz, der lauter gerät als der
 * Testsatz.
 */
export const ZIEL_SPITZE_DBFS = -6;

/**
 * Unterhalb dieser Spitze war nichts als Raumrauschen zu hören; daraus
 * ließe sich keine Verstärkung ableiten.
 */
export const MINDEST_SPITZE_DBFS = -60;

/** Wie `wortlaut.audio`: Stille ergibt −120 statt minus unendlich. */
export const STILL_DBFS = -120;

/** Fenster der Pegelmessung: rund 43 ms bei 48 kHz, ruhig genug fürs Auge. */
const FFT_GROESSE = 2048;

/** Ein auswählbares Aufnahmegerät. */
export type Mikrofon = { id: string; name: string };

/** Momentaufnahme des Pegels, beides in dBFS. */
export type Pegel = { rms: number; spitze: number };

export function dbfs(betrag: number): number {
  return betrag <= 0 ? STILL_DBFS : Math.max(STILL_DBFS, 20 * Math.log10(betrag));
}

/** Steht die Mikrofonauswahl in diesem Browser überhaupt zur Verfügung? */
export function auswahlMoeglich(): boolean {
  return Boolean(navigator.mediaDevices?.enumerateDevices);
}

/**
 * Die verfügbaren Mikrofone.
 *
 * Vor der ersten Erlaubnis liefert der Browser die Geräte ohne Namen — aus
 * gutem Grund, denn die Liste verrät sonst ungefragt etwas über das Gerät.
 * Solche Einträge bekommen hier einen Behelfsnamen; sobald einmal ein Strom
 * offen war, stehen die echten Namen bereit und ein zweiter Aufruf liefert
 * sie.
 */
export async function mikrofone(): Promise<Mikrofon[]> {
  if (!auswahlMoeglich()) return [];
  const geraete = await navigator.mediaDevices.enumerateDevices();
  return geraete
    .filter((geraet) => geraet.kind === 'audioinput')
    .map((geraet, nummer) => ({
      id: geraet.deviceId,
      name: geraet.label || `Mikrofon ${nummer + 1}`,
    }));
}

/** Meldet, wenn Geräte dazukommen oder verschwinden. Löst die Anmeldung wieder. */
export function beiGeraeteAenderung(melde: () => void): () => void {
  if (!auswahlMoeglich()) return () => {};
  navigator.mediaDevices.addEventListener('devicechange', melde);
  return () => navigator.mediaDevices.removeEventListener('devicechange', melde);
}

/**
 * Verstärkungsfaktor, der eine gemessene Spitze auf `ZIEL_SPITZE_DBFS` bringt.
 *
 * `bisher` ist der Faktor, der beim Messen schon aktiv war — die Messung
 * enthält ihn ja bereits.
 */
export function faktorFuerSpitze(spitzeDbfs: number, bisher = 1): number {
  const gebraucht = bisher * 10 ** ((ZIEL_SPITZE_DBFS - spitzeDbfs) / 20);
  const gerundet = Math.round(gebraucht / VERSTAERKUNG_SPANNE.schritt) * VERSTAERKUNG_SPANNE.schritt;
  return Math.min(VERSTAERKUNG_SPANNE.max, Math.max(VERSTAERKUNG_SPANNE.min, gerundet));
}

export type Kettenoptionen = {
  /** `null` heißt: was der Browser vorschlägt. */
  geraeteId?: string | null;
  verstaerkung?: number;
  /** Die browsereigene Pegelregelung (AGC). */
  autoPegel?: boolean;
};

/** Der Zugriff aufs Mikrofon ist gescheitert — mit einem Satz, der vorlesbar ist. */
export class MikrofonFehler extends Error {}

/**
 * Der Name des Fehlers, unabhängig von seinem Typ.
 *
 * `getUserMedia` wirft nicht durchweg `DOMException`: `OverconstrainedError`
 * ist in Chrome eine eigene Schnittstelle. Ein `instanceof` darauf schlägt
 * fehl, und der Ersatz für ein abgezogenes Gerät griffe nie.
 */
function fehlerName(ursache: unknown): string {
  return typeof ursache === 'object' && ursache !== null && 'name' in ursache
    ? String((ursache as { name: unknown }).name)
    : '';
}

function alsFehler(ursache: unknown): MikrofonFehler {
  switch (fehlerName(ursache)) {
    case 'NotAllowedError':
    case 'SecurityError':
      return new MikrofonFehler('Kein Zugriff auf das Mikrofon. Bitte im Browser erlauben.');
    case 'NotFoundError':
      return new MikrofonFehler('Es ist kein Mikrofon angeschlossen.');
    case 'NotReadableError':
      return new MikrofonFehler('Das Mikrofon ist belegt — ein anderes Programm hört mit.');
    default:
      return new MikrofonFehler('Aufnahme nicht möglich. Braucht HTTPS oder localhost.');
  }
}

/**
 * Ein offenes Mikrofon samt Verstärkung und Messung.
 *
 * Erzeugt wird sie mit `Aufnahmekette.oeffne`; am Ende muss `schliesse`
 * laufen, sonst bleibt die Aufnahmeanzeige des Browsers stehen.
 */
export class Aufnahmekette {
  /** Der Strom, der aufgezeichnet gehört — nach der Verstärkung. */
  readonly strom: MediaStream;
  /** Das gewünschte Gerät war nicht da, es wurde die Vorgabe geöffnet. */
  readonly ersatzGeraet: boolean;

  #roh: MediaStream;
  #kontext: AudioContext;
  #verstaerker: GainNode;
  #analyse: AnalyserNode;
  // Der Typ kommt aus dem Aufruf: eine Angabe `Float32Array` allein wäre in
  // neueren TypeScript-Fassungen zu weit für `getFloatTimeDomainData`.
  #puffer = new Float32Array(FFT_GROESSE);

  private constructor(roh: MediaStream, ersatzGeraet: boolean, verstaerkung: number) {
    this.#roh = roh;
    this.ersatzGeraet = ersatzGeraet;
    this.#kontext = new AudioContext();
    this.#verstaerker = this.#kontext.createGain();
    this.#verstaerker.gain.value = verstaerkung;
    this.#analyse = this.#kontext.createAnalyser();
    this.#analyse.fftSize = FFT_GROESSE;

    const quelle = this.#kontext.createMediaStreamSource(roh);
    const ziel = this.#kontext.createMediaStreamDestination();
    quelle.connect(this.#verstaerker);
    this.#verstaerker.connect(this.#analyse);
    this.#verstaerker.connect(ziel);
    this.strom = ziel.stream;
  }

  static async oeffne(optionen: Kettenoptionen = {}): Promise<Aufnahmekette> {
    const { geraeteId = null, verstaerkung = VERSTAERKUNG_VORGABE, autoPegel = true } = optionen;
    // Die Umwandlung macht ffmpeg; hier geht es nur um saubere Rohdaten.
    // Ausnahme ist die Pegelregelung: die muss wirken, bevor aufgezeichnet
    // wird, nachträglich ist ein zu leiser Pegel nicht mehr zu retten.
    const wunsch: MediaTrackConstraints = {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: false,
      autoGainControl: autoPegel,
    };

    let ersatzGeraet = false;
    let roh: MediaStream;
    try {
      roh = await navigator.mediaDevices.getUserMedia({
        audio: geraeteId ? { ...wunsch, deviceId: { exact: geraeteId } } : wunsch,
      });
    } catch (ursache) {
      // Ein gemerktes Gerät kann abgezogen worden sein. Dann lieber die
      // Vorgabe öffnen und es sagen, als die Aufnahme zu verweigern.
      const fehltNur =
        geraeteId &&
        ['OverconstrainedError', 'NotFoundError', 'ConstraintNotSatisfiedError'].includes(
          fehlerName(ursache),
        );
      if (!fehltNur) throw alsFehler(ursache);
      try {
        roh = await navigator.mediaDevices.getUserMedia({ audio: wunsch });
        ersatzGeraet = true;
      } catch (zweiterVersuch) {
        throw alsFehler(zweiterVersuch);
      }
    }

    const kette = new Aufnahmekette(roh, ersatzGeraet, verstaerkung);
    // Ein angehaltener Kontext liefert einen stummen Strom.
    await kette.#kontext.resume();
    return kette;
  }

  /** Welches Gerät tatsächlich offen ist — nach einem Ersatz nicht das gewünschte. */
  get geraeteId(): string | null {
    return this.#roh.getAudioTracks()[0]?.getSettings().deviceId ?? null;
  }

  get verstaerkung(): number {
    return this.#verstaerker.gain.value;
  }

  /** Wirkt sofort, auch mitten in einer laufenden Messung. */
  setzeVerstaerkung(faktor: number): void {
    this.#verstaerker.gain.value = faktor;
  }

  /** Der Pegel im Augenblick des Aufrufs. */
  miss(): Pegel {
    this.#analyse.getFloatTimeDomainData(this.#puffer);
    let spitze = 0;
    let summe = 0;
    for (const wert of this.#puffer) {
      const betrag = Math.abs(wert);
      if (betrag > spitze) spitze = betrag;
      summe += wert * wert;
    }
    return {
      rms: dbfs(Math.sqrt(summe / this.#puffer.length)),
      spitze: dbfs(spitze),
    };
  }

  schliesse(): void {
    this.#roh.getTracks().forEach((spur) => spur.stop()); // Mikrofon freigeben
    void this.#kontext.close();
  }
}

/**
 * Das Aufnahmeformat, das dieser Browser beherrscht.
 *
 * `MediaRecorder` liefert je nach Browser Opus in WebM oder OGG, Safari
 * liefert MP4. Was davon kommt, ist gleichgültig: umgewandelt wird
 * serverseitig an genau einer Stelle (`wortlaut.audio`).
 */
export function bevorzugterTyp(): string {
  const kandidaten = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'];
  return kandidaten.find((typ) => MediaRecorder.isTypeSupported(typ)) ?? '';
}

/** Nimmt auf, was durch die Kette läuft, bis die Rückgabefunktion gerufen wird. */
export function zeichneAuf(kette: Aufnahmekette): () => Promise<Blob> {
  const typ = bevorzugterTyp();
  const stuecke: Blob[] = [];
  const rekorder = new MediaRecorder(kette.strom, typ ? { mimeType: typ } : undefined);
  rekorder.ondataavailable = (ereignis) => {
    if (ereignis.data.size > 0) stuecke.push(ereignis.data);
  };
  rekorder.start();
  return () =>
    new Promise<Blob>((erfuelle) => {
      rekorder.onstop = () => erfuelle(new Blob(stuecke, { type: typ || 'audio/webm' }));
      rekorder.stop();
    });
}
