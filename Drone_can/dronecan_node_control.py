#!/usr/bin/env python3
"""
Hobbywing ESC — Full DroneCAN Node Motor Control
==================================================
Uses dronecan.node.Node with a custom Waveshare driver to get 
FULL DroneCAN protocol support (proper transfer IDs, CRC, heartbeats).

⚠️ REMOVE PROPELLERS!
"""

import sys
import time
import signal
import struct
import threading
import queue

import dronecan
import dronecan.node
from dronecan.driver.common import AbstractDriver, CANFrame

from waveshare_can import (
    WaveshareCAN, detect_adapter,
    CAN_BAUD_500K, CAN_MODE_NORMAL,
    CANFrame as WsFrame
)

_stop = False
def sigint(s, f):
    global _stop
    _stop = True
    print("\n🛑 STOPPING...")
signal.signal(signal.SIGINT, sigint)


class WaveshareDriver(AbstractDriver):
    """Wraps WaveshareCAN as a dronecan driver."""
    
    def __init__(self, port=None, bitrate=500000, **kwargs):
        super().__init__()
        self._ws = WaveshareCAN()
        self._closed = False
        self._rx_buffer = []
        
        port = port or detect_adapter()
        if not port:
            raise Exception("No Waveshare adapter found")
        
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
        print(f"   ✅ Waveshare driver ready at {bitrate} bps")
    
    def close(self):
        if not self._closed:
            self._closed = True
            self._ws.close()
    
    def __del__(self):
        self.close()
    
    def _call_hooks(self, direction, frame):
        for hook in getattr(self, '_io_hooks', []):
            try: hook(direction, frame)
            except: pass

    def receive(self, timeout=None):
        if self._closed:
            return None
        
        if not self._rx_buffer:
            frames = self._ws.receive(timeout=timeout or 0.001)
            for f in frames:
                self._rx_buffer.append(CANFrame(
                    can_id=f.can_id,
                    data=f.data,
                    extended=f.is_extended,
                    ts_monotonic=time.monotonic(),
                    ts_real=time.time()
                ))
                
        if self._rx_buffer:
            cf = self._rx_buffer.pop(0)
            self._call_hooks(self.FRAME_DIRECTION_INCOMING, cf)
            return cf
            
        return None
    
    def send(self, message_id, message, extended=False, canfd=False):
        if self._closed:
            return
        ws_frame = WsFrame(
            can_id=message_id,
            data=bytes(message),
            is_extended=extended
        )
        self._ws.send_frame(ws_frame)


# Telemetry state
TELEM = {
    'voltage': 0.0, 'current': 0.0, 'rpm': 0, 'temp': 0,
    'esc_temp': 0, 'motor_temp': 0, 'status_count': 0
}
TELEM_LOCK = threading.Lock()

def on_esc_status(event):
    with TELEM_LOCK:
        TELEM['voltage'] = event.message.voltage
        TELEM['current'] = event.message.current
        TELEM['rpm'] = event.message.rpm
        TELEM['status_count'] += 1

def on_hw_status1(event):
    with TELEM_LOCK:
        TELEM['rpm'] = event.message.rpm
        TELEM['status_count'] += 1

def on_hw_status2(event):
    with TELEM_LOCK:
        TELEM['voltage'] = event.message.input_voltage
        TELEM['status_count'] += 1

def get_telem():
    with TELEM_LOCK:
        return dict(TELEM)


def main():
    global _stop
    
    print("=" * 60)
    print("  Hobbywing ESC — DroneCAN Node Motor Control")
    print("  ⚠️  REMOVE PROPELLERS!")
    print("=" * 60)
    
    # Create the custom driver
    driver = WaveshareDriver(bitrate=500000)
    
    # Create a full DroneCAN node
    node = dronecan.node.Node(driver, node_id=10)
    node.mode = dronecan.uavcan.protocol.NodeStatus().MODE_OPERATIONAL
    
    # Broadcast ArmingStatus (Required by many ESCs to enable output)
    def send_arming_status():
        node.broadcast(dronecan.uavcan.equipment.safety.ArmingStatus(status=255))
    node.periodic(0.1, send_arming_status)
    
    # Register standard telemetry handlers
    node.add_handler(dronecan.uavcan.equipment.esc.Status, on_esc_status)
    node.add_handler(dronecan.com.hobbywing.esc.StatusMsg1, on_hw_status1)
    node.add_handler(dronecan.com.hobbywing.esc.StatusMsg2, on_hw_status2)
    
    print("   ✅ DroneCAN node created (ID=10, Mode=OPERATIONAL, ArmingStatus=FULLY_ARMED)")
    
    # ── Wait for telemetry ──
    print("\n📊 Waiting for ESC telemetry...")
    start = time.time()
    while time.time() - start < 2.0 and not _stop:
        node.spin(timeout=0.1)
    t = get_telem()
    print(f"   V={t['voltage']:.1f}V I={t['current']:.2f}A RPM={t['rpm']}")
    
    # ── Listen for DroneCAN nodes ──
    print("\n🔍 Listening for DroneCAN nodes on the bus...")
    nodes_found = {}
    
    def node_status_handler(event):
        nid = event.transfer.source_node_id
        if nid not in nodes_found:
            nodes_found[nid] = event
            print(f"   🟢 Node {nid}: uptime={event.message.uptime_sec}s")
    
    node.add_handler(dronecan.uavcan.protocol.NodeStatus, node_status_handler)
    
    start = time.time()
    while time.time() - start < 3.0 and not _stop:
        node.spin(timeout=0.1)
    
    if not nodes_found:
        print("   ⚠️  No DroneCAN NodeStatus detected from ESC")
        print("   (Proceeding anyway — ESC may only respond to service requests)")
    
    # ── Try GetMajorConfig to confirm ESC is reachable ──
    print("\n📡 Querying ESC configuration (GetMajorConfig)...")
    config_received = [False]
    config_data = [None]
    
    def config_response(event):
        config_received[0] = True
        config_data[0] = event.response
        print(f"   ✅ Config received!")
        print(f"      direction: {event.response.direction}")
        print(f"      throttle_source: {event.response.throttle_source}")
        print(f"      throttle_channel: {event.response.throttle_channel}")
        print(f"      led_status: {event.response.led_status}")
        print(f"      MSG1_rate: {event.response.MSG1_rate}")
        print(f"      MSG2_rate: {event.response.MSG2_rate}")
    
    node.request(
        dronecan.com.hobbywing.esc.GetMajorConfig.Request(option=0),
        1,  # ESC node ID
        config_response
    )
    
    start = time.time()
    while time.time() - start < 3.0 and not config_received[0] and not _stop:
        node.spin(timeout=0.1)
    
    if not config_received[0]:
        print("   ❌ No response from ESC — cannot proceed")
        driver.close()
        return
    
    # ── Set throttle source to CAN_DIGITAL ──
    print("\n⚙️  Setting throttle source to CAN_DIGITAL...")
    ts_response = [None]
    
    def ts_callback(event):
        ts_response[0] = event.response
        print(f"   ✅ ThrottleSource set! Response source={event.response.source}")
    
    node.request(
        dronecan.com.hobbywing.esc.SetThrottleSource.Request(source=0),  # CAN_DIGITAL
        1,
        ts_callback
    )
    
    start = time.time()
    while time.time() - start < 2.0 and ts_response[0] is None and not _stop:
        node.spin(timeout=0.1)
    
    if _stop:
        driver.close()
        return

    # ── Set Throttle Channel (SetID) ──
    print("\n⚙️  Setting throttle channel to 1 (Currently Unassigned)...")
    id_response = [None]
    
    def id_callback(event):
        id_response[0] = event.response
        print(f"   ✅ SetID set! node_id={event.response.node_id}, throttle_channel={event.response.throttle_channel}")
    
    node.request(
        dronecan.com.hobbywing.esc.SetID.Request(node_id=1, throttle_channel=1),
        1,
        id_callback
    )
    
    start = time.time()
    while time.time() - start < 2.0 and id_response[0] is None and not _stop:
        node.spin(timeout=0.1)
    
    # ══════════════════════════════════════════
    #  MOTOR CONTROL TESTS
    # ══════════════════════════════════════════
    
    # Periodically print standard ESC status to check for errors
    def print_status(event):
        print(f"\r   [ESC Status] Node {event.transfer.source_node_id} | V={event.message.voltage:.1f}V | I={event.message.current:.2f}A | RPM={event.message.rpm} | Error={event.message.error_count}      ", end="", flush=True)
    
    node.add_handler(dronecan.uavcan.equipment.esc.Status, print_status)

    tests = [
        # (description, command_func, throttle_values_sequence)
        ("TEST 1: HW RawCommand (Hobbywing DTID 20100) - ALL Channels",
         lambda val: dronecan.com.hobbywing.esc.RawCommand(command=[val, val, val, val]),
         [0, 0, 500, 1000, 2000, 4000, 6000, 8000, 0]),
        ("TEST 2: STD RawCommand (Standard DTID 1030) - ALL Channels",
         lambda val: dronecan.uavcan.equipment.esc.RawCommand(cmd=[val, val, val, val]),
         [0, 0, 500, 1000, 2000, 4000, 6000, 8000, 0]),
    ]
    
    print("\n\n" + "═" * 60)
    print("  ✋ PRE-ARM PHASE (Broadcasting GetEscID for 3s)")
    print("═" * 60)
    
    start_manual = time.time()
    last_getid = 0
    while time.time() - start_manual < 3.0 and not _stop:
        if time.time() - last_getid > 1.0:
            last_getid = time.time()
            msg = dronecan.com.hobbywing.esc.GetEscID()
            msg.payload.append(0)
            node.broadcast(msg)
            print("   -> Broadcasted com.hobbywing.esc.GetEscID")
            
        # Keep throttle at 0
        node.broadcast(dronecan.com.hobbywing.esc.RawCommand(command=[0, 0, 0, 0]), priority=0)
        node.spin(timeout=0.05)
    
    motor_spun = False
    
    for test_name, make_msg, throttle_seq in tests:
        if _stop or motor_spun:
            break
        
        print(f"\n{'═' * 60}")
        print(f"  {test_name}")
        print(f"{'═' * 60}")
        
        baseline_current = None
        
        for throttle in throttle_seq:
            if _stop:
                break
            
            print(f"\n  Throttle = {throttle} (sending for 2s @ 100Hz)...")
            
            start = time.time()
            count = 0
            while time.time() - start < 2.0 and not _stop:
                msg = make_msg(throttle)
                node.broadcast(msg, priority=0)
                count += 1
                
                node.spin(timeout=0.01)
                
                if count % 20 == 0:
                    t = get_telem()
                    if baseline_current is None:
                        baseline_current = t['current']
                    
                    delta_i = abs(t['current'] - (baseline_current or 0))
                    active = delta_i > 0.3
                    
                    print(f"\r     V={t['voltage']:5.1f}V I={t['current']:6.2f}A "
                          f"RPM={t['rpm']:5d} T={t['temp']}°C "
                          f"[ΔI={delta_i:.2f}A {'🟢ACTIVE!' if active else '⚪idle'}]",
                          end="", flush=True)
                    
                    if active and throttle > 0:
                        motor_spun = True
                        print(f"\n\n  🎉🎉🎉 MOTOR IS SPINNING! 🎉🎉🎉")
                        print(f"  Command: {test_name}")
                        print(f"  Throttle value: {throttle}")
                        # Run for a bit more then stop
                        time.sleep(2.0)
                        break
            
            print()
            
            if motor_spun:
                # Stop
                print("  Stopping motor...")
                for _ in range(100):
                    msg = make_msg(0)
                    node.broadcast(msg, priority=0)
                    node.spin(timeout=0.01)
                break
        
        # Send stop commands
        for _ in range(50):
            try:
                msg = make_msg(0)
                node.broadcast(msg, priority=0)
                node.spin(timeout=0.005)
            except:
                pass
    
    # ── Final cleanup ──
    print("\n" + "=" * 60)
    if motor_spun:
        print("  ✅ SUCCESS! Motor control achieved via DroneCAN!")
    else:
        print("  ❌ Motor did not spin with any command type tested")
        print("  Possible causes:")
        print("  - ESC arming sequence not satisfied")
        print("  - ESC expects PWM signal first to arm")
        print("  - Throttle range or channel mapping incorrect")
    print("=" * 60)
    
    # Emergency stop
    for _ in range(100):
        try:
            node.broadcast(dronecan.com.hobbywing.esc.RawCommand(command=[0]), priority=0)
            node.broadcast(dronecan.uavcan.equipment.esc.RawCommand(cmd=[0]), priority=0)
            node.spin(timeout=0.005)
        except:
            pass
    
    driver.close()
    print("\n🔌 Done.")


if __name__ == "__main__":
    main()
