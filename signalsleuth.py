#!/usr/bin/env python3
"""
SignalSleuth v2.0 — UMIK-1 Acoustic Forensics Toolkit
====================================================

A real-time spectral analysis tool for detecting, documenting, and
forensically logging acoustic anomalies in indoor environments.

Designed for use with the miniDSP UMIK-1 calibrated measurement microphone.

Scientific Framework:
- Group 0: Ambient Acoustic Baseline (AAB) — inherent room sound field
- Group 1: Primary Injected Signal (PIS) — non-ambient, localized sound energy
- Group 2: Secondary Artifacts & Distortion Products (SADP) — spectral
  components temporally correlated with PIS (intermodulation, harmonics,
  or ultrasonic carrier demodulation if hardware supports >48kHz sampling)

Author: SignalSleuth Project
License: MIT
"""

import os
import sys
import time
import hashlib
import json
import csv
import wave
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional, Dict
from threading import Lock

import sounddevice as sd
import numpy as np
import scipy.signal as signal
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.patches import Rectangle

# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class Config:
    """Runtime configuration for SignalSleuth."""
    # Hardware
    sample_rate: int = 48000          # UMIK-1 hardware limit (upgrade to 96000/192000 for ultrasonic)
    chunk_size: int = 4096            # FFT window size (power of 2 recommended)
    device_index: Optional[int] = None  # Auto-detect if None

    # UMIK-1 Calibration
    calibration_file: Optional[str] = None  # Path to miniDSP .txt calibration file
    umik_sensitivity_dbfs: float = -18.0    # dBFS @ 94 dB SPL @ 1kHz (check your UMIK-1 certificate)

    # Detection Thresholds
    db_threshold: float = 15.0        # dB above median noise floor for peak detection
    min_peak_distance_hz: float = 50.0  # Minimum Hz separation between peaks
    spl_threshold: float = 50.0       # Absolute SPL threshold for anomaly logging (dB re 20 µPa)

    # Frequency Zones (Hz)
    zone_ambient_max: float = 2000.0
    zone_primary_max: float = 12000.0
    zone_artifact_max: float = 24000.0  # Nyquist limit at 48kHz

    # Logging
    log_dir: str = "./forensic_logs"
    log_interval_sec: float = 1.0     # Minimum seconds between CSV log entries for same peak
    wav_trigger_spl: float = 60.0   # SPL threshold to trigger WAV recording
    wav_duration_sec: float = 5.0   # Duration of triggered WAV capture

    # Display
    y_min_db: float = -40.0
    y_max_db: float = 100.0
    update_interval_ms: int = 50    # Matplotlib animation interval


# =============================================================================
# UMIK-1 CALIBRATION LOADER
# =============================================================================

def load_umik_calibration(filepath: str, sample_rate: int, fft_size: int) -> Optional[np.ndarray]:
    """
    Load a miniDSP UMIK-1 calibration file (.txt format).

    File format: Frequency(Hz) SPL(dB) Phase(degrees)
    Returns an interpolation array matching FFT frequency bins.
    """
    freqs = []
    gains = []

    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('*') or line.startswith('Freq'):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    freqs.append(float(parts[0]))
                    gains.append(float(parts[1]))
    except Exception as e:
        print(f"[WARN] Could not load calibration file: {e}")
        return None

    if len(freqs) < 2:
        return None

    # Interpolate to FFT frequency bins
    fft_freqs = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)
    cal_interp = np.interp(fft_freqs, freqs, gains, left=gains[0], right=gains[-1])

    print(f"[INFO] Loaded calibration: {filepath} ({len(freqs)} points)")
    return cal_interp


# =============================================================================
# FORENSIC LOGGING SYSTEM
# =============================================================================

class ForensicLogger:
    """
    Handles timestamped, hashed forensic data logging.
    Produces: CSV peak log, JSON metadata, triggered WAV recordings.
    """

    def __init__(self, config: Config):
        self.config = config
        self.session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.log_dir = Path(config.log_dir) / self.session_id
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # CSV setup
        self.csv_path = self.log_dir / "peak_log.csv"
        self.csv_file = open(self.csv_path, 'w', newline='')
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow([
            'timestamp_iso', 'timestamp_unix', 'frequency_hz', 'magnitude_dbfs',
            'spl_db', 'zone', 'peak_type', 'session_id', 'file_hash'
        ])

        # Metadata
        self.metadata = {
            'session_id': self.session_id,
            'start_time_iso': datetime.now(timezone.utc).isoformat(),
            'config': asdict(config),
            'hardware': self._detect_hardware(),
            'software_version': '2.0.0',
            'calibration_applied': config.calibration_file is not None,
        }

        # Peak deduplication (freq ± 5Hz within log_interval)
        self._last_logged: Dict[str, float] = {}
        self._lock = Lock()

        # WAV recording state
        self._wav_buffer: List[np.ndarray] = []
        self._recording = False
        self._record_start_time = 0.0

        print(f"[INFO] Forensic session: {self.session_id}")
        print(f"[INFO] Log directory: {self.log_dir.resolve()}")

    def _detect_hardware(self) -> dict:
        """Detect audio hardware info."""
        try:
            info = sd.query_devices(kind='input')
            return {
                'name': info['name'],
                'channels': info['max_input_channels'],
                'sample_rate': info['default_samplerate'],
                'device_index': info['index']
            }
        except Exception as e:
            return {'error': str(e)}

    def log_peak(self, freq_hz: float, mag_dbfs: float, spl_db: float, zone: str, 
                 peak_type: str = "narrowband") -> bool:
        """Log a detected peak with deduplication and hashing."""

        # Deduplication key: rounded frequency
        key = f"{round(freq_hz / 5.0) * 5.0:.0f}_{zone}"
        now = time.time()

        with self._lock:
            if key in self._last_logged:
                if now - self._last_logged[key] < self.config.log_interval_sec:
                    return False
            self._last_logged[key] = now

        timestamp_iso = datetime.now(timezone.utc).isoformat()
        timestamp_unix = time.time()

        # Create hash of the data row for integrity
        row_data = f"{timestamp_iso}{freq_hz}{mag_dbfs}{spl_db}{zone}{peak_type}{self.session_id}"
        file_hash = hashlib.sha256(row_data.encode()).hexdigest()[:16]

        self.csv_writer.writerow([
            timestamp_iso, timestamp_unix, f"{freq_hz:.2f}", f"{mag_dbfs:.2f}",
            f"{spl_db:.2f}", zone, peak_type, self.session_id, file_hash
        ])
        self.csv_file.flush()

        print(f"[LOG] {zone} | {freq_hz:.1f} Hz | {spl_db:.1f} dB SPL | {peak_type}")
        return True

    def start_wav_recording(self, audio_buffer: np.ndarray):
        """Start a triggered WAV recording."""
        if self._recording:
            return
        self._recording = True
        self._record_start_time = time.time()
        self._wav_buffer = [audio_buffer.copy()]
        print(f"[REC] WAV recording triggered (threshold: {self.config.wav_trigger_spl} dB SPL)")

    def append_wav(self, audio_buffer: np.ndarray):
        """Append audio to ongoing WAV recording."""
        if not self._recording:
            return
        self._wav_buffer.append(audio_buffer.copy())

        # Check if duration exceeded
        elapsed = time.time() - self._record_start_time
        if elapsed >= self.config.wav_duration_sec:
            self._save_wav()

    def _save_wav(self):
        """Save buffered audio to WAV file."""
        if not self._recording or not self._wav_buffer:
            return

        self._recording = False
        audio = np.concatenate(self._wav_buffer)

        # Normalize to 16-bit
        audio_norm = np.int16(audio / np.max(np.abs(audio)) * 32767)

        wav_path = self.log_dir / f"trigger_{datetime.now(timezone.utc).strftime('%H%M%S')}.wav"
        with wave.open(str(wav_path), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.config.sample_rate)
            wf.writeframes(audio_norm.tobytes())

        # Hash the WAV
        with open(wav_path, 'rb') as f:
            wav_hash = hashlib.sha256(f.read()).hexdigest()[:16]

        print(f"[REC] Saved: {wav_path.name} (SHA256: {wav_hash})")
        self._wav_buffer = []

    def save_metadata(self):
        """Save session metadata JSON."""
        self.metadata['end_time_iso'] = datetime.now(timezone.utc).isoformat()
        self.metadata['total_duration_sec'] = time.time() -             datetime.fromisoformat(self.metadata['start_time_iso'].replace('Z', '+00:00')).timestamp()

        meta_path = self.log_dir / "metadata.json"
        with open(meta_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)
        print(f"[INFO] Metadata saved: {meta_path.name}")

    def close(self):
        """Clean up resources."""
        if self._recording:
            self._save_wav()
        self.save_metadata()
        self.csv_file.close()
        print(f"[INFO] Session closed. All logs in: {self.log_dir.resolve()}")


# =============================================================================
# SIGNAL PROCESSING ENGINE
# =============================================================================

class SignalProcessor:
    """
    Handles FFT computation, calibration correction, SPL conversion,
    peak detection, and zone classification.
    """

    def __init__(self, config: Config, calibration: Optional[np.ndarray] = None):
        self.config = config
        self.calibration = calibration

        # Precompute FFT parameters
        self.xf = np.fft.rfftfreq(config.chunk_size, 1.0 / config.sample_rate)
        self.window = np.hanning(config.chunk_size)

        # Reference for SPL: UMIK-1 sensitivity
        # Sensitivity: -18 dBFS = 94 dB SPL @ 1kHz
        # dB SPL = dBFS - sensitivity + 94
        self.spl_offset = 94.0 - config.umik_sensitivity_dbfs

        # Background subtraction buffer
        self._ambient_spectrum: Optional[np.ndarray] = None
        self._ambient_count = 0
        self._ambient_target = 60  # Frames to average for ambient fingerprint

    def compute_fft(self, audio_data: np.ndarray) -> np.ndarray:
        """Compute calibrated FFT magnitude in dB."""
        windowed = audio_data * self.window
        yf = np.fft.rfft(windowed)
        magnitude = np.abs(yf)

        # Apply calibration if available
        if self.calibration is not None:
            # Calibration file gives deviation from flat; add to compensate
            magnitude *= 10 ** (self.calibration / 20.0)

        # Convert to dB (relative)
        magnitude_db = 20 * np.log10(magnitude + 1e-10)
        return magnitude_db

    def dbfs_to_spl(self, dbfs: float) -> float:
        """Convert relative dBFS to absolute dB SPL."""
        return dbfs + self.spl_offset

    def detect_peaks(self, magnitude_db: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Detect spectral peaks above the dynamic noise floor.

        Returns:
            peaks: indices of detected peaks
            properties: scipy peak properties dict
        """
        median_floor = np.median(magnitude_db)

        # Convert distance from Hz to samples
        freq_resolution = self.config.sample_rate / self.config.chunk_size
        min_distance_samples = int(self.config.min_peak_distance_hz / freq_resolution)

        peaks, properties = signal.find_peaks(
            magnitude_db,
            height=median_floor + self.config.db_threshold,
            distance=max(min_distance_samples, 10),
            prominence=self.config.db_threshold * 0.5
        )
        return peaks, properties

    def classify_zone(self, freq_hz: float) -> str:
        """Classify frequency into acoustic zone."""
        if freq_hz <= self.config.zone_ambient_max:
            return "AAB"  # Ambient Acoustic Baseline
        elif freq_hz <= self.config.zone_primary_max:
            return "PIS"  # Primary Injected Signal
        else:
            return "SADP"  # Secondary Artifacts & Distortion Products

    def capture_ambient_fingerprint(self, magnitude_db: np.ndarray) -> bool:
        """Capture and average ambient spectrum for background subtraction."""
        if self._ambient_spectrum is None:
            self._ambient_spectrum = magnitude_db.copy()
        else:
            self._ambient_spectrum = (self._ambient_spectrum * self._ambient_count + magnitude_db) /                                      (self._ambient_count + 1)

        self._ambient_count += 1
        return self._ambient_count >= self._ambient_target

    def subtract_ambient(self, magnitude_db: np.ndarray) -> np.ndarray:
        """Subtract ambient fingerprint from current spectrum."""
        if self._ambient_spectrum is None:
            return magnitude_db
        return magnitude_db - self._ambient_spectrum


# =============================================================================
# MAIN APPLICATION
# =============================================================================

class SignalSleuth:
    """Main application controller."""

    def __init__(self):
        self.config = Config()

        # Load calibration if available
        self.calibration = None
        if self.config.calibration_file and os.path.exists(self.config.calibration_file):
            self.calibration = load_umik_calibration(
                self.config.calibration_file,
                self.config.sample_rate,
                self.config.chunk_size
            )
        else:
            print("[WARN] No calibration file loaded. Measurements are relative, not absolute SPL.")
            print("[WARN] For legal admissibility, provide UMIK-1 .txt calibration file.")

        # Initialize subsystems
        self.processor = SignalProcessor(self.config, self.calibration)
        self.logger = ForensicLogger(self.config)

        # Thread-safe audio buffer
        self.audio_data = np.zeros(self.config.chunk_size)
        self.audio_lock = Lock()
        self._ambient_captured = False

        # Setup matplotlib
        self._setup_plot()
        self._setup_audio()

    def _setup_plot(self):
        """Initialize the real-time visualization."""
        self.fig, self.ax = plt.subplots(figsize=(14, 7))
        self.fig.canvas.manager.set_window_title('SignalSleuth v2.0 — Acoustic Forensics')

        # Main spectrum line
        self.line, = self.ax.semilogx(
            self.processor.xf, np.zeros(len(self.processor.xf)),
            color='cyan', lw=1.5, label="Live Spectrum (dB FS)"
        )

        # Ambient-subtracted line (optional display)
        self.diff_line, = self.ax.semilogx(
            self.processor.xf, np.zeros(len(self.processor.xf)),
            color='yellow', lw=1.0, alpha=0.6, label="Ambient-Subtracted"
        )

        # Peak markers by zone
        self.peaks_aab, = self.ax.plot([], [], 'o', color='gray', markersize=6, label="AAB Peaks")
        self.peaks_pis, = self.ax.plot([], [], 'rx', markersize=8, label="PIS Anomalies")
        self.peaks_sadp, = self.ax.plot([], [], 'm^', markersize=8, label="SADP Artifacts")

        # Zone highlighting
        self.ax.axvspan(20, self.config.zone_ambient_max, color='gray', alpha=0.15,
                        label='Zone 0: Ambient Acoustic Baseline')
        self.ax.axvspan(self.config.zone_ambient_max, self.config.zone_primary_max,
                        color='blue', alpha=0.08,
                        label='Zone 1: Primary Injected Signal (PIS)')
        self.ax.axvspan(self.config.zone_primary_max, self.config.zone_artifact_max,
                        color='red', alpha=0.08,
                        label='Zone 2: Secondary Artifacts & Distortion Products (SADP)')

        # Formatting
        self.ax.set_xlim(20, self.config.zone_artifact_max)
        self.ax.set_ylim(self.config.y_min_db, self.config.y_max_db)
        self.ax.set_title(
            "SignalSleuth v2.0 — Real-Time Layered Acoustic Anomaly Detection\n"
            "Press 'A' to capture ambient fingerprint | 'Q' to quit",
            fontsize=12
        )
        self.ax.set_xlabel("Frequency (Hz) — Log Scale", fontsize=11)
        self.ax.set_ylabel("Magnitude (dB FS / Relative)", fontsize=11)
        self.ax.grid(True, which="both", ls="--", alpha=0.4)
        self.ax.legend(loc='upper right', fontsize=8)

        # Status text
        self.status_text = self.ax.text(
            0.02, 0.98, "Status: Running | Ambient: Not captured",
            transform=self.ax.transAxes, fontsize=9, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='black', alpha=0.7, edgecolor='white'),
            color='white', family='monospace'
        )

        # Keyboard handler
        self.fig.canvas.mpl_connect('key_press_event', self._on_key)

    def _setup_audio(self):
        """Initialize the audio stream."""
        try:
            self.stream = sd.InputStream(
                samplerate=self.config.sample_rate,
                blocksize=self.config.chunk_size,
                device=self.config.device_index,
                channels=1,
                dtype='float32',
                callback=self._audio_callback
            )
        except Exception as e:
            print(f"[FATAL] Audio stream initialization failed: {e}")
            print("[FATAL] Available devices:")
            print(sd.query_devices())
            sys.exit(1)

    def _audio_callback(self, indata, frames, time_info, status):
        """Audio callback — called on separate thread."""
        if status:
            print(f"[AUDIO STATUS] {status}")
        with self.audio_lock:
            self.audio_data = indata[:, 0].copy()

    def _on_key(self, event):
        """Handle keyboard commands."""
        if event.key.lower() == 'a':
            self._ambient_captured = False
            self.processor._ambient_spectrum = None
            self.processor._ambient_count = 0
            print("[CMD] Ambient fingerprint capture restarted. Hold still for ~3 seconds...")
        elif event.key.lower() == 'q':
            plt.close(self.fig)

    def update_plot(self, frame):
        """Main animation update function — called by FuncAnimation."""
        with self.audio_lock:
            data = self.audio_data.copy()

        # Compute spectrum
        magnitude_db = self.processor.compute_fft(data)

        # Ambient capture logic
        if not self._ambient_captured:
            done = self.processor.capture_ambient_fingerprint(magnitude_db)
            if done:
                self._ambient_captured = True
                print("[INFO] Ambient fingerprint captured (60 frames averaged).")

        # Subtract ambient for display
        diff_db = self.processor.subtract_ambient(magnitude_db)

        # Detect peaks on original spectrum (not subtracted, to preserve absolute levels)
        peaks, properties = self.processor.detect_peaks(magnitude_db)

        # Categorize peaks
        aab_freqs, aab_mags = [], []
        pis_freqs, pis_mags = [], []
        sadp_freqs, sadp_mags = [], []

        max_spl = -np.inf

        for peak in peaks:
            freq = self.processor.xf[peak]
            mag = magnitude_db[peak]
            spl = self.processor.dbfs_to_spl(mag)
            zone = self.processor.classify_zone(freq)

            if spl > max_spl:
                max_spl = spl

            # Log significant peaks
            if spl > self.config.spl_threshold:
                self.logger.log_peak(freq, mag, spl, zone)

            # Categorize for display
            if zone == "AAB":
                aab_freqs.append(freq)
                aab_mags.append(mag)
            elif zone == "PIS":
                pis_freqs.append(freq)
                pis_mags.append(mag)
            else:
                sadp_freqs.append(freq)
                sadp_mags.append(mag)

        # Trigger WAV recording if SPL exceeds threshold
        if max_spl > self.config.wav_trigger_spl:
            if not self.logger._recording:
                self.logger.start_wav_recording(data)

        if self.logger._recording:
            self.logger.append_wav(data)

        # Update plot lines
        self.line.set_ydata(magnitude_db)
        self.diff_line.set_ydata(diff_db)

        self.peaks_aab.set_data(aab_freqs, aab_mags)
        self.peaks_pis.set_data(pis_freqs, pis_mags)
        self.peaks_sadp.set_data(sadp_freqs, sadp_mags)

        # Update status
        ambient_status = "Captured" if self._ambient_captured else "Capturing..."
        self.status_text.set_text(
            f"Status: Running | Ambient: {ambient_status}\n"
            f"Peaks: AAB={len(aab_freqs)} PIS={len(pis_freqs)} SADP={len(sadp_freqs)} | "
            f"Max SPL: {max_spl:.1f} dB"
        )

        return self.line, self.diff_line, self.peaks_aab, self.peaks_pis, self.peaks_sadp, self.status_text

    def run(self):
        """Start the application."""
        print("=" * 60)
        print("SignalSleuth v2.0 — Acoustic Forensics Toolkit")
        print("=" * 60)
        print(f"Sample Rate: {self.config.sample_rate} Hz")
        print(f"FFT Size: {self.config.chunk_size} ({self.config.chunk_size / self.config.sample_rate * 1000:.1f} ms window)")
        print(f"Frequency Resolution: {self.config.sample_rate / self.config.chunk_size:.1f} Hz/bin")
        print(f"SPL Offset (UMIK-1): {self.processor.spl_offset:.1f} dB")
        print(f"Log Directory: {self.logger.log_dir.resolve()}")
        print("=" * 60)
        print("Controls:")
        print("  'A' — Capture/reset ambient fingerprint")
        print("  'Q' — Quit")
        print("=" * 60)

        self.stream.start()

        ani = animation.FuncAnimation(
            self.fig, self.update_plot,
            interval=self.config.update_interval_ms,
            blit=True,
            cache_frame_data=False
        )

        try:
            plt.show()
        except KeyboardInterrupt:
            pass
        finally:
            self.stream.stop()
            self.stream.close()
            self.logger.close()
            print("[INFO] SignalSleuth terminated cleanly.")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    app = SignalSleuth()
    app.run()
