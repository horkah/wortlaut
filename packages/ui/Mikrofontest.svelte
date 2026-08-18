<script lang="ts">
  /**
   * Mikrofon wählen, Pegel sehen, sich selbst hören.
   *
   * Der Test benutzt dieselbe Kette wie die echte Aufnahme. Was hier gut
   * klingt und gut aussieht, kommt später genauso auf dem Server an — sonst
   * wäre der Test wertlos.
   *
   * Alles läuft nur, solange der Test offen ist: ein Mikrofon, das im
   * Hintergrund mithört, hat in einer App mit Sprachaufnahmen nichts zu
   * suchen.
   */
  import AudioPlayer from './AudioPlayer.svelte';
  import Pegelanzeige from './Pegelanzeige.svelte';
  import {
    Aufnahmekette,
    auswahlMoeglich,
    beiGeraeteAenderung,
    faktorFuerSpitze,
    mikrofone,
    zeichneAuf,
    MikrofonFehler,
    MINDEST_SPITZE_DBFS,
    STILL_DBFS,
    VERSTAERKUNG_SPANNE,
    type Mikrofon,
    type Pegel,
  } from './mikrofon';

  let {
    geraeteId,
    verstaerkung,
    autoPegel,
    ongeraet,
    onverstaerkung,
    onautoPegel,
  }: {
    geraeteId: string | null;
    verstaerkung: number;
    autoPegel: boolean;
    ongeraet: (id: string | null) => void;
    onverstaerkung: (faktor: number) => void;
    onautoPegel: (an: boolean) => void;
  } = $props();

  /** So lange wird beim Einmessen zugehört. */
  const EINMESS_SEKUNDEN = 5;

  let liste = $state<Mikrofon[]>([]);
  let kette = $state<Aufnahmekette | null>(null);
  let pegel = $state<Pegel>({ rms: STILL_DBFS, spitze: STILL_DBFS });
  let ersatzGeraet = $state(false);
  let fehler = $state('');
  let probeUrl = $state<string | null>(null);
  let nimmtAuf = $state(false);
  let misstEin = $state(0); // verbleibende Sekunden, 0 heißt: läuft nicht
  let einmessErgebnis = $state('');

  let beendeAufnahme: (() => Promise<Blob>) | null = null;
  let einmessUhr: ReturnType<typeof setInterval> | null = null;
  let spitzeGemessen = STILL_DBFS;

  async function ladeListe() {
    try {
      liste = await mikrofone();
    } catch {
      liste = []; // Ohne Liste bleibt die Vorgabe des Browsers — kein Grund zu klagen.
    }
  }

  ladeListe();
  $effect(() => beiGeraeteAenderung(ladeListe));

  // Aufräumen, wenn die Ansicht verlassen wird, während der Test noch läuft.
  $effect(() => () => halt());

  function loeseProbe() {
    if (probeUrl) URL.revokeObjectURL(probeUrl);
    probeUrl = null;
  }

  async function starte() {
    fehler = '';
    einmessErgebnis = '';
    loeseProbe();
    try {
      kette = await Aufnahmekette.oeffne({ geraeteId, verstaerkung, autoPegel });
      ersatzGeraet = kette.ersatzGeraet;
      // Erst mit erteilter Erlaubnis nennt der Browser die Gerätenamen.
      await ladeListe();
      messSchleife();
    } catch (ursache) {
      fehler = ursache instanceof MikrofonFehler ? ursache.message : String(ursache);
      kette = null;
    }
  }

  function messSchleife() {
    const laufende = kette;
    if (!laufende) return;
    const nachschauen = () => {
      if (kette !== laufende) return; // Test wurde beendet oder neu gestartet
      pegel = laufende.miss();
      if (misstEin > 0 && pegel.spitze > spitzeGemessen) spitzeGemessen = pegel.spitze;
      requestAnimationFrame(nachschauen);
    };
    requestAnimationFrame(nachschauen);
  }

  function halt() {
    if (einmessUhr) clearInterval(einmessUhr);
    einmessUhr = null;
    misstEin = 0;
    // Eine noch laufende Probeaufnahme erst beenden, dann das Mikrofon
    // schließen — ein `MediaRecorder` auf einer toten Quelle bleibt sonst
    // offen und die Aufnahmeanzeige des Browsers steht weiter.
    const laufende = beendeAufnahme;
    beendeAufnahme = null;
    nimmtAuf = false;
    void laufende?.();
    kette?.schliesse();
    kette = null;
    pegel = { rms: STILL_DBFS, spitze: STILL_DBFS };
  }

  /** Gerätewechsel bei laufendem Test: kurz schließen, neu öffnen. */
  async function waehle(id: string) {
    ongeraet(id || null);
    if (kette) {
      halt();
      await starte();
    }
  }

  function schiebe(faktor: number) {
    onverstaerkung(faktor);
    kette?.setzeVerstaerkung(faktor); // wirkt sofort, ohne Neustart
  }

  /** Von Hand am Regler: die Meldung der letzten Einmessung gilt dann nicht mehr. */
  function schiebeVonHand(faktor: number) {
    einmessErgebnis = '';
    schiebe(faktor);
  }

  async function schalteAutoPegel(an: boolean) {
    onautoPegel(an);
    // Die Pegelregelung sitzt in der Aufnahme des Browsers, nicht in der
    // Kette dahinter — sie lässt sich nur beim Öffnen setzen.
    if (kette) {
      halt();
      await starte();
    }
  }

  function messeEin() {
    if (!kette) return;
    einmessErgebnis = '';
    spitzeGemessen = STILL_DBFS;
    misstEin = EINMESS_SEKUNDEN;
    einmessUhr = setInterval(() => {
      misstEin -= 1;
      if (misstEin > 0) return;
      if (einmessUhr) clearInterval(einmessUhr);
      einmessUhr = null;
      werteEinmessungAus();
    }, 1000);
  }

  function werteEinmessungAus() {
    if (!kette) return;
    if (spitzeGemessen < MINDEST_SPITZE_DBFS) {
      einmessErgebnis = 'Nichts gehört. Bitte während der fünf Sekunden laut sprechen.';
      return;
    }
    const faktor = faktorFuerSpitze(spitzeGemessen, kette.verstaerkung);
    schiebe(faktor);
    einmessErgebnis =
      faktor >= VERSTAERKUNG_SPANNE.max
        ? `Verstärkung auf das Maximum von ${faktor.toFixed(1)}× gesetzt — dieses Mikrofon ist ` +
          'auch damit noch leise. Näher heran oder ein anderes Mikrofon hilft mehr.'
        : `Verstärkung auf ${faktor.toFixed(1)}× gesetzt.`;
  }

  async function probeAufnahme() {
    if (!kette) return;
    if (nimmtAuf && beendeAufnahme) {
      const aufnahme = await beendeAufnahme();
      beendeAufnahme = null;
      nimmtAuf = false;
      loeseProbe();
      probeUrl = URL.createObjectURL(aufnahme);
      return;
    }
    loeseProbe();
    beendeAufnahme = zeichneAuf(kette);
    nimmtAuf = true;
  }
</script>

{#if auswahlMoeglich() && liste.length > 1}
  <label>
    <span>Mikrofon</span>
    <select value={geraeteId ?? ''} onchange={(ereignis) => waehle(ereignis.currentTarget.value)}>
      <option value="">Vorgabe des Browsers</option>
      {#each liste as mikrofon (mikrofon.id)}
        <option value={mikrofon.id}>{mikrofon.name}</option>
      {/each}
    </select>
  </label>
  {#if liste.some((m) => m.name.startsWith('Mikrofon '))}
    <p class="gedaempft">
      Die Namen der Geräte nennt der Browser erst, wenn der Test einmal gelaufen ist.
    </p>
  {/if}
{/if}

<div class="reihe">
  <button class="knopf" class:haupt={!kette} onclick={() => (kette ? halt() : starte())}>
    {kette ? '■ Test beenden' : '▶ Mikrofon testen'}
  </button>
  {#if kette}
    <button class="knopf" onclick={probeAufnahme} disabled={misstEin > 0}>
      {nimmtAuf ? '■ Aufnahme beenden' : '● Probe aufnehmen'}
    </button>
    <button class="knopf" onclick={messeEin} disabled={nimmtAuf || misstEin > 0}>
      {misstEin > 0 ? `Sprechen … ${misstEin}` : 'Automatisch einmessen'}
    </button>
  {/if}
</div>

{#if kette}
  <div class="karte">
    <Pegelanzeige {pegel} beschriftung="Eingangspegel" />
  </div>
  {#if ersatzGeraet}
    <p class="gedaempft">
      Das zuletzt gewählte Mikrofon ist nicht da. Es läuft die Vorgabe des Browsers.
    </p>
  {/if}
  {#if misstEin > 0}
    <p class="gedaempft">
      Bitte jetzt so sprechen, wie später aufgenommen wird — gleicher Abstand, gleiche Lautstärke.
    </p>
  {/if}
{:else}
  <p class="gedaempft">
    Der Test öffnet das Mikrofon und zeigt den Pegel. Solange er nicht läuft, hört die App nicht mit.
  </p>
{/if}

{#if probeUrl}
  <AudioPlayer quelle={probeUrl} beschriftung="Probe" />
{/if}

<label>
  <span>Verstärkung — {verstaerkung.toFixed(1)}×</span>
  <input
    type="range"
    class="schieber"
    min={VERSTAERKUNG_SPANNE.min}
    max={VERSTAERKUNG_SPANNE.max}
    step={VERSTAERKUNG_SPANNE.schritt}
    value={verstaerkung}
    oninput={(ereignis) => schiebeVonHand(Number(ereignis.currentTarget.value))}
  />
</label>
<p class="gedaempft">
  Wird vor der Aufzeichnung angewandt und ist in der gespeicherten Aufnahme enthalten. Verstärkt
  wird alles, auch das Rauschen des Raumes — so viel wie nötig, nicht so viel wie möglich.
</p>

<label class="kasten">
  <input
    type="checkbox"
    checked={autoPegel}
    onchange={(ereignis) => schalteAutoPegel(ereignis.currentTarget.checked)}
  />
  <span class="dazu">Pegel automatisch nachregeln</span>
</label>
<p class="gedaempft">
  Die Pegelregelung des Browsers gleicht aus, wenn mal lauter und mal leiser gesprochen wird. Sie
  hebt einen durchweg zu leisen Eingang aber nicht an — dafür ist die Verstärkung da.
</p>

{#if einmessErgebnis}
  <p class="gedaempft ergebnis">{einmessErgebnis}</p>
{/if}
{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

<style>
  /* Die globale Regel für `input` gibt Rahmen und Polster — beides steht
     einem Schieberegler und einem Kästchen schlecht. */
  .schieber {
    border: 0;
    padding: 0;
    max-width: 20rem;
  }
  .kasten {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }
  .kasten input {
    width: 1.1rem;
    height: 1.1rem;
    padding: 0;
    flex: none;
  }
  /* Die globale Regel blendet `label > span` als kleine Überschrift aus; im
     Kästchen ist der Text aber die Beschriftung selbst. */
  .kasten .dazu {
    font-size: 1rem;
    color: inherit;
    margin: 0;
  }
  .ergebnis {
    color: var(--akzent);
  }
</style>
