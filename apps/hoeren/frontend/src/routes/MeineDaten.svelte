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
   */
  import { fehlertext } from '$ui/api';
  import AudioPlayer from '$ui/AudioPlayer.svelte';
  import Kalender from '$ui/Kalender.svelte';
  import Pager from '$ui/Pager.svelte';
  import Papierkorb from '$ui/Papierkorb.svelte';
  import Warnzeichen from '$ui/Warnzeichen.svelte';
  import { ZUGANGSDATEN_PFAD, ZUSCHNITT_PFAD } from '$ui/apps';
  import { gueltigePin, merkePin, schloss, vergissPin } from '$ui/pin.svelte';
  import { datum, dauer, tag } from '$ui/zeit';
  import {
    aufnahmeVerwerfen,
    meinDatensatz,
    meinKonto,
    meineAufnahmeAudio,
    meineAufnahmen,
    meineSicherung,
    meineAufnahmezeiten,
    michUmbenennen,
    pinSetzen,
    pinStand,
    type AufsichtAufnahme,
    type Konto,
  } from '../lib/api';
  import { gehZu, lage } from '../lib/zustand.svelte';

  const PRO_SEITE = 10;

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
  const aufnahmenSeiten = $derived(Math.max(1, Math.ceil(aufnahmenGesamt / PRO_SEITE)));

  let fehler = $state('');
  let meldung = $state('');
  let laeuft = $state('');
  // Zu welcher Aufnahme gerade das Audio geladen ist. Nur eine auf einmal:
  // Der Browser hielte sonst Dutzende Aufnahmen im Speicher.
  let hoerprobe = $state<{ id: string; adresse: string } | null>(null);

  async function ladeZeiten() {
    zeiten = await meineAufnahmezeiten(meinePin);
  }

  async function ladeAufnahmen() {
    const seite = await meineAufnahmen((aufnahmenSeite - 1) * PRO_SEITE, PRO_SEITE, meinePin);
    aufnahmen = seite.aufnahmen;
    aufnahmenGesamt = seite.gesamt;
  }

  async function lade() {
    fehler = '';
    try {
      daten = await meinKonto(meinePin);
      await Promise.all([ladeZeiten(), ladeAufnahmen()]);
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
      await Promise.all([ladeZeiten(), ladeAufnahmen()]);
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

  async function wechsleAufnahmenSeite(seite: number) {
    aufnahmenSeite = seite;
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

  async function hoere(aufnahme: AufsichtAufnahme) {
    if (hoerprobe?.id === aufnahme.id) {
      URL.revokeObjectURL(hoerprobe.adresse);
      hoerprobe = null;
      return;
    }
    if (hoerprobe) URL.revokeObjectURL(hoerprobe.adresse);
    hoerprobe = null;
    await tue(
      `hoere-${aufnahme.id}`,
      async () => {
        const inhalt = await meineAufnahmeAudio(aufnahme.id);
        hoerprobe = { id: aufnahme.id, adresse: URL.createObjectURL(inhalt) };
      },
      '',
    );
  }

  async function verwirf(aufnahme: AufsichtAufnahme) {
    const anfang = aufnahme.text.slice(0, 60);
    if (
      !confirm(
        `Diese Aufnahme verwerfen?\n\n„${anfang}…“\n\nDer Text steht danach wieder zum Aufnehmen an.`,
      )
    )
      return;
    await tue(
      `verwerfen-${aufnahme.id}`,
      async () => {
        await aufnahmeVerwerfen(aufnahme.id);
        // Auch Kennzahlen und Kalender: Eine verworfene Aufnahme zählt nicht mehr.
        await lade();
      },
      'Aufnahme verworfen.',
    );
  }

  const megabyte = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`;

  // Der Weg in den Zuschnitt steht nur da, wenn der Server den
  // Bearbeitungsschlüssel annimmt (`lage.bearbeiten`) - eine Tür zeigen, die
  // 401 antwortet, ist keine Auskunft, sondern eine Sackgasse. Fehlt er nur,
  // steht ein Hinweis auf die Zugangsdaten da; ist der Zuschnitt
  // abgeschaltet, nichts.
  const zuschneidbar = $derived(lage.bearbeiten === 'gilt');

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
  <h2>Meine Daten</h2>
  <div class="karte">
    <p>Diese Seite ist mit einer PIN gesichert.</p>
    <p class="gedaempft">Geben Sie Ihre vierstellige PIN ein (4 Ziffern).</p>
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

  <!--
    Der Knopf steht beim Namen, denn der Name ist, was er ändert. Er stand
    einmal in der Karte darunter, zwischen „Sicherung" und „Datensatz" - unter
    der Überschrift „Ausleiten", die von zwei Dateien zum Herunterladen
    handelt. Umbenennen lädt nichts herunter; es war dort nur die dritte
    Handlung, die sonst nirgends hinpasste. Der erklärende Absatz derselben
    Karte nennt ihn bis heute nicht, und das war der Hinweis.
  -->
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

  <h2>Ausleiten</h2>
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
    <p class="gedaempft">
      <strong>Sicherung:</strong> Datenbank und Aufnahmen, zurückzuspielen mit
      <code>scripts/restore.py</code>. Ohne Messwerte - die rechnet ein Auswertungslauf
      neu.<br />
      <strong>Datensatz:</strong> je Aufnahme WAV und Text, für fremde Werkzeuge. Keine Sicherung.
    </p>
  </div>

  <!--
    Kurzes zuerst, Langes ans Ende. Die Aufnahmen sind eine Liste, die über
    Seiten läuft; alles, was man einmal einstellt, stünde dahinter außer
    Sicht. Die PIN stand dort - hinter allen Listen, am Ende einer Seite, die
    je nach Korpus sehr lang ist.

    Die Einsicht der Aufsicht hatte es schon richtig herum; jetzt sind beide
    Ansichten desselben Profils auch in der Reihenfolge dieselben.
  -->
  <h2>PIN</h2>
  <div class="karte">
    <p class="gedaempft">
      Eine PIN sichert diese Seite zusätzlich zum Zugang - gedacht gegen den Klick aus Versehen,
      nicht als zweites Passwort.
    </p>
    <p class="gedaempft">Geben Sie eine vierstellige PIN ein (4 Ziffern).</p>
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
    <p class="gedaempft">
      Anlegen, abstellen und löschen unter <a href="#/quelle">Textquelle</a>.
    </p>
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

  <h2>Aufnahmen</h2>
  <!--
    Der Weg in den Zuschnitt steht über der Liste und nicht bei „Ausleiten":
    Er handelt von genau diesen Aufnahmen, und wer sie gerade durchsieht, ist
    der, dem auffällt, dass vorn und hinten Stille steht. Ein eigener
    Menüpunkt wäre er nicht - die Ansicht dahinter ist eine Werkbank, keine
    Station auf dem täglichen Weg (siehe `ZUSCHNITT_PFAD` in `$ui/apps`).
  -->
  {#if zuschneidbar}
    <div class="karte">
      <div class="reihe">
        <button class="knopf" onclick={() => gehZu(ZUSCHNITT_PFAD)}>Zuschnitt öffnen</button>
      </div>
      <p class="gedaempft">
        Zwischen dem Druck auf den Aufnahmeknopf und dem ersten Laut liegt meist eine Sekunde,
        hinten oft mehr. Im Zuschnitt sehen Sie zu jeder Aufnahme den Lautstärkeverlauf und
        schneiden weg, was davor und dahinter steht. Der Zuschnitt überschreibt die Originale.
      </p>
    </div>
  {:else if lage.bearbeiten === 'fehlt' || lage.bearbeiten === 'falsch'}
    <p class="gedaempft">
      Zuschneiden und Editieren gehen mit dem Bearbeitungsschlüssel dieses Servers - einzutragen
      unter <a href="#{ZUGANGSDATEN_PFAD}">Zugangsdaten</a>.
    </p>
  {/if}
  {#each aufnahmen as aufnahme (aufnahme.id)}
    <div class="karte">
      <div class="reihe">
        <div style="flex:1">
          <div>{aufnahme.text}</div>
          <div class="gedaempft">
            {aufnahme.dauer_s.toFixed(1)} s · {aufnahme.modus} · {tag(aufnahme.erstellt)}
            {#if aufnahme.hinweise.length}<Warnzeichen hinweise={aufnahme.hinweise} />{/if}
            {#if aufnahme.status !== 'ok'}· <strong>{aufnahme.status}</strong>{/if}
          </div>
        </div>
        {#if aufnahme.audio_vorhanden}
          <button class="knopf" onclick={() => hoere(aufnahme)}>
            {hoerprobe?.id === aufnahme.id ? 'Zu' : '▶ Hören'}
          </button>
        {/if}
        {#if aufnahme.status === 'ok'}
          <Papierkorb
            title="Aufnahme verwerfen"
            label="Aufnahme verwerfen"
            disabled={laeuft === `verwerfen-${aufnahme.id}`}
            onclick={() => verwirf(aufnahme)}
          />
        {/if}
      </div>
      {#if hoerprobe?.id === aufnahme.id}
        <AudioPlayer quelle={hoerprobe.adresse} />
      {/if}
    </div>
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
