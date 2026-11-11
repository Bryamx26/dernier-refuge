// Proxy TCP qui ajoute une latence fixe (et une gigue optionnelle) dans les deux sens.
// Placé entre Vite et uvicorn, il retarde tout le trafic HTTP et WebSocket du client :
//
//   navigateur → Vite (VITE_PROXY_TARGET=http://localhost:<port>) → ce proxy → uvicorn
//
// Chaque chunk reçu est réémis après `delayMs` (+ gigue aléatoire dans [0, jitterMs]). L'ordre des
// octets est conservé (TCP) : un chunk n'est jamais émis avant le précédent du même sens.
//
// En ligne de commande :
//   node e2e/tools/latency-proxy.cjs --listen 8150 --target 127.0.0.1:8000 --delay 75 [--jitter 0]
// `--delay` est la latence **par sens** : 75 ms ≈ 150 ms ajoutées au RTT.
// En bibliothèque : `startLatencyProxy({ listenPort, targetHost, targetPort, delayMs, jitterMs })`.
'use strict';

const net = require('node:net');

// File FIFO par sens et un seul minuteur à la fois : l'ordre des chunks est garanti (des minuteurs
// indépendants, même à échéances croissantes, peuvent se déclencher dans le désordre et corrompre
// le flux TCP — c'est arrivé avec la gigue).
function delayedPipe(from, to, delayMs, jitterMs) {
  const queue = [];
  let lastDue = 0;
  let ended = false;
  let timer = null;
  const pump = () => {
    timer = null;
    const now = performance.now();
    while (queue.length && queue[0].due <= now) {
      const { chunk } = queue.shift();
      if (!to.destroyed) to.write(chunk);
    }
    if (queue.length) timer = setTimeout(pump, Math.max(0, queue[0].due - performance.now()));
    else if (ended && !to.destroyed) to.end();
  };
  from.on('data', (chunk) => {
    const due = Math.max(performance.now() + delayMs + Math.random() * jitterMs, lastDue);
    lastDue = due;
    queue.push({ chunk, due });
    if (!timer) timer = setTimeout(pump, Math.max(0, queue[0].due - performance.now()));
  });
  from.on('end', () => {
    ended = true;
    if (!timer) timer = setTimeout(pump, delayMs);
  });
}

function startLatencyProxy({ listenPort, targetHost = '127.0.0.1', targetPort, delayMs = 75, jitterMs = 0 }) {
  const sockets = new Set();
  const server = net.createServer((client) => {
    const upstream = net.connect(targetPort, targetHost);
    client.setNoDelay(true);
    upstream.setNoDelay(true);
    sockets.add(client);
    sockets.add(upstream);
    const destroyBoth = () => {
      client.destroy();
      upstream.destroy();
      sockets.delete(client);
      sockets.delete(upstream);
    };
    client.on('error', destroyBoth);
    upstream.on('error', destroyBoth);
    client.on('close', () => setTimeout(destroyBoth, delayMs + jitterMs + 10));
    upstream.on('close', () => setTimeout(destroyBoth, delayMs + jitterMs + 10));
    delayedPipe(client, upstream, delayMs, jitterMs);
    delayedPipe(upstream, client, delayMs, jitterMs);
  });
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(listenPort, '127.0.0.1', () => {
      resolve({
        port: server.address().port,
        close: () =>
          new Promise((done) => {
            for (const s of sockets) s.destroy();
            server.close(() => done());
          }),
      });
    });
  });
}

module.exports = { startLatencyProxy };

if (require.main === module) {
  const args = process.argv.slice(2);
  const opt = (name, fallback) => {
    const i = args.indexOf(`--${name}`);
    return i >= 0 ? args[i + 1] : fallback;
  };
  const [host, port] = opt('target', '127.0.0.1:8000').split(':');
  startLatencyProxy({
    listenPort: Number(opt('listen', '8150')),
    targetHost: host,
    targetPort: Number(port),
    delayMs: Number(opt('delay', '75')),
    jitterMs: Number(opt('jitter', '0')),
  }).then((p) => {
    console.log(`latency-proxy : 127.0.0.1:${p.port} → ${host}:${port}, ${opt('delay', '75')} ms par sens`);
  });
}
