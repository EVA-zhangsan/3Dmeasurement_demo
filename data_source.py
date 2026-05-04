import numpy as np
import threading
import time
from abc import ABC, abstractmethod
from queue import Queue


class DataSource(ABC):
    """Abstract base class for hardware communication (serial/TCP) or simulation."""

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def disconnect(self):
        pass

    @abstractmethod
    def is_connected(self):
        pass

    @abstractmethod
    def read_point(self):
        """Return a tuple (x, y, z) or None if no data available."""
        pass


class SimulatedDataSource(DataSource):
    """
    Simulated laser scan data generator.
    Generates random points with a groove pattern in the middle.
    Runs in background thread, outputs to queue.
    """

    def __init__(self, queue_obj, total_points=1000, x_range=(0, 50), y_range=(0, 50)):
        self.queue = queue_obj
        self.total_points = total_points
        self.x_range = x_range
        self.y_range = y_range
        self._running = False
        self._thread = None
        self._connected = False

    def connect(self):
        """Start the simulated data generation thread."""
        if self._connected:
            return
        self._connected = True
        self._running = True
        self._thread = threading.Thread(target=self._generate_loop, daemon=True)
        self._thread.start()

    def disconnect(self):
        """Stop the simulated data generation."""
        self._running = False
        self._connected = False
        if self._thread:
            self._thread.join(timeout=2)

    def is_connected(self):
        return self._connected

    def read_point(self):
        """Read one point from queue. Returns (x, y, z) or None."""
        try:
            return self.queue.get_nowait()
        except:
            return None

    def _generate_loop(self):
        """Background thread: emit gridded raster scan points (CNC-like).
        
        RASTER SCAN MODE (realistic CNC/parallel robot motion):
        - X, Y: Regular grid coordinates from meshgrid (not random)
        - Z: Laser displacement sensor height measurement
        
        Surface geometry:
        - Base height: 10 mm (Z₀ = 10)
        - Groove feature: 20 mm < X < 30 mm → Z decreases by 3 mm (Z = 7 mm)
        - Sensor noise: Gaussian white noise (σ = 0.1 mm)
        
        Grid resolution: sqrt(total_points) × sqrt(total_points)
        Scan order: Row-major (Y-inner loop, X-outer loop) to simulate line-by-line motion
        """
        # Calculate grid dimensions (square grid to fill total_points)
        grid_size = int(np.sqrt(self.total_points))
        actual_total = grid_size * grid_size
        
        # Generate regular grid using meshgrid (CNC raster scan pattern)
        x_grid = np.linspace(self.x_range[0], self.x_range[1], grid_size)
        y_grid = np.linspace(self.y_range[0], self.y_range[1], grid_size)
        X, Y = np.meshgrid(x_grid, y_grid)  # Shape: (grid_size, grid_size)
        
        # Flatten to 1D array for iteration (preserves row-major order)
        X_flat = X.flatten()
        Y_flat = Y.flatten()
        
        for idx in range(actual_total):
            if not self._running:
                break
            
            # Extract gridded coordinates (NOT random)
            x = X_flat[idx]
            y = Y_flat[idx]
            
            # Base surface height: 10 mm
            z = 10.0
            
            # Groove feature: X in (20, 30) mm reduces Z by 3 mm
            if 20 < x < 30:
                z -= 3.0  # Z = 7 mm in groove region
            
            # Add laser sensor measurement noise (Gaussian, σ = 0.1 mm)
            z += np.random.normal(0, 0.1)
            
            # Emit (X, Y, Z) physical coordinates
            self.queue.put((x, y, z))
            
            # Ultra-fast simulation (1 ms per point for real-time responsiveness)
            time.sleep(0.001)


class SerialDataSource(DataSource):
    """Placeholder for real hardware via serial (COM port)."""

    def __init__(self, port='COM1', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self._connected = False

    def connect(self):
        # TODO: Implement pySerial connection
        self._connected = True

    def disconnect(self):
        self._connected = False

    def is_connected(self):
        return self._connected

    def read_point(self):
        # TODO: Parse serial data
        return None


class TCPDataSource(DataSource):
    """Placeholder for real hardware via TCP/IP."""

    def __init__(self, host='127.0.0.1', port=5000):
        self.host = host
        self.port = port
        self._connected = False

    def connect(self):
        # TODO: Implement TCP connection
        self._connected = True

    def disconnect(self):
        self._connected = False

    def is_connected(self):
        return self._connected

    def read_point(self):
        # TODO: Parse TCP data
        return None
