# Voice-to-Plotter 🗣✍️

Ein System zur Umwandlung von gesprochener Sprache in G-Code für Stift-Plotter (oder 3D-Drucker mit aufgesetztem Stift). Das Programm nutzt OpenAI Whisper zur lokalen Spracherkennung und wandelt den Text in präzise Vektorpfade (zurzeit nur Hershey-Fonts) um.

## 📋 Systemvoraussetzungen

1.  **Python**: 3.8 oder neuer.
2.  **FFmpeg**: Whisper benötigt FFmpeg zur Audio-Verarbeitung.
    *   **Windows**: `choco install ffmpeg` oder manuell von ffmpeg.org laden.
    *   **Linux**: `sudo apt install ffmpeg`
    *   **macOS**: `brew install ffmpeg`
3.  **Hardware (Optional für GPU-Beschleunigung)**:
    *   NVIDIA Grafikkarte.
    *   NVIDIA CUDA Toolkit (passend zur Treiberversion).
    *   cuDNN Library.

## 🚀 Installation

### 1. Repository klonen
```bash
git clone https://github.com/Seminakurs/Plotter-UI-Serial-Connection.git
md C:\Plooter
cd C:\Plooter

```

### 2. Abhängigkeiten installieren
Zuerst die Standard-Abhängigkeiten:
```bash
pip install -r requirements.txt
```

### 3. GPU-Support einrichten (WICHTIG für NVIDIA Nutzer)
Falls du eine NVIDIA GPU hast, musst du PyTorch mit CUDA-Unterstützung installieren. Ersetze `cu121` durch deine installierte CUDA-Version (z.B. `cu118`):
```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

## 🛠 Starten der Anwendung
Führe einfach die `main.py` aus:
```bash
python main.py
```

## 🎮 Bedienung
1.  **Verbindung**: Wähle den COM-Port deines Plotters/Druckers und klicke auf "Verbinden".
2.  **Spracherkennung**:
    *   Wähle das Gerät (Auto/CPU/CUDA).
    *   Klicke auf "Spracherkennung starten".
    *   Sprich deinen Text. Whisper transkribiert ihn automatisch ins Textfeld.
3.  **Plotten**:
    *   Passe bei Bedarf Z-Höhen und Feedrate an.
    *   Klicke auf "PLOTTEN STARTEN".

## ⚠️ Fehlerbehebung (Troubleshooting)

*   **Whisper findet FFmpeg nicht**: Stelle sicher, dass `ffmpeg` in deinem Systempfad (PATH) hinterlegt ist.
*   **CUDA wird nicht erkannt**: Prüfe mit `python -c "import torch; print(torch.cuda.is_available())"`. Wenn `False`, wurde die CPU-Version von Torch installiert.
*   **Plotter reagiert nicht**: Prüfe den COM-Port und die Baudrate (Standard 115200) in der `data/config.json`.
*   **Leere Eingabefelder**: Die UI markiert ungültige Felder rot. Fülle diese aus und speichere die Einstellungen.

---
Entwickelt von Jules.
