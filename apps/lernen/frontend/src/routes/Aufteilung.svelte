<script lang="ts">
  /**
   * Wer lernt, wer steuert, wer prüft.
   *
   * Die Ansicht zeigt eine Entscheidung, die sie nicht treffen kann: Die
   * Zuteilung wird vergeben und nie wieder geändert (siehe
   * `backend/services/aufteilung.py`). Es gibt hier deshalb keinen Knopf, der
   * etwas verschiebt - er wäre der Weg, auf dem eine Testaufnahme ins Training
   * rutscht, und danach hätte jede Zahl dieser App ihren Wert verloren.
   *
   * **Warum die Liste trotzdem dasteht.** Weil die Zusage sonst eine Behauptung
   * wäre. Wer wissen will, ob seine Prüfaufnahmen wirklich ungesehen sind, muss
   * sie sehen können - mit ihrem Platz im Muster daneben, an dem sich die
   * Zuteilung nachrechnen lässt.
   */
  import { onMount } from 'svelte';
  import { aufteilung as ladeAufteilung, type Aufteilung } from '../lib/api';

  let daten = $state<Aufteilung | null>(null);
  let fehler = $state('');
  // Welcher Teil allein gezeigt wird; leer heißt alle. Kein Suchfeld daneben:
  // Gesucht wird hier nicht nach einem Satz, sondern nachgesehen, was in
  // welchem Topf liegt.
  let nurTeil = $state('');

  const teile = $derived(daten?.teile ?? []);
  const proben = $derived(
    (daten?.proben ?? []).filter((probe) => !nurTeil || probe.teil === nurTeil),
  );
  const gesamt = $derived(
    Object.values(daten?.anzahl ?? {}).reduce((summe, wert) => summe + wert, 0),
  );

  /**
   * Die Farbe eines Teils. Fest und nicht aus der Darstellung: Die drei müssen
   * sich voneinander unterscheiden, und wer unter „Darstellung" alles auf
   * Grüntöne stellt, hätte sonst drei gleiche Streifen. Dieselbe Palette wie
   * in der Auswertung von „hören", aus demselben Grund - sie ist auch bei
   * Rot-Grün-Schwäche auseinanderzuhalten.
   */
  const FARBEN: Record<string, string> = {
    train: '#0072b2',
    validierung: '#cc79a7',
    test: '#d55e00',
  };

  function name(schluessel: string): string {
    return teile.find((teil) => teil.schluessel === schluessel)?.name ?? schluessel;
  }

  function minuten(sekunden: number): string {
    return sekunden >= 60 ? `${(sekunden / 60).toFixed(1)} min` : `${sekunden.toFixed(0)} s`;
  }

  function anteil(schluessel: string): number {
    return gesamt ? ((daten?.anzahl?.[schluessel] ?? 0) / gesamt) * 100 : 0;
  }

  async function hole() {
    try {
      daten = await ladeAufteilung();
      fehler = '';
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  onMount(hole);
</script>

<h2>Aufteilung</h2>
<p class="gedaempft">
  Zwei Drittel der Aufnahmen trainieren das Modell, ein Drittel prüft es. Die Zuteilung wird
  einmal vergeben und nie wieder geändert: Eine Aufnahme, die geprüft hat, trainiert nie - sonst
  misst der Test, was das Modell auswendig gelernt hat.
</p>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

{#if !daten}
  <p class="gedaempft">Wird geladen …</p>
{:else if !gesamt}
  <div class="karte">
    <p>Noch keine brauchbare Aufnahme im Korpus - es gibt nichts aufzuteilen.</p>
    <p class="gedaempft">
      Aufgenommen wird in „hören". Sobald dort etwas liegt, steht es beim nächsten Blick hier.
    </p>
  </div>
{:else}
  <!-- Ein Streifen statt dreier Zahlen: Das Verhältnis ist die Auskunft, und
       ein Verhältnis sieht man schneller, als man es rechnet. -->
  <div class="streifen" aria-hidden="true">
    {#each teile as teil (teil.schluessel)}
      {#if anteil(teil.schluessel) > 0}
        <div
          class="stueck"
          style="width: {anteil(teil.schluessel)}%; background: {FARBEN[teil.schluessel]}"
        ></div>
      {/if}
    {/each}
  </div>

  <table class="zahlen">
    <thead>
      <tr>
        <th scope="col">Teil</th>
        <th scope="col">Aufnahmen</th>
        <th scope="col">Anteil</th>
        <th scope="col">Dauer</th>
        <th scope="col" class="breit">Wozu</th>
      </tr>
    </thead>
    <tbody>
      {#each teile as teil (teil.schluessel)}
        <tr>
          <th scope="row">
            <span
              class="marker"
              style="background: {FARBEN[teil.schluessel]}"
              aria-hidden="true"
            ></span>
            {teil.name}
          </th>
          <td>{daten.anzahl[teil.schluessel] ?? 0}</td>
          <td>{anteil(teil.schluessel).toFixed(0)} %</td>
          <td>{minuten(daten.sekunden[teil.schluessel] ?? 0)}</td>
          <td class="breit gedaempft">{teil.erklaerung}</td>
        </tr>
      {/each}
    </tbody>
  </table>

  <p class="gedaempft">
    Zugeteilt wird nach einem festen Muster, immer in der Reihenfolge der Aufnahme:
    <span class="muster">
      {#each daten.muster as schritt, stelle (stelle)}<span
          class="platz"
          style="background: {FARBEN[schritt]}"
          title={name(schritt)}>{stelle + 1}</span
        >{/each}
    </span>
    - und dann wieder von vorn. Kein Zufall, damit die Zuteilung ohne gespeicherten Keim
    nachvollziehbar bleibt; die Nummer in der Liste unten ist der Platz darin.
  </p>

  {#if daten.verwaist}
    <p class="hinweise">
      {daten.verwaist}
      {daten.verwaist === 1 ? 'Zuteilung gehört' : 'Zuteilungen gehören'} zu Aufnahmen, die
      gelöscht wurden. Ihr Platz bleibt vergeben - nur so behalten die übrigen ihren Teil. Das
      Verhältnis weicht dadurch leicht von 2:1 ab; das ist der richtige Preis.
    </p>
  {/if}

  <div class="reihe waehler">
    <label>
      <span>Zeigen</span>
      <select bind:value={nurTeil}>
        <option value="">alle {gesamt} Aufnahmen</option>
        {#each teile as teil (teil.schluessel)}
          <option value={teil.schluessel}>
            nur {teil.name} ({daten.anzahl[teil.schluessel] ?? 0})
          </option>
        {/each}
      </select>
    </label>
  </div>

  <table class="liste">
    <thead>
      <tr>
        <th scope="col">Nr.</th>
        <th scope="col">Teil</th>
        <th scope="col">Dauer</th>
        <th scope="col" class="breit">Vorlage</th>
      </tr>
    </thead>
    <tbody>
      {#each proben as probe (probe.aufnahme_id)}
        <tr>
          <td class="wenig">{probe.nummer + 1}</td>
          <th scope="row">
            <span
              class="marker"
              style="background: {FARBEN[probe.teil]}"
              aria-hidden="true"
            ></span>
            {name(probe.teil)}
          </th>
          <td>{probe.dauer_s.toFixed(1)} s</td>
          <td class="breit vorlage">{probe.text}</td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}

<style>
  .streifen {
    display: flex;
    height: 1.4rem;
    margin: 1rem 0 0.8rem;
    border-radius: 0.3rem;
    overflow: hidden;
    border: 1px solid var(--rand);
  }

  .stueck {
    height: 100%;
  }

  .zahlen,
  .liste {
    border-collapse: collapse;
    width: 100%;
    margin: 0.6rem 0;
  }

  .zahlen th,
  .zahlen td,
  .liste th,
  .liste td {
    padding: 0.35rem 0.9rem 0.35rem 0;
    text-align: right;
    border-bottom: 1px solid var(--rand);
    /* Ziffern gleicher Breite: Sonst stehen die Kommastellen zweier Zeilen
       nicht untereinander, und genau die vergleicht man hier. */
    font-variant-numeric: tabular-nums;
  }

  .zahlen thead th,
  .liste thead th {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--gedaempft);
  }

  .zahlen tbody th,
  .liste tbody th {
    text-align: left;
    font-weight: 600;
    white-space: nowrap;
  }

  .breit {
    text-align: left;
    width: 100%;
  }

  .wenig {
    color: var(--gedaempft);
  }

  .vorlage {
    /* Eine Zeile je Aufnahme: Die Liste ist zum Überfliegen da, nicht zum
       Lesen - der volle Text steht in „hören". */
    max-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .marker {
    display: inline-block;
    vertical-align: middle;
    margin-right: 0.5rem;
    width: 0.7rem;
    height: 0.7rem;
    border-radius: 50%;
  }

  .muster {
    display: inline-flex;
    gap: 0.2rem;
    vertical-align: middle;
  }

  .platz {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.4rem;
    height: 1.4rem;
    border-radius: 0.25rem;
    color: #fff;
    font-size: 0.8rem;
    font-weight: 600;
  }

  .waehler {
    margin-top: 0.9rem;
    align-items: flex-end;
  }

  .waehler label {
    margin: 0;
  }

  .waehler select {
    max-width: 18rem;
  }
</style>
