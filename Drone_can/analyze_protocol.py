#!/usr/bin/env python3
"""
Deep analysis of Hobbywing HWCAN protocol telemetry.
Dumps all fields and byte values to understand the data format.
"""

import sys
import time
import struct
from waveshare_can import WaveshareCAN, detect_adapter, CANFrame, CAN_BAUD_500K, CAN_MODE_NORMAL

def main():
    port = detect_adapter()
    if not port: sys.exit(1)
    
    can = WaveshareCAN()
    if not can.open(port): sys.exit(1)
    can.configure(can_baud=CAN_BAUD_500K, frame_type=0x02, mode=CAN_MODE_NORMAL, use_variable_protocol=True)
    time.sleep(0.5)
    
    print("Capturing 3 seconds of telemetry...\n")
    
    frame_data = {0x52: [], 0x53: [], 0x54: []}
    
    start = time.time()
    while time.time() - start < 3.0:
        frames = can.receive(timeout=0.3)
        for f in frames:
            if f.is_extended:
                msg_type = (f.can_id >> 8) & 0xFF
                if msg_type in frame_data and len(frame_data[msg_type]) < 5:
                    frame_data[msg_type].append(f.data)
    
    for msg_type, samples in frame_data.items():
        print(f"=== Message Type 0x{msg_type:02X} (CAN ID 0x1F4E{msg_type:02X}01) ===")
        for i, data in enumerate(samples):
            print(f"  Sample {i}: {data.hex(' ').upper()}")
            
            # Decode each pair of bytes as various formats
            print(f"    Byte-by-byte: {' '.join(f'{b:3d}' for b in data)}")
            
            for offset in range(0, len(data) - 1, 2):
                val_le = struct.unpack_from('<H', data, offset)[0]
                val_be = struct.unpack_from('>H', data, offset)[0]
                val_le_s = struct.unpack_from('<h', data, offset)[0]
                print(f"    bytes[{offset}:{offset+2}]: uint16_LE={val_le:5d}(0x{val_le:04X}) "
                      f"uint16_BE={val_be:5d}(0x{val_be:04X}) "
                      f"int16_LE={val_le_s:6d}")
            
            # Last byte often changes (transfer counter)
            print(f"    Last byte: {data[-1]:3d} (0x{data[-1]:02X})")
        print()
    
    # Now analyze the 0x53 frame more carefully
    print("=== Voltage analysis (0x53) ===")
    if frame_data[0x53]:
        d = frame_data[0x53][0]
        print(f"  Bytes 0-1 as uint16_LE * 0.1 = {struct.unpack_from('<H', d, 0)[0] * 0.1:.1f}V")
        print(f"  Bytes 2-3 as int16_LE * 0.01 = {struct.unpack_from('<h', d, 2)[0] * 0.01:.2f}A")
        print(f"  Byte 4: {d[4]:d} (0x{d[4]:02X})")
        print(f"  Byte 5 (last): {d[5]:d} (0x{d[5]:02X}) - likely transfer counter")
    
    print("\n=== RPM/Temp analysis (0x54) ===")
    if frame_data[0x54]:
        d = frame_data[0x54][0]
        print(f"  Bytes 0-1: {struct.unpack_from('<H', d, 0)[0]}")
        print(f"  Bytes 2-3: {struct.unpack_from('<H', d, 2)[0]}")
        print(f"  Bytes 4-5: {struct.unpack_from('<H', d, 4)[0]}")
        print(f"  Byte 6: {d[6]:d}")
        print(f"  Byte 7 (last): {d[7]:d} (0x{d[7]:02X}) - likely transfer counter")
        print()
        # RPM = 0 when not spinning. So bytes 0-1 might be something else
        # Let's check if it's eRPM
        val = struct.unpack_from('<H', d, 0)[0]
        print(f"  If eRPM: {val} * 5/7 = {val*5/7:.0f}")
        print(f"  If ADC/counter: raw = {val}")
    
    print("\n=== Status analysis (0x52) ===")
    if frame_data[0x52]:
        d = frame_data[0x52][0]
        for i in range(len(d)):
            print(f"  Byte {i}: {d[i]:3d} (0x{d[i]:02X})")
    
    # Now send a throttle command and see if telemetry changes
    print("\n\n=== THROTTLE TEST ===")
    print("Sending throttle commands with various values and monitoring changes...")
    
    # Test different CAN IDs and higher throttle values
    test_configs = [
        (0x1F4E5001, bytes([0x00, 0x00]) + struct.pack('<H', 500) + bytes(4), "offset2 val=500"),
        (0x1F4E5001, bytes([0x00, 0x00]) + struct.pack('<H', 1000) + bytes(4), "offset2 val=1000"),
        (0x1F4E5001, bytes([0x00, 0x00]) + struct.pack('<H', 2000) + bytes(4), "offset2 val=2000"),
        (0x1F4E5001, bytes([0x00, 0x00]) + struct.pack('<H', 4000) + bytes(4), "offset2 val=4000"),
        (0x1F4E5001, struct.pack('<H', 500) + bytes(6), "offset0 val=500"),
        (0x1F4E5001, struct.pack('<H', 1000) + bytes(6), "offset0 val=1000"),
        (0x1F4E5001, struct.pack('<H', 2000) + bytes(6), "offset0 val=2000"),
        (0x1F4E5001, struct.pack('<H', 4000) + bytes(6), "offset0 val=4000"),
        # Try byte3 as the throttle
        (0x1F4E5001, bytes(3) + bytes([0x64]) + bytes(4), "byte3=100"),
        (0x1F4E5001, bytes(3) + bytes([0xFF]) + bytes(4), "byte3=255"),
    ]
    
    # Read baseline
    print("\nBaseline:")
    baseline_samples = []
    for _ in range(10):
        frames = can.receive(timeout=0.2)
        for f in frames:
            if f.is_extended:
                msg_type = (f.can_id >> 8) & 0xFF
                if msg_type == 0x53:
                    baseline_samples.append(f.data[:5])
    
    if baseline_samples:
        d = baseline_samples[0]
        print(f"  V={struct.unpack_from('<H', d, 0)[0] * 0.1:.1f}V "
              f"I={struct.unpack_from('<h', d, 2)[0] * 0.01:.2f}A "
              f"b4={d[4]:d}")
    
    for cmd_id, data, desc in test_configs:
        print(f"\n  Testing: {desc} (data={data.hex().upper()})...")
        
        # Send for 2 seconds
        for i in range(100):
            can.send_frame(CANFrame(can_id=cmd_id, data=data, is_extended=True))
            time.sleep(0.02)
        
        # Read telemetry
        for _ in range(5):
            frames = can.receive(timeout=0.2)
            for f in frames:
                if f.is_extended and (f.can_id >> 8) & 0xFF == 0x53:
                    d = f.data
                    v = struct.unpack_from('<H', d, 0)[0] * 0.1
                    i_val = struct.unpack_from('<h', d, 2)[0] * 0.01
                    print(f"    📊 V={v:.1f}V I={i_val:.2f}A b4={d[4]:d}")
                    if abs(i_val) > 0.1:
                        print(f"    🎯 CURRENT DETECTED! Motor is drawing power!")
                    break
        
        # Stop
        for _ in range(20):
            can.send_frame(CANFrame(can_id=cmd_id, data=bytes(8), is_extended=True))
            time.sleep(0.02)
        time.sleep(0.3)
    
    can.close()
    print("\n✅ Analysis complete!")

if __name__ == "__main__":
    main()
