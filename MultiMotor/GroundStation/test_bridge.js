/**
 * End-to-end test of the Ground Station bridge, standing in for the browser.
 * Verifies: serial connect, telemetry broadcast, and command round-trip
 * (including the new PMU `B` and mixer `Q` / `Y` messages).
 */
const WebSocket = require('ws');

const seen = [];
let ws;

function send(c) { ws.send(c); }

ws = new WebSocket('ws://localhost:3000');

ws.on('open', () => {
  console.log('browser-side WS connected');
  setTimeout(() => send('Q'), 600);                 // mixer geometry
  setTimeout(() => send('B'), 1200);                // battery snapshot
  setTimeout(() => send('Y1500,100,0,0'), 1600);    // dry-run mix
  setTimeout(() => send('W'), 2000);                // verbose gains
});

ws.on('message', (raw) => {
  let m;
  try { m = JSON.parse(raw.toString()); } catch { return; }
  if (m.type === 'serial') console.log('  [serial]', m.status, m.port || m.msg || '');
  if (m.type === 'telemetry') seen.push(m.data);
});

setTimeout(() => {
  const kind = (p) => seen.filter(l => l.startsWith(p));
  const T = kind('T'), B = kind('B,'), Q = kind('Q,'), Y = kind('Y,'), W = kind('W');
  console.log('\n── broadcast telemetry received by the browser ──');
  console.log(`  T (motor telemetry) : ${T.length}`);
  console.log(`  B (battery/PMU)     : ${B.length}`);
  console.log('\n── command responses ──');
  console.log('  Q geometry :', Q[0] || '(none)');
  console.log('  B battery  :', B[B.length - 1] || '(none)');
  console.log('  Y dry-run  :', Y[0] || '(none)');
  console.log('  W gains    :', W.length, 'rows; first =', W[0] || '(none)');
  const ok = T.length > 10 && B.length > 2 && Q.length === 1 && Y.length === 1 && W.length === 6;
  console.log('\nDATAPATH E2E:', ok ? 'PASS' : 'FAIL');
  process.exit(ok ? 0 : 1);
}, 3200);
