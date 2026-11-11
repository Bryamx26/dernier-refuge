// Phase 2 — prototype jouable : synchronisation à deux navigateurs, collisions côté serveur,
// tricheur WebSocket, fluidité et réconciliation sous 150 ms de latence.
// Prérequis : pile démarrée (voir e2e/README.md). Le test de latence demande en plus un second Vite
// (DR_E2E_LAG_BASE_URL) dont le proxy vise le proxy de latence lancé par le test.
'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const h = require('./helpers.cjs');
const n = require('./net.cjs');
const { startLatencyProxy } = require('../tools/latency-proxy.cjs');

const TIMEOUT = 120_000;
const GRID = n.loadCollisionGrid();
const TICK_S = 1 / 20;

/** Toutes les violations « boîte dans une tuile solide » d'une liste de snapshots. */
function wallViolations(snapshots, filter = () => true) {
  const out = [];
  for (const snap of snapshots)
    for (const e of snap.entities) {
      if (!filter(e)) continue;
      const hits = n.solidTilesUnder(GRID, e.x, e.y);
      if (hits.length) out.push({ tick: snap.tick, name: e.name, x: e.x, y: e.y, hits });
    }
  return out;
}

/** Trajectoire (tick, x, y) d'une entité dans les snapshots d'un observateur. */
function track(snapshots, pick) {
  const out = [];
  for (const snap of snapshots) {
    const e = snap.entities.find(pick);
    if (e) out.push({ tick: snap.tick, x: e.x, y: e.y });
  }
  return out;
}

/** Vitesse maximale (tuiles/s) moyennée sur une fenêtre glissante de `windowTicks` ticks. */
function maxWindowSpeed(trajectory, windowTicks) {
  let max = 0;
  for (let i = 0; i < trajectory.length; i += 1) {
    let j = i;
    while (j + 1 < trajectory.length && trajectory[j + 1].tick - trajectory[i].tick <= windowTicks) j += 1;
    const dt = (trajectory[j].tick - trajectory[i].tick) * TICK_S;
    if (dt <= 0) continue;
    // Somme des pas (et non distance à vol d'oiseau) : un aller-retour compte.
    let path = 0;
    for (let k = i + 1; k <= j; k += 1)
      path += Math.hypot(trajectory[k].x - trajectory[k - 1].x, trajectory[k].y - trajectory[k - 1].y);
    max = Math.max(max, path / Math.max(dt, windowTicks * TICK_S));
  }
  return max;
}

/** Valeur d'une ligne du panneau « Terrain » (data-testid). */
function worldValue(page, testId) {
  return page.getByTestId(testId).innerText();
}

/** « 64,0 · 64,0 » → { x, y }. */
function parsePosition(text) {
  const m = text.match(/(-?\d+,\d)\s*·\s*(-?\d+,\d)/);
  return m ? { x: Number(m[1].replace(',', '.')), y: Number(m[2].replace(',', '.')) } : null;
}

/** « 0,03 t » → 0.03. */
function parseCorrection(text) {
  const m = text.match(/(\d+,\d+)/);
  return m ? Number(m[1].replace(',', '.')) : NaN;
}

/** Maintient des touches (event.code) pendant `ms`. */
async function hold(page, keys, ms) {
  for (const k of keys) await page.keyboard.down(k);
  await page.waitForTimeout(ms);
  for (const k of [...keys].reverse()) await page.keyboard.up(k);
}

/** Enregistre les snapshots reçus par la page (trames WebSocket du navigateur). */
function recordBrowserSnapshots(page) {
  const snapshots = [];
  page.on('websocket', (ws) => {
    if (!ws.url().includes('/ws/zone/')) return;
    ws.on('framereceived', (frame) => {
      try {
        const msg = JSON.parse(String(frame.payload));
        if (msg.t === 'snapshot') snapshots.push({ tick: msg.tick, entities: msg.d.entities });
      } catch {
        /* trame non JSON : ignorée */
      }
    });
  });
  return snapshots;
}

async function joinedPlayer(browser, { record = false } = {}) {
  const tab = await h.newPage(browser);
  const account = h.uniqueAccount();
  tab.account = account;
  tab.frames = record ? recordBrowserSnapshots(tab.page) : null;
  await h.registerViaUi(tab.page, account);
  await h.createCharacterViaUi(tab.page, account);
  await h.joinZoneViaUi(tab.page, account);
  // Carte chargée et prédiction prête : la position s'affiche au HUD.
  await tab.page.getByTestId('world-position').filter({ hasText: /\d+,\d/ }).waitFor({ timeout: 15_000 });
  return tab;
}

// -------------------------------------------------------------------------------------------------

test('deux navigateurs voient le mouvement l’un de l’autre (HUD, trames reçues, snapshots serveur)', { timeout: TIMEOUT }, async () => {
  const browser = await h.launchBrowser();
  let observer = null;
  try {
    const [a, b] = await Promise.all([joinedPlayer(browser, { record: true }), joinedPlayer(browser, { record: true })]);
    observer = await n.openZoneSocket(await n.apiAccountWithCharacter());
    const nameA = a.account.character;
    const nameB = b.account.character;

    // Chacun compte les deux autres (A, B, observateur) dans le panneau « Terrain ».
    for (const tab of [a, b])
      await tab.page.getByTestId('world-players').filter({ hasText: /^3$/ }).waitFor({ timeout: 5_000 });

    await n.sleep(500);
    const a0 = observer.last(nameA);
    const b0 = observer.last(nameB);
    assert.ok(a0 && b0, 'l’observateur voit A et B');
    const hudA0 = parsePosition(await worldValue(a.page, 'world-position'));

    // A marche vers l’est 1,5 s (D maintenu) : 4,5 tuiles attendues.
    const framesB0 = b.frames.length;
    await hold(a.page, ['KeyD'], 1_500);
    await n.sleep(600);
    const a1 = observer.last(nameA);
    assert.ok(a1.x - a0.x >= 3.5 && a1.x - a0.x <= 5.0, `serveur : A a avancé de ${(a1.x - a0.x).toFixed(2)} tuiles en x`);
    assert.ok(Math.abs(a1.y - a0.y) < 1e-9, 'serveur : A n’a pas bougé en y');
    const hudA1 = parsePosition(await worldValue(a.page, 'world-position'));
    assert.ok(hudA1.x - hudA0.x >= 3.5, `HUD de A : ${hudA0.x} → ${hudA1.x}`);
    assert.ok(Math.abs(hudA1.x - a1.x) <= 0.051, `HUD de A (${hudA1.x}) = serveur (${a1.x.toFixed(2)})`);

    // Le navigateur de B a reçu la trajectoire de A, jusqu’à sa position finale.
    const seenByB = track(b.frames.slice(framesB0), (e) => e.name === nameA);
    assert.ok(seenByB.length >= 20, `B a reçu ${seenByB.length} états de A`);
    assert.ok(Math.abs(seenByB[seenByB.length - 1].x - a1.x) < 1e-9, 'dernier état de A reçu par B = serveur');
    assert.ok(new Set(seenByB.map((p) => p.x)).size >= 10, 'B voit A se déplacer progressivement');
    // A est animé (walk) pendant la marche, vu de B.
    assert.ok(
      b.frames.slice(framesB0).some((s) => s.entities.some((e) => e.name === nameA && e.anim === 'walk')),
      'B voit A en animation walk',
    );

    // Dans l’autre sens : B marche vers le nord 1 s (colonne libre au-dessus du point d’apparition), A le voit.
    const framesA0 = a.frames.length;
    await hold(b.page, ['KeyW'], 1_000);
    await n.sleep(600);
    const b1 = observer.last(nameB);
    assert.ok(b0.y - b1.y >= 2.2 && b0.y - b1.y <= 3.5, `serveur : B est monté de ${(b0.y - b1.y).toFixed(2)} tuiles`);
    const seenByA = track(a.frames.slice(framesA0), (e) => e.name === nameB);
    assert.ok(seenByA.length >= 15, `A a reçu ${seenByA.length} états de B`);
    assert.ok(Math.abs(seenByA[seenByA.length - 1].y - b1.y) < 1e-9, 'A a reçu la position finale de B');

    await h.screenshot(b.page, 'phase2-01-deux-joueurs-vue-B.png');
    await h.screenshot(a.page, 'phase2-02-deux-joueurs-vue-A.png');

    assert.deepEqual(wallViolations(observer.snapshots), [], 'aucune boîte dans un mur');
    assert.deepEqual(a.consoleErrors, [], 'aucune erreur console (A)');
    assert.deepEqual(b.consoleErrors, [], 'aucune erreur console (B)');
  } finally {
    await observer?.close();
    await browser.close();
  }
});

test('mur : marcher et sprinter contre un bâtiment ne fait jamais entrer la boîte dans une case solide', { timeout: TIMEOUT }, async () => {
  const browser = await h.launchBrowser();
  let observer = null;
  try {
    const c = await joinedPlayer(browser);
    observer = await n.openZoneSocket(await n.apiAccountWithCharacter());
    const name = c.account.character;
    await n.sleep(300);
    const start = observer.last(name);
    const i0 = observer.snapshots.length;

    // Depuis le point d’apparition (64, 64), le bâtiment au sud (tuiles x 57–65, y ≥ 68) est à 4 tuiles.
    await hold(c.page, ['ShiftLeft', 'KeyS'], 2_500); // sprint plein sud, 1,5 s poussé contre le mur
    const pushed = observer.last(name);
    await h.screenshot(c.page, 'phase2-03-joueur-contre-batiment.png');
    await hold(c.page, ['KeyS'], 1_000); // marche contre le mur
    await hold(c.page, ['ShiftLeft', 'KeyS', 'KeyD'], 1_500); // glisse le long du mur en sprint
    await hold(c.page, ['ShiftLeft', 'KeyS', 'KeyA'], 3_000); // glisse vers l’ouest, coin, ruelle
    await hold(c.page, ['ShiftLeft', 'KeyW'], 2_000); // remonte vers le bâtiment nord
    await n.sleep(400);

    const snaps = observer.snapshots.slice(i0);
    const traj = track(snaps, (e) => e.name === name);
    assert.ok(traj.length >= 150, `${traj.length} positions serveur relevées`);
    assert.ok(Math.abs(start.x - 64) < 1e-9 && Math.abs(start.y - 64) < 1e-9, `départ au point d’apparition (${start.x}, ${start.y})`);
    // Contre le mur sud : bord bas de la boîte = 68 exactement (centre 67,7).
    assert.ok(Math.abs(pushed.y - (68 - n.MOVEMENT.player_half_size)) < 1e-9, `poussé contre le mur : y = ${pushed.y}`);
    assert.deepEqual(wallViolations(snaps), [], 'aucune boîte dans un mur');
    // Pas de téléportation : au plus 3 pas de sprint par tick (règle max_inputs_per_tick).
    for (let i = 1; i < traj.length; i += 1) {
      const d = Math.hypot(traj[i].x - traj[i - 1].x, traj[i].y - traj[i - 1].y) / (traj[i].tick - traj[i - 1].tick);
      assert.ok(d <= n.MOVEMENT.sprint_speed * TICK_S * n.MOVEMENT.max_inputs_per_tick + 1e-9, `pas de ${d} tuile au tick ${traj[i].tick}`);
    }
    const speed = maxWindowSpeed(traj, 20);
    assert.ok(speed <= n.MOVEMENT.sprint_speed * 1.1 + 1e-6, `vitesse max d’un client honnête sur 1 s : ${speed.toFixed(2)} t/s`);
    assert.deepEqual(c.consoleErrors, [], 'aucune erreur console');
  } finally {
    await observer?.close();
    await browser.close();
  }
});

test('tricheur : entrées hors bornes, mal typées ou avec champs en trop refusées sans effet', { timeout: TIMEOUT }, async () => {
  const cheater = await n.openZoneSocket(await n.apiAccountWithCharacter());
  try {
    await n.sleep(300);
    const before = cheater.last();
    const bad = [
      { move_x: 50, move_y: 0, aim: 0, sprint: true },
      { move_x: 1, move_y: -1e308, aim: 0, sprint: true },
      { move_x: 1, move_y: 0, aim: 100, sprint: true },
      { move_x: 1, move_y: 0, aim: 0, sprint: 1 },
      { move_x: '1', move_y: 0, aim: 0, sprint: true },
      { move_x: 1, move_y: 0, aim: 0, sprint: true, speed: 99 },
    ];
    for (const d of bad) cheater.send('input', d);
    cheater.sendRaw('{"t":"input","seq":99,"d":{"move_x":NaN,"move_y":0,"aim":0,"sprint":true}}');
    cheater.sendRaw('{"t":"input","seq":-1,"d":{"move_x":1,"move_y":0,"aim":0,"sprint":true}}');
    await n.sleep(500);
    assert.equal(cheater.errors.length, bad.length + 2, JSON.stringify(cheater.errors));
    assert.ok(cheater.errors.every((e) => e.code === 'bad_message'));
    const after = cheater.last();
    assert.equal(after.x, before.x);
    assert.equal(after.y, before.y);
    assert.equal(cheater.snapshots[cheater.snapshots.length - 1].ack, 0, 'aucune entrée acquittée');

    // Doublons et désordre : ignorés (seq ≤ dernier appliqué).
    cheater.send('input', { move_x: 1, move_y: 0, aim: 0, sprint: false }, 10);
    for (let i = 0; i < 5; i += 1) cheater.send('input', { move_x: 1, move_y: 0, aim: 0, sprint: true }, 5);
    await n.sleep(400);
    const dup = cheater.last();
    assert.ok(Math.abs(dup.x - (before.x + n.MOVEMENT.walk_speed * TICK_S)) < 1e-9, `un seul pas appliqué : x = ${dup.x}`);
    assert.equal(cheater.closeCode, null, 'connexion toujours ouverte');
  } finally {
    await cheater.close();
  }
});

test('tricheur : 100 entrées de sprint d’un coup → distance ≤ budget cumulé du serveur', { timeout: TIMEOUT }, async () => {
  const cheater = await n.openZoneSocket(await n.apiAccountWithCharacter());
  try {
    await n.sleep(300);
    const i0 = cheater.snapshots.length;
    // Vers le nord : ~10 tuiles libres au-dessus du point d’apparition (64, 64).
    for (let i = 0; i < 100; i += 1) cheater.send('input', { move_x: 0, move_y: -1, aim: 0, sprint: true });
    await n.sleep(2_500);
    const traj = track(cheater.snapshots.slice(i0 - 1), (e) => e.id === cheater.welcome.entity_id);
    const rateLimited = cheater.errors.filter((e) => e.code === 'rate_limited').length;
    let perTick = 0;
    for (let i = 1; i < traj.length; i += 1)
      perTick = Math.max(perTick, Math.hypot(traj[i].x - traj[i - 1].x, traj[i].y - traj[i - 1].y) / (traj[i].tick - traj[i - 1].tick));
    const windowSpeed = maxWindowSpeed(traj, 20);
    const travelled = Math.hypot(traj[traj.length - 1].x - traj[0].x, traj[traj.length - 1].y - traj[0].y);
    console.log(
      `# tricheur : ${100 - rateLimited} entrées acceptées, ${rateLimited} rate_limited, ` +
        `${travelled.toFixed(2)} tuiles parcourues, max ${(perTick / TICK_S).toFixed(2)} t/s sur un tick, ` +
        `${windowSpeed.toFixed(2)} t/s sur 1 s`,
    );
    assert.deepEqual(wallViolations(cheater.snapshots), [], 'aucune boîte dans un mur');
    assert.equal(cheater.closeCode, null, 'connexion toujours ouverte (moins de 50 refus)');
    // Budget cumulé du serveur : depuis l'arrivée, au plus (ticks écoulés + 20) entrées appliquées,
    // donc distance ≤ sprint × dt × (ticks + 20) ; un client honnête n'utilise jamais la marge.
    const ticksAlive = traj[traj.length - 1].tick - cheater.snapshots[0].tick + 1;
    const bound = n.MOVEMENT.sprint_speed * TICK_S * (ticksAlive + 20);
    const start = cheater.snapshots[0].entities.find((e) => e.id === cheater.welcome.entity_id);
    const end = traj[traj.length - 1];
    const fromSpawn = Math.hypot(end.x - start.x, end.y - start.y);
    assert.ok(fromSpawn <= bound + 1e-6, `distance ${fromSpawn.toFixed(2)} > borne ${bound.toFixed(2)} (speed hack)`);
    // Sur la durée, pas plus vite que le sprint : la marge ne sert qu'une fois.
    assert.ok(windowSpeed <= n.MOVEMENT.sprint_speed * 2.5, `pointe sur 1 s = ${windowSpeed.toFixed(2)} t/s`);
  } finally {
    await cheater.close();
  }
});

test('gel réseau de 1 s : le retard d’entrées côté serveur se résorbe (rattrapage)', { timeout: TIMEOUT }, async () => {
  // Client honnête à 20 entrées/s sur échéances fixes (comme le navigateur) ; ses envois sont
  // bloqués 1 s (réseau gelé) puis délivrés d'un coup, comme le ferait TCP.
  const c = await n.openZoneSocket(await n.apiAccountWithCharacter());
  try {
    const t0 = performance.now();
    let k = 0;
    let held = [];
    const lag = [];
    await new Promise((done) => {
      const loop = () => {
        const t = performance.now() - t0;
        while (k * 50 <= t) {
          k += 1;
          const d = { move_x: k % 40 < 20 ? 1 : -1, move_y: 0, aim: 0, sprint: false };
          if (t > 2000 && t < 3000) held.push(d);
          else {
            for (const x of held) c.send('input', x);
            held = [];
            c.send('input', d);
          }
        }
        const snap = c.snapshots[c.snapshots.length - 1];
        if (snap) lag.push({ t, behind: c.seq - snap.ack });
        if (t < 9000) setTimeout(loop, 10);
        else done();
      };
      loop();
    });
    const before = Math.max(...lag.filter((l) => l.t > 1000 && l.t < 2000).map((l) => l.behind));
    const after = Math.max(...lag.filter((l) => l.t > 6000).map((l) => l.behind));
    console.log(`# gel 1 s : retard max avant ${before} entrées, 3 s après le gel ${after} entrées`);
    // Sans rattrapage, ~18 entrées (0,9 s) de retard resteraient en file pour toute la session.
    assert.ok(after <= before + 2, `retard d’entrées persistant après le gel : ${after} entrées (avant : ${before})`);
  } finally {
    await c.close();
  }
});

// -------------------------------------------------------------------------------------------------

const LAG_BASE_URL = process.env.DR_E2E_LAG_BASE_URL || '';
const LAG_MS = Number(process.env.DR_E2E_LAG_MS || 75); // par sens : RTT + 2 × LAG_MS
const LAG_JITTER_MS = Number(process.env.DR_E2E_LAG_JITTER_MS || 0); // gigue par sens, ordre conservé
const LAG_PROXY_PORT = Number(process.env.DR_E2E_LAG_PROXY_PORT || 8150);
const [API_HOST, API_PORT] = (process.env.DR_E2E_API_TARGET || '127.0.0.1:8000').split(':');

test(
  `latence ${2 * LAG_MS} ms (RTT) : erreur de réconciliation < 0,25 tuile et aucun saut du joueur local`,
  { timeout: TIMEOUT, skip: LAG_BASE_URL ? false : 'DR_E2E_LAG_BASE_URL non défini (voir e2e/README.md)' },
  async () => {
    const proxy = await startLatencyProxy({
      listenPort: LAG_PROXY_PORT,
      targetHost: API_HOST,
      targetPort: Number(API_PORT),
      delayMs: LAG_MS,
      jitterMs: LAG_JITTER_MS,
    });
    let browser = null;
    try {
      browser = await h.launchBrowser();
      const context = await browser.newContext({
        baseURL: LAG_BASE_URL,
        viewport: { width: 1280, height: 800 },
        deviceScaleFactor: 2,
        locale: 'fr-FR',
      });
      const page = await context.newPage();
      const consoleErrors = [];
      page.on('console', (m) => m.type() === 'error' && consoleErrors.push(m.text()));
      page.on('pageerror', (e) => consoleErrors.push(String(e)));
      const account = h.uniqueAccount();
      await h.registerViaUi(page, account);
      await h.createCharacterViaUi(page, account);
      await h.joinZoneViaUi(page, account);
      await page.getByTestId('world-position').filter({ hasText: /\d+,\d/ }).waitFor({ timeout: 20_000 });

      // Le ping mesuré inclut bien la latence ajoutée.
      await page.waitForTimeout(2_500);
      const ping = Number((await h.hudValue(page, 'Ping')).replace(/\D/g, ''));
      assert.ok(ping >= 2 * LAG_MS - 5, `ping affiché ${ping} ms (latence ajoutée ${2 * LAG_MS} ms)`);

      // Intervalles entre images (fluidité du rendu) pendant le parcours.
      await page.evaluate(() => {
        window.__qaFrames = [];
        let last = performance.now();
        const loop = (t) => {
          window.__qaFrames.push(t - last);
          last = t;
          if (window.__qaFrames.length < 5000) requestAnimationFrame(loop);
        };
        requestAnimationFrame(loop);
      });

      const samples = [];
      let sampling = true;
      // Un échantillon toutes les 100 ms (échéances fixes), lu en une seule évaluation.
      const sampler = (async () => {
        const origin = Date.now();
        for (let k = 1; sampling; k += 1) {
          const { pos, corr } = await page.evaluate(() => ({
            pos: document.querySelector('[data-testid="world-position"]')?.textContent ?? '',
            corr: document.querySelector('[data-testid="world-correction"]')?.textContent ?? '',
          }));
          samples.push({ t: Date.now(), pos: parsePosition(pos), corr: parseCorrection(corr) });
          await n.sleep(Math.max(0, origin + k * 100 - Date.now()));
        }
      })();

      // ~10 s : marche, sprint, changements de direction, poussée contre un mur.
      await hold(page, ['KeyD'], 1_500);
      await hold(page, ['ShiftLeft', 'KeyD'], 1_500);
      await hold(page, ['ShiftLeft', 'KeyA'], 1_500);
      await hold(page, ['ShiftLeft', 'KeyS'], 2_500); // bâtiment au sud du point d’apparition
      for (let i = 0; i < 6; i += 1) await hold(page, [i % 2 ? 'KeyA' : 'KeyD', 'KeyS'], 250); // zigzag contre le mur
      await hold(page, ['KeyW', 'KeyA'], 1_000);
      await page.waitForTimeout(800);
      sampling = false;
      await sampler;

      const corrections = samples.map((s) => s.corr).filter(Number.isFinite);
      const maxCorrection = Math.max(...corrections);
      // Saut = déplacement entre deux échantillons au-delà de ce que permet le sprint pendant
      // l’intervalle, plus la période de rafraîchissement du HUD (200 ms) et l’arrondi (0,1).
      let maxJump = 0;
      let maxExcess = -Infinity;
      for (let i = 1; i < samples.length; i += 1) {
        const p = samples[i - 1].pos;
        const q = samples[i].pos;
        if (!p || !q) continue;
        const d = Math.hypot(q.x - p.x, q.y - p.y);
        const dt = (samples[i].t - samples[i - 1].t) / 1000;
        maxJump = Math.max(maxJump, d);
        maxExcess = Math.max(maxExcess, d - (n.MOVEMENT.sprint_speed * (dt + 0.2) + 0.1));
      }
      const frames = (await page.evaluate(() => window.__qaFrames)).slice(1).sort((x, y) => x - y);
      const p95 = frames[Math.floor(frames.length * 0.95)] ?? 0;
      console.log(
        `# latence ${2 * LAG_MS} ms (gigue ${LAG_JITTER_MS} ms/sens) : ping ${ping} ms, ${samples.length} échantillons, correction max ${maxCorrection.toFixed(2)} t, ` +
          `saut max entre échantillons ${maxJump.toFixed(2)} t (excès ${maxExcess.toFixed(2)} t), images ${frames.length} (p95 ${p95.toFixed(1)} ms, max ${frames[frames.length - 1]?.toFixed(1)} ms)`,
      );
      assert.ok(samples.length >= 80, `${samples.length} échantillons`);
      assert.ok(maxCorrection < 0.25, `correction max ${maxCorrection} tuile`);
      assert.ok(maxExcess <= 0, `saut de position : ${maxExcess.toFixed(2)} tuile au-delà du sprint (saut max ${maxJump})`);
      assert.ok(maxJump <= 1.5, `saut de position ${maxJump} tuile entre deux échantillons`);
      assert.deepEqual(consoleErrors, [], 'aucune erreur console');
    } finally {
      await browser?.close();
      await proxy.close();
    }
  },
);
