<script lang="ts">
  /**
   * Die Aufsicht sieht **einen** Sprecher an: was in seiner Datenbank steht,
   * und was sich damit tun lässt.
   *
   * Immer nur einer. Eine Ansicht, die alle Aufnahmen aller Personen
   * nebeneinanderlegt, lädt dazu ein, quer darüber zu löschen - und das ist
   * genau der Griff, den es hier nicht geben soll. Wer zwei Korpora ansehen
   * will, öffnet sie nacheinander.
   */
  import AudioPlayer from '$ui/AudioPlayer.svelte';
  import Pager from '$ui/Pager.svelte';
  import { dauer, tag, tagUndZeit } from '$ui/zeit';
  import {
    alleAufnahmenLoeschen,
    aufnahmeAudio,
    aufnahmeLoeschen,
    aufsichtAufnahmen,
    aufsichtSitzungen,
    datensatzSprecher,
    einsicht as ladeEinsicht,
    pinSetzenAdmin,
    sicherungSprecher,
    sprecherLoeschen,
    sprecherUmbenennen,
    type AufsichtAufnahme,
    type AufsichtSitzung,
    type Einsicht,
  } from '../lib/api';
  import { gehZu, lage, sprecherAusRoute } from '../lib/zustand.svelte';

  // Wie viele Zeilen eine Seite hat - für Sitzungen und Aufnahmen gleich, denn
  // beides sind Listen derselben Art (siehe `Pager.svelte`).
  const PRO_SEITE = 10;

  const sprecherId = $derived(sprecherAusRoute(lage.route));

  let daten = $state<Einsicht | null>(null);
  let neuePin = $state('');

  let sitzungen = $state<AufsichtSitzung[]>([]);
  let sitzungenSeite = $state(1);
  let sitzungenGesamt = $state(0);
  const sitzungenSeiten = $derived(Math.max(1, Math.ceil(sitzungenGesamt / PRO_SEITE)));

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

  async function ladeSitzungen() {
    const seite = await aufsichtSitzungen(sprecherId, (sitzungenSeite - 1) * PRO_SEITE, PRO_SEITE);
    sitzungen = seite.sitzungen;
    sitzungenGesamt = seite.gesamt;
  }

  async function ladeAufnahmen() {
    const seite = await aufsichtAufnahmen(sprecherId, (aufnahmenSeite - 1) * PRO_SEITE, PRO_SEITE);
    aufnahmen = seite.aufnahmen;
    aufnahmenGesamt = seite.gesamt;
  }

  async function lade() {
    fehler = '';
    try {
      daten = await ladeEinsicht(sprecherId);
      await Promise.all([ladeSitzungen(), ladeAufnahmen()]);
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  async function wechsleSitzungenSeite(seite: number) {
    sitzungenSeite = seite;
    try {
      await ladeSitzungen();
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  async function wechsleAufnahmenSeite(seite: number) {
    aufnahmenSeite = seite;
    try {
      await ladeAufnahmen();
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
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
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
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
    await tue(`hoere-${aufnahme.id}`, async () => {
      const inhalt = await aufnahmeAudio(sprecherId, aufnahme.id);
      hoerprobe = { id: aufnahme.id, adresse: URL.createObjectURL(inhalt) };
    }, '');
  }

  async function benenneUm() {
    if (!daten) return;
    const neuer = prompt('Neuer Name für diesen Sprecher:', daten.sprecher.name);
    if (neuer === null || !neuer.trim()) return;
    await tue('umbenennen', async () => {
      await sprecherUmbenennen(sprecherId, neuer.trim());
      await lade();
    }, 'Umbenannt.');
  }

  /**
   * PIN setzen oder ändern - ohne die alte zu kennen. Die Aufsicht ist der
   * Rückweg, wenn jemand seine PIN vergessen oder aus Versehen eine falsche
   * eingetippt hat (siehe `services/pin.py`).
   */
  async function pinAendern(ereignis: SubmitEvent) {
    ereignis.preventDefault();
    const neue = neuePin.trim();

    // Validierung: genau 4 Ziffern
    if (!neue || neue.length !== 4 || !/^[0-9]{4}$/.test(neue)) {
      fehler = 'Die PIN muss aus genau 4 Ziffern bestehen.';
      return;
    }

    await tue('pin', async () => {
      await pinSetzenAdmin(sprecherId, neue);
      neuePin = '';
      await lade();
    }, 'PIN gespeichert.');
  }

  async function pinWegnehmen() {
    await tue('pin', async () => {
      await pinSetzenAdmin(sprecherId, null);
      await lade();
    }, 'PIN entfernt.');
  }

  async function loescheEine(aufnahme: AufsichtAufnahme) {
    const anfang = aufnahme.text.slice(0, 60);
    if (!confirm(`Diese Aufnahme endgültig löschen?\n\n„${anfang}…“`)) return;
    await tue(`loesche-${aufnahme.id}`, async () => {
      await aufnahmeLoeschen(sprecherId, aufnahme.id);
      await lade();
    }, 'Aufnahme gelöscht.');
  }

  async function loescheAlleAufnahmen() {
    if (!daten) return;
    const name = daten.sprecher.name;
    if (
      !confirm(
        `Alle ${aufnahmenGesamt} Aufnahmen von „${name}“ endgültig löschen?\n\n` +
          'Profil, Textquellen und Warteschlange bleiben stehen - gesprochen ist danach nichts ' +
          'mehr. Das lässt sich nicht rückgängig machen.',
      )
    )
      return;
    if (!bestaetigeMitNamen(name)) return;
    await tue('leeren', async () => {
      const ergebnis = await alleAufnahmenLoeschen(sprecherId);
      aufnahmenSeite = 1;
      await lade();
      meldung = `${ergebnis.geloescht} Aufnahme(n) gelöscht.`;
    }, '');
  }

  async function loescheSprecher() {
    if (!daten) return;
    const name = daten.sprecher.name;
    if (
      !confirm(
        `„${name}“ vollständig löschen?\n\n` +
          'Profil, Aufnahmen, Textquellen, Diktate, Modellstände und Schnappschüsse. ' +
          'Das lässt sich nicht rückgängig machen - vorher eine Sicherung ziehen.',
      )
    )
      return;
    if (!bestaetigeMitNamen(name)) return;
    await tue('loeschen', async () => {
      await sprecherLoeschen(sprecherId);
      gehZu('/sprecher');
    }, '');
  }

  /**
   * Die zweite Frage, und die verlangt Tippen.
   *
   * Ein zweites „Wirklich?" klickt man weg, ohne es gelesen zu haben. Den
   * Namen abzuschreiben zwingt dazu, hinzusehen, wen es trifft - und genau
   * diese Verwechslung ist der Fehler, den es hier zu verhindern gilt.
   */
  function bestaetigeMitNamen(name: string): boolean {
    const getippt = prompt(`Zur Bestätigung den Namen abschreiben: ${name}`);
    if (getippt === null) return false;
    if (getippt.trim() !== name) {
      fehler = 'Der Name stimmt nicht - es wurde nichts gelöscht.';
      return false;
    }
    return true;
  }

  const megabyte = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`;

  $effect(() => {
    if (lage.art === 'aufsicht' && sprecherId) lade();
  });
</script>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}
{#if meldung}
  <p class="gedaempft">{meldung}</p>
{/if}

{#if !daten}
  <p class="gedaempft">Wird geladen …</p>
{:else}
  {@const person = daten.sprecher}
  {@const zahlen = person.kennzahlen}

  <div class="reihe kopf">
    <button class="knopf" onclick={() => gehZu('/sprecher')}>← Alle Sprecher</button>
  </div>

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
    {person.id} · {person.sprache} · angelegt am {tag(person.erstellt)}
    {#if person.zugang_erneuert}
      · Zugang vom {tag(person.zugang_erneuert)}
    {:else}
      · kein Zugang - für niemanden erreichbar
    {/if}
    · PIN {person.pin_gesetzt ? 'gesetzt' : 'nicht gesetzt'}
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
          tue('sicherung', () => sicherungSprecher(sprecherId), 'Sicherung heruntergeladen.')}
      >
        {laeuft === 'sicherung' ? 'Wird gepackt …' : 'Sicherung (.tgz)'}
      </button>
      <button
        class="knopf"
        disabled={laeuft === 'datensatz'}
        onclick={() =>
          tue('datensatz', () => datensatzSprecher(sprecherId), 'Datensatz heruntergeladen.')}
      >
        {laeuft === 'datensatz' ? 'Wird gepackt …' : 'Datensatz (.zip)'}
      </button>
    </div>
    <p class="gedaempft">
      <strong>Sicherung:</strong> Datenbank und Aufnahmen, zurückzuspielen mit
      <code>scripts/restore.py</code>. Ohne Abwandlungen und Messwerte - die rechnet ein
      Auswertungslauf neu.<br />
      <strong>Datensatz:</strong> je Aufnahme WAV und Text, für fremde Werkzeuge. Keine Sicherung.
    </p>
  </div>

  <h2>PIN vor „Meine Daten"</h2>
  <div class="karte">
    <p class="gedaempft">
      Sichert die Ansicht, in der diese Person ihre eigenen Daten sieht - gegen den Klick aus
      Versehen, nicht als zweites Passwort. Setzen oder ändern verlangt die alte PIN nicht: Das
      ist der Rückweg, wenn sie vergessen wurde.
    </p>
    <p class="gedaempft">Geben Sie eine vierstellige PIN ein (4 Ziffern).</p>
    <form class="reihe" onsubmit={pinAendern}>
      <!-- `pattern` als Ausdruck, nicht als Text: In einer Vorlage ist `{4}`
           eine Einsetzung, `pattern="[0-9]{4}"` käme als `[0-9]4` beim Browser
           an - und der wiese dann jede richtige PIN ab, ohne dass `onsubmit`
           je liefe. -->
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
        {person.pin_gesetzt ? 'PIN ändern' : 'PIN einrichten'}
      </button>
      {#if person.pin_gesetzt}
        <button class="knopf" type="button" disabled={laeuft === 'pin'} onclick={pinWegnehmen}>
          PIN entfernen
        </button>
      {/if}
    </form>
  </div>

  <h2>Textquellen</h2>
  {#each daten.quellen as quelle (quelle.id)}
    <div class="karte">
      <strong>{quelle.titel}</strong>
      <div class="gedaempft">
        {quelle.art} · {quelle.einheiten} Einheiten · {quelle.aktiv ? 'aktiv' : 'stillgelegt'} ·
        {tag(quelle.erstellt)} · {quelle.id}
      </div>
    </div>
  {:else}
    <p class="gedaempft">Keine Textquelle.</p>
  {/each}

  <h2>Sitzungen</h2>
  {#each sitzungen as sitzung (sitzung.id)}
    <div class="karte gedaempft">
      {tagUndZeit(sitzung.begonnen)} · {sitzung.aufnahmen} Aufnahme(n) · {sitzung.id}
    </div>
  {:else}
    <p class="gedaempft">Keine Sitzung.</p>
  {/each}
  <Pager seite={sitzungenSeite} gesamtSeiten={sitzungenSeiten} aendere={wechsleSitzungenSeite} />

  <h2>Aufnahmen</h2>
  {#each aufnahmen as aufnahme (aufnahme.id)}
    <div class="karte">
      <div class="reihe">
        <div style="flex:1">
          <div>{aufnahme.text}</div>
          <div class="gedaempft">
            {aufnahme.dauer_s.toFixed(1)} s · {aufnahme.pegel_dbfs.toFixed(0)} dBFS ·
            {aufnahme.modus} · {aufnahme.quelle_art} · {tag(aufnahme.erstellt)}
            {#if aufnahme.status !== 'ok'}· <strong>{aufnahme.status}</strong>{/if}
            {#if !aufnahme.audio_vorhanden}· <strong>ohne Audio</strong>{/if}
          </div>
          {#if aufnahme.hinweise.length}
            <div class="hinweise">{aufnahme.hinweise.join(' · ')}</div>
          {/if}
        </div>
        {#if aufnahme.audio_vorhanden}
          <button class="knopf" onclick={() => hoere(aufnahme)}>
            {hoerprobe?.id === aufnahme.id ? 'Zu' : '▶ Hören'}
          </button>
        {/if}
        <button class="knopf" onclick={() => loescheEine(aufnahme)}>Löschen</button>
      </div>
      {#if hoerprobe?.id === aufnahme.id}
        <AudioPlayer quelle={hoerprobe.adresse} />
      {/if}
    </div>
  {:else}
    <p class="gedaempft">Keine Aufnahme.</p>
  {/each}
  <Pager seite={aufnahmenSeite} gesamtSeiten={aufnahmenSeiten} aendere={wechsleAufnahmenSeite} />

  <!-- Ganz unten und abgesetzt: Was hier steht, ist nicht rückgängig zu
       machen, und niemand soll versehentlich darauf stoßen. -->
  <h2>Löschen</h2>
  <div class="karte gefahr">
    <p class="gedaempft">
      Beides ist endgültig und trifft <strong>nur diesen einen Sprecher</strong>. Vorher eine
      Sicherung ziehen - mit ihr lässt sich der Stand zurückholen, ohne sie nicht.
    </p>
    <div class="reihe">
      <button
        class="knopf"
        disabled={!aufnahmenGesamt || laeuft === 'leeren'}
        onclick={loescheAlleAufnahmen}
      >
        Alle Aufnahmen löschen
      </button>
      <button class="knopf" disabled={laeuft === 'loeschen'} onclick={loescheSprecher}>
        Diesen Sprecher vollständig löschen
      </button>
    </div>
  </div>
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
  .kopf {
    margin-top: 1rem;
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

  .gefahr {
    border-color: var(--fehler);
  }
</style>
