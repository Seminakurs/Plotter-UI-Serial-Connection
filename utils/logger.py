import os
import time
from datetime import datetime


class SessionLogger:
    """
    Schreibt Log-Einträge in separate Dateien pro Kategorie.
    Alle Dateien landen in data/output/logs/ mit Dateinamen, die sofort
    zeigen, was drin steckt:
      - stt_transkripte_<datum>.log   (erkannter Text + Confidence)
      - whisper_system_<datum>.log    (Modell-Laden, GPU-Info, Fehler)
      - plotter_<datum>.log           (G-Code, Verbindung, Fehler)
      - app_<datum>.log               (allgemeine UI-/Systemmeldungen)
    """

    CATEGORIES = ("stt_transkripte", "whisper_system", "plotter", "app")

    def __init__(self, log_dir="data/output/logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self._date_tag = datetime.now().strftime("%Y-%m-%d")
        self._handles = {}

    def _get_handle(self, category):
        key = f"{category}_{self._date_tag}"
        if key not in self._handles:
            path = os.path.join(self.log_dir, f"{key}.log")
            self._handles[key] = open(path, "a", encoding="utf-8")
        return self._handles[key]

    def write(self, category, message):
        """
        Schreibt eine Zeile in die Log-Datei der gewählten Kategorie.
        category: einer der Werte aus CATEGORIES
        """
        if category not in self.CATEGORIES:
            category = "app"
        stamp = time.strftime("%H:%M:%S")
        handle = self._get_handle(category)
        handle.write(f"[{stamp}] {message}\n")
        handle.flush()

    def close(self):
        for h in self._handles.values():
            try:
                h.close()
            except Exception:
                pass
        self._handles.clear()
