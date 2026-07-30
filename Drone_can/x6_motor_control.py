#!/usr/bin/env python3
"""
Hobbywing X6 Plus Motor Control - WORKING VERSION
==================================================
Controls the Hobbywing X6 Plus ESC via CAN bus using the
Waveshare USB-CAN-A adapter with the discovered HWCAN protocol.

DISCOVERED PROTOCOL:
  Throttle Command:
    CAN ID:  0x1F4E5001 (extended frame)
    Format:  [00 00] [throttle_uint16_LE] [00 00 00 00]
    Range:   0 = stop, higher = more throttle (tested up to ~2000)
    
  Telemetry (ESC → us):
    0x1F4E5201 = Status/Info (7 bytes)
    0x1F4E5301 = Voltage/Current (6 bytes)
    0x1F4E5401 = RPM/Temperature (8 bytes)

Usage:
    source venv/bin/activate
    python x6_motor_control.py

⚠️  SAFETY WARNING:
    - Remove propellers before testing!
    - Motor will spin during the test
    - Press Ctrl+C at any time to EMERGENCY STOP
"""

import sys
import time
import signal
import struct

from waveshare_can import (
    WaveshareCAN, detect_adapter, CANFrame,
    CAN_BAUD_500K, CAN_MODE_NORMAL,
)

# ──────────────────────────────────────────────
# HWCAN Protocol Constants (Discovered)
# ──────────────────────────────────────────────
HWCAN_THROTTLE_ID   = 0x1F4E5001   # Throttle command CAN ID for ESC #1
HWCAN_TELEM_STATUS  = 0x1F4E5201   # Status telemetry 
HWCAN_TELEM_VI      = 0x1F4E5301   # Voltage/Current telemetry
HWCAN_TELEM_RPM     = 0x1F4E5401   # RPM/Temperature telemetry

# ──────────────────────────────────────────────
# Safety
# ──────────────────────────────────────────────
_emergency_stop = False

def signal_handler(sig, frame):
    global _emergency_stop
    _emergency_stop = True
    print("\n\n  🛑 EMERGENCY STOP TRIGGERED!")

signal.signal(signal.SIGINT, signal_handler)


# ──────────────────────────────────────────────
# Motor Control Functions
# ──────────────────────────────────────────────

def send_throttle(can: WaveshareCAN, throttle: int, esc_id: int = 1):
    """
    Send throttle command to the Hobbywing ESC.
    
    Args:
        can: WaveshareCAN adapter
        throttle: Throttle value (0 = stop, higher = faster)
        esc_id: ESC node ID (default 1)
    """
    cmd_id = 0x1F4E5000 | (esc_id & 0xFF)
    throttle_clamped = max(0, min(8000, throttle))
    
    # Data format: [00 00] [throttle uint16 LE] [00 00 00 00]
    data = bytes([0x00, 0x00]) + struct.pack('<H', throttle_clamped) + bytes([0x00, 0x00, 0x00, 0x00])
    
    frame = CANFrame(can_id=cmd_id, data=data, is_extended=True)
    return can.send_frame(frame)


def read_telemetry(can: WaveshareCAN, duration: float = 0.3) -> dict:
    """
    Read ESC telemetry data.
    
    Returns dict with: voltage, current, rpm, temperature, status
    """
    result = {
        'voltage': 0.0,
        'current': 0.0, 
        'rpm': 0,
        'rpm_raw': 0,
        'has_data': False,
    }
    
    start = time.time()
    while time.time() - start < duration:
        frames = can.receive(timeout=0.1)
        for f in frames:
            if not f.is_extended:
                continue
            
            if f.can_id == HWCAN_TELEM_VI and len(f.data) >= 4:
                v_raw = struct.unpack_from('<H', f.data, 0)[0]
                i_raw = struct.unpack_from('<h', f.data, 2)[0]
                result['voltage'] = v_raw * 0.1
                result['current'] = i_raw * 0.01
                result['has_data'] = True
            
            elif f.can_id == HWCAN_TELEM_RPM and len(f.data) >= 6:
                rpm_raw = struct.unpack_from('<H', f.data, 0)[0]
                result['rpm_raw'] = rpm_raw
                result['rpm'] = int(rpm_raw * 5.0 / 7.0)
                result['has_data'] = True
    
    return result


def emergency_stop(can: WaveshareCAN):
    """Send zero throttle rapidly to stop the motor."""
    print("  🛑 Stopping motor...")
    for _ in range(200):
        send_throttle(can, 0)
        time.sleep(0.005)
    print("  ✅ Motor stopped (zero throttle sent)")


def print_banner():
    print()
    print("╔" + "═" * 58 + "╗")
    print("║" + " 🚀 Hobbywing X6 Plus Motor Control - CAN Bus ".center(58) + "║")
    print("║" + " HWCAN Protocol (Discovered & Verified) ".center(58) + "║")
    print("╠" + "═" * 58 + "╣")
    print("║" + " ⚠️  REMOVE PROPELLERS BEFORE TESTING! ".center(58) + "║")
    print("║" + " Press Ctrl+C anytime for EMERGENCY STOP ".center(58) + "║")
    print("╚" + "═" * 58 + "╝")
    print()


def main():
    global _emergency_stop
    
    print_banner()
    
    # ── STEP 1: Detect & Connect ──
    print("━" * 60)
    print("  STEP 1: Detect Adapter & Connect")
    print("━" * 60)
    
    port = detect_adapter()
    if not port:
        print("❌ No adapter found!")
        sys.exit(1)
    
    can = WaveshareCAN()
    if not can.open(port, serial_baud=2000000):
        sys.exit(1)
    
    try:
        # Configure CAN bus  
        can.configure(
            can_baud=CAN_BAUD_500K,
            frame_type=0x02,
            mode=CAN_MODE_NORMAL,
            use_variable_protocol=True,
        )
        time.sleep(0.5)
        print("✅ CAN bus configured at 500 kbps")
        
        # ── STEP 2: Verify ESC Communication ──
        print("\n" + "━" * 60)
        print("  STEP 2: Verify ESC Communication")
        print("━" * 60)
        
        telem = read_telemetry(can, 1.0)
        
        if not telem['has_data']:
            print("❌ No ESC telemetry received!")
            print("   Check: CAN_H→CAN_H, CAN_L→CAN_L, 120Ω resistor, ESC powered")
            return
        
        print(f"  ✅ ESC Online!")
        print(f"     🔋 Voltage:  {telem['voltage']:.1f} V")
        print(f"     ⚡ Current:  {telem['current']:.2f} A")
        print(f"     🔄 RPM Raw:  {telem['rpm_raw']}")
        print(f"     📡 Protocol: HWCAN (Hobbywing Proprietary)")
        print(f"     🎯 CMD ID:   0x{HWCAN_THROTTLE_ID:08X}")
        
        if _emergency_stop: return
        
        # ── STEP 3: Arm ESC (Zero Throttle) ──
        print("\n" + "━" * 60)
        print("  STEP 3: Arming ESC (Sending Zero Throttle)")
        print("━" * 60)
        
        for i in range(100):  # 2 seconds
            if _emergency_stop: return emergency_stop(can)
            send_throttle(can, 0)
            time.sleep(0.02)
        
        telem = read_telemetry(can, 0.3)
        print(f"  ✅ ESC armed | V={telem['voltage']:.1f}V I={telem['current']:.2f}A")
        
        if _emergency_stop: return emergency_stop(can)
        
        # ── STEP 4: Ramp Up Motor ──
        target_throttle = 300   # Conservative throttle
        ramp_step = 20
        
        print("\n" + "━" * 60)
        print(f"  STEP 4: Starting Motor (Target Throttle: {target_throttle})")
        print("━" * 60)
        print("  🎵 Motor should start spinning now!\n")
        
        current_throttle = 0
        
        while current_throttle < target_throttle:
            if _emergency_stop:
                emergency_stop(can)
                return
            
            current_throttle = min(current_throttle + ramp_step, target_throttle)
            
            # Send throttle at 50Hz for 100ms per step
            for _ in range(5):
                if _emergency_stop: break
                send_throttle(can, current_throttle)
                time.sleep(0.02)
            
            # Read telemetry
            telem = read_telemetry(can, 0.05)
            
            # Progress bar
            pct = current_throttle / target_throttle * 100
            bar_len = int(pct / 2)
            bar = "█" * bar_len + "░" * (50 - bar_len)
            print(f"\r  Throttle: {current_throttle:4d} [{bar}] {pct:5.1f}% "
                  f"| V={telem['voltage']:5.1f}V I={telem['current']:5.2f}A "
                  f"RPM={telem['rpm_raw']:5d}", end="", flush=True)
        
        print("\n\n  ✅ Target throttle reached!")
        
        if _emergency_stop:
            emergency_stop(can)
            return
        
        # ── STEP 5: Hold & Monitor ──
        print("\n" + "━" * 60)
        print(f"  STEP 5: Holding Throttle at {target_throttle} for 5 seconds")
        print("━" * 60)
        
        hold_start = time.time()
        sample_count = 0
        
        while time.time() - hold_start < 5.0:
            if _emergency_stop:
                emergency_stop(can)
                return
            
            # Send throttle
            send_throttle(can, current_throttle)
            time.sleep(0.02)
            
            # Read telemetry every ~0.5s
            sample_count += 1
            if sample_count % 25 == 0:
                telem = read_telemetry(can, 0.05)
                elapsed = time.time() - hold_start
                print(f"\r  t={elapsed:.1f}s | 📊 V={telem['voltage']:5.1f}V "
                      f"I={telem['current']:6.2f}A RPM={telem['rpm_raw']:5d}  ", 
                      end="", flush=True)
        
        print()
        
        # ── STEP 6: Ramp Down ──
        print("\n" + "━" * 60)
        print("  STEP 6: Ramping Down")
        print("━" * 60)
        
        while current_throttle > 0:
            if _emergency_stop: break
            
            current_throttle = max(current_throttle - ramp_step, 0)
            
            for _ in range(5):
                send_throttle(can, current_throttle)
                time.sleep(0.02)
            
            pct = current_throttle / target_throttle * 100 if target_throttle > 0 else 0
            bar_len = int(pct / 2)
            bar = "█" * bar_len + "░" * (50 - bar_len)
            print(f"\r  Throttle: {current_throttle:4d} [{bar}] {pct:5.1f}%", end="", flush=True)
        
        print()
        
        # Send zero throttle for safety
        for _ in range(100):
            send_throttle(can, 0)
            time.sleep(0.02)
        
        # ── STEP 7: Final Status ──
        print("\n" + "━" * 60)
        print("  STEP 7: Final Status")
        print("━" * 60)
        
        time.sleep(0.5)
        telem = read_telemetry(can, 0.5)
        
        print(f"  🔋 Voltage:  {telem['voltage']:.1f} V")
        print(f"  ⚡ Current:  {telem['current']:.2f} A")
        print(f"  🔄 RPM Raw:  {telem['rpm_raw']}")
        print(f"  ✅ Motor test COMPLETE!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        emergency_stop(can)
    
    finally:
        # Always ensure motor is stopped
        try:
            emergency_stop(can)
        except:
            pass
        can.close()
    
    print("\n" + "═" * 60)
    print("  🏁 Session Complete!")
    print("═" * 60)
    
    if _emergency_stop:
        print("  ⚠️  Ended by emergency stop (Ctrl+C)")
    else:
        print("  ✅ Completed normally")
    print()


if __name__ == "__main__":
    main()
