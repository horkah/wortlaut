<script lang="ts">
  /**
   * Läufe beauftragen und ihnen zusehen.
   *
   * **Warum wenige Wahlen und keine Formularseite.** Zwei Methoden, zwei
   * Datensätze, dazu der Abschluss: was am Ende mit den Gewichten geschieht.
   * Alles andere steht fest - das Grundmodell, die Aufteilung, die Zahlen des
   * Rezepts. Eine Seite voller Felder täuschte eine Freiheit vor, die es nicht
   * gibt, und jede Einstellmöglichkeit wäre eine, deren Wirkung später niemand
   * mehr zuzuordnen weiß.
   *
   * Jede der drei Wahlen ist deshalb eine Achse der Vergleichstafel und keine
   * Stellschraube: Sie steht im Auftrag, sie steht am Modellstand, und sie
   * lässt sich hinterher gegen die anderen messen. Der Abschluss hat mit
   * `bester` genau die Vorgabe, nach der jeder Stand von vorher entstand -
   * wer nichts wählt, rechnet, was dieses Projekt immer gerechnet hat.
   *
   * **Warum die Liste im Takt nachfragt.** Ein Training dauert Stunden. Der
   * Balken soll währenddessen wachsen, ohne dass jemand neu lädt - und er soll
   * es auch dann, wenn der Auftrag in einem anderen Reiter angestoßen wurde.
   * Im Ruhezustand bleibt ein langsamer Takt: Läuft nichts, ist nichts zu
   * sehen.
   */
  import { onMount } from 'svelte';
  import {
    beauftrage as beauftrageLauf,
    brichAb,
    laeufe as ladeLaeufe,
    loescheLauf,
    type Lauf,
    type Laufliste,
  } from '../lib/api';
  import { setzeTrainerschluessel, trainerschluessel } from '../lib/trainerschluessel';
  import { LAUF_ROUTE, gehZu } from '../lib/zustand.svelte';

  // Während gerechnet wird, soll der Balken mitwachsen - aber ein Takt von
  // einer Sekunde brächte nichts: Ein Trainingsschritt dauert länger.
  const TAKT_LAEUFT = 3000;
  const TAKT_RUHT = 20000;

  let daten = $state<Laufliste | null>(null);
  let fehler = $state('');
  let bestellt = $state('');
  // Welcher Lauf gerade gelöscht wird - der Knopf sperrt sich so lange selbst.
  let loescht = $state('');

  let methode = $state('lora');
  let datensatz = $state('original');
  // Die Vorgabe ist das Verfahren von vorher - siehe Kopf dieser Datei.
  let abschluss = $state('bester');
  let augmentierung = $state('keine');
  // Der Trainerschlüssel. Er steht hier neben Methode und Datensatz, weil er
  // an derselben Stelle gebraucht wird - aber er gehört nicht zur Bestellung,
  // sondern zur Erlaubnis, sie aufzugeben (siehe `lib/trainerschluessel.ts`).
  let schluessel = $state(trainerschluessel());

  const laeufe = $derived(daten?.laeufe ?? []);
  const arbeitet = $derived(laeufe.some((lauf) => lauf.status === 'laeuft'));
  const wartend = $derived(laeufe.filter((lauf) => lauf.status === 'wartet').length);

  /**
   * Welche der vier Kombinationen schon gelaufen sind. Nicht, um sie zu
   * sperren - ein zweiter Lauf derselben Art ist ein gutes Recht, etwa nach
   * fünfzig neuen Aufnahmen -, sondern um zu zeigen, was noch fehlt: Die
   * Frage dieser App ist der Vergleich der vier, und der ist erst mit allen
   * vieren zu haben.
   */
  const gerechnet = $derived(
    new Set(
      laeufe
        .filter((lauf) => lauf.status === 'fertig')
        .map((lauf) => `${lauf.methode}/${lauf.daten}`),
    ),
  );

  /**
   * Dasselbe mit dem Abschluss dazu - für den Satz neben dem Knopf.
   *
   * Die Tafel darüber bleibt bei den vier Feldern: Sie beantwortet die erste
   * Frage dieser App (Methode gegen Datensatz), und ein Raster aus sechzehn
   * Feldern beantwortete gar keine mehr. Wer aber gerade denselben Lauf mit
   * einem anderen Abschluss bestellt, hat etwas Neues bestellt - und soll
   * nicht lesen, das sei schon gerechnet.
   */
  const gerechnetGenau = $derived(
    new Set(
      laeufe
        .filter((lauf) => lauf.status === 'fertig')
        .map(
          (lauf) =>
            `${lauf.methode}/${lauf.daten}/${lauf.abschluss || 'bester'}/` +
            `${lauf.augmentierung || 'keine'}`,
        ),
    ),
  );

  const STUFEN: Record<string, string> = {
    vorbereiten: 'wird vorbereitet',
    laden: 'Modell wird geladen',
    training: 'trainiert',
    abschluss: 'die Gewichte werden abgeschlossen',
    sichern: 'wird gesichert',
    umwandeln: 'wird umgewandelt',
    bewerten: 'wird an den Testaufnahmen gemessen',
  };

  const STATUS: Record<string, string> = {
    wartet: 'wartet auf den Trainer',
    laeuft: 'läuft',
    fertig: 'fertig',
    gescheitert: 'gescheitert',
    abgebrochen: 'zurückgenommen',
  };

  /**
   * Die Überschrift einer Laufkarte.
   *
   * Der Abschluss steht nur dabei, wenn er nicht der gewöhnliche ist: Ein Lauf
   * von früher soll heute heißen, wie er damals hieß, sonst sieht die Liste
   * nach einer Änderung aus, wo keine ist.
   */
  function bezeichnung(lauf: Lauf): string {
    const m = daten?.methoden.find((wahl) => wahl.schluessel === lauf.methode);
    const d = daten?.datensaetze.find((wahl) => wahl.schluessel === lauf.daten);
    const a = daten?.abschluesse.find((wahl) => wahl.schluessel === lauf.abschluss);
    const g = daten?.augmentierungen.find((wahl) => wahl.schluessel === lauf.augmentierung);
    const teile = [m?.name ?? lauf.methode, d?.name ?? lauf.daten];
    if (lauf.abschluss && lauf.abschluss !== 'bester') teile.push(a?.name ?? lauf.abschluss);
    if (lauf.augmentierung && lauf.augmentierung !== 'keine') {
      teile.push(g?.name ?? lauf.augmentierung);
    }
    return teile.join(' · ');
  }

  function zeit(roh: string): string {
    if (!roh) return '';
    const wann = new Date(roh);
    return Number.isNaN(wann.getTime()) ? roh : wann.toLocaleString('de-DE');
  }

  async function hole() {
    try {
      daten = await ladeLaeufe();
      fehler = '';
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  async function bestelle() {
    bestellt = 'laeuft';
    try {
      await beauftrageLauf(methode, datensatz, abschluss, augmentierung, schluessel);
      // Erst merken, wenn er gestimmt hat: Ein falsch getippter Schlüssel, der
      // den Neustart überlebt, ist einer, den man beim nächsten Mal nicht mehr
      // verdächtigt.
      setzeTrainerschluessel(schluessel);
      await hole();
      fehler = '';
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      bestellt = '';
    }
  }

  async function nimmZurueck(jobId: string) {
    try {
      await brichAb(jobId);
      await hole();
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  /**
   * Einen Lauf löschen - ersatzlos, und das steht vorher in der Abfrage.
   *
   * Die Abfrage nennt, was verschwindet, und nicht nur „wirklich?". Ein
   * fertiger Lauf hat ein Modell hervorgebracht, und das geht mit: Bliebe es
   * stehen, zeigte es auf ein Verzeichnis, das es nicht mehr gibt, und die
   * Frage, worauf es trainiert wurde, wäre nicht mehr zu beantworten. Wer das
   * nicht weiß, bevor er bestätigt, erfährt es hinterher.
   *
   * Ein freigegebener Stand bekommt einen eigenen Satz dazu: Mit ihm ändert
   * sich, womit in „schreiben" diktiert wird.
   */
  async function loesche(lauf: Lauf) {
    const zeilen = [`${bezeichnung(lauf)} vom ${zeit(lauf.erstellt)} löschen?`, ''];
    if (lauf.stand) {
      zeilen.push(`Das Modell „${lauf.stand.version}" wird mitgelöscht.`);
      if (lauf.stand.freigegeben) {
        zeilen.push(
          'Es ist gerade freigegeben - „schreiben" fällt danach auf das Grundmodell zurück, ' +
            'bis ein anderer Stand freigegeben wird.',
        );
      }
      zeilen.push('');
    }
    zeilen.push('Auftrag, Schnappschuss, Kurven und Protokoll verschwinden mit.');
    zeilen.push('Das lässt sich nicht rückgängig machen.');

    if (!confirm(zeilen.join('\n'))) return;

    loescht = lauf.job_id;
    try {
      await loescheLauf(lauf.job_id);
      await hole();
      fehler = '';
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      loescht = '';
    }
  }

  onMount(() => {
    let uhr: ReturnType<typeof setTimeout>;
    let beendet = false;

    // Ein sich selbst neu stellender Wecker statt eines festen Intervalls: So
    // hängt der Takt am Zustand, und zwei Abfragen können sich nicht
    // überholen, wenn der Server einmal länger braucht.
    async function takt() {
      await hole();
      if (beendet) return;
      uhr = setTimeout(takt, arbeitet || wartend ? TAKT_LAEUFT : TAKT_RUHT);
    }

    takt();
    return () => {
      beendet = true;
      clearTimeout(uhr);
    };
  });
</script>

<h2>Training</h2>
<p class="gedaempft">
  Aus den Aufnahmen von „hören" ein Modell für diese eine Stimme. Trainiert wird auf
  {daten?.basismodell ?? 'whisper-small'} - fest, denn nur so ist das Ergebnis mit der Grundlinie
  aus der Auswertung vergleichbar.
</p>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

<div class="karte bestellung">
  {#if daten && !daten.bereit}
    <p>{daten.hinweis}</p>
  {:else if daten}
    <div class="wahlen">
      <fieldset>
        <legend>Wie trainiert wird</legend>
        {#each daten.methoden as wahl (wahl.schluessel)}
          <label class="option">
            <input type="radio" bind:group={methode} value={wahl.schluessel} />
            <span>
              <strong>{wahl.name}</strong>
              <span class="gedaempft">{wahl.erklaerung}</span>
            </span>
          </label>
        {/each}
      </fieldset>

      <fieldset>
        <legend>Womit</legend>
        {#each daten.datensaetze as wahl (wahl.schluessel)}
          <label class="option">
            <input type="radio" bind:group={datensatz} value={wahl.schluessel} />
            <span>
              <strong>{wahl.name}</strong>
              <span class="gedaempft">{wahl.erklaerung}</span>
            </span>
          </label>
        {/each}
      </fieldset>

      <!-- Die vierte Achse: was mit einer Probe geschieht, während gelernt
           wird. Anders als „Womit" (welche abgelegten Fassungen als eigene
           Zeilen ins Manifest kommen) wird hier nichts abgelegt - es ist in
           jedem Durchgang eine andere Abwandlung, und genau daran liegt die
           Wirkung. -->
      <fieldset>
        <legend>Wie abgewandelt wird</legend>
        {#each daten.augmentierungen as wahl (wahl.schluessel)}
          <label class="option">
            <input type="radio" bind:group={augmentierung} value={wahl.schluessel} />
            <span>
              <strong>{wahl.name}</strong>
              <span class="gedaempft">{wahl.erklaerung}</span>
            </span>
          </label>
        {/each}
      </fieldset>

      <!-- Die dritte Achse. Sie fasst das Training nicht an: Sie entscheidet
           nur, welcher Stand aus einem gelaufenen Training ausgeliefert wird -
           und lässt sich damit an denselben Testaufnahmen messen wie die
           beiden anderen. -->
      <fieldset>
        <legend>Was am Ende zählt</legend>
        {#each daten.abschluesse as wahl (wahl.schluessel)}
          <label class="option">
            <input type="radio" bind:group={abschluss} value={wahl.schluessel} />
            <span>
              <strong>{wahl.name}</strong>
              <span class="gedaempft">{wahl.erklaerung}</span>
            </span>
          </label>
        {/each}
      </fieldset>
    </div>

    {#if daten.schluessel_noetig}
      <!-- Ein Lauf belegt die Karte für Stunden, und das soll nicht jeder
           anstoßen können, der einen Aufnahmelink hat. Der Schlüssel steht
           beim Knopf und nicht auf einer Anmeldeseite: Er erlaubt keine
           Ansicht, sondern genau diese eine Handlung. -->
      <label class="schluessel">
        <span class="gedaempft">Trainerschlüssel</span>
        <input
          type="password"
          bind:value={schluessel}
          autocomplete="off"
          placeholder="nötig, um einen Lauf anzustoßen"
        />
      </label>
    {/if}

    <div class="reihe">
      <button
        class="knopf haupt"
        onclick={bestelle}
        disabled={bestellt === 'laeuft' || (daten.schluessel_noetig && !schluessel.trim())}
      >
        Training beauftragen
      </button>
      <span class="gedaempft">
        {#if gerechnetGenau.has(`${methode}/${datensatz}/${abschluss}/${augmentierung}`)}
          Diese Kombination ist schon gerechnet - ein zweiter Lauf nimmt die seither
          hinzugekommenen Aufnahmen mit.
        {:else}
          Der Lauf rechnet auf der Karte und dauert; er wartet, bis der Trainer Zeit hat.
        {/if}
      </span>
    </div>

    {#if daten.aufnahmen_neu > 0 && daten.laeufe.some((lauf) => lauf.status === 'fertig')}
      <!-- Kein Knopf, der von selbst drückt: Ein Lauf belegt die Karte und
           friert einen Stand des Korpus ein; von allein angestoßen wüsste
           hinterher niemand, welche Aufnahmen in welchem Modell stecken.
           Sichtbar machen, wann es sich lohnt, ist die halbe Automatik - und
           die richtige Hälfte. -->
      <p class="neu">
        <strong>{daten.aufnahmen_neu}</strong>
        {daten.aufnahmen_neu === 1 ? 'Aufnahme ist' : 'Aufnahmen sind'} dazugekommen, seit
        zuletzt etwas fertig trainiert wurde ({daten.aufnahmen_jetzt} insgesamt). Ein neuer Lauf
        nimmt sie mit.
      </p>
    {/if}

    <!-- Vier Felder, und man sieht auf einen Blick, welche noch fehlen: Die
         Frage dieser App ist der Vergleich der vier. -->
    <div class="matrix" aria-hidden="true">
      {#each daten.methoden as m (m.schluessel)}
        {#each daten.datensaetze as d (d.schluessel)}
          <span class="feld" class:da={gerechnet.has(`${m.schluessel}/${d.schluessel}`)}>
            {m.name} · {d.name}
          </span>
        {/each}
      {/each}
    </div>
  {:else}
    <p class="gedaempft">Wird geladen …</p>
  {/if}
</div>

{#if laeufe.length}
  <h3>Läufe</h3>
  <div class="laeufe">
    {#each laeufe as lauf (lauf.job_id)}
      <div class="karte lauf" class:offen={lauf.status === 'laeuft'}>
        <div class="kopfzeile">
          <p class="marke">{bezeichnung(lauf)}</p>
          <span class="rechts">
            <span class="zustand {lauf.status}">{STATUS[lauf.status] ?? lauf.status}</span>
            <!-- Der Papierkorb sitzt in der Kopfzeile der Karte und nicht bei
                 den Knöpfen darunter: Dort stehen die Wege weiter, hier der
                 eine Weg hinaus. Beschriftet für Vorlesestimmen, denn ein
                 Sinnbild allein sagt nichts. -->
            <button
              class="papierkorb"
              title={lauf.loeschbar
                ? 'Diesen Lauf löschen'
                : 'Ein rechnender Lauf lässt sich nicht löschen'}
              aria-label="Lauf {bezeichnung(lauf)} löschen"
              disabled={!lauf.loeschbar || loescht === lauf.job_id}
              onclick={() => loesche(lauf)}
            >
              <!-- Strich und Maß stehen als Attribute, nicht nur im
                   Stylesheet: Die Linien haben keine Fläche, ein reiner `fill`
                   zeichnet also nichts. Bliebe das CSS einmal aus, wäre der
                   Knopf unsichtbar statt unschön. -->
              <svg
                viewBox="0 0 24 24"
                width="18"
                height="18"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
              >
                <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6" />
              </svg>
            </button>
          </span>
        </div>

        <p class="gedaempft klein">
          {zeit(lauf.erstellt)} · {lauf.aufnahmen} Aufnahmen ·
          {lauf.zeilen.train ?? 0} Proben zum Lernen,
          {lauf.zeilen.test ?? 0} zum Prüfen
        </p>

        {#if lauf.status === 'laeuft'}
          <!-- Der Balken bleibt leer, solange der Trainer die Schrittzahl nicht
               genannt hat: Ein Balken, der bei null steht und nicht weiß, wovon,
               ist eine Behauptung. Die Stufe daneben sagt, dass es vorangeht. -->
          <div class="balken" aria-hidden="true">
            <div class="fuellung" style="width: {(lauf.anteil ?? 0) * 100}%"></div>
          </div>
          <p class="klein">
            {STUFEN[lauf.stufe] ?? lauf.stufe}
            {#if lauf.anteil !== null}
              <span class="gedaempft">· {(lauf.anteil * 100).toFixed(0)} %</span>
            {/if}
          </p>
        {/if}

        {#if lauf.fehler}
          <p class="hinweise">{lauf.fehler}</p>
        {/if}

        <div class="reihe">
          <a class="knopf" href="#{LAUF_ROUTE}{lauf.job_id}">
            {lauf.status === 'fertig' ? 'Ergebnis ansehen' : 'Kurven ansehen'}
          </a>
          {#if lauf.status === 'wartet'}
            <button class="knopf" onclick={() => nimmZurueck(lauf.job_id)}>
              Zurücknehmen
            </button>
            <span class="gedaempft klein">
              Solange niemand rechnet, lässt sich der Auftrag zurückziehen.
            </span>
          {/if}
        </div>
      </div>
    {/each}
  </div>
{/if}

<style>
  .bestellung {
    margin-bottom: 1.4rem;
  }

  .schluessel {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    max-width: 22rem;
    margin-bottom: 0.8rem;
    font-size: 0.85rem;
  }

  .wahlen {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem 2rem;
    margin-bottom: 0.8rem;
  }

  /* `min-width: 0` auch hier, und zwar gegen eine Eigenheit von `fieldset`:
     Es bringt eine eigene Mindestbreite mit, die sich an seinem Inhalt
     bemisst, und ignoriert damit als Flex-Element die Breite der Karte. */
  fieldset {
    border: none;
    padding: 0;
    margin: 0;
    min-width: 0;
    flex: 1 1 18rem;
  }

  legend {
    padding: 0;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--gedaempft);
    margin-bottom: 0.4rem;
  }

  /* Die Begründung steht unter dem Namen und nicht in einem Tooltip: Was die
     Wahl bedeutet, soll lesen können, wer sie trifft. */
  .option {
    display: flex;
    align-items: flex-start;
    gap: 0.6rem;
    margin: 0 0 0.5rem;
    cursor: pointer;
  }

  /* Der Knopf behält sein Maß, der Text nimmt den Rest. `min-width: 0` ist
     dabei die halbe Miete: Ohne das schrumpft ein Flex-Element nicht unter
     seinen Inhalt, und eine lange Begründung schöbe sich aus der Karte
     hinaus, statt umzubrechen. */
  .option input {
    flex: none;
    margin-top: 0.2rem;
  }

  .option > span {
    flex: 1;
    min-width: 0;
  }

  .option span {
    display: block;
    margin: 0;
  }

  .option .gedaempft {
    font-size: 0.85rem;
    line-height: 1.4;
  }

  /* Ein Hinweis, kein Alarm: Dass Aufnahmen dazugekommen sind, ist der
     Normalfall und kein Fehler. */
  .neu {
    margin: 0.9rem 0 0;
    padding: 0.5rem 0.7rem;
    border-left: 3px solid var(--akzent);
    background: var(--akzent-hell);
    border-radius: 0 0.3rem 0.3rem 0;
    font-size: 0.9rem;
  }

  .matrix {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-top: 0.9rem;
  }

  .feld {
    padding: 0.25rem 0.6rem;
    border: 1px dashed var(--rand);
    border-radius: 0.3rem;
    font-size: 0.8rem;
    color: var(--gedaempft);
  }

  .feld.da {
    border-style: solid;
    border-color: var(--akzent);
    color: var(--akzent);
    font-weight: 600;
  }

  .laeufe {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
  }

  .lauf.offen {
    border-color: var(--akzent);
  }

  .kopfzeile {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.4rem 1rem;
  }

  .marke {
    margin: 0;
    font-weight: 600;
    color: var(--akzent);
  }

  .rechts {
    display: inline-flex;
    align-items: center;
    gap: 0.6rem;
  }

  .zustand {
    font-size: 0.85rem;
    color: var(--gedaempft);
  }

  /* Leise, bis man darauf zeigt: Der Weg hinaus soll zu finden, aber nicht das
     Auffälligste an einer Karte sein. Die Fläche ist trotzdem groß genug für
     einen Daumen. */
  .papierkorb {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2.2rem;
    height: 2.2rem;
    padding: 0;
    border: 1px solid transparent;
    border-radius: 0.35rem;
    background: none;
    color: var(--gedaempft);
    cursor: pointer;
  }

  .papierkorb:hover:not(:disabled),
  .papierkorb:focus-visible {
    color: var(--fehler);
    border-color: var(--rand);
  }

  .papierkorb:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  .zustand.gescheitert {
    color: var(--fehler);
    font-weight: 600;
  }

  .zustand.fertig {
    color: var(--akzent);
    font-weight: 600;
  }

  .klein {
    font-size: 0.85rem;
    margin: 0.3rem 0;
  }

  .balken {
    height: 0.5rem;
    margin: 0.6rem 0 0.2rem;
    border-radius: 0.25rem;
    background: var(--rand);
    overflow: hidden;
  }

  .fuellung {
    height: 100%;
    background: var(--akzent);
    transition: width 0.4s ease;
  }
</style>
