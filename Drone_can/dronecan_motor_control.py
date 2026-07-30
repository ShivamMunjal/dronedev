#!/usr/bin/env python3
"""
Hobbywing ESC — Motor Control via DroneCAN
===========================================
Now that we KNOW the ESC responds to DroneCAN services (Node ID 1),
let's properly spin the motor using:
  1. com.hobbywing.esc.RawCommand (DTID 20100) — Hobbywing custom
  2. uavcan.equipment.esc.RawCommand (DTID 1030) — Standard DroneCAN

⚠️ REMOVE PROPELLERS BEFORE RUNNING!
"""

import sys
import time
import signal
import struct

import dronecan
from dronecan.transport import Transfer

from waveshare_can import (
    WaveshareCAN, detect_adapter, CANFrame,
    CAN_BAUD_500K, CAN_MODE_NORMAL
)

HWCAN_TELEM_VI   = 0x1F4E5301
HWCAN_TELEM_RPM  = 0x1F4E5401
HWCAN_TELEM_TEMP = 0x1F4E5201

_stop = False
def sigint(s, f):
    global _stop
    _stop = True
    print("\n🛑 STOPPING — sending zero throttle...")
signal.signal(signal.SIGINT, sigint)

OUR_NODE_ID = 10
ESC_NODE_ID = 1
_tid = 0

def next_tid():
    global _tid
    _tid = (_tid + 1) % 32
    return _tid


def send_message(can, msg, priority=0):
    """Send a DroneCAN broadcast message."""
    tr = Transfer(
        transfer_id=next_tid(),
        source_node_id=OUR_NODE_ID,
        payload=msg,
        transfer_priority=priority,
        service_not_message=False
    )
    for f in tr.to_frames():
        can_frame = CANFrame(
            can_id=f.message_id,
            data=bytes(f.bytes),
            is_extended=True
        )
        can.send_frame(can_frame)


def send_node_status(can):
    """Send our NodeStatus heartbeat."""
    msg = dronecan.uavcan.protocol.NodeStatus(
        uptime_sec=int(time.time()) & 0xFFFFFFFF,
        health=0, mode=0, sub_mode=0,
        vendor_specific_status_code=0
    )
    send_message(can, msg, priority=6)


def read_telemetry(can, duration=0.05):
    """Quick telemetry read."""
    telem = {'voltage': 0.0, 'current': 0.0, 'rpm_raw': 0, 'temp': 0}
    start = time.time()
    while time.time() - start < duration:
        for f in can.receive(timeout=0.01):
            if not f.is_extended:
                continue
            if f.can_id == HWCAN_TELEM_VI and len(f.data) >= 5:
                telem['voltage'] = struct.unpack_from('<H', f.data, 0)[0] * 0.1
                telem['current'] = struct.unpack_from('<h', f.data, 2)[0] * 0.01
                telem['temp'] = f.data[4]
            elif f.can_id == HWCAN_TELEM_RPM and len(f.data) >= 2:
                telem['rpm_raw'] = struct.unpack_from('<H', f.data, 0)[0]
    return telem


def send_hw_raw_command(can, throttle_values):
    """Send com.hobbywing.esc.RawCommand (DTID 20100)."""
    msg = dronecan.com.hobbywing.esc.RawCommand(command=throttle_values)
    send_message(can, msg, priority=0)


def send_std_raw_command(can, throttle_values):
    """Send uavcan.equipment.esc.RawCommand (DTID 1030)."""
    msg = dronecan.uavcan.equipment.esc.RawCommand(cmd=throttle_values)
    send_message(can, msg, priority=0)


def throttle_loop(can, cmd_func, cmd_name, throttle_val, duration=3.0, rate_hz=50):
    """Send throttle at a given rate, monitoring telemetry."""
    print(f"\n  📤 {cmd_name}: throttle={throttle_val} for {duration}s @ {rate_hz}Hz")
    period = 1.0 / rate_hz
    start = time.time()
    count = 0
    baseline_current = None
    motor_active = False
    
    while time.time() - start < duration:
        if _stop:
            break
        
        cmd_func(can, [throttle_val])
        count += 1
        
        if count % 10 == 0:
            t = read_telemetry(can, 0.01)
            if baseline_current is None:
                baseline_current = t['current']
            
            current_delta = abs(t['current'] - (baseline_current or 0))
            if current_delta > 0.5:
                motor_active = True
            
            print(f"\r     V={t['voltage']:5.1f}V I={t['current']:6.2f}A RPM={t['rpm_raw']:5d}"
                  f" [ΔI={current_delta:.2f}A {'🟢ACTIVE' if motor_active else '⚪idle'}]",
                  end="", flush=True)
        
        elapsed = time.time() - start
        next_time = (count) * period
        if next_time > elapsed:
            time.sleep(next_time - elapsed)
    
    print()
    return motor_active


def stop_motor(can, cmd_func, duration=1.0, rate_hz=50):
    """Send zero throttle to stop."""
    period = 1.0 / rate_hz
    start = time.time()
    count = 0
    while time.time() - start < duration:
        cmd_func(can, [0])
        count += 1
        elapsed = time.time() - start
        next_time = count * period
        if next_time > elapsed:
            time.sleep(next_time - elapsed)


def main():
    global _stop
    
    print("=" * 60)
    print("  Hobbywing ESC — DroneCAN Motor Control")
    print("  ⚠️  REMOVE PROPELLERS!")
    print("=" * 60)
    
    port = detect_adapter()
    if not port:
        sys.exit(1)
    
    can = WaveshareCAN()
    if not can.open(port):
        sys.exit(1)
    
    try:
        can.configure(
            can_baud=CAN_BAUD_500K,
            frame_type=0x02,
            mode=CAN_MODE_NORMAL,
            use_variable_protocol=True
        )
        time.sleep(0.3)
        
        # Verify ESC
        print("\n📊 ESC telemetry check...")
        t = read_telemetry(can, 1.0)
        print(f"   ✅ V={t['voltage']:.1f}V I={t['current']:.2f}A RPM={t['rpm_raw']}")
        
        # Send heartbeats
        print("\n📡 Establishing DroneCAN presence...")
        for i in range(30):
            send_node_status(can)
            time.sleep(0.02)
        
        # ──────────────────────────────────────────
        # TEST 1: Hobbywing RawCommand with escalating throttle
        # int14 range: -8192 to 8191
        # Typically 0 = stop, values scale linearly
        # ──────────────────────────────────────────
        print("\n" + "═" * 60)
        print("  TEST 1: com.hobbywing.esc.RawCommand (Hobbywing custom)")
        print("═" * 60)
        
        # Arm phase — send 0 for 2 seconds
        print("\n  Phase A: Arming (throttle=0, 2s)...")
        throttle_loop(can, send_hw_raw_command, "HW_RawCmd", 0, duration=2.0, rate_hz=50)
        
        if not _stop:
            # Low throttle
            active = throttle_loop(can, send_hw_raw_command, "HW_RawCmd", 1000, duration=3.0, rate_hz=50)
            if active:
                print("  🟢 MOTOR SPINNING with HW RawCommand @ 1000!")
                stop_motor(can, send_hw_raw_command)
            elif not _stop:
                # Try higher
                active = throttle_loop(can, send_hw_raw_command, "HW_RawCmd", 2000, duration=3.0, rate_hz=50)
                if active:
                    print("  🟢 MOTOR SPINNING with HW RawCommand @ 2000!")
                    stop_motor(can, send_hw_raw_command)
                elif not _stop:
                    active = throttle_loop(can, send_hw_raw_command, "HW_RawCmd", 4000, duration=3.0, rate_hz=50)
                    if active:
                        print("  🟢 MOTOR SPINNING with HW RawCommand @ 4000!")
                    stop_motor(can, send_hw_raw_command)
        
        # Stop before next test
        stop_motor(can, send_hw_raw_command, 1.0)
        
        if _stop:
            stop_motor(can, send_hw_raw_command, 1.0)
            stop_motor(can, send_std_raw_command, 1.0)
            return
        
        # ──────────────────────────────────────────
        # TEST 2: Standard uavcan.equipment.esc.RawCommand
        # int14 range: -8192 to 8191
        # ArduPilot uses 0-8191 for 0-100% throttle
        # ──────────────────────────────────────────
        print("\n" + "═" * 60)
        print("  TEST 2: uavcan.equipment.esc.RawCommand (Standard DroneCAN)")
        print("═" * 60)
        
        # Arm
        print("\n  Phase A: Arming (throttle=0, 2s)...")
        throttle_loop(can, send_std_raw_command, "STD_RawCmd", 0, duration=2.0, rate_hz=50)
        
        if not _stop:
            active = throttle_loop(can, send_std_raw_command, "STD_RawCmd", 1000, duration=3.0, rate_hz=50)
            if active:
                print("  🟢 MOTOR SPINNING with STD RawCommand @ 1000!")
                stop_motor(can, send_std_raw_command)
            elif not _stop:
                active = throttle_loop(can, send_std_raw_command, "STD_RawCmd", 2000, duration=3.0, rate_hz=50)
                if active:
                    print("  🟢 MOTOR SPINNING with STD RawCommand @ 2000!")
                    stop_motor(can, send_std_raw_command)
                elif not _stop:
                    active = throttle_loop(can, send_std_raw_command, "STD_RawCmd", 4000, duration=3.0, rate_hz=50)
                    if active:
                        print("  🟢 MOTOR SPINNING with STD RawCommand @ 4000!")
                    stop_motor(can, send_std_raw_command)
        
        # Final stop
        stop_motor(can, send_hw_raw_command, 0.5)
        stop_motor(can, send_std_raw_command, 0.5)
        
        print("\n" + "=" * 60)
        print("  TESTS COMPLETE")
        print("=" * 60)
        
    finally:
        # Emergency stop: send zeros on both command types
        try:
            for _ in range(100):
                send_hw_raw_command(can, [0])
                send_std_raw_command(can, [0])
                time.sleep(0.01)
        except:
            pass
        can.close()
        print("\n🔌 Done.")


if __name__ == "__main__":
    main()
