import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import threading
import time

# Import core modules
from core.speech_to_text import SpeechRecognizer
from core.text_vectorization import TextToPathConverter
from core.gcode_converter import GCodeGenerator
from core.serial_comm import SerialPlotter

class PlotterUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Voice-to-Plotter Controller")
        self.geometry("1000x700")

        # Core instances
        self.recognizer = None
        self.converter = TextToPathConverter()
        self.generator = GCodeGenerator()
        self.plotter = SerialPlotter(log_callback=self.log)

        # State
        self.current_paths = []

        self.create_widgets()
        self.load_config_to_ui()

        # Periodic update for serial logs/responses
        self.after(100, self._periodic_check)

    def create_widgets(self):
        # Main layout: Left (Controls), Right (Preview)
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        left_panel = ttk.Frame(main_frame, width=350)
        left_panel.pack(side="left", fill="y", padx=(0, 10))

        right_panel = ttk.Frame(main_frame)
        right_panel.pack(side="right", fill="both", expand=True)

        # --- LEFT PANEL: Settings & Controls ---

        # 1. Connection Frame
        conn_frame = ttk.LabelFrame(left_panel, text="Verbindung (Plotter)")
        conn_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(conn_frame, text="Port:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(conn_frame, textvariable=self.port_var, values=self.plotter.list_ports())
        self.port_cb.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Button(conn_frame, text="Aktualisieren", command=self.refresh_ports).grid(row=0, column=2, padx=5, pady=5)

        self.connect_btn = ttk.Button(conn_frame, text="Verbinden", command=self.toggle_connection)
        self.connect_btn.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="ew")

        # 2. Whisper Frame
        whisper_frame = ttk.LabelFrame(left_panel, text="Spracherkennung (Whisper)")
        whisper_frame.pack(fill="x", pady=10)

        ttk.Label(whisper_frame, text="Modell:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.model_var = tk.StringVar(value="medium")
        ttk.Entry(whisper_frame, textvariable=self.model_var).grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(whisper_frame, text="Threads:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.threads_var = tk.IntVar(value=12)
        self.threads_entry = ttk.Entry(whisper_frame, textvariable=self.threads_var)
        self.threads_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(whisper_frame, text="Gerät:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.device_var = tk.StringVar(value="auto")
        self.device_cb = ttk.Combobox(whisper_frame, textvariable=self.device_var, values=["auto", "cpu", "cuda"])
        self.device_cb.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        self.voice_btn = ttk.Button(whisper_frame, text="Spracherkennung starten", command=self.toggle_voice)
        self.voice_btn.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        # 3. Plotter Settings
        settings_frame = ttk.LabelFrame(left_panel, text="Plotter-Einstellungen")
        settings_frame.pack(fill="x", pady=10)

        ttk.Label(settings_frame, text="Stift HOCH (mm):").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        self.z_up_var = tk.StringVar(value="5.0")
        self.z_up_entry = ttk.Entry(settings_frame, textvariable=self.z_up_var, width=8)
        self.z_up_entry.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(settings_frame, text="Stift RUNTER (mm):").grid(row=1, column=0, padx=5, pady=2, sticky="w")
        self.z_down_var = tk.StringVar(value="0.0")
        self.z_down_entry = ttk.Entry(settings_frame, textvariable=self.z_down_var, width=8)
        self.z_down_entry.grid(row=1, column=1, padx=5, pady=2)

        ttk.Label(settings_frame, text="Feedrate:").grid(row=2, column=0, padx=5, pady=2, sticky="w")
        self.feed_var = tk.StringVar(value="1500")
        self.feed_entry = ttk.Entry(settings_frame, textvariable=self.feed_var, width=8)
        self.feed_entry.grid(row=2, column=1, padx=5, pady=2)

        ttk.Button(settings_frame, text="Speichern", command=self.save_settings).grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        # 4. Action Frame
        action_frame = ttk.LabelFrame(left_panel, text="Aktionen")
        action_frame.pack(fill="x", pady=10)

        ttk.Button(action_frame, text="Home (G28)", command=self.home_plotter).pack(fill="x", padx=5, pady=2)
        self.plot_btn = ttk.Button(action_frame, text="PLOTTEN STARTEN", command=self.start_plot)
        self.plot_btn.pack(fill="x", padx=5, pady=10)
        ttk.Button(action_frame, text="STOP / Not-Aus", command=self.stop_plot).pack(fill="x", padx=5, pady=2)

        # --- RIGHT PANEL: Preview & Console ---

        # 1. Preview (Canvas)
        preview_frame = ttk.LabelFrame(right_panel, text="Vorschau (Vektorpfade)")
        preview_frame.pack(fill="both", expand=True, pady=(0, 10))

        self.canvas = tk.Canvas(preview_frame, bg="white")
        self.canvas.pack(fill="both", expand=True, padx=5, pady=5)

        # 2. Text Input / Recognized Text
        text_frame = ttk.LabelFrame(right_panel, text="Erkannter Text / Eingabe")
        text_frame.pack(fill="x", pady=10)

        self.text_input = tk.Text(text_frame, height=3)
        self.text_input.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        ttk.Button(text_frame, text="Vorschau\naktualisieren", command=self.update_preview).pack(side="right", padx=5, pady=5)

        # 3. Console/Log
        log_frame = ttk.LabelFrame(right_panel, text="Log / Konsole")
        log_frame.pack(fill="both", expand=True)

        self.log_out = scrolledtext.ScrolledText(log_frame, height=8, state="disabled", font=("Consolas", 9))
        self.log_out.pack(fill="both", expand=True, padx=5, pady=5)

    def load_config_to_ui(self):
        try:
            with open("data/config.json", "r") as f:
                cfg = json.load(f)
                self.port_var.set(cfg.get("plotter", {}).get("port", ""))
                self.model_var.set(cfg.get("whisper", {}).get("model_size", "medium"))
                self.threads_var.set(cfg.get("whisper", {}).get("threads", 12))
                self.device_var.set(cfg.get("whisper", {}).get("device", "auto"))
                self.z_up_var.set(cfg.get("plotter", {}).get("z_up", 5.0))
                self.z_down_var.set(cfg.get("plotter", {}).get("z_down", 0.0))
                self.feed_var.set(cfg.get("plotter", {}).get("feedrate", 1500))
        except:
            pass

    def validate_fields(self):
        """Validiert die Eingabefelder und gibt visuelles Feedback."""
        valid = True
        # Liste der zu validierenden Felder: (Variable, Widget, Label-Name)
        fields = [
            (self.z_up_var, self.z_up_entry, "Stift HOCH"),
            (self.z_down_var, self.z_down_entry, "Stift RUNTER"),
            (self.feed_var, self.feed_entry, "Feedrate"),
            (self.port_var, self.port_cb, "Port")
        ]

        # Style zurücksetzen
        style = ttk.Style()
        style.configure("Invalid.TEntry", fieldbackground="red")
        style.configure("Invalid.TCombobox", fieldbackground="red")

        for var, widget, name in fields:
            val = var.get().strip()
            if not val:
                # Tkinter Entry Hintergrundfarbe ändern
                if isinstance(widget, ttk.Entry) or isinstance(widget, ttk.Combobox):
                    widget.configure(style="Invalid.TEntry" if isinstance(widget, ttk.Entry) else "Invalid.TCombobox")

                # Fallback für Standard-Entry falls ttk Style nicht greift
                try: widget.config(background="red")
                except: pass

                self.log(f"WARNUNG: Feld '{name}' muss ausgefüllt werden.")
                valid = False
            else:
                # Hintergrund zurücksetzen
                if isinstance(widget, ttk.Entry) or isinstance(widget, ttk.Combobox):
                    widget.configure(style="TEntry" if isinstance(widget, ttk.Entry) else "TCombobox")
                try: widget.config(background="white")
                except: pass

        if not valid:
            messagebox.showwarning("Eingabefehler", "Einige Felder müssen ausgefüllt werden.")

        return valid

    def save_settings(self):
        if not self.validate_fields():
            return

        try:
            with open("data/config.json", "r") as f:
                cfg = json.load(f)

            cfg["plotter"]["port"] = self.port_var.get()
            cfg["plotter"]["z_up"] = float(self.z_up_var.get())
            cfg["plotter"]["z_down"] = float(self.z_down_var.get())
            cfg["plotter"]["feedrate"] = int(self.feed_var.get())
            cfg["whisper"]["model_size"] = self.model_var.get()
            cfg["whisper"]["threads"] = self.threads_var.get()
            cfg["whisper"]["device"] = self.device_var.get()

            with open("data/config.json", "w") as f:
                json.dump(cfg, f, indent=4)

            # Update instances
            self.plotter.load_config()
            self.generator.load_config()
            self.log("Einstellungen gespeichert.")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Einstellungen nicht speichern: {e}")

    def log(self, message):
        self.log_out.config(state="normal")
        self.log_out.insert("end", f"{time.strftime('%H:%M:%S')} {message}\n")
        self.log_out.see("end")
        self.log_out.config(state="disabled")

    def refresh_ports(self):
        ports = self.plotter.list_ports()
        self.port_cb["values"] = ports
        if ports: self.port_cb.current(0)

    def toggle_connection(self):
        if self.plotter.ser and self.plotter.ser.is_open:
            self.plotter.disconnect()
            self.connect_btn.config(text="Verbinden")
        else:
            if self.plotter.connect(self.port_var.get()):
                self.connect_btn.config(text="Trennen")

    def toggle_voice(self):
        if self.recognizer and self.recognizer.running:
            self.recognizer.stop()
            self.voice_btn.config(text="Spracherkennung starten")
            self.log("Spracherkennung gestoppt.")
        else:
            self.log("Initialisiere Whisper (bitte warten)...")
            self.voice_btn.config(state="disabled", text="Lade Modell...")

            # Modellladen in separatem Thread, um UI nicht zu blockieren
            def load_and_start():
                try:
                    if not self.recognizer:
                        self.recognizer = SpeechRecognizer(callback=self._on_speech_recognized)

                    self.recognizer.start()
                    self.after(0, lambda: self._voice_started())
                except Exception as e:
                    self.after(0, lambda: self._voice_failed(e))

            threading.Thread(target=load_and_start, daemon=True).start()

    def _voice_started(self):
        self.voice_btn.config(state="normal", text="Spracherkennung STOP")
        self.log("Spracherkennung aktiv.")

    def _voice_failed(self, error):
        self.voice_btn.config(state="normal", text="Spracherkennung starten")
        self.log(f"Fehler bei Spracherkennung: {error}")
        messagebox.showerror("Fehler", f"Whisper konnte nicht gestartet werden: {error}")

    def _on_speech_recognized(self, text):
        # Callback vom Whisper-Thread
        self.after(0, lambda: self._add_text_to_ui(text))

    def _add_text_to_ui(self, text):
        self.text_input.insert("end", f"{text}\n")
        self.log(f"Erkannt: {text}")
        self.update_preview()

    def update_preview(self):
        text = self.text_input.get("1.0", "end").strip()
        if not text:
            return

        # Vektorisieren
        self.current_paths = self.converter.text_to_paths(text, start_x=10, start_y=100)

        # Zeichnen auf Canvas
        self.canvas.delete("all")

        # Skalierung und Verschiebung für Vorschau (Canvas 0,0 ist oben links)
        # Wir müssen Y ggf. anpassen, da Plotter 0,0 meist unten links ist
        for path in self.current_paths:
            if len(path) < 2: continue
            # Konvertiere Punkte in Canvas-Koordinaten
            points = []
            for (x, y) in path:
                # Canvas-Y = h - y (einfache Spiegelung für Vorschau)
                points.append(x * 2) # Skalierung für Vorschau
                points.append(400 - (y * 2))

            self.canvas.create_line(points, fill="blue", width=1)

    def start_plot(self):
        if not self.validate_fields():
            return

        if not self.current_paths:
            messagebox.showwarning("Kein Text", "Bitte geben Sie Text ein oder nutzen Sie die Spracherkennung.")
            return

        if not self.plotter.ser or not self.plotter.ser.is_open:
            messagebox.showwarning("Nicht verbunden", "Bitte verbinden Sie zuerst den Plotter.")
            return

        gcode = self.generator.generate_gcode(self.current_paths)
        self.plotter.start_plotting(gcode)

    def stop_plot(self):
        self.plotter.stop_plotting()
        # Not-Aus an Plotter senden
        if self.plotter.ser and self.plotter.ser.is_open:
            self.plotter.ser.write(b"M112\n")

    def home_plotter(self):
        if self.plotter.ser and self.plotter.ser.is_open:
            self.plotter.send_line("G28")

    def _periodic_check(self):
        # Hier könnten wir Status-Abfragen vom Plotter einbauen
        self.after(100, self._periodic_check)

    def on_closing(self):
        if self.recognizer:
            self.recognizer.stop()
        self.plotter.disconnect()
        self.destroy()

if __name__ == "__main__":
    app = PlotterUI()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
