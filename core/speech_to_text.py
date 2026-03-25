import os
import time
import queue
import threading
import numpy as np
import sounddevice as sd
import whisper
import torch
import json

class SpeechRecognizer:
    """
    Klasse zur Spracherkennung mit OpenAI Whisper (lokal).
    Nutzt Callbacks zur Rückgabe von erkanntem Text.
    """

    def __init__(self, config_path="data/config.json", callback=None):
        self.config_path = config_path
        self.callback = callback
        self.running = False

        # Standardwerte laden
        self.load_config()

        # Audio-Konfiguration
        self.sample_rate = 16000
        self.silence_threshold = 0.01
        self.silence_duration = 0.8
        self.min_speech_duration = 0.5

        # Whisper Setup
        self._apply_thread_settings()
        self.model = None
        self.load_model()

        # Audio Puffer und Queue
        self.audio_queue = queue.Queue()
        self.audio_buffer = np.zeros((0,), dtype=np.float32)

        # Status-Variablen
        self.speech_active = False
        self.silence_timer = 0
        self.speech_start_time = None

        # Threading
        self.worker_thread = None
        self.stream = None

    def load_config(self):
        """Lädt die Konfiguration aus der JSON-Datei."""
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
                whisper_cfg = config.get("whisper", {})
                self.model_size = whisper_cfg.get("model_size", "medium")
                self.device = whisper_cfg.get("device", "cpu")
                self.threads = whisper_cfg.get("threads", 12)
                self.language = whisper_cfg.get("language", "de")
        except Exception as e:
            print(f"Fehler beim Laden der Konfig: {e}")
            self.model_size = "medium"
            self.device = "cpu"
            self.threads = 12
            self.language = "de"

    def _apply_thread_settings(self):
        """Setzt die CPU-Threads für Whisper und Torch."""
        os.environ["OMP_NUM_THREADS"] = str(self.threads)
        os.environ["MKL_NUM_THREADS"] = str(self.threads)
        torch.set_num_threads(self.threads)
        torch.set_num_interop_threads(self.threads)

    def load_model(self, model_size=None, device=None):
        """Lädt das Whisper-Modell."""
        if model_size: self.model_size = model_size
        if device: self.device = device

        print(f"Lade Whisper Modell '{self.model_size}' auf {self.device}...")
        self.model = whisper.load_model(self.model_size, device=self.device)
        print("Modell geladen.")

    def _audio_callback(self, indata, frames, time_info, status):
        """Wird vom sounddevice Stream aufgerufen, wenn neue Audiodaten vorliegen."""
        if status:
            print(f"Audio-Status-Fehler: {status}")
        self.audio_queue.put(indata.copy())

    def _transcription_loop(self):
        """Hauptloop des Worker-Threads zur Verarbeitung der Audio-Queue."""
        while self.running:
            try:
                # Hole Daten aus der Queue (mit Timeout, um Thread beenden zu können)
                data = self.audio_queue.get(timeout=0.1)
                data = data.flatten().astype(np.float32)
                volume = np.abs(data).mean()

                if volume > self.silence_threshold:
                    if not self.speech_active:
                        self.speech_active = True
                        self.speech_start_time = time.time()
                        self.audio_buffer = np.zeros((0,), dtype=np.float32)

                    self.silence_timer = 0
                    self.audio_buffer = np.concatenate((self.audio_buffer, data))
                else:
                    if self.speech_active:
                        self.silence_timer += len(data) / self.sample_rate
                        self.audio_buffer = np.concatenate((self.audio_buffer, data))

                        if self.silence_timer >= self.silence_duration:
                            speech_length = time.time() - self.speech_start_time

                            if speech_length >= self.min_speech_duration:
                                self._transcribe_and_report()

                            self.speech_active = False
                            self.silence_timer = 0
                            self.audio_buffer = np.zeros((0,), dtype=np.float32)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Fehler im Transkriptions-Loop: {e}")

    def _transcribe_and_report(self):
        """Führt die eigentliche Transkription durch und ruft den Callback auf."""
        try:
            # Transkribiere den aktuellen Audio-Buffer
            result = self.model.transcribe(
                self.audio_buffer,
                fp16=False if self.device == "cpu" else True,
                language=self.language
            )
            text = result.get("text", "").strip()

            if text and self.callback:
                self.callback(text)
            elif text:
                print(f"🗣 Text erkannt: {text}")
        except Exception as e:
            print(f"Fehler bei der Transkription: {e}")

    def start(self):
        """Startet die Audioaufnahme und den Transkriptions-Thread."""
        if self.running:
            return

        self.running = True
        self.audio_queue = queue.Queue() # Queue zurücksetzen

        # Worker Thread starten
        self.worker_thread = threading.Thread(target=self._transcription_loop, daemon=True)
        self.worker_thread.start()

        # Audio Stream starten
        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                callback=self._audio_callback
            )
            self.stream.start()
            print("Spracherkennung gestartet.")
        except Exception as e:
            print(f"Fehler beim Starten des Audio-Streams: {e}")
            self.stop()

    def stop(self):
        """Stoppt die Spracherkennung sauber."""
        self.running = False

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        if self.worker_thread:
            self.worker_thread.join(timeout=1)
            self.worker_thread = None

        print("Spracherkennung gestoppt.")

if __name__ == "__main__":
    # Test-Funktion
    def test_callback(text):
        print(f"TEST CALLBACK: {text}")

    recognizer = SpeechRecognizer(callback=test_callback)
    recognizer.start()

    try:
        print("Sprechen Sie jetzt... (STRG+C zum Beenden)")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        recognizer.stop()
