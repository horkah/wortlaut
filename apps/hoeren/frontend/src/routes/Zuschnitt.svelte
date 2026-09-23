<script lang="ts" module>
  // Welche Seite gerade offen ist - über die Ansicht hinaus gemerkt. Wer aus
  // „Editieren" zurückkommt, soll dort weiterarbeiten, wo er die Karte
  // verlassen hat, und nicht auf Seite 1 von vorn suchen. Nur für diesen
  // Reiter und diese Sitzung: Ein Neuladen fängt vorn an, wie bisher.
  const gemerkt = { seite: 1, proSeite: 0 };
</script>

<script lang="ts">
  /**
   * Zuschnitt: die Stille an den Rändern der eigenen Aufnahmen wegschneiden.
   *
   * Erreichbar aus „Meine Daten" und nur von dort - kein Reiter, kein
   * Menüpunkt. Das ist dieselbe Stellung, die die Einsicht der Aufsicht hat
   * (`Einsicht.svelte`): eine Werkbank, zu der ein Weg führt und derselbe
   * zurück. In der Reiterreihe stünde sie neben „Aufnehmen" und „Fortschritt",
   * also zwischen Dingen, die ein Sprecher täglich tut - und wäre damit
   * genauso oft ein Fehlgriff wie eine Hilfe (Grundentscheidung 7).
   *
   * **Was hier passiert.** Je Aufnahme eine Karte: der Lautstärkeverlauf, zwei
   * orange Linien darin, die Vorlage darunter, zwei Knöpfe zum Hören. Die
   * Linien stehen anfangs dort, wo der Server die Stimme vermutet
   * (`audio.stimmgrenzen`) - oder dort, wo schon einmal geschnitten wurde.
   * Verschoben werden sie mit Finger, Maus oder Pfeiltasten.
   *
   * **Und was hier nicht passiert.** Geschrieben wird nichts, solange niemand
   * unten auf den Knopf drückt und die Rückfrage bestätigt. Bis dahin ist der
   * Ausschnitt eine Zahl in diesem Browser; auch der Ausschnitt-Knopf spielt
   * nur einen Bereich der geladenen Datei ab (`$ui/ausschnitt`). Es gibt keine
   * vorläufigen Dateien auf dem Server - eine angefangene Bearbeitung, die
   * jemand wegklickt, hinterlässt nichts.
   */
  import Pager from '$ui/Pager.svelte';
  import Pegelverlauf from '$ui/Pegelverlauf.svelte';
  import { spiele, stoppe, vergiss } from '$ui/ausschnitt';
  import { tag } from '$ui/zeit';
  import {
    zuschnittAufnahmen,
    zuschnittLoeschen,
    zuschnittOriginal,
    zuschnittSchreiben,
    zuschnittStand,
    zuschnittZuruecknehmen,
    type Zuschnittaufnahme,
  } from '../lib/api';
  import { bearbeitungsschluessel, setzeBearbeitungsschluessel } from '../lib/bearbeitungsschluessel';
  import { gehZu, zustand } from '../lib/zustand.svelte';
  import { MEINE_DATEN_PFAD, EDITIEREN_ROUTE } from '$ui/apps';

  // Wie viele Aufnahmen auf eine Seite gehen. Zehn ist die Vorgabe; mehr darf
  // wählen, wer einen großen Bildschirm und einen kurzen Korpus hat. Je Zeile
  // rechnet der Server einen Pegelverlauf, also ist die Zahl auch die Antwort
  // darauf, wie lange das Blättern dauert.
  const SEITENGROESSEN = [10, 20, 50];

  let stand = $state<'unbekannt' | 'aus' | 'schluessel' | 'offen'>('unbekannt');
  let hinweis = $state('');
  let schluessel = $state(bearbeitungsschluessel());
  let eingabe = $state('');

  let aufnahmen = $state<Zuschnittaufnahme[]>([]);
  let gesamt = $state(0);
  let seite = $state(gemerkt.seite);
  let proSeite = $state(gemerkt.proSeite || SEITENGROESSEN[0]);
  const seiten = $derived(Math.max(1, Math.ceil(gesamt / proSeite)));

  /**
   * Die Grenzen, an denen gerade gezogen wird - je Aufnahme ein Paar.
   *
   * Getrennt von `aufnahmen` und nicht als Feld darin: `aufnahmen` ist die
   * Antwort des Servers und soll es bleiben. Was daneben steht, ist die
   * Bearbeitung, und beim Verwerfen („Vorschlag zurück") muss klar sein,
   * worauf zurückgesetzt wird.
   */
  let grenzen = $state<Record<string, { start: number; ende: number }>>({});
  let markiert = $state<Record<string, boolean>>({});
  let spielt = $state('');

  /**
   * Die geholten Audiodateien dieser Seite.
   *
   * Kein `$state`: Niemand zeichnet daraus, es ist ein Zwischenspeicher. Er
   * spart bei jedem zweiten Druck auf „Abspielen" eine Anfrage über gut
   * hundert Kilobyte - und auf dieser Seite drückt man oft, erst das Ganze,
   * dann den Ausschnitt, dann die Linie verschieben und noch einmal.
   * Geleert wird er beim Blättern, zusammen mit den dekodierten Fassungen in
   * `$ui/ausschnitt`.
   */
  let dateien = new Map<string, Blob>();

  let fehler = $state('');
  let meldung = $state('');
  let laeuft = $state('');

  const anzahlMarkiert = $derived(Object.values(markiert).filter(Boolean).length);
  const alleMarkiert = $derived(aufnahmen.length > 0 && anzahlMarkiert === aufnahmen.length);

  /** Wo die Linien einer Aufnahme anfangs stehen: der Schnitt, sonst der Vorschlag. */
  function anfang(aufnahme: Zuschnittaufnahme) {
    return {
      start: aufnahme.zuschnitt_start_s ?? aufnahme.vorschlag_start_s,
      ende: aufnahme.zuschnitt_ende_s ?? aufnahme.vorschlag_ende_s,
    };
  }

  async function lade() {
    fehler = '';
    stoppe();
    // Die Aufnahmen der alten Seite freigeben - sonst wächst der Speicher mit
    // jedem Blättern (`$ui/ausschnitt`).
    vergiss();
    dateien = new Map();
    spielt = '';
    gemerkt.seite = seite;
    gemerkt.proSeite = proSeite;
    try {
      const antwort = await zuschnittAufnahmen(schluessel, (seite - 1) * proSeite, proSeite);
      aufnahmen = antwort.aufnahmen;
      gesamt = antwort.gesamt;
      grenzen = Object.fromEntries(aufnahmen.map((eine) => [eine.id, anfang(eine)]));
      markiert = {};
      stand = 'offen';
    } catch (ursache) {
      const satz = ursache instanceof Error ? ursache.message : String(ursache);
      // Ein falscher Schlüssel ist kein Fehler auf der Seite, sondern die
      // Frage nach dem richtigen - sonst stünde die Liste leer da und daneben
      // ein Satz, den niemand beantworten kann.
      if (satz.includes('schlüssel') || satz.includes('Schlüssel')) {
        stand = 'schluessel';
        hinweis = satz;
      } else {
        fehler = satz;
      }
    }
  }

  async function starte() {
    try {
      const auskunft = await zuschnittStand();
      if (!auskunft.bereit) {
        stand = 'aus';
        hinweis = auskunft.hinweis;
        return;
      }
      if (!schluessel) {
        stand = 'schluessel';
        return;
      }
      await lade();
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  function schluesselMerken(ereignis: SubmitEvent) {
    ereignis.preventDefault();
    if (!eingabe.trim()) return;
    schluessel = eingabe.trim();
    setzeBearbeitungsschluessel(schluessel);
    eingabe = '';
    hinweis = '';
    lade();
  }

  function schluesselVergessen() {
    setzeBearbeitungsschluessel('');
    schluessel = '';
    aufnahmen = [];
    stand = 'schluessel';
  }

  async function blaettere(neue: number) {
    seite = neue;
    await lade();
  }

  async function seitengroesse(neue: number) {
    proSeite = neue;
    seite = 1;
    await lade();
  }

  function markiereAlle(an: boolean) {
    markiert = an ? Object.fromEntries(aufnahmen.map((eine) => [eine.id, true])) : {};
  }

  function aufVorschlag(aufnahme: Zuschnittaufnahme) {
    grenzen[aufnahme.id] = {
      start: aufnahme.vorschlag_start_s,
      ende: aufnahme.vorschlag_ende_s,
    };
  }

  function ganzeAufnahme(aufnahme: Zuschnittaufnahme) {
    grenzen[aufnahme.id] = { start: 0, ende: aufnahme.dauer_s };
  }

  /**
   * Abspielen - ganz oder nur den Ausschnitt.
   *
   * Beides aus derselben Datei: Sie wird beim ersten Druck geholt und bleibt
   * dekodiert liegen, bis jemand weiterblättert. Ein zweiter Druck auf
   * denselben Knopf hält an, denn bei acht Sekunden wartet sonst niemand ab.
   */
  async function hoere(aufnahme: Zuschnittaufnahme, nurAusschnitt: boolean) {
    const marke = `${aufnahme.id}:${nurAusschnitt}`;
    if (spielt === marke) {
      stoppe();
      spielt = '';
      return;
    }
    const bereich = grenzen[aufnahme.id] ?? anfang(aufnahme);
    try {
      spielt = marke;
      let datei = dateien.get(aufnahme.id);
      if (!datei) {
        datei = await zuschnittOriginal(schluessel, aufnahme.id);
        dateien.set(aufnahme.id, datei);
      }
      await spiele(
        aufnahme.id,
        datei,
        nurAusschnitt ? bereich.start : 0,
        nurAusschnitt ? bereich.ende : aufnahme.dauer_s,
        () => {
          if (spielt === marke) spielt = '';
        },
      );
    } catch (ursache) {
      spielt = '';
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  const gewaehlt = () =>
    aufnahmen
      .filter((eine) => markiert[eine.id])
      .map((eine) => ({
        id: eine.id,
        start_s: (grenzen[eine.id] ?? anfang(eine)).start,
        ende_s: (grenzen[eine.id] ?? anfang(eine)).ende,
      }));

  async function schreibe() {
    const auswahl = gewaehlt();
    if (!auswahl.length) return;
    if (
      !confirm(
        `${auswahl.length} Aufnahme(n) zuschneiden?\n\n` +
          'Ab dann wird überall mit den zugeschnittenen Dateien gearbeitet: ' +
          'beim Messen, beim Trainieren und beim Anhören.\n\n' +
          'Die Originale bleiben erhalten und lassen sich jederzeit ' +
          'zurückholen. Die bisherigen Messwerte dieser Aufnahmen werden ' +
          'verworfen - der nächste Auswertungslauf rechnet sie neu.',
      )
    )
      return;
    await tue('schreiben', () => zuschnittSchreiben(schluessel, auswahl));
  }

  async function nimmZurueck() {
    const auswahl = gewaehlt();
    if (!auswahl.length) return;
    if (
      !confirm(
        `Zuschnitt von ${auswahl.length} Aufnahme(n) zurücknehmen?\n\n` +
          'Danach gelten wieder die Originale in voller Länge. ' +
          'Die bisherigen Messwerte dieser Aufnahmen werden verworfen.',
      )
    )
      return;
    await tue('zurueck', () => zuschnittZuruecknehmen(schluessel, auswahl));
  }

  /**
   * Löschen - ganz, nicht verwerfen.
   *
   * Gedacht vor allem für das Original nach dem Teilen in „Editieren": Es steht dann
   * neben seinen beiden Teilen und hat dort nichts mehr zu suchen. Die
   * Rückfrage sagt deshalb ausdrücklich, was anders ist als beim Verwerfen in
   * „Meine Daten" - dort wird der Satz wieder offen, hier geht er mit.
   */
  async function loesche() {
    const auswahl = gewaehlt();
    if (!auswahl.length) return;
    if (
      !confirm(
        `${auswahl.length} Aufnahme(n) endgültig löschen?\n\n` +
          'Gelöscht werden die Aufnahme, ihre Dateien (auch Zuschnitt und Abwandlungen) ' +
          'und alle Messwerte. Hängt an ihrer Vorlage keine andere Aufnahme, geht auch ' +
          'die Vorlage - der Satz kommt nicht wieder in die Warteschlange.\n\n' +
          'Das lässt sich nicht rückgängig machen. Wer den Satz neu sprechen will, ' +
          'verwirft die Aufnahme stattdessen in „Meine Daten".',
      )
    )
      return;
    await tue('loeschen', () => zuschnittLoeschen(schluessel, auswahl), 'gelöscht');
  }

  /** Ein Knopf, der arbeitet - und danach die Seite neu holt, damit sie stimmt. */
  async function tue(
    name: string,
    arbeit: () => Promise<{ geschrieben: number; fehler: Record<string, string> }>,
    was = 'geschrieben',
  ) {
    fehler = '';
    meldung = '';
    laeuft = name;
    try {
      const ergebnis = await arbeit();
      const offen = Object.entries(ergebnis.fehler);
      meldung = `${ergebnis.geschrieben} Aufnahme(n) ${was}.`;
      if (offen.length) {
        fehler = offen.map(([kennung, satz]) => `${kennung}: ${satz}`).join(' · ');
      }
      await lade();
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      laeuft = '';
    }
  }

  $effect(() => {
    if (zustand.art === 'sprecher') starte();
    // Beim Verlassen der Ansicht nichts weiterlaufen lassen und den Speicher
    // freigeben: Eine Aufnahme, die aus einer geschlossenen Seite weiterspricht,
    // ist das Gegenteil von dem, was diese Ansicht verspricht.
    return () => {
      stoppe();
      vergiss();
      dateien = new Map();
    };
  });
</script>

<div class="reihe titel">
  <h2>Zuschnitt</h2>
  <button class="knopf" onclick={() => gehZu(MEINE_DATEN_PFAD)}>Zurück zu „Meine Daten“</button>
</div>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}
{#if meldung}
  <p class="gedaempft">{meldung}</p>
{/if}

{#if stand === 'unbekannt'}
  <p class="gedaempft">Wird geladen …</p>
{:else if stand === 'aus'}
  <div class="karte">
    <p>{hinweis}</p>
    <p class="gedaempft">
      Der Zuschnitt greift in den Bestand: Er entscheidet, welcher Ton ab dann gemessen und
      trainiert wird. Deshalb steht ein eigener Schlüssel davor, und ohne hinterlegten Schlüssel
      ist er abgeschaltet - wie das Training in „lernen“.
    </p>
  </div>
{:else if stand === 'schluessel'}
  <div class="karte">
    <p>Zum Zuschneiden braucht es den Bearbeitungsschlüssel dieses Servers.</p>
    {#if hinweis}<p class="fehler">{hinweis}</p>{/if}
    <form class="reihe" onsubmit={schluesselMerken}>
      <!-- svelte-ignore a11y_autofocus -->
      <input
        bind:value={eingabe}
        type="password"
        autocomplete="off"
        placeholder="Bearbeitungsschlüssel"
        required
      />
      <button class="knopf haupt" type="submit">Weiter</button>
    </form>
    <p class="gedaempft">
      Er bleibt in diesem Browser gespeichert, damit er nicht bei jeder Seite neu getippt werden
      muss. Ihr Zugang bleibt davon unberührt - es sind zwei verschiedene Geheimnisse.
    </p>
  </div>
{:else}
  <div class="karte">
    <p class="gedaempft">
      Die orangen Linien sagen, was von jeder Aufnahme bleibt. Sie stehen dort, wo die Stimme
      anfängt und aufhört - verschieben lassen sie sich mit Finger, Maus oder den Pfeiltasten.
      Geschrieben wird erst unten, und nur für das, was hier markiert ist.
    </p>
    <div class="reihe werkzeuge">
      <label class="reihe schmal">
        <input
          type="checkbox"
          checked={alleMarkiert}
          onchange={(e) => markiereAlle(e.currentTarget.checked)}
        />
        Alle auf dieser Seite
      </label>
      <span class="gedaempft">{anzahlMarkiert} von {aufnahmen.length} markiert</span>
      <span class="wachsen"></span>
      <label class="reihe schmal gedaempft">
        Je Seite
        <select
          value={proSeite}
          onchange={(e) => seitengroesse(Number(e.currentTarget.value))}
        >
          {#each SEITENGROESSEN as groesse (groesse)}
            <option value={groesse}>{groesse}</option>
          {/each}
        </select>
      </label>
      <button class="knopf" onclick={schluesselVergessen}>Schlüssel vergessen</button>
    </div>
  </div>

  {#each aufnahmen as aufnahme, nummer (aufnahme.id)}
    <!-- `grenzen` wird in `lade()` für jede Aufnahme dieser Seite gesetzt.
         Ohne den Eintrag stünde hier ein frisches Objekt, und `bind:` schriebe
         in etwas, das niemand mehr liest - lieber die Karte auslassen als eine
         Kurve zeigen, deren Linien sich nicht merken lassen. -->
    {@const bereich = grenzen[aufnahme.id]}
    {#if bereich}
    <div class="karte" class:markiert={markiert[aufnahme.id]}>
      <div class="reihe kopf">
        <label class="reihe schmal">
          <input type="checkbox" bind:checked={markiert[aufnahme.id]} />
          <span class="gedaempft">
            {(seite - 1) * proSeite + nummer + 1} · {aufnahme.dauer_s.toFixed(1)} s · {tag(
              aufnahme.erstellt,
            )}
          </span>
        </label>
        <span class="wachsen"></span>
        {#if aufnahme.zuschnitt_start_s !== null}
          <span class="geschnitten">zugeschnitten</span>
        {/if}
        <!-- Zwei Knöpfe, zwei Zeichen: das volle Dreieck für die ganze
             Aufnahme, das Dreieck zwischen zwei Begrenzern für den Ausschnitt.
             Beschriftet sind beide trotzdem, für Vorlesegeräte und für die
             Maus, die kurz darauf stehen bleibt. -->
        <button
          class="knopf zeichen"
          title="Ganze Aufnahme anhören"
          aria-label="Ganze Aufnahme anhören"
          onclick={() => hoere(aufnahme, false)}
        >
          {#if spielt === `${aufnahme.id}:false`}
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
          title="Nur den Ausschnitt anhören"
          aria-label="Nur den Ausschnitt anhören"
          onclick={() => hoere(aufnahme, true)}
        >
          {#if spielt === `${aufnahme.id}:true`}
            <svg viewBox="0 0 16 16" aria-hidden="true"
              ><rect x="0.5" y="2" width="1.5" height="12" class="grenze" /><rect
                x="14"
                y="2"
                width="1.5"
                height="12"
                class="grenze"
              /><rect x="4.5" y="4" width="2.5" height="8" /><rect
                x="9"
                y="4"
                width="2.5"
                height="8"
              /></svg
            >
          {:else}
            <svg viewBox="0 0 16 16" aria-hidden="true"
              ><rect x="0.5" y="2" width="1.5" height="12" class="grenze" /><rect
                x="14"
                y="2"
                width="1.5"
                height="12"
                class="grenze"
              /><path d="M5 4 L11.5 8 L5 12 Z" /></svg
            >
          {/if}
        </button>
      </div>

      <Pegelverlauf
        verlauf={aufnahme.verlauf}
        fensterS={aufnahme.fenster_s}
        schwelle={aufnahme.schwelle}
        dauerS={aufnahme.dauer_s}
        bind:start={bereich.start}
        bind:ende={bereich.ende}
        beschriftung="Ausschnitt {nummer + 1}"
      />

      <p class="vorlage">{aufnahme.text}</p>

      <div class="reihe schmal">
        <button class="knopf klein" onclick={() => aufVorschlag(aufnahme)}>Vorschlag</button>
        <button class="knopf klein" onclick={() => ganzeAufnahme(aufnahme)}>Ganze Aufnahme</button>
        <!-- In eine eigene Ansicht, nicht in die Karte: Dort braucht es eine
             dritte Linie und einen teilbaren Text, und beides passte nicht
             neben neun andere Karten. -->
        <button class="knopf klein" onclick={() => gehZu(`${EDITIEREN_ROUTE}${aufnahme.id}`)}
          >Editieren …</button
        >
      </div>
    </div>
    {/if}
  {:else}
    <p class="gedaempft">Keine Aufnahme, die sich zuschneiden ließe.</p>
  {/each}

  <Pager {seite} gesamtSeiten={seiten} aendere={blaettere} />

  <div class="karte abschluss">
    <div class="reihe">
      <button
        class="knopf haupt"
        disabled={!anzahlMarkiert || laeuft !== ''}
        onclick={schreibe}
      >
        {laeuft === 'schreiben'
          ? 'Wird geschrieben …'
          : `Zuschnitt schreiben (${anzahlMarkiert})`}
      </button>
      <button class="knopf" disabled={!anzahlMarkiert || laeuft !== ''} onclick={nimmZurueck}>
        {laeuft === 'zurueck' ? 'Wird zurückgenommen …' : 'Zuschnitt zurücknehmen'}
      </button>
      <button
        class="knopf gefahr"
        disabled={!anzahlMarkiert || laeuft !== ''}
        onclick={loesche}
      >
        {laeuft === 'loeschen' ? 'Wird gelöscht …' : `Löschen (${anzahlMarkiert})`}
      </button>
    </div>
    <p class="gedaempft">
      Geschrieben wird eine zweite Datei neben dem Original; das Original bleibt unverändert
      liegen. Ab dann arbeiten alle Apps mit der zugeschnittenen Fassung - beim Messen, beim
      Trainieren, beim Ausleiten und beim Anhören. Die bisherigen Messwerte der betroffenen
      Aufnahmen werden dabei verworfen, weil sie am ungeschnittenen Ton entstanden sind; der
      nächste Auswertungslauf rechnet sie neu.
    </p>
  </div>
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

  .schmal {
    gap: 0.4rem;
    align-items: center;
  }

  .werkzeuge {
    flex-wrap: wrap;
    align-items: center;
    gap: 0.75rem;
  }

  .kopf {
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  /* Eine markierte Karte trägt den Akzent am linken Rand statt einer Färbung:
     Die Kurve darin ist selbst schon farbig, und ein zweiter Hintergrund
     darunter nähme ihr den Kontrast. */
  .karte.markiert {
    border-left: 4px solid var(--akzent);
  }

  .geschnitten {
    color: var(--warnung);
    font-size: 0.8rem;
    border: 1px solid var(--warnung);
    border-radius: 0.3rem;
    padding: 0.05rem 0.4rem;
  }

  /* Die Vorlage steht unter der Kurve und ist das, wogegen gehört wird -
     also lesbar groß, nicht als Fußnote. */
  .vorlage {
    margin: 0.5rem 0;
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

  /* Wie „Löschen" in der Einsicht der Aufsicht: derselbe Knopf, nur mit rotem
     Rand - er soll nicht lauter sein als „Zuschnitt schreiben", nur anders. */
  .gefahr {
    border-color: var(--fehler);
  }
</style>
