// Outils réseau des tests de la phase 2 : comptes créés par l'API, client WebSocket « nu »
// (WebSocket global de Node 22, aucune dépendance), carte de collision de Valcendre.
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { BASE_URL, uniqueAccount } = require('./helpers.cjs');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const MOVEMENT = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, 'shared/movement/movement.json'), 'utf8'));
const EPSILON = 1e-9;

async function api(method, url, body, token) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${BASE_URL}${url}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const text = await res.text();
  if (!res.ok) throw new Error(`${method} ${url} → ${res.status} ${text}`);
  return text ? JSON.parse(text) : null;
}

/** Compte + personnage créés par l'API (sans navigateur). */
async function apiAccountWithCharacter(account = uniqueAccount()) {
  await api('POST', '/api/auth/register', { username: account.username, password: account.password });
  const { access_token: token } = await api('POST', '/api/auth/login', {
    username: account.username,
    password: account.password,
  });
  const character = await api('POST', '/api/characters', { name: account.character }, token);
  return { account, token, character };
}

/**
 * Client WebSocket de zone. Conserve tous les messages reçus ; `snapshots` liste
 * `{ tick, ack, receivedAt, entities }`. `send(t, d, seq?)` envoie une enveloppe brute
 * (`attack: false` ajouté aux `input` qui ne le précisent pas).
 */
async function openZoneSocket({ token, character }, zoneId = 'valcendre') {
  const { ticket, ws_path: wsPath } = await api('POST', `/api/zones/${zoneId}/join`, { character_id: character.id }, token);
  const wsUrl = `${BASE_URL.replace(/^http/, 'ws')}${wsPath}?ticket=${encodeURIComponent(ticket)}`;
  const ws = new WebSocket(wsUrl);
  const client = {
    ws,
    welcome: null,
    snapshots: [],
    errors: [],
    closeCode: null,
    seq: 0,
    send(t, d, seq) {
      this.seq = seq ?? this.seq + 1;
      // Protocole v3 : `input` porte aussi la gâchette ; ajoutée (relâchée) si le test l'omet.
      const payload = t === 'input' && d && typeof d === 'object' && !('attack' in d) ? { ...d, attack: false } : d;
      ws.send(JSON.stringify({ t, seq: this.seq, d: payload }));
      return this.seq;
    },
    sendRaw(text) {
      ws.send(text);
    },
    /** Position de l'entité `name` (ou la sienne) dans le dernier snapshot. */
    last(name) {
      const snap = this.snapshots[this.snapshots.length - 1];
      if (!snap) return null;
      return snap.entities.find((e) => (name ? e.name === name : e.id === this.welcome?.entity_id)) ?? null;
    },
    close() {
      if (ws.readyState <= 1) ws.close(1000);
      return new Promise((resolve) => {
        if (ws.readyState === 3) resolve();
        else ws.addEventListener('close', () => resolve(), { once: true });
      });
    },
  };
  ws.addEventListener('message', (event) => {
    const msg = JSON.parse(event.data);
    if (msg.t === 'welcome') client.welcome = msg.d;
    else if (msg.t === 'snapshot')
      client.snapshots.push({ tick: msg.tick, ack: msg.d.ack_seq, receivedAt: Date.now(), entities: msg.d.entities });
    else if (msg.t === 'error') client.errors.push(msg.d);
  });
  ws.addEventListener('close', (event) => {
    client.closeCode = event.code;
  });
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('welcome non reçu')), 10_000);
    const check = () => {
      if (client.welcome) {
        clearTimeout(timer);
        resolve();
      } else if (client.closeCode !== null) {
        clearTimeout(timer);
        reject(new Error(`WebSocket fermé ${client.closeCode}`));
      } else setTimeout(check, 20);
    };
    check();
  });
  return client;
}

// --- Carte ---------------------------------------------------------------------------------------

/** Grille de collision de maps/valcendre.tmj (calque `collision`, non nul = solide). */
function loadCollisionGrid(mapFile = path.join(REPO_ROOT, 'maps/valcendre.tmj')) {
  const map = JSON.parse(fs.readFileSync(mapFile, 'utf8'));
  const layer = map.layers.find((l) => l.name === 'collision');
  if (!layer) throw new Error('calque collision absent');
  const { width, height } = map;
  return {
    width,
    height,
    isSolid(tx, ty) {
      if (tx < 0 || ty < 0 || tx >= width || ty >= height) return true;
      return layer.data[ty * width + tx] !== 0;
    },
  };
}

/**
 * Tuiles solides que la boîte du joueur centrée en (x, y) recouvre **strictement** (le contact
 * exact contre un bord est permis, à EPSILON près, comme dans step()).
 */
function solidTilesUnder(grid, x, y, half = MOVEMENT.player_half_size) {
  const hits = [];
  const tx0 = Math.floor(x - half + EPSILON);
  const tx1 = Math.floor(x + half - EPSILON);
  const ty0 = Math.floor(y - half + EPSILON);
  const ty1 = Math.floor(y + half - EPSILON);
  for (let ty = ty0; ty <= ty1; ty += 1)
    for (let tx = tx0; tx <= tx1; tx += 1) if (grid.isSolid(tx, ty)) hits.push([tx, ty]);
  return hits;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

module.exports = {
  MOVEMENT,
  api,
  apiAccountWithCharacter,
  openZoneSocket,
  loadCollisionGrid,
  solidTilesUnder,
  sleep,
};
