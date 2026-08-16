<script lang="ts">
  /**
   * Ein Knopf, eine Aufnahme.
   *
   * `MediaRecorder` liefert je nach Browser Opus in WebM oder OGG, Safari
   * liefert MP4. Was davon kommt, ist gleichgültig: umgewandelt wird
   * serverseitig an genau einer Stelle (`wortlaut.audio`).
   */
  let {
    onaufnahme,
    deaktiviert = false,
  }: {
    /** Wird mit der fertigen Aufnahme aufgerufen. */
    onaufnahme: (aufnahme: Blob) => void;
    deaktiviert?: boolean;
  } = $props();

  let laeuft = $state(false);
  let fehler = $state('');
  let sekunden = $state(0);

  let rekorder: MediaRecorder | null = null;
  let uhr: ReturnType<typeof setInterval> | null = null;

  function bevorzugterTyp(): string {
    const kandidaten = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'];
    return kandidaten.find((typ) => MediaRecorder.isTypeSupported(typ)) ?? '';
  }

  async function starte() {
    fehler = '';
    try {
      const strom = await navigator.mediaDevices.getUserMedia({
        // Die Umwandlung macht ffmpeg; hier geht es nur um saubere Rohdaten.
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: false },
      });
      const stuecke: Blob[] = [];
      const typ = bevorzugterTyp();
      rekorder = new MediaRecorder(strom, typ ? { mimeType: typ } : undefined);

      rekorder.ondataavailable = (ereignis) => {
        if (ereignis.data.size > 0) stuecke.push(ereignis.data);
      };
      rekorder.onstop = () => {
        strom.getTracks().forEach((t) => t.stop()); // Mikrofon wieder freigeben
        onaufnahme(new Blob(stuecke, { type: typ || 'audio/webm' }));
      };

      rekorder.start();
      laeuft = true;
      sekunden = 0;
      uhr = setInterval(() => (sekunden += 1), 1000);
    } catch (ursache) {
      fehler =
        ursache instanceof DOMException && ursache.name === 'NotAllowedError'
          ? 'Kein Zugriff auf das Mikrofon. Bitte im Browser erlauben.'
          : 'Aufnahme nicht möglich. Braucht HTTPS oder localhost.';
    }
  }

  function stoppe() {
    rekorder?.stop();
    rekorder = null;
    laeuft = false;
    if (uhr) clearInterval(uhr);
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
    background: #b3261e;
    border-color: #b3261e;
    color: #fff;
  }
  .fehler {
    color: #b3261e;
    margin: 0;
  }
</style>
