#!/usr/bin/env python3
"""
Hobbywing DroneCAN Protocol Tester
==================================
Uses the official dronecan library to serialize messages and compute CRCs/frames,
then sends them via the Waveshare CAN adapter.

Tests:
1. Standard DroneCAN RawCommand (uavcan.equipment.esc.RawCommand, ID 1030)
2. Custom Hobbywing RawCommand (com.hobbywing.esc.RawCommand, ID 20100)

Safety: REMOVE PROPELLERS!
"""

import sys
import time
import signal
import struct
import threading

import dronecan
from dronecan.transport import Transfer

from waveshare_can import (
    WaveshareCAN, detect_adapter, CANFrame,
    CAN_BAUD_500K, CAN_MODE_NORMAL
)

# DroneCAN / Hobbywing Telemetry IDs
HWCAN_TELEM_STATUS = 0x1F4E5201  # com.hobbywing.esc.StatusMsg1
HWCAN_TELEM_VI     = 0x1F4E5301  # com.hobbywing.esc.StatusMsg2
HWCAN_TELEM_RPM    = 0x1F4E5401  # com.hobbywing.esc.StatusMsg3

_stop = False
_heartbeat_thread = None

def sigint(s, f):
    global _stop
    _stop = True
    print("\n🛑 STOPPING IMMEDIATELY...")

signal.signal(signal.SIGINT, sigint)


def send_dronecan_message(can: WaveshareCAN, msg, transfer_id: int, source_node_id: int = 10, priority: int = 0) -> bool:
    """Serializes a DroneCAN message and sends its frames via Waveshare CAN."""
    tr = Transfer(
        transfer_id=transfer_id,
        source_node_id=source_node_id,
        payload=msg,
        transfer_priority=priority,
        service_not_message=False
    )
    success = True
    for f in tr.to_frames():
        if not can.send(f.message_id, bytes(f.bytes), extended=True):
            success = False
    return success


def run_heartbeat(can: WaveshareCAN, source_node_id: int):
    """Sends NodeStatus heartbeat at 1Hz in a background thread."""
    global _stop
    transfer_id = 0
    start_time = time.time()
    
    while not _stop:
        uptime = int(time.time() - start_time) & 0xFFFFFFFF
        # Create standard NodeStatus message
        msg = dronecan.uavcan.protocol.NodeStatus(
            uptime_sec=uptime,
            health=dronecan.uavcan.protocol.NodeStatus().HEALTH_OK,
            mode=dronecan.uavcan.protocol.NodeStatus().MODE_OPERATIONAL,
            sub_mode=0,
            vendor_specific_status_code=0
        )
        send_dronecan_message(can, msg, transfer_id, source_node_id, priority=6)
        transfer_id = (transfer_id + 1) % 32
        
        # Sleep for 1.0s in small chunks so we can exit quickly
        for _ in range(10):
            if _stop:
                break
            time.sleep(0.1)


def read_telemetry_snapshot(can: WaveshareCAN, duration: float = 0.2) -> dict:
    """Reads and decodes telemetry frames."""
    telem = {'voltage': 0.0, 'current': 0.0, 'rpm_raw': 0, 'temp': 0, 'has_data': False}
    start = time.time()
    while time.time() - start < duration:
        frames = can.receive(timeout=0.05)
        for f in frames:
            if not f.is_extended:
                continue
            if f.can_id == HWCAN_TELEM_VI and len(f.data) >= 4:
                v_raw = struct.unpack_from('<H', f.data, 0)[0]
                i_raw = struct.unpack_from('<h', f.data, 2)[0]
                telem['voltage'] = v_raw * 0.1
                telem['current'] = i_raw * 0.01
                telem['has_data'] = True
            elif f.can_id == HWCAN_TELEM_RPM and len(f.data) >= 6:
                telem['rpm_raw'] = struct.unpack_from('<H', f.data, 0)[0]
                telem['temp'] = f.data[4]
                telem['has_data'] = True
    return telem


def test_command_type(can: WaveshareCAN, cmd_type: str, test_value: int) -> bool:
    """Tests a specific throttle command type (standard or custom)."""
    global _stop
    print(f"\n🚀 Testing Command Type: {cmd_type} (value = {test_value})")
    
    # Capture baseline
    base = read_telemetry_snapshot(can, 0.5)
    if not base['has_data']:
        print("   ⚠️ No ESC telemetry received! Check wiring/power.")
        return False
    print(f"   Baseline: V={base['voltage']:.1f}V | I={base['current']:.2f}A | RPM={base['rpm_raw']} | Temp={base['temp']}C")
    
    transfer_id = 0
    
    # 1. Arming: Send 0 throttle at 50Hz for 2.0 seconds
    print("   Arming ESC (sending 0 throttle)...")
    for _ in range(100):
        if _stop: return False
        
        if cmd_type == "standard":
            msg = dronecan.uavcan.equipment.esc.RawCommand(cmd=[0])
        else:
            msg = dronecan.com.hobbywing.esc.RawCommand(command=[0])
            
        send_dronecan_message(can, msg, transfer_id, source_node_id=10, priority=0)
        transfer_id = (transfer_id + 1) % 32
        time.sleep(0.02)
        
    # 2. Run: Send test throttle at 50Hz for 4.0 seconds
    print(f"   Sending test throttle ({test_value})...")
    start_run = time.time()
    last_print = 0
    max_current = 0.0
    seen_rpm_changes = []
    
    while time.time() - start_run < 4.0:
        if _stop: break
        
        if cmd_type == "standard":
            msg = dronecan.uavcan.equipment.esc.RawCommand(cmd=[test_value])
        else:
            msg = dronecan.com.hobbywing.esc.RawCommand(command=[test_value])
            
        send_dronecan_message(can, msg, transfer_id, source_node_id=10, priority=0)
        transfer_id = (transfer_id + 1) % 32
        time.sleep(0.02)
        
        now = time.time()
        if now - last_print > 0.4:
            last_print = now
            t = read_telemetry_snapshot(can, 0.05)
            print(f"\r     Telemetry: V={t['voltage']:5.1f}V | I={t['current']:6.2f}A | RPM={t['rpm_raw']:5d}", end="", flush=True)
            
            if t['has_data']:
                if t['current'] > max_current:
                    max_current = t['current']
                rpm_diff = abs(t['rpm_raw'] - base['rpm_raw'])
                if rpm_diff > 15:
                    seen_rpm_changes.append(rpm_diff)
                    
    print()
    
    # 3. Stop: Send 0 throttle to stop motor
    print("   Stopping motor...")
    for _ in range(50):
        if cmd_type == "standard":
            msg = dronecan.uavcan.equipment.esc.RawCommand(cmd=[0])
        else:
            msg = dronecan.com.hobbywing.esc.RawCommand(command=[0])
        send_dronecan_message(can, msg, transfer_id, source_node_id=10, priority=0)
        transfer_id = (transfer_id + 1) % 32
        time.sleep(0.01)
        
    motor_responded = (max_current - base['current'] > 0.1) or (len(seen_rpm_changes) > 0)
    if motor_responded:
        print(f"   🎉 SUCCESS! Motor responded to {cmd_type} command!")
        if max_current > 0.1:
            print(f"      Max current: {max_current:.2f}A")
        if seen_rpm_changes:
            print(f"      RPM changed by: {max(seen_rpm_changes)}")
        return True
    else:
        print(f"   ❌ No response detected for {cmd_type} command.")
        return False


def main():
    global _stop, _heartbeat_thread
    
    print("=" * 60)
    print("  Hobbywing DroneCAN Command Tester")
    print("  ⚠️ SAFETY: Ensure propellers are REMOVED!")
    print("=" * 60)
    
    port = detect_adapter()
    if not port:
        sys.exit(1)
        
    can = WaveshareCAN()
    if not can.open(port):
        sys.exit(1)
        
    try:
        # Configure CAN adapter to 500kbps, normal mode, variable protocol
        can.configure(
            can_baud=CAN_BAUD_500K,
            frame_type=0x02,
            mode=CAN_MODE_NORMAL,
            use_variable_protocol=True
        )
        time.sleep(0.5)
        
        # Start NodeStatus heartbeat thread (node ID = 10)
        _heartbeat_thread = threading.Thread(target=run_heartbeat, args=(can, 10), daemon=True)
        _heartbeat_thread.start()
        print("📡 Background NodeStatus heartbeat started (Node ID 10)")
        
        # Test standard DroneCAN RawCommand first
        # Range is 0 to 8191. Let's try 1500 (approx 18% throttle)
        success_std = test_command_type(can, "standard", 1500)
        
        if success_std:
            print("\n🏆 VERIFIED PROTOCOL: Standard DroneCAN RawCommand (ID 1030)")
            return
            
        time.sleep(1.5)
        
        # Test custom Hobbywing RawCommand
        # Range is also typically 0 to 8191 (or similar). Let's try 1500.
        success_hw = test_command_type(can, "custom_hw", 1500)
        
        if success_hw:
            print("\n🏆 VERIFIED PROTOCOL: Custom Hobbywing RawCommand (ID 20100)")
            return
            
        print("\n❌ Neither DroneCAN command format resulted in motor response.")
        print("   Possible issues:")
        print("   - Throttle source in ESC is not set to CAN.")
        print("   - ESC is not armed (check if beep sequences occurred).")
        print("   - Node ID or test throttle value needs adjustment.")
        
    finally:
        _stop = True
        if _heartbeat_thread:
            _heartbeat_thread.join(timeout=1.0)
        can.close()
        print("\nCleanup complete.")

if __name__ == "__main__":
    main()
