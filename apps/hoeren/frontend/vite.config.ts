import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

const hier = dirname(fileURLToPath(import.meta.url));
const repowurzel = resolve(hier, '../../..');

// Das Baudatum wandert als fester Wert ins Bündel (siehe packages/ui/bau.ts);
// der Seitenfuß zeigt es an. In der Entwicklung ist es der Serverstart.
const baudatum = new Date().toISOString().slice(0, 10);

export default defineConfig({
  plugins: [svelte()],
  define: { __BAUDATUM__: JSON.stringify(baudatum) },
  resolve: {
    // Geteilte Komponenten liegen außerhalb dieser App.
    alias: { $ui: resolve(repowurzel, 'packages/ui') },
  },
  server: {
    // Ohne diese Freigabe verweigert Vite Dateien oberhalb des Projektordners.
    fs: { allow: [repowurzel] },
    // Statt CORS: der Entwicklungsserver reicht /api an das Backend durch.
    proxy: {
      '/api': 'http://localhost:8000',
      // Der Reiter „schreiben" führt auf `/schreiben/` — im Betrieb verteilt
      // das der Reverse Proxy, hier der Entwicklungsserver. Ohne diese Zeile
      // beantwortet Vite den Pfad mit der eigenen index.html, und der Klick
      // bliebe sichtbar in „hören" stehen. Läuft `make dev APP=schreiben`
      // nicht, kommt an dieser Stelle ein Verbindungsfehler statt der App.
      '/schreiben': { target: 'http://localhost:5174', ws: true },
    },
  },
});
