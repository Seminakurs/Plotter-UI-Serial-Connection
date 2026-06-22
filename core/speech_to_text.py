import os
import math
import time
import queue
import threading
import numpy as np
import sounddevice as sd
import whisper
import torch
import json

from utils.logger import SessionLogger

# torch.cuda.OutOfMemoryError existiert erst seit PyTorch 2.0
_CUDA_OOM_ERROR = getattr(torch.cuda, "OutOfMemoryError", RuntimeError)

_DEFAULT_WHISPER = {"model_size": "medium", "device": "auto", "threads": 12, "language": "de"}
_DEFAULT_STT = {
    "silence_threshold": 0.01,
    "silence_duration": 0.8,
    "min_speech_duration": 0.5,
    "max_buffer_seconds": 30,
    "undo_keyword": "Dino",
}


class SpeechRecognizer:
    """
    Spracherkennung mit OpenAI Whisper (lokal).
    Callback liefert {"text": str, "confidence": float}.
    """

    def __init__(self, config_path="data/config.json", callback=None, status_callback=None):
        """
        callback:        wird mit {"text": str, "confidence": float} aufgerufen.
        status_callback: wird mit Status-Strings (Hardware-Info, Fehler) aufgerufen.
        """
        self.config_path = config_path
        self.callback = callback
        self.status_callback = status_callback
        self.running = False
        self.logger = SessionLogger()

        self.load_config()

        # Whisper Setup — erst Modell laden, dann Thread-Settings basierend auf
        # dem *tatsächlich* genutzten Device (nach potenziellem CUDA->CPU Fallback)
        self.model = None
        self.load_model()
        self._apply_thread_settings()

        # Audio-State
        self.audio_queue = queue.Queue()
        self.audio_buffer = np.zeros((0,), dtype=np.float32)
        self.speech_active = False
        self.silence_timer = 0
        self.speech_start_time = None

        # Threading
        self.worker_thread = None
        self.stream = None

    # ── Config ────────────────────────────────────────────────────────────

    def load_config(self):
        """Lädt Whisper- und STT-Konfiguration aus der JSON-Datei (mit Defaults als Fallback)."""
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
            whisper_cfg = config.get("whisper", {})
            stt_cfg = config.get("stt_settings", {})
        except Exception as e:
            self._report_status(f"Fehler beim Laden der Konfig: {e}")
            whisper_cfg = {}
            stt_cfg = {}

        self.model_size = whisper_cfg.get("model_size", _DEFAULT_WHISPER["model_size"])
        self.device = whisper_cfg.get("device", _DEFAULT_WHISPER["device"])
        self.threads = whisper_cfg.get("threads", _DEFAULT_WHISPER["threads"])
        self.language = whisper_cfg.get("language", _DEFAULT_WHISPER["language"])

        # ── STT SETTINGS ──────────────────────────────────────────────────
        # Diese Werte sind über die Config (und später die UI) änderbar.
        self.silence_threshold = stt_cfg.get("silence_threshold", _DEFAULT_STT["silence_threshold"])
        self.silence_duration = stt_cfg.get("silence_duration", _DEFAULT_STT["silence_duration"])
        self.min_speech_duration = stt_cfg.get("min_speech_duration", _DEFAULT_STT["min_speech_duration"])
        self.max_buffer_seconds = stt_cfg.get("max_buffer_seconds", _DEFAULT_STT["max_buffer_seconds"])
        self.undo_keyword = stt_cfg.get("undo_keyword", _DEFAULT_STT["undo_keyword"]).strip().lower()
        # ────────────────────────────────────────────────────────────────────

        if self.device == "auto":
            self.device = "cuda" if self._check_cuda_support() else "cpu"
            self._report_status(f"Automatische Geräte-Erkennung: Nutze {self.device.upper()}")

        self.sample_rate = 16000

    # ── Logging / Status ──────────────────────────────────────────────────

    def _report_status(self, message):
        """Loggt auf Konsole, in die Log-Datei und optional an die UI."""
        print(message)
        self.logger.write("whisper_system", message)
        if self.status_callback:
            self.status_callback(message)

    # ── CUDA-Prüfung ─────────────────────────────────────────────────────

    def _check_cuda_support(self):
        cuda_build = getattr(torch.version, "cuda", None)
        if cuda_build is None:
            self._report_status(
                "WARNUNG: PyTorch ohne CUDA-Unterstützung gebaut (torch.version.cuda ist None). "
                "CUDA-fähige Version nötig (https://pytorch.org/get-started/locally/). Fallback auf CPU."
            )
            return False
        if not torch.cuda.is_available():
            self._report_status(
                f"WARNUNG: PyTorch mit CUDA {cuda_build} gebaut, aber keine GPU/Treiber gefunden. "
                "Fallback auf CPU."
            )
            return False
        return True

    def _report_hardware_info(self):
        self._report_status(f"Whisper-Modell: '{self.model_size}' | Gerät: {self.device.upper()}")
        if self.device == "cuda" and torch.cuda.is_available():
            try:
                gpu_name = torch.cuda.get_device_name(0)
                free_bytes, total_bytes = torch.cuda.mem_get_info(0)
                self._report_status(
                    f"GPU: {gpu_name} | VRAM frei: {free_bytes / (1024**2):.0f} MB / {total_bytes / (1024**2):.0f} MB"
                )
            except Exception as e:
                self._report_status(f"Konnte GPU-Details nicht auslesen: {e}")

    # ── Thread-Settings ───────────────────────────────────────────────────

    def _apply_thread_settings(self):
        """Setzt CPU-Thread-Limits. Wird NACH load_model() aufgerufen,
        damit self.device den tatsächlich genutzten Wert hat (auch nach Fallback)."""
        if self.device == "cpu":
            os.environ["OMP_NUM_THREADS"] = str(self.threads)
            os.environ["MKL_NUM_THREADS"] = str(self.threads)
            torch.set_num_threads(self.threads)
            torch.set_num_interop_threads(self.threads)
            self._report_status(f"CPU-Threads gesetzt: {self.threads}")

    # ── Modell laden (kompakt, ein Fallback-Block) ────────────────────────

    def load_model(self, model_size=None, device=None):
        if model_size: self.model_size = model_size
        if device: self.device = device
        if self.device == "cuda" and not self._check_cuda_support():
            self.device = "cpu"

        # Altes Modell freigeben, falls vorhanden (verhindert VRAM-Leak bei Reload)
        if self.model is not None:
            del self.model
            self.model = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        self._report_status(f"Lade Whisper Modell '{self.model_size}' auf {self.device.upper()}...")
        try:
            self.model = whisper.load_model(self.model_size, device=self.device)
        except (_CUDA_OOM_ERROR, RuntimeError) as e:
            is_oom = isinstance(e, _CUDA_OOM_ERROR)
            is_cuda_error = is_oom or "cuda" in str(e).lower()
            if self.device != "cuda" or not is_cuda_error:
                raise
            reason = "Nicht genug VRAM" if is_oom else f"CUDA-Fehler ({e})"
            self._report_status(f"FEHLER: {reason} auf GPU. Fallback auf CPU.")
            torch.cuda.empty_cache()
            self.device = "cpu"
            self.model = whisper.load_model(self.model_size, device=self.device)

        self._report_status(f"Modell '{self.model_size}' erfolgreich geladen.")
        self._report_hardware_info()

    # ── Audio-Callback ────────────────────────────────────────────────────

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            self._report_status(f"Audio-Status-Fehler: {status}")
        self.audio_queue.put(indata.copy())

    # ── Transkriptions-Loop ───────────────────────────────────────────────

    def _reset_audio_buffer(self):
        self.audio_buffer = np.zeros((0,), dtype=np.float32)

    def _transcription_loop(self):
        while self.running:
            try:
                data = self.audio_queue.get(timeout=0.1)
                data = data.flatten().astype(np.float32)
                volume = np.abs(data).mean()

                if volume > self.silence_threshold:
                    if not self.speech_active:
                        self.speech_active = True
                        self.speech_start_time = time.time()
                        self._reset_audio_buffer()

                    self.silence_timer = 0
                    self.audio_buffer = np.concatenate((self.audio_buffer, data))

                    # ── Buffer-Limit: bei max_buffer_seconds pausieren + transkribieren ──
                    buffer_seconds = len(self.audio_buffer) / self.sample_rate
                    if buffer_seconds >= self.max_buffer_seconds:
                        self._report_status(
                            f"Buffer-Limit ({self.max_buffer_seconds}s) erreicht. "
                            "Transkribiere und höre weiter zu..."
                        )
                        self._transcribe_and_report()
                        self._reset_audio_buffer()
                        self.speech_start_time = time.time()
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
                            self._reset_audio_buffer()
            except queue.Empty:
                continue
            except Exception as e:
                self._report_status(f"Fehler im Transkriptions-Loop: {e}")

    # ── Confidence-Berechnung ─────────────────────────────────────────────

    @staticmethod
    def _confidence_from_segments(segments):
        if not segments:
            return 0.0
        scores = []
        for seg in segments:
            avg_logprob = seg.get("avg_logprob", -1.0)
            no_speech_prob = seg.get("no_speech_prob", 0.0)
            scores.append(math.exp(avg_logprob) * (1.0 - no_speech_prob))
        return round((sum(scores) / len(scores)) * 100, 1)

    # ── Transkription + Undo-Keyword ──────────────────────────────────────

    def _transcribe_and_report(self):
        try:
            result = self.model.transcribe(
                self.audio_buffer,
                fp16=(self.device != "cpu"),
                language=self.language
            )
            text = result.get("text", "").strip()
            confidence = self._confidence_from_segments(result.get("segments", []))

            # Undo-Keyword: wenn der erkannte Text das Keyword enthält (oder nur
            # daraus besteht), wird statt des Textes ein Lösch-Signal gesendet.
            if text and text.lower().rstrip(".!?,") == self.undo_keyword:
                self._report_status(f"Undo-Keyword '{self.undo_keyword}' erkannt — letzter Satz wird gelöscht.")
                self.logger.write("stt_transkripte", f"[UNDO] Keyword erkannt (Confidence: {confidence}%)")
                if self.callback:
                    self.callback({"text": "", "confidence": confidence, "undo": True})
                return

            if text and self.callback:
                self.logger.write("stt_transkripte", f"{text} (Confidence: {confidence}%)")
                self.callback({"text": text, "confidence": confidence, "undo": False})
            elif text:
                self._report_status(f"Text erkannt ({confidence:.1f}%): {text}")

        except _CUDA_OOM_ERROR:
            self._report_status(
                "FEHLER: Nicht genug VRAM während der Transkription. "
                "Audio-Segment verworfen, GPU-Speicher freigegeben."
            )
            torch.cuda.empty_cache()
        except Exception as e:
            self._report_status(f"Fehler bei der Transkription: {e}")

    # ── Start / Stop ──────────────────────────────────────────────────────

    def start(self):
        if self.running:
            return
        self.running = True
        self.audio_queue = queue.Queue()

        self.worker_thread = threading.Thread(target=self._transcription_loop, daemon=True)
        self.worker_thread.start()

        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                callback=self._audio_callback
            )
            self.stream.start()
            self._report_status("Spracherkennung gestartet.")
        except Exception as e:
            self._report_status(f"Fehler beim Starten des Audio-Streams: {e}")
            self.stop()

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        if self.worker_thread:
            self.worker_thread.join(timeout=1)
            self.worker_thread = None
        self._report_status("Spracherkennung gestoppt.")

    # ── Live-Reload ───────────────────────────────────────────────────────

    def reload_config(self):
        """Lädt Config neu und lädt bei Modell-/Device-Änderung das Modell neu."""
        old_model = self.model_size
        old_device = self.device
        self.load_config()

        if self.model_size != old_model or self.device != old_device:
            self._report_status("Modell- oder Device-Änderung erkannt — lade Modell neu...")
            self.load_model()
            self._apply_thread_settings()
        else:
            self._report_status("STT-Einstellungen neu geladen (Modell unverändert).")


if __name__ == "__main__":
    def test_callback(result):
        if result.get("undo"):
            print("TEST: UNDO ausgelöst")
        else:
            print(f"TEST: {result['text']} (Confidence: {result['confidence']}%)")

    recognizer = SpeechRecognizer(callback=test_callback)
    recognizer.start()
    try:
        print("Sprechen Sie jetzt... (STRG+C zum Beenden)")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        recognizer.stop()
