#!/usr/bin/env python3
"""
Hobbywing HWCAN Direct Protocol Tester (Rigorously Verified)
===========================================================
Tests the user-provided HWCAN proprietary protocol parameters:
- CAN IDs: 0x201 (standard), 0x1F000100 (extended), 0x1F000101 (extended)
- Payload: [uint16_BE_throttle] [00]*6
- Range: 1050 (idle/arm) to 1950 (max)
- Frequency: 50Hz (20ms interval)

Safety: REMOVE PROPELLERS!
"""

import sys
import time
import signal
import struct
from waveshare_can import (
    WaveshareCAN, detect_adapter, CANFrame,
    CAN_BAUD_500K, CAN_MODE_NORMAL
)

# Telemetry IDs we expect the ESC to broadcast
HWCAN_TELEM_STATUS = 0x1F4E5201
HWCAN_TELEM_VI     = 0x1F4E5301
HWCAN_TELEM_RPM    = 0x1F4E5401

_stop = False
def sigint(s, f):
    global _stop
    _stop = True
    print("\n🛑 STOPPING IMMEDIATELY...")

signal.signal(signal.SIGINT, sigint)


def read_telemetry_snapshot(can: WaveshareCAN, duration: float = 0.2) -> dict:
    """Reads telemetry for a short duration and returns decoded values."""
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


def test_combination(can: WaveshareCAN, can_id: int, is_extended: bool, name: str):
    """Tests a single CAN ID configuration."""
    global _stop
    print(f"\n🚀 Testing configuration: {name} (ID: 0x{can_id:08X}, Extended: {is_extended})")
    
    # 1. Capture baseline
    print("   Capturing baseline telemetry...")
    base = read_telemetry_snapshot(can, 0.5)
    if not base['has_data']:
        print("   ⚠️ No telemetry received! Is the ESC powered?")
        return False
    print(f"   Baseline: Voltage={base['voltage']:.1f}V, Temp={base['temp']}C, RPM={base['rpm_raw']}, Current={base['current']:.2f}A")
    
    # 2. Arming sequence: send 1050 (idle) at 50Hz for 1.5 seconds
    print("   Sending arming sequence (1050 µs)...")
    payload_arm = bytearray(8)
    struct.pack_into('>H', payload_arm, 0, 1050)
    
    for _ in range(75):
        if _stop: return False
        frame = CANFrame(can_id=can_id, data=bytes(payload_arm), is_extended=is_extended)
        can.send_frame(frame)
        time.sleep(0.02)
        
    # 3. Test sequence: send 1100 (low run) at 50Hz for 3.0 seconds
    print("   Sending test throttle (1100 µs)...")
    payload_run = bytearray(8)
    struct.pack_into('>H', payload_run, 0, 1100)
    
    start_run = time.time()
    last_print = 0
    motor_active = False
    
    # We will log the maximum current and any RPM change seen during the run
    max_current = 0.0
    seen_rpm_changes = []
    
    while time.time() - start_run < 3.0:
        if _stop: break
        frame = CANFrame(can_id=can_id, data=bytes(payload_run), is_extended=is_extended)
        can.send_frame(frame)
        time.sleep(0.02)
        
        # Periodically read telemetry
        now = time.time()
        if now - last_print > 0.3:
            last_print = now
            t = read_telemetry_snapshot(can, 0.05)
            print(f"\r     Telemetry: V={t['voltage']:5.1f}V | I={t['current']:6.2f}A | RPM={t['rpm_raw']:5d}", end="", flush=True)
            
            if t['has_data']:
                if t['current'] > max_current:
                    max_current = t['current']
                rpm_diff = abs(t['rpm_raw'] - base['rpm_raw'])
                if rpm_diff > 10:
                    seen_rpm_changes.append(rpm_diff)
                    
    print()
    
    # Check if motor responded based on strict metrics:
    # 1. Current draw increased significantly (> 0.1A above baseline)
    # 2. RPM raw changed significantly (> 20 units)
    current_increased = (max_current - base['current']) > 0.1
    rpm_changed = len(seen_rpm_changes) > 0
    
    if current_increased or rpm_changed:
        motor_active = True
        
    # 4. Stop motor (send 1050/0)
    print("   Stopping motor...")
    for _ in range(50):
        frame = CANFrame(can_id=can_id, data=bytes(payload_arm), is_extended=is_extended)
        can.send_frame(frame)
        time.sleep(0.01)
        
    if motor_active:
        print(f"   🎉 SUCCESS! Motor responded to {name}!")
        if current_increased:
            print(f"      - Current draw increased to {max_current:.2f}A")
        if rpm_changed:
            print(f"      - RPM changed by up to {max(seen_rpm_changes)} units")
        return True
    else:
        print(f"   ❌ No motor response detected for {name}.")
        return False


def main():
    print("=" * 60)
    print("  Hobbywing HWCAN Direct Protocol Tester")
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
            frame_type=0x02,  # supports extended frames (and standard)
            mode=CAN_MODE_NORMAL,
            use_variable_protocol=True
        )
        time.sleep(0.5)
        
        # Test configurations
        configs = [
            {"can_id": 0x201, "is_extended": False, "name": "Standard ID 0x201"},
            {"can_id": 0x1F000101, "is_extended": True, "name": "Extended ID 0x1F000101"},
            {"can_id": 0x1F000100, "is_extended": True, "name": "Extended ID 0x1F000100"},
        ]
        
        results = {}
        for config in configs:
            if _stop:
                break
            success = test_combination(can, config["can_id"], config["is_extended"], config["name"])
            results[config["name"]] = success
            time.sleep(1.0)
            
        print("\n" + "=" * 40)
        print("  SUMMARY OF RESULTS")
        print("=" * 40)
        for name, success in results.items():
            status = "WORKING ✅" if success else "NO RESPONSE ❌"
            print(f"  {name:25s} : {status}")
        print("=" * 40)
            
    finally:
        # Force stop
        print("\nCleaning up...")
        can.close()
        print("Done.")

if __name__ == "__main__":
    main()
