<script lang="ts">
  /**
   * Läufe beauftragen und ihnen zusehen.
   *
   * **Warum wenige Wahlen und keine Formularseite.** Sieben Achsen, jede mit
   * wenigen Werten; alles andere steht im Rezept. Jede Achse steht im Auftrag
   * und als Glied im Optionscode (`wortlaut/laeufe.optionscode`), der einen
   * Lauf hier, in der Modelltafel und in der Einzelansicht benennt. Die
   * Vorgaben sind das Verfahren, nach dem jeder Stand von vorher entstand.
   *
   * **Warum die Liste im Takt nachfragt.** Ein Training dauert Stunden. Der
   * Balken soll währenddessen wachsen, ohne dass jemand neu lädt - und er soll
   * es auch dann, wenn der Auftrag in einem anderen Reiter angestoßen wurde.
   * Im Ruhezustand bleibt ein langsamer Takt: Läuft nichts, ist nichts zu
   * sehen.
   *
   * **Warum fertige Läufe hier fehlen.** Ein fertiger Lauf ist ein Modell und
   * steht in der Modelltafel; von dort führt sein Code in die Einzelansicht,
   * wo er sich auch löschen lässt. Hier stehen nur die Läufe, die noch etwas
   * tun oder an denen etwas schiefging - oben, vor der Bestellung.
   */
  import { onMount } from 'svelte';
  import {
    beauftrage as beauftrageLauf,
    brichAb,
    laeufe as ladeLaeufe,
    loescheLauf,
    type Grundmodell,
    type Lauf,
    type Laufliste,
    type Wahl,
  } from '../lib/api';
  import { setzeTrainerschluessel, trainerschluessel } from '../lib/trainerschluessel';
  import { setzeTrainingswahl, trainingswahl } from '../lib/trainingswahl';
  import { LAUF_ROUTE, gehZu } from '../lib/zustand.svelte';
  import { zeitpunkt } from '$ui/zeit';

  // Während gerechnet wird, soll der Balken mitwachsen - aber ein Takt von
  // einer Sekunde brächte nichts: Ein Trainingsschritt dauert länger.
  const TAKT_LAEUFT = 3000;
  const TAKT_RUHT = 20000;

  let daten = $state<Laufliste | null>(null);
  let fehler = $state('');
  let bestellt = $state('');
  // Welcher Lauf gerade gelöscht wird - der Knopf sperrt sich so lange selbst.
  let loescht = $state('');

  // Die Wahl kommt aus dem Browser und geht dorthin zurück: Wer vier Läufe
  // vergleicht, sieht sich zwischendurch Kurven an, und nach der Rückkehr soll
  // nicht alles wieder auf der Vorgabe stehen (siehe `lib/trainingswahl.ts`).
  // Die Vorgaben selbst sind das Verfahren von vorher - siehe Kopf dieser Datei.
  const gemerkt = trainingswahl();
  let grundmodell = $state(gemerkt.grundmodell);
  let methode = $state(gemerkt.methode);
  let datensatz = $state(gemerkt.datensatz);
  let abschluss = $state(gemerkt.abschluss);
  let augmentierung = $state(gemerkt.augmentierung);
  let dauer = $state(gemerkt.dauer);
  let tempowahl = $state(gemerkt.tempowahl);

  $effect(() => {
    setzeTrainingswahl({
      grundmodell,
      methode,
      datensatz,
      abschluss,
      augmentierung,
      dauer,
      tempowahl,
    });
  });

  /**
   * Welche Methoden das gewählte Grundmodell verträgt.
   *
   * Der Server sagt es je Grundmodell mit; die Seite führt keine eigene Liste.
   * Steht die Wahl auf einer Kombination, die es nicht gibt - etwa weil beim
   * letzten Besuch ein anderes Grundmodell gewählt war -, rückt die Methode auf
   * die erste zurück, die geht.
   */
  const gewaehltesGrundmodell = $derived(
    daten?.grundmodelle.find((g) => g.schluessel === (grundmodell || daten?.basismodell)),
  );
  const erlaubteMethoden = $derived(
    gewaehltesGrundmodell?.methoden ?? (daten?.methoden ?? []).map((m) => m.schluessel),
  );

  $effect(() => {
    if (erlaubteMethoden.length && !erlaubteMethoden.includes(methode)) {
      methode = erlaubteMethoden[0];
    }
  });
  // Der Trainerschlüssel. Er steht hier neben Methode und Datensatz, weil er
  // an derselben Stelle gebraucht wird - aber er gehört nicht zur Bestellung,
  // sondern zur Erlaubnis, sie aufzugeben (siehe `lib/trainerschluessel.ts`).
  let schluessel = $state(trainerschluessel());

  const laeufe = $derived(daten?.laeufe ?? []);
  const arbeitet = $derived(laeufe.some((lauf) => lauf.status === 'laeuft'));
  const wartend = $derived(laeufe.filter((lauf) => lauf.status === 'wartet').length);

  // Was hier als Karte steht: alles außer den fertigen Läufen - die sind
  // Modelle und stehen in der Modelltafel, samt Weg in die Einzelansicht.
  // Die rechnenden und wartenden zuerst, danach gescheiterte und
  // zurückgenommene; innerhalb dessen bleibt die Reihenfolge des Servers.
  const RANG: Record<string, number> = { laeuft: 0, wartet: 1 };
  const offeneLaeufe = $derived(
    laeufe
      .filter((lauf) => lauf.status !== 'fertig')
      .map((lauf, stelle) => ({ lauf, stelle }))
      .sort((a, b) => (RANG[a.lauf.status] ?? 2) - (RANG[b.lauf.status] ?? 2) || a.stelle - b.stelle)
      .map(({ lauf }) => lauf),
  );

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
            [
              lauf.basismodell,
              lauf.methode,
              lauf.daten,
              lauf.abschluss || 'bester',
              lauf.augmentierung || 'keine',
              lauf.dauer || 'fest',
              lauf.tempowahl || 'wie_eingestellt',
            ].join('/'),
        ),
    ),
  );

  /**
   * Die gerade eingestellte Bestellung als Schlüssel - dieselbe Form wie in
   * `gerechnetGenau`.
   *
   * Das Grundmodell steht mit darin, und das fehlte bis September 2026: Ein
   * fertiger `small`-Lauf meldete eine `medium`-Bestellung als „schon
   * gerechnet". Solange es nur ein Grundmodell gab, war der Schlüssel
   * vollständig; seither war er es nicht mehr, ohne dass sich etwas daran
   * geändert hätte - der stillste aller Fehler.
   */
  const bestellschluessel = $derived(
    [
      grundmodell || daten?.basismodell || '',
      methode,
      datensatz,
      abschluss,
      augmentierung,
      dauer,
      tempowahl,
    ].join('/'),
  );

  const STUFEN: Record<string, string> = {
    vorbereiten: 'wird vorbereitet',
    laden: 'Modell wird geladen',
    tempowahl: 'sucht die Geschwindigkeit',
    training: 'trainiert',
    abschluss: 'die Gewichte werden abgeschlossen',
    sichern: 'wird gesichert',
    umwandeln: 'wird umgewandelt',
    bewerten: 'misst die zurückgehaltene Faltung',
  };

  /**
   * Welches der sieben Trainings gerade läuft.
   *
   * Ohne diese Angabe erschien „Modell wird geladen" siebenmal im Lauf, ohne
   * dass zu sehen war, dass es jedes Mal ein anderes Training ist - wer nach
   * zwanzig Minuten wieder hinsah, las dieselbe Zeile wie am Anfang und
   * schloss auf einen Lauf, der hängt.
   */
  function wobei(lauf: Lauf): string {
    const stufe = STUFEN[lauf.stufe] ?? lauf.stufe;
    if (lauf.status !== 'laeuft') return stufe;
    // `faltung === null` heißt: das siebte Training, das auf allem lernt.
    // Auch das gehört dazu - sonst sieht die letzte halbe Stunde eines Laufs
    // aus wie die erste.
    const wo =
      lauf.faltung === null
        ? 'Endmodell'
        : `Faltung ${lauf.faltung + 1} von ${lauf.faltungen_gesamt}`;
    return `${wo} · ${stufe}`;
  }

  /**
   * Wie lange ein Lauf schon stillsteht, für Menschen.
   *
   * Grob und mit Absicht: Ob es einundzwanzig oder zweiundzwanzig Minuten
   * sind, ändert nichts an dem, was jemand jetzt tut. Dass es Minuten und
   * nicht Sekunden sind, ändert alles.
   */
  function stillstand(sekunden: number | null): string {
    const s = sekunden ?? 0;
    if (s < 5400) return `${Math.round(s / 60)} Minuten`;
    const stunden = s / 3600;
    return stunden < 48
      ? `${Math.round(stunden)} Stunden`
      : `${Math.round(stunden / 24)} Tagen`;
  }

  const STATUS: Record<string, string> = {
    wartet: 'wartet auf den Trainer',
    laeuft: 'läuft',
    fertig: 'fertig',
    gescheitert: 'gescheitert',
    abgebrochen: 'zurückgenommen',
  };

  /** `1.75` → `1,75×`, `2` → `2×`. Ohne Nullen, die niemand liest. */
  function tempoText(faktor: number): string {
    return `${faktor.toFixed(2).replace(/0+$/, '').replace(/\.$/, '').replace('.', ',')}×`;
  }

  /**
   * Die Geschwindigkeit, mit der ein Lauf rechnet - ein Ergebnis, keine Option,
   * und deshalb nicht im Optionscode.
   */
  function tempoErgebnis(lauf: Lauf): string {
    if (lauf.tempowahl !== 'aus') {
      if (lauf.tempo === null) return 'Tempo wird ermittelt';
      return `Tempo ${tempoText(lauf.tempo)}${lauf.tempo_endgueltig ? '' : ' (vorläufig)'}`;
    }
    return lauf.tempo !== null && lauf.tempo !== 1 ? `Tempo ${tempoText(lauf.tempo)}` : '';
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
      await beauftrageLauf(
        {
          methode,
          daten: datensatz,
          abschluss,
          augmentierung,
          dauer,
          tempowahl,
          grundmodell,
        },
        schluessel,
      );
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
    const zeilen = [`${lauf.code} vom ${zeitpunkt(lauf.erstellt)} löschen?`, ''];
    if (lauf.stand) {
      zeilen.push(`Das Modell „${lauf.stand.version}" wird mitgelöscht.`);
      if (lauf.stand.freigegeben) {
        zeilen.push(
          'Es ist gerade freigegeben - „schreiben" fällt danach auf das Grundmodell zurück, ' +
            'bis ein anderer Stand freigegeben wird.',
        );
      }
      // Die Folge, die niemand erwartet: Die Modelltafel rechnet jede Zahl
      // über die Messungen, die **alle** Modelle haben. Fällt eine Zeile weg,
      // wächst diese Schnittmenge - und jede übrige Zahl ändert sich.
      // Gemessen waren das 0,15 WER, als ein alter Stand verschwand.
      zeilen.push(
        'In der Modelltafel können sich dadurch die Zahlen der übrigen Modelle ändern: ' +
          'Sie stehen auf den Messungen, die alle Modelle gemeinsam haben.',
      );
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

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

<!-- Die Läufe zuerst: Wer diese Seite öffnet, will meist wissen, wie weit der
     laufende ist, und erst danach den nächsten beauftragen. Fertige stehen
     hier nicht - sie sind Modelle und stehen in der Modelltafel. -->
{#if offeneLaeufe.length}
  <h2>Läufe</h2>
  <div class="laeufe">
    {#each offeneLaeufe as lauf (lauf.job_id)}
      <!-- `offen` hebt die Karte hervor, solange gerechnet wird. Ein hängender
           Lauf gehört nicht dazu: Er sagt zwar `laeuft`, aber hervorzuheben ist
           er nicht, weil dort etwas geschieht, sondern weil dort nichts mehr
           geschieht - und das sagt schon das Wort daneben. -->
      <div class="karte lauf" class:offen={lauf.status === 'laeuft' && !lauf.haengt}>
        <div class="kopfzeile">
          <p class="marke">
            <!-- Die Kennung sagt, **welcher** Stand, der Optionscode, **was**
                 er ist - beide dieselben wie in der Modelltafel. Der Code ist
                 der Weg in die Einzelansicht. -->
            {#if lauf.kennung}<code class="kennung">{lauf.kennung}</code>{/if}
            <a class="titel" href="#{LAUF_ROUTE}{lauf.job_id}">{lauf.code}</a>
          </p>
          <span class="rechts">
            <!-- Ein hängender Lauf sagt im Zustand `laeuft`. Das hier ist die
                 einzige Stelle, an der die Ansicht ihm widerspricht - und sie
                 tut es, weil „läuft" neben einem Balken, der sich seit zwanzig
                 Minuten nicht bewegt, die Unwahrheit ist. -->
            <span class="zustand {lauf.haengt ? 'gescheitert' : lauf.status}">
              {lauf.haengt ? 'hängt' : (STATUS[lauf.status] ?? lauf.status)}
            </span>
            <!-- Der Papierkorb sitzt in der Kopfzeile der Karte und nicht bei
                 den Knöpfen darunter: Dort stehen die Wege weiter, hier der
                 eine Weg hinaus. Beschriftet für Vorlesestimmen, denn ein
                 Sinnbild allein sagt nichts. -->
            <button
              class="papierkorb"
              title={lauf.loeschbar
                ? 'Diesen Lauf löschen'
                : 'Ein rechnender Lauf lässt sich nicht löschen'}
              aria-label="Lauf {lauf.code} löschen"
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
          {zeitpunkt(lauf.erstellt)} · {lauf.aufnahmen} Aufnahmen ·
          {lauf.zeilen.gesamt ?? 0} Proben · {daten?.faltungen ?? 6} Faltungen
          {#if tempoErgebnis(lauf)} · {tempoErgebnis(lauf)}{/if}
        </p>

        {#if lauf.haengt}
          <!-- Kein Balken. Ein Fortschrittsbalken sagt „gleich kommt der
               nächste Schritt", und genau das stimmt hier nicht. Was
               stattdessen dasteht, ist die Auskunft, die weiterhilft: wie weit
               er kam, und seit wann nichts mehr geschah. -->
          <p class="hinweise">
            Keine Ausgabe seit {stillstand(lauf.stillstand_s)}{#if lauf.anteil !== null},
              stehen geblieben bei {(lauf.anteil * 100).toFixed(0)} %{/if}. Nicht fortsetzbar.
          </p>
        {:else if lauf.status === 'laeuft'}
          <!-- Der Balken bleibt leer, solange der Trainer die Schrittzahl nicht
               genannt hat: Ein Balken, der bei null steht und nicht weiß, wovon,
               ist eine Behauptung. Die Stufe daneben sagt, dass es vorangeht. -->
          <div class="balken" aria-hidden="true">
            <div class="fuellung" style="width: {(lauf.anteil ?? 0) * 100}%"></div>
          </div>
          <p class="klein">
            {wobei(lauf)}
            {#if lauf.anteil !== null}
              <span class="gedaempft">· {(lauf.anteil * 100).toFixed(0)} %</span>
            {/if}
          </p>
        {/if}

        {#if lauf.fehler}
          <p class="hinweise">{lauf.fehler}</p>
        {/if}

        {#if lauf.status === 'wartet'}
          <div class="reihe">
            <button class="knopf" onclick={() => nimmZurueck(lauf.job_id)}>
              Zurücknehmen
            </button>
          </div>
        {/if}
      </div>
    {/each}
  </div>
{/if}

<h2>Training</h2>

{#snippet option(wahl: Wahl | Grundmodell)}
  <span>
    <strong>{wahl.name}</strong>
    {#if wahl.code}<code class="glied">{wahl.code}</code>{/if}
    {#if wahl.erklaerung}<span class="gedaempft">{wahl.erklaerung}</span>{/if}
  </span>
{/snippet}

<div class="karte bestellung">
  {#if daten && !daten.bereit}
    <p>{daten.hinweis}</p>
  {:else if daten}
    <!-- Die Reihenfolge der Felder ist die der Glieder im Optionscode
         (`wortlaut/laeufe.optionscode`). -->
    <div class="wahlen">
      <fieldset>
        <legend>Grundmodell</legend>
        {#each daten.grundmodelle as wahl (wahl.schluessel)}
          <label class="option">
            <input
              type="radio"
              bind:group={grundmodell}
              value={wahl.schluessel === daten.basismodell ? '' : wahl.schluessel}
            />
            {@render option(wahl)}
          </label>
        {/each}
      </fieldset>

      <fieldset>
        <legend>Methode</legend>
        {#each daten.methoden as wahl (wahl.schluessel)}
          {@const geht = erlaubteMethoden.includes(wahl.schluessel)}
          <label class="option" class:nichtmoeglich={!geht}>
            <input
              type="radio"
              bind:group={methode}
              value={wahl.schluessel}
              disabled={!geht}
            />
            {@render option(
              geht
                ? wahl
                : { ...wahl, erklaerung: `Mit ${gewaehltesGrundmodell?.name} nicht möglich (GPU-Speicher).` },
            )}
          </label>
        {/each}
      </fieldset>

      <fieldset>
        <legend>Datensatz</legend>
        {#each daten.datensaetze as wahl (wahl.schluessel)}
          <label class="option">
            <input type="radio" bind:group={datensatz} value={wahl.schluessel} />
            {@render option(wahl)}
          </label>
        {/each}
      </fieldset>

      <fieldset>
        <legend>Epochen</legend>
        {#each daten.dauern as wahl (wahl.schluessel)}
          <label class="option">
            <input type="radio" bind:group={dauer} value={wahl.schluessel} />
            {@render option(wahl)}
          </label>
        {/each}
      </fieldset>

      <!-- Online, je Durchgang neu gewürfelt - anders als „Datensatz", der
           abgelegte Fassungen als eigene Proben hinzunimmt. -->
      <fieldset>
        <legend>Augmentierung</legend>
        {#each daten.augmentierungen as wahl (wahl.schluessel)}
          <label class="option">
            <input type="radio" bind:group={augmentierung} value={wahl.schluessel} />
            {@render option(wahl)}
          </label>
        {/each}
      </fieldset>

      <fieldset>
        <legend>Tempo</legend>
        {#each daten.tempi as wahl (wahl.schluessel)}
          <label class="option">
            <input type="radio" bind:group={tempowahl} value={wahl.schluessel} />
            {@render option(wahl)}
          </label>
        {/each}
      </fieldset>

      <fieldset>
        <legend>Abschluss</legend>
        {#each daten.abschluesse as wahl (wahl.schluessel)}
          <label class="option">
            <input type="radio" bind:group={abschluss} value={wahl.schluessel} />
            {@render option(wahl)}
          </label>
        {/each}
      </fieldset>
    </div>

    {#if daten.schluessel_noetig}
      <!-- Ein Lauf belegt die Karte für Stunden, und das soll nicht jeder
           anstoßen können, der einen Aufnahmelink hat. -->
      <label class="schluessel">
        <span class="gedaempft">Trainerschlüssel</span>
        <input type="password" bind:value={schluessel} autocomplete="off" />
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
      {#if gerechnetGenau.has(bestellschluessel)}
        <span class="gedaempft">Schon gerechnet.</span>
      {/if}
    </div>

    {#if daten.aufnahmen_neu > 0 && daten.laeufe.some((lauf) => lauf.status === 'fertig')}
      <!-- Kein Knopf, der von selbst drückt: Ein Lauf belegt die Karte und
           friert einen Stand des Korpus ein; von allein angestoßen wüsste
           hinterher niemand, welche Aufnahmen in welchem Modell stecken. -->
      <p class="neu">
        <strong>{daten.aufnahmen_neu}</strong>
        {daten.aufnahmen_neu === 1 ? 'neue Aufnahme' : 'neue Aufnahmen'} seit dem letzten fertigen
        Lauf ({daten.aufnahmen_jetzt} insgesamt).
      </p>
    {/if}

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

<style>
  /* Der Titel ist der Weg in die Einzelansicht. Er soll aussehen wie eine
     Überschrift und sich anfassen lassen wie ein Link - unterstrichen erst
     beim Zeigen, damit die Liste nicht wie ein Linkverzeichnis aussieht. */
  .titel {
    color: inherit;
    text-decoration: none;
  }

  .titel:hover,
  .titel:focus-visible {
    text-decoration: underline;
  }

  .titel {
    font-family: ui-monospace, Menlo, Consolas, monospace;
  }

  /* Die Kurzkennung: klein, einfarbig, monospace - sie soll gefunden und
     verglichen werden, nicht gelesen. */
  .kennung {
    font-size: 0.8em;
    padding: 0.05em 0.35em;
    border: 1px solid var(--rand);
    border-radius: 3px;
    color: var(--gedaempft);
    margin-right: 0.35em;
    white-space: nowrap;
  }

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

  /* Das Glied dieser Wahl im Optionscode. */
  .glied {
    margin-left: 0.35em;
    padding: 0 0.3em;
    border: 1px solid var(--akzent);
    border-radius: 3px;
    color: var(--akzent);
    font-size: 0.8em;
    white-space: nowrap;
  }

  /* Nicht versteckt, sondern abgeblendet: Dass volles Training mit `medium`
     nicht geht, ist eine Auskunft. Eine Wahl, die spurlos verschwindet,
     hinterlässt die Frage, ob man sie sich eingebildet hat. */
  .option.nichtmoeglich {
    cursor: default;
    opacity: 0.55;
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
