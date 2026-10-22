/**
 * IMU Ground Station — Node.js bridge
 *
 * Browser (WebSocket) <-> Serial (USB) <-> NUCLEO-C092RC running the IMU
 * firmware with MotionFX fusion.
 *
 * The firmware streams one mode at a time. This bridge asks for the fused
 * attitude stream ("a") and keeps asking until E, lines actually arrive, so a
 * booting board reliably ends up in the right mode.
 *
 * Fused line format (angles in milli-degrees):
 *   E,<t_ms>,<roll_mdeg>,<pitch_mdeg>,<yaw_mdeg>,<gbx_mdps>,<gby_mdps>,<gbz_mdps>
 */

const express = require('express');
const http = require('http');
const path = require('path');
const { WebSocketServer } = require('ws');
const { SerialPort } = require('serialport');
const { ReadlineParser } = require('@serialport/parser-readline');

const BAUD_RATE = 115200;
const PORT = process.env.PORT || 4100;

const app = express();
const server = http.createServer(app);
const wss = new WebSocketServer({ server });

app.use(express.static(path.join(__dirname, 'public')));

let serial = null;
let serialConnected = false;
let fusedSeen = false;
let askTimer = null;
let stats = { raw: 0, fused: 0 };

function broadcast(obj) {
    const msg = JSON.stringify(obj);
    wss.clients.forEach(c => { if (c.readyState === 1) c.send(msg); });
}

/* ── serial port discovery ─────────────────────────────────────────── */
async function findPort() {
    const ports = await SerialPort.list();
    const nucleo = ports.find(p =>
        (p.path.includes('usbmodem') && p.vendorId === '0483') ||
        (p.manufacturer && p.manufacturer.includes('STMicro')) ||
        p.path.includes('cu.usbmodem')
    );
    if (nucleo) return nucleo.path.replace('/dev/tty.', '/dev/cu.');
    return null;
}

/* Keep requesting the fused stream until E, lines show up. This is what makes
 * the dashboard work no matter what mode the board booted into. */
function ensureFused() {
    if (askTimer) return;
    askTimer = setInterval(() => {
        if (fusedSeen) { clearInterval(askTimer); askTimer = null; return; }
        if (serial && serialConnected) serial.write('a\n');
    }, 500);
    if (serial && serialConnected) serial.write('a\n');
}

function connectSerial() {
    findPort().then(portPath => {
        if (!portPath) {
            console.log('⚠  No NUCLEO found. Retrying...');
            broadcast({ type: 'serial', status: 'disconnected', msg: 'No NUCLEO detected' });
            setTimeout(connectSerial, 3000);
            return;
        }
        console.log(`🔌 ${portPath} @ ${BAUD_RATE}`);
        serial = new SerialPort({ path: portPath, baudRate: BAUD_RATE, autoOpen: true });

        serial.on('open', () => {
            serialConnected = true;
            fusedSeen = false;
            stats = { raw: 0, fused: 0 };
            console.log('✅ serial connected');
            broadcast({ type: 'serial', status: 'connected', port: portPath });
            serial.write('\n');
            ensureFused();
        });

        serial.on('close', () => {
            serialConnected = false;
            fusedSeen = false;
            console.log('❌ serial disconnected');
            broadcast({ type: 'serial', status: 'disconnected' });
            setTimeout(connectSerial, 3000);
        });

        serial.on('error', err => {
            console.error('Serial error:', err.message);
            broadcast({ type: 'serial', status: 'error', msg: err.message });
        });

        serial.pipe(new ReadlineParser({ delimiter: '\n' })).on('data', d => {
            const line = d.toString().trim();
            if (!line) return;

            if (line[0] === 'E' && line[1] === ',') {
                const p = line.substring(2).split(',');
                if (p.length >= 7) {
                    fusedSeen = true;
                    stats.fused++;
                    broadcast({
                        type: 'e',
                        t: +p[0],
                        roll: +p[1] / 1000,
                        pitch: +p[2] / 1000,
                        yaw: +p[3] / 1000,
                        gb: [+p[4] / 1000, +p[5] / 1000, +p[6] / 1000]
                    });
                }
            } else if (line[0] === '#' ) {
                broadcast({ type: 'log', data: line });
            } else if ((line[0] === 'I' || line[0] === 'S') && line[1] === ',') {
                stats.raw++;
                broadcast({ type: 'raw', kind: line[0] });
            } else {
                broadcast({ type: 'log', data: line });
            }
        });
    }).catch(e => {
        console.log('port scan error:', e.message);
        setTimeout(connectSerial, 3000);
    });
}

/* ── WebSocket ─────────────────────────────────────────────────────── */
wss.on('connection', ws => {
    console.log('🖥  browser connected');
    ws.send(JSON.stringify({
        type: 'serial',
        status: serialConnected ? 'connected' : 'disconnected'
    }));
    if (serialConnected) ensureFused();

    ws.on('message', m => {
        const cmd = m.toString().trim();
        if (!cmd) return;
        if (serial && serialConnected) serial.write(cmd + '\n');
        if (cmd[0] === 'a') { fusedSeen = false; ensureFused(); }
    });

    ws.on('close', () => console.log('🖥  browser disconnected'));
});

/* periodic stats to any client that wants them */
setInterval(() => {
    broadcast({ type: 'stats', raw: stats.raw, fused: stats.fused });
}, 1000);

server.listen(PORT, () => {
    console.log('');
    console.log('╔══════════════════════════════════════════════╗');
    console.log('║   IMU Ground Station (MotionFX 6X)          ║');
    console.log(`║   Open: http://localhost:${PORT}              ║`);
    console.log('╚══════════════════════════════════════════════╝');
    console.log('');
    connectSerial();
});
