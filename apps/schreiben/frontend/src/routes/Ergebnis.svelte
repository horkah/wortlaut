<script lang="ts">
  /**
   * Der Text, abschnittsweise: vorlesen, anklicken, neu einsprechen, bestätigen.
   *
   * Vorgelesen wird, weil die Zielperson den Text nicht sicher lesen kann -
   * gehört wird der Fehler, nicht gesehen. Deshalb liest die Ansicht von
   * selbst los, sobald sie erscheint, und markiert dabei, wo sie gerade ist.
   *
   * Ein Klick auf einen Abschnitt betrifft nur diesen: Er wird neu
   * eingesprochen und neu transkribiert, alle anderen bleiben unberührt. Das
   * ist der Grund, warum Abschnitte einzeln mit Audio gespeichert werden.
   */
  import AudioPlayer from '$ui/AudioPlayer.svelte';
  import Recorder from '$ui/Recorder.svelte';
  import SegmentList from '$ui/SegmentList.svelte';
  import { einstellungen } from '$ui/einstellungen.svelte';
  import { brichVorlesenAb, sprich, stimmeNachUri, stimmeVerfuegbar, stimmen } from '$ui/speak';
  import { kannTeilen, teile } from '$ui/teilen';
  import { inDieZwischenablage } from '$ui/zwischenablage';
  import {
    abschnittAudioUrl,
    abschnittNeuSprechen,
    bestaetigen,
    postausgangSenden,
    sitzungHolen,
    type Versand,
  } from '../lib/api';
  import { gehZu, setzeSitzung, zustand } from '../lib/zustand.svelte';

  let liest = $state(false);
  let gesprochen = $state<string | null>(null);
  // Gemerkt wird die Kennung, nicht der Abschnitt: Nach jeder Antwort des
  // Servers sind die Abschnitte neue Objekte, die Kennung bleibt.
  let bearbeitetId = $state<string | null>(null);
  let stand = $state<'bereit' | 'verstehe' | 'sendet'>('bereit');
  let versand = $state<Versand | null>(null);
  let fehler = $state('');
  // Wie lange „Kopiert" stehen bleibt. Lang genug, um es zu lesen, ohne dass
  // der Knopf seine Beschriftung dauerhaft verliert.
  let kopiert = $state(false);
  let kopierUhr: ReturnType<typeof setTimeout> | undefined;
  // Einmal beim Aufbau gefragt und nicht bei jedem Bild: Ob dieses Gerät ein
  // Teilen-Blatt hat, ändert sich nicht, solange die Seite offen ist.
  const teilbar = kannTeilen();

  const sitzung = $derived(zustand.sitzung!);
  const abschnitte = $derived(sitzung?.abschnitte ?? []);
  const bestaetigt = $derived(sitzung?.status === 'bestaetigt');
  const ganzerText = $derived(abschnitte.map((a) => a.text).join(' '));
  const bearbeitet = $derived(abschnitte.find((a) => a.id === bearbeitetId) ?? null);

  // ── Vorlesen ──────────────────────────────────────────────────────────────

  async function lies() {
    if (liest) return halt();
    liest = true;
    fehler = '';
    try {
      for (const abschnitt of abschnitte) {
        if (!liest) break; // in der Zwischenzeit angehalten
        gesprochen = abschnitt.id;
        await sprich(abschnitt.text, {
          stimme: stimmeNachUri(einstellungen.stimmeUri, stimmen(zustand.sprache)),
          tempo: einstellungen.tempo,
        });
      }
    } catch (ursache) {
      // Ein Abbruch mitten im Satz meldet sich hier ebenfalls; das ist kein
      // Fehler, der jemanden interessiert.
      if (liest) fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      liest = false;
      gesprochen = null;
    }
  }

  function halt() {
    liest = false;
    brichVorlesenAb();
    gesprochen = null;
  }

  // ── Einen Abschnitt neu einsprechen ───────────────────────────────────────

  function waehle(id: string) {
    if (bestaetigt) return; // bestätigter Text wird nicht mehr angefasst
    halt();
    bearbeitetId = bearbeitetId === id ? null : id; // zweiter Klick schließt wieder
  }

  async function ersetze(aufnahme: Blob) {
    if (!bearbeitet) return;
    fehler = '';
    stand = 'verstehe';
    try {
      setzeSitzung(await abschnittNeuSprechen(bearbeitet.id, aufnahme));
      bearbeitetId = null;
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      stand = 'bereit';
    }
  }

  // ── Abschließen ───────────────────────────────────────────────────────────

  async function fertig() {
    halt();
    fehler = '';
    stand = 'sendet';
    try {
      versand = await bestaetigen(sitzung.id);
      setzeSitzung(await sitzungHolen(sitzung.id));
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      stand = 'bereit';
    }
  }

  async function nochmalSenden() {
    stand = 'sendet';
    try {
      const bericht = await postausgangSenden();
      versand = { eingestellt: 0, ...bericht };
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      stand = 'bereit';
    }
  }

  function neuerText() {
    halt();
    setzeSitzung(null);
    gehZu('/');
  }

  // ── Weiterreichen ─────────────────────────────────────────────────────────

  /**
   * Den ganzen Text in die Zwischenablage - ohne ihn vorher auszuwählen.
   *
   * Das ist der Weg aus dieser App heraus. Diktiert wird, um das Gesagte
   * anderswo zu benutzen: in einer Nachricht, in einer Mail, in einem
   * Formular. Bis hierher endete er an einem schreibgeschützten Textfeld, aus
   * dem man erst mit dem Finger auswählen musste - antippen, halten, die
   * Griffe an den Rand ziehen. Genau diese Bewegung gelingt der Zielperson
   * oft nicht (Grundentscheidung 7), und sie ist auch gar nicht nötig: Der
   * ganze Text ist gemeint, jedes Mal.
   */
  async function kopiere() {
    fehler = '';
    if (await inDieZwischenablage(ganzerText)) {
      kopiert = true;
      clearTimeout(kopierUhr);
      kopierUhr = setTimeout(() => (kopiert = false), 4000);
    } else {
      // Still zu scheitern wäre hier das Schlimmste: Er merkte es erst beim
      // Einfügen, in einer anderen App, wo nichts mehr zu retten ist.
      fehler = 'Das Kopieren hat nicht geklappt. Der Text steht unten und lässt sich auswählen.';
    }
  }

  /**
   * Den Text an eine andere App weitergeben - der kurze Weg.
   *
   * Kopieren ist der halbe: Danach muss die Ziel-App noch geöffnet, das Feld
   * gefunden und „Einfügen" getroffen werden. Das Teilen-Blatt macht daraus
   * einen Schritt, und der Text steht schon im Nachrichtenfeld.
   */
  async function weitergeben() {
    fehler = '';
    const ergebnis = await teile(ganzerText);
    if (ergebnis === 'ging-nicht') {
      // Nicht geteilt heißt nicht verloren: Was das Blatt nicht nimmt, nimmt
      // die Zwischenablage.
      await kopiere();
    }
  }

  // Von selbst vorlesen, sobald der Text dasteht - genau dafür ist die Ansicht
  // da: Wer nicht sicher liest, hört den Fehler, statt ihn zu suchen.
  //
  // Abschaltbar unter „Audio", und zwar dort und nicht hier: Ob überhaupt von
  // selbst vorgelesen wird, entscheidet man einmal - unterwegs, neben anderen
  // Leuten, ist ein Telefon, das von selbst zu sprechen anfängt, der Grund,
  // es wegzulegen. Der Knopf „▶ Vorlesen" oben bleibt davon unberührt; er ist
  // die Handlung, das hier ist die Gewohnheit dahinter.
  if (einstellungen.liestVonSelbst && stimmeVerfuegbar(zustand.sprache) && !bestaetigt) lies();
</script>

<div class="reihe kopfzeile">
  {#if stimmeVerfuegbar(zustand.sprache)}
    <button class="knopf" onclick={lies}>{liest ? '■ Anhalten' : '▶ Vorlesen'}</button>
  {/if}
  <span class="gedaempft">{abschnitte.length} Abschnitte · zum Bessern anklicken</span>
</div>

<SegmentList
  {abschnitte}
  {gesprochen}
  offen={bearbeitetId}
  schriftRem={einstellungen.schriftRem * 0.8}
  onwaehle={waehle}
/>

{#if bearbeitet}
  <div class="karte">
    <p class="gedaempft">Diesen Abschnitt noch einmal sprechen:</p>
    <p class="satz" style="font-size:{einstellungen.schriftRem}rem">{bearbeitet.text}</p>
    {#if bearbeitet.hat_audio}
      <AudioPlayer quelle={abschnittAudioUrl(bearbeitet.id)} beschriftung="So klang es" />
    {/if}
    <div class="mitte">
      <Recorder
        onaufnahme={ersetze}
        deaktiviert={stand === 'verstehe'}
        geraeteId={einstellungen.mikrofonId}
        verstaerkung={einstellungen.verstaerkung}
        autoPegel={einstellungen.autoPegel}
      />
      {#if stand === 'verstehe'}<p class="gedaempft">Wird verstanden …</p>{/if}
      <button class="knopf" onclick={() => (bearbeitetId = null)}>Doch nicht</button>
    </div>
  </div>
{/if}

{#if bestaetigt}
  <h2>Fertig</h2>
  <p>Der Text ist abgeschickt.</p>
  {#if versand}
    <p class="gedaempft">
      {versand.gesendet} von {versand.gesendet + versand.offen} Abschnitten sind bei „hören"
      angekommen.
    </p>
    {#if versand.offen > 0}
      <div class="hinweise">
        <strong>Noch nicht alles übergeben.</strong>
        <p>
          {versand.fehler ?? 'Unbekannter Grund.'} Der Rest liegt im Postausgang; verloren
          gehen kann nichts, und ein neuer Versuch schadet nie.
        </p>
        <button class="knopf" onclick={nochmalSenden} disabled={stand === 'sendet'}>
          Noch einmal senden
        </button>
      </div>
    {/if}
  {/if}
  {#if teilbar}
    <button class="knopf weiter haupt" onclick={weitergeben}>Text weitergeben</button>
  {/if}
  <div class="reihe">
    <button class="knopf" onclick={kopiere}>
      {kopiert ? '✓ Kopiert' : 'Kopieren'}
    </button>
    <button class="knopf haupt" onclick={neuerText}>Neuer Text</button>
  </div>
{:else}
  <!--
    Der Weg nach draußen steht über dem Textfeld und nicht darunter: Er ist
    das, wofür diktiert wurde. „Fertig" schickt die Berichtigungen an „hören"
    zurück und gehört zum Lernen, nicht zum Benutzen - deshalb darunter, in
    der Zeile mit „Weitersprechen".
  -->
  <!--
    Teilen steht vor Kopieren, wo es beides gibt: Es ist ein Schritt statt
    dreier - antippen, App wählen, fertig. Kopieren bleibt daneben, denn nicht
    jedes Ziel steht im Teilen-Blatt, und auf dem Rechner gibt es gar keines.
  -->
  {#if teilbar}
    <button class="knopf weiter haupt" onclick={weitergeben}>Text weitergeben</button>
  {/if}
  <button class="knopf weiter" class:haupt={!teilbar} onclick={kopiere}>
    {kopiert ? '✓ In der Zwischenablage' : 'Text kopieren'}
  </button>
  <textarea class="ganz" readonly rows="3" value={ganzerText}></textarea>
  <div class="reihe">
    <button class="knopf" onclick={() => gehZu('/')}>Weitersprechen</button>
    <button class="knopf haupt" onclick={fertig} disabled={stand === 'sendet'}>
      {stand === 'sendet' ? 'Wird geschickt …' : 'Fertig'}
    </button>
  </div>
{/if}

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

<style>
  .kopfzeile {
    justify-content: space-between;
    margin-top: 0.5rem;
  }
  .satz {
    line-height: 1.4;
    margin: 0.5rem 0 1rem;
  }
  .mitte {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
  }
  /* Der zusammenhängende Text - zum Kopieren, nicht zum Bearbeiten:
     geändert wird er, indem man ihn neu spricht. */
  /*
    Breit, hoch und allein in seiner Zeile: Dieser Knopf wird mit dem Daumen
    getroffen, oft unterwegs, von jemandem, der schlecht zielt. Ein Knopf in
    einer Reihe mit anderen wäre halb so groß.
  */
  .weiter {
    width: 100%;
    padding-block: 0.9rem;
    margin-bottom: 0.75rem;
    font-weight: 600;
  }
  .ganz {
    width: 100%;
    max-width: none;
    margin-bottom: 1rem;
    color: var(--gedaempft);
  }
</style>
