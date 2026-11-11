// Phase 1 — parcours joueur de bout en bout dans un vrai navigateur.
// Prérequis : API (uvicorn) + Postgres + Redis + client Vite démarrés (voir e2e/README.md).
'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const h = require('./helpers.cjs');

const TIMEOUT = 60_000;

test('inscription → connexion → personnage → zone : le HUD affiche En ligne, un ping et un tick qui augmente', { timeout: TIMEOUT }, async () => {
  const browser = await h.launchBrowser();
  try {
    const { page, consoleErrors } = await h.newPage(browser);
    const account = h.uniqueAccount();

    // Écran de connexion (capture avant toute saisie).
    await page.goto('/');
    await page.getByRole('button', { name: 'Se connecter' }).waitFor();
    await page.evaluate(() => document.fonts.ready);
    await h.screenshot(page, '01-connexion.png');

    // Inscription (l'interface connecte automatiquement après l'inscription).
    await h.registerViaUi(page, account);

    // Déconnexion puis connexion explicite avec les mêmes identifiants.
    await page.getByRole('button', { name: 'Déconnexion' }).click();
    await page.getByRole('button', { name: 'Se connecter' }).waitFor();
    await h.loginViaUi(page, account);
    await page.getByText(account.username, { exact: true }).waitFor();

    // Création d'un personnage.
    await h.createCharacterViaUi(page, account);
    // La liste des zones est chargée (Valcendre, x/32).
    await page.getByText('Valcendre', { exact: true }).waitFor();
    await h.screenshot(page, '02-personnages.png');

    // Rejoindre la zone : WebSocket ouvert, welcome reçu.
    await h.joinZoneViaUi(page, account);

    // Ping : au moins un pong reçu (ping toutes les secondes).
    await page
      .locator('section[aria-label="Liaison réseau"] dd')
      .filter({ hasText: /^\d+ ms$/ })
      .waitFor({ timeout: 5_000 });
    const ping = await h.hudValue(page, 'Ping');
    assert.match(ping, /^\d+ ms$/, `ping affiché : ${ping}`);

    // Tick : nombre qui augmente entre deux lectures (le tick est recopié dans chaque pong).
    const tick1 = Number(await h.hudValue(page, 'Tick'));
    await page.waitForTimeout(2_500);
    const tick2 = Number(await h.hudValue(page, 'Tick'));
    assert.ok(Number.isInteger(tick1) && tick1 > 0, `tick initial : ${tick1}`);
    assert.ok(tick2 > tick1, `le tick doit augmenter (${tick1} → ${tick2})`);

    assert.equal(await h.hudValue(page, 'Zone'), 'Valcendre');
    assert.equal(await h.hudValue(page, 'Fréquence'), '20 Hz');
    await h.screenshot(page, '03-jeu-connecte.png');

    // Côté API, le personnage est compté en ligne.
    const token = await h.apiLogin(account);
    assert.equal(await h.waitForValue(() => h.zoneOnline(token), 1), 1);

    // Quitter la zone libère la place.
    await page.getByRole('button', { name: 'Quitter la zone' }).click();
    await page.getByRole('heading', { name: 'Survivants' }).waitFor();
    assert.equal(await h.waitForValue(() => h.zoneOnline(token), 0), 0, 'online revient à 0 après Quitter');

    assert.deepEqual(consoleErrors, [], 'aucune erreur dans la console du navigateur');
  } finally {
    await browser.close();
  }
});

test('deux navigateurs, deux comptes dans la même zone : online = 2 côté API', { timeout: TIMEOUT }, async () => {
  const browserA = await h.launchBrowser();
  const browserB = await h.launchBrowser();
  try {
    const a = h.uniqueAccount();
    const b = h.uniqueAccount();
    const tabA = await h.newPage(browserA);
    const tabB = await h.newPage(browserB);

    await Promise.all([h.registerViaUi(tabA.page, a), h.registerViaUi(tabB.page, b)]);
    await Promise.all([h.createCharacterViaUi(tabA.page, a), h.createCharacterViaUi(tabB.page, b)]);

    const token = await h.apiLogin(a);
    const baseline = await h.zoneOnline(token);
    assert.equal(baseline, 0, 'la zone doit être vide au départ (serveur dédié aux tests)');

    await Promise.all([h.joinZoneViaUi(tabA.page, a), h.joinZoneViaUi(tabB.page, b)]);
    assert.equal(await h.waitForValue(() => h.zoneOnline(token), 2), 2, 'deux joueurs en ligne');

    // Les deux HUD reçoivent des ticks.
    for (const { page } of [tabA, tabB]) {
      await page
        .locator('section[aria-label="Liaison réseau"] dd')
        .filter({ hasText: /^\d+ ms$/ })
        .waitFor({ timeout: 5_000 });
    }

    // Fermer brutalement un navigateur (sans « Quitter ») : le serveur détecte la déconnexion.
    await browserB.close();
    assert.equal(await h.waitForValue(() => h.zoneOnline(token), 1), 1, 'online = 1 après fermeture de B');

    assert.deepEqual(tabA.consoleErrors, [], 'aucune erreur console (A)');
  } finally {
    await browserA.close();
    await browserB.close().catch(() => {});
  }
});
