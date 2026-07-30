#!/usr/bin/env python3
"""
Hobbywing X6 Plus - Comprehensive Throttle Command Scanner
==========================================================
This script exhaustively tries ALL known Hobbywing HWCAN throttle
command formats to find what makes the motor spin.

Based on analysis of the ESC telemetry traffic pattern:
  Telemetry IDs: 0x1F4E52XX, 0x1F4E53XX, 0x1F4E54XX
  Where XX = ESC Node ID (01 for default)

The throttle command ID likely follows one of these patterns:
  Pattern A: 0x1F4E50XX or 0x1F4E51XX (same prefix, different type)
  Pattern B: 0x0000XXYY (low ID range)
  Pattern C: DroneCAN standard with DSDL CRC in the CAN ID

Also tries different data payload formats for the throttle value.
"""

import sys
import time
import signal
import struct

from waveshare_can import (
    WaveshareCAN, detect_adapter, CANFrame,
    CAN_BAUD_500K, CAN_BAUD_1M,
    CAN_MODE_NORMAL,
)

_stop = False
def sigint(s, f):
    global _stop
    _stop = True
    print("\n🛑 STOPPED")
signal.signal(signal.SIGINT, sigint)


def read_rpm(can, duration=0.5):
    """Read RPM-related data from telemetry frames."""
    result = {'rpm_raw': 0, 'voltage_raw': 0, 'current_raw': 0, 'has_data': False}
    start = time.time()
    while time.time() - start < duration:
        frames = can.receive(timeout=0.2)
        for f in frames:
            if f.is_extended:
                msg_type = (f.can_id >> 8) & 0xFF
                if msg_type == 0x53 and len(f.data) >= 4:  # V/I frame
                    result['voltage_raw'] = struct.unpack_from('<H', f.data, 0)[0]
                    result['current_raw'] = struct.unpack_from('<h', f.data, 2)[0]
                    result['has_data'] = True
                elif msg_type == 0x54 and len(f.data) >= 6:  # RPM frame
                    result['rpm_raw'] = struct.unpack_from('<H', f.data, 0)[0]
                    result['has_data'] = True
    return result


def try_command(can, can_id, data, name, baseline):
    """Send a throttle command and check for changes."""
    global _stop
    
    # Send command for ~1 second at 50Hz
    for i in range(50):
        if _stop: return False
        frame = CANFrame(can_id=can_id, data=data, is_extended=True)
        can.send_frame(frame)
        time.sleep(0.02)
    
    # Read telemetry
    current = read_rpm(can, 0.3)
    
    changed = False
    if current['has_data'] and baseline['has_data']:
        # Check if current changed (motor drawing power)
        if abs(current['current_raw'] - baseline['current_raw']) > 5:
            changed = True
        # Check if RPM changed  
        if abs(current['rpm_raw'] - baseline['rpm_raw']) > 50:
            changed = True
    
    return changed


def main():
    global _stop
    
    print("=" * 60)
    print("  Hobbywing X6 Plus - Exhaustive Throttle Command Scanner")
    print("  ⚠️  SAFETY: Remove propellers! Press Ctrl+C to stop")
    print("=" * 60)
    
    port = detect_adapter()
    if not port:
        sys.exit(1)
    
    can = WaveshareCAN()
    if not can.open(port):
        sys.exit(1)
    
    can.configure(can_baud=CAN_BAUD_500K, frame_type=0x02, mode=CAN_MODE_NORMAL, use_variable_protocol=True)
    time.sleep(0.5)
    
    # Read baseline
    print("\n📊 Reading baseline telemetry...")
    baseline = read_rpm(can, 1.0)
    print(f"   Baseline: rpm_raw={baseline['rpm_raw']}, V_raw={baseline['voltage_raw']}, "
          f"I_raw={baseline['current_raw']}, has_data={baseline['has_data']}")
    
    if not baseline['has_data']:
        print("❌ No telemetry received! Check connections.")
        can.close()
        sys.exit(1)
    
    esc_id = 1  # Default Hobbywing ESC ID
    
    # ──────────────────────────────────────────────
    # Define ALL possible throttle command formats
    # ──────────────────────────────────────────────
    
    throttle_value = 200  # Small test throttle
    
    # Different data payload formats to try
    data_formats = {
        'uint16_le': struct.pack('<H', throttle_value) + bytes(6),
        'uint16_be': struct.pack('>H', throttle_value) + bytes(6),
        'uint16_le_offset2': bytes(2) + struct.pack('<H', throttle_value) + bytes(4),
        'byte1_percent': bytes([int(throttle_value/2000*100)]) + bytes(7),
        'byte1_value': bytes([throttle_value & 0xFF]) + bytes(7),
        'uint16_1000_base': struct.pack('<H', 1000 + throttle_value) + bytes(6),
        'pwm_style': struct.pack('<H', 1100) + bytes(6),  # 1100us PWM equivalent
        'hwcan_thr_format1': struct.pack('<HH', throttle_value, 0) + bytes(4),
        'dronecan_14bit': bytes([throttle_value & 0xFF, (throttle_value >> 8) & 0x3F]) + bytes(5) + bytes([0xC0]),
    }
    
    # CAN IDs to try (comprehensive list)
    can_ids = [
        # Based on telemetry prefix pattern 0x1F4E5X01
        (0x1F4E5001, "HW Prefix-same: 0x1F4E5001"),
        (0x1F4E5101, "HW Prefix-51: 0x1F4E5101"),
        (0x1F4E4F01, "HW Prefix-4F: 0x1F4E4F01"),
        
        # Based on pattern analysis - telemetry is 0x1F__5X01, command might be 0x1F__0X01
        (0x1F4E0001, "HW Alt-00: 0x1F4E0001"),
        (0x1F4E0101, "HW Alt-01: 0x1F4E0101"),
        
        # Common Hobbywing throttle command patterns from datasheets
        (0x1F050001, "HW Classic: 0x1F050001"),
        (0x1F050101, "HW Classic2: 0x1F050101"),
        (0x1F060001, "HW Format3: 0x1F060001"),
        
        # Simple low IDs
        (0x00000001, "Simple ID 1"),
        (0x00000100, "Simple ID 256"),
        (0x00000201, "Simple ID 0x201"),
        (0x00000401, "Simple ID 0x401"),
        
        # DroneCAN standard ESC RawCommand 
        # Message Type 1030 = 0x0406
        # CAN ID = (priority << 24) | (msg_type << 8) | (service << 7) | node_id
        (0x0004060A, "DroneCAN pri=0 node=10"),
        (0x0404060A, "DroneCAN pri=1 node=10"),
        (0x0804060A, "DroneCAN pri=2 node=10"),
        (0x1004060A, "DroneCAN pri=4 node=10"),
        
        # DroneCAN with DSDL CRC in ID (proper format)
        # The actual CAN ID includes a discriminator based on DSDL signature
        (0x0004060A, "DroneCAN RawCmd(1030) p0 n10"),
        
        # Standard Hobbywing node addressing
        (0x01000001, "HW Node1 Type1"),
        (0x02000001, "HW Node1 Type2"),
        
        # Try reversing the endianness of observed IDs
        (0x01534E1F, "Reversed telemetry ID"),
        
        # Some other patterns from CAN ESC protocols
        (0x00000141, "CAN 0x141"),
        (0x00000241, "CAN 0x241"),
        (0x00000601, "CAN 0x601"),
        
        # Broadcast IDs
        (0x00000000, "Broadcast 0"),
        (0x1FFFFFFF, "Max Extended ID"),
    ]
    
    print(f"\n🔍 Testing {len(can_ids)} CAN IDs × {len(data_formats)} data formats...")
    print(f"   Throttle value: {throttle_value}")
    print(f"   Test duration per combo: ~1s")
    print()
    
    found = False
    tested = 0
    total = len(can_ids) * len(data_formats)
    
    for cmd_id, id_name in can_ids:
        if _stop or found:
            break
        
        for fmt_name, data in data_formats.items():
            if _stop or found:
                break
            
            tested += 1
            
            # Send zero first (brief)
            for _ in range(10):
                zero_frame = CANFrame(can_id=cmd_id, data=bytes(8), is_extended=True)
                can.send_frame(zero_frame)
                time.sleep(0.01)
            
            # Send test throttle
            print(f"\r  [{tested}/{total}] ID=0x{cmd_id:08X} fmt={fmt_name}      ", end="", flush=True)
            
            changed = try_command(can, cmd_id, data, f"{id_name}/{fmt_name}", baseline)
            
            if changed:
                found = True
                print(f"\n\n  🎯 FOUND! Motor responded to:")
                print(f"     CAN ID: 0x{cmd_id:08X} ({id_name})")
                print(f"     Data Format: {fmt_name}")
                print(f"     Data: {data.hex().upper()}")
                
                # Stop motor
                for _ in range(100):
                    can.send_frame(CANFrame(can_id=cmd_id, data=bytes(8), is_extended=True))
                    time.sleep(0.01)
                
                break
            
            # Send zero to ensure motor stays stopped
            for _ in range(5):
                can.send_frame(CANFrame(can_id=cmd_id, data=bytes(8), is_extended=True))
                time.sleep(0.01)
    
    print()
    
    if not found and not _stop:
        print(f"\n❌ No working throttle command found after {tested} combinations.")
        print(f"\n📝 Analysis of your ESC:")
        print(f"   • ESC is running HWCAN proprietary protocol")
        print(f"   • ESC ID: 1, Voltage: {baseline['voltage_raw'] * 0.1:.1f}V")
        print(f"   • Telemetry CAN IDs: 0x1F4E5201, 0x1F4E5301, 0x1F4E5401")
        print(f"\n💡 Recommended next steps:")
        print(f"   1. Get a Hobbywing DataLink V2 box to:")
        print(f"      - Switch protocol from HWCAN to DroneCAN") 
        print(f"      - Set the throttle source to CAN")
        print(f"      - Configure the CAN baud rate to 1 Mbps")
        print(f"   2. After switching to DroneCAN, use the 'dronecan' Python library")
        print(f"   3. Alternative: Use PWM control (connect ESC PWM wire to a PWM source)")
    
    # Cleanup
    can.close()
    print("\n✅ Done!")


if __name__ == "__main__":
    main()
