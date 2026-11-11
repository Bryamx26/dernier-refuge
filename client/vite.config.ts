/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

// Cible du proxy de développement : le serveur FastAPI.
// En local : http://localhost:8000 ; sous Docker Compose : VITE_PROXY_TARGET=http://server:8000.
const DEFAULT_PROXY_TARGET = 'http://localhost:8000';

export default defineConfig(({ mode }) => {
  // Préfixe vide : on lit aussi les variables d'environnement du processus (Docker).
  const env = loadEnv(mode, process.cwd(), '');
  const httpTarget = env.VITE_PROXY_TARGET || DEFAULT_PROXY_TARGET;
  const wsTarget = httpTarget.replace(/^http/, 'ws');

  return {
    plugins: [react(), tailwindcss()],
    server: {
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
