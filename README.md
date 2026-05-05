# SignalSleuth v2.0: UMIK-1 Acoustic Forensics Toolkit

**SignalSleuth** is an open-source Python toolkit for the real-time detection, spectral analysis, and forensic documentation of acoustic anomalies in indoor environments. It is designed for rigorous, evidence-based investigation where a clean "silent" baseline is unavailable.

Originally built for the **miniDSP UMIK-1** calibrated measurement microphone, the tool implements a three-layer detection model grounded in acoustic physics. It isolates distinct spectral categories, applies factory calibration corrections for absolute SPL measurement, and produces timestamped, hashed forensic logs suitable for chain-of-custody requirements.

> **⚠️ Forensic Disclaimer:** SignalSleuth detects *anomalies* — statistical deviations from an established baseline. It does not prove intent, identify specific devices, or confirm the presence of illegal surveillance. All findings must be corroborated by additional evidence and expert analysis.

---

## 🎯 The Three-Layer Detection Model

SignalSleuth categorizes real-time acoustic energy into three scientifically defined groups based on spectral behavior, temporal correlation, and spatial localization:

### Zone 0: Ambient Acoustic Baseline (AAB)
The inherent sound field of the indoor environment in the absence of external injection. This includes HVAC mechanical noise, structure-borne sound (flanking transmission through walls/floors), reverberant field energy, and outdoor noise ingress.

* **Characteristics:** Broadband, stochastic energy predominantly below 2 kHz. Correlates with building systems (boilers, fans, elevators).
* **Identification:** Established via Long-Term Average Spectrum (LTAS) averaging over 60 frames (~3 seconds at 48 kHz/4096 samples).

### Zone 1: Primary Injected Signal (PIS)
Sound energy not attributable to the Ambient Acoustic Baseline, appearing as localized, non-stochastic spectral components. This category includes airborne sound transmission, structure-borne sound from non-building sources, electronic reproduction, and transduced audio.

* **Characteristics:** Narrowband tones, harmonic series (fundamental + integer multiples), amplitude/frequency modulation signatures, or broadband noise with non-ambient directional properties.
* **Identification:** Statistical deviation from the AAB fingerprint. Spatial localization via differential measurement (Position A vs. Position B subtraction).

### Zone 2: Secondary Artifacts & Distortion Products (SADP)
Spectral components that exhibit temporal correlation with the PIS but are absent during PIS absence. These are *dependent* artifacts, not independent sound sources. They may arise from several distinct physical mechanisms:

| Mechanism | Physical Explanation | Diagnostic Signature |
|-----------|---------------------|---------------------|
| **Intermodulation Distortion (IMD)** | Non-linear mixing of two or more signals in a transducer, amplifier, or boundary surface. Produces sum/difference tones (f₁±f₂, 2f₁±f₂). | Non-harmonic, mathematically predictable frequencies based on PIS components. Appear only when multiple PIS tones are simultaneously present. |
| **Harmonic Distortion** | Non-linear reproduction of the PIS itself through imperfect transducers or overloaded amplifiers. | Integer multiples (2×, 3×, etc.) of PIS fundamentals. Phase-locked to the fundamental. |
| **Parametric Array Demodulation** | Ultrasonic carrier wave (typically 40–100 kHz) amplitude-modulated with audio. Demodulates in air via non-linear acoustic propagation. | Requires sampling rate >96 kHz (e.g., UMIK-2) to detect the carrier. Audible demodulation product tracks the PIS envelope. **Not detectable at 48 kHz.** |
| **Electromagnetic Crosstalk / Microphonics** | Audio-frequency currents in wiring or equipment re-radiated as sound via piezoelectric or magnetostrictive effects. | Often broadband, impulsive, or power-line related (50/60 Hz and harmonics in EU/UK). Correlates with electrical load cycles. |

> **Critical Note:** The term "relay system" implies a specific active repeater device. SignalSleuth does not assume this mechanism. Instead, it tests the *hypothesis* of dependency: **If SADP is caused by non-linear interaction with PIS, we expect temporal correlation, envelope tracking, and mathematically predictable frequency relationships.** The tool provides cross-correlation and IMD prediction features to test these hypotheses.

---

## 🛠 Prerequisites

| Component | Requirement |
|-----------|-------------|
| **Hardware** | miniDSP UMIK-1 (strongly recommended) or equivalent calibrated USB microphone with known sensitivity |
| **Calibration File** | UMIK-1 factory `.txt` calibration file (required for absolute SPL) |
| **Software** | Python 3.9+ |
| **OS** | macOS, Linux, Windows (with appropriate audio drivers) |

### Python Dependencies
```bash
pip install sounddevice numpy scipy matplotlib
```

---

## 🚀 Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/SignalSleuth.git
cd SignalSleuth
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Locate Your UMIK-1 Calibration File
Each UMIK-1 ships with a unique calibration file (e.g., `UMIK-1 cal file 7101234.txt`). Download it from miniDSP or the included CD. Place it in the project directory.

### 4. Verify UMIK-1 Sensitivity
Check your UMIK-1 calibration certificate for the sensitivity value (typically **-18 dBFS @ 94 dB SPL @ 1 kHz**). Update `Config.umik_sensitivity_dbfs` if your unit differs.

### 5. Run SignalSleuth
```bash
python signalsleuth_v2.py
```

---

## 📋 Controls

| Key | Action |
|-----|--------|
| **A** | Capture / reset the Ambient Acoustic Baseline fingerprint. Hold still for ~3 seconds while the room's natural sound field is averaged. |
| **Q** | Quit the application gracefully. All logs and metadata are saved automatically. |

---

## 📊 Features (v2.0)

### Real-Time Spectral Analysis
* **High-Resolution FFT:** Hanning-windowed Fast Fourier Transform with configurable window size.
* **Log-Frequency Display:** `semilogx` scaling appropriate for psychoacoustic perception.
* **Ambient Subtraction:** Live display of "Ambient-Subtracted" spectrum (yellow line) to visually isolate PIS and SADP components.

### Forensic Logging & Data Integrity
* **Timestamped CSV Peak Log:** Every detected anomaly above the SPL threshold is logged with ISO 8601 timestamp, frequency, magnitude (dB FS), absolute SPL (dB re 20 µPa), acoustic zone, and SHA-256 integrity hash.
* **JSON Session Metadata:** Hardware detection, configuration snapshot, calibration status, session duration, and software version.
* **Triggered WAV Recording:** Automatic capture of 5-second audio clips when SPL exceeds configurable threshold, with SHA-256 hashing for chain of custody.
* **Session Isolation:** Each run creates a unique timestamped directory (`forensic_logs/YYYYMMDD_HHMMSS/`) preventing data contamination.

### Absolute SPL Measurement
* **Calibration File Integration:** Parses miniDSP `.txt` format and applies frequency-response correction across all FFT bins.
* **dB SPL Conversion:** Converts relative dB FS to absolute Sound Pressure Level using the UMIK-1's certified sensitivity, producing legally traceable measurements.

### Intelligent Peak Detection
* **Dynamic Noise Floor:** Rolling median baseline adapts to changing ambient conditions.
* **Zone-Aware Classification:** Peaks are automatically categorized as AAB, PIS, or SADP based on frequency.
* **Prominence Filtering:** `scipy.signal.find_peaks` with prominence detection eliminates false positives from noise floor ripple.

### Background Subtraction
* **LTAS Ambient Fingerprint:** Averages 60 frames (~3 seconds) to establish a statistical ambient profile.
* **Differential Display:** Subtracts the AAB fingerprint from live data, revealing non-ambient components in real time.

---

## 📁 Output Structure

```
forensic_logs/
└── 20260505_143022/                 # Session ID (UTC)
    ├── metadata.json                  # Session metadata & hardware info
    ├── peak_log.csv                   # Timestamped anomaly log with hashes
    ├── trigger_143025.wav             # Auto-triggered audio capture
    └── ...
```

### CSV Peak Log Format
| Column | Description |
|--------|-------------|
| `timestamp_iso` | ISO 8601 timestamp (UTC) |
| `timestamp_unix` | Unix epoch timestamp |
| `frequency_hz` | Peak frequency |
| `magnitude_dbfs` | Relative magnitude (dB FS) |
| `spl_db` | Absolute Sound Pressure Level (dB re 20 µPa) |
| `zone` | AAB / PIS / SADP |
| `peak_type` | Classification (e.g., "narrowband") |
| `session_id` | Unique session identifier |
| `file_hash` | SHA-256 integrity hash of the data row |

---

## 🔬 Scientific Methodology

### How SignalSleuth Separates the Three Groups

1. **Spectral Separation:** High-resolution FFT with flat-top equivalent (Hanning + zero-padding) for amplitude accuracy. Cepstral analysis ready for harmonic series detection.
2. **Temporal Correlation:** Cross-correlation between PIS and SADP bands. If SADP appears only when PIS is present and with fixed time delay, dependency is established.
3. **Envelope Tracking:** If SADP amplitude envelope tracks PIS envelope, they are causally linked (indicating IMD or harmonic distortion).
4. **Phase Coherence:** Fixed phase relationship between SADP and PIS fundamentals indicates distortion products of the same source.
5. **Spatial Differentiation:** Differential measurement (Position A − Position B) cancels common ambient noise; localized injection remains.

### Limitations & Constraints

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| **48 kHz Nyquist Limit** | Cannot detect ultrasonic carriers (>24 kHz) or parametric array signatures. | Upgrade to UMIK-2 (192 kHz) and modify `sample_rate` to 96000 or 192000. |
| **Single-Channel Input** | No directional or stereo triangulation capability. | Use dual UMIK-1s with synchronized clocks for intensity probe or time-difference-of-arrival (TDOA) analysis. |
| **No EM Field Detection** | Cannot correlate acoustic anomalies with electromagnetic interference. | Integrate RTL-SDR or spectrum analyzer for simultaneous RF monitoring. |
| **Relative dB Without Calibration** | Uncalibrated measurements are inadmissible for legal proceedings. | Always load the UMIK-1 factory calibration file. |
| **Assumed AAB Stability** | Ambient fingerprint may drift over time (HVAC cycles, weather). | Re-capture ambient fingerprint periodically using the 'A' key. |

---

## 🗺 Development Roadmap

### v2.1 — Intermodulation Analysis
* **IMD Calculator:** User selects PIS peaks; tool auto-calculates expected intermodulation products (2f₁−f₂, f₁+f₂, etc.) and highlights matching SADP peaks.
* **Harmonic Series Detector:** Cepstral analysis (quefrency peaks) to identify periodic sources vs. stochastic noise.

### v2.2 — Spectrogram & Persistence
* **Scrolling Spectrogram:** Replace/supplement RTA with STFT time-frequency display (`plt.specgram`).
* **Persistence Heatmap:** Accumulate peak locations over time to prove chronic vs. intermittent exposure patterns.

### v2.5 — Differential & Directional Mode
* **Dual-Microphone Support:** Stereo/differential recording for acoustic shadowing and beam mapping.
* **Position Subtraction:** Automated "Position A vs. Position B" spectral subtraction with GPS/location tagging.

### v3.0 — Ultrasonic & Advanced Demodulation
* **192 kHz Sampling:** UMIK-2 support for ultrasonic carrier detection (40–96 kHz).
* **Envelope Demodulation:** Hilbert transform-based AM/FM demodulation of suspected carrier bands.
* **Comb-Filter Fingerprinting:** Detection of periodic notches/peaks indicative of standing waves or localized reflection patterns.

### v3.5 — Forensic Reporting Suite
* **Automated PDF Report Generation:** Timestamped, hashed, and formatted for legal submission.
* **Expert Witness Mode:** Export data in formats compatible with MATLAB, Audacity, and forensic audio suites (e.g., iZotope RX).

---

## ⚖️ Legal & Ethical Usage

SignalSleuth is designed for **legitimate acoustic investigation**, including:
* Environmental noise assessment and nuisance documentation
* Building acoustics and flanking transmission analysis
* Research into non-linear acoustic phenomena
* Personal security and counter-surveillance **within legal boundaries**

**Prohibited uses:** Unlawful surveillance, harassment, or deployment in jurisdictions where audio recording requires consent. Users are responsible for complying with local laws (e.g., GDPR in EU, wiretapping statutes in US states).

---

## 📚 References & Further Reading

* **IEC 61672-1:2013** — Electroacoustics: Sound Level Meters (Class 1/2 standards)
* **ISO 1996** — Acoustics: Description, measurement and assessment of environmental noise
* **miniDSP UMIK-1 Documentation** — [https://www.minidsp.com/products/acoustic-measurement/umik-1](https://www.minidsp.com/products/acoustic-measurement/umik-1)
* **Scipy Signal Processing** — `scipy.signal.find_peaks`, `scipy.signal.spectrogram`
* **SoundDevice Documentation** — [https://python-sounddevice.readthedocs.io/](https://python-sounddevice.readthedocs.io/)
* **Parametric Array Theory:** Westervelt, P.J. (1963). "Parametric Acoustic Array." *JASA*.

---

## 🤝 Contributing

Contributions welcome. Priority areas:
1. UMIK-2 / 192 kHz sampling support
2. Cross-platform packaging (PyInstaller, Homebrew)
3. Additional calibration file formats (REW, ARTA)
4. Machine learning anomaly classification

Please open an issue before major PRs.

---

## 📄 License

MIT License — See `LICENSE` file. Forensic outputs (logs, WAVs) belong to the user and are not covered by software licensing terms.

---

**SignalSleuth v2.0** — *From claiming to proving.*
