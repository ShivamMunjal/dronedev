#!/usr/bin/env python3
"""
Hobbywing X6 Plus - Web Interface
=================================
Runs a DroneCAN node in the background while serving a simple HTTP API 
and an HTML dashboard for 0-100% throttle control and live telemetry.
"""

import sys
import time
import json
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
import dronecan
from dronecan.driver.common import AbstractDriver, CANFrame

# Import Waveshare low-level driver
from waveshare_can import WaveshareCAN, detect_adapter, CAN_BAUD_500K, CAN_MODE_NORMAL
from waveshare_can import CANFrame as WsFrame

# --- Global State ---
_target_throttle = 0  # 0 to 8191
TELEM = {'voltage': 0.0, 'current': 0.0, 'rpm': 0, 'temp': 0}

# --- Custom DroneCAN Driver for Waveshare ---
class WaveshareDriver(AbstractDriver):
    def __init__(self, port=None, bitrate=500000, **kwargs):
        super().__init__()
        self._ws = WaveshareCAN()
        self._closed = False
        self._rx_buffer = []
        
        port = port or detect_adapter()
        if not port:
            raise Exception("No Waveshare adapter found!")
            
        if not self._ws.open(port):
            raise Exception(f"Failed to open {port}")
            
        baud_map = {1000000: 0x01, 500000: 0x03, 250000: 0x05, 125000: 0x07}
        self._ws.configure(
            can_baud=baud_map.get(bitrate, CAN_BAUD_500K),
            frame_type=0x02,
            mode=CAN_MODE_NORMAL,
            use_variable_protocol=True
        )
        time.sleep(0.3)
    
    def close(self):
        if not self._closed:
            self._closed = True
            self._ws.close()
    
    def receive(self, timeout=None):
        if self._closed: return None
        if not self._rx_buffer:
            frames = self._ws.receive(timeout=timeout or 0.001)
            for f in frames:
                self._rx_buffer.append(CANFrame(
                    can_id=f.can_id, data=f.data, extended=f.is_extended,
                    ts_monotonic=time.monotonic(), ts_real=time.time()
                ))
        if self._rx_buffer:
            cf = self._rx_buffer.pop(0)
            self._call_hooks(self.FRAME_DIRECTION_INCOMING, cf)
            return cf
        return None
    
    def send(self, message_id, message, extended=False, canfd=False):
        if self._closed: return
        self._ws.send_frame(WsFrame(can_id=message_id, data=bytes(message), is_extended=extended))
        
    def _call_hooks(self, direction, frame):
        for hook in getattr(self, '_io_hooks', []):
            try: hook(direction, frame)
            except: pass

# --- Telemetry Handlers ---
def on_esc_status(event):
    TELEM['voltage'] = event.message.voltage / 10.0  
    TELEM['current'] = event.message.current
    TELEM['rpm'] = event.message.rpm

def on_hw_status1(event):
    TELEM['rpm'] = event.message.rpm

def on_hw_status2(event):
    TELEM['voltage'] = event.message.input_voltage * 0.1
    TELEM['current'] = event.message.current * 0.1
    TELEM['temp'] = event.message.temperature

# --- Web Server Handler ---
class WebHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/telem':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(TELEM).encode())
        elif self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            try:
                with open('index.html', 'rb') as f:
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.wfile.write(b"index.html not found!")
        else:
            super().do_GET()

    def do_POST(self):
        global _target_throttle
        if self.path == '/api/throttle':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode())
                if 'throttle' in data:
                    pct = max(0.0, min(100.0, float(data['throttle'])))
                    # Map 0-100% to 0-8191 DroneCAN RawCommand
                    _target_throttle = int((pct / 100.0) * 8191)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "raw": _target_throttle}).encode())
            except Exception as e:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_error(404)
            
    # Disable logging to avoid spam
    def log_message(self, format, *args):
        pass

def dronecan_thread():
    global _target_throttle
    try:
        driver = WaveshareDriver(bitrate=500000)
        node = dronecan.node.Node(driver, node_id=10)
        node.mode = dronecan.uavcan.protocol.NodeStatus().MODE_OPERATIONAL
    except Exception as e:
        print(f"Failed to initialize CAN: {e}")
        return

    # Safety Heartbeats
    node.periodic(0.1, lambda: node.broadcast(dronecan.uavcan.equipment.safety.ArmingStatus(status=255)))

    # Telemetry
    node.add_handler(dronecan.uavcan.equipment.esc.Status, on_esc_status)
    node.add_handler(dronecan.com.hobbywing.esc.StatusMsg1, on_hw_status1)
    node.add_handler(dronecan.com.hobbywing.esc.StatusMsg2, on_hw_status2)

    # Initial Configuration
    print("⚙️  Configuring ESC via CAN...")
    node.request(dronecan.com.hobbywing.esc.SetThrottleSource.Request(source=0), 1, lambda e: None)
    node.request(dronecan.com.hobbywing.esc.SetID.Request(node_id=1, throttle_channel=1), 1, lambda e: None)

    # Give ESC time to configure
    start_time = time.time()
    while time.time() - start_time < 1.0:
        node.spin(timeout=0.1)

    print("🚀 DroneCAN Engine Running! Sending throttle at 100Hz.")
    while True:
        # Throttle is updated by the web thread
        msg = dronecan.com.hobbywing.esc.RawCommand(command=[_target_throttle, 0, 0, 0])
        node.broadcast(msg, priority=0)
        node.spin(timeout=0.01)

def main():
    print("=" * 60)
    print(" 🌐 Hobbywing Web Dashboard Starting...")
    print("=" * 60)
    
    # Start DroneCAN in background
    can_thread = threading.Thread(target=dronecan_thread, daemon=True)
    can_thread.start()
    
    # Start Web Server
    port = 8080
    server = HTTPServer(('0.0.0.0', port), WebHandler)
    print(f"\n🌍 Web Interface active!")
    print(f"👉 Open this link in your browser:  http://localhost:{port}\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down server...")
        server.server_close()
        # Set throttle to 0 in CAN thread before exit? 
        # (Daemon thread will die, but hardware usually stops on timeout)

if __name__ == "__main__":
    main()
