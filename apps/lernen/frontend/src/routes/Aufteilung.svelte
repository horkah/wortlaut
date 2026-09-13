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
      Die Aufnahmen werden der Reihe nach auf {faltungen} Faltungen verteilt - die erste
      Aufnahme in Faltung 1, die zweite in Faltung 2, und nach der sechsten geht es wieder
      von vorn los. Dann wird {faltungen}-mal trainiert: Jedes Mal bleibt eine Faltung
      draußen, gelernt wird auf den anderen fünf, und gemessen wird auf der einen, die das
      Modell nicht kennt.
    </p>
    <p>
      Am Ende ist <strong>jede einzelne Aufnahme</strong> genau einmal von einem Modell gehört
      worden, das sie nie gesehen hat. Das ist die Zahl, die in der Modelltabelle steht - und
      sie steht auf dem ganzen Korpus statt auf einem Drittel davon.
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
        Für {faltungen} Faltungen braucht es mindestens {faltungen} brauchbare Aufnahmen -
        sonst bliebe eine Faltung leer und ein Training würde auf nichts gemessen. Vorhanden
        sind {daten.aufnahmen}.
      </p>
    {/if}

    <p class="klein">
      Die Aufnahmen selbst stehen unter
      <a href="/#{MEINE_DATEN_PFAD}">Meine Daten</a> - dort einmal und vollständig, mit Text,
      Dauer und zum Anhören.
    </p>
  </div>

  <div class="karte">
    <h3>Das Modell, das Sie am Ende benutzen</h3>
    <p>
      Nach den {faltungen} Messläufen wird noch ein letztes Mal trainiert, diesmal auf
      <strong>allen</strong> Aufnahmen - mit den Einstellungen, die sich in den Faltungen
      bewährt haben: wie viele Durchgänge es braucht und wie stark mit dem Grundmodell
      verrechnet wird. Dieses Modell wird gespeichert und steht in „Modelle" zur Freigabe für
      „schreiben".
    </p>
    <p class="gedaempft">
      Es hat mehr gesehen als jedes der {faltungen} Messmodelle und ist deshalb sehr
      wahrscheinlich besser als sie - und genau deshalb lässt es sich nicht mehr ehrlich
      messen: Es kennt jede Aufnahme, an der man es prüfen könnte. Die Zahl, die daneben
      steht, ist die vorsichtige aus der Kreuzvalidierung.
    </p>
  </div>

  <div class="karte">
    <h3>Was noch fehlt</h3>
    <p class="gedaempft">
      Ein wirklich unabhängiger Test - Aufnahmen, die eigens dafür entstehen und in kein
      Training geraten. Bis es sie gibt, steht hier keiner, und das ist ehrlicher, als ein
      Sechstel so zu nennen: Die Kreuzvalidierung sagt, wie gut das Verfahren auf diesem
      Korpus arbeitet, nicht, wie gut es auf der nächsten Aufnahme arbeiten wird.
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
