<script lang="ts">
  /**
   * Textquelle wählen: entweder ein Thema, aus dem ein LLM Text erzeugt, oder
   * ein hochgeladener Text. Beides wird zu Sprecheinheiten geschnitten und
   * hinten an die Warteschlange gehängt.
   */
  import {
    erkennungMoeglich,
    quelleAusDatei,
    quelleAusLLM,
    quelleAusText,
    quelleLoeschen,
    quelleText,
    quelleUmstellen,
    quellen,
    textErkennen,
    type Quelle,
  } from '../lib/api';
  import { gehZu } from '../lib/zustand.svelte';

  let liste = $state<Quelle[]>([]);
  let fehler = $state('');
  let laeuft = $state(false);

  let thema = $state('');
  let altersspanne = $state('Erwachsene');
  let umfang = $state(300);
  let datei = $state<FileList | null>(null);

  /**
   * Der Prüfschritt: Was gelesen oder erkannt wurde, steht hier, bis jemand
   * es übernimmt.
   *
   * `null` heißt: kein Entwurf offen, die Ansicht sieht aus wie immer. Sobald
   * etwas darin steht, tritt es an die Stelle des Formulars - es ist der
   * nächste Schritt und keine zweite Möglichkeit daneben.
   */
  let entwurf = $state<{
    text: string;
    titel: string;
    herkunft: string;
    /**
     * Die Vorlage selbst, solange der Entwurf offen ist.
     *
     * **Zum Vergleichen** - wer erkannten Text bessern soll, muss das Original
     * daneben sehen; hin- und herzuwechseln ist genau das, was der Zielperson
     * schwerfällt (Grundentscheidung 7).
     *
     * **Und auf dem iPhone noch für etwas anderes.** Apples eigene
     * Texterkennung („Live Text") ist dieser hier überlegen: Sie liest auch
     * schräg fotografierte Folien, bei denen die Zeilen zusammenlaufen. An sie
     * kommt eine Webseite nicht heran - `TextDetector` ist ausdrücklich nicht
     * standardisiert, und Safari liefert ihn nicht. Der Mensch kommt aber
     * heran: Safari bietet Live Text auf **jedem** angezeigten Bild an. Wer
     * hier lange auf das Bild drückt, kann den Text auswählen, kopieren und
     * ins Feld darunter einfügen - ohne die App zu verlassen.
     */
    bildUrl: string | null;
  } | null>(null);
  let kannErkennen = $state(false);

  // Was das Auswahlfeld annimmt. Die Bildformate kommen vom Server, denn er
  // entscheidet, was er lesen kann - und ohne Zeichenerkennung bietet die
  // Oberfläche sie gar nicht erst an.
  const TEXTFORMATE = '.txt,.md,.pdf,.epub,.docx';
  let bildformate = $state('');
  const annimmt = $derived(TEXTFORMATE + bildformate);

  async function lade() {
    liste = await quellen();
  }

  // Einmal beim Aufbau: Ob der Server Bilder lesen kann, ändert sich nicht,
  // solange die Seite offen ist.
  $effect(() => {
    erkennungMoeglich()
      .then((antwort) => {
        kannErkennen = antwort.moeglich;
        bildformate = antwort.moeglich ? ',' + antwort.formate.join(',') : '';
      })
      .catch(() => {
        // Eine Auskunft, die nicht kommt, ist keine Fehlermeldung wert: Dann
        // bleibt es beim Hochladen von Text, so wie vorher.
      });
  });

  async function fuehreAus(arbeit: () => Promise<unknown>) {
    fehler = '';
    laeuft = true;
    try {
      await arbeit();
      await lade();
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      laeuft = false;
    }
  }

  const ausLLM = (ereignis: SubmitEvent) => {
    ereignis.preventDefault();
    fuehreAus(() => quelleAusLLM({ thema, altersspanne, umfang }));
  };

  /**
   * Welche Dateien vor dem Anlegen zur Ansicht kommen.
   *
   * Bilder immer - sie sind geraten. PDFs auch, und das ist eine Entscheidung
   * über den bisherigen Stand hinaus: Ein PDF trägt Kopfzeilen, Fußnoten und
   * Seitenzahlen, die niemand vorlesen will, und ob überhaupt eine Textebene
   * darin steckt, weiß man vorher nicht. Wer es sieht, streicht es weg.
   *
   * `txt`, `md`, `epub` und `docx` gehen weiterhin unmittelbar: Dort steht der
   * Text schon so da, wie ihn jemand geschrieben hat, und ein Prüfschritt wäre
   * ein Klick ohne Anlass.
   */
  const ZUR_ANSICHT = /\.(pdf|png|jpe?g|webp|gif|bmp|tiff?|heic|heif)$/i;

  const ausDatei = (ereignis: SubmitEvent) => {
    ereignis.preventDefault();
    const gewaehlt = datei?.[0];
    if (!gewaehlt) return;
    if (ZUR_ANSICHT.test(gewaehlt.name)) {
      fuehreAus(async () => {
        const gelesen = await textErkennen(gewaehlt);
        oeffneEntwurf(gelesen.text, gewaehlt.name, gelesen.herkunft, gewaehlt);
      });
    } else {
      fuehreAus(() => quelleAusDatei(gewaehlt));
    }
  };

  /**
   * Was aus der Zwischenablage kommt - ein Bild oder ein Schnipsel Text.
   *
   * Über das `paste`-Ereignis und nicht über `navigator.clipboard.read()`:
   * Letzteres fragt in Safari jedes Mal um Erlaubnis und gibt in Firefox
   * überhaupt keine Bilder heraus. Einfügen dagegen kann jeder Browser, es ist
   * eine Handlung des Menschen und braucht deshalb keine Rückfrage.
   */
  async function ausZwischenablage(ereignis: ClipboardEvent) {
    const daten = ereignis.clipboardData;
    if (!daten) return;

    const bild = Array.from(daten.items).find((teil) => teil.type.startsWith('image/'));
    if (bild) {
      const roh = bild.getAsFile();
      if (!roh) return;
      ereignis.preventDefault();
      // **Immer mit Namen weiterreichen.** Ein Bildschirmfoto kommt als
      // `image.png` an, ein Foto aus der Mediathek des iPhones je nach Browser
      // ohne Endung oder ganz ohne Namen - und ein Teil ohne Dateinamen ist für
      // den Server kein Anhang, sondern ein Formularfeld. Die werden bei einem
      // Megabyte abgeschnitten, und ein Foto ist größer. Genau daran scheiterte
      // es, während Bildschirmfotos durchgingen.
      const datei = roh.name
        ? roh
        : new File([roh], `einfügung.${(roh.type.split('/')[1] || 'png').split('+')[0]}`, {
            type: roh.type,
          });
      fuehreAus(async () => {
        const gelesen = await textErkennen(datei);
        oeffneEntwurf(gelesen.text, 'Aus der Zwischenablage', gelesen.herkunft, datei);
      });
      return;
    }

    const text = daten.getData('text/plain');
    if (text.trim()) {
      ereignis.preventDefault();
      oeffneEntwurf(text, 'Aus der Zwischenablage', 'eingefügt', null);
    }
  }

  /**
   * Einen Entwurf öffnen und das Bild dazu bereitstellen.
   *
   * Die Adresse zeigt auf den Arbeitsspeicher dieses Browsers; sie wird beim
   * Schließen wieder freigegeben, sonst hielte jede Vorlage ihr Bild bis zum
   * Neuladen fest.
   */
  function oeffneEntwurf(text: string, titel: string, herkunft: string, bild: File | null) {
    schliesseEntwurf();
    entwurf = {
      text,
      titel,
      herkunft,
      bildUrl: bild ? URL.createObjectURL(bild) : null,
    };
  }

  function schliesseEntwurf() {
    if (entwurf?.bildUrl) URL.revokeObjectURL(entwurf.bildUrl);
    entwurf = null;
  }

  const uebernimm = (ereignis: SubmitEvent) => {
    ereignis.preventDefault();
    const offen = entwurf;
    if (!offen?.text.trim()) return;
    fuehreAus(async () => {
      await quelleAusText({ text: offen.text, titel: offen.titel, herkunft: offen.herkunft });
      schliesseEntwurf();
      datei = null;
    });
  };

  const stelleUm = (quelle: Quelle) =>
    fuehreAus(() => quelleUmstellen(quelle.id, !quelle.aktiv));

  function loesche(quelle: Quelle) {
    // Gewarnt wird vorher, nicht hinterher: Die Einheiten sind fort, und bei
    // einer erzeugten Quelle kostet ein neuer Anlauf wieder Rechenzeit.
    const sicher = confirm(
      `„${quelle.titel}“ mit ${quelle.einheiten} Einheiten löschen?\n\n` +
        'Das lässt sich nicht rückgängig machen. Soll die Quelle nur aus der ' +
        'Warteschlange verschwinden, stelle sie stattdessen ab.',
    );
    if (sicher) fuehreAus(() => quelleLoeschen(quelle.id));
  }

  async function zeigeText(quelle: Quelle) {
    // Das Fenster muss vor dem `await` aufgehen: Danach gilt es dem Browser
    // nicht mehr als Folge des Klicks und wird als Popup abgefangen.
    const tab = window.open('', '_blank');
    try {
      const text = await quelleText(quelle.id);
      const adresse = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
      if (tab) tab.location.href = adresse;
      else window.open(adresse, '_blank'); // doch abgefangen: zweiter Versuch
      // Erst freigeben, wenn der Tab sie geladen hat.
      setTimeout(() => URL.revokeObjectURL(adresse), 60_000);
    } catch (ursache) {
      tab?.close();
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  lade();
</script>

<h2>Thema (Text vom Sprachmodell)</h2>
<form onsubmit={ausLLM}>
  <label>
    <span>Thema oder Stichwort</span>
    <input bind:value={thema} required placeholder="Zum Beispiel: Einkaufen im Wochenmarkt" />
  </label>
  <label>
    <span>Altersspanne der Zielgruppe</span>
    <input bind:value={altersspanne} placeholder="Erwachsene, 8-12, …" />
  </label>
  <label>
    <span>Umfang (ungefähre Wortzahl)</span>
    <input type="number" bind:value={umfang} min="50" max="3000" step="50" />
  </label>
  <button class="knopf haupt" type="submit" disabled={laeuft}>Text erzeugen</button>
</form>

<h2>Eigener Text</h2>

{#if entwurf}
  <!--
    Der Prüfschritt. Er tritt an die Stelle des Formulars und steht nicht
    daneben: Er ist der nächste Schritt und keine zweite Möglichkeit.
  -->
  <p class="gedaempft">
    {#if entwurf.herkunft === 'erkannt'}
      <strong>Erkannt, nicht gelesen.</strong> Was hier steht, hat eine Maschine aus dem Bild
      geraten - sie verwechselt <code>rn</code> mit <code>m</code> und erfindet an Knicken
      Zeichen. Bitte durchsehen und bessern: Was hier stehen bleibt, wird nachher vorgesprochen
      und nachgesprochen.
    {:else}
      Bitte durchsehen. Kopfzeilen, Seitenzahlen und Fußnoten will niemand vorlesen - was hier
      wegfällt, wird gar nicht erst zur Vorlage.
    {/if}
  </p>
  {#if entwurf.bildUrl}
    <!--
      Die Vorlage selbst, zum Vergleichen - und auf dem iPhone zu mehr: Safari
      bietet Apples eigene Texterkennung („Live Text") auf jedem angezeigten
      Bild an. Sie liest auch schräg fotografierte Folien, an denen diese hier
      scheitert. Ein langer Druck aufs Bild, auswählen, kopieren, unten
      einfügen - ohne die App zu verlassen.
    -->
    <figure class="vorlage">
      <img src={entwurf.bildUrl} alt="Die hochgeladene Vorlage" />
      <figcaption class="gedaempft">
        Zum Vergleichen. Stimmt wenig davon - schräg fotografiert, Zeilen laufen zusammen? Auf
        dem iPhone lange auf das Bild drücken: Dessen eigene Texterkennung ist besser und lässt
        sich auswählen, kopieren und unten einfügen.
      </figcaption>
    </figure>
  {/if}

  <form onsubmit={uebernimm}>
    <label>
      <span>Titel</span>
      <input bind:value={entwurf.titel} maxlength="200" />
    </label>
    <label>
      <span>Text - eine Leerzeile trennt Absätze</span>
      <textarea class="entwurf" bind:value={entwurf.text} rows="14"></textarea>
    </label>
    <div class="reihe">
      <button class="knopf haupt" type="submit" disabled={laeuft || !entwurf.text.trim()}>
        {laeuft ? 'Wird übernommen …' : 'Übernehmen'}
      </button>
      <button class="knopf" type="button" onclick={schliesseEntwurf}>Verwerfen</button>
      <span class="gedaempft">{entwurf.text.trim().length} Zeichen</span>
    </div>
  </form>
{:else}
  <p class="gedaempft">
    txt, md, pdf, epub oder docx.
    {#if kannErkennen}
      Auch ein <strong>Foto</strong> einer Seite oder ein eingescanntes PDF - der Text wird dann
      erkannt und liegt euch vorher zum Bessern vor.
    {/if}
  </p>
  <!--
    Der Satz steht hier und nicht in der Datenschutzerklärung, weil hier
    gezögert wird: Wer einen Brief oder einen Befund abfotografiert hat,
    entscheidet in diesem Augenblick, ob er ihn hochlädt. Beide Zusagen sind
    nachgemessen - im Erkennungsweg steht kein einziger Netzaufruf, und nach
    der Verarbeitung bleibt nichts im Zwischenspeicher liegen (siehe
    `docs/datenschutz.md`).
  -->
  <p class="gedaempft zusage">
    Die Datei bleibt auf diesem Server und wird gleich nach dem Lesen wieder gelöscht.
    Gespeichert wird allein der Text, den ihr danach übernehmt.
  </p>
  <form onsubmit={ausDatei}>
    <input type="file" accept={annimmt} bind:files={datei} />
    <button class="knopf" type="submit" disabled={laeuft}>
      {laeuft ? 'Wird gelesen …' : 'Hochladen'}
    </button>
  </form>

  <!--
    Einfügen statt Hochladen. Ein `textarea`, weil ein Feld, in das man tippen
    kann, auch das Feld ist, in das jeder Browser einfügt - ohne Erlaubnis,
    ohne Knopf, mit derselben Handbewegung wie überall sonst.
  -->
  <label class="einfuegen">
    <span>
      … oder hier einfügen{kannErkennen ? ' - Text oder ein Bild aus der Zwischenablage' : ''}
    </span>
    <textarea
      rows="2"
      placeholder={kannErkennen
        ? 'Hier hineintippen und einfügen (⌘V / Strg+V)'
        : 'Hier hineintippen und Text einfügen (⌘V / Strg+V)'}
      onpaste={ausZwischenablage}
    ></textarea>
  </label>
{/if}

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

<h2>Vorhandene Quellen</h2>
{#each liste as quelle (quelle.id)}
  <div class="karte zeile" class:still={!quelle.aktiv}>
    <button
      class="feld schalter"
      role="switch"
      aria-checked={quelle.aktiv}
      aria-label={quelle.aktiv ? 'Quelle abstellen' : 'Quelle wieder aufnehmen'}
      title={quelle.aktiv
        ? 'Aktiv - abstellen nimmt die Einheiten aus der Warteschlange'
        : 'Abgestellt - wieder aufnehmen stellt die Einheiten zurück'}
      disabled={laeuft}
      onclick={() => stelleUm(quelle)}
    >
      <!-- Ein- und Ausschalter: das übliche Zeichen, gefüllt wenn an. -->
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor"
        stroke-width="2" stroke-linecap="round" aria-hidden="true">
        <path d="M12 3.5v8" />
        <path d="M7 6.6a7.5 7.5 0 1 0 10 0" />
      </svg>
    </button>

    <div class="mitte">
      <button class="titel" title="Text in einem neuen Tab ansehen" onclick={() => zeigeText(quelle)}>
        {quelle.titel}
      </button>
      <div class="gedaempft">
        {quelle.art} · {quelle.einheiten} Einheiten · {quelle.erstellt}
        {#if !quelle.aktiv}· abgestellt{/if}
      </div>
    </div>

    <button
      class="feld loeschen"
      aria-label="Quelle löschen"
      title="Quelle löschen"
      disabled={laeuft}
      onclick={() => loesche(quelle)}
    >
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor"
        stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M4 7h16M10 4h4M6 7l1 13h10l1-13M10 11v6M14 11v6" />
      </svg>
    </button>
  </div>
{:else}
  <p class="gedaempft">Noch keine Quelle.</p>
{/each}

{#if liste.length > 0}
  <button class="knopf haupt" onclick={() => gehZu('/aufnahme')}>Zur Aufnahme</button>
{/if}

<style>
  /* Eine Zusage, keine Fußnote: dieselbe Größe wie der Hinweis darüber, aber
     abgesetzt, damit sie nicht mit den Formatangaben verschwimmt. */
  .zusage {
    border-left: 3px solid var(--akzent);
    padding-left: 0.6rem;
    margin-bottom: 1rem;
  }
  /* Hoch genug, um Schrift darauf zu erkennen, und begrenzt, damit das
     Prüffeld nicht aus dem Bild rutscht. */
  .vorlage {
    margin: 0 0 1rem;
  }
  .vorlage img {
    display: block;
    width: 100%;
    max-height: 45vh;
    object-fit: contain;
    border-radius: 0.4rem;
    background: var(--gedaempft);
  }
  .vorlage figcaption {
    margin-top: 0.4rem;
  }
  /* Der Entwurf ist zum Lesen da, nicht zum Überfliegen: volle Breite und
     Zeilen, die nicht kleben. */
  .entwurf {
    width: 100%;
    max-width: none;
    line-height: 1.45;
  }
  /* Die Einfügefläche bleibt klein - sie ist ein Ziel, kein Schreibfeld. */
  .einfuegen textarea {
    width: 100%;
    max-width: none;
  }
  /* Schalter - Titel - Löschen. Die Mitte nimmt den Platz, die beiden Felder
     behalten ihre Größe, auch wenn der Titel lang ist. */
  .zeile {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .mitte {
    flex: 1;
    min-width: 0; /* sonst sprengt ein langer Titel die Zeile */
  }

  /* Beide Felder gleich groß und quadratisch: 2,75rem sind bei üblicher
     Grundschrift 44 px - das Maß, das ein Finger sicher trifft. */
  .feld {
    flex: none;
    display: grid;
    place-items: center;
    width: 2.75rem;
    height: 2.75rem;
    padding: 0;
    border: 1px solid var(--rand);
    border-radius: 0.5rem;
    background: none;
    color: var(--gedaempft);
    cursor: pointer;
  }

  .feld:disabled {
    opacity: 0.5;
    cursor: default;
  }

  /* Eingeschaltet ist der Normalfall und darf ruhig zu sehen sein. */
  .schalter[aria-checked='true'] {
    border-color: var(--akzent);
    background: var(--akzent-hell);
    color: var(--akzent);
  }

  /* Dieselbe Farbe wie `.fehler` in der gemeinsamen app.css. */
  .loeschen:hover:not(:disabled) {
    border-color: var(--fehler);
    color: var(--fehler);
  }

  /* Der Titel ist der Weg zum Text - als Knopf, damit der Token mitgeht,
     aber wie ein Verweis anzusehen. */
  .titel {
    display: block;
    max-width: 100%;
    padding: 0;
    border: 0;
    background: none;
    font: inherit;
    font-weight: 600;
    text-align: left;
    color: var(--akzent);
    text-decoration: underline;
    text-underline-offset: 0.15em;
    cursor: pointer;
    overflow-wrap: anywhere;
  }

  /* Abgestellt: sichtbar, aber erkennbar außer Dienst. */
  .still {
    opacity: 0.6;
  }
</style>
