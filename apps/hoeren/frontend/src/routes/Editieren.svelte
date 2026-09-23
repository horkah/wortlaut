<script lang="ts">
  /**
   * Editieren: eine Aufnahme in zwei neue zerlegen, oder eine Kopie mit
   * berichtigtem Text anlegen - im Ton und im Text.
   *
   * Erreichbar aus dem Zuschnitt, über den Knopf „Editieren …" an einer Karte,
   * und nur von dort. Gezeigt wird genau diese eine Aufnahme: dieselbe Kurve
   * wie in der Liste, aber mit drei Linien statt zwei - Anfang, Teilung, Ende.
   * Darunter die Vorlage, Wort für Wort, mit einer anklickbaren Lücke vor dem
   * ersten, zwischen je zwei und nach dem letzten Wort, und darunter die
   * beiden Texte als Eingabefelder.
   *
   * **Die Textteilung folgt der Linie, bis jemand sie selbst setzt.** Anfangs
   * steht sie an der Wortgrenze, die zum Anteil der Zeit am besten passt; wer
   * die Linie verschiebt, schiebt sie mit. Ein Klick auf eine Lücke löst sie
   * davon, und wer in einem der Felder schreibt, löst die Felder ganz von der
   * Vorlage - gesprochen wird nicht immer, was dasteht. „Text zurücksetzen"
   * holt beides zurück.
   *
   * **Liegt die Teilung auf Anfang oder Ende**, hat ein Teil keine Länge. Sein
   * Feld wird grau, und gespeichert wird nur der andere, als Kopie.
   *
   * **Geschrieben wird erst nach der Rückfrage**, und dann entstehen neue
   * Aufnahmen neben dem Original (`api/zuschnitt.py`, `teilen`). Das Original
   * bleibt; wer es nicht mehr will, löscht es danach in der Liste. Abgespielt
   * wird bis dahin wie im Zuschnitt aus der geladenen Datei (`$ui/ausschnitt`),
   * ohne vorläufige Dateien auf dem Server.
   */
  import Pegelverlauf from '$ui/Pegelverlauf.svelte';
  import { spiele, stoppe, vergiss } from '$ui/ausschnitt';
  import { tag } from '$ui/zeit';
  import { EDITIEREN_ROUTE, ZUSCHNITT_PFAD } from '$ui/apps';
  import {
    zuschnittEine,
    zuschnittOriginal,
    zuschnittTeilen,
    type Zuschnittaufnahme,
  } from '../lib/api';
  import { bearbeitungsschluessel } from '../lib/bearbeitungsschluessel';
  import { gehZu, zustand } from '../lib/zustand.svelte';

  const schluessel = bearbeitungsschluessel();
  const kennung = $derived(zustand.route.slice(EDITIEREN_ROUTE.length));

  let aufnahme = $state<Zuschnittaufnahme | null>(null);
  let start = $state(0);
  let ende = $state(0);
  let teilung = $state(0);
  // Wo die Linien beim Laden standen - dorthin setzt „Linien zurücksetzen".
  let anfangs = { start: 0, ende: 0, teilung: 0 };
  // Vor dem wievielten Wort der zweite Teil beginnt: 0 heißt alles in Teil 2,
  // die Zahl der Wörter alles in Teil 1.
  let wortgrenze = $state(1);
  let vonHand = $state(false);
  // Die beiden Texte. Solange niemand darin schreibt, kommen sie aus der
  // Vorlage und der Wortgrenze; danach gehören sie dem, der schreibt.
  let textVorn = $state('');
  let textHinten = $state('');
  let bearbeitet = $state(false);

  let fehler = $state('');
  let spielt = $state<'' | 'ganz' | 'vorn' | 'hinten'>('');
  let laeuft = $state(false);
  let datei: Blob | null = null;

  const woerter = $derived(aufnahme ? aufnahme.text.split(/\s+/).filter(Boolean) : []);
  // Ein Teil ohne Länge: Die Teilung liegt auf Anfang oder Ende.
  const leerVorn = $derived(teilung <= start);
  const leerHinten = $derived(teilung >= ende);
  const bereit = $derived(
    (leerVorn || textVorn.trim() !== '') && (leerHinten || textHinten.trim() !== ''),
  );
  const knopftext = $derived(
    leerVorn
      ? 'Teil 2 als Kopie speichern'
      : leerHinten
        ? 'Teil 1 als Kopie speichern'
        : 'In zwei Aufnahmen teilen',
  );

  /**
   * Wo die Teilung anfangs steht: in der Mitte der längsten Pause zwischen
   * den Grenzen - dort, wo zwei Sätze aneinanderstoßen. Gibt es keine, in der
   * Mitte des Ausschnitts.
   */
  function pausenmitte(eine: Zuschnittaufnahme, von: number, bis: number): number {
    const fenster = eine.fenster_s;
    let beste = { laenge: 0, mitte: (von + bis) / 2 };
    let anfang = -1;
    const erstes = Math.ceil(von / fenster);
    const letztes = Math.floor(bis / fenster);
    for (let nummer = erstes; nummer <= letztes + 1; nummer++) {
      const leise = nummer <= letztes && (eine.verlauf[nummer] ?? 0) < eine.schwelle;
      if (leise && anfang < 0) anfang = nummer;
      if (!leise && anfang >= 0) {
        // Pausen am Rand zählen nicht: Das ist die Stille vor dem ersten und
        // nach dem letzten Wort, nicht die zwischen zwei Sätzen.
        const amRand = anfang === erstes || nummer > letztes;
        if (!amRand && nummer - anfang > beste.laenge) {
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
    const gesamt = Math.max(woerter.join(' ').length, 1);
    let beste = 0;
    let abstand = Infinity;
    for (let grenze = 0; grenze <= woerter.length; grenze++) {
      const vorn = woerter.slice(0, grenze).join(' ').length;
      const neu = Math.abs(vorn / gesamt - anteil);
      if (neu < abstand) {
        abstand = neu;
        beste = grenze;
      }
    }
    return beste;
  }

  $effect(() => {
    // Die Textteilung läuft mit der Linie mit, solange niemand sie selbst gesetzt hat.
    if (!vonHand && aufnahme) wortgrenze = passendeGrenze();
  });

  $effect(() => {
    // Und die Felder folgen der Textteilung, solange niemand darin schreibt.
    if (bearbeitet) return;
    textVorn = woerter.slice(0, wortgrenze).join(' ');
    textHinten = woerter.slice(wortgrenze).join(' ');
  });

  async function lade(id: string) {
    fehler = '';
    stoppe();
    vergiss();
    datei = null;
    aufnahme = null;
    if (!schluessel) {
      fehler = 'Zum Editieren braucht es den Bearbeitungsschlüssel - bitte im Zuschnitt eingeben.';
      return;
    }
    try {
      const eine = await zuschnittEine(schluessel, id);
      start = eine.zuschnitt_start_s ?? eine.vorschlag_start_s;
      ende = eine.zuschnitt_ende_s ?? eine.vorschlag_ende_s;
      teilung = pausenmitte(eine, start, ende);
      anfangs = { start, ende, teilung };
      vonHand = false;
      bearbeitet = false;
      aufnahme = eine;
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  /** Eine Lücke angeklickt: Die Felder kommen wieder aus der Vorlage, an dieser Stelle geteilt. */
  function setzeText(grenze: number) {
    wortgrenze = grenze;
    vonHand = true;
    bearbeitet = false;
  }

  /** Die Vorlage zurück in die Felder, und die Teilung folgt wieder der Linie. */
  function textZuruecksetzen() {
    vonHand = false;
    bearbeitet = false;
  }

  function linienZuruecksetzen() {
    ({ start, ende, teilung } = anfangs);
  }

  function allesZuruecksetzen() {
    linienZuruecksetzen();
    textZuruecksetzen();
  }

  /** Abspielen - das Ganze oder einen der beiden Teile. Ein zweiter Druck hält an. */
  async function hoere(welches: 'ganz' | 'vorn' | 'hinten') {
    if (!aufnahme) return;
    if (spielt === welches) {
      stoppe();
      spielt = '';
      return;
    }
    const [von, bis] =
      welches === 'ganz'
        ? [0, aufnahme.dauer_s]
        : welches === 'vorn'
          ? [start, teilung]
          : [teilung, ende];
    try {
      spielt = welches;
      datei ??= await zuschnittOriginal(schluessel, aufnahme.id);
      await spiele(aufnahme.id, datei, von, bis, () => {
        if (spielt === welches) spielt = '';
      });
    } catch (ursache) {
      spielt = '';
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  async function speichere() {
    if (!aufnahme || !bereit) return;
    const zeilen = [
      ...(leerVorn ? [] : [`Teil 1 (${(teilung - start).toFixed(2)} s): ${textVorn.trim()}`]),
      ...(leerHinten ? [] : [`Teil 2 (${(ende - teilung).toFixed(2)} s): ${textHinten.trim()}`]),
    ];
    const frage =
      zeilen.length === 2
        ? 'Diese Aufnahme in zwei neue Aufnahmen teilen?'
        : `${knopftext.replace(' speichern', '')} speichern?`;
    if (
      !confirm(
        `${frage}\n\n${zeilen.join('\n')}\n\n` +
          'Neue Aufnahmen tragen das Datum des Originals und stehen in der Liste direkt darunter. ' +
          'Das Original bleibt erhalten - wer es nicht mehr braucht, löscht es danach im Zuschnitt.',
      )
    )
      return;
    fehler = '';
    laeuft = true;
    try {
      await zuschnittTeilen(schluessel, {
        id: aufnahme.id,
        start_s: start,
        teilung_s: teilung,
        ende_s: ende,
        text_vorn: leerVorn ? '' : textVorn,
        text_hinten: leerHinten ? '' : textHinten,
      });
      gehZu(ZUSCHNITT_PFAD);
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      laeuft = false;
    }
  }

  $effect(() => {
    if (zustand.art === 'sprecher' && kennung) lade(kennung);
    return () => {
      stoppe();
      vergiss();
      datei = null;
    };
  });
</script>

<div class="reihe titel">
  <h2>Editieren</h2>
  <button class="knopf" onclick={() => gehZu(ZUSCHNITT_PFAD)}>Zurück zum Zuschnitt</button>
</div>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

{#if aufnahme}
  <div class="karte">
    <p class="gedaempft">
      Die gestrichelte Linie teilt die Aufnahme in zwei; die beiden äußeren sagen, was von jedem
      Teil an den Rändern bleibt. Im Text darunter setzt ein Klick auf eine Lücke die Stelle, an der
      der Text geteilt wird - auch vor dem ersten oder nach dem letzten Wort. Die beiden Felder lassen
      sich berichtigen, wenn etwas anderes gesprochen wurde, als dasteht. Liegt die gestrichelte
      Linie auf Anfang oder Ende, wird nur der andere Teil als Kopie gespeichert.
    </p>
  </div>

  <div class="karte">
    <div class="reihe kopf">
      <span class="gedaempft">{aufnahme.dauer_s.toFixed(1)} s · {tag(aufnahme.erstellt)}</span>
      <span class="wachsen"></span>
      <!-- Drei Knöpfe, drei Zeichen: das volle Dreieck für die ganze Aufnahme,
           und je eines zwischen einer festen und einer gestrichelten Grenze für
           die beiden Teile - die gestrichelte ist die Teilung, wie in der Kurve. -->
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
      <button
        class="knopf zeichen"
        title="Teil 1 anhören"
        aria-label="Teil 1 anhören"
        disabled={leerVorn}
        onclick={() => hoere('vorn')}
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
          />{#if spielt === 'vorn'}<rect x="4.5" y="4" width="2.5" height="8" /><rect
              x="9"
              y="4"
              width="2.5"
              height="8"
            />{:else}<path d="M5 4 L11.5 8 L5 12 Z" />{/if}</svg
        >
      </button>
      <button
        class="knopf zeichen"
        title="Teil 2 anhören"
        aria-label="Teil 2 anhören"
        disabled={leerHinten}
        onclick={() => hoere('hinten')}
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
          />{#if spielt === 'hinten'}<rect x="4.5" y="4" width="2.5" height="8" /><rect
              x="9"
              y="4"
              width="2.5"
              height="8"
            />{:else}<path d="M5 4 L11.5 8 L5 12 Z" />{/if}</svg
        >
      </button>
    </div>

    <Pegelverlauf
      verlauf={aufnahme.verlauf}
      fensterS={aufnahme.fenster_s}
      schwelle={aufnahme.schwelle}
      dauerS={aufnahme.dauer_s}
      bind:start
      bind:ende
      bind:teilung
      beschriftung="Schnitt"
    />

    <p class="vorlage" class:bearbeitet aria-label="Vorlage, an jeder Wortgrenze teilbar">
      {#each Array.from({ length: woerter.length + 1 }, (_, n) => n) as grenze (grenze)}
        <button
          class="luecke"
          class:gesetzt={grenze === wortgrenze}
          title="Hier teilen"
          aria-label={grenze === 0
            ? 'Vor dem ersten Wort teilen - alles in Teil 2'
            : grenze === woerter.length
              ? 'Nach dem letzten Wort teilen - alles in Teil 1'
              : `Vor „${woerter[grenze]}“ teilen`}
          aria-pressed={grenze === wortgrenze}
          onclick={() => setzeText(grenze)}>{grenze === wortgrenze ? '|' : '\u00a0'}</button
        >{#if grenze < woerter.length}<span class:hinten={grenze >= wortgrenze}
            >{woerter[grenze]}</span
          >{/if}
      {/each}
    </p>
    {#if bearbeitet}
      <p class="gedaempft klein">
        Die Texte unten sind von Hand geändert. Ein Klick auf eine Lücke teilt wieder die Vorlage.
      </p>
    {/if}

    <div class="felder">
      <label class:leer={leerVorn}>
        <span>Teil 1{leerVorn ? ' - ohne Länge, entsteht nicht' : ''}</span>
        <textarea
          rows="2"
          bind:value={textVorn}
          disabled={leerVorn}
          oninput={() => (bearbeitet = true)}
        ></textarea>
      </label>
      <label class:leer={leerHinten}>
        <span>Teil 2{leerHinten ? ' - ohne Länge, entsteht nicht' : ''}</span>
        <textarea
          rows="2"
          bind:value={textHinten}
          disabled={leerHinten}
          oninput={() => (bearbeitet = true)}
        ></textarea>
      </label>
    </div>

    <div class="reihe schmal">
      <button
        class="knopf klein"
        disabled={!vonHand && !bearbeitet}
        title="Die Vorlage zurück in die Felder; die Teilung im Text folgt wieder der Linie"
        onclick={textZuruecksetzen}>Text zurücksetzen</button
      >
      <button
        class="knopf klein"
        title="Anfang, Teilung und Ende dorthin, wo sie beim Öffnen standen"
        onclick={linienZuruecksetzen}>Linien zurücksetzen</button
      >
      <button class="knopf klein" onclick={allesZuruecksetzen}>Alles zurücksetzen</button>
    </div>
  </div>

  <div class="karte abschluss">
    <div class="reihe">
      <button class="knopf haupt" disabled={laeuft || !bereit} onclick={speichere}>
        {laeuft ? 'Wird gespeichert …' : knopftext}
      </button>
      <button class="knopf" onclick={() => gehZu(ZUSCHNITT_PFAD)}>Abbrechen</button>
    </div>
    <p class="gedaempft">
      Es entstehen neue Aufnahmen mit eigenen Dateien und eigenem Text, verlustfrei aus dem
      Original geschnitten. Das Original bleibt unverändert; gemessen werden die neuen Aufnahmen
      beim nächsten Auswertungslauf.
    </p>
  </div>
{:else if !fehler}
  <p class="gedaempft">Wird geladen …</p>
{/if}

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

  .vorlage {
    margin: 0.75rem 0 0.5rem;
    line-height: 2;
  }

  /* Der zweite Teil in der Akzentfarbe - dieselbe Trennung wie die Linie in
     der Kurve, nur im Text. */
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

  /* Nach Handarbeit an den Feldern ist die Wortreihe nur noch Vorlage zum
     Neuanfangen - blasser, damit klar ist, dass die Felder gelten. */
  .vorlage.bearbeitet {
    opacity: 0.6;
  }

  .klein {
    font-size: 0.85rem;
  }

  .felder {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
    margin: 0.5rem 0 0.75rem;
  }
  @media (max-width: 600px) {
    .felder {
      grid-template-columns: 1fr;
    }
  }
  .felder textarea {
    width: 100%;
    box-sizing: border-box;
    resize: vertical;
  }
  /* Ein Teil ohne Länge: grau und nicht bearbeitbar - er entsteht nicht. */
  .felder .leer textarea {
    background: var(--rand);
    color: var(--gedaempft);
  }

  .schmal {
    gap: 0.4rem;
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

  .abschluss {
    margin-top: 1.5rem;
  }
</style>
