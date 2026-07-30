#!/usr/bin/env python3
"""
Waveshare CAN → DroneCAN Driver Bridge
=======================================
Custom dronecan driver that wraps the Waveshare USB-CAN-A adapter
so we can use dronecan.make_node() with full protocol support.
"""

import time
import threading
import queue

from dronecan.driver.common import AbstractDriver, CANFrame, DriverError

from waveshare_can import (
    WaveshareCAN, detect_adapter,
    CAN_BAUD_500K, CAN_MODE_NORMAL,
    CANFrame as WsFrame
)


class WaveshareDriver(AbstractDriver):
    """
    DroneCAN-compatible driver wrapping the Waveshare USB-CAN-A adapter.
    """
    
    def __init__(self, device_name=None, bitrate=500000, **kwargs):
        super().__init__()
        self._ws = WaveshareCAN()
        self._rx_queue = queue.Queue(maxsize=4096)
        self._running = False
        self._rx_thread = None
        
        # Detect and open
        port = device_name or detect_adapter()
        if not port:
            raise DriverError("No Waveshare adapter found")
        
        if not self._ws.open(port):
            raise DriverError(f"Failed to open {port}")
        
        # Map bitrate
        baud_map = {
            1000000: 0x01,  # CAN_BAUD_1M
            800000:  0x02,
            500000:  0x03,  # CAN_BAUD_500K
            400000:  0x04,
            250000:  0x05,
            200000:  0x06,
            125000:  0x07,
            100000:  0x08,
        }
        can_baud = baud_map.get(bitrate, CAN_BAUD_500K)
        
        self._ws.configure(
            can_baud=can_baud,
            frame_type=0x02,  # Extended
            mode=CAN_MODE_NORMAL,
            use_variable_protocol=True
        )
        time.sleep(0.3)
        
        # Start receiver thread
        self._running = True
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()
    
    def _rx_loop(self):
        """Background thread to receive CAN frames."""
        while self._running:
            try:
                frames = self._ws.receive(timeout=0.05)
                for f in frames:
                    cf = CANFrame(
                        id=f.can_id,
                        data=f.data,
                        extended=f.is_extended,
                        ts_monotonic=time.monotonic(),
                        ts_real=time.time()
                    )
                    try:
                        self._rx_queue.put_nowait(cf)
                    except queue.Full:
                        pass  # Drop oldest if full
                    
                    # Call hooks
                    self._call_hooks(self.FRAME_DIRECTION_INCOMING, cf)
            except Exception:
                if self._running:
                    time.sleep(0.01)
    
    def _call_hooks(self, direction, frame):
        """Call registered I/O hooks."""
        try:
            for hook in self._io_hooks:
                hook(direction, frame)
        except:
            pass
    
    @property
    def _io_hooks(self):
        return getattr(self, '_hooks_list', [])
    
    def add_io_hook(self, hook):
        if not hasattr(self, '_hooks_list'):
            self._hooks_list = []
        self._hooks_list.append(hook)
        
        class HookRemover:
            def __init__(self, hooks, hook):
                self._hooks = hooks
                self._hook = hook
            def remove(self):
                try:
                    self._hooks.remove(self._hook)
                except ValueError:
                    pass
            def __del__(self):
                pass
        
        return HookRemover(self._hooks_list, hook)
    
    def close(self):
        self._running = False
        if self._rx_thread:
            self._rx_thread.join(timeout=2.0)
        self._ws.close()
    
    def __del__(self):
        self.close()
    
    def receive(self, timeout=None):
        """Receive a single CAN frame."""
        try:
            return self._rx_queue.get(timeout=timeout or 0.001)
        except queue.Empty:
            return None
    
    def send(self, message_id, message, extended=False, canfd=False):
        """Send a CAN frame."""
        ws_frame = WsFrame(
            can_id=message_id,
            data=bytes(message),
            is_extended=extended
        )
        self._ws.send_frame(ws_frame)
        
        # Create frame for hooks
        cf = CANFrame(
            id=message_id,
            data=bytes(message),
            extended=extended,
            ts_monotonic=time.monotonic(),
            ts_real=time.time()
        )
        self._call_hooks(self.FRAME_DIRECTION_OUTGOING, cf)


# Allow dronecan.make_node to use this driver  
def make_waveshare_node(**kwargs):
    """Create a DroneCAN node using the Waveshare adapter."""
    import dronecan
    
    driver = WaveshareDriver(**kwargs)
    node = dronecan.make_node(
        None,  # device_name not needed since we provide driver
        node_id=kwargs.get('node_id', 10),
        _drv_override=driver
    )
    return node, driver
