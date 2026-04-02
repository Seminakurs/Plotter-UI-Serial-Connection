# Gap-Analyse: Voice-to-Plotter

Nach Analyse des aktuellen Code-Stands wurden folgende Lücken identifiziert, die für einen vollständigen und fehlerfreien Betrieb (insbesondere mit GPU-Unterstützung) geschlossen werden müssen:

### 1. System-Abhängigkeiten (Extern)
*   **FFmpeg**: Whisper benötigt `ffmpeg` auf dem Systempfad, um Audiodaten zu dekodieren. Ohne `ffmpeg` wird die Transkription fehlschlagen.
*   **NVIDIA Treiber & CUDA Toolkit**: Für die GPU-Nutzung müssen aktuelle NVIDIA-Treiber sowie das passende CUDA Toolkit (z.B. 11.8 oder 12.x) installiert sein.
*   **cuDNN**: Die NVIDIA CUDA Deep Neural Network Library ist für die Beschleunigung von Torch-Operationen notwendig.

### 2. Python-Bibliotheken & Installation
*   **PyTorch CUDA-Version**: Ein einfaches `pip install torch` installiert oft nur die CPU-Version. Die Installation muss spezifisch für die CUDA-Version erfolgen (z.B. via `--index-url https://download.pytorch.org/whl/cu121`).
*   **Fehlende Pakete in requirements.txt**: `Hershey-Fonts` und `pyserial` müssen fest in die Datei aufgenommen werden.

### 3. Logik-Bausteine (Code)
*   **GPU Auto-Detection**: Die `SpeechRecognizer`-Klasse prüft aktuell nicht automatisch auf `cuda`.
*   **GPU/CPU Umschalter**: In der UI fehlt die Möglichkeit, explizit zwischen CPU und GPU zu wählen.
*   **UI-Validierung**: Felder wie Z-Höhe, Feedrate oder Port werden nicht auf Gültigkeit geprüft. Leere Felder führen zu Fehlern.
*   **Visuelles Feedback**: Die geforderte Fehlermeldung (roter Hintergrund) bei Validierungsfehlern ist noch nicht implementiert.

### 4. Dokumentation
*   **README.md**: Es fehlt eine detaillierte Anleitung zur Einrichtung der GPU-Umgebung, Fehlerbehebung (Troubleshooting) und Systemvoraussetzungen.

Diese Punkte werden in den nächsten Schritten abgearbeitet.
