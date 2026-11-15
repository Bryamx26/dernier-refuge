// Phase 3 — zombies, combat, fouille, inventaire, survie, dans un vrai navigateur.
// Prérequis : pile démarrée (voir e2e/README.md), contenu de jeu du dépôt.
"use strict";

const assert = require("node:assert/strict");
const { test } = require("node:test");
const h = require("./helpers.cjs");

const TIMEOUT = 120_000;

/** Enregistre les messages serveur reçus par la page (sans les snapshots, sauf le dernier). */
function recordFrames(page) {
  const state = { messages: [], last: null };
  page.on("websocket", (ws) =>
    ws.on("framereceived", (frame) => {
      let m;
      try {
        m = JSON.parse(frame.payload);
      } catch {
        return;
      }
      if (m.t === "snapshot") state.last = m;
      else state.messages.push(m);
    }),
  );
  return state;
}

/** Marche (touches ZQSD physiques) jusqu'à (tx, ty), d'après les snapshots serveur. */
async function walkTo(page, state, tx, ty, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const me = state.last.d.entities.find((e) => e.kind === "player");
    const dx = tx - me.x;
    const dy = ty - me.y;
    if (Math.hypot(dx, dy) < 0.5) return me;
    const keys = [];
    if (dx > 0.3) keys.push("KeyD");
    if (dx < -0.3) keys.push("KeyA");
    if (dy > 0.3) keys.push("KeyS");
    if (dy < -0.3) keys.push("KeyW");
    for (const k of keys) await page.keyboard.down(k);
    await page.waitForTimeout(100);
    for (const k of keys) await page.keyboard.up(k);
  }
  return state.last.d.entities.find((e) => e.kind === "player");
}

test(
  "arrivée : équipement de départ, HUD de survie, coup de couteau, inventaire",
  { timeout: TIMEOUT },
  async () => {
    const browser = await h.launchBrowser();
    try {
      const { page, consoleErrors } = await h.newPage(browser);
      const state = recordFrames(page);
      const account = h.uniqueAccount();
      await h.registerViaUi(page, account);
      await h.createCharacterViaUi(page, account);
      await h.joinZoneViaUi(page, account);

      // Inventaire de départ : couteau en main, eau, biscuits, bandage.
      await page
        .getByTestId("weapon")
        .filter({ hasText: "Couteau de cuisine" })
        .waitFor();
      assert.equal(await page.getByTestId("vital-health").innerText(), "100");
      const inventory = state.messages.filter((m) => m.t === "inventory").pop();
      assert.deepEqual(inventory.d.slots.map((s) => s.item).sort(), [
        "bandage",
        "biscuits",
        "knife",
        "water_bottle",
      ]);
      assert.equal(
        inventory.d.slots.find((s) => s.slot === inventory.d.equipped).item,
        "knife",
      );

      // Nouveau personnage : sur un point d'apparition de la carte (place du village).
      const me = state.last.d.entities.find((e) => e.kind === "player");
      assert.ok(
        me.x > 57 && me.x < 66 && me.y > 49 && me.y < 58,
        `apparition en ${me.x}, ${me.y}`,
      );

      // Monde prêt (carte chargée, prédiction active) avant d'agir.
    await page.getByTestId('world-position').filter({ hasText: /\d/ }).waitFor();
    // Clic gauche : un coup (effet `swing` renvoyé par le serveur).
      await page.mouse.move(800, 400);
      await page.mouse.down();
      await page.waitForTimeout(120);
      await page.mouse.up();
      await page.waitForTimeout(300);
      const swings = state.messages
        .filter((m) => m.t === "fx")
        .flatMap((m) => m.d.events)
        .filter((e) => e.kind === "swing");
      assert.ok(swings.length >= 1, "coup visible");

      // I : inventaire ; « Boire » consomme la bouteille.
      await page.keyboard.press("KeyI");
      const panel = page.getByTestId("inventory");
      await panel.waitFor();
      await h.screenshot(page, "phase3-01-inventaire.png");
      await page
        .getByTestId("slot-water_bottle")
        .getByRole("button", { name: "Boire" })
        .click();
      await page
        .getByTestId("slot-water_bottle")
        .waitFor({ state: "detached" });
      await page
        .getByTestId("notice")
        .filter({ hasText: "Utilisé : Bouteille d'eau" })
        .waitFor();
      assert.deepEqual(consoleErrors, []);
    } finally {
      await browser.close();
    }
  },
);

test(
  "fouille de la maison du notaire : barre de progression puis butin",
  { timeout: TIMEOUT },
  async () => {
    const browser = await h.launchBrowser();
    try {
      const { page } = await h.newPage(browser);
      const state = recordFrames(page);
      const account = h.uniqueAccount();
      await h.registerViaUi(page, account);
      await h.createCharacterViaUi(page, account);
      await h.joinZoneViaUi(page, account);
      await page.getByTestId("weapon").waitFor();
      // Porte (82, 45) : par la rue au sud du bâtiment.
      await walkTo(page, state, 66, 52);
      await walkTo(page, state, 76, 47.6);
      await walkTo(page, state, 82.5, 47.6);
      const me = await walkTo(page, state, 82.5, 46.35, 3_000);
      assert.ok(
        Math.hypot(me.x - 82.5, me.y - 45.5) < 1.6,
        `devant la porte : ${me.x}, ${me.y}`,
      );
      await page.keyboard.press("KeyE");
      const progress = page.getByTestId("action-progress");
      // Bâtiment déjà fouillé par une exécution précédente : message explicite, sans barre.
      const outcome = await Promise.race([
        progress.waitFor().then(() => "search"),
        page
          .getByTestId("notice")
          .filter({ hasText: "déjà fouillé" })
          .waitFor()
          .then(() => "already"),
      ]);
      if (outcome === "search") {
        await h.screenshot(page, "phase3-02-fouille.png");
        await progress.waitFor({ state: "detached", timeout: 6_000 });
        await page
          .getByTestId("notice")
          .filter({ hasText: /Trouvé|rien trouvé/ })
          .waitFor();
      }
      const texts = state.messages
        .filter((m) => m.t === "notice")
        .map((m) => m.d.text);
      assert.ok(
        texts.some((t) => /Trouvé|rien trouvé|déjà fouillé/.test(t)),
        texts.join(" | "),
      );
    } finally {
      await browser.close();
    }
  },
);
