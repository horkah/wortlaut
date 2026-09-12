<script lang="ts">
  /**
   * Alle Modelle dieses Menschen an einem Ort - gemessen, verglichen, freigegeben.
   *
   * **Warum eine Ansicht und nicht zwei.** Es waren zwei: eine Liste der
   * eigenen Stände mit einem Freigabeknopf hier, und drüben in „schreiben"
   * eine zweite Liste, in der sich zusätzlich ein Grundmodell auswählen ließ.
   * Zwei Ansichten, zwei Begriffe, dieselbe Entscheidung - und in keiner von
   * beiden stand die Frage, um die es geht: Ist das eigene Modell besser als
   * das, was Whisper von sich aus mitbringt? Diese Frage beantwortet nur eine
   * Tabelle, in der beide Sorten nebeneinander stehen.
   *
   * **Warum eine Tabelle und nicht Karten.** Karten zeigen ein Modell gut und
   * fünf Modelle schlecht: Der Blick muss von Zahl zu Zahl springen, statt
   * eine Spalte hinunterzulaufen. Gefragt ist hier eine Rangfolge, und eine
   * Rangfolge liest man in Spalten.
   *
   * **Warum trotzdem wenig darin steht.** Vier Spalten, mehr nicht. Die
   * vollständige Aufschlüsselung - je Aufnahme, je Fassung, mit den erkannten
   * Texten daneben - steht dort, wo sie hingehört: in der Auswertung von
   * „hören" und beim einzelnen Lauf. Hier wird entschieden, nicht geforscht.
   *
   * **Warum das Beste hervorgehoben wird und nicht sortiert werden muss.**
   * Sortiert wird trotzdem, nach der Spalte, die gerade zählt; aber auch ohne
   * einen Klick soll die beste Zahl jeder Spalte ins Auge fallen. Sie steht
   * nicht nur farbig da, sondern trägt ein Wort in ihrem `title` - Farbe
   * allein wäre für einen Teil der Leser keine Auskunft.
   */
  import { onMount } from 'svelte';
  import {
    aussteuernSetzen,
    diktatmodell as ladeDiktatmodell,
    gibFrei,
    modelle as ladeModelle,
    type Diktatmodell,
    type Mass,
    type Modell,
    type Modelluebersicht,
  } from '../lib/api';

  let uebersicht = $state<Modelluebersicht | null>(null);
  let diktat = $state<Diktatmodell | null>(null);
  let fehler = $state('');
  let geladen = $state(false);
  let arbeitet = $state('');

  // Welche Fassung die Tabelle zeigt. „Alle Fassungen" ist die Vorgabe: Das
  // ist die Zahl, die ein Modell in einem Satz beschreibt. Wer wissen will, ob
  // ein Stand den Sprecher verstanden hat oder seine Aufnahmesituation,
  // schaltet auf „Original" oder „Rauschen" um - dieselbe Frage wie beim Lauf.
  let fassung = $state('alle');
  // Wonach sortiert wird; die Richtung ergibt sich aus dem Maß selbst (bei den
  // Fehlerraten ist klein besser). Ein eigener Umschalter dafür wäre eine
  // Gelegenheit, versehentlich die schlechtesten nach oben zu holen.
  let sortiertNach = $state('genauigkeit');

  const masse = $derived(uebersicht?.masse ?? []);
  const fassungen = $derived(uebersicht?.fassungen ?? []);
  const gewaehlteFassung = $derived(fassungen.find((f) => f.schluessel === fassung));

  function wert(modell: Modell, mass: string): number | null {
    const werte = modell.werte[fassung];
    return werte && werte[mass] !== undefined ? werte[mass] : null;
  }

  /** Deutsche Schreibweise, feste Stellenzahl - sonst springen die Spalten. */
  function zahl(roh: number, mass: Mass): string {
    return (
      roh.toLocaleString('de-DE', {
        minimumFractionDigits: mass.stellen,
        maximumFractionDigits: mass.stellen,
      }) + mass.einheit
    );
  }

  const zeilen = $derived(
    [...(uebersicht?.modelle ?? [])].sort((a, b) => {
      const links = wert(a, sortiertNach);
      const rechts = wert(b, sortiertNach);
      // Ungemessene Modelle ganz nach unten: Sie sind keine schlechten, sie
      // sind unbekannte, und oben zwischen den Zahlen wären sie ein Rätsel.
      if (links === null && rechts === null) return 0;
      if (links === null) return 1;
      if (rechts === null) return -1;
      const hochIstGut = masse.find((m) => m.schluessel === sortiertNach)?.hoch_ist_gut ?? true;
      return hochIstGut ? rechts - links : links - rechts;
    }),
  );

  /** Der beste Wert einer Spalte - oder `null`, wenn niemand ihn gemessen hat. */
  function bester(mass: Mass): number | null {
    const werte = (uebersicht?.modelle ?? [])
      .map((modell) => wert(modell, mass.schluessel))
      .filter((eintrag): eintrag is number => eintrag !== null);
    if (!werte.length) return null;
    return mass.hoch_ist_gut ? Math.max(...werte) : Math.min(...werte);
  }

  const einheiten = $derived(
    Math.max(0, ...(uebersicht?.modelle ?? []).map((modell) => modell.einheiten[fassung] ?? 0)),
  );

  async function hole() {
    try {
      uebersicht = await ladeModelle();
      fehler = '';
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      geladen = true;
    }
    diktat = await ladeDiktatmodell();
  }

  async function freigeben(ref: string) {
    arbeitet = ref;
    try {
      uebersicht = await gibFrei(ref);
      fehler = '';
      // „schreiben" lädt daraufhin ein anderes Modell - die Zeile oben soll
      // das sofort sagen und nicht erst beim nächsten Öffnen.
      diktat = await ladeDiktatmodell();
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      arbeitet = '';
    }
  }

  async function schalteAussteuern(an: boolean) {
    arbeitet = 'aussteuern';
    try {
      diktat = (await aussteuernSetzen(an)) ?? diktat;
    } finally {
      arbeitet = '';
    }
  }

  onMount(hole);
</script>

<h2>Modelle</h2>
<p class="gedaempft">
  Was diesem Menschen zuhören kann - die selbst trainierten Stände und die unveränderten
  Grundmodelle, an denselben Testaufnahmen gemessen. Freigegeben ist höchstens eines; mit dem
  arbeitet „schreiben".
</p>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

{#if !geladen}
  <p class="gedaempft">Wird geladen …</p>
{:else if uebersicht}
  {#if diktat}
    <div class="karte einsatz">
      <div class="kopfzeile">
        <p class="marke">Beim Diktieren geladen</p>
        {#if !diktat.trainiert}
          <span class="abzeichen leise">Grundmodell</span>
        {/if}
      </div>
      <p class="beschriftung">{diktat.beschriftung}</p>

      <label class="umschalter">
        <span>Vor dem Erkennen aussteuern</span>
        <input
          type="checkbox"
          role="switch"
          checked={diktat.aussteuern}
          disabled={arbeitet === 'aussteuern'}
          onchange={(ereignis) => schalteAussteuern(ereignis.currentTarget.checked)}
        />
      </label>
      <p class="gedaempft klein">
        Das Diktat wird lauter gerechnet, bis seine lauteste Stelle knapp unter dem Anschlag steht -
        ein einziger Faktor über die ganze Aufnahme. Vor allem die kleineren Modelle hören damit
        besser. Gespeichert wird die Aufnahme trotzdem so, wie sie gesprochen wurde.
      </p>
    </div>
  {/if}

  <div class="messgrundlage">
    <p class="gedaempft klein">
      {#if uebersicht.vergleichbar}
        Gemessen an {uebersicht.testaufnahmen} Testaufnahmen, die kein Modell je zum Lernen gesehen
        hat - {einheiten}
        {einheiten === 1 ? 'Messung' : 'Messungen'} je Modell, für alle dieselben.
      {:else}
        Noch kein gemeinsamer Boden: Jede Zeile rechnet auf dem, was sie hat.
      {/if}
    </p>
    <label class="fassungswahl">
      <span>Fassung</span>
      <select bind:value={fassung}>
        {#each fassungen as eintrag (eintrag.schluessel)}
          <option value={eintrag.schluessel}>{eintrag.name}</option>
        {/each}
      </select>
    </label>
  </div>

  {#if gewaehlteFassung}
    <p class="gedaempft klein hinweiszeile">{gewaehlteFassung.erklaerung}</p>
  {/if}

  {#if uebersicht.hinweis}
    <p class="warnung">{uebersicht.hinweis}</p>
  {/if}

  <div class="tabellenrahmen">
    <table>
      <thead>
        <tr>
          <th scope="col" class="modellspalte">Modell</th>
          {#each masse as mass (mass.schluessel)}
            <th scope="col" class="zahlenspalte">
              <!-- Der Kopf ist zugleich der Sortierknopf: eine Fläche, die man
                   ohnehin liest, und kein zusätzlicher Bedienteil daneben. -->
              <button
                type="button"
                class="sortierknopf"
                class:aktiv={sortiertNach === mass.schluessel}
                title="{mass.erklaerung} Klicken sortiert danach."
                onclick={() => (sortiertNach = mass.schluessel)}
              >
                {mass.kurz}
              </button>
            </th>
          {/each}
          <th scope="col" class="wahlspalte"><span class="versteckt">Freigabe</span></th>
        </tr>
      </thead>
      <tbody>
        {#each zeilen as modell (modell.ref)}
          <tr class:frei={modell.freigegeben}>
            <th scope="row" class="modellspalte">
              <span class="zeile">
                <span class="name">{modell.name}</span>
                {#if modell.art === 'trainiert'}
                  <span class="abzeichen leise">eigenes</span>
                {/if}
                {#if modell.freigegeben}
                  <span class="abzeichen">freigegeben</span>
                {/if}
              </span>
              <span class="gedaempft klein">{modell.herkunft}</span>
            </th>

            {#each masse as mass (mass.schluessel)}
              {@const roh = wert(modell, mass.schluessel)}
              {@const beste = bester(mass)}
              <td class="zahlenspalte">
                {#if roh === null}
                  <span class="gedaempft" title="Auf diesen Aufnahmen nicht gemessen.">–</span>
                {:else}
                  <span class:beste={roh === beste} title={roh === beste ? 'Bester Wert dieser Spalte' : undefined}>
                    {zahl(roh, mass)}
                  </span>
                {/if}
              </td>
            {/each}

            <td class="wahlspalte">
              {#if modell.freigegeben}
                <span class="gedaempft klein">gilt</span>
              {:else}
                <button
                  class="knopf"
                  disabled={arbeitet === modell.ref}
                  onclick={() => freigeben(modell.ref)}
                >
                  Freigeben
                </button>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  <p class="gedaempft klein">
    Freigeben zieht jedes andere Modell zurück - es gilt immer höchstens eines, und es gilt sofort;
    ein Neustart ist dafür nicht nötig. Ein größeres Grundmodell hört genauer und rechnet länger:
    Nach dem Wechsel dauert das erste Diktat spürbar, weil das Modell erst geladen wird.
  </p>
  <p class="gedaempft klein">
    Die Zahlen kommen aus zwei Rechnungen, die es längst gibt: für die Grundmodelle aus der
    Auswertung in „hören", für jeden eigenen Stand aus der Bewertung seines Laufs. Gemessen wird
    einmal - ein zweites Mal wäre eine zweite Gelegenheit, es anders zu machen. Aufgeschlüsselt je
    Aufnahme steht beides dort, wo es entstanden ist.
  </p>
{/if}

<style>
  /* Die Zeile, die sagt, womit gerade gesprochen wird - sie steht über der
     Tabelle, weil sie die Antwort ist und die Tabelle die Begründung. */
  .einsatz {
    margin-bottom: 1.2rem;
  }

  .kopfzeile {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.4rem 1rem;
  }

  .marke {
    margin: 0 0 0.2rem;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--akzent);
  }

  .beschriftung {
    margin: 0 0 0.8rem;
    font-size: 1.05rem;
    font-weight: 600;
  }

  /* Beschriftung links, Schalter rechts - und auf einem schmalen Telefon
     untereinander. Das Stylesheet macht `label > span` sonst klein, grau und
     zu einer eigenen Zeile darüber. */
  .umschalter {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem 1rem;
    margin: 0;
    padding-top: 0.7rem;
    border-top: 1px solid var(--rand);
    cursor: pointer;
  }

  .umschalter span {
    display: inline;
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: inherit;
  }

  /* Was gemessen wurde, links; welche Fassung gezeigt wird, rechts. Beides
     gehört zusammen: Die eine Zeile sagt, worauf sich die andere bezieht. */
  .messgrundlage {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.4rem 1rem;
    margin-bottom: 0.3rem;
  }

  .messgrundlage p {
    margin: 0;
    flex: 1 1 14rem;
  }

  .fassungswahl {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0;
    flex: none;
  }

  .fassungswahl span {
    display: inline;
    margin: 0;
    font-size: 0.85rem;
  }

  .fassungswahl select {
    width: auto;
    margin: 0;
  }

  .hinweiszeile {
    margin: 0 0 0.8rem;
  }

  /* Auf einem schmalen Gerät scrollt die Tabelle, statt die Seite zu
     sprengen - die erste Spalte trägt den Namen und bleibt darum stehen. */
  .tabellenrahmen {
    overflow-x: auto;
    border: 1px solid var(--rand);
    border-radius: 0.5rem;
    background: #fff;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-variant-numeric: tabular-nums;
  }

  th,
  td {
    padding: 0.55rem 0.7rem;
    text-align: left;
    vertical-align: middle;
  }

  thead th {
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--gedaempft);
    border-bottom: 1px solid var(--rand);
    white-space: nowrap;
  }

  tbody tr + tr th,
  tbody tr + tr td {
    border-top: 1px solid var(--rand);
  }

  /* Das freigegebene Modell ist die Antwort auf die Frage dieser Seite - es
     trägt zusätzlich das Wort „freigegeben", damit die Farbe nicht die
     einzige Auskunft ist. */
  tbody tr.frei th,
  tbody tr.frei td {
    background: var(--akzent-hell);
  }

  .modellspalte {
    min-width: 13rem;
    font-weight: 400;
  }

  .modellspalte .zeile {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.4rem;
  }

  .modellspalte .name {
    font-weight: 600;
  }

  .modellspalte .klein {
    display: block;
  }

  .zahlenspalte {
    text-align: right;
    white-space: nowrap;
  }

  .wahlspalte {
    text-align: right;
    white-space: nowrap;
  }

  .beste {
    font-weight: 700;
    color: var(--akzent);
  }

  .sortierknopf {
    padding: 0;
    border: 0;
    background: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }

  .sortierknopf:hover {
    color: var(--akzent);
    text-decoration: underline;
  }

  .sortierknopf.aktiv {
    color: var(--akzent);
    text-decoration: underline;
  }

  /* Nicht nur eine Farbe: Der Zustand steht als Wort da, damit er auch ohne
     Farbunterscheidung zu lesen ist. */
  .abzeichen {
    padding: 0.05rem 0.45rem;
    border-radius: 0.25rem;
    background: var(--akzent);
    color: #fff;
    font-size: 0.72rem;
    font-weight: 600;
    white-space: nowrap;
  }

  .abzeichen.leise {
    background: none;
    border: 1px solid var(--rand);
    color: var(--gedaempft);
  }

  .klein {
    font-size: 0.85rem;
    margin: 0.2rem 0;
  }

  /* Eine Spaltenüberschrift, die nur die Vorlesestimme braucht: Über den
     Freigabeknöpfen stünde sonst ein Wort, das die Zeile daneben schon sagt. */
  .versteckt {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
</style>
