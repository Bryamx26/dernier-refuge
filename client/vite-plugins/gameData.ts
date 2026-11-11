// Plugin Vite : sert les données de jeu de la racine du dépôt (`maps/`, `assets/`) sous `/game/…`
// en développement, et les copie dans `dist/game/` au build.
import { createReadStream, cpSync, existsSync, statSync } from 'node:fs';
import path from 'node:path';
import type { Plugin } from 'vite';

/** Dossiers servis : préfixe d'URL sous `/game/` → dossier de la racine du dépôt. */
export const GAME_DATA_DIRS = ['maps', 'assets'] as const;
export const GAME_URL_PREFIX = '/game/';

const CONTENT_TYPES: Record<string, string> = {
  '.tmj': 'application/json; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.md': 'text/markdown; charset=utf-8',
};

/**
 * Résout `/game/<dossier>/<chemin>` vers un fichier existant sous `dataRoot`, ou null.
 * Refuse toute sortie du dossier (`..`, chemins absolus encodés).
 */
export function resolveGameFile(dataRoot: string, urlPath: string): string | null {
  if (!urlPath.startsWith(GAME_URL_PREFIX)) return null;
  let relative: string;
  try {
    relative = decodeURIComponent(urlPath.slice(GAME_URL_PREFIX.length).split('?')[0] ?? '');
  } catch {
    return null;
  }
  const [dir] = relative.split('/');
  if (!dir || !(GAME_DATA_DIRS as readonly string[]).includes(dir)) return null;
  const base = path.resolve(dataRoot, dir);
  const file = path.resolve(dataRoot, relative);
  if (!file.startsWith(base + path.sep)) return null;
  if (!existsSync(file) || !statSync(file).isFile()) return null;
  return file;
}

export function gameDataPlugin(dataRoot: string): Plugin {
  let outDir = 'dist';
  return {
    name: 'dernier-refuge:game-data',
    configResolved(config) {
      outDir = path.resolve(config.root, config.build.outDir);
    },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const file = req.url ? resolveGameFile(dataRoot, req.url) : null;
        if (!file) {
          if (req.url?.startsWith(GAME_URL_PREFIX)) {
            res.statusCode = 404;
            res.end('Fichier de jeu introuvable');
            return;
          }
          next();
          return;
        }
        res.setHeader('Content-Type', CONTENT_TYPES[path.extname(file)] ?? 'application/octet-stream');
        // Pas de cache en dev : la carte et les sprites sont régénérés pendant le développement.
        res.setHeader('Cache-Control', 'no-cache');
        createReadStream(file).pipe(res);
      });
    },
    writeBundle() {
      for (const dir of GAME_DATA_DIRS) {
        const source = path.resolve(dataRoot, dir);
        if (!existsSync(source)) {
          this.warn(`Données de jeu absentes : ${source} (non copiées dans dist/game/)`);
          continue;
        }
        cpSync(source, path.join(outDir, 'game', dir), { recursive: true });
      }
    },
  };
}
