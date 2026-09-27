<script lang="ts">
  /**
   * Wie gut hören verschiedene Modelle diesem Sprecher zu?
   *
   * Jede Aufnahme im Korpus ist eine fertige Prüfaufgabe: Was gesprochen
   * werden sollte, steht als Vorlage daneben. Der Server schickt sie durch
   * mehrere Erkenner und misst, was herauskommt (`backend/api/auswertung.py`,
   * `wortlaut/metriken.py`); diese Seite zeigt das Ergebnis und stößt den Lauf
   * an.
   *
   * **Ein Diagramm**, denn gefragt ist, ob eine Zahl sich über den Korpus
   * hält: Ein Modell, das bei jeder fünften Aufnahme einbricht, hat dasselbe
   * Mittel wie eines, das gleichmäßig etwas schlechter liegt. **Darunter
   * Median und Mittel** (`kennzahlen`) - ihr Auseinanderfallen ist der
   * Einbruch als Zahl.
   *
   * **Im Bild je Modell der beste Wert** über die Fassungen
   * (`wortlaut/augmentierung.py`) - was das Modell herausholt, wenn der Ton
   * stimmt; „am besten" je nach Maß größer oder kleiner. Jede Fassung steht in
   * der Tabelle.
   *
   * ECharts (`lib/diagramm.ts`) wird erst hier geladen.
   */
  import { onMount } from 'svelte';
  import AudioPlayer from '$ui/AudioPlayer.svelte';
  import Textvergleich from '$ui/Textvergleich.svelte';
  import type { Diagramm } from '../lib/diagramm';
  import { einstellungen } from '$ui/einstellungen.svelte';
  import {
    auswertung as ladeAuswertung,
    auswertungStarten,
    auswertungStoppen,
    diktatmodell,
    meineAufnahmeAudio,
    vergleich as ladeVergleich,
    type Auswertung,
    type Vergleich,
  } from '../lib/api';

  // Während gerechnet wird, wächst die Kurve mit; im Ruhezustand kommt ein
  // Lauf aus einem anderen Reiter trotzdem an.
  const TAKT_LAEUFT = 2500;
  const TAKT_RUHT = 20000;

  // Fest, nicht aus der Darstellung, damit die Reihen unterscheidbar bleiben -
  // auch bei Rot-Grün-Schwäche, zusätzlich mit eigener Form.
  const PUNKTFARBEN = ['#d55e00', '#0072b2', '#009e73', '#cc79a7', '#8a5aa8'];
  const PUNKTFORMEN = ['circle', 'diamond', 'triangle', 'rect', 'pin'];

  // Die Zeile zur Kurve (Bestwert über alle Fassungen) - ein Zeichen, das in
  // keiner Kennung vorkommt.
  const BESTE = '*';

  let daten = $state<Auswertung | null>(null);
  let fehler = $state('');
  let laeuftGerade = $state('');
  // Was der letzte Knopfdruck bewirkt hat, wenn er nichts bewirkt hat. Kein
  // Fehler, sondern eine Quittung - siehe `starte`.
  let meldung = $state('');

  let metrik = $state('genauigkeit');
  // Welches Modell als Balken steht; die übrigen werden Punkte darüber. Steht
  // hier nichts, entscheidet `balkenmodell` weiter unten.
  let gewaehlterBalken = $state('');
  // Womit „schreiben" gerade diktiert - leer, solange die Antwort aussteht
  // oder „schreiben" keine gibt.
  let diktatRef = $state('');

  let gewaehlt = $state<Vergleich | null>(null);
  let gewaehlteNummer = $state(0);
  let vergleichLaeuft = $state(false);

  /**
   * Die Aufnahme zum Mithören - genau die Fassung, deren Texte darunter stehen.
   *
   * Ohne Knopf davor - es ist eine einzige, anders als die Liste in „Meine
   * Daten". Als Blob, weil `<audio src>` den Zugang nicht mitschickt. Die
   * Kennung verhindert, dass ein spätes Laden eine neuere Wahl übertönt.
   */
  let hoerprobe = $state<{ schluessel: string; adresse: string } | null>(null);

  function vergissHoerprobe() {
    if (hoerprobe) URL.revokeObjectURL(hoerprobe.adresse);
    hoerprobe = null;
  }

  async function ladeHoerprobe(aufnahmeId: string, fassung: string) {
    const schluessel = `${aufnahmeId}.${fassung}`;
    if (hoerprobe?.schluessel === schluessel) return;
    vergissHoerprobe();
    try {
      const inhalt = await meineAufnahmeAudio(aufnahmeId, fassung);
      // Noch dieselbe Aufnahme und dieselbe Fassung? Sonst ist das hier die
      // Antwort auf eine Frage, die niemand mehr stellt.
      if (gewaehlt?.aufnahme_id === aufnahmeId && gewaehlteFassung === fassung) {
        hoerprobe = { schluessel, adresse: URL.createObjectURL(inhalt) };
      }
    } catch {
      // Noch nicht gerechnet: kein Abspieler, keine Meldung.
      vergissHoerprobe();
    }
  }

  // Nachladen, sobald sich Aufnahme oder Fassung ändert - und aufräumen, wenn
  // die Ansicht geht: Ein nicht freigegebenes Objekt-URL hält die ganze
  // Audiodatei im Speicher.
  $effect(() => {
    const aufnahmeId = gewaehlt?.aufnahme_id;
    const fassung = gewaehlteFassung;
    if (!aufnahmeId) {
      vergissHoerprobe();
      return;
    }
    ladeHoerprobe(aufnahmeId, fassung);
  });

  $effect(() => () => vergissHoerprobe());

  // Abweichungen von der Vorlage auszeichnen - an als Vorgabe, aus für den
  // Wortlaut, wenn ein Satz sonst in Schnipsel zerfällt. Ein Griff zwischen
  // zwei Blicken, keine Vorliebe unter „Darstellung".
  let hervorheben = $state(true);

  // Welche Fassung im Textvergleich gelesen wird - eine, Vorgabe das Original.
  let gewaehlteFassung = $state('original');

  let huelle = $state<HTMLDivElement | null>(null);
  // Das Diagramm selbst, ohne `$state`: ECharts führt seinen eigenen Zustand,
  // und ein Proxy darum herum brächte nur Ärger.
  let diagramm: Diagramm | null = null;

  const metriken = $derived(daten?.metriken ?? []);
  const aktuelleMetrik = $derived(metriken.find((m) => m.schluessel === metrik) ?? metriken[0]);
  const modelle = $derived(daten?.modelle ?? []);
  /**
   * Der Name, der dasteht: Grundmodellname oder Kurzkennung des Standes.
   */
  const benannt = $derived((modell: string) => daten?.beschriftungen?.[modell] ?? modell);
  const varianten = $derived(daten?.varianten ?? []);

  /**
   * Welches Modell den Balken bekommt: das, womit „schreiben" diktiert -
   * sonst `small`, sonst die Mitte der Liste.
   */
  const balkenmodell = $derived(
    gewaehlterBalken && modelle.includes(gewaehlterBalken)
      ? gewaehlterBalken
      : diktatRef && modelle.includes(diktatRef)
        ? diktatRef
        : modelle.includes('small')
          ? 'small'
          : (modelle[Math.floor((modelle.length - 1) / 2)] ?? ''),
  );

  // Je Modell stehen alle Fassungen da; gelesen wird eine.
  const gelesen = $derived(
    (gewaehlt?.erkennungen ?? []).filter(
      (erkennung) => erkennung.variante === gewaehlteFassung,
    ),
  );

  const stand = $derived(daten?.stand ?? null);
  // Die Farben als ein Wert, damit jede einzeln beobachtet wird - sonst käme
  // eine neue Akzentfarbe erst nach einem Seitenwechsel an.
  const farbstand = $derived(Object.values(einstellungen.farben).join('|'));
  const anteil = $derived(stand && stand.gesamt ? stand.erledigt / stand.gesamt : 0);
  // Solange nichts gerechnet ist, sagt die Seite es, statt leere Achsen zu zeigen.
  const hatWerte = $derived(
    (daten?.punkte ?? []).some((punkt) => Object.keys(punkt.werte).length > 0),
  );

  function farbe(name: string, ersatz: string): string {
    const wert = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return wert || ersatz;
  }

  type Werte = Record<string, Record<string, Record<string, number>>>;

  function wertVon(punkt: { werte: Werte }, modell: string, variante: string) {
    // `null`, nicht `0`: Nicht gerechnet ist nicht nichts verstanden.
    const gemessen = punkt.werte[modell]?.[variante]?.[metrik];
    return gemessen === undefined ? null : gemessen;
  }

  /**
   * Der Bestwert eines Modells über alle Fassungen - die Zahl in der Kurve.
   *
   * Bei der Genauigkeit der größte, sonst der kleinste. Gezählt wird, was
   * gerechnet ist - während eines Laufs wächst es mit.
   */
  function bestesVon(punkt: { werte: Werte }, modell: string) {
    const gemessen = Object.values(punkt.werte[modell] ?? {})
      .map((fassung) => fassung[metrik])
      .filter((wert): wert is number => wert !== undefined);
    if (!gemessen.length) return null;
    return aktuelleMetrik?.hoch_ist_gut === false
      ? Math.min(...gemessen)
      : Math.max(...gemessen);
  }

  /**
   * Ein Wert im gewählten Maß: Prozente auf eine Stelle, Raten auf drei.
   */
  function zeige(wert: number): string {
    const einheit = aktuelleMetrik?.einheit ?? '';
    return `${wert.toFixed(einheit === '%' ? 1 : 3)}${einheit}`;
  }

  /**
   * Die Farbe einer Reihe, für Diagramm und Tabelle. Der Akzent als Argument:
   * ECharts braucht eine fertige Farbe, die Tabelle nimmt `var(--akzent)`.
   */
  function reihenfarbe(modell: string, nummer: number, akzent: string): string {
    return modell === balkenmodell ? akzent : PUNKTFARBEN[nummer % PUNKTFARBEN.length];
  }

  /** Eine Zeile der Tabelle: eine Reihe von Werten, zu zwei Zahlen gerafft. */
  type Kennzahl = {
    schluessel: string;
    name: string;
    /** Wie viele Aufnahmen dahinterstehen - ohne die sind die Zahlen nicht zu lesen. */
    anzahl: number;
    median: number;
    mittel: number;
  };

  /** Ein Modell mit seinen Zeilen: die beste der Fassungen, dann jede einzeln. */
  type Modellzahlen = {
    modell: string;
    nummer: number;
    zeilen: Kennzahl[];
  };

  function median(werte: number[]): number {
    const sortiert = [...werte].sort((eins, zwei) => eins - zwei);
    const mitte = Math.floor(sortiert.length / 2);
    return sortiert.length % 2
      ? sortiert[mitte]
      : (sortiert[mitte - 1] + sortiert[mitte]) / 2;
  }

  function gerafft(schluessel: string, name: string, werte: number[]): Kennzahl {
    return {
      schluessel,
      name,
      anzahl: werte.length,
      median: werte.length ? median(werte) : 0,
      mittel: werte.length ? werte.reduce((summe, wert) => summe + wert, 0) / werte.length : 0,
    };
  }

  /**
   * Median und Mittel je Modell und Fassung, im gerade gewählten Maß.
   *
   * Das Mittel nimmt jeden Ausreißer mit, der Median zeigt den Normalfall -
   * weit auseinander heißt: Das Modell verreißt einzelne Aufnahmen. Je
   * Fassung eine Zeile, denn ihr Abstand zeigt, ob ein Modell beim Rauschen
   * einbricht. Obendrüber die Zeile zur Kurve: Der Median der Bestwerte ist
   * nicht der beste der Mediane. Im Browser gerechnet - die Daten sind da.
   */
  const kennzahlen = $derived<Modellzahlen[]>(
    modelle
      .map((modell, nummer) => {
        const punkte = daten?.punkte ?? [];
        const gefiltert = (werte: (number | null)[]) =>
          werte.filter((wert): wert is number => wert !== null);
        return {
          modell,
          nummer,
          zeilen: [
            gerafft(
              BESTE,
              'Bestwert',
              gefiltert(punkte.map((punkt) => bestesVon(punkt, modell))),
            ),
            ...varianten.map((variante) =>
              gerafft(
                variante.schluessel,
                variante.name,
                gefiltert(punkte.map((punkt) => wertVon(punkt, modell, variante.schluessel))),
              ),
            ),
          ],
        };
      })
      // Ohne Erkennung keine Zeile.
      .filter((gruppe) => gruppe.zeilen[0].anzahl > 0),
  );

  function option() {
    const punkte = daten?.punkte ?? [];
    const schrift = farbe('--text', '#1c1b19');
    const leise = farbe('--gedaempft', '#6b6b6b');
    const rand = farbe('--rand', '#d8d4cd');
    const akzent = farbe('--akzent', '#1b4d3e');
    const einheit = aktuelleMetrik?.einheit ?? '';

    const reihen = modelle.map((modell, nummer) => {
      const werte = punkte.map((punkt) => bestesVon(punkt, modell));
      if (modell === balkenmodell) {
        return {
          id: modell,
          // `id` bleibt die Kennung des Modells, `name` ist, was in der
          // Legende steht - bei einem Stand die Kurzkennung statt seines
          // ganzen Pfades.
          name: benannt(modell),
          type: 'bar' as const,
          data: werte,
          itemStyle: {
            color: reihenfarbe(modell, nummer, akzent),
            borderRadius: [2, 2, 0, 0],
          },
          barMaxWidth: 26,
          z: 2,
          // Die Markierung sitzt auf dem Balken und nicht in einer eigenen
          // Reihe: So bleibt sie beim Zoomen an ihrer Aufnahme.
          markArea: gewaehlteNummer
            ? {
                silent: true,
                itemStyle: { color: `${akzent}1f` },
                data: [
                  [{ xAxis: String(gewaehlteNummer) }, { xAxis: String(gewaehlteNummer) }],
                ],
              }
            : undefined,
        };
      }
      return {
        id: modell,
        name: benannt(modell),
        type: 'scatter' as const,
        data: werte,
        symbol: PUNKTFORMEN[nummer % PUNKTFORMEN.length],
        symbolSize: 9,
        itemStyle: {
          color: reihenfarbe(modell, nummer, akzent),
          borderColor: '#fff',
          borderWidth: 1,
        },
        z: 3,
      };
    });

    return {
      // Die Schriftart der Oberfläche gilt auch hier: Wer sie unter
      // „Darstellung" umstellt, soll nicht ein Diagramm in einer anderen
      // Schrift bekommen.
      textStyle: { fontFamily: einstellungen.schriftart, color: schrift },
      animationDuration: 300,
      grid: { left: 8, right: 14, top: 16, bottom: 76, containLabel: true },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        confine: true,
        valueFormatter: (wert: number | null) =>
          wert === null || wert === undefined ? 'noch nicht gerechnet' : zeige(wert),
      },
      legend: { bottom: 34, itemGap: 18, textStyle: { color: leise } },
      dataZoom: [
        // Ziehen und Zwei-Finger-Zoom direkt im Bild - das ist die Geste, die
        // auf einem Telefon erwartet wird.
        { type: 'inside', throttle: 60 },
        { type: 'slider', height: 16, bottom: 6, borderColor: rand, fillerColor: `${akzent}22` },
      ],
      xAxis: {
        type: 'category',
        data: punkte.map((punkt) => String(punkt.nummer)),
        name: 'Aufnahme',
        nameLocation: 'end' as const,
        nameGap: 6,
        nameTextStyle: { color: leise },
        axisLine: { lineStyle: { color: rand } },
        axisLabel: { color: leise, hideOverlap: true },
        axisTick: { alignWithLabel: true },
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: aktuelleMetrik?.obergrenze ?? undefined,
        name: `${aktuelleMetrik?.name ?? ''}${einheit ? ` (${einheit})` : ''}`,
        nameTextStyle: { color: leise, align: 'left' as const },
        axisLabel: { color: leise },
        splitLine: { lineStyle: { color: rand, opacity: 0.6 } },
      },
      series: reihen,
    };
  }

  function zeichne() {
    if (!diagramm) return;
    // `replaceMerge`: ersetzt die Reihen, lässt aber den Zoomausschnitt stehen.
    diagramm.setOption(option(), { replaceMerge: ['series'] });
  }

  async function baueDiagramm() {
    if (!huelle || diagramm) return;

    // Erst jetzt geladen, und nur die eingerichteten Teile - welche das sind
    // und warum namentlich, steht in `lib/diagramm.ts`.
    const { init } = await import('../lib/diagramm');
    diagramm = init(huelle, undefined, { renderer: 'canvas' });

    // Ein Klick irgendwo in der Spalte - auf dem Telefon ist ein Balken kein Ziel.
    diagramm.getZr().on('click', (ereignis: { offsetX: number; offsetY: number }) => {
      if (!diagramm) return;
      const ort = [ereignis.offsetX, ereignis.offsetY];
      if (!diagramm.containPixel('grid', ort)) return;
      const [stelle] = diagramm.convertFromPixel({ seriesIndex: 0 }, ort) as number[];
      waehleStelle(Math.round(stelle));
    });

    new ResizeObserver(() => diagramm?.resize()).observe(huelle);
    zeichne();
  }

  async function waehleStelle(stelle: number) {
    const punkt = daten?.punkte[stelle];
    if (!punkt || punkt.nummer === gewaehlteNummer) return;
    gewaehlteNummer = punkt.nummer;
    vergleichLaeuft = true;
    try {
      gewaehlt = await ladeVergleich(punkt.aufnahme_id);
    } catch (ursache) {
      gewaehlt = null;
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      vergleichLaeuft = false;
    }
  }

  async function hole() {
    try {
      daten = await ladeAuswertung();
      fehler = '';
      // Sobald wieder gerechnet wird, ist die Quittung von vorhin überholt.
      if (daten.stand.laeuft) meldung = '';
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  /**
   * Den Lauf anstoßen - und sagen, wenn dabei nichts zu tun war.
   *
   * Der Lauf rechnet nur, was fehlt (`services/auswertung.py`). Steht alles,
   * sähe der Knopf kaputt aus - deshalb eine Quittung, kein Fehler.
   */
  async function starte() {
    laeuftGerade = 'start';
    meldung = '';
    try {
      // Die Antwort auf das Anstoßen sagt es selbst: `laeuft` ist genau dann
      // falsch, wenn nichts offen war (siehe `services/auswertung.py`). Sich
      // stattdessen auf den Stand nach `hole()` zu verlassen wäre ein Rennen -
      // die Aufgabe im Hintergrund kann dann schon angefangen haben oder
      // eben nicht.
      const angestossen = await auswertungStarten();
      await hole();
      if (!angestossen.laeuft) {
        meldung = angestossen.gesamt
          ? `Nichts Neues zu rechnen - alle ${angestossen.gesamt} Messungen stehen schon.`
          : 'Noch keine Aufnahmen, an denen sich etwas messen ließe.';
      }
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      laeuftGerade = '';
    }
  }

  async function halteAn() {
    laeuftGerade = 'stopp';
    try {
      await auswertungStoppen();
      await hole();
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      laeuftGerade = '';
    }
  }

  onMount(() => {
    let uhr: ReturnType<typeof setTimeout>;
    let beendet = false;

    // Ein sich selbst neu stellender Wecker statt eines festen Intervalls: So
    // hängt der Takt am Zustand (rechnet oder ruht), und zwei Abfragen können
    // sich nicht überholen, wenn der Server einmal länger braucht.
    async function takt() {
      await hole();
      if (beendet) return;
      uhr = setTimeout(takt, stand?.laeuft ? TAKT_LAEUFT : TAKT_RUHT);
    }

    takt();
    baueDiagramm();
    // Einmal je Besuch: Freigegeben wird in „lernen", und wer das tut, kommt
    // danach über den Reiter hierher zurück.
    diktatmodell().then((ref) => {
      if (!beendet && ref) diktatRef = ref;
    });

    return () => {
      beendet = true;
      clearTimeout(uhr);
      diagramm?.dispose();
      diagramm = null;
    };
  });

  // Neu zeichnen bei neuen Daten, Maß, Balkenmodell oder Darstellung.
  $effect(() => {
    void daten;
    void metrik;
    void balkenmodell;
    void gewaehlteNummer;
    void farbstand;
    void einstellungen.schriftart;
    if (diagramm) zeichne();
  });
</script>

<h2>Auswertung</h2>
<p class="gedaempft">
  Jede Aufnahme ist zugleich eine Prüfaufgabe: Was vorgelesen werden sollte, steht daneben. Hier
  laufen mehrere Erkenner über dieselben Aufnahmen, und was sie daraus machen, wird mit der Vorlage
  verglichen.
</p>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

<div class="karte lauf">
  {#if !stand}
    <p class="gedaempft">Wird geladen …</p>
  {:else if stand.gesamt === 0}
    <p>Noch keine brauchbare Aufnahme im Korpus - es gibt nichts zu messen.</p>
    <p class="gedaempft">
      Aufnehmen unter „Aufnehmen"; verworfene Aufnahmen zählen hier bewusst nicht mit.
    </p>
  {:else}
    <div class="balken" aria-hidden="true">
      <div style="width: {(anteil * 100).toFixed(1)}%"></div>
    </div>
    <p class="zahlen">
      <strong>{stand.erledigt}</strong> von {stand.gesamt} gerechnet
      <span class="gedaempft">({(anteil * 100).toFixed(0)} %)</span>
      {#if stand.laeuft && stand.aktuell}
        <span class="gedaempft">· läuft gerade: {stand.aktuell}</span>
      {/if}
      {#if stand.uebersprungen}
        <span class="gedaempft">· {stand.uebersprungen} übersprungen</span>
      {/if}
    </p>

    {#if stand.fehler}
      <p class="hinweise">{stand.fehler}</p>
    {/if}

    <div class="reihe">
      {#if stand.laeuft}
        <button class="knopf" onclick={halteAn} disabled={laeuftGerade === 'stopp'}>
          Anhalten
        </button>
        <span class="gedaempft">
          Läuft im Hintergrund weiter - diese Seite darf zu sein.
        </span>
      {:else if stand.fremder_lauf}
        <span class="gedaempft">
          Es läuft gerade eine Auswertung für einen anderen Sprecher. Es rechnet immer nur eine.
        </span>
      {:else if stand.erledigt >= stand.gesamt}
        <button class="knopf" onclick={starte} disabled={laeuftGerade === 'start'}>
          Erneut prüfen
        </button>
        <span class="gedaempft">
          {meldung || 'Alles gerechnet. Neue Aufnahmen werden nachgeholt.'}
        </span>
      {:else}
        <button class="knopf haupt" onclick={starte} disabled={laeuftGerade === 'start'}>
          Auswertung starten
        </button>
        <span class="gedaempft">
          Rechnet auf diesem Server und dauert; darum von Hand angestoßen.
        </span>
      {/if}
    </div>
  {/if}
</div>

<!-- Das Diagramm bleibt im Baum, auch solange nichts darin steht: ECharts
     bindet sich beim Aufbau an dieses Element, und ein `{#if}` darum nähme es
     ihm unter den Füßen weg. -->
<div class="bild" class:leer={!hatWerte}>
  <div class="leinwand" bind:this={huelle}></div>
  {#if !hatWerte}
    <p class="gedaempft ueberlagert">
      {stand && stand.gesamt ? 'Noch nichts gerechnet.' : 'Noch keine Aufnahmen.'}
    </p>
  {/if}
</div>

{#if hatWerte}
  <div class="reihe waehler">
    <label>
      <span>Maß</span>
      <select bind:value={metrik}>
        {#each metriken as eintrag (eintrag.schluessel)}
          <option value={eintrag.schluessel}>{eintrag.name}</option>
        {/each}
      </select>
    </label>
    {#if modelle.length > 1}
      <label>
        <span>Als Balken</span>
        <!-- `balkenmodell`, nicht `gewaehlterBalken`: Auch die Vorgabe soll dastehen. -->
        <select
          value={balkenmodell}
          onchange={(ereignis) => (gewaehlterBalken = ereignis.currentTarget.value)}
        >
          {#each modelle as modell (modell)}
            <option value={modell}
              >{benannt(modell)}{modell === diktatRef ? ' · schreiben' : ''}</option
            >
          {/each}
        </select>
      </label>
    {/if}
  </div>
  {#if aktuelleMetrik}
    <p class="gedaempft">
      {aktuelleMetrik.erklaerung}
      {aktuelleMetrik.hoch_ist_gut ? 'Höher ist besser.' : 'Niedriger ist besser.'}
      Im Bild steht je Modell sein bester Wert - die Aufnahme wird in jeder
      Fassung gemessen, einmal wie gesprochen und einmal je Abwandlung. Alle
      stehen in der Tabelle darunter.
    </p>
  {/if}

  {#if kennzahlen.length}
    <!-- Die Kurve zeigt den Verlauf, diese Zeilen die Bilanz. -->
    <table class="kennzahlen">
      <thead>
        <tr>
          <th scope="col">Modell</th>
          <th scope="col">Fassung</th>
          <th scope="col">Median</th>
          <th scope="col">Mittel</th>
          <th scope="col">Aufnahmen</th>
        </tr>
      </thead>
      <!-- Je Modell ein `tbody` - die Zeilen gehören zusammen, auch für Vorlesestimmen. -->
      {#each kennzahlen as gruppe (gruppe.modell)}
        <tbody>
          {#each gruppe.zeilen as zeile, stelle (zeile.schluessel)}
            <tr class:beste={zeile.schluessel === BESTE}>
              {#if stelle === 0}
                <!-- Der Name steht einmal und gilt für die Zeilen darunter.
                     Dieselbe Farbe wie im Bild, und für den Balken ein Rechteck
                     statt eines Punktes: So findet man die Zeile zur Reihe auch
                     dann, wenn man Farben nicht unterscheiden kann. -->
                <th scope="rowgroup" rowspan={gruppe.zeilen.length}>
                  <span
                    class="marker"
                    class:balken={gruppe.modell === balkenmodell}
                    style="background: {reihenfarbe(gruppe.modell, gruppe.nummer, 'var(--akzent)')}"
                    aria-hidden="true"
                  ></span>
                  {benannt(gruppe.modell)}
                </th>
              {/if}
              <th scope="row" class="fassung">{zeile.name}</th>
              <td>{zeige(zeile.median)}</td>
              <td>{zeige(zeile.mittel)}</td>
              <td class="wenig">{zeile.anzahl}</td>
            </tr>
          {/each}
        </tbody>
      {/each}
    </table>
    <p class="gedaempft">
      Über alle gerechneten Aufnahmen. Median = Normalfall, Mittel = mit
      Ausreißern. Weit auseinander heißt: Das Modell verreißt einzelne
      Aufnahmen - welche, zeigt die Kurve.
    </p>
    <p class="gedaempft">
      Die Fassungen sind dieselbe Aufnahme unter veränderten Bedingungen:
    </p>
    <ul class="fassungsliste gedaempft">
      {#each varianten as variante (variante.schluessel)}
        <li><strong>{variante.name}</strong> - {variante.erklaerung}</li>
      {/each}
    </ul>
    <p class="gedaempft">
      Dicht beieinander: Das Modell versteht den Sprecher. Weit auseinander: Es
      verträgt nur eine bestimmte Aufnahmesituation. Der Bestwert oben ist je
      Aufnahme der beste über alle Fassungen - und damit nicht der beste der
      Mediane darunter.
    </p>
  {/if}

  <p class="gedaempft">
    Auf eine Spalte tippen zeigt die Vorlage und darunter, was jedes Modell
    daraus gemacht hat - eine Fassung zur Zeit, umschaltbar.
  </p>
{/if}

{#if vergleichLaeuft}
  <p class="gedaempft">Wird geladen …</p>
{:else if gewaehlt}
  <div class="kopfzeile">
    <h2>Aufnahme {gewaehlt.nummer}</h2>
    <!-- Bei den Texten: Der Schalter ändert nur, wie sie zu lesen sind. -->
    <label class="umschalter">
      <span>Unterschiede hervorheben</span>
      <input type="checkbox" role="switch" bind:checked={hervorheben} />
    </label>
  </div>
  <div class="karte">
    <p class="marke">Vorlage</p>
    <p class="vorlage">{gewaehlt.referenz}</p>
    <!-- Erst selbst hinhören; der Abspieler folgt der Fassungswahl. -->
    {#if hoerprobe}
      <AudioPlayer
        quelle={hoerprobe.adresse}
        beschriftung={varianten.length > 1
          ? `Gehört: ${varianten.find((v) => v.schluessel === gewaehlteFassung)?.name ?? gewaehlteFassung}`
          : 'Die Aufnahme'}
      />
    {/if}
  </div>

  {#if varianten.length > 1}
    <!-- Schalter statt Auswahlliste - man springt zwischen den Fassungen. -->
    <div class="fassungen" role="group" aria-label="Fassung der Aufnahme">
      {#each varianten as variante (variante.schluessel)}
        <button
          type="button"
          class="knopf schmal"
          class:haupt={gewaehlteFassung === variante.schluessel}
          aria-pressed={gewaehlteFassung === variante.schluessel}
          title={variante.erklaerung}
          onclick={() => (gewaehlteFassung = variante.schluessel)}
        >
          {variante.name}
        </button>
      {/each}
    </div>
    <p class="gedaempft">
      {varianten.find((variante) => variante.schluessel === gewaehlteFassung)?.erklaerung ?? ''}
    </p>
  {/if}

  {#each gelesen as erkennung (erkennung.modell)}
    <div class="karte">
      <p class="marke">
        {benannt(erkennung.modell)}
        <span class="gedaempft">
          · Genauigkeit {erkennung.genauigkeit.toFixed(1)} % · WER {erkennung.wer.toFixed(2)} ·
          {erkennung.rechenzeit_s.toFixed(1)} s
        </span>
      </p>
      <Textvergleich vorlage={gewaehlt.referenz} erkannt={erkennung.text} {hervorheben} />
    </div>
  {/each}

  {#if !gelesen.length}
    <p class="gedaempft">Für diese Fassung ist noch nichts gerechnet.</p>
  {/if}

  {#if hervorheben}
    <p class="gedaempft">
      <del>Durchgestrichen</del> fehlt in der Erkennung, <ins>hervorgehoben</ins> kam hinzu.
      Verglichen wird auf Zeichen; gemessen wird dagegen ohne Satzzeichen und Großschreibung, damit
      ein fehlender Punkt nicht als Hörfehler zählt.
    </p>
  {:else}
    <p class="gedaempft">
      Jede Fassung so, wie das Modell sie geschrieben hat. Die Zahlen daneben stehen unverändert -
      gemessen wird immer gegen die Vorlage, ob die Abweichungen nun ausgezeichnet sind oder nicht.
    </p>
  {/if}
{/if}

<style>
  .lauf {
    margin-bottom: 1rem;
  }

  .zahlen {
    margin: 0.6rem 0 0.4rem;
  }

  /* Feste Höhe: Ein Diagramm, das mit seinen Daten wächst, schöbe beim
     Nachladen alles darunter nach unten. */
  .bild {
    position: relative;
    height: 22rem;
    border: 1px solid var(--rand);
    border-radius: 0.5rem;
    background: #fff;
    padding: 0.5rem;
    box-sizing: border-box;
  }

  .leinwand {
    width: 100%;
    height: 100%;
  }

  .ueberlagert {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0;
    pointer-events: none;
  }

  .waehler {
    margin-top: 0.9rem;
    align-items: flex-end;
    gap: 1rem;
  }

  .waehler label {
    margin: 0;
  }

  .waehler select {
    max-width: 16rem;
  }

  /* Überschrift links, Schalter rechts - und auf einem schmalen Telefon
     untereinander, damit die Beschriftung nicht umbricht. */
  .kopfzeile {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.5rem 1rem;
  }

  .umschalter {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin: 0;
    cursor: pointer;
  }

  /* Das Stylesheet macht `label > span` klein, grau und zu einer eigenen
     Zeile darüber - hier steht die Beschriftung neben dem Schalter. */
  .umschalter span {
    display: inline;
    margin: 0;
  }

  .kennzahlen {
    border-collapse: collapse;
    margin: 0.9rem 0 0.6rem;
    /* Nicht über die ganze Breite: Schmale Spalten, die sich über einen großen
       Bildschirm ziehen, sind schwerer zu lesen als eine kurze Zeile. */
    width: auto;
    min-width: min(100%, 28rem);
  }

  .fassungsliste {
    margin: 0.2rem 0 0.6rem;
    padding-left: 1.2rem;
    line-height: 1.5;
  }

  .kennzahlen th,
  .kennzahlen td {
    padding: 0.35rem 0.9rem 0.35rem 0;
    text-align: right;
    border-bottom: 1px solid var(--rand);
    /* Ziffern gleicher Breite: Sonst stehen die Kommastellen zweier Zeilen
       nicht untereinander, und genau die vergleicht man hier. */
    font-variant-numeric: tabular-nums;
  }

  .kennzahlen thead th {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--gedaempft);
  }

  /* Die Namensspalte bleibt eine Tabellenzelle - ein `display: flex` darauf
     nähme sie der Tabellenrechnung, und die Spalten stünden nicht mehr
     untereinander. Der Punkt davor ist deshalb `inline-block`. */
  .kennzahlen tbody th {
    text-align: left;
    font-weight: 600;
  }

  .kennzahlen .wenig {
    color: var(--gedaempft);
  }

  /* Die Fassungen eines Modells stehen eingerückt unter seinem Namen - sie
     gehören dazu und sind nicht selbst Modelle. */
  .kennzahlen .fassung {
    font-weight: 400;
    color: var(--gedaempft);
    padding-right: 1.2rem;
  }

  /* Die Zeile zur Kurve, hervorgehoben wie die Reihe im Bild. */
  .kennzahlen .beste .fassung,
  .kennzahlen .beste td {
    font-weight: 600;
    color: inherit;
  }

  /* Nur zwischen den Modellen eine Linie, nicht zwischen ihren Fassungen:
     Sonst zerfiele die Gruppe in fünf gleich schwere Zeilen. */
  .kennzahlen tbody th,
  .kennzahlen tbody td {
    border-bottom: none;
  }

  .kennzahlen tbody {
    border-bottom: 1px solid var(--rand);
  }

  .fassungen {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin: 0.8rem 0 0.4rem;
  }

  .fassungen .schmal {
    padding: 0.35rem 0.7rem;
    font-size: 0.9rem;
  }

  .marker {
    display: inline-block;
    vertical-align: middle;
    margin-right: 0.5rem;
    width: 0.7rem;
    height: 0.7rem;
    border-radius: 50%;
  }

  .marker.balken {
    border-radius: 0.1rem;
    width: 0.6rem;
    height: 0.9rem;
  }

  .marke {
    margin: 0 0 0.4rem;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--akzent);
  }

  .vorlage {
    margin: 0;
    line-height: 1.55;
  }

  /* Dieselbe Auszeichnung wie im Vergleich selbst, damit die Legende zeigt,
     wovon sie spricht. */
  del {
    color: var(--gedaempft);
    text-decoration: line-through;
  }

  ins {
    color: var(--fehler);
    font-weight: 700;
    text-decoration: none;
  }
</style>
