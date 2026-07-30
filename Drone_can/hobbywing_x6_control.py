#!/usr/bin/env python3
"""
Hobbywing X6 Plus - DroneCAN Motor Control Script
=================================================
This script connects to a Hobbywing X6 Plus ESC using a Waveshare USB-CAN-A adapter.
It dynamically configures the ESC for CAN control, arms it, and provides real-time 
throttle control while printing live telemetry (RPM, Voltage, Current, Temp).

Hardware Setup:
- Waveshare USB-CAN-A connected to Mac.
- 120-ohm terminating resistor connected between CAN_H and CAN_L.
- Motor securely mounted with NO PROPELLERS.

Usage:
  python hobbywing_x6_control.py
"""

import sys
import time
import signal
import threading
import dronecan
import dronecan.node
from dronecan.driver.common import AbstractDriver, CANFrame

# Import Waveshare low-level driver from your workspace
from waveshare_can import WaveshareCAN, detect_adapter, CAN_BAUD_500K, CAN_MODE_NORMAL
from waveshare_can import CANFrame as WsFrame

# --- Global State ---
_stop = False
_target_throttle = 0  # Range: 0 to 8191

def sigint(s, f):
    global _stop
    _stop = True
    print("\n🛑 STOPPING...")
signal.signal(signal.SIGINT, sigint)

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
TELEM = {'voltage': 0.0, 'current': 0.0, 'rpm': 0, 'temp': 0}
def on_esc_status(event):
    # Hobbywing populates voltage as Decivolts instead of Volts. Scaling it down.
    TELEM['voltage'] = event.message.voltage / 10.0  
    TELEM['current'] = event.message.current
    TELEM['rpm'] = event.message.rpm

def on_hw_status1(event):
    TELEM['rpm'] = event.message.rpm

def on_hw_status2(event):
    TELEM['voltage'] = event.message.input_voltage * 0.1
    TELEM['current'] = event.message.current * 0.1
    TELEM['temp'] = event.message.temperature

# --- CLI Input Thread ---
def input_loop():
    global _target_throttle, _stop
    while not _stop:
        try:
            # We use a simple prompt. It might visually clash with telemetry, but it works reliably.
            val = input()
            if val.strip().lower() == 'q':
                _stop = True
                break
            _target_throttle = max(0, min(8191, int(val)))
        except ValueError:
            pass

def main():
    global _stop, _target_throttle
    
    print("=" * 60)
    print(" 🚁 Hobbywing X6 Plus - Live Control")
    print(" ⚠️  Ensure PROPELLERS ARE REMOVED!")
    print("=" * 60)

    try:
        driver = WaveshareDriver(bitrate=500000)
        node = dronecan.node.Node(driver, node_id=10)
        node.mode = dronecan.uavcan.protocol.NodeStatus().MODE_OPERATIONAL
    except Exception as e:
        print(f"Failed to initialize CAN: {e}")
        return

    # 1. Broadcast Arming Status (Required by flight controller safety logic)
    node.periodic(0.1, lambda: node.broadcast(dronecan.uavcan.equipment.safety.ArmingStatus(status=255)))

    # Register handlers
    node.add_handler(dronecan.uavcan.equipment.esc.Status, on_esc_status)
    node.add_handler(dronecan.com.hobbywing.esc.StatusMsg1, on_hw_status1)
    node.add_handler(dronecan.com.hobbywing.esc.StatusMsg2, on_hw_status2)

    # 2. Configure ESC for CAN Digital mode
    print("⚙️  Configuring ESC (Switching to CAN_DIGITAL & Assigning Channel 1)...")
    node.request(dronecan.com.hobbywing.esc.SetThrottleSource.Request(source=0), 1, lambda e: None)
    
    # 3. Assign Throttle Channel (CRITICAL STEP - By default they are unassigned and ignore throttle)
    node.request(dronecan.com.hobbywing.esc.SetID.Request(node_id=1, throttle_channel=1), 1, lambda e: None)

    # 4. Give the ESC a second to process configuration
    start_time = time.time()
    while time.time() - start_time < 1.0:
        node.spin(timeout=0.1)

    print("\n✅ Setup Complete!")
    print("\n" + "="*60)
    print(" 🎮 CONTROLS:")
    print(" Type a number between 0 and 8191 and press ENTER to set throttle.")
    print(" Type '0' to stop immediately.")
    print(" Type 'q' to quit.")
    print("="*60 + "\n")

    # Start keyboard listener
    threading.Thread(target=input_loop, daemon=True).start()

    # Main control loop
    last_print = 0
    try:
        while not _stop:
            # Broadcast the proprietary Hobbywing RawCommand message (Required for X6 Plus)
            msg = dronecan.com.hobbywing.esc.RawCommand(command=[_target_throttle, 0, 0, 0])
            node.broadcast(msg, priority=0)
            
            # Spin the node to process incoming telemetry and background tasks
            node.spin(timeout=0.01)

            # Print telemetry at ~10Hz
            if time.time() - last_print > 0.1:
                # \r overwrites the current line. We pad with spaces to clear old text.
                print(f"\r⚡ Throttle: {_target_throttle:4d} / 8191  |  RPM: {TELEM['rpm']:5d}  |  "
                      f"V: {TELEM['voltage']:5.1f}V  |  I: {TELEM['current']:5.1f}A  |  "
                      f"Temp: {TELEM['temp']}°C   (Type new throttle & press Enter) ", end="", flush=True)
                last_print = time.time()
                
    except KeyboardInterrupt:
        _stop = True

    # Safely stop the motor before exiting
    print("\n\n🛑 Shutting down... Stopping motor.")
    for _ in range(20):
        try:
            node.broadcast(dronecan.com.hobbywing.esc.RawCommand(command=[0, 0, 0, 0]), priority=0)
            node.spin(timeout=0.01)
        except:
            pass

    driver.close()
    print("🔌 Disconnected.")

if __name__ == "__main__":
    main()
