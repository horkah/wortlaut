<script lang="ts">
  /**
   * Ein Sprecher sieht seine eigenen Daten an - dieselbe Ansicht, die die
   * Aufsicht für ihn hätte (`Einsicht.svelte`), nur auf die eigene Kennung
   * beschränkt. Genau **eine** Karte von dort fehlt hier: die beiden
   * Löschstufen „alle Aufnahmen" und „diesen Sprecher vollständig". Alles Übrige darf
   * jeder über seine eigenen Daten - ansehen, anhören, eine einzelne Aufnahme
   * verwerfen (dasselbe Verwerfen wie beim Aufnehmen, `Aufnahme.svelte`),
   * sich umbenennen und beides mitnehmen, Sicherung wie Datensatz.
   */
  import AudioPlayer from '$ui/AudioPlayer.svelte';
  import Pager from '$ui/Pager.svelte';
  import { merkePin, schloss, vergissPin } from '$ui/pin.svelte';
  import { dauer, tag, tagUndZeit } from '$ui/zeit';
  import {
    aufnahmeVerwerfen,
    meinDatensatz,
    meinKonto,
    meineAufnahmeAudio,
    meineAufnahmen,
    meineSicherung,
    meineSitzungen,
    michUmbenennen,
    pinSetzen,
    pinStand,
    type AufsichtAufnahme,
    type AufsichtSitzung,
    type Konto,
  } from '../lib/api';
  import { zustand } from '../lib/zustand.svelte';

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
    const seite = await meineSitzungen((sitzungenSeite - 1) * PRO_SEITE, PRO_SEITE, meinePin);
    sitzungen = seite.sitzungen;
    sitzungenGesamt = seite.gesamt;
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
      await Promise.all([ladeSitzungen(), ladeAufnahmen()]);
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
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
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  async function entsperren(ereignis: SubmitEvent) {
    ereignis.preventDefault();
    pinFehler = '';

    // Validierung: genau 4 Ziffern
    if (!pinEingabe || pinEingabe.length !== 4 || !/^[0-9]{4}$/.test(pinEingabe)) {
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
      await Promise.all([ladeSitzungen(), ladeAufnahmen()]);
    } catch {
      pinFehler = 'Falsche PIN.';
    }
  }

  async function pinAendern(ereignis: SubmitEvent) {
    ereignis.preventDefault();
    const neue = neuePin.trim();

    // Validierung: genau 4 Ziffern
    if (!neue || neue.length !== 4 || !/^[0-9]{4}$/.test(neue)) {
      fehler = 'Die PIN muss aus genau 4 Ziffern bestehen.';
      return;
    }

    // Wer zum ersten Mal eine PIN einrichtet, bekommt die Seite gleich wieder
    // zugesperrt und muss sie einmal eingeben. Nicht als Schikane: Eine PIN,
    // die man setzt und nie tippt, merkt man sich nicht - und wer sich hier
    // vertippt hat, erfährt es in derselben Minute, statt beim nächsten
    // Besuch vor einer Seite zu stehen, die ihn nicht mehr hereinlässt.
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
        await ladeAufnahmen();
      },
      'Aufnahme verworfen.',
    );
  }

  const megabyte = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`;

  $effect(() => {
    if (zustand.art === 'sprecher') starte();
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

  <h2>{person.name}</h2>
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
      <button class="knopf" disabled={laeuft === 'umbenennen'} onclick={benenneUm}>
        Umbenennen
      </button>
    </div>
    <p class="gedaempft">
      <strong>Sicherung:</strong> Datenbank und Aufnahmen, zurückzuspielen mit
      <code>scripts/restore.py</code>. Ohne Abwandlungen und Messwerte - die rechnet ein
      Auswertungslauf neu.<br />
      <strong>Datensatz:</strong> je Aufnahme WAV und Text, für fremde Werkzeuge. Keine Sicherung.
    </p>
  </div>

  <h2>Textquellen</h2>
  {#each daten.quellen as quelle (quelle.id)}
    <div class="karte">
      <strong>{quelle.titel}</strong>
      <div class="gedaempft">
        {quelle.art} · {quelle.einheiten} Einheiten · {quelle.aktiv ? 'aktiv' : 'stillgelegt'} ·
        {tag(quelle.erstellt)}
      </div>
    </div>
  {:else}
    <p class="gedaempft">Keine Textquelle.</p>
  {/each}

  <h2>Sitzungen</h2>
  {#each sitzungen as sitzung (sitzung.id)}
    <div class="karte gedaempft">
      {tagUndZeit(sitzung.begonnen)} · {sitzung.aufnahmen} Aufnahme(n)
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
            {aufnahme.dauer_s.toFixed(1)} s · {aufnahme.modus} · {tag(aufnahme.erstellt)}
            {#if aufnahme.status !== 'ok'}· <strong>{aufnahme.status}</strong>{/if}
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
        {#if aufnahme.status === 'ok'}
          <button class="knopf" onclick={() => verwirf(aufnahme)}>Verwerfen</button>
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
{/if}

<style>
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
