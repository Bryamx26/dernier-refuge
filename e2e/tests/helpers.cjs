// Outils partagés des tests de bout en bout (Playwright piloté depuis node:test).
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const BASE_URL = process.env.DR_E2E_BASE_URL || 'http://localhost:5173';
// Dossier des captures d'écran ; désactivé si vide.
const SCREENSHOT_DIR = process.env.DR_E2E_SCREENSHOTS || '';
// Chromium préinstallé (ex. /opt/pw-browsers/chromium) si la version de Playwright ne correspond pas.
const EXECUTABLE_PATH = process.env.DR_E2E_CHROMIUM || undefined;

function launchBrowser() {
  return chromium.launch({ headless: true, executablePath: EXECUTABLE_PATH });
}

async function newPage(browser) {
  const context = await browser.newContext({
    baseURL: BASE_URL,
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 2,
    locale: 'fr-FR',
  });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => consoleErrors.push(String(err)));
  return { context, page, consoleErrors };
}

/** Suffixe aléatoire en lettres seules (les noms de personnage n'acceptent pas les chiffres). */
function letters(n) {
  const alphabet = 'abcdefghijklmnopqrstuvwxyz';
  let out = '';
  for (let i = 0; i < n; i += 1) out += alphabet[Math.floor(Math.random() * alphabet.length)];
  return out;
}

function uniqueAccount() {
  const suffix = letters(8);
  return {
    username: `qa_${suffix}`,
    password: `Refuge-${suffix}-2026`,
    character: `Survivant ${suffix[0].toUpperCase()}${suffix.slice(1)}`,
  };
}

async function screenshot(page, name) {
  if (!SCREENSHOT_DIR) return;
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, name) });
}

// --- Parcours dans l'interface ------------------------------------------------------------------

async function registerViaUi(page, account) {
  await page.goto('/');
  await page.getByRole('tab', { name: 'Inscription' }).click();
  await page.getByLabel('Pseudo').fill(account.username);
  await page.getByLabel('Mot de passe').fill(account.password);
  await page.getByLabel('Confirmation').fill(account.password);
  await page.getByRole('button', { name: "S'inscrire" }).click();
  await page.getByRole('heading', { name: 'Survivants' }).waitFor();
}

async function loginViaUi(page, account) {
  await page.getByRole('tab', { name: 'Connexion' }).click();
  await page.getByLabel('Pseudo').fill(account.username);
  await page.getByLabel('Mot de passe').fill(account.password);
  await page.getByRole('button', { name: 'Se connecter' }).click();
  await page.getByRole('heading', { name: 'Survivants' }).waitFor();
}

async function createCharacterViaUi(page, account) {
  await page.getByLabel('Nom').fill(account.character);
  await page.getByRole('button', { name: 'Créer' }).click();
  await page.getByText(account.character, { exact: true }).waitFor();
}

async function joinZoneViaUi(page, account) {
  const row = page.locator('li', { hasText: account.character });
  await row.getByRole('button', { name: 'Rejoindre' }).click();
  await page.getByTestId('net-state').filter({ hasText: 'En ligne' }).waitFor({ timeout: 10_000 });
}

/** Valeur d'une ligne du panneau « Liaison » du HUD (Ping, Tick, Zone…). */
function hudValue(page, label) {
  return page
    .locator('section[aria-label="Liaison réseau"] div')
    .filter({ has: page.locator('dt', { hasText: new RegExp(`^${label}$`) }) })
    .locator('dd')
    .innerText();
}

// --- API REST (via le proxy Vite) --------------------------------------------------------------

async function apiLogin(account) {
  const res = await fetch(`${BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: account.username, password: account.password }),
  });
  if (!res.ok) throw new Error(`login API ${res.status}`);
  return (await res.json()).access_token;
}

async function zoneOnline(token, zoneId = 'valcendre') {
  const res = await fetch(`${BASE_URL}/api/zones`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new Error(`zones API ${res.status}`);
  const zones = await res.json();
  const zone = zones.find((z) => z.id === zoneId);
  if (!zone) throw new Error(`zone ${zoneId} absente`);
  return zone.online;
}

/** Attend que `fn()` renvoie `expected` (polling), sinon renvoie la dernière valeur. */
async function waitForValue(fn, expected, timeoutMs = 5_000) {
  const deadline = Date.now() + timeoutMs;
  let value;
  while (Date.now() < deadline) {
    value = await fn();
    if (value === expected) return value;
    await new Promise((r) => setTimeout(r, 200));
  }
  return value;
}

module.exports = {
  BASE_URL,
  launchBrowser,
  newPage,
  uniqueAccount,
  screenshot,
  registerViaUi,
  loginViaUi,
  createCharacterViaUi,
  joinZoneViaUi,
  hudValue,
  apiLogin,
  zoneOnline,
  waitForValue,
};
