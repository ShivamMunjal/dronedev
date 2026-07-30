"""
Waveshare USB-CAN-A Adapter Driver for macOS
=============================================
Implements the proprietary serial protocol used by the Waveshare USB-CAN-A
adapter to send and receive CAN frames over a virtual COM port.

Protocol Reference:
  https://www.waveshare.com/wiki/Secondary_Development_Serial_Conversion_Definition_of_CAN_Protocol

Supports:
  - Variable-length communication protocol
  - Standard (CAN2.0A) and Extended (CAN2.0B) frames
  - CAN configuration commands (baud rate, mode, filters)
  - Non-blocking receive with timeout
"""

import serial
import struct
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Callable


# ──────────────────────────────────────────────
# CAN Baud Rate Codes
# ──────────────────────────────────────────────
CAN_BAUD_1M   = 0x01
CAN_BAUD_800K = 0x02
CAN_BAUD_500K = 0x03
CAN_BAUD_400K = 0x04
CAN_BAUD_250K = 0x05
CAN_BAUD_200K = 0x06
CAN_BAUD_125K = 0x07
CAN_BAUD_100K = 0x08
CAN_BAUD_50K  = 0x09
CAN_BAUD_20K  = 0x0A
CAN_BAUD_10K  = 0x0B
CAN_BAUD_5K   = 0x0C

CAN_BAUD_NAMES = {
    CAN_BAUD_1M:   "1 Mbps",
    CAN_BAUD_800K: "800 kbps",
    CAN_BAUD_500K: "500 kbps",
    CAN_BAUD_400K: "400 kbps",
    CAN_BAUD_250K: "250 kbps",
    CAN_BAUD_200K: "200 kbps",
    CAN_BAUD_125K: "125 kbps",
    CAN_BAUD_100K: "100 kbps",
    CAN_BAUD_50K:  "50 kbps",
    CAN_BAUD_20K:  "20 kbps",
    CAN_BAUD_10K:  "10 kbps",
    CAN_BAUD_5K:   "5 kbps",
}

# CAN Modes
CAN_MODE_NORMAL   = 0x00
CAN_MODE_SILENT   = 0x01
CAN_MODE_LOOPBACK = 0x02
CAN_MODE_SILENT_LOOPBACK = 0x03

CAN_MODE_NAMES = {
    CAN_MODE_NORMAL:          "Normal",
    CAN_MODE_SILENT:          "Silent",
    CAN_MODE_LOOPBACK:        "Loopback",
    CAN_MODE_SILENT_LOOPBACK: "Silent Loopback",
}

# Protocol constants
PACKET_HEADER = 0xAA
PACKET_END    = 0x55

# Frame type bits in the Type byte
TYPE_BASE          = 0xC0
TYPE_EXTENDED_BIT  = 0x20  # bit5: 1=extended, 0=standard
TYPE_REMOTE_BIT    = 0x10  # bit4: 1=remote, 0=data
TYPE_LENGTH_MASK   = 0x0F  # bit0-3: data length


@dataclass
class CANFrame:
    """Represents a CAN bus frame."""
    can_id: int
    data: bytes = b''
    is_extended: bool = False
    is_remote: bool = False
    timestamp: float = 0.0
    
    @property
    def dlc(self) -> int:
        return len(self.data)
    
    def __repr__(self):
        id_str = f"0x{self.can_id:08X}" if self.is_extended else f"0x{self.can_id:03X}"
        ext = "EXT" if self.is_extended else "STD"
        rtr = " RTR" if self.is_remote else ""
        data_hex = ' '.join(f'{b:02X}' for b in self.data)
        return f"CANFrame({ext}{rtr} ID={id_str} DLC={self.dlc} Data=[{data_hex}])"


class WaveshareCAN:
    """
    Driver for Waveshare USB-CAN-A adapter.
    
    Uses the variable-length serial protocol to send/receive CAN frames.
    The adapter communicates over a virtual serial port (CH340 chip) at
    2,000,000 baud by default.
    """
    
    def __init__(self):
        self.ser: Optional[serial.Serial] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._rx_running = False
        self._rx_callback: Optional[Callable[[CANFrame], None]] = None
        self._rx_buffer: List[CANFrame] = []
        self._rx_lock = threading.Lock()
        self._raw_buffer = bytearray()
        
    def open(self, port: str, serial_baud: int = 2000000, timeout: float = 0.1) -> bool:
        """
        Open connection to the Waveshare USB-CAN-A adapter.
        
        Args:
            port: Serial port path (e.g., '/dev/cu.wchusbserial110')
            serial_baud: Serial baud rate (default 2000000)
            timeout: Serial read timeout in seconds
            
        Returns:
            True if connection was successful
        """
        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=serial_baud,
                bytesize=serial.EIGHTBITS,
                stopbits=serial.STOPBITS_ONE,
                parity=serial.PARITY_NONE,
                timeout=timeout,
                write_timeout=1.0,
            )
            # Flush any stale data
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            time.sleep(0.1)
            print(f"✅ Opened {port} at {serial_baud} baud")
            return True
        except serial.SerialException as e:
            print(f"❌ Failed to open {port}: {e}")
            return False
    
    def close(self):
        """Close the serial connection and stop receive thread."""
        self.stop_receiving()
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("🔌 Serial port closed")
    
    def configure(self, 
                  can_baud: int = CAN_BAUD_500K,
                  frame_type: int = 0x01,  # 0x01=standard, 0x02=extended
                  mode: int = CAN_MODE_NORMAL,
                  filter_id: int = 0x00000000,
                  mask_id: int = 0x00000000,
                  auto_retransmit: bool = True,
                  use_variable_protocol: bool = True) -> bool:
        """
        Send CAN configuration command to the adapter.
        
        Args:
            can_baud: CAN bus baud rate code (e.g., CAN_BAUD_500K)
            frame_type: 0x01 for standard frame, 0x02 for extended frame
            mode: CAN mode (normal, silent, loopback, etc.)
            filter_id: CAN filter ID (32-bit)
            mask_id: CAN mask ID (32-bit)
            auto_retransmit: Enable automatic message retransmission
            use_variable_protocol: True for variable-length, False for fixed 20-byte
            
        Returns:
            True if configuration was sent successfully
        """
        if not self.ser or not self.ser.is_open:
            print("❌ Serial port not open")
            return False
        
        # Build the 20-byte configuration command
        cmd = bytearray(20)
        cmd[0] = 0xAA  # Header 1
        cmd[1] = 0x55  # Header 2
        cmd[2] = 0x12 if use_variable_protocol else 0x02  # Type
        cmd[3] = can_baud  # CAN baud rate
        cmd[4] = frame_type  # Frame type
        
        # Filter ID (big-endian per protocol docs)
        cmd[5] = (filter_id >> 0) & 0xFF
        cmd[6] = (filter_id >> 8) & 0xFF
        cmd[7] = (filter_id >> 16) & 0xFF
        cmd[8] = (filter_id >> 24) & 0xFF
        
        # Mask ID (big-endian per protocol docs)
        cmd[9]  = (mask_id >> 0) & 0xFF
        cmd[10] = (mask_id >> 8) & 0xFF
        cmd[11] = (mask_id >> 16) & 0xFF
        cmd[12] = (mask_id >> 24) & 0xFF
        
        cmd[13] = mode  # CAN mode
        cmd[14] = 0x00 if auto_retransmit else 0x01  # Auto retransmit
        cmd[15] = 0x00  # Reserved
        cmd[16] = 0x00  # Reserved
        cmd[17] = 0x00  # Reserved
        cmd[18] = 0x00  # Reserved
        
        # Checksum: low 8 bits of sum from byte 2 to byte 18
        checksum = sum(cmd[2:19]) & 0xFF
        cmd[19] = checksum
        
        try:
            self.ser.write(bytes(cmd))
            self.ser.flush()
            baud_name = CAN_BAUD_NAMES.get(can_baud, f"0x{can_baud:02X}")
            mode_name = CAN_MODE_NAMES.get(mode, f"0x{mode:02X}")
            proto = "Variable-length" if use_variable_protocol else "Fixed 20-byte"
            print(f"⚙️  Configured: CAN Baud={baud_name}, Mode={mode_name}, Protocol={proto}")
            time.sleep(0.2)  # Give adapter time to apply config
            # Flush any response
            self.ser.reset_input_buffer()
            return True
        except serial.SerialException as e:
            print(f"❌ Configuration failed: {e}")
            return False
    
    def send_frame(self, frame: CANFrame) -> bool:
        """
        Send a CAN frame via the variable-length protocol.
        
        Protocol format:
          [0xAA] [Type] [Frame ID (2 or 4 bytes, little-endian)] [Data 0-8 bytes] [0x55]
        
        Args:
            frame: CANFrame to send
            
        Returns:
            True if the frame was sent successfully
        """
        if not self.ser or not self.ser.is_open:
            print("❌ Serial port not open")
            return False
        
        # Build type byte
        type_byte = TYPE_BASE
        if frame.is_extended:
            type_byte |= TYPE_EXTENDED_BIT
        if frame.is_remote:
            type_byte |= TYPE_REMOTE_BIT
        type_byte |= (frame.dlc & TYPE_LENGTH_MASK)
        
        # Build packet
        packet = bytearray()
        packet.append(PACKET_HEADER)  # 0xAA
        packet.append(type_byte)
        
        # Frame ID in little-endian
        if frame.is_extended:
            packet.extend(frame.can_id.to_bytes(4, 'little'))
        else:
            packet.extend((frame.can_id & 0x7FF).to_bytes(2, 'little'))
        
        # Frame data
        packet.extend(frame.data[:8])
        
        # End code
        packet.append(PACKET_END)  # 0x55
        
        try:
            self.ser.write(bytes(packet))
            self.ser.flush()
            return True
        except serial.SerialException as e:
            print(f"❌ Send failed: {e}")
            return False
    
    def send(self, can_id: int, data: bytes, extended: bool = False) -> bool:
        """
        Convenience method to send a CAN frame.
        
        Args:
            can_id: CAN frame ID
            data: Frame data (0-8 bytes)
            extended: True for extended (29-bit) frame
            
        Returns:
            True if sent successfully
        """
        frame = CANFrame(can_id=can_id, data=data, is_extended=extended)
        return self.send_frame(frame)
    
    def _parse_frames(self, raw: bytearray) -> List[CANFrame]:
        """
        Parse received serial data into CAN frames using variable-length protocol.
        
        Returns:
            List of parsed CANFrame objects
        """
        frames = []
        i = 0
        
        while i < len(raw):
            # Look for packet header 0xAA
            if raw[i] != PACKET_HEADER:
                i += 1
                continue
            
            # Need at least header + type byte
            if i + 1 >= len(raw):
                break
                
            type_byte = raw[i + 1]
            
            # Check if this looks like a valid type byte (should have 0xC0 or 0xE0 base)
            if (type_byte & 0xC0) != 0xC0:
                i += 1
                continue
            
            is_extended = bool(type_byte & TYPE_EXTENDED_BIT)
            is_remote = bool(type_byte & TYPE_REMOTE_BIT)
            data_len = type_byte & TYPE_LENGTH_MASK
            
            if data_len > 8:
                i += 1
                continue
            
            # Calculate expected packet length
            id_len = 4 if is_extended else 2
            packet_len = 1 + 1 + id_len + data_len + 1  # header + type + id + data + end
            
            if i + packet_len > len(raw):
                break  # Incomplete packet, wait for more data
            
            # Check end byte
            if raw[i + packet_len - 1] != PACKET_END:
                i += 1
                continue
            
            # Parse frame ID (little-endian)
            id_start = i + 2
            if is_extended:
                can_id = int.from_bytes(raw[id_start:id_start + 4], 'little')
            else:
                can_id = int.from_bytes(raw[id_start:id_start + 2], 'little')
            
            # Parse data
            data_start = id_start + id_len
            data = bytes(raw[data_start:data_start + data_len])
            
            frame = CANFrame(
                can_id=can_id,
                data=data,
                is_extended=is_extended,
                is_remote=is_remote,
                timestamp=time.time()
            )
            frames.append(frame)
            
            i += packet_len
        
        # Keep unparsed data in buffer
        if i < len(raw):
            self._raw_buffer = raw[i:]
        else:
            self._raw_buffer = bytearray()
        
        return frames
    
    def receive(self, timeout: float = 0.5) -> List[CANFrame]:
        """
        Receive CAN frames (blocking with timeout).
        
        Args:
            timeout: Maximum time to wait for data in seconds
            
        Returns:
            List of received CANFrame objects
        """
        if not self.ser or not self.ser.is_open:
            return []
        
        start = time.time()
        while time.time() - start < timeout:
            data = self.ser.read(self.ser.in_waiting or 1)
            if data:
                self._raw_buffer.extend(data)
                frames = self._parse_frames(self._raw_buffer)
                if frames:
                    return frames
        
        return []
    
    def start_receiving(self, callback: Optional[Callable[[CANFrame], None]] = None):
        """
        Start background thread to continuously receive CAN frames.
        
        Args:
            callback: Optional callback function called for each received frame
        """
        self._rx_callback = callback
        self._rx_running = True
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()
        print("📡 Started CAN receive thread")
    
    def stop_receiving(self):
        """Stop the background receive thread."""
        self._rx_running = False
        if self._rx_thread:
            self._rx_thread.join(timeout=2.0)
            self._rx_thread = None
    
    def _rx_loop(self):
        """Background receive loop."""
        while self._rx_running:
            try:
                if self.ser and self.ser.is_open:
                    data = self.ser.read(self.ser.in_waiting or 1)
                    if data:
                        self._raw_buffer.extend(data)
                        frames = self._parse_frames(self._raw_buffer)
                        for frame in frames:
                            if self._rx_callback:
                                self._rx_callback(frame)
                            with self._rx_lock:
                                self._rx_buffer.append(frame)
                                # Keep buffer manageable
                                if len(self._rx_buffer) > 1000:
                                    self._rx_buffer = self._rx_buffer[-500:]
            except serial.SerialException:
                break
            except Exception as e:
                print(f"RX Error: {e}")
                time.sleep(0.01)
    
    def get_received_frames(self) -> List[CANFrame]:
        """Get all frames from the receive buffer and clear it."""
        with self._rx_lock:
            frames = list(self._rx_buffer)
            self._rx_buffer.clear()
        return frames
    
    def loopback_test(self) -> bool:
        """
        Perform a loopback test to verify the adapter is working.
        Configures the adapter in loopback mode, sends a test frame,
        and checks if it's received back.
        
        Returns:
            True if loopback test passed
        """
        print("\n🔄 Running loopback test...")
        
        # Configure for loopback mode
        self.configure(
            can_baud=CAN_BAUD_500K,
            mode=CAN_MODE_LOOPBACK,
            use_variable_protocol=True
        )
        time.sleep(0.3)
        
        # Send a test frame
        test_data = bytes([0xDE, 0xAD, 0xBE, 0xEF, 0xCA, 0xFE, 0x01, 0x02])
        test_id = 0x7FF
        
        print(f"  📤 Sending test frame: ID=0x{test_id:03X} Data={test_data.hex().upper()}")
        self.send(test_id, test_data)
        
        # Try to receive
        time.sleep(0.2)
        frames = self.receive(timeout=1.0)
        
        if frames:
            for f in frames:
                print(f"  📥 Received: {f}")
                if f.can_id == test_id and f.data == test_data:
                    print("  ✅ Loopback test PASSED!")
                    return True
        
        print("  ⚠️  Loopback test - no matching frame received")
        print("     (This may be normal if adapter doesn't echo in variable protocol)")
        return False


def detect_adapter() -> Optional[str]:
    """
    Auto-detect the Waveshare USB-CAN-A adapter on macOS.
    
    Returns:
        Serial port path if found, None otherwise
    """
    import glob
    
    # Common CH340/CH341 serial port patterns on macOS
    patterns = [
        '/dev/cu.wchusbserial*',
        '/dev/cu.usbserial*',
        '/dev/tty.wchusbserial*',
        '/dev/tty.usbserial*',
    ]
    
    found_ports = []
    for pattern in patterns:
        found_ports.extend(glob.glob(pattern))
    
    if not found_ports:
        print("❌ No USB-CAN adapter detected!")
        print("   Make sure the Waveshare USB-CAN-A is plugged in")
        print("   and the CH340 driver is installed.")
        return None
    
    # Prefer cu. over tty. (cu. doesn't block on carrier detect)
    cu_ports = [p for p in found_ports if '/dev/cu.' in p]
    if cu_ports:
        port = cu_ports[0]
    else:
        port = found_ports[0]
    
    print(f"🔍 Detected adapter at: {port}")
    return port


if __name__ == "__main__":
    print("=" * 60)
    print("  Waveshare USB-CAN-A Adapter Test")
    print("=" * 60)
    
    # Detect adapter
    port = detect_adapter()
    if not port:
        exit(1)
    
    # Open connection
    adapter = WaveshareCAN()
    if not adapter.open(port):
        exit(1)
    
    # Run loopback test
    adapter.loopback_test()
    
    # Configure for normal mode at 500kbps (X6 Plus default)
    print("\n⚙️  Configuring for normal mode at 500kbps...")
    adapter.configure(
        can_baud=CAN_BAUD_500K,
        mode=CAN_MODE_NORMAL,
        use_variable_protocol=True
    )
    
    # Listen for any CAN traffic for 3 seconds
    print("\n📡 Listening for CAN traffic (3 seconds)...")
    start = time.time()
    frame_count = 0
    while time.time() - start < 3.0:
        frames = adapter.receive(timeout=0.5)
        for f in frames:
            print(f"  📥 {f}")
            frame_count += 1
    
    if frame_count == 0:
        print("  (No CAN traffic detected)")
    else:
        print(f"  Received {frame_count} frames")
    
    adapter.close()
    print("\n✅ Test complete!")
