/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { defineConfig, loadEnv } from 'vite';
import { gameDataPlugin } from './vite-plugins/gameData';

// Cible du proxy de développement : le serveur FastAPI.
// En local : http://localhost:8000 ; sous Docker Compose : VITE_PROXY_TARGET=http://server:8000.
const DEFAULT_PROXY_TARGET = 'http://localhost:8000';

// Racine du dépôt (contient `shared/`, `maps/`, `assets/`). Sous Docker, le client vit dans
// /srv/client : monter ces dossiers dans /srv (ou fixer DR_REPO_ROOT).
const DEFAULT_REPO_ROOT = path.resolve(import.meta.dirname, '..');

export default defineConfig(({ mode }) => {
  // Préfixe vide : on lit aussi les variables d'environnement du processus (Docker).
  const env = loadEnv(mode, process.cwd(), '');
  const httpTarget = env.VITE_PROXY_TARGET || DEFAULT_PROXY_TARGET;
  const wsTarget = httpTarget.replace(/^http/, 'ws');
  const repoRoot = path.resolve(env.DR_REPO_ROOT || DEFAULT_REPO_ROOT);

  return {
    plugins: [react(), tailwindcss(), gameDataPlugin(repoRoot)],
    resolve: {
      // Données partagées client/serveur (constantes de déplacement, fixtures).
      alias: { '@shared': path.join(repoRoot, 'shared') },
    },
    server: {
      // Autorise l'import de fichiers hors de client/ (shared/).
      fs: { allow: [import.meta.dirname, path.join(repoRoot, 'shared')] },
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': { target: httpTarget, changeOrigin: true },
        '/ws': { target: wsTarget, ws: true, changeOrigin: true },
      },
    },
    build: {
      target: 'es2022',
      // Phaser pèse ~1,2 Mo minifié : on l'isole dans son propre chunk.
      chunkSizeWarningLimit: 1600,
      rollupOptions: {
        output: {
          manualChunks: { phaser: ['phaser'] },
        },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      css: false,
    },
  };
});
