<script lang="ts">
  /**
   * Editieren: eine Aufnahme kürzen, in zwei teilen, ihren Text berichtigen.
   *
   * Erreichbar aus „Meine Daten", über den Stift an einer aufgeklappten
   * Aufnahme, und nur von dort. Gezeigt wird genau diese eine Aufnahme: der
   * Lautstärkeverlauf mit zwei Linien für Anfang und Ende, darunter ihr Text
   * zum Mitlesen und das Feld, in dem er berichtigt wird.
   *
   * **Beim Öffnen ist nichts geändert.** Die Linien stehen ganz außen, der
   * Teilen-Modus ist aus, „Speichern" gesperrt. Jede Änderung - Linien, Text,
   * Teilen - schaltet es frei; sein Tooltip und die Rückfrage sagen, was sich
   * beim Speichern ändert. „Auto" setzt die Linien an die Grenzen der Stimme, nach
   * derselben Rechnung, mit der der Server Randstille meldet
   * (`audio.stimmgrenzen`).
   *
   * **Teilen** ist ein Schalter. Gedrückt steht eine dritte Linie in der
   * längsten Pause der Mitte, der Text bekommt anklickbare Lücken und das
   * Feld wird zu zweien; die Textteilung folgt der Linie, bis jemand eine
   * Lücke anklickt, und die Felder folgen der Textteilung, bis jemand darin
   * schreibt. Wieder gelöst, verschmelzen beide Felder zu einem - was darin
   * geändert wurde, bleibt.
   *
   * **Bis zum Speichern hat nichts eine Folge.** Abgespielt wird aus der
   * geladenen Datei (`$ui/ausschnitt`), ohne vorläufige Dateien auf dem
   * Server. Gespeichert wird in einem Schritt (`api/zuschnitt.py`,
   * `speichern`), nach einer Rückfrage; danach lässt sich nur weiter kürzen,
   * teilen und berichtigen. Wer mit ungespeicherten Änderungen geht, wird
   * gefragt.
   *
   * **Oben die Lage**: neben „Zurück" die Stelle in der Liste von „Meine
   * Daten", wie sie beim Öffnen sortiert war (`lib/rueckkehr`), mit Knöpfen
   * zur vorigen und nächsten Aufnahme darin; in der Karte Datum der Aufnahme
   * und der letzten Änderung, rechts die Genauigkeit des Diktiermodells wie
   * in der Liste. Mit ungespeicherten Änderungen fragt das Weiterblättern wie
   * „Abbrechen".
   */
  import { onMount } from 'svelte';
  import { erklaert } from '$ui/erklaerung';
  import { fehlertext } from '$ui/api';
  import Pegelverlauf from '$ui/Pegelverlauf.svelte';
  import Guete from '../lib/Guete.svelte';
  import Rueckfrage from '$ui/Rueckfrage.svelte';
  import { spiele, stelle, stoppe, vergiss } from '$ui/ausschnitt';
  import { bewache } from '$ui/route';
  import { tag, tagUndZeit } from '$ui/zeit';
  import { EDITIEREN_ROUTE, MEINE_DATEN_PFAD } from '$ui/apps';
  import {
    ARTNAMEN,
    zuschnittEine,
    zuschnittOriginal,
    zuschnittSpeichern,
    type Zuschnittaufnahme,
  } from '../lib/api';
  import { gehZu, lage } from '../lib/zustand.svelte';
  import { reihenfolge, wechsleZu, type Reihenfolge } from '../lib/rueckkehr';

  const kennung = $derived(lage.route.slice(EDITIEREN_ROUTE.length));

  let aufnahme = $state<Zuschnittaufnahme | null>(null);
  let start = $state(0);
  let ende = $state(0);
  let teilen = $state(false);
  let teilung = $state(0);
  // Der eine Text außerhalb des Teilen-Modus.
  let text = $state('');
  // Im Teilen-Modus: die Wörter, aus denen die beiden Felder kommen - der Text
  // beim Einschalten -, vor dem wievielten Teil B beginnt, und die Felder.
  let basis = $state<string[]>([]);
  let wortgrenze = $state(1);
  let vonHand = $state(false);
  let textA = $state('');
  let textB = $state('');
  let bearbeitet = $state(false);

  let fehler = $state('');
  let meldung = $state('');
  let spielt = $state<'' | 'ganz' | 'ausschnitt' | 'a' | 'b'>('');
  let cursor = $state<number | null>(null);
  let laeuft = $state(false);
  // Wonach gerade gefragt wird.
  let frage = $state<'' | 'speichern' | 'verlassen'>('');
  // Wohin nach einem bestätigten Verlassen.
  let ziel = MEINE_DATEN_PFAD;
  // Gesetzt, wenn das Verlassen bestätigt ist - dann fragt die Wache nicht mehr.
  let freigegeben = false;
  let datei: Blob | null = null;
  // Mit welcher Aufnahme der Editor aufging.
  let zuerst = '';
  // Die Liste aus „Meine Daten", eingefroren beim Öffnen.
  const folge: Reihenfolge | null = reihenfolge();

  const stelleInFolge = $derived(
    folge ? folge.eintraege.findIndex((eintrag) => eintrag.id === kennung) : -1,
  );
  /** Die nächste bearbeitbare Aufnahme in dieser Richtung - verworfene haben kein Audio. */
  function nachbar(schritt: -1 | 1): string | null {
    if (!folge || stelleInFolge < 0) return null;
    const eintraege = folge.eintraege;
    for (let nummer = stelleInFolge + schritt; eintraege[nummer]; nummer += schritt) {
      if (eintraege[nummer].status === 'ok') return eintraege[nummer].id;
    }
    return null;
  }
  const vorige = $derived(nachbar(-1));
  const naechste = $derived(nachbar(1));

  const glatt = (wert: string) => wert.split(/\s+/).filter(Boolean).join(' ');

  const gekuerzt = $derived(aufnahme !== null && (start > 0 || ende < aufnahme.dauer_s));
  const neuerText = $derived(
    aufnahme !== null &&
      (teilen ? glatt(`${textA} ${textB}`) : glatt(text)) !== glatt(aufnahme.text),
  );
  const pruefen = $derived(aufnahme !== null && aufnahme.korrektur && !aufnahme.validiert);
  const geaendert = $derived(gekuerzt || neuerText || teilen);

  /** Was das Speichern ändert, in kurzen Worten - für Knopf, Warnzeile und Rückfrage. */
  const aenderungen = $derived(
    [
      gekuerzt ? 'Audio gekürzt' : '',
      teilen ? 'in zwei Aufnahmen geteilt' : '',
      neuerText ? 'Text geändert' : '',
      pruefen ? 'Text als geprüft übernommen' : '',
    ].filter(Boolean),
  );
  const fertig = $derived(teilen ? glatt(textA) !== '' && glatt(textB) !== '' : glatt(text) !== '');
  const speicherbar = $derived((geaendert || pruefen) && fertig && !laeuft);

  /**
   * Wo die Teilung vorgeschlagen wird: in der Mitte der längsten Pause im
   * mittleren Bereich - dort, wo zwei Sätze aneinanderstoßen. Gibt es keine,
   * in der Mitte.
   */
  function pausenmitte(eine: Zuschnittaufnahme, von: number, bis: number): number {
    const fenster = eine.fenster_s;
    const rand = (bis - von) / 4;
    const erstes = Math.ceil((von + rand) / fenster);
    const letztes = Math.floor((bis - rand) / fenster);
    let beste = { laenge: 0, mitte: (von + bis) / 2 };
    let anfang = -1;
    for (let nummer = erstes; nummer <= letztes + 1; nummer++) {
      const leise = nummer <= letztes && (eine.verlauf[nummer] ?? 0) < eine.schwelle;
      if (leise && anfang < 0) anfang = nummer;
      if (!leise && anfang >= 0) {
        if (nummer - anfang > beste.laenge) {
          beste = { laenge: nummer - anfang, mitte: ((anfang + nummer) / 2) * fenster };
        }
        anfang = -1;
      }
    }
    return beste.mitte;
  }

  /** Die Wortgrenze, deren Anteil am Text dem Anteil der Zeit am nächsten kommt. */
  function passendeGrenze(): number {
    if (ende <= start) return 0;
    const anteil = (teilung - start) / (ende - start);
    const gesamt = Math.max(basis.join(' ').length, 1);
    let beste = 1;
    let abstand = Infinity;
    for (let grenze = 1; grenze < basis.length; grenze++) {
      const neu = Math.abs(basis.slice(0, grenze).join(' ').length / gesamt - anteil);
      if (neu < abstand) {
        abstand = neu;
        beste = grenze;
      }
    }
    return beste;
  }

  $effect(() => {
    // Die Textteilung läuft mit der Linie mit, solange niemand sie selbst gesetzt hat.
    if (teilen && !vonHand && aufnahme) wortgrenze = passendeGrenze();
  });

  $effect(() => {
    // Und die Felder folgen der Textteilung, solange niemand darin schreibt.
    if (!teilen || bearbeitet) return;
    textA = basis.slice(0, wortgrenze).join(' ');
    textB = basis.slice(wortgrenze).join(' ');
  });

  async function lade(id: string) {
    fehler = '';
    freigegeben = false;
    // Geblättert: Nach der Rückkehr steht in „Meine Daten" diese Karte offen.
    if (!zuerst) zuerst = id;
    else if (id !== zuerst) wechsleZu(id);
    halte();
    vergiss();
    datei = null;
    aufnahme = null;
    // Ob der Bearbeitungsschlüssel gilt, sagt der Server; gelesen hier, damit
    // die Ansicht neu lädt, sobald er unter „Zugangsdaten" eingetragen ist.
    if (lage.bearbeiten === 'unbekannt') return;
    if (lage.bearbeiten !== 'gilt') {
      fehler = 'Zum Editieren braucht es den Bearbeitungsschlüssel - einzutragen unter „Zugangsdaten“.';
      return;
    }
    try {
      const eine = await zuschnittEine(id);
      start = 0;
      ende = eine.dauer_s;
      teilen = false;
      text = eine.text;
      bearbeitet = false;
      vonHand = false;
      aufnahme = eine;
    } catch (ursache) {
      fehler = fehlertext(ursache);
    }
  }

  /** Anfang und Ende an die Grenzen der Stimme - und die Teilung neu in die Mitte. */
  function auto() {
    if (!aufnahme) return;
    start = aufnahme.vorschlag_start_s;
    ende = aufnahme.vorschlag_ende_s;
    if (teilen) teilung = pausenmitte(aufnahme, start, ende);
  }

  /** Teilen ein und aus. Aus verschmelzen die beiden Felder zu einem. */
  function schalteTeilen() {
    if (!aufnahme) return;
    halte();
    if (teilen) {
      text = glatt(`${textA} ${textB}`);
      teilen = false;
      return;
    }
    basis = glatt(text).split(' ').filter(Boolean);
    teilung = pausenmitte(aufnahme, start, ende);
    vonHand = false;
    bearbeitet = false;
    teilen = true;
  }

  /** Eine Lücke angeklickt: Die Felder kommen wieder aus dem Text, an dieser Stelle geteilt. */
  function setzeGrenze(grenze: number) {
    wortgrenze = Math.min(Math.max(grenze, 0), basis.length);
    vonHand = true;
    bearbeitet = false;
  }

  function halte() {
    stoppe();
    spielt = '';
    cursor = null;
  }

  /** Abspielen - das Ganze, den Ausschnitt oder einen der Teile. Ein zweiter Druck hält an. */
  async function hoere(welches: 'ganz' | 'ausschnitt' | 'a' | 'b') {
    if (!aufnahme) return;
    if (spielt === welches) {
      halte();
      return;
    }
    const [von, bis] = {
      ganz: [0, aufnahme.dauer_s],
      ausschnitt: [start, ende],
      a: [start, teilung],
      b: [teilung, ende],
    }[welches];
    try {
      spielt = welches;
      datei ??= await zuschnittOriginal(aufnahme.id, aufnahme.version);
      await spiele(`${aufnahme.id}@${aufnahme.version}`, datei, von, bis, () => {
        if (spielt === welches) halte();
      });
      laufeMit();
    } catch (ursache) {
      halte();
      fehler = fehlertext(ursache);
    }
  }

  /** Der Cursor folgt dem Abspielen, Bild für Bild. */
  function laufeMit() {
    const jetzt = stelle();
    cursor = spielt ? jetzt : null;
    if (spielt && jetzt !== null) requestAnimationFrame(laufeMit);
  }

  /** Leertaste und Tippen auf die Kurve: was zwischen den Linien liegt, an oder aus. */
  function umschalten() {
    if (spielt) halte();
    else hoere(gekuerzt ? 'ausschnitt' : 'ganz');
  }

  function taste(ereignis: KeyboardEvent) {
    if (ereignis.code !== 'Space' || frage) return;
    const ort = ereignis.target as HTMLElement | null;
    if (ort?.closest('input, textarea, select, button, [contenteditable="true"]')) return;
    ereignis.preventDefault();
    umschalten();
  }

  async function speichern() {
    frage = '';
    if (!aufnahme || !speicherbar) return;
    const id = aufnahme.id;
    halte();
    fehler = '';
    meldung = '';
    laeuft = true;
    try {
      await zuschnittSpeichern({
        id,
        start_s: start,
        ende_s: ende,
        teilung_s: teilen ? teilung : null,
        texte: teilen ? [glatt(textA), glatt(textB)] : [glatt(text)],
      });
      if (teilen) {
        freigegeben = true;
        gehZu(MEINE_DATEN_PFAD);
        return;
      }
      await lade(id);
      meldung = 'Gespeichert.';
    } catch (ursache) {
      fehler = fehlertext(ursache);
    } finally {
      laeuft = false;
    }
  }

  /** Zurück zu „Meine Daten" - mit Rückfrage, wenn etwas verloren ginge. */
  function verlasse(wohin = MEINE_DATEN_PFAD) {
    ziel = wohin;
    if (geaendert && !freigegeben) {
      frage = 'verlassen';
      return;
    }
    freigegeben = true;
    gehZu(wohin);
  }

  function verwirf() {
    frage = '';
    freigegeben = true;
    gehZu(ziel);
  }

  // Die Teile, wie sie in der Rückfrage stehen.
  const teile = $derived([
    `A (${(teilung - start).toFixed(2)} s): ${glatt(textA)}`,
    `B (${(ende - teilung).toFixed(2)} s): ${glatt(textB)}`,
  ]);

  $effect(() => {
    if (lage.art === 'sprecher' && kennung) lade(kennung);
    return () => {
      halte();
      vergiss();
      datei = null;
    };
  });

  onMount(() => {
    // Andere Ansicht über einen Reiter oder den Zurück-Knopf: dieselbe Frage.
    bewache((wohin) => {
      if (!geaendert || freigegeben) return true;
      ziel = wohin;
      frage = 'verlassen';
      return false;
    });
    const warne = (ereignis: BeforeUnloadEvent) => {
      if (geaendert && !freigegeben) ereignis.preventDefault();
    };
    window.addEventListener('beforeunload', warne);
    window.addEventListener('keydown', taste);
    return () => {
      bewache(null);
      window.removeEventListener('beforeunload', warne);
      window.removeEventListener('keydown', taste);
    };
  });
</script>

<div class="reihe titel">
  <h2
    use:erklaert={'Die beiden Linien bestimmen, was an den Rändern bleibt; „Auto“ setzt sie an die Grenzen der Stimme. „Teilen“ legt eine dritte Linie in die längste Pause der Mitte und teilt Ton und Text in zwei Aufnahmen - die Stelle im Text lässt sich mit einem Klick auf eine Lücke setzen. Der Text darunter lässt sich berichtigen, wenn anders gesprochen wurde, als dasteht. Leertaste oder ein Tippen auf die Kurve spielt ab, was zwischen den Linien liegt. Erst „Speichern“ ändert etwas; gekürzt wird verlustfrei, und die Messwerte der Aufnahme rechnet die nächste Auswertung neu.'}
  >
    Editieren
  </h2>
  <div class="reihe rechts">
    {#if folge && stelleInFolge >= 0}
      <div class="blaettern">
        <button
          class="knopf zeichen"
          title="Vorige Aufnahme"
          aria-label="Vorige Aufnahme"
          disabled={!vorige}
          onclick={() => vorige && verlasse(`${EDITIEREN_ROUTE}${vorige}`)}
        >
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3 L5 8 L10 13" class="strich" /></svg>
        </button>
        <span class="position">{stelleInFolge + 1} / {folge.eintraege.length}</span>
        <button
          class="knopf zeichen"
          title="Nächste Aufnahme"
          aria-label="Nächste Aufnahme"
          disabled={!naechste}
          onclick={() => naechste && verlasse(`${EDITIEREN_ROUTE}${naechste}`)}
        >
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3 L11 8 L6 13" class="strich" /></svg>
        </button>
      </div>
    {/if}
    <button class="knopf" onclick={() => verlasse()}>Zurück zu „Meine Daten“</button>
  </div>
</div>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}
{#if meldung}
  <p class="gedaempft">{meldung}</p>
{/if}

{#if aufnahme}
  <div class="karte">
    <div class="reihe lage">
      <span class="gedaempft daten">
        {ARTNAMEN[aufnahme.art]} · aufgenommen {tag(aufnahme.erstellt)}
        {#if aufnahme.geaendert}· <span class="editiert">editiert</span>
          {tagUndZeit(aufnahme.geaendert)}{/if}
        · {aufnahme.dauer_s.toFixed(1)} s
      </span>
      {#if aufnahme.qualitaet !== null}
        <Guete wert={aufnahme.qualitaet} skala={aufnahme.skala} modell={aufnahme.modell} />
      {/if}
    </div>

    <div class="reihe kopf">
      <span class="wachsen"></span>
      <!-- Die Zeichen: das volle Dreieck für die ganze Aufnahme, eines zwischen
           zwei festen Grenzen für den Ausschnitt, und je eines zwischen einer
           festen und einer gestrichelten Grenze für die beiden Teile - die
           gestrichelte ist die Teilung, wie in der Kurve. -->
      <button
        class="knopf zeichen"
        title="Ganze Aufnahme anhören"
        aria-label="Ganze Aufnahme anhören"
        onclick={() => hoere('ganz')}
      >
        {#if spielt === 'ganz'}
          <svg viewBox="0 0 16 16" aria-hidden="true"
            ><rect x="3.5" y="3" width="3.5" height="10" /><rect
              x="9"
              y="3"
              width="3.5"
              height="10"
            /></svg
          >
        {:else}
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 3 L13 8 L4 13 Z" /></svg>
        {/if}
      </button>
      {#if teilen}
        <button
          class="knopf zeichen"
          title="Teil A anhören"
          aria-label="Teil A anhören"
          onclick={() => hoere('a')}
        >
          <svg viewBox="0 0 16 16" aria-hidden="true"
            ><rect x="0.5" y="2" width="1.5" height="12" class="grenze" /><rect
              x="14"
              y="2"
              width="1.5"
              height="3"
              class="grenze"
            /><rect x="14" y="6.5" width="1.5" height="3" class="grenze" /><rect
              x="14"
              y="11"
              width="1.5"
              height="3"
              class="grenze"
            />{#if spielt === 'a'}<rect x="4.5" y="4" width="2.5" height="8" /><rect
                x="9"
                y="4"
                width="2.5"
                height="8"
              />{:else}<path d="M5 4 L11.5 8 L5 12 Z" />{/if}</svg
          >
        </button>
        <button
          class="knopf zeichen"
          title="Teil B anhören"
          aria-label="Teil B anhören"
          onclick={() => hoere('b')}
        >
          <svg viewBox="0 0 16 16" aria-hidden="true"
            ><rect x="0.5" y="2" width="1.5" height="3" class="grenze" /><rect
              x="0.5"
              y="6.5"
              width="1.5"
              height="3"
              class="grenze"
            /><rect x="0.5" y="11" width="1.5" height="3" class="grenze" /><rect
              x="14"
              y="2"
              width="1.5"
              height="12"
              class="grenze"
            />{#if spielt === 'b'}<rect x="4.5" y="4" width="2.5" height="8" /><rect
                x="9"
                y="4"
                width="2.5"
                height="8"
              />{:else}<path d="M5 4 L11.5 8 L5 12 Z" />{/if}</svg
          >
        </button>
      {:else if gekuerzt}
        <button
          class="knopf zeichen"
          title="Ausschnitt anhören"
          aria-label="Ausschnitt anhören"
          onclick={() => hoere('ausschnitt')}
        >
          <svg viewBox="0 0 16 16" aria-hidden="true"
            ><rect x="0.5" y="2" width="1.5" height="12" class="grenze" /><rect
              x="14"
              y="2"
              width="1.5"
              height="12"
              class="grenze"
            />{#if spielt === 'ausschnitt'}<rect x="4.5" y="4" width="2.5" height="8" /><rect
                x="9"
                y="4"
                width="2.5"
                height="8"
              />{:else}<path d="M5 4 L11.5 8 L5 12 Z" />{/if}</svg
          >
        </button>
      {/if}
      <button
        class="knopf klein"
        title="Anfang und Ende an die Grenzen der Stimme setzen"
        onclick={auto}>Auto</button
      >
      <button
        class="knopf klein schalter"
        class:gedrueckt={teilen}
        aria-pressed={teilen}
        title={teilen ? 'Nicht teilen - die beiden Texte werden wieder einer' : 'In zwei Aufnahmen teilen'}
        onclick={schalteTeilen}>Split</button
      >
    </div>

    <Pegelverlauf
      verlauf={aufnahme.verlauf}
      fensterS={aufnahme.fenster_s}
      schwelle={aufnahme.schwelle}
      dauerS={aufnahme.dauer_s}
      bind:start
      bind:ende
      bind:teilung
      {teilen}
      {cursor}
      ontipp={umschalten}
      beschriftung="Schnitt"
    />

    {#if teilen}
      <p class="vorlage" class:bearbeitet aria-label="Text, an jeder Wortgrenze teilbar">
        {#each basis as wort, nummer (nummer)}
          {#if nummer > 0}<button
              class="luecke"
              class:gesetzt={nummer === wortgrenze}
              title="Hier teilen"
              aria-label={`Vor „${wort}“ teilen`}
              aria-pressed={nummer === wortgrenze}
              onclick={() => setzeGrenze(nummer)}
              >{nummer === wortgrenze ? '|' : '\u00a0'}</button
            >{/if}<span class:hinten={nummer >= wortgrenze}>{wort}</span>
        {/each}
      </p>
      <div class="felder">
        <label>
          <span>A</span>
          <textarea rows="2" bind:value={textA} oninput={() => (bearbeitet = true)}></textarea>
        </label>
        <label>
          <span>B</span>
          <textarea rows="2" bind:value={textB} oninput={() => (bearbeitet = true)}></textarea>
        </label>
      </div>
    {:else}
      <p class="vorlage">{aufnahme.text}</p>
      <label class="feld">
        <span>Text</span>
        <textarea rows="2" bind:value={text}></textarea>
      </label>
    {/if}
  </div>

  <div class="karte abschluss">
    <div class="reihe">
      <button
        class="knopf haupt"
        disabled={!speicherbar}
        title={aenderungen.length ? `Speichern: ${aenderungen.join(', ')}` : undefined}
        onclick={() => (frage = 'speichern')}
      >
        {laeuft ? 'Wird gespeichert …' : 'Speichern'}
      </button>
      <button class="knopf" onclick={() => verlasse()}>Abbrechen</button>
    </div>
  </div>
{:else if !fehler}
  <p class="gedaempft">Wird geladen …</p>
{/if}

<Rueckfrage
  offen={frage === 'speichern'}
  titel="Änderungen speichern?"
  knopf="Speichern"
  gefahr
  onja={speichern}
  onnein={() => (frage = '')}
>
  {#if teilen}
    <p><strong>Neu:</strong></p>
    <ul>
      {#each teile as zeile (zeile)}<li>{zeile}</li>{/each}
    </ul>
  {/if}
  {#if gekuerzt || teilen || neuerText}
    <p><strong>Gelöscht wird:</strong></p>
    <ul>
      {#if teilen}
        <li>die bisherige Aufnahme mit Ton, Text und Messwerten</li>
      {:else}
        {#if start > 0}<li>der Ton vor {start.toFixed(2)} s</li>{/if}
        {#if aufnahme && ende < aufnahme.dauer_s}<li>der Ton nach {ende.toFixed(2)} s</li>{/if}
        {#if neuerText}<li>der bisherige Text</li>{/if}
        <li>die Messwerte dieser Aufnahme</li>
      {/if}
    </ul>
  {/if}
  {#if pruefen}
    <p>Der Text gilt danach als geprüft.</p>
  {/if}
</Rueckfrage>

<Rueckfrage
  offen={frage === 'verlassen'}
  titel="Änderungen verwerfen?"
  knopf="Verwerfen"
  onja={verwirf}
  onnein={() => (frage = '')}
>
  <p>{aenderungen.filter((a) => a !== 'Text als geprüft übernommen').join(' · ')} - nicht gespeichert.</p>
</Rueckfrage>

<style>
  .titel {
    justify-content: space-between;
    align-items: baseline;
    margin-top: 2rem;
  }
  .titel h2 {
    margin: 0;
  }

  .wachsen {
    flex: 1;
  }

  .kopf {
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .rechts {
    align-items: center;
    gap: 0.75rem;
  }

  .lage {
    justify-content: space-between;
    align-items: center;
    gap: 0.4rem 1rem;
    margin-bottom: 0.6rem;
    padding-bottom: 0.6rem;
    border-bottom: 1px solid var(--rand);
  }
  .blaettern {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
  }
  .position {
    min-width: 4.5rem;
    text-align: center;
    font-variant-numeric: tabular-nums;
  }
  .daten {
    font-size: 0.85rem;
  }
  .knopf.zeichen svg .strich {
    fill: none;
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  .vorlage {
    margin: 0.75rem 0 0.5rem;
    line-height: 2;
  }

  /* Teil B in der Akzentfarbe - dieselbe Trennung wie die Linie in der Kurve,
     nur im Text. */
  .hinten {
    color: var(--akzent);
  }

  /* Die Lücke zwischen zwei Wörtern ist der Knopf: breit genug für einen
     Finger, und doch nicht breiter als ein Leerzeichen, solange dort nicht
     geteilt wird.

     Feste Maße und ein geschütztes Leerzeichen als Inhalt: Ein gewöhnliches
     Leerzeichen wirft der Browser in einem Inline-Block weg, und der Knopf
     war dann null Pixel hoch - anklickbar nur die eine Lücke, in der schon
     der Strich stand. */
  .luecke {
    display: inline-block;
    min-width: 0.9rem;
    height: 1.6em;
    vertical-align: middle;
    line-height: 1.6em;
    text-align: center;
    border: none;
    background: none;
    padding: 0 0.2rem;
    margin: 0;
    font: inherit;
    color: var(--warnung);
    cursor: pointer;
    border-radius: 0.2rem;
  }
  .luecke:hover,
  .luecke:focus-visible {
    background: var(--akzent-hell);
  }
  .luecke.gesetzt {
    font-weight: bold;
  }

  /* Nach Handarbeit an den Feldern ist die Wortreihe nur noch Stoff zum
     Neuanfangen - blasser, damit klar ist, dass die Felder gelten. */
  .vorlage.bearbeitet {
    opacity: 0.6;
  }

  .felder {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
    margin: 0.5rem 0 0.25rem;
  }
  @media (max-width: 600px) {
    .felder {
      grid-template-columns: 1fr;
    }
  }
  .felder textarea,
  .feld textarea {
    width: 100%;
    box-sizing: border-box;
    resize: vertical;
  }
  .feld {
    display: block;
    margin: 0.5rem 0 0.25rem;
  }

  .knopf.zeichen {
    padding: 0.35rem 0.5rem;
    line-height: 0;
  }

  .knopf.zeichen svg {
    width: 1rem;
    height: 1rem;
    fill: currentColor;
  }

  .knopf.zeichen svg .grenze {
    opacity: 0.45;
  }

  .knopf.klein {
    padding: 0.3rem 0.7rem;
    font-size: 0.85rem;
  }

  /* „Split" bleibt gedrückt, solange geteilt wird - ein Schalter, anders als
     die Schieber sonst in dieser Oberfläche. */
  .knopf.schalter.gedrueckt {
    background: var(--akzent);
    border-color: var(--akzent);
    color: var(--hintergrund);
    box-shadow: inset 0 2px 4px rgb(0 0 0 / 0.25);
  }

  .abschluss {
    margin-top: 1.5rem;
  }

</style>
