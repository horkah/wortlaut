<script lang="ts">
  /**
   * Ein Sprecher sieht seine eigenen Daten an - dieselbe Ansicht, die die
   * Aufsicht für ihn hätte (`Einsicht.svelte`), nur auf die eigene Kennung
   * beschränkt. Genau **eine** Karte von dort fehlt hier: die beiden
   * Löschstufen „alle Aufnahmen" und „diesen Sprecher vollständig". Und die
   * Textquellen stehen nur als Summe da, denn ein Sprecher hat - anders als
   * die Aufsicht - ihren eigenen Reiter „Textquelle". Alles Übrige darf
   * jeder über seine eigenen Daten - ansehen, anhören, eine einzelne Aufnahme
   * verwerfen (dasselbe Verwerfen wie beim Aufnehmen, `Aufnahme.svelte`),
   * sich umbenennen und beides mitnehmen, Sicherung wie Datensatz.
   *
   * **Zurück aus dem Editor steht die Seite, wie sie war**: dieselbe Seite der
   * Liste, dieselbe Karte offen, dieselbe Stelle im Fenster (`lib/rueckkehr`).
   */
  import { tick } from 'svelte';
  import { erklaert } from '$ui/erklaerung';
  import { fehlertext } from '$ui/api';
  import Kalender from '$ui/Kalender.svelte';
  import Aufnahmekarte from '$ui/Aufnahmekarte.svelte';
  import Listenwahl from '../lib/Listenwahl.svelte';
  import { merke, nimmStelle, type Reihenfolge, type Stelle } from '$ui/rueckkehr';
  import Pager from '$ui/Pager.svelte';
  import { EDITIEREN_ROUTE } from '$ui/apps';
  import { gueltigePin, merkePin, schloss, vergissPin } from '$ui/pin.svelte';
  import { datum, dauer, tag } from '$ui/zeit';
  import {
    meinDatensatz,
    meinKonto,
    meineAufnahmen,
    meineReihenfolge,
    VORGABE_ARTEN,
    meineSicherung,
    meineAufnahmezeiten,
    michUmbenennen,
    pinSetzen,
    pinStand,
    type AufsichtAufnahme,
    type Konto,
    type Aufnahmenseite,
    type Guteskala,
    type Listenwahl as Wahl,
    type Quellenwahl,
  } from '../lib/api';
  import { gehZu, lage } from '../lib/zustand.svelte';

  // Wie die Liste steht - gemerkt in diesem Browser, eine Bequemlichkeit.
  const LISTE = 'wortlaut.meine-daten.liste';
  const VORGABE: { wahl: Wahl; proSeite: number } = {
    wahl: { quelle: '', arten: VORGABE_ARTEN, sortierung: 'geaendert', richtung: 'ab' },
    proSeite: 10,
  };

  function gemerkteListe(): typeof VORGABE {
    try {
      const roh = localStorage.getItem(LISTE);
      if (!roh) return VORGABE;
      const gelesen = JSON.parse(roh) as Partial<typeof VORGABE>;
      const wahl = { ...VORGABE.wahl, ...gelesen.wahl };
      return {
        wahl: {
          quelle: wahl.quelle,
          arten: Array.isArray(wahl.arten) ? wahl.arten : VORGABE.wahl.arten,
          sortierung: wahl.sortierung,
          richtung: wahl.richtung,
        },
        proSeite: [10, 20, 50, 100].includes(Number(gelesen.proSeite))
          ? Number(gelesen.proSeite)
          : VORGABE.proSeite,
      };
    } catch {
      return VORGABE;
    }
  }

  const gemerkt = gemerkteListe();
  let wahl = $state<Wahl>(gemerkt.wahl);
  let proSeite = $state(gemerkt.proSeite);
  let quellen = $state<Quellenwahl[]>([]);
  let arten = $state<Aufnahmenseite['arten']>([]);
  let skala = $state<Guteskala>({ rot: 50, gruen: 85 });
  let modell = $state('');

  /**
   * In den Editor: Stelle und Reihenfolge der Liste merken (`lib/rueckkehr`).
   * Die Reihenfolge ist die ganze Liste, nicht nur diese Seite - der Editor
   * blättert darin. Kommt sie nicht, blättert er eben nicht.
   */
  async function oeffneEditor(kennung: string) {
    let folge: Reihenfolge | null = null;
    try {
      folge = { eintraege: await meineReihenfolge(wahl, meinePin), proSeite };
    } catch {
      folge = null;
    }
    merke({ seite: aufnahmenSeite, aufgeklappt, y: window.scrollY }, folge);
    gehZu(`${EDITIEREN_ROUTE}${kennung}`);
  }

  /**
   * Zurück aus dem Editor, sortiert nach „Editiert" oder „Genauigkeit": Die
   * bearbeitete Aufnahme ist jetzt woanders - die Liste sortiert neu und geht
   * zu ihr. Ist sie fort (geteilt), steht die Liste oben.
   */
  async function neueStelle(stelle: Stelle | null): Promise<Stelle | null> {
    if (!stelle || wahl.sortierung === 'aufgenommen') return stelle;
    try {
      const folge = await meineReihenfolge(wahl, meinePin);
      const nummer = folge.findIndex((eintrag) => eintrag.id === stelle.aufgeklappt);
      if (nummer < 0) return { seite: 1, aufgeklappt: null, y: 0 };
      return { seite: Math.floor(nummer / proSeite) + 1, aufgeklappt: stelle.aufgeklappt, y: null };
    } catch {
      return stelle;
    }
  }

  /** Nach dem Laden: Karte wieder auf, Fenster an die alte Stelle - oder zur Karte. */
  async function kehreZurueck(stelle: Stelle) {
    const karte = aufnahmen.find((aufnahme) => aufnahme.id === stelle.aufgeklappt);
    if (karte) klappe(karte);
    await tick();
    if (stelle.y !== null) window.scrollTo(0, stelle.y);
    else document.getElementById(`aufnahme-${stelle.aufgeklappt}`)?.scrollIntoView({ block: 'center' });
  }

  // Ob und womit diese Seite offen ist. `noetig` heißt: eine PIN ist gesetzt
  // und noch nicht eingegeben. Die PIN selbst liegt nur hier im Speicher,
  // nie in `localStorage` - dort steht schon der Zugang, und ein zweites
  // dauerhaft gemerktes Geheimnis nähme der PIN genau den Sinn, den sie haben
  // soll (siehe `services/pin.py`).
  //
  // Geteilt wird die eingegebene PIN trotzdem, und zwar mit „Darstellung" und
  // „Zugangsdaten" (`$ui/pin.svelte`): Es ist dieselbe PIN, derselbe Mensch
  // und dieselbe Sitzung - zweimal tippen wäre keine zweite Sicherheit,
  // sondern nur eine zweite Gelegenheit, sie zu vergessen.
  let stand = $state<'unbekannt' | 'noetig' | 'offen'>('unbekannt');
  let meinePin = $state<string | undefined>(undefined);
  let pinEingabe = $state('');
  let pinFehler = $state('');
  // Getrennt von `pinEingabe`: Die Verwaltung der eigenen PIN ist ein anderes
  // Formular, das erst zu sehen ist, wenn diese Seite schon offen ist.
  let neuePin = $state('');

  let daten = $state<Konto | null>(null);

  // Wann jede gültige Aufnahme entstand (UTC, älteste zuerst) - Stoff für
  // die Zeile über den Sitzungen und den Kalender darunter.
  let zeiten = $state<string[]>([]);
  // Je Tag in der Zeitzone des Betrachters, wie viele es waren.
  const proTag = $derived.by(() => {
    const zaehlung = new Map<string, number>();
    for (const zeit of zeiten) {
      const schluessel = tag(zeit);
      zaehlung.set(schluessel, (zaehlung.get(schluessel) ?? 0) + 1);
    }
    return zaehlung;
  });

  let aufnahmen = $state<AufsichtAufnahme[]>([]);
  let aufnahmenSeite = $state(1);
  let aufnahmenGesamt = $state(0);
  const aufnahmenSeiten = $derived(Math.max(1, Math.ceil(aufnahmenGesamt / proSeite)));

  let fehler = $state('');
  let meldung = $state('');
  let laeuft = $state('');
  // Welche Karte aufgeklappt ist. Nur eine auf einmal: Der Browser hielte
  // sonst Dutzende Aufnahmen im Speicher.
  let aufgeklappt = $state<string | null>(null);

  async function ladeZeiten() {
    zeiten = await meineAufnahmezeiten(meinePin);
  }

  async function ladeAufnahmen() {
    const seite = await meineAufnahmen((aufnahmenSeite - 1) * proSeite, proSeite, wahl, meinePin);
    aufnahmen = seite.aufnahmen;
    aufnahmenGesamt = seite.gesamt;
    quellen = seite.quellen;
    arten = seite.arten;
    skala = seite.skala;
    modell = seite.modell;
  }

  async function lade() {
    fehler = '';
    const stelle = await neueStelle(nimmStelle());
    if (stelle) aufnahmenSeite = stelle.seite;
    try {
      daten = await meinKonto(meinePin);
      await Promise.all([ladeZeiten(), ladeAufnahmen()]);
      if (stelle) await kehreZurueck(stelle);
    } catch (ursache) {
      fehler = fehlertext(ursache);
    }
  }

  /** Ob eine PIN nötig ist, und danach, falls nicht, gleich laden. */
  async function starte() {
    fehler = '';
    try {
      if (!(await pinStand()).gesetzt) {
        stand = 'offen';
      } else if (schloss.pin) {
        // Anderswo in dieser Sitzung schon eingegeben und geprüft.
        meinePin = schloss.pin;
        stand = 'offen';
      } else {
        stand = 'noetig';
      }
      if (stand === 'offen') await lade();
    } catch (ursache) {
      fehler = fehlertext(ursache);
    }
  }

  async function entsperren(ereignis: SubmitEvent) {
    ereignis.preventDefault();
    pinFehler = '';

    if (!gueltigePin(pinEingabe)) {
      pinFehler = 'Die PIN muss aus genau 4 Ziffern bestehen.';
      return;
    }

    try {
      // Ein Testabruf: Er wirft, wenn die PIN nicht stimmt, und sagt damit
      // beides in einem - ob sie stimmt und, wenn ja, gleich die Daten.
      daten = await meinKonto(pinEingabe);
      meinePin = pinEingabe;
      merkePin(pinEingabe);
      pinEingabe = '';
      stand = 'offen';
      await lade();
    } catch {
      pinFehler = 'Falsche PIN.';
    }
  }

  async function pinAendern(ereignis: SubmitEvent) {
    ereignis.preventDefault();
    const neue = neuePin.trim();

    if (!gueltigePin(neue)) {
      fehler = 'Die PIN muss aus genau 4 Ziffern bestehen.';
      return;
    }

    // Nach dem Einrichten sperrt die Seite gleich wieder: Wer die PIN einmal
    // tippt, merkt sie sich - und ein Vertipper fällt sofort auf.
    const ersteinrichtung = !meinePin;

    await tue(
      'pin',
      async () => {
        await pinSetzen(neue);
        neuePin = '';
        // Die gemerkte PIN stimmt jetzt nicht mehr; die anderen Ansichten
        // fragen von Neuem nach (`$ui/pin.svelte`).
        vergissPin();
        if (ersteinrichtung) {
          meinePin = undefined;
          daten = null;
          stand = 'noetig';
        } else {
          meinePin = neue;
          merkePin(neue);
        }
      },
      ersteinrichtung
        ? 'PIN gesetzt. Bitte einmal mit der neuen PIN entsperren.'
        : 'PIN geändert.',
    );
  }

  async function pinWegnehmen() {
    await tue(
      'pin',
      async () => {
        await pinSetzen(null);
        meinePin = undefined;
        vergissPin();
      },
      'PIN entfernt.',
    );
  }

  async function benenneUm() {
    if (!daten) return;
    const neuer = prompt('Neuer Name:', daten.sprecher.name);
    if (neuer === null || !neuer.trim()) return;
    await tue(
      'umbenennen',
      async () => {
        await michUmbenennen(neuer.trim(), meinePin);
        await lade();
      },
      'Umbenannt.',
    );
  }

  /** Sortierung, Filter oder Seitengröße geändert: gemerkt, und von vorn. */
  async function neueListe() {
    try {
      localStorage.setItem(LISTE, JSON.stringify({ wahl, proSeite }));
    } catch {
      // Ohne Speicher gilt die Wahl bis zum Neuladen - kein Fehlerfall.
    }
    await wechsleAufnahmenSeite(1);
  }

  async function wechsleAufnahmenSeite(seite: number) {
    aufnahmenSeite = seite;
    aufgeklappt = null;
    try {
      await ladeAufnahmen();
    } catch (ursache) {
      fehler = fehlertext(ursache);
    }
  }

  /** Ein Knopf, der arbeitet: sperren, tun, entsperren - und Fehler zeigen. */
  async function tue(name: string, arbeit: () => Promise<void>, danach = 'Fertig.') {
    fehler = '';
    meldung = '';
    laeuft = name;
    try {
      await arbeit();
      meldung = danach;
    } catch (ursache) {
      fehler = fehlertext(ursache);
    } finally {
      laeuft = '';
    }
  }

  /** Auf- oder zuklappen - aufgeklappt holt die Karte ihre Wellenform. */
  function klappe(aufnahme: AufsichtAufnahme) {
    aufgeklappt = aufgeklappt === aufnahme.id ? null : aufnahme.id;
  }

  /** Gelöscht: Auch Kennzahlen und Kalender - eine verworfene Aufnahme zählt nicht mehr. */
  async function verworfen() {
    aufgeklappt = null;
    await tue('verwerfen', lade, 'Aufnahme gelöscht.');
  }

  const megabyte = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`;

  // Der Knopf in den Editor steht nur da, wenn der Server den
  // Bearbeitungsschlüssel annimmt (`lage.bearbeiten`) - eine Tür zeigen, die
  // 401 antwortet, ist keine Auskunft, sondern eine Sackgasse.
  const bearbeitbar = $derived(lage.bearbeiten === 'gilt');

  $effect(() => {
    if (lage.art === 'sprecher') starte();
  });

</script>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}
{#if meldung}
  <p class="gedaempft">{meldung}</p>
{/if}

{#if stand === 'noetig'}
  <h2
    use:erklaert={'Die vierstellige PIN, die unter „Meine Daten“ vergeben wurde. Wer sie vergessen hat, lässt sie von der Aufsicht zurücksetzen.'}
  >
    Meine Daten
  </h2>
  <div class="karte">
    <p>Diese Seite ist mit einer PIN gesichert.</p>
    <form class="reihe" onsubmit={entsperren}>
      <!-- `pattern` als Ausdruck, nicht als Text: In einer Vorlage ist `{4}`
           eine Einsetzung, `pattern="[0-9]{4}"` käme als `[0-9]4` beim Browser
           an - und der wiese dann jede richtige PIN ab, ohne dass `onsubmit`
           je liefe. -->
      <input
        bind:value={pinEingabe}
        type="text"
        inputmode="numeric"
        pattern={'[0-9]{4}'}
        maxlength="4"
        placeholder="z.B. 1234"
        title="Genau 4 Ziffern (0–9)"
        autocomplete="off"
        required
      />
      <button class="knopf haupt" type="submit">Entsperren</button>
    </form>
    {#if pinFehler}<p class="fehler">{pinFehler}</p>{/if}
  </div>
{:else if stand === 'unbekannt' || !daten}
  <p class="gedaempft">Wird geladen …</p>
{:else}
  {@const person = daten.sprecher}
  {@const zahlen = person.kennzahlen}
  {@const quellen = daten.quellen}
  {@const aktiv = quellen.filter((quelle) => quelle.aktiv).length}
  {@const einheiten = quellen.reduce((summe, quelle) => summe + quelle.einheiten, 0)}

  <!-- Der Knopf steht beim Namen, denn der Name ist, was er ändert. -->
  <div class="reihe titel">
    <h2>{person.name}</h2>
    <button class="knopf" disabled={laeuft === 'umbenennen'} onclick={benenneUm}>
      Umbenennen
    </button>
  </div>
  <p class="gedaempft">
    {person.sprache} · angelegt am {tag(person.erstellt)}
  </p>

  <div class="karte zahlen">
    <div><strong>{zahlen.aufnahmen}</strong><span>Aufnahmen</span></div>
    <div><strong>{dauer(zahlen.sekunden)}</strong><span>gesprochen</span></div>
    <div><strong>{megabyte(zahlen.bytes_audio)}</strong><span>Audio</span></div>
    <div><strong>{zahlen.einheiten}</strong><span>Einheiten</span></div>
    <div><strong>{zahlen.quellen}</strong><span>Textquellen</span></div>
    <div><strong>{zahlen.sitzungen}</strong><span>Sitzungen</span></div>
    <div><strong>{zahlen.verworfen}</strong><span>verworfen</span></div>
  </div>

  <h2 use:erklaert={'Sicherung: Datenbank und Aufnahmen, zurückzuspielen mit scripts/restore.py - ohne Messwerte, die rechnet die Auswertung neu. Datensatz: je Aufnahme WAV und Text, für fremde Werkzeuge; keine Sicherung.'}>Ausleiten</h2>
  <div class="karte">
    <div class="reihe">
      <button
        class="knopf haupt"
        disabled={laeuft === 'sicherung'}
        onclick={() =>
          tue('sicherung', () => meineSicherung(meinePin), 'Sicherung heruntergeladen.')}
      >
        {laeuft === 'sicherung' ? 'Wird gepackt …' : 'Sicherung (.tgz)'}
      </button>
      <button
        class="knopf"
        disabled={laeuft === 'datensatz'}
        onclick={() =>
          tue('datensatz', () => meinDatensatz(meinePin), 'Datensatz heruntergeladen.')}
      >
        {laeuft === 'datensatz' ? 'Wird gepackt …' : 'Datensatz (.zip)'}
      </button>
    </div>
  </div>

  <!--
    Kurzes zuerst, Langes ans Ende: Die Aufnahmen sind eine Liste, die über
    Seiten läuft; alles, was man einmal einstellt, stünde dahinter außer
    Sicht. Dieselbe Reihenfolge wie in der Einsicht der Aufsicht.
  -->
  <h2
    use:erklaert={'Vier Ziffern, die diese Seite zusätzlich zum Zugang sichern - gegen den Klick aus Versehen, nicht als zweites Passwort.'}
  >
    PIN
  </h2>
  <div class="karte">
    <form class="reihe" onsubmit={pinAendern}>
      <input
        bind:value={neuePin}
        type="text"
        inputmode="numeric"
        pattern={'[0-9]{4}'}
        maxlength="4"
        placeholder="z.B. 1234"
        title="Genau 4 Ziffern (0–9)"
        autocomplete="off"
        required
      />
      <button class="knopf haupt" type="submit" disabled={laeuft === 'pin'}>
        {meinePin ? 'PIN ändern' : 'PIN einrichten'}
      </button>
      {#if meinePin}
        <button class="knopf" type="button" disabled={laeuft === 'pin'} onclick={pinWegnehmen}>
          PIN entfernen
        </button>
      {/if}
    </form>
  </div>

  <!--
    Nur die Summe, nicht die Liste: Die Quellen selbst stehen im Reiter
    „Textquelle", und dort kann man auch etwas mit ihnen tun - abstellen,
    wieder aufnehmen, löschen. Eine zweite, stumme Abschrift hier hieße, zwei
    Listen gleich zu halten, und zeigte doch nur weniger.
  -->
  <h2>Textquellen</h2>
  <div class="karte">
    {#if quellen.length}
      <p>
        {quellen.length}
        {quellen.length === 1 ? 'Textquelle' : 'Textquellen'} mit zusammen {einheiten} Einheiten -
        {aktiv} aktiv, {quellen.length - aktiv} abgestellt.
      </p>
    {:else}
      <p>Noch keine Textquelle.</p>
    {/if}
    <p><a href="#/quelle">Textquellen verwalten</a></p>
  </div>

  <!--
    Eine Zeile statt einer Liste: Die Sitzungen einzeln aufzuzählen sagte
    Zeile für Zeile, was der Kalender darunter auf einen Blick zeigt - an
    welchen Tagen geübt wurde. Gezählt wird wie in den Kennzahlen oben.
  -->
  <h2>Sitzungen</h2>
  <div class="karte">
    {#if zeiten.length}
      {@const von = datum(zeiten[0])}
      {@const bis = datum(zeiten[zeiten.length - 1])}
      <p class="sitzungszeile">
        {zahlen.sitzungen}
        {zahlen.sitzungen === 1 ? 'Sitzung' : 'Sitzungen'}
        {von === bis ? `am ${von}` : `im Zeitraum ${von} – ${bis}`} mit insgesamt
        {zahlen.aufnahmen}
        {zahlen.aufnahmen === 1 ? 'Aufnahme' : 'Aufnahmen'}.
      </p>
      <Kalender tage={proTag} />
    {:else}
      <p>Noch keine Aufnahme.</p>
    {/if}
  </div>

  <h2
    use:erklaert={'Ein Tippen auf eine Aufnahme klappt sie auf: zum Anhören und Löschen, und mit dem Bearbeitungsschlüssel aus den Zugangsdaten auch zum Bearbeiten - zuschneiden, teilen, den Text berichtigen. Ein zweites Tippen klappt sie wieder zu. Gelöscht wird nur die Aufnahme; ihr Text steht wieder zum Aufnehmen an.'}
  >
    Aufnahmen
  </h2>
  <Listenwahl
    bind:wahl
    bind:proSeite
    {quellen}
    {arten}
    gesamt={aufnahmenGesamt}
    aendere={neueListe}
  />
  {#each aufnahmen as aufnahme (aufnahme.id)}
    <Aufnahmekarte
      {aufnahme}
      {skala}
      {modell}
      offen={aufgeklappt === aufnahme.id}
      {bearbeitbar}
      onklappe={() => klappe(aufnahme)}
      onbearbeite={() => oeffneEditor(aufnahme.id)}
      onverworfen={verworfen}
      onfehler={(text) => (fehler = text)}
    />
  {:else}
    <p class="gedaempft">Keine Aufnahme.</p>
  {/each}
  <Pager seite={aufnahmenSeite} gesamtSeiten={aufnahmenSeiten} aendere={wechsleAufnahmenSeite} />
{/if}

<style>
  /* Überschrift und Knopf in einer Zeile, ohne dass der Knopf die Grundlinie
     der Überschrift verschiebt. Der eigene Abstand oben ersetzt den, den `h2`
     global mitbringt und hier verliert. */
  .titel {
    justify-content: space-between;
    align-items: baseline;
    margin-top: 2rem;
  }
  .titel h2 {
    margin: 0;
  }
  .sitzungszeile {
    margin: 0 0 1.25rem;
  }
  /* Die Kennzahlen als Reihe kleiner Blöcke: Sie werden überflogen, nicht
     gelesen - die Zahl groß, ihre Bedeutung klein darunter. */
  .zahlen {
    display: flex;
    flex-wrap: wrap;
    gap: 1.5rem;
  }

  .zahlen > div {
    display: flex;
    flex-direction: column;
  }

  .zahlen strong {
    font-size: 1.3rem;
  }

  .zahlen span {
    color: var(--gedaempft);
    font-size: 0.85rem;
  }
</style>
