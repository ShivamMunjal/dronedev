"""
DroneCAN Protocol Implementation for Hobbywing X6 Plus ESC
==========================================================
Implements the minimal DroneCAN (UAVCAN v0) protocol needed to:
1. Send ESC RawCommand (throttle) messages
2. Handle NodeStatus broadcasts
3. Parse ESC status telemetry

DroneCAN CAN ID Structure (29-bit extended):
  Bits 0-6:   Source Node ID (7 bits)
  Bit 7:      Service not message (0 for broadcast)
  Bits 8-9:   Reserved (0)
  Bits 10-25: Message Type ID (16 bits) 
  Bits 26-28: Priority (3 bits, 0=highest)

Key Message Types:
  - uavcan.protocol.NodeStatus (341): Heartbeat from nodes
  - uavcan.equipment.esc.RawCommand (1030): Throttle commands
  - uavcan.equipment.esc.Status (1034): ESC telemetry feedback

Reference:
  https://dronecan.github.io/Specification/
"""

import struct
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from waveshare_can import WaveshareCAN, CANFrame


# ──────────────────────────────────────────────
# DroneCAN Message Type IDs
# ──────────────────────────────────────────────
MSG_NODE_STATUS     = 341   # uavcan.protocol.NodeStatus
MSG_ESC_RAW_COMMAND = 1030  # uavcan.equipment.esc.RawCommand
MSG_ESC_STATUS      = 1034  # uavcan.equipment.esc.Status
MSG_GET_NODE_INFO   = 1     # uavcan.protocol.GetNodeInfo (service)

# DroneCAN Transfer Constants
TOGGLE_BIT        = 0x20  # Bit 5 in tail byte
START_OF_TRANSFER = 0x80  # Bit 7 in tail byte
END_OF_TRANSFER   = 0x40  # Bit 6 in tail byte

# Node health constants
HEALTH_OK       = 0
HEALTH_WARNING  = 1
HEALTH_ERROR    = 2
HEALTH_CRITICAL = 3

HEALTH_NAMES = {
    HEALTH_OK: "OK",
    HEALTH_WARNING: "WARNING", 
    HEALTH_ERROR: "ERROR",
    HEALTH_CRITICAL: "CRITICAL",
}

# Node mode constants
MODE_OPERATIONAL     = 0
MODE_INITIALIZATION  = 1
MODE_MAINTENANCE     = 2
MODE_SOFTWARE_UPDATE = 3

MODE_NAMES = {
    MODE_OPERATIONAL: "Operational",
    MODE_INITIALIZATION: "Initialization",
    MODE_MAINTENANCE: "Maintenance",
    MODE_SOFTWARE_UPDATE: "Software Update",
}


@dataclass
class NodeStatus:
    """Parsed uavcan.protocol.NodeStatus message."""
    node_id: int
    uptime_sec: int
    health: int
    mode: int
    sub_mode: int
    vendor_specific_status_code: int
    
    def __repr__(self):
        health_str = HEALTH_NAMES.get(self.health, f"Unknown({self.health})")
        mode_str = MODE_NAMES.get(self.mode, f"Unknown({self.mode})")
        return (f"NodeStatus(id={self.node_id}, uptime={self.uptime_sec}s, "
                f"health={health_str}, mode={mode_str}, vssc=0x{self.vendor_specific_status_code:04X})")


@dataclass 
class ESCStatus:
    """Parsed uavcan.equipment.esc.Status message."""
    node_id: int
    error_count: int
    voltage: float
    current: float
    temperature: float
    rpm: int
    power_rating_pct: int
    esc_index: int


def build_dronecan_can_id(message_type_id: int, source_node_id: int, priority: int = 4) -> int:
    """
    Build a 29-bit DroneCAN CAN ID for broadcast messages.
    
    DroneCAN CAN ID format:
      [28:26] Priority (3 bits)
      [25:10] Message Type ID (16 bits) -- but actually shifted
      [9:8]   Reserved (0)
      [7]     Service not Message (0 for broadcast)
      [6:0]   Source Node ID (7 bits)
    
    Actually the UAVCAN v0 format is:
      Bits 28-26: Priority (0-7, lower = higher priority)
      Bits 25-8:  Message Type ID (16 bits) shifted << 8
      Bit 7:      Service not Message flag (0)
      Bits 6-0:   Source Node ID
    """
    can_id = 0
    can_id |= (priority & 0x07) << 24
    can_id |= (message_type_id & 0xFFFF) << 8
    can_id |= 0 << 7  # Broadcast (not service)
    can_id |= (source_node_id & 0x7F)
    return can_id


def parse_dronecan_can_id(can_id: int) -> dict:
    """
    Parse a 29-bit DroneCAN CAN ID.
    
    Returns dict with: priority, message_type_id, is_service, source_node_id
    """
    source_node_id = can_id & 0x7F
    is_service = bool(can_id & 0x80)
    message_type_id = (can_id >> 8) & 0xFFFF
    priority = (can_id >> 24) & 0x07
    
    return {
        'priority': priority,
        'message_type_id': message_type_id,
        'is_service': is_service,
        'source_node_id': source_node_id,
    }


class DroneCAN:
    """
    Minimal DroneCAN protocol implementation for ESC control.
    """
    
    def __init__(self, can_adapter: WaveshareCAN, node_id: int = 10):
        """
        Initialize DroneCAN protocol handler.
        
        Args:
            can_adapter: WaveshareCAN adapter instance
            node_id: Our DroneCAN node ID (1-127)
        """
        self.can = can_adapter
        self.node_id = node_id
        self._transfer_id = 0  # Increments with each transfer
        self._discovered_nodes = {}
    
    def _next_transfer_id(self) -> int:
        """Get next transfer ID (0-31 wrapping)."""
        tid = self._transfer_id
        self._transfer_id = (self._transfer_id + 1) % 32
        return tid
    
    def send_node_status(self, health: int = HEALTH_OK, mode: int = MODE_OPERATIONAL):
        """
        Send our NodeStatus heartbeat message.
        
        uavcan.protocol.NodeStatus format (7 bytes):
          uint32 uptime_sec
          uint2 health
          uint2 mode
          uint3 sub_mode
          uint16 vendor_specific_status_code
        """
        uptime = int(time.time()) & 0xFFFFFFFF
        
        # Pack status fields: health (2 bits) | mode (2 bits) | sub_mode (3 bits) = 7 bits
        status_byte = ((health & 0x03) << 6) | ((mode & 0x03) << 4) | (0 & 0x07)
        # Actually in DroneCAN the packing is different, let me use the proper format
        
        # NodeStatus is 7 bytes:
        # bytes 0-3: uptime_sec (uint32, little-endian)
        # byte 4: bits 0-1: health, bits 2-3: mode, bits 4-6: sub_mode
        # bytes 5-6: vendor_specific_status_code (uint16, little-endian)
        
        status_bits = (health & 0x03) | ((mode & 0x03) << 2)
        payload = struct.pack('<IBH', uptime, status_bits, 0)
        
        # Build CAN frame
        can_id = build_dronecan_can_id(MSG_NODE_STATUS, self.node_id, priority=6)
        
        # Add tail byte for single-frame transfer
        tid = self._next_transfer_id()
        tail_byte = START_OF_TRANSFER | END_OF_TRANSFER | (tid & 0x1F)
        
        data = payload + bytes([tail_byte])
        
        if len(data) <= 8:
            frame = CANFrame(can_id=can_id, data=data, is_extended=True)
            self.can.send_frame(frame)
    
    def send_esc_raw_command(self, throttle_values: List[int]):
        """
        Send ESC RawCommand message to control motor throttle.
        
        uavcan.equipment.esc.RawCommand format:
          int14[] cmd  - Array of throttle commands
          
        Each command is a 14-bit signed integer (-8192 to 8191).
        The values are packed as a dynamic array with DSDL bit packing.
        
        For a single ESC (index 0), the format is simpler.
        
        Args:
            throttle_values: List of throttle values (-8192 to 8191) for each ESC index
        """
        # Pack 14-bit signed values
        # DroneCAN uses bit-level packing with DSDL
        # For RawCommand, it's: void5 + uint3 (array length) + int14[] (values)
        # Actually, it's a dynamic array: the length is implicitly determined by the payload size
        
        # Simpler approach: pack each 14-bit value in little-endian bit order
        # For DroneCAN, the RawCommand payload is just the packed 14-bit values
        
        # Each int14 takes 14 bits. For N values, total bits = N * 14
        # Pack into bytes, LSB first
        
        bits = []
        for val in throttle_values:
            # Clamp to int14 range
            val = max(-8192, min(8191, val))
            # Convert to unsigned 14-bit representation (two's complement)
            if val < 0:
                val = (1 << 14) + val
            # Extract 14 bits, LSB first
            for bit_pos in range(14):
                bits.append((val >> bit_pos) & 1)
        
        # Pad to byte boundary
        while len(bits) % 8 != 0:
            bits.append(0)
        
        # Convert bits to bytes
        payload = bytearray()
        for byte_idx in range(len(bits) // 8):
            byte_val = 0
            for bit_pos in range(8):
                if bits[byte_idx * 8 + bit_pos]:
                    byte_val |= (1 << bit_pos)
            payload.append(byte_val)
        
        # Build CAN ID for RawCommand (message type 1030)
        can_id = build_dronecan_can_id(MSG_ESC_RAW_COMMAND, self.node_id, priority=0)
        
        # Add tail byte
        tid = self._next_transfer_id()
        tail_byte = START_OF_TRANSFER | END_OF_TRANSFER | (tid & 0x1F)
        
        data = bytes(payload) + bytes([tail_byte])
        
        # RawCommand with up to 4 ESCs fits in a single CAN frame (4 * 14 / 8 = 7 bytes + 1 tail = 8)
        if len(data) <= 8:
            frame = CANFrame(can_id=can_id, data=data, is_extended=True)
            return self.can.send_frame(frame)
        else:
            # Multi-frame transfer needed
            return self._send_multi_frame(can_id, payload, MSG_ESC_RAW_COMMAND)
    
    def _send_multi_frame(self, can_id: int, payload: bytes, msg_type_id: int) -> bool:
        """Send a multi-frame DroneCAN transfer."""
        # Calculate CRC for multi-frame transfers
        crc = self._compute_crc16(payload, msg_type_id)
        
        # Add CRC to payload
        full_data = payload + struct.pack('<H', crc)
        
        tid = self._next_transfer_id()
        toggle = False
        offset = 0
        first = True
        
        while offset < len(full_data):
            is_last = (offset + 7) >= len(full_data)
            chunk = full_data[offset:offset + 7]
            
            tail_byte = tid & 0x1F
            if toggle:
                tail_byte |= TOGGLE_BIT
            if first:
                tail_byte |= START_OF_TRANSFER
            if is_last:
                tail_byte |= END_OF_TRANSFER
            
            frame_data = bytes(chunk) + bytes([tail_byte])
            frame = CANFrame(can_id=can_id, data=frame_data, is_extended=True)
            self.can.send_frame(frame)
            
            toggle = not toggle
            first = False
            offset += 7
            
            time.sleep(0.001)  # Small delay between frames
        
        return True
    
    def _compute_crc16(self, data: bytes, msg_type_id: int) -> int:
        """Compute DroneCAN CRC-16/CCITT-FALSE."""
        crc = 0xFFFF
        
        # Include data type signature in CRC for multi-frame
        # (simplified - proper implementation needs DSDL signature)
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc = crc << 1
                crc &= 0xFFFF
        
        return crc
    
    def parse_received_frame(self, frame: CANFrame) -> Optional[dict]:
        """
        Parse a received CAN frame as a DroneCAN message.
        
        Args:
            frame: Received CAN frame (must be extended)
            
        Returns:
            Parsed message dict or None
        """
        if not frame.is_extended or len(frame.data) < 1:
            return None
        
        # Parse CAN ID
        info = parse_dronecan_can_id(frame.can_id)
        
        # Get tail byte (last byte of data)
        tail_byte = frame.data[-1]
        payload = frame.data[:-1]
        
        transfer_id = tail_byte & 0x1F
        is_start = bool(tail_byte & START_OF_TRANSFER)
        is_end = bool(tail_byte & END_OF_TRANSFER)
        toggle = bool(tail_byte & TOGGLE_BIT)
        
        result = {
            **info,
            'transfer_id': transfer_id,
            'is_start': is_start,
            'is_end': is_end,
            'payload': payload,
            'raw_frame': frame,
        }
        
        # Parse known message types
        if info['message_type_id'] == MSG_NODE_STATUS and is_start and is_end:
            result['parsed'] = self._parse_node_status(payload, info['source_node_id'])
        elif info['message_type_id'] == MSG_ESC_STATUS and is_start and is_end:
            result['parsed'] = self._parse_esc_status(payload, info['source_node_id'])
        
        return result
    
    def _parse_node_status(self, payload: bytes, node_id: int) -> Optional[NodeStatus]:
        """Parse NodeStatus message payload."""
        if len(payload) < 7:
            return None
        
        try:
            uptime = struct.unpack_from('<I', payload, 0)[0]
            status_bits = payload[4]
            health = status_bits & 0x03
            mode = (status_bits >> 2) & 0x03
            sub_mode = (status_bits >> 4) & 0x07
            vssc = struct.unpack_from('<H', payload, 5)[0]
            
            status = NodeStatus(
                node_id=node_id,
                uptime_sec=uptime,
                health=health,
                mode=mode,
                sub_mode=sub_mode,
                vendor_specific_status_code=vssc,
            )
            
            self._discovered_nodes[node_id] = status
            return status
        except Exception:
            return None
    
    def _parse_esc_status(self, payload: bytes, node_id: int) -> Optional[ESCStatus]:
        """Parse ESC Status message payload."""
        if len(payload) < 6:
            return None
        
        try:
            # ESC Status format (simplified):
            # uint32 error_count
            # float16 voltage
            # float16 current  
            # float16 temperature
            # int18 rpm
            # uint7 power_rating_pct
            # uint5 esc_index
            
            error_count = struct.unpack_from('<I', payload, 0)[0]
            # Note: float16 decoding would need proper half-precision handling
            # For now, return raw data
            
            return ESCStatus(
                node_id=node_id,
                error_count=error_count,
                voltage=0.0,
                current=0.0,
                temperature=0.0,
                rpm=0,
                power_rating_pct=0,
                esc_index=0,
            )
        except Exception:
            return None
    
    def discover_nodes(self, timeout: float = 3.0) -> dict:
        """
        Listen for DroneCAN NodeStatus messages to discover nodes on the bus.
        
        Args:
            timeout: How long to listen in seconds
            
        Returns:
            Dict of discovered nodes {node_id: NodeStatus}
        """
        print(f"🔍 Discovering DroneCAN nodes (listening for {timeout}s)...")
        self._discovered_nodes.clear()
        
        start = time.time()
        while time.time() - start < timeout:
            frames = self.can.receive(timeout=0.5)
            for frame in frames:
                if frame.is_extended:
                    result = self.parse_received_frame(frame)
                    if result and 'parsed' in result and isinstance(result['parsed'], NodeStatus):
                        ns = result['parsed']
                        print(f"  🟢 Found: {ns}")
                else:
                    # Also print standard frames for debugging
                    print(f"  📨 Standard frame: {frame}")
        
        return self._discovered_nodes
    
    def scan_bus(self, timeout: float = 5.0):
        """
        Scan the CAN bus for any traffic and report findings.
        
        Args:
            timeout: How long to listen in seconds
        """
        print(f"\n📡 Scanning CAN bus for all traffic ({timeout}s)...")
        
        seen_ids = {}
        start = time.time()
        frame_count = 0
        
        while time.time() - start < timeout:
            frames = self.can.receive(timeout=0.5)
            for frame in frames:
                frame_count += 1
                key = (frame.can_id, frame.is_extended)
                
                if key not in seen_ids:
                    seen_ids[key] = 0
                    ext_str = "EXT" if frame.is_extended else "STD"
                    
                    if frame.is_extended:
                        info = parse_dronecan_can_id(frame.can_id)
                        msg_type = info['message_type_id']
                        src = info['source_node_id']
                        print(f"  📨 [{ext_str}] ID=0x{frame.can_id:08X} "
                              f"(MsgType={msg_type}, Node={src}) "
                              f"DLC={frame.dlc} Data=[{frame.data.hex().upper()}]")
                    else:
                        print(f"  📨 [{ext_str}] ID=0x{frame.can_id:03X} "
                              f"DLC={frame.dlc} Data=[{frame.data.hex().upper()}]")
                
                seen_ids[key] += 1
        
        print(f"\n  Summary: {frame_count} frames received, {len(seen_ids)} unique IDs")
        for (can_id, is_ext), count in sorted(seen_ids.items()):
            ext = "EXT" if is_ext else "STD"
            print(f"    [{ext}] 0x{can_id:08X if is_ext else can_id:03X}: {count} frames")


if __name__ == "__main__":
    from waveshare_can import detect_adapter, CAN_BAUD_500K
    
    print("=" * 60)
    print("  DroneCAN Protocol Test")
    print("=" * 60)
    
    port = detect_adapter()
    if not port:
        exit(1)
    
    can = WaveshareCAN()
    if not can.open(port):
        exit(1)
    
    # Configure for 500kbps (X6 Plus default)
    can.configure(
        can_baud=CAN_BAUD_500K,
        frame_type=0x02,  # Extended frame for DroneCAN
        mode=0x00,  # Normal
        use_variable_protocol=True
    )
    
    dc = DroneCAN(can, node_id=10)
    
    # Scan for any traffic
    dc.scan_bus(timeout=5.0)
    
    # Try to discover nodes
    nodes = dc.discover_nodes(timeout=3.0)
    
    if nodes:
        print(f"\n✅ Found {len(nodes)} DroneCAN node(s)")
    else:
        print("\n⚠️  No DroneCAN nodes discovered")
        print("   The ESC may need power or may use a different baud rate")
    
    can.close()
