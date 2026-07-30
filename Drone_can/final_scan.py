#!/usr/bin/env python3
"""
Final comprehensive scan - tries wide CAN ID ranges including
standard frames, different DroneCAN priorities, and monitors
ALL telemetry fields for ANY change.
"""
import sys, time, signal, struct
from waveshare_can import WaveshareCAN, detect_adapter, CANFrame, CAN_BAUD_500K, CAN_MODE_NORMAL

_stop = False
def sigint(s,f):
    global _stop; _stop = True; print("\n🛑 STOPPED")
signal.signal(signal.SIGINT, sigint)

def snapshot(can, dur=0.4):
    """Capture a full telemetry snapshot."""
    r = {}
    t0 = time.time()
    while time.time() - t0 < dur:
        for f in can.receive(timeout=0.15):
            if f.is_extended:
                mt = (f.can_id >> 8) & 0xFF
                r[mt] = f.data[:-1]  # exclude transfer counter
    return r

def snapshots_differ(a, b):
    """Check if any telemetry field changed."""
    for k in a:
        if k in b and a[k] != b[k]:
            return True, k
    return False, None

def main():
    global _stop
    port = detect_adapter()
    if not port: sys.exit(1)
    can = WaveshareCAN()
    if not can.open(port): sys.exit(1)
    can.configure(can_baud=CAN_BAUD_500K, frame_type=0x02, mode=CAN_MODE_NORMAL, use_variable_protocol=True)
    time.sleep(0.5)

    print("="*60)
    print("  FINAL COMPREHENSIVE THROTTLE SCAN")
    print("  Monitoring ALL telemetry fields for ANY change")
    print("="*60)

    # Baseline
    baseline = snapshot(can, 1.0)
    print(f"\nBaseline captured: {len(baseline)} frame types")
    for mt, data in baseline.items():
        print(f"  0x{mt:02X}: {data.hex(' ').upper()}")

    throttle_payloads = [
        struct.pack('<H', 1000) + bytes(6),
        bytes(2) + struct.pack('<H', 1000) + bytes(4),
        struct.pack('>H', 1000) + bytes(6),
        bytes([0x00, 0x00, 0xE8, 0x03, 0x00, 0x00, 0x00, 0x00]),  # 1000 at offset 2
    ]

    # ---- EXTENDED FRAMES: Wide CAN ID scan ----
    ext_ids = []
    
    # Hobbywing patterns
    for prefix in [0x1F4E, 0x1F05, 0x1F06, 0x1F00, 0x0000, 0x0100, 0x0200]:
        for mtype in range(0x00, 0x60):
            ext_ids.append((prefix << 16) | (mtype << 8) | 0x01)
    
    # DroneCAN with all priorities (0-31) for ESC RawCommand (1030)
    for pri in range(32):
        ext_ids.append((pri << 24) | (1030 << 8) | 10)
        ext_ids.append((pri << 24) | (1030 << 8) | 1)  # pretend to be node 1
    
    # DroneCAN with other message types
    for msg_type in [1010, 1030, 1034, 200, 341]:
        for pri in [0, 4, 16, 20]:
            for nid in [1, 10, 127]:
                ext_ids.append((pri << 24) | (msg_type << 8) | nid)

    # Remove duplicates
    ext_ids = list(set(ext_ids))
    
    # ---- STANDARD FRAMES ----
    std_ids = list(range(0, 0x800))  # All 2048 standard CAN IDs
    
    total = len(ext_ids) * len(throttle_payloads) + len(std_ids)
    tested = 0
    print(f"\nScanning {len(ext_ids)} extended IDs × {len(throttle_payloads)} payloads + {len(std_ids)} standard IDs")
    print(f"Total combinations: {total}")
    print()

    # Test extended frames
    for cid in ext_ids:
        if _stop: break
        for payload in throttle_payloads:
            if _stop: break
            tested += 1
            if tested % 100 == 0:
                print(f"\r  Progress: {tested}/{total} ({tested*100//total}%)    ", end="", flush=True)
            
            # Send command for ~0.5s
            for _ in range(25):
                can.send_frame(CANFrame(can_id=cid, data=payload, is_extended=True))
                time.sleep(0.02)
            
            # Check telemetry
            current = snapshot(can, 0.15)
            changed, field = snapshots_differ(baseline, current)
            
            if changed:
                print(f"\n\n  🎯 CHANGE DETECTED!")
                print(f"     CAN ID: 0x{cid:08X} (extended)")
                print(f"     Payload: {payload.hex(' ').upper()}")
                print(f"     Changed field: 0x{field:02X}")
                print(f"     Before: {baseline[field].hex(' ').upper()}")
                print(f"     After:  {current[field].hex(' ').upper()}")
                
                # Check if current draw changed
                if 0x53 in current and len(current[0x53]) >= 4:
                    i_val = struct.unpack_from('<h', current[0x53], 2)[0]
                    if abs(i_val) > 5:
                        print(f"     ⚡ MOTOR DRAWING CURRENT: {i_val * 0.01:.2f}A!")
                
                # Stop
                for _ in range(50):
                    can.send_frame(CANFrame(can_id=cid, data=bytes(8), is_extended=True))
                    time.sleep(0.01)
                
                # Re-read baseline to see if it returns to normal
                time.sleep(0.5)
                new_base = snapshot(can, 0.5)
                print(f"     After stop: {new_base.get(field, b'N/A').hex(' ').upper() if isinstance(new_base.get(field), bytes) else 'N/A'}")
                
                # Update baseline
                baseline = snapshot(can, 0.5)
                continue
            
            # Brief zero
            can.send_frame(CANFrame(can_id=cid, data=bytes(8), is_extended=True))

    if not _stop:
        # Test standard frames
        print(f"\n\n  Now testing standard (11-bit) CAN IDs...")
        payload = struct.pack('<H', 1000) + bytes(6)
        
        for sid in std_ids:
            if _stop: break
            tested += 1
            if tested % 200 == 0:
                print(f"\r  Progress: {tested}/{total} ({tested*100//total}%) STD ID=0x{sid:03X}  ", end="", flush=True)
            
            for _ in range(15):
                can.send_frame(CANFrame(can_id=sid, data=payload, is_extended=False))
                time.sleep(0.02)
            
            current = snapshot(can, 0.1)
            changed, field = snapshots_differ(baseline, current)
            
            if changed:
                print(f"\n\n  🎯 STD FRAME CHANGE!")
                print(f"     CAN ID: 0x{sid:03X} (standard)")
                print(f"     Changed field: 0x{field:02X}")
                print(f"     Before: {baseline[field].hex(' ').upper()}")
                print(f"     After:  {current[field].hex(' ').upper()}")
                
                for _ in range(50):
                    can.send_frame(CANFrame(can_id=sid, data=bytes(8), is_extended=False))
                    time.sleep(0.01)
                baseline = snapshot(can, 0.5)

    print(f"\n\nScan complete. Tested {tested} combinations.")
    can.close()
    print("✅ Done")

if __name__ == "__main__":
    main()
