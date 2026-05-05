# SignalSleuth: UMIK-1 Acoustic Forensics Toolkit

**SignalSleuth** is an open-source Python toolkit designed to detect, analyze, and mathematically document complex, continuous acoustic anomalies in indoor environments. 

Originally built for use with the **miniDSP UMIK-1** calibrated measurement microphone, this tool focuses on isolating multiple layers of sound when a clean "silent" baseline is unavailable. It actively looks for unnatural mathematical signatures—such as parametric audio artifacts, artificial narrowband spikes, and intermodulation distortion—to prove the presence of injected audio.

## 🎯 The Three-Layer Detection Model
This software categorizes real-time audio into three groups based on frequency behavior and acoustic physics:
1. **The Ambient Floor:** Broad, low-frequency sound (HVAC, building hum).
2. **Group 1 (Primary Injected Sound):** Artificial narrowband peaks, unnatural harmonics, or mid-range broadband anomalies.
3. **Group 2 (Piggybacked/Relay Artifacts):** High-frequency anomalies (15kHz - 24kHz) indicative of intermodulation distortion or the audible footprint of an ultrasonic carrier wave demodulating in the air.

## 🛠 Prerequisites
* **Hardware:** miniDSP UMIK-1 (or equivalent calibrated USB microphone).
* **Software:** Python 3.8+
* **Libraries:** `sounddevice`, `numpy`, `scipy`, `matplotlib`

## 🚀 Installation
1. Clone this repository: `git clone https://github.com/yourusername/SignalSleuth.git`
2. Install the required Python libraries:
   ```bash
   pip install sounddevice numpy scipy matplotlib
   ```
3. Plug in your UMIK-1 via USB.
4. Run the script: `python signalsleuth.py`


### 📋 Overview of Features (Current)

*   **Real-Time Spectroscopic Analysis (RTA):** Visualizes the continuous sound pressure level across the entire spectrum (0 Hz to 24 kHz) in real-time.
*   **Algorithmic Peak Detection:** Automatically scans the FFT (Fast Fourier Transform) array for mathematically perfect, constant frequencies (narrowband spikes) that indicate electronic or relayed transducers, drawing a red 'X' over them.
*   **Zoned Frequency Highlighting:** Color-codes the graph to help the user visually separate Natural Ambient (0-2kHz), Primary Injected Audio (2-12kHz), and High-Frequency Carrier Artifacts (12-24kHz).
*   **Median Noise Floor Tracking:** Calculates a rolling mathematical median to establish a dynamic baseline, allowing the script to find anomalies even when the sound never stops.

### 🗺 Roadmap of Future Features

*   **[v1.2] Phase-Cancellation Module:** Allow users to record a clean sample of Group 1, invert its phase, and play it back to mathematically cancel it out and reveal Group 2.
*   **[v1.5] Acoustic Shadowing / Differential Mode:** A feature to record "Position A" and subtract it from "Position B" in real-time to instantly map highly directional audio beams.
*   **[v2.0] High-Sample-Rate Demodulation (UMIK-2 Support):** Upgrade digital signal processing limits to 192kHz to actively view and demodulate 40kHz-96kHz ultrasonic carrier waves used in parametric speakers.
*   **[v2.5] Comb-Filter Fingerprinting:** Implement an algorithm to automatically detect mathematical "V" shape patterns indicative of continuous localized audio bouncing off a specific wall.
