#!/usr/bin/env python3
"""
Hobbywing ESC DroneCAN Service Probe
=====================================
Non-destructive probe to check if the ESC responds to DroneCAN 
service requests while running in HWCAN mode.

Step 1: Send GetMajorConfig (read-only) to ESC node ID 1
Step 2: If it responds, optionally send SetThrottleSource(CAN_DIGITAL)
Step 3: If throttle source changed, try RawCommand to spin the motor

Safety: REMOVE PROPELLERS!
"""

import sys
import time
import signal
import struct

import dronecan
from dronecan.transport import Transfer, Frame, TransferManager

from waveshare_can import (
    WaveshareCAN, detect_adapter, CANFrame,
    CAN_BAUD_500K, CAN_MODE_NORMAL
)

# HWCAN telemetry IDs (for monitoring)
HWCAN_TELEM_VI  = 0x1F4E5301
HWCAN_TELEM_RPM = 0x1F4E5401

_stop = False
def sigint(s, f):
    global _stop
    _stop = True
    print("\n🛑 STOPPED")
signal.signal(signal.SIGINT, sigint)


def send_dronecan_service_request(can, request_msg, dest_node_id, source_node_id=10, transfer_id=0):
    """
    Serialize a DroneCAN service request and send it via Waveshare CAN.
    Returns the list of CAN frames sent.
    """
    tr = Transfer(
        transfer_id=transfer_id,
        source_node_id=source_node_id,
        dest_node_id=dest_node_id,
        payload=request_msg,
        transfer_priority=16,  # medium priority
        request_not_response=True,
        service_not_message=True
    )
    frames_sent = []
    for f in tr.to_frames():
        can_frame = CANFrame(
            can_id=f.message_id,
            data=bytes(f.bytes),
            is_extended=True
        )
        can.send_frame(can_frame)
        frames_sent.append(f)
        print(f"  📤 Sent: ID=0x{f.message_id:08X} Data=[{bytes(f.bytes).hex(' ').upper()}]")
    return frames_sent


def send_dronecan_node_status(can, source_node_id=10, transfer_id=0):
    """Send a NodeStatus heartbeat so the ESC knows we're alive."""
    msg = dronecan.uavcan.protocol.NodeStatus(
        uptime_sec=int(time.time()) & 0xFFFFFFFF,
        health=0,  # OK
        mode=0,    # Operational
        sub_mode=0,
        vendor_specific_status_code=0
    )
    tr = Transfer(
        transfer_id=transfer_id,
        source_node_id=source_node_id,
        payload=msg,
        transfer_priority=6,
        service_not_message=False
    )
    for f in tr.to_frames():
        can.send(f.message_id, bytes(f.bytes), extended=True)


def listen_for_service_response(can, expected_dtid, source_node_id, dest_node_id, timeout=2.0):
    """
    Listen for a DroneCAN service response frame.
    
    Service response CAN ID format (29-bit):
      [28:24] Priority (5 bits)
      [23:16] Service Type ID (8 bits)
      [15]    Request not Response (0 for response)
      [14:8]  Destination Node ID (7 bits) - this is US
      [7]     Service not Message (1)
      [6:0]   Source Node ID (7 bits) - this is the ESC
    """
    print(f"  📡 Listening for response (timeout={timeout}s)...")
    
    start = time.time()
    while time.time() - start < timeout:
        if _stop:
            return None
        frames = can.receive(timeout=0.2)
        for f in frames:
            if not f.is_extended:
                continue
            
            # Parse CAN ID
            cid = f.can_id
            src_node = cid & 0x7F
            is_service = bool(cid & 0x80)
            dest_node = (cid >> 8) & 0x7F
            is_request = bool(cid & 0x8000)
            service_type = (cid >> 16) & 0xFF
            priority = (cid >> 24) & 0x1F
            
            # Check if this is a service response from the ESC to us
            if is_service and not is_request and dest_node == source_node_id:
                print(f"  📥 Service Response! ID=0x{cid:08X}")
                print(f"      From Node: {src_node}")
                print(f"      Service Type: {service_type} (expected: {expected_dtid})")
                print(f"      Data: [{f.data.hex(' ').upper()}]")
                return f
            
            # Also log any non-HWCAN frames we see (potential DroneCAN)
            msg_type = (cid >> 8) & 0xFFFF
            if msg_type not in [0x4E52, 0x4E53, 0x4E54]:  # Not HWCAN telemetry
                if is_service:
                    print(f"  📨 Other service frame: ID=0x{cid:08X} [{f.data.hex(' ').upper()}]")
                elif msg_type == 341:  # NodeStatus
                    node_id = cid & 0x7F
                    print(f"  🟢 DroneCAN NodeStatus from node {node_id}!")
                    return f  # This alone proves DroneCAN is active
    
    return None


def read_telemetry(can, duration=0.3):
    """Quick telemetry read to confirm ESC is alive."""
    telem = {'voltage': 0.0, 'current': 0.0, 'rpm_raw': 0, 'has_data': False}
    start = time.time()
    while time.time() - start < duration:
        for f in can.receive(timeout=0.1):
            if f.is_extended and f.can_id == HWCAN_TELEM_VI and len(f.data) >= 4:
                telem['voltage'] = struct.unpack_from('<H', f.data, 0)[0] * 0.1
                telem['current'] = struct.unpack_from('<h', f.data, 2)[0] * 0.01
                telem['has_data'] = True
            elif f.is_extended and f.can_id == HWCAN_TELEM_RPM and len(f.data) >= 2:
                telem['rpm_raw'] = struct.unpack_from('<H', f.data, 0)[0]
                telem['has_data'] = True
    return telem


def main():
    global _stop
    
    print("=" * 60)
    print("  Hobbywing ESC — DroneCAN Service Probe")
    print("  This is NON-DESTRUCTIVE (read-only probing)")
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
        time.sleep(0.5)
        
        # Verify ESC is alive
        print("\n📊 Verifying ESC telemetry...")
        telem = read_telemetry(can, 1.0)
        if not telem['has_data']:
            print("❌ No HWCAN telemetry received. Is the ESC powered?")
            return
        print(f"   ✅ ESC alive: {telem['voltage']:.1f}V, {telem['current']:.2f}A")
        
        # ──────────────────────────────────────────
        # STEP 1: Send NodeStatus heartbeats first
        # (The ESC may need to see us as a live node)
        # ──────────────────────────────────────────
        print("\n📡 Sending NodeStatus heartbeats (establishing presence)...")
        for i in range(20):
            if _stop: return
            send_dronecan_node_status(can, source_node_id=10, transfer_id=i % 32)
            time.sleep(0.05)
        
        # Also listen for any DroneCAN NodeStatus from the ESC
        print("\n🔍 Listening for DroneCAN NodeStatus from ESC...")
        dronecan_detected = False
        start = time.time()
        while time.time() - start < 3.0:
            if _stop: return
            frames = can.receive(timeout=0.2)
            for f in frames:
                if not f.is_extended:
                    continue
                cid = f.can_id
                is_service = bool(cid & 0x80)
                msg_type = (cid >> 8) & 0xFFFF
                node_id = cid & 0x7F
                
                if not is_service and msg_type == 341:  # NodeStatus
                    print(f"   🟢 DroneCAN NodeStatus detected from node {node_id}!")
                    print(f"      Data: [{f.data.hex(' ').upper()}]")
                    dronecan_detected = True
                    break
            
            # Keep sending heartbeats
            send_dronecan_node_status(can, source_node_id=10, transfer_id=int(time.time()) % 32)
            
            if dronecan_detected:
                break
        
        if not dronecan_detected:
            print("   ⚠️  No DroneCAN NodeStatus seen from ESC")
            print("   (ESC may still respond to service requests)")
        
        # ──────────────────────────────────────────
        # STEP 2: Probe with GetMajorConfig (read-only)
        # ──────────────────────────────────────────
        print("\n" + "─" * 60)
        print("  STEP 2: Probing with GetMajorConfig (read-only)")
        print("─" * 60)
        
        esc_node_id = 1  # Default Hobbywing ESC node ID
        our_node_id = 10
        
        req = dronecan.com.hobbywing.esc.GetMajorConfig.Request(option=0)
        print(f"\n  Sending GetMajorConfig to ESC node {esc_node_id}...")
        
        send_dronecan_service_request(
            can, req, 
            dest_node_id=esc_node_id,
            source_node_id=our_node_id,
            transfer_id=1
        )
        
        response = listen_for_service_response(
            can,
            expected_dtid=242,  # GetMajorConfig
            source_node_id=our_node_id,
            dest_node_id=esc_node_id,
            timeout=2.0
        )
        
        if response is None:
            # Try other possible node IDs
            for try_node in [0, 2, 3, 127]:
                if _stop: break
                print(f"\n  Retrying with ESC node ID = {try_node}...")
                send_dronecan_service_request(
                    can, req,
                    dest_node_id=try_node,
                    source_node_id=our_node_id,
                    transfer_id=2
                )
                response = listen_for_service_response(
                    can,
                    expected_dtid=242,
                    source_node_id=our_node_id,
                    dest_node_id=try_node,
                    timeout=1.5
                )
                if response:
                    esc_node_id = try_node
                    break
        
        if response is None:
            print("\n" + "=" * 60)
            print("  RESULT: ESC did NOT respond to DroneCAN service requests")
            print("=" * 60)
            print()
            print("  This means the ESC is running HWCAN-only firmware and")
            print("  does NOT have a DroneCAN service listener active.")
            print()
            print("  To switch to DroneCAN mode, you need:")
            print("  1. Hobbywing DataLink V2 box (~$30-50)")
            print("  2. Or: Connect ESC to an ArduPilot flight controller")
            print("     with CAN_D1_UC_OPTION = 128 (Hobbywing ESC)")
            print()
            print("  The DataLink box connects via USB and has software to")
            print("  switch protocol mode, set baud rate, and configure IDs.")
            return
        
        print("\n" + "=" * 60)
        print("  🎉 ESC RESPONDED to DroneCAN service request!")
        print("=" * 60)
        print(f"  ESC Node ID: {esc_node_id}")
        print(f"  Response data: [{response.data.hex(' ').upper()}]")
        
        # ──────────────────────────────────────────
        # STEP 3: If we got here, try SetThrottleSource
        # ──────────────────────────────────────────
        print("\n" + "─" * 60)
        print("  STEP 3: Setting throttle source to CAN_DIGITAL")
        print("─" * 60)
        
        req2 = dronecan.com.hobbywing.esc.SetThrottleSource.Request(source=0)  # CAN_DIGITAL
        print(f"\n  Sending SetThrottleSource(CAN_DIGITAL) to node {esc_node_id}...")
        
        send_dronecan_service_request(
            can, req2,
            dest_node_id=esc_node_id,
            source_node_id=our_node_id,
            transfer_id=3
        )
        
        response2 = listen_for_service_response(
            can,
            expected_dtid=215,
            source_node_id=our_node_id,
            dest_node_id=esc_node_id,
            timeout=2.0
        )
        
        if response2:
            print("  ✅ SetThrottleSource acknowledged!")
            print(f"     Response: [{response2.data.hex(' ').upper()}]")
            
            # Now try sending throttle commands
            print("\n  Attempting motor spin with RawCommand...")
            time.sleep(1.0)
            
            # Arm: send 0 throttle
            for i in range(50):
                if _stop: break
                msg = dronecan.com.hobbywing.esc.RawCommand(command=[0])
                tr = Transfer(
                    transfer_id=i % 32,
                    source_node_id=our_node_id,
                    payload=msg,
                    transfer_priority=0,
                    service_not_message=False
                )
                for frame in tr.to_frames():
                    can.send(frame.message_id, bytes(frame.bytes), extended=True)
                time.sleep(0.02)
            
            # Low throttle test
            print("  Sending low throttle (500)...")
            for i in range(150):
                if _stop: break
                msg = dronecan.com.hobbywing.esc.RawCommand(command=[500])
                tr = Transfer(
                    transfer_id=i % 32,
                    source_node_id=our_node_id,
                    payload=msg,
                    transfer_priority=0,
                    service_not_message=False
                )
                for frame in tr.to_frames():
                    can.send(frame.message_id, bytes(frame.bytes), extended=True)
                time.sleep(0.02)
                
                if i % 25 == 0:
                    t = read_telemetry(can, 0.05)
                    print(f"\r     V={t['voltage']:5.1f}V I={t['current']:6.2f}A RPM={t['rpm_raw']:5d}", end="", flush=True)
            
            print()
            
            # Stop
            for i in range(50):
                msg = dronecan.com.hobbywing.esc.RawCommand(command=[0])
                tr = Transfer(
                    transfer_id=i % 32,
                    source_node_id=our_node_id,
                    payload=msg,
                    transfer_priority=0,
                    service_not_message=False
                )
                for frame in tr.to_frames():
                    can.send(frame.message_id, bytes(frame.bytes), extended=True)
                time.sleep(0.01)
            
            print("  ✅ Motor test complete")
        else:
            print("  ⚠️  SetThrottleSource sent but no response received")
        
    finally:
        can.close()
        print("\n🔌 Done.")


if __name__ == "__main__":
    main()
