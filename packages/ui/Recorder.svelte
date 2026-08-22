<script lang="ts">
  /**
   * Ein Knopf, eine Aufnahme.
   *
   * Gerätewahl, Verstärkung und Format stecken in `mikrofon.ts` — dieselbe
   * Kette, die der Mikrofontest in den Einstellungen vorführt. Hier bleibt
   * nur, was den Knopf betrifft.
   */
  import { Aufnahmekette, MikrofonFehler, zeichneAuf } from './mikrofon';

  let {
    onaufnahme,
    deaktiviert = false,
    geraeteId = null,
    verstaerkung = 1,
    autoPegel = true,
  }: {
    /** Wird mit der fertigen Aufnahme aufgerufen. */
    onaufnahme: (aufnahme: Blob) => void;
    deaktiviert?: boolean;
    /** Gewähltes Mikrofon; `null` heißt: was der Browser vorschlägt. */
    geraeteId?: string | null;
    verstaerkung?: number;
    autoPegel?: boolean;
  } = $props();

  let laeuft = $state(false);
  let fehler = $state('');
  let sekunden = $state(0);

  let kette: Aufnahmekette | null = null;
  let beende: (() => Promise<Blob>) | null = null;
  let uhr: ReturnType<typeof setInterval> | null = null;

  async function starte() {
    fehler = '';
    try {
      kette = await Aufnahmekette.oeffne({ geraeteId, verstaerkung, autoPegel });
      if (kette.ersatzGeraet) {
        fehler = 'Das gewählte Mikrofon ist nicht da — es läuft die Vorgabe des Browsers.';
      }
      beende = zeichneAuf(kette);
      laeuft = true;
      sekunden = 0;
      uhr = setInterval(() => (sekunden += 1), 1000);
    } catch (ursache) {
      fehler = ursache instanceof MikrofonFehler ? ursache.message : String(ursache);
      kette?.schliesse();
      kette = null;
    }
  }

  async function stoppe() {
    laeuft = false;
    if (uhr) clearInterval(uhr);
    const fertig = beende;
    beende = null;
    // Erst die Aufnahme einsammeln, dann das Mikrofon freigeben: umgekehrt
    // fehlt dem Rekorder die Quelle, bevor er sein letztes Stück liefert.
    const aufnahme = await fertig?.();
    kette?.schliesse();
    kette = null;
    if (aufnahme) onaufnahme(aufnahme);
  }
</script>

<div class="aufnehmer">
  <button
    class="knopf gross"
    class:laeuft
    disabled={deaktiviert}
    onclick={() => (laeuft ? stoppe() : starte())}
  >
    {laeuft ? `■ Fertig (${sekunden}s)` : '● Aufnehmen'}
  </button>
  {#if fehler}
    <p class="fehler">{fehler}</p>
  {/if}
</div>

<style>
  .aufnehmer {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
  }
  .gross {
    font-size: 1.5rem;
    padding: 1.25rem 2.5rem;
    min-width: 16rem;
  }
  .laeuft {
    background: var(--fehler);
    border-color: var(--fehler);
    color: #fff;
  }
  .fehler {
    color: var(--fehler);
    margin: 0;
  }
</style>
