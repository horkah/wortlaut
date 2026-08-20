import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

const hier = dirname(fileURLToPath(import.meta.url));
const repowurzel = resolve(hier, '../../..');

export default defineConfig({
  plugins: [svelte()],
  // Diese App liegt unter der gemeinsamen Domain auf `/schreiben/` (siehe
  // `BASIS` in backend/main.py und packages/ui/apps.ts). Ohne `base` verwiese
  // das gebaute HTML auf `/assets/…` und träfe damit die App „hören" auf der
  // Wurzel.
  base: '/schreiben/',
  resolve: {
    // Geteilte Komponenten liegen außerhalb dieser App.
    alias: { $ui: resolve(repowurzel, 'packages/ui') },
  },
  server: {
    // Eigener Port, damit „hören" (5173) daneben laufen kann.
    port: 5174,
    // Ohne diese Freigabe verweigert Vite Dateien oberhalb des Projektordners.
    fs: { allow: [repowurzel] },
    // Statt CORS: der Entwicklungsserver reicht die API an das Backend durch.
    // Der Pfad bleibt dabei unverändert — das Backend hängt sie selbst unter
    // `/schreiben` (siehe `BASIS` dort). Port 8001, damit beide Backends
    // gleichzeitig laufen können (Makefile).
    proxy: { '/schreiben/api': 'http://localhost:8001' },
  },
});
