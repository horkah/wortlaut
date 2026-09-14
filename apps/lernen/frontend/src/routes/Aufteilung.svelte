<script lang="ts">
  /**
   * Wie gemessen wird - und warum die Aufnahmen hier nicht noch einmal stehen.
   *
   * Diese Ansicht hieß einmal „wer lernt, wer steuert, wer prüft" und zeigte
   * jede Aufnahme mit ihrem Platz in der Aufteilung. Das war nötig, solange es
   * ein Testdrittel gab: Wer wissen wollte, ob seine Prüfaufnahmen ungesehen
   * sind, musste sie sehen können.
   *
   * Seit der Kreuzvalidierung gibt es diese Teilmenge nicht mehr - jede
   * Aufnahme trainiert in fünf von sechs Faltungen und misst in der sechsten.
   * Es bleibt also nichts nachzuzählen, und die Liste wäre eine zweite
   * Darstellung derselben Daten, die unter „Meine Daten" schon vollständig
   * steht. Zwei Listen über dieselbe Sache sind eine zu viel; die zweite ist
   * die, die irgendwann nicht mehr stimmt.
   *
   * Was hierher gehört, ist die Erklärung: was mit den Aufnahmen geschieht,
   * wenn trainiert und gemessen wird.
   */
  import { onMount } from 'svelte';
  import { MEINE_DATEN_PFAD } from '$ui/apps';
  import { aufteilung as ladeAufteilung, type Aufteilung } from '../lib/api';

  let daten = $state<Aufteilung | null>(null);
  let fehler = $state('');

  const faltungen = $derived(daten?.faltungen ?? 6);
  const jeFaltung = $derived(
    Object.entries(daten?.je_faltung ?? {})
      .map(([nummer, anzahl]) => ({ nummer: Number(nummer), anzahl }))
      .sort((a, b) => a.nummer - b.nummer),
  );
  const groesste = $derived(Math.max(1, ...jeFaltung.map((f) => f.anzahl)));

  function minuten(sekunden: number): string {
    const m = Math.round(sekunden / 60);
    return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
  }

  onMount(async () => {
    try {
      daten = await ladeAufteilung();
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  });
</script>

<h2>Wie gemessen wird</h2>

{#if fehler}
  <p class="fehler">{fehler}</p>
{:else if !daten}
  <p class="gedaempft">Wird geladen …</p>
{:else}
  <p class="gedaempft">
    Ein Trainingslauf rechnet {faltungen} Trainings hintereinander, nicht eines. Erst
    {faltungen} für die Messung, dann eines, das ausgeliefert wird.
  </p>

  <div class="karte">
    <h3>Sechsfache Kreuzvalidierung</h3>
    <p>
      Die Aufnahmen gehen reihum auf {faltungen} Faltungen. Dann wird {faltungen}-mal
      trainiert: gelernt auf fünf Faltungen, gemessen auf der sechsten.
    </p>
    <p>
      So ist am Ende <strong>jede Aufnahme</strong> genau einmal von einem Modell gehört
      worden, das sie nicht kannte. Das ist die Zahl in der Modelltabelle.
    </p>

    {#if daten.aufnahmen > 0}
      <div class="faltungen" aria-hidden="true">
        {#each jeFaltung as faltung (faltung.nummer)}
          <div class="faltung">
            <div class="saeule">
              <div class="fuellung" style="height: {(faltung.anzahl / groesste) * 100}%"></div>
            </div>
            <span class="klein">{faltung.nummer + 1}</span>
            <span class="gedaempft klein">{faltung.anzahl}</span>
          </div>
        {/each}
      </div>
      <p class="gedaempft klein">
        {daten.aufnahmen} Aufnahmen, {minuten(daten.sekunden)} Sprache, verteilt auf
        {faltungen} Faltungen.
      </p>
    {/if}

    {#if !daten.genug}
      <p class="hinweise">
        {faltungen} Faltungen brauchen mindestens {faltungen} brauchbare Aufnahmen - vorhanden
        sind {daten.aufnahmen}.
      </p>
    {/if}

    <p class="klein">
      Die Aufnahmen selbst: <a href="/#{MEINE_DATEN_PFAD}">Meine Daten</a>.
    </p>
  </div>

  <div class="karte">
    <h3>Das Modell, das Sie am Ende benutzen</h3>
    <p>
      Nach den {faltungen} Messläufen wird ein letztes Mal trainiert - auf
      <strong>allen</strong> Aufnahmen, mit den Einstellungen, die sich in den Faltungen
      bewährt haben (Durchgänge, α, Tempo). Dieser Stand steht in „Modelle" zur Freigabe.
    </p>
    <p class="gedaempft">
      Er kennt jede Aufnahme und lässt sich deshalb nicht mehr messen. Die Zahl daneben ist
      die vorsichtige aus der Kreuzvalidierung.
    </p>
  </div>

  <div class="karte">
    <h3>Was noch fehlt</h3>
    <p class="gedaempft">
      Ein unabhängiger Test - eigens aufgenommen, in keinem Training. Die Kreuzvalidierung
      sagt, wie gut das Verfahren auf <em>diesem</em> Korpus arbeitet, nicht wie gut auf der
      nächsten Aufnahme.
    </p>
  </div>
{/if}

<style>
  .karte + .karte {
    margin-top: 1rem;
  }

  h3 {
    margin: 0 0 0.6rem;
    font-size: 1rem;
  }

  p {
    margin: 0 0 0.7rem;
    line-height: 1.55;
  }

  p:last-child {
    margin-bottom: 0;
  }

  .klein {
    font-size: 0.85rem;
  }

  /* Sechs Säulen nebeneinander - kein Diagramm, nur ein Blick darauf, ob die
     Faltungen gleich schwer sind. Bei einem Korpus, der nicht durch sechs
     teilbar ist, sind sie es nicht ganz, und das soll man sehen. */
  .faltungen {
    display: flex;
    align-items: flex-end;
    gap: 0.5rem;
    margin: 1rem 0 0.6rem;
    height: 5rem;
  }

  .faltung {
    display: flex;
    flex: 1;
    flex-direction: column;
    align-items: center;
    gap: 0.15rem;
    height: 100%;
  }

  .saeule {
    display: flex;
    flex: 1;
    align-items: flex-end;
    width: 100%;
    min-height: 0;
  }

  .fuellung {
    width: 100%;
    min-height: 2px;
    background: var(--akzent);
    border-radius: 0.2rem 0.2rem 0 0;
  }

  .hinweise {
    margin: 0.9rem 0 0.7rem;
  }
</style>
