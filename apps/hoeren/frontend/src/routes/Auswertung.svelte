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
   * **Warum ein Diagramm und nicht eine Tabelle.** Gefragt ist nicht die
   * einzelne Zahl, sondern ob sie sich über den Korpus hinweg hält: Ein Modell,
   * das im Mittel gut ist und bei jeder fünften Aufnahme einbricht, ist ein
   * anderes Modell als eines, das gleichmäßig etwas schlechter liegt. Der
   * Mittelwert zeigt beide gleich; die Kurve zeigt den Unterschied sofort.
   *
   * **Warum trotzdem Zahlen darunter.** Weil die Kurve die andere Hälfte
   * offen lässt: Sie zeigt, *dass* eine Reihe tiefer liegt, aber nicht, um wie
   * viel. Deshalb steht unter dem Bild je Modell Median und Mittel (siehe
   * `kennzahlen`) - und gerade das Auseinanderfallen der beiden ist dieselbe
   * Auskunft wie der Einbruch in der Kurve, nur als Zahl.
   *
   * **Warum im Bild nur eine von vier Zahlen steht.** Gemessen wird jede
   * Aufnahme viermal je Modell: einmal, wie sie gesprochen wurde, und einmal
   * je Abwandlung (ausgesteuert, pauschal lauter, mit Rauschen - siehe
   * `wortlaut/augmentierung.py`). Alle vier in die Kurve zu legen ergäbe bei
   * vier Modellen sechzehn Reihen über denselben Aufnahmen; man sähe nichts
   * mehr. Die Kurve zeigt deshalb je Modell den **besten** der vier Werte -
   * was das Modell aus dieser Aufnahme herausholen kann, wenn der Ton stimmt.
   * „Am besten" heißt dabei je nach Maß größer oder kleiner: Bei den
   * Fehlerraten ist der kleinste Wert der beste, und eine Kurve, die beim
   * Wechsel des Maßes stillschweigend die Bedeutung tauschte, wäre eine Falle.
   * Die vollständigen vier Zahlen stehen in der Tabelle darunter.
   *
   * **Warum ECharts.** Diese eine Kurve käme mit weniger aus. Kommen sollen
   * aber mehrere, die sich gegenseitig folgen - und dafür ist die Wahl schon
   * jetzt zu treffen, weil ein Wechsel später jede Ansicht anfasst. ECharts
   * bringt mit, was das braucht: Zeigen und Zoomen mit dem Finger wie mit der
   * Maus, gemischte Reihen (Balken und Punkte in einem Bild), und
   * `echarts.connect`, das mehrere Diagramme aneinanderkoppelt. Geladen wird es
   * erst hier (`await import`), damit die Aufnahmeseite es nicht mitschleppt.
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
    meineAufnahmeAudio,
    vergleich as ladeVergleich,
    type Auswertung,
    type Vergleich,
  } from '../lib/api';

  // Wie oft nachgefragt wird. Während gerechnet wird, soll die Kurve mitwachsen
  // - aber ein Takt von einer Sekunde brächte nichts: Eine Aufnahme durch ein
  // Modell dauert länger. Im Ruhezustand bleibt ein langsamer Takt, damit ein
  // Lauf, der in einem anderen Reiter angestoßen wurde, hier ankommt.
  const TAKT_LAEUFT = 2500;
  const TAKT_RUHT = 20000;

  // Farben und Formen der Punktreihen. Fest und nicht aus der Darstellung:
  // Die Reihen müssen sich voneinander unterscheiden, und ein Sprecher, der
  // unter „Darstellung" alles auf Grüntöne stellt, hätte sonst drei gleiche
  // Reihen. Gewählt aus einer Palette, die auch bei Rot-Grün-Schwäche
  // auseinanderzuhalten ist - zusätzlich trägt jede Reihe eine eigene Form.
  const PUNKTFARBEN = ['#d55e00', '#0072b2', '#009e73', '#cc79a7', '#8a5aa8'];
  const PUNKTFORMEN = ['circle', 'diamond', 'triangle', 'rect', 'pin'];

  // Der Schlüssel der Zeile, die nicht zu einer Fassung gehört, sondern zur
  // Kurve: die beste der vier. Kein Name, den der Server je schickt - deshalb
  // ein Zeichen, das in keiner Kennung vorkommt.
  const BESTE = '*';

  let daten = $state<Auswertung | null>(null);
  let fehler = $state('');
  let laeuftGerade = $state('');

  let metrik = $state('genauigkeit');
  // Welches Modell als Balken steht; die übrigen werden Punkte darüber. Steht
  // hier nichts, entscheidet `balkenmodell` weiter unten.
  let gewaehlterBalken = $state('');

  let gewaehlt = $state<Vergleich | null>(null);
  let gewaehlteNummer = $state(0);
  let vergleichLaeuft = $state(false);

  /**
   * Die Aufnahme zum Mithören - genau die Fassung, deren Texte darunter stehen.
   *
   * **Warum ohne Knopf davor.** In „Meine Daten" steht ein „▶ Hören", weil dort
   * eine lange Liste von Aufnahmen untereinander liegt und der Browser sonst
   * Dutzende davon in den Speicher zöge. Hier ist es eine einzige, und man ist
   * schon zweimal hingekommen: einmal auf die Spalte getippt, einmal die
   * Fassung gewählt. Ein dritter Klick, um zu hören, worüber man gerade liest,
   * wäre einer zu viel.
   *
   * **Warum als Blob und nicht als Adresse.** Die Datei hängt am Zugang des
   * Sprechers, und ein `<audio src>` schickt keine Kopfzeilen mit.
   *
   * Die Kennung steht mit dabei, damit ein spätes Laden nicht eine Aufnahme
   * übertönt, zu der inzwischen weitergeklickt wurde.
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
      // Eine Fassung, die noch nicht gerechnet ist, gibt es schlicht nicht -
      // dann steht kein Abspieler da. Eine Fehlermeldung wäre hier eine
      // Warnung vor nichts: Die Texte darunter fehlen dann ohnehin auch.
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

  // Ob die Fassungen ihre Abweichungen von der Vorlage ausgezeichnet tragen.
  // An als Vorgabe - das ist die Frage, mit der man herkommt. Aus, sobald es
  // um den Wortlaut selbst geht: Bei einem Modell, das viel danebenliegt,
  // zerfällt der Satz in Schnipsel aus Gestrichenem und Fettem, und
  // ausgerechnet die interessanteste Fassung liest sich am schlechtesten.
  //
  // Hier und nicht unter „Darstellung": Das ist keine Vorliebe, die für jede
  // Ansicht gilt, sondern ein Griff zwischen zwei Blicken auf dieselbe
  // Aufnahme - man schaltet hin und her, nicht einmal um.
  let hervorheben = $state(true);

  // Welche Fassung im Textvergleich gelesen wird. Alle sechzehn Texte
  // untereinander wären keine Ansicht mehr, sondern eine Liste; gefragt ist
  // beim Lesen immer „was haben die Modelle aus *dieser* Aufnahme gemacht?".
  // Vorgabe ist das Original - die Aufnahme, wie sie gesprochen wurde.
  let gewaehlteFassung = $state('original');

  let huelle = $state<HTMLDivElement | null>(null);
  // Das Diagramm selbst, ohne `$state`: ECharts führt seinen eigenen Zustand,
  // und ein Proxy darum herum brächte nur Ärger.
  let diagramm: Diagramm | null = null;

  const metriken = $derived(daten?.metriken ?? []);
  const aktuelleMetrik = $derived(metriken.find((m) => m.schluessel === metrik) ?? metriken[0]);
  const modelle = $derived(daten?.modelle ?? []);
  const varianten = $derived(daten?.varianten ?? []);

  /**
   * Welches Modell den Balken bekommt. Die Vorgabe ist `small` - der
   * Alltagsfall, gegen den die übrigen zu vergleichen sind. Ist es nicht
   * konfiguriert, nimmt die Mitte der Liste seinen Platz ein; bei nur einem
   * Modell ist es dieses.
   */
  const balkenmodell = $derived(
    gewaehlterBalken && modelle.includes(gewaehlterBalken)
      ? gewaehlterBalken
      : modelle.includes('small')
        ? 'small'
        : (modelle[Math.floor((modelle.length - 1) / 2)] ?? ''),
  );

  // Die Fassungen sind je Modell viermal da; gelesen wird immer eine.
  const gelesen = $derived(
    (gewaehlt?.erkennungen ?? []).filter(
      (erkennung) => erkennung.variante === gewaehlteFassung,
    ),
  );

  const stand = $derived(daten?.stand ?? null);
  // Die gewählten Farben als **ein** Wert. `einstellungen.farben` selbst zu
  // lesen genügt nicht: Das meldet nur an, dass es das Feld gibt, nicht seinen
  // Inhalt - eine geänderte Akzentfarbe käme im Diagramm erst an, wenn man die
  // Seite verlässt und zurückkommt. Hier wird jeder Wert angefasst und damit
  // jeder einzelne beobachtet.
  const farbstand = $derived(Object.values(einstellungen.farben).join('|'));
  const anteil = $derived(stand && stand.gesamt ? stand.erledigt / stand.gesamt : 0);
  // Ob überhaupt schon etwas zu sehen ist. Ein leeres Diagramm mit Achsen wäre
  // eine Behauptung; solange nichts gerechnet ist, sagt die Seite das lieber.
  const hatWerte = $derived(
    (daten?.punkte ?? []).some((punkt) => Object.keys(punkt.werte).length > 0),
  );

  function farbe(name: string, ersatz: string): string {
    const wert = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return wert || ersatz;
  }

  type Werte = Record<string, Record<string, Record<string, number>>>;

  function wertVon(punkt: { werte: Werte }, modell: string, variante: string) {
    // `null` und nicht `0`: Was nicht gerechnet ist, ist keine Null, und eine
    // Null in der Kurve wäre ein Modell, das nichts verstanden hat.
    const gemessen = punkt.werte[modell]?.[variante]?.[metrik];
    return gemessen === undefined ? null : gemessen;
  }

  /**
   * Der beste der vier Werte eines Modells - die Zahl, die in die Kurve geht.
   *
   * Welcher der beste ist, sagt das Maß und nicht diese Funktion: Bei der
   * Genauigkeit der größte, bei jeder Fehlerrate und bei der Rechenzeit der
   * kleinste. Ohne diese Unterscheidung zeigte dieselbe Kurve beim Wechsel des
   * Maßes einmal den besten und einmal den schlechtesten Fall, ohne es zu
   * sagen.
   *
   * Gezählt wird nur, was gerechnet ist: Während ein Lauf läuft, steht hier
   * vielleicht das Beste aus zweien. Das ist richtig so - es wächst mit.
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
   * Ein Wert im gewählten Maß, so geschrieben, wie er gelesen werden soll.
   * Prozente auf eine Stelle - mehr behauptete eine Genauigkeit, die die
   * Messung nicht hat -, die Raten auf drei, weil sie klein sind und der
   * Unterschied zwischen zwei Modellen in der dritten Stelle stehen kann.
   */
  function zeige(wert: number): string {
    const einheit = aktuelleMetrik?.einheit ?? '';
    return `${wert.toFixed(einheit === '%' ? 1 : 3)}${einheit}`;
  }

  /**
   * Die Farbe einer Reihe. Eine Stelle für beides - Diagramm und Tabelle -,
   * damit die Zeile unter dem Bild dieselbe Farbe trägt wie die Punkte darin.
   * Der Akzent kommt als Argument, weil ECharts eine fertige Farbe braucht
   * und die Tabelle mit `var(--akzent)` auskommt.
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
   * **Warum beide Zahlen.** Das Mittel nimmt jeden Ausreißer mit: Eine
   * Aufnahme, bei der Whisper in eine Wiederholungsschleife gerät, zieht es
   * über den ganzen Korpus hinweg. Der Median sagt dagegen den Normalfall -
   * die Aufnahme in der Mitte. Stehen die beiden weit auseinander, liegt genau
   * darin die Auskunft: Das Modell ist nicht gleichmäßig schlechter, es
   * verreißt einzelne Aufnahmen. Deshalb beide nebeneinander und keine der
   * beiden allein.
   *
   * **Warum je Fassung eine Zeile.** Weil erst der Vergleich der vier die
   * Frage beantwortet, für die sie gerechnet wurden: Liegt ein Modell nur
   * deshalb vorn, weil der Ton gut ausgesteuert war? Bricht es bei etwas
   * Rauschen ein? Vier Zeilen, die dicht beieinanderliegen, sagen „dieses
   * Modell versteht den Sprecher"; vier, die auseinanderfallen, sagen „es
   * verträgt diese eine Aufnahmesituation".
   *
   * **Warum die beste obendrüber.** Sie ist die Zeile zur Kurve. Ohne sie
   * stünde im Bild eine Reihe, zu der unten keine Zahl gehört - und man
   * suchte sie in den vieren darunter, wo sie nicht steht: Der Median der
   * besten Werte ist nicht der beste der Mediane.
   *
   * **Warum im Browser gerechnet.** Die Zahlen stehen schon da - die Kurve
   * bringt sie ohnehin mit. Sie beim Wechsel des Maßes erneut beim Server zu
   * holen hieße, auf eine Antwort zu warten, für die kein Byte fehlt.
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
              'Beste der vier',
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
      // Ein Modell ohne eine einzige Erkennung bekommt keine Zeile: Zwei
      // Nullen wären eine Behauptung über ein Modell, das nichts gerechnet hat.
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
          name: modell,
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
        name: modell,
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
    // `replaceMerge` statt `notMerge`: Es ersetzt die Reihen vollständig (sonst
    // bliebe ein abgewähltes Modell als Leiche stehen), lässt aber den
    // Zoomausschnitt, wo er ist. Ohne das spränge die Ansicht bei jedem Takt
    // zurück, während man gerade etwas anschaut.
    diagramm.setOption(option(), { replaceMerge: ['series'] });
  }

  async function baueDiagramm() {
    if (!huelle || diagramm) return;

    // Erst jetzt geladen, und nur die eingerichteten Teile - welche das sind
    // und warum namentlich, steht in `lib/diagramm.ts`.
    const { init } = await import('../lib/diagramm');
    diagramm = init(huelle, undefined, { renderer: 'canvas' });

    // Ein Klick irgendwo in der Spalte, nicht nur auf den Balken: Auf einem
    // Telefon ist ein 20 Pixel breiter Balken kein Ziel, und ein Punkt erst
    // recht nicht.
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
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  async function starte() {
    laeuftGerade = 'start';
    try {
      await auswertungStarten();
      await hole();
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

    return () => {
      beendet = true;
      clearTimeout(uhr);
      diagramm?.dispose();
      diagramm = null;
    };
  });

  // Neu zeichnen, wenn sich die Daten, das gewählte Maß, das Balkenmodell oder
  // die Darstellung geändert haben. Die Farben stehen absichtlich in der
  // Abhängigkeitsliste: Ein Diagramm, das nach dem Umstellen der Akzentfarbe
  // die alte behielte, sähe aus wie ein Fehler.
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
        <span class="gedaempft">Alles gerechnet. Neue Aufnahmen werden nachgeholt.</span>
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
        <select bind:value={gewaehlterBalken}>
          {#each modelle as modell (modell)}
            <option value={modell}>{modell}</option>
          {/each}
        </select>
      </label>
    {/if}
  </div>
  {#if aktuelleMetrik}
    <p class="gedaempft">
      {aktuelleMetrik.erklaerung}
      {aktuelleMetrik.hoch_ist_gut ? 'Höher ist besser.' : 'Niedriger ist besser.'}
      Im Bild steht je Modell der beste seiner vier Werte - die Aufnahme wird
      viermal gemessen, einmal wie gesprochen und einmal je Abwandlung. Alle
      vier stehen in der Tabelle darunter.
    </p>
  {/if}

  {#if kennzahlen.length}
    <!-- Die Kurve zeigt den Verlauf, diese Zeile die Bilanz. Beides steht
         nebeneinander und nicht das eine statt des anderen: Eine Zahl je
         Modell wäre zu wenig, eine Kurve ohne Zahl ließe „um wie viel?"
         offen. -->
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
      <!-- Je Modell ein eigener Rumpf: Die fünf Zeilen gehören zusammen, und
           ein `tbody` sagt das auch einer Vorlesestimme - nicht nur der Linie
           dazwischen. -->
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
                  {gruppe.modell}
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
      Über alle gerechneten Aufnahmen. Der Median ist der Normalfall - die
      Aufnahme in der Mitte; das Mittel nimmt jeden Ausreißer mit. Stehen die
      beiden weit auseinander, ist das Modell nicht gleichmäßig schlechter,
      sondern verreißt einzelne Aufnahmen. Welche, zeigt die Kurve darüber.
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
      Liegen die Zeilen eines Modells dicht beieinander, versteht es den
      Sprecher. Fallen sie auseinander, verträgt es bloß eine bestimmte
      Aufnahmesituation. Die oberste Zeile je Modell ist die Reihe im Bild - je
      Aufnahme die beste der vier, und deshalb nicht der beste der vier Mediane
      darunter.
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
    <!-- Der Schalter steht bei den Texten und nicht oben bei den
         Auswahllisten: Er ändert nichts an der Messung, nur daran, wie die
         Fassungen darunter zu lesen sind. -->
    <label class="umschalter">
      <span>Unterschiede hervorheben</span>
      <input type="checkbox" role="switch" bind:checked={hervorheben} />
    </label>
  </div>
  <div class="karte">
    <p class="marke">Vorlage</p>
    <p class="vorlage">{gewaehlt.referenz}</p>
    <!-- Was dastand, und gleich darunter, was daraus wurde: Wer beurteilt, ob
         ein Modell danebengegriffen hat, hört zuerst selbst hin. Der Abspieler
         folgt der Fassungswahl darunter - beim Rauschen ist gerade das die
         Frage, ob man selbst noch versteht, was das Modell nicht verstand. -->
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
    <!-- Die Fassungen als Reihe von Schaltern und nicht als Auswahlliste: Es
         sind vier, sie stehen nebeneinander, und man springt zwischen ihnen
         hin und her, statt einmal eine auszusuchen. -->
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
        {erkennung.modell}
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
