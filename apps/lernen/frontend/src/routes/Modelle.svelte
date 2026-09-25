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
  import { ANZEIGE_GEBIET } from '$ui/sprache';
  import { zeitpunkt } from '$ui/zeit';
  import { onMount } from 'svelte';
  import {
    diktatmodell as ladeDiktatmodell,
    gibFrei,
    modelle as ladeModelle,
    type Diktatmodell,
    type Intervall,
    type Mass,
    type Modell,
    type Modelluebersicht,
    type Unterschied,
  } from '../lib/api';
  import { LAUF_ROUTE } from '../lib/zustand.svelte';

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

  /**
   * Ob und wie ein Vertrauensbereich neben jede Zahl tritt.
   *
   * **Warum das abschaltbar ist und abgeschaltet anfängt.** Diese Tabelle ist
   * das Laborbuch dieses Projekts: Was hier steht, wird mit dem verglichen, was
   * vor Monaten hier stand. Eine Ansicht, die ihre Zahlen von sich aus anders
   * rechnet, macht jeden solchen Vergleich zunichte. Also ändert sie nichts -
   * `aus` ist die Tabelle von gestern, Zeichen für Zeichen -, und wer die
   * Streuung sehen will, bestellt sie.
   *
   * **Warum zwei Arten zur Wahl stehen.** `aufnahme` zieht blockweise: Die vier
   * Fassungen einer Aufnahme sind vier Messungen an einem Gegenstand und
   * gehören zusammen gezogen. Das ist die richtige Wahl. `einheit` zieht naiv
   * je Messung und ergibt einen etwa halb so breiten Bereich - falsch, aber das
   * in der Literatur übliche Verfahren, und ohne es wären die Zahlen hier mit
   * keiner Veröffentlichung vergleichbar.
   */
  let sicherheit = $state('aus');
  /** Gegen welches Modell gepaart verglichen wird; leer heißt: gegen keines. */
  let gegen = $state('');

  /**
   * Wie ein Modell in einer Auswahl heißt.
   *
   * Ein Stand trägt hier seine Kurzkennung und nicht seinen Optionscode: Zwei
   * Läufe mit denselben Optionen haben denselben Code, aber nie dieselbe
   * Kennung. Ein Grundmodell heißt ohnehin kurz und hat keine Kennung.
   */
  const kurz = (eintrag: Modell) => eintrag.kennung ?? eintrag.name;

  const masse = $derived(uebersicht?.masse ?? []);

  const fassungen = $derived(uebersicht?.fassungen ?? []);
  const gewaehlteFassung = $derived(fassungen.find((f) => f.schluessel === fassung));

  function wert(modell: Modell, mass: string): number | null {
    const werte = modell.werte[fassung];
    return werte && werte[mass] !== undefined ? werte[mass] : null;
  }

  function bereich(modell: Modell, mass: string): Intervall | null {
    return modell.intervalle?.[fassung]?.[mass] ?? null;
  }

  function abstand(modell: Modell, mass: string): Unterschied | null {
    return modell.unterschied?.[fassung]?.[mass] ?? null;
  }

  /** `0,003` statt `0.003` - und unterhalb der Auflösung ehrlich als „<".  */
  function pWert(p: number): string {
    return p < 0.001 ? '< 0,001' : p.toLocaleString(ANZEIGE_GEBIET, { maximumFractionDigits: 3 });
  }

  /** Deutsche Schreibweise, feste Stellenzahl - sonst springen die Spalten. */
  function zahl(roh: number, mass: Mass): string {
    return (
      roh.toLocaleString(ANZEIGE_GEBIET, {
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

  /**
   * Ob eine Spalte überhaupt verglichen werden darf.
   *
   * Alle dürfen es - außer der Rechenzeit, und die nur dann, wenn jede Zeile
   * dasselbe Rechenwerk nennt. Sie hängt an der Maschine und nicht am Modell:
   * Dasselbe whisper-small braucht auf einem Prozessor das Zehn- bis
   * Zwanzigfache dessen, was es auf einer Karte braucht. Eine Bestmarke über
   * zwei Maschinen hinweg wäre keine Auskunft, sondern eine Falle.
   */
  function vergleichbar(mass: Mass): boolean {
    return mass.schluessel !== 'rechenzeit_s' || (uebersicht?.zeit_vergleichbar ?? false);
  }

  /** Der beste Wert einer Spalte - oder `null`, wenn niemand ihn gemessen hat. */
  function bester(mass: Mass): number | null {
    const werte = (uebersicht?.modelle ?? [])
      .map((modell) => wert(modell, mass.schluessel))
      .filter((eintrag): eintrag is number => eintrag !== null);
    if (!werte.length || !vergleichbar(mass)) return null;
    return mass.hoch_ist_gut ? Math.max(...werte) : Math.min(...werte);
  }

  /**
   * Ob der Vorsprung des besten Wertes vor dem zweitbesten überhaupt einer ist.
   *
   * `null`, solange keine Bereiche angefordert sind - dann bleibt die
   * Hervorhebung, was sie immer war. Sonst: überlappen die beiden Bereiche,
   * ist der Vorsprung **nicht** belegt, und die Spalte sagt das.
   *
   * Der Test über zwei einzelne Bereiche ist dabei die vorsichtige Variante:
   * Überlappen sie nicht, ist der Unterschied sicher; überlappen sie, kann er
   * trotzdem belastbar sein. Die schärfere Auskunft gibt der gepaarte
   * Vergleich über „Gegen" - deshalb steht er in der Erklärung daneben.
   */
  function vorsprungBelegt(mass: Mass): boolean | null {
    if (sicherheit === 'aus' || !vergleichbar(mass)) return null;
    const bereiche = (uebersicht?.modelle ?? [])
      .map((modell) => ({ roh: wert(modell, mass.schluessel), um: bereich(modell, mass.schluessel) }))
      .filter((eintrag): eintrag is { roh: number; um: Intervall } =>
        eintrag.roh !== null && eintrag.um !== null,
      )
      .sort((a, b) => (mass.hoch_ist_gut ? b.roh - a.roh : a.roh - b.roh));
    if (bereiche.length < 2) return null;
    const [erster, zweiter] = bereiche;
    return !(erster.um.unten <= zweiter.um.oben && zweiter.um.unten <= erster.um.oben);
  }

  const einheiten = $derived(
    Math.max(0, ...(uebersicht?.modelle ?? []).map((modell) => modell.einheiten[fassung] ?? 0)),
  );

  /**
   * Die Tabellenzeile zu dem Modell, das „schreiben" gerade geladen hat.
   *
   * Damit stehen in der Karte oben und in der Zeile unten dieselben Zahlen aus
   * derselben Rechnung. Vorher nannte die Karte die Wortfehlerrate aus dem
   * Manifest des Standes - das Mittel über die Testeinheiten *seines* Laufs -,
   * die Tabelle dagegen das Mittel über die Einheiten, die **alle** Modelle
   * gemessen haben. Beide Zahlen waren richtig, nebeneinander waren sie ein
   * Rätsel.
   *
   * `undefined` ist möglich und kein Fehler: `WORTLAUT_MODELL_REF` kann auf
   * einen Stand zeigen, der hier nicht zur Wahl steht, und ein gelöschter
   * steht ebenfalls nicht mehr in der Liste. Dann bleibt die Beschriftung von
   * „schreiben" stehen, und Zahlen gibt es eben keine.
   */
  const laufend = $derived(
    diktat ? (uebersicht?.modelle ?? []).find((modell) => modell.ref === diktat!.ref) : undefined,
  );

  async function hole() {
    try {
      uebersicht = await ladeModelle(sicherheit, gegen);
      fehler = '';
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      geladen = true;
    }
    diktat = await ladeDiktatmodell();
  }

  /**
   * Ein Modell freigeben - nach einer Rückfrage, die es beim Namen nennt.
   *
   * Die Rückfrage ist nicht Zierde. Diese Liste enthält Zeilen, die einander
   * ähneln - sechs Achsen, und zwei Läufe können sich in genau einer
   * unterscheiden. Ein Klick ändert, womit ein Mensch ab sofort diktiert;
   * dass dabei genannt wird, **welches** Modell gemeint ist, ist die letzte
   * Stelle, an der ein Vergreifen auffällt.
   *
   * Genannt wird beides: was gilt und was gelten soll. „Statt" ist die
   * Information, die fehlt, wenn man nur das Ziel liest.
   */
  async function freigeben(ref: string) {
    const neu = uebersicht?.modelle.find((m) => m.ref === ref);
    const alt = uebersicht?.modelle.find((m) => m.freigegeben);
    const zeilen = [
      `„${neu?.name ?? ref}" für „schreiben" freigeben?`,
      '',
      neu?.herkunft ?? '',
      '',
      alt ? `Statt bisher: „${alt.name}" (${alt.herkunft})` : 'Bisher gilt das Grundmodell.',
      '',
      'Ab sofort wird damit diktiert.',
    ];
    if (!confirm(zeilen.join('\n'))) return;

    arbeitet = ref;
    try {
      uebersicht = await gibFrei(ref, sicherheit, gegen);
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

  onMount(hole);
</script>

<h2>Modelle</h2>
<p class="gedaempft">
  Was diesem Menschen zuhören kann - die selbst trainierten Stände und die unveränderten
  Grundmodelle, an denselben Aufnahmen gemessen. Freigegeben ist höchstens eines; mit dem
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
      <p class="beschriftung">{laufend?.name ?? diktat.beschriftung}</p>
      <p class="gedaempft klein">{laufend?.herkunft ?? ''}</p>

      {#if laufend}
        <!-- Dieselben Zahlen wie in der Zeile unten, aus derselben Rechnung
             und über dieselben Messeinheiten - sie folgen deshalb auch der
             Fassungswahl. Zwei Quellen für dieselbe Auskunft wären zwei
             Gelegenheiten, verschiedene zu geben. -->
        <p class="kennzahlen">
          {#each masse as mass (mass.schluessel)}
            {@const roh = wert(laufend, mass.schluessel)}
            <span class="kennzahl">
              <span class="gedaempft">{mass.kurz}</span>
              <strong>{roh === null ? '–' : zahl(roh, mass)}</strong>
            </span>
          {/each}
        </p>
        <p class="gedaempft klein">
          Gemessen wie in der Tabelle unten - {gewaehlteFassung?.name ?? 'alle Fassungen'},
          {laufend.einheiten[fassung] ?? 0}
          {(laufend.einheiten[fassung] ?? 0) === 1 ? 'Messung' : 'Messungen'}.
        </p>
      {/if}

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
    <!-- Die beiden neuen Wahlmöglichkeiten. Sie ändern nichts an den Zahlen
         darüber - sie legen eine zweite Zeile darunter. „Aus" ist die Vorgabe
         und ergibt die Tabelle, die hier immer stand. -->
    <label class="fassungswahl">
      <span>Sicherheit</span>
      <select bind:value={sicherheit} onchange={hole}>
        <option value="aus">aus</option>
        <option value="aufnahme">je Aufnahme</option>
        <option value="einheit">je Messung</option>
      </select>
    </label>
    {#if sicherheit !== 'aus'}
      <label class="fassungswahl">
        <span>Gegen</span>
        <select bind:value={gegen} onchange={hole}>
          <option value="">keines</option>
          {#each uebersicht.modelle as eintrag (eintrag.ref)}
            <option value={eintrag.ref}>{kurz(eintrag)}</option>
          {/each}
        </select>
      </label>
    {/if}
  </div>

  {#if gewaehlteFassung}
    <p class="gedaempft klein hinweiszeile">{gewaehlteFassung.erklaerung}</p>
  {/if}

  {#if sicherheit !== 'aus'}
    <p class="gedaempft klein hinweiszeile">
      95-%-Bereich aus 2000 Ziehungen, blockweise über
      {sicherheit === 'aufnahme' ? 'die Aufnahmen' : 'die einzelnen Messungen'}.
      {sicherheit === 'aufnahme'
        ? 'Die Fassungen einer Aufnahme sind nicht unabhängig - deshalb diese Blockart.'
        : 'Üblich in der Literatur, hier zu schmal: Die Fassungen einer Aufnahme sind nicht unabhängig.'}
      {#if uebersicht.vergleich_mit}
        {@const verglichen = uebersicht.modelle.find(
          (m) => m.ref === uebersicht!.vergleich_mit,
        )}
        Statt des Bereichs der gepaarte Abstand zu „{verglichen
          ? kurz(verglichen)
          : uebersicht.vergleich_mit}" - schärfer, weil auf denselben Aufnahmen.
      {/if}
    </p>
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
              {#if vorsprungBelegt(mass) === false}
                <!-- Farbe allein wäre keine Auskunft, also ein Zeichen mit
                     Erklärung: Der beste Wert dieser Spalte hebt sich nicht
                     vom zweitbesten ab. -->
                <span
                  class="unsicher"
                  title="Die Bereiche des besten und des zweitbesten Wertes überlappen - der Vorsprung ist nicht belegt. Der gepaarte Vergleich über „Gegen“ kann trotzdem einen zeigen; er ist schärfer."
                  aria-label="Vorsprung nicht belegt">≈</span
                >
              {/if}
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
                {#if modell.kennung}<code class="kennung">{modell.kennung}</code>{/if}
                <!-- Der Name **ist** der Weg in die Einzelansicht: Steckbrief,
                     Lernkurven, Protokoll. Ein Link „Details" darunter war eine
                     zweite Beschriftung für dasselbe Ziel; wer eine Zahl in
                     dieser Tafel nicht glaubt, klickt auf das Modell.

                     Nur bei eigenen Ständen: Ein Grundmodell hat keinen Lauf,
                     und ein Link ins Leere wäre schlimmer als keiner. -->
                {#if modell.job_id}
                  <a class="name titel optionscode" href="#{LAUF_ROUTE}{modell.job_id}"
                    >{modell.name}</a
                  >
                {:else}
                  <span class="name">{modell.name}</span>
                {/if}
                {#if modell.freigegeben}
                  <span class="abzeichen">freigegeben</span>
                {/if}
              </span>
              <span class="gedaempft klein">
                {modell.herkunft}{#if modell.erstellt} · {zeitpunkt(modell.erstellt)}{/if}
              </span>
              <!-- Steht hier und nicht in einer eigenen Spalte: Es betrifft die
                   ganze Zeile, und wer die Zahlen rechts liest, soll den Satz
                   vorher gelesen haben. -->
              {#if modell.vorbehalt}
                <span class="vorbehalt klein">{modell.vorbehalt}</span>
              {/if}
            </th>

            {#each masse as mass (mass.schluessel)}
              {@const roh = wert(modell, mass.schluessel)}
              {@const beste = bester(mass)}
              <td class="zahlenspalte">
                {#if roh === null}
                  <span class="gedaempft" title="Auf diesen Aufnahmen nicht gemessen.">–</span>
                {:else}
                  <span
                    class:beste={roh === beste}
                    title={roh === beste ? 'Bester Wert dieser Spalte' : undefined}
                  >
                    {zahl(roh, mass)}
                  </span>
                  <!-- Nur an der Rechenzeit und nur, wenn sie nicht vergleichbar
                       ist: Dann sagt die Marke, worauf sie entstand, statt die
                       Zahl kommentarlos neben eine von einer anderen Maschine zu
                       stellen. -->
                  {#if mass.schluessel === 'rechenzeit_s' && !vergleichbar(mass)}
                    <span class="werk" title="Gemessen auf {modell.rechenwerk || 'unbekanntem Rechenwerk'}">
                      {modell.rechenwerk ? modell.rechenwerk.split('/')[0] : '?'}
                    </span>
                  {/if}
                  <!-- Die zweite Zeile: entweder der Bereich um diese Zahl oder,
                       wenn ein Vergleichsmodell gewählt ist, der gepaarte
                       Abstand zu ihm. Beides zugleich wäre in einer Tabellen-
                       zelle nicht mehr zu lesen. -->
                  {@const um = abstand(modell, mass.schluessel)}
                  {@const drum = bereich(modell, mass.schluessel)}
                  {#if um}
                    <span
                      class="streuung"
                      class:belegt={um.belegt}
                      title="Gepaarter Abstand auf denselben {um.einheiten} Messungen aus {um.bloecke} Aufnahmen: {zahl(um.differenz, mass)} (95 %: {zahl(um.unten, mass)} bis {zahl(um.oben, mass)}), p = {pWert(um.p)}. {um.belegt ? 'Der Bereich schließt die Null aus - der Abstand ist belegt.' : 'Der Bereich enthält die Null - der Abstand kann Zufall sein.'} Verfahren: {um.marke}"
                    >
                      {um.differenz >= 0 ? '+' : '−'}{zahl(Math.abs(um.differenz), mass)} · p {pWert(um.p)}
                    </span>
                  {:else if drum}
                    <span
                      class="streuung"
                      title="95-%-Bereich aus {drum.einheiten} Messungen über {drum.bloecke} Aufnahmen; Standardfehler {drum.streuung}. Verfahren: {drum.marke}"
                    >
                      {zahl(drum.unten, mass)} – {zahl(drum.oben, mass)}
                    </span>
                  {/if}
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

  {#if !uebersicht.zeit_vergleichbar && uebersicht.modelle.some((m) => m.werte[fassung])}
    <p class="warnung">
      Rechenzeiten von verschiedenen Rechenwerken - nicht vergleichbar (Prozessor: zehn- bis
      zwanzigfach). Die Marke steht an jeder Zahl. Ein neuer Auswertungslauf in „hören“ misst
      alles auf demselben nach.
    </p>
  {/if}

  <p class="gedaempft klein">
    Es gilt höchstens ein Modell, und sofort. Nach einem Wechsel dauert das erste Diktat länger -
    das Modell wird geladen.
  </p>
  <p class="gedaempft klein">
    Zahlen: Grundmodelle aus der Auswertung in „hören", eigene Stände aus der Bewertung ihres
    Laufs. Je Aufnahme aufgeschlüsselt jeweils dort.
  </p>
{/if}

<style>
  /* Wie unter „Training": aussehen wie eine Überschrift, sich anfassen lassen
     wie ein Link. */
  .titel {
    color: inherit;
    text-decoration: none;
  }

  .titel:hover,
  .titel:focus-visible {
    text-decoration: underline;
  }

  /* Dieselbe Kennung wie in „Training" und „schreiben" - und deshalb auch
     dieselbe Gestalt. */
  .vorbehalt {
    display: block;
    margin-top: 0.25rem;
    color: var(--warnung, #8a4b08);
  }

  .kennung {
    font-size: 0.8em;
    padding: 0.05em 0.35em;
    border: 1px solid var(--rand);
    border-radius: 3px;
    color: var(--gedaempft);
    white-space: nowrap;
  }

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
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
  }

  /* Die Zahlen der laufenden Zeile, als Reihe kleiner Paare: Maß darüber,
     Wert darunter. Auf einem schmalen Gerät bricht die Reihe um, statt die
     Karte breiter zu machen. */
  .kennzahlen {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem 1.6rem;
    margin: 0.7rem 0 0.2rem;
    font-variant-numeric: tabular-nums;
  }

  .kennzahl {
    display: flex;
    flex-direction: column;
    line-height: 1.25;
  }

  .kennzahl .gedaempft {
    font-size: 0.78rem;
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

  .optionscode {
    font-family: ui-monospace, Menlo, Consolas, monospace;
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

  /* Die Maschine hinter einer Rechenzeit, wenn sie nicht zu den übrigen passt.
     Klein und blass: Sie ist ein Vorbehalt zur Zahl, nicht ihr Gegenstand. */
  .werk {
    margin-left: 0.35rem;
    padding: 0.02rem 0.3rem;
    border: 1px solid var(--rand);
    border-radius: 0.25rem;
    font-size: 0.7rem;
    color: var(--gedaempft);
  }

  /* Die zweite Zeile in einer Zahlenzelle: der Bereich um die Zahl oder der
     gepaarte Abstand. Eine eigene Zeile und kein Zusatz in derselben - sonst
     liest sich keine der beiden Zahlen mehr als Zahl. Blass, weil sie die
     darüber begleitet und nicht ersetzt. */
  .streuung {
    display: block;
    margin-top: 0.1rem;
    font-size: 0.7rem;
    font-variant-numeric: tabular-nums;
    color: var(--gedaempft);
    white-space: nowrap;
  }

  /* Ein Abstand, dessen Bereich die Null ausschließt. Nicht grün oder rot:
     Belegt heißt nicht gut, sondern nur „nicht bloß Zufall" - ob es ein
     Gewinn oder ein Verlust ist, steht im Vorzeichen daneben. */
  .streuung.belegt {
    color: var(--text);
    font-weight: 600;
  }

  /* Die Marke am Spaltenkopf, wenn der beste Wert sich nicht vom zweitbesten
     abhebt. */
  .unsicher {
    margin-left: 0.25rem;
    color: var(--gedaempft);
    cursor: help;
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
