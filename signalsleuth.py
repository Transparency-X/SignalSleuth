import sounddevice as sd
import numpy as np
import scipy.signal as signal
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# --- CONFIGURATION ---
SAMPLE_RATE = 48000  # UMIK-1 hardware limit
CHUNK_SIZE = 4096    # FFT Window size
DB_THRESHOLD = 15    # How many dB above the noise floor constitutes an "Artificial Peak"

# Create figure and axis for live plotting
fig, ax = plt.subplots(figsize=(12, 6))
fig.canvas.manager.set_window_title('SignalSleuth - Live Acoustic Forensics')

# Frequency array for the X-axis (up to the Nyquist limit: 24,000 Hz)
xf = np.fft.rfftfreq(CHUNK_SIZE, 1 / SAMPLE_RATE)

# Initialize plot line
line, = ax.semilogx(xf, np.zeros(len(xf)), color='cyan', lw=1.5, label="Live Spectrum")
peaks_scatter, = ax.plot([],[], 'rx', markersize=8, label="Artificial Narrowband Spikes (Group 1/2)")

# Format the Graph
ax.set_xlim(20, 24000)
ax.set_ylim(-40, 100) # Adjust based on your UMIK-1 gain settings
ax.set_title("Real-Time Spectrum: Layered Acoustic Anomaly Detection", fontsize=14)
ax.set_xlabel("Frequency (Hz) - Log Scale", fontsize=12)
ax.set_ylabel("Magnitude (Relative dB)", fontsize=12)
ax.grid(True, which="both", ls="--", alpha=0.5)

# --- ZONE HIGHLIGHTING (The Three Groups) ---
# Group 0: Natural Room/Ambient (0-2000 Hz)
ax.axvspan(20, 2000, color='gray', alpha=0.2, label='Ambient / HVAC Floor')
# Group 1: Primary Injected Audio / Speech range (2000 - 12000 Hz)
ax.axvspan(2000, 12000, color='blue', alpha=0.1, label='Group 1: Primary Injected Zone')
# Group 2: Piggybacked / Relay Artifacts (12000 - 24000 Hz)
ax.axvspan(12000, 24000, color='red', alpha=0.1, label='Group 2: High-Freq/Artifact Zone')

ax.legend(loc='upper right')

# Global variable to store audio data safely
audio_data = np.zeros(CHUNK_SIZE)

def audio_callback(indata, frames, time, status):
    """ Captures live audio from the UMIK-1 """
    global audio_data
    if status:
        print(status)
    # Get the mono channel
    audio_data = indata[:, 0]

def update_plot(frame):
    """ Calculates FFT and updates the graph continuously """
    global audio_data
    
    # Apply a Hanning window to smooth the FFT edges
    windowed_data = audio_data * np.hanning(len(audio_data))
    
    # Calculate Fast Fourier Transform (FFT)
    yf = np.fft.rfft(windowed_data)
    
    # Convert magnitude to Decibels (dB)
    # Adding a small offset to avoid log(0)
    magnitude_db = 20 * np.log10(np.abs(yf) + 1e-6)
    
    # --- PEAK DETECTION (Finding Group 1 & 2 Signals) ---
    # We calculate the median noise floor of the current data
    median_floor = np.median(magnitude_db)
    
    # Look for sharp spikes that are significantly above the ambient baseline
    # These are highly indicative of electronic relays, carrier artifacts, or digital injection
    peaks, _ = signal.find_peaks(magnitude_db, height=median_floor + DB_THRESHOLD, distance=50)
    
    # Update the live RTA line
    line.set_ydata(magnitude_db)
    
    # Update the red 'X' markers for detected anomalies
    if len(peaks) > 0:
        peaks_scatter.set_data(xf[peaks], magnitude_db[peaks])
    else:
        peaks_scatter.set_data([],
