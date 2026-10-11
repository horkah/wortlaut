<script lang="ts">
  /**
   * Eine Rückfrage vor einem Schritt, als Dialog über der Seite.
   *
   * `gefahr` steht für Unumkehrbares: Dann trägt der Dialog das rote
   * Warnzeichen und den Satz, dass sich das nicht rückgängig machen lässt,
   * und der bestätigende Knopf ist rot. Den Fokus hat anfangs „Abbrechen" -
   * ein versehentliches Enter löscht nichts.
   *
   * Esc, „Abbrechen" und ein Klick neben den Dialog sind dasselbe: `onnein`.
   */
  import type { Snippet } from 'svelte';

  let {
    offen,
    titel,
    knopf,
    gefahr = false,
    onja,
    onnein,
    children,
  }: {
    offen: boolean;
    titel: string;
    knopf: string;
    gefahr?: boolean;
    onja: () => void;
    onnein: () => void;
    children?: Snippet;
  } = $props();

  const kennung = $props.id();
  let dialog: HTMLDialogElement;

  $effect(() => {
    if (offen && !dialog.open) dialog.showModal();
    else if (!offen && dialog.open) dialog.close();
  });

  function schliesse() {
    if (offen) onnein();
  }
</script>

<!-- Der Klick neben den Dialog trifft das Element selbst; Esc hat die Tastatur. -->
<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
<dialog
  bind:this={dialog}
  class="rueckfrage"
  aria-labelledby="{kennung}-titel"
  onclose={schliesse}
  onclick={(ereignis) => {
    if (ereignis.target === dialog) dialog.close();
  }}
>
  {#if offen}
    <div class="innen">
      <h3 id="{kennung}-titel">{titel}</h3>
      {@render children?.()}
      {#if gefahr}
        <p class="warnung">
          <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
            <path d="M12 2.5 23 21.5H1Z" fill="currentColor" />
            <path d="M12 9.5v5.5" stroke="#fff" stroke-width="2.2" stroke-linecap="round" />
            <circle cx="12" cy="18.2" r="1.3" fill="#fff" />
          </svg>
          Das kann nicht rückgängig gemacht werden.
        </p>
      {/if}
      <div class="reihe knoepfe">
        <!-- svelte-ignore a11y_autofocus -->
        <button class="knopf" autofocus onclick={() => dialog.close()}>Abbrechen</button>
        <button class="knopf" class:gefahr class:haupt={!gefahr} onclick={onja}>{knopf}</button>
      </div>
    </div>
  {/if}
</dialog>

<style>
  .rueckfrage {
    width: min(28rem, calc(100vw - 2rem));
    box-sizing: border-box;
    padding: 0;
    border: 1px solid var(--rand);
    border-radius: 0.5rem;
    background: #fff;
    color: var(--text);
    box-shadow: 0 8px 28px rgb(0 0 0 / 0.2);
  }

  .rueckfrage::backdrop {
    background: rgb(0 0 0 / 0.35);
  }

  .innen {
    padding: 1.1rem 1.25rem 1.25rem;
  }

  h3 {
    margin: 0 0 0.75rem;
    font-size: 1.1rem;
  }

  .warnung {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--fehler);
    font-weight: 600;
  }

  .warnung svg {
    flex: none;
  }

  .knoepfe {
    justify-content: flex-end;
    margin-top: 1rem;
  }

  .knopf.gefahr {
    background: var(--fehler);
    border-color: var(--fehler);
    color: #fff;
  }
</style>
