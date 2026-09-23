<script lang="ts">
  /**
   * Schneiden: eine Aufnahme in zwei neue zerlegen - im Ton und im Text.
   *
   * Erreichbar aus dem Zuschnitt, über den Knopf „Schneiden …" an einer Karte,
   * und nur von dort. Gezeigt wird genau diese eine Aufnahme: dieselbe Kurve
   * wie in der Liste, aber mit drei Linien statt zwei - Anfang, Teilung, Ende.
   * Darunter die Vorlage, Wort für Wort, und zwischen je zwei Wörtern eine
   * Stelle, an der sich der Text teilen lässt.
   *
   * **Die Textteilung folgt der Linie, bis jemand sie selbst setzt.** Anfangs
   * steht sie an der Wortgrenze, die zum Anteil der Zeit am besten passt; wer
   * die Linie verschiebt, schiebt sie mit. Erst ein Klick zwischen zwei Wörter
   * löst sie davon - dann ist es eine Entscheidung und kein Vorschlag mehr.
   *
   * **Geschrieben wird erst nach der Rückfrage**, und dann entstehen zwei neue
   * Aufnahmen neben dem Original (`api/zuschnitt.py`, `teilen`). Das Original
   * bleibt; wer es nicht mehr will, löscht es danach in der Liste. Abgespielt
   * wird bis dahin wie im Zuschnitt aus der geladenen Datei (`$ui/ausschnitt`),
   * ohne vorläufige Dateien auf dem Server.
   */
  import Pegelverlauf from '$ui/Pegelverlauf.svelte';
  import { spiele, stoppe, vergiss } from '$ui/ausschnitt';
  import { tag } from '$ui/zeit';
  import { TEILEN_ROUTE, ZUSCHNITT_PFAD } from '$ui/apps';
  import {
    zuschnittEine,
    zuschnittOriginal,
    zuschnittTeilen,
    type Zuschnittaufnahme,
  } from '../lib/api';
  import { bearbeitungsschluessel } from '../lib/bearbeitungsschluessel';
  import { gehZu, zustand } from '../lib/zustand.svelte';

  const schluessel = bearbeitungsschluessel();
  const kennung = $derived(zustand.route.slice(TEILEN_ROUTE.length));

  let aufnahme = $state<Zuschnittaufnahme | null>(null);
  let start = $state(0);
  let ende = $state(0);
  let teilung = $state(0);
  // Vor dem wievielten Wort der zweite Teil beginnt.
  let wortgrenze = $state(1);
  let vonHand = $state(false);

  let fehler = $state('');
  let spielt = $state<'' | 'ganz' | 'vorn' | 'hinten'>('');
  let laeuft = $state(false);
  let datei: Blob | null = null;

  const woerter = $derived(aufnahme ? aufnahme.text.split(/\s+/).filter(Boolean) : []);
  const textVorn = $derived(woerter.slice(0, wortgrenze).join(' '));
  const textHinten = $derived(woerter.slice(wortgrenze).join(' '));

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
    if (woerter.length < 2 || ende <= start) return 1;
    const anteil = (teilung - start) / (ende - start);
    const gesamt = woerter.join(' ').length;
    let beste = 1;
    let abstand = Infinity;
    for (let grenze = 1; grenze < woerter.length; grenze++) {
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

  async function lade(id: string) {
    fehler = '';
    stoppe();
    vergiss();
    datei = null;
    aufnahme = null;
    if (!schluessel) {
      fehler = 'Zum Schneiden braucht es den Bearbeitungsschlüssel - bitte im Zuschnitt eingeben.';
      return;
    }
    try {
      const eine = await zuschnittEine(schluessel, id);
      start = eine.zuschnitt_start_s ?? eine.vorschlag_start_s;
      ende = eine.zuschnitt_ende_s ?? eine.vorschlag_ende_s;
      teilung = pausenmitte(eine, start, ende);
      vonHand = false;
      aufnahme = eine;
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  function setzeText(grenze: number) {
    wortgrenze = grenze;
    vonHand = true;
  }

  function textFolgtLinie() {
    vonHand = false;
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
    if (!aufnahme || !textVorn || !textHinten) return;
    if (
      !confirm(
        'Diese Aufnahme in zwei neue Aufnahmen teilen?\n\n' +
          `Teil 1 (${(teilung - start).toFixed(2)} s): ${textVorn}\n` +
          `Teil 2 (${(ende - teilung).toFixed(2)} s): ${textHinten}\n\n` +
          'Beide tragen das Datum des Originals und stehen in der Liste direkt darunter. ' +
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
        text_vorn: textVorn,
        text_hinten: textHinten,
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
  <h2>Schneiden</h2>
  <button class="knopf" onclick={() => gehZu(ZUSCHNITT_PFAD)}>Zurück zum Zuschnitt</button>
</div>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

{#if aufnahme}
  <div class="karte">
    <p class="gedaempft">
      Die gestrichelte Linie teilt die Aufnahme in zwei; die beiden äußeren sagen, was von jedem
      Teil an den Rändern bleibt. Im Text darunter wird zwischen zwei Wörtern geteilt - ein Klick
      auf die Lücke setzt die Stelle.
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

    <p class="vorlage" aria-label="Vorlage, zwischen zwei Wörtern teilbar">
      {#each woerter as wort, nummer (nummer)}
        {#if nummer > 0}
          <button
            class="luecke"
            class:gesetzt={nummer === wortgrenze}
            title="Hier teilen"
            aria-label="Vor „{wort}“ teilen"
            aria-pressed={nummer === wortgrenze}
            onclick={() => setzeText(nummer)}>{nummer === wortgrenze ? '|' : '\u00a0'}</button
          >
        {/if}<span class:hinten={nummer >= wortgrenze}>{wort}</span>
      {/each}
    </p>

    <dl class="teile">
      <dt>Teil 1</dt>
      <dd>{textVorn}</dd>
      <dt>Teil 2</dt>
      <dd>{textHinten}</dd>
    </dl>
    {#if vonHand}
      <button class="knopf klein" onclick={textFolgtLinie}>Text wieder der Linie folgen lassen</button>
    {/if}
    {#if woerter.length < 2}
      <p class="fehler">Die Vorlage hat nur ein Wort - daran lässt sich nichts teilen.</p>
    {/if}
  </div>

  <div class="karte abschluss">
    <div class="reihe">
      <button
        class="knopf haupt"
        disabled={laeuft || woerter.length < 2}
        onclick={speichere}
      >
        {laeuft ? 'Wird geteilt …' : 'In zwei Aufnahmen teilen'}
      </button>
      <button class="knopf" onclick={() => gehZu(ZUSCHNITT_PFAD)}>Abbrechen</button>
    </div>
    <p class="gedaempft">
      Es entstehen zwei neue Aufnahmen mit eigenen Dateien und eigenem Text, verlustfrei aus dem
      Original geschnitten. Das Original bleibt unverändert; gemessen werden die Teile beim
      nächsten Auswertungslauf.
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

  .teile {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 0.25rem 0.75rem;
    margin: 0.5rem 0;
  }
  .teile dt {
    color: var(--gedaempft);
  }
  .teile dd {
    margin: 0;
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
