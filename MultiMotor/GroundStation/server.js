/**
 * EMAX Ground Station — Node.js Bridge Server
 * Bridges: Browser (WebSocket) ↔ Serial (USB) ↔ NUCLEO-C092RC
 */

const express = require('express');
const http = require('http');
const path = require('path');
const { WebSocketServer } = require('ws');
const { SerialPort } = require('serialport');
const { ReadlineParser } = require('@serialport/parser-readline');

const BAUD_RATE = 115200;
const PORT = 3000;

/* ── Auto-detect NUCLEO serial port ─────────────────────────── */
async function findNucleoPort() {
    const ports = await SerialPort.list();
    // Look for ST-LINK VCP (usbmodem on macOS, COM* on Windows)
    const nucleo = ports.find(p =>
        (p.path.includes('cu.usbmodem')) ||
        (p.path.includes('usbmodem') && !p.path.includes('tty')) ||
        (p.manufacturer && p.manufacturer.includes('STMicro')) ||
        (p.vendorId === '0483')
    );
    if (nucleo) return nucleo.path;
    // Fallback: first available port
    if (ports.length > 0) return ports[0].path;
    return null;
}

/* ── Express + WebSocket ────────────────────────────────────── */
const app = express();
const server = http.createServer(app);
const wss = new WebSocketServer({ server });

app.use(express.static(path.join(__dirname, 'public')));

/* ── State ──────────────────────────────────────────────────── */
let serial = null;
let serialParser = null;
let serialConnected = false;

/* ── Broadcast to all WebSocket clients ─────────────────────── */
function broadcast(data) {
    const msg = typeof data === 'string' ? data : JSON.stringify(data);
    wss.clients.forEach(client => {
        if (client.readyState === 1) client.send(msg);
    });
}

/* ── Connect to serial port ─────────────────────────────────── */
async function connectSerial() {
    let portPath = null;
    try {
        const ports = await SerialPort.list();
        const nucleo = ports.find(p =>
            (p.path.includes('usbmodem')) && (p.vendorId === '0483')
        );
        if (nucleo) {
            // Prefer cu. on macOS (reliable for serial I/O)
            portPath = nucleo.path.replace('/dev/tty.', '/dev/cu.');
        }
    } catch (e) {}

    if (!portPath) {
        console.log('⚠  No NUCLEO found. Waiting...');
        broadcast({ type: 'serial', status: 'disconnected', msg: 'No NUCLEO detected' });
        setTimeout(connectSerial, 3000);  // retry
        return;
    }

    console.log(`🔌 Connecting to NUCLEO on ${portPath} @ ${BAUD_RATE} baud`);

    serial = new SerialPort({
        path: portPath,
        baudRate: BAUD_RATE,
        autoOpen: true
    });

    serial.on('open', () => {
        serialConnected = true;
        console.log(`✅ Serial connected: ${portPath}`);
        broadcast({ type: 'serial', status: 'connected', port: portPath });
    });

    serial.on('close', () => {
        serialConnected = false;
        console.log('❌ Serial disconnected');
        broadcast({ type: 'serial', status: 'disconnected' });
        setTimeout(connectSerial, 3000);  // auto-reconnect
    });

    serial.on('error', (err) => {
        console.error('Serial error:', err.message);
        broadcast({ type: 'serial', status: 'error', msg: err.message });
    });

    /* Parse newline-delimited messages from NUCLEO */
    serialParser = serial.pipe(new ReadlineParser({ delimiter: '\n' }));
    serialParser.on('data', (data) => {
        const line = data.toString().trim();
        if (line.length > 0) {
            broadcast({ type: 'telemetry', data: line });
        }
    });
}

/* ── WebSocket: browser commands → serial ───────────────────── */
wss.on('connection', (ws) => {
    console.log('🖥  Browser connected');
    ws.send(JSON.stringify({
        type: 'serial',
        status: serialConnected ? 'connected' : 'disconnected'
    }));

    ws.on('message', (msg) => {
        const cmd = msg.toString().trim();
        if (serial && serialConnected) {
            serial.write(cmd + '\n');
        }
    });

    ws.on('close', () => {
        console.log('🖥  Browser disconnected');
    });
});

/* ── Start ──────────────────────────────────────────────────── */
server.listen(PORT, () => {
    console.log('');
    console.log('╔══════════════════════════════════════════════╗');
    console.log('║   🚁 EMAX Ground Station                    ║');
    console.log(`║   Open: http://localhost:${PORT}               ║`);
    console.log('╚══════════════════════════════════════════════╝');
    console.log('');
    connectSerial();
});
