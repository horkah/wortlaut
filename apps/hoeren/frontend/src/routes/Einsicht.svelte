<script lang="ts">
  /**
   * Die Aufsicht sieht **einen** Sprecher an: was in seiner Datenbank steht,
   * und was sich damit tun lässt.
   *
   * Immer nur einer. Eine Ansicht, die alle Aufnahmen aller Personen
   * nebeneinanderlegt, lädt dazu ein, quer darüber zu löschen — und das ist
   * genau der Griff, den es hier nicht geben soll. Wer zwei Korpora ansehen
   * will, öffnet sie nacheinander.
   */
  import AudioPlayer from '$ui/AudioPlayer.svelte';
  import {
    alleAufnahmenLoeschen,
    aufnahmeAudio,
    aufnahmeLoeschen,
    aufsichtAufnahmen,
    datensatzSprecher,
    einsicht as ladeEinsicht,
    sicherungSprecher,
    sprecherLoeschen,
    sprecherUmbenennen,
    type AufsichtAufnahme,
    type Einsicht,
  } from '../lib/api';
  import { gehZu, sprecherAusRoute, zustand } from '../lib/zustand.svelte';

  const sprecherId = $derived(sprecherAusRoute(zustand.route));

  let daten = $state<Einsicht | null>(null);
  let aufnahmen = $state<AufsichtAufnahme[]>([]);
  let gesamt = $state(0);
  let fehler = $state('');
  let meldung = $state('');
  let laeuft = $state('');
  // Zu welcher Aufnahme gerade das Audio geladen ist. Nur eine auf einmal:
  // Der Browser hielte sonst Dutzende Aufnahmen im Speicher.
  let hoerprobe = $state<{ id: string; adresse: string } | null>(null);

  async function lade() {
    fehler = '';
    try {
      daten = await ladeEinsicht(sprecherId);
      const seite = await aufsichtAufnahmen(sprecherId);
      aufnahmen = seite.aufnahmen;
      gesamt = seite.gesamt;
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  /** Ein Knopf, der arbeitet: sperren, tun, entsperren — und Fehler zeigen. */
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
        `Alle ${gesamt} Aufnahmen von „${name}“ endgültig löschen?\n\n` +
          'Profil, Textquellen und Warteschlange bleiben stehen — gesprochen ist danach nichts ' +
          'mehr. Das lässt sich nicht rückgängig machen.',
      )
    )
      return;
    if (!bestaetigeMitNamen(name)) return;
    await tue('leeren', async () => {
      const ergebnis = await alleAufnahmenLoeschen(sprecherId);
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
          'Das lässt sich nicht rückgängig machen — vorher eine Sicherung ziehen.',
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
   * Namen abzuschreiben zwingt dazu, hinzusehen, wen es trifft — und genau
   * diese Verwechslung ist der Fehler, den es hier zu verhindern gilt.
   */
  function bestaetigeMitNamen(name: string): boolean {
    const getippt = prompt(`Zur Bestätigung den Namen abschreiben: ${name}`);
    if (getippt === null) return false;
    if (getippt.trim() !== name) {
      fehler = 'Der Name stimmt nicht — es wurde nichts gelöscht.';
      return false;
    }
    return true;
  }

  const minuten = (sekunden: number) => `${Math.round(sekunden / 60)} min`;
  const megabyte = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  const tag = (zeitpunkt: string) => zeitpunkt.slice(0, 10);

  $effect(() => {
    if (zustand.art === 'aufsicht' && sprecherId) lade();
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

  <h2>{person.name}</h2>
  <p class="gedaempft">
    {person.id} · {person.basismodell} · {person.sprache} · angelegt am {tag(person.erstellt)}
    {#if person.zugang_erneuert}
      · Zugang vom {tag(person.zugang_erneuert)}
    {:else}
      · kein Zugang — für niemanden erreichbar
    {/if}
  </p>

  <div class="karte zahlen">
    <div><strong>{zahlen.aufnahmen}</strong><span>Aufnahmen</span></div>
    <div><strong>{minuten(zahlen.sekunden)}</strong><span>gesprochen</span></div>
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
      <button class="knopf" disabled={laeuft === 'umbenennen'} onclick={benenneUm}>
        Umbenennen
      </button>
    </div>
    <p class="gedaempft">
      Die <strong>Sicherung</strong> enthält Datenbank und Aufnahmen, wie sie auf dem Server
      liegen; sie lässt sich mit <code>scripts/restore.py</code> vollständig zurückspielen. Der
      <strong>Datensatz</strong> enthält zu jeder Aufnahme die WAV-Datei und ihren Text — für
      Training und für Werkzeuge, die von wortlaut nichts wissen. Zum Sichern taugt er nicht.
    </p>
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
  {#each daten.sitzungen.slice(0, 20) as sitzung (sitzung.id)}
    <div class="karte gedaempft">
      {tag(sitzung.begonnen)} · {sitzung.aufnahmen} Aufnahme(n) · {sitzung.id}
    </div>
  {:else}
    <p class="gedaempft">Keine Sitzung.</p>
  {/each}

  <h2>Aufnahmen</h2>
  {#if gesamt > aufnahmen.length}
    <p class="gedaempft">
      Die {aufnahmen.length} neuesten von {gesamt}. Der Rest steht im Datensatz.
    </p>
  {/if}

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

  <!-- Ganz unten und abgesetzt: Was hier steht, ist nicht rückgängig zu
       machen, und niemand soll versehentlich darauf stoßen. -->
  <h2>Löschen</h2>
  <div class="karte gefahr">
    <p class="gedaempft">
      Beides ist endgültig und trifft <strong>nur diesen einen Sprecher</strong>. Vorher eine
      Sicherung ziehen — mit ihr lässt sich der Stand zurückholen, ohne sie nicht.
    </p>
    <div class="reihe">
      <button class="knopf" disabled={!gesamt || laeuft === 'leeren'} onclick={loescheAlleAufnahmen}>
        Alle Aufnahmen löschen
      </button>
      <button class="knopf" disabled={laeuft === 'loeschen'} onclick={loescheSprecher}>
        Diesen Sprecher vollständig löschen
      </button>
    </div>
  </div>
{/if}

<style>
  .kopf {
    margin-top: 1rem;
  }

  /* Die Kennzahlen als Reihe kleiner Blöcke: Sie werden überflogen, nicht
     gelesen — die Zahl groß, ihre Bedeutung klein darunter. */
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
