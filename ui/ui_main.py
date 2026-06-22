import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import threading
import time

_UI_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_UI_DIR)
CONFIG_PATH = os.path.join(_PROJECT_DIR, "data", "config.json")

if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

from core.speech_to_text import SpeechRecognizer
from core.text_vectorization import TextToPathConverter
from core.gcode_converter import GCodeGenerator
from core.serial_comm import SerialPlotter
from utils.logger import SessionLogger


class PlotterUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.THEME = {
            "bg":              "#0d1117",
            "bg_panel":        "#161b22",
            "bg_widget":       "#21262d",
            "bg_log":          "#010409",
            "bg_button":       "#21262d",
            "bg_button_hover": "#30363d",
            "bg_accent":       "#1f6feb",
            "bg_stop":         "#b91c1c",
            "fg":              "#e6edf3",
            "fg_accent":       "#58a6ff",
            "fg_dim":          "#8b949e",
            "fg_error":        "#f85149",
            "fg_plot_line":    "#3fb950",
            "border":          "#30363d",
        }
        T = self.THEME

        self.configure(bg=T["bg"])
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".",
            background=T["bg"], foreground=T["fg"],
            fieldbackground=T["bg_widget"], bordercolor=T["border"],
            darkcolor=T["bg_panel"], lightcolor=T["bg_panel"],
            troughcolor=T["bg_panel"])
        style.configure("TLabelframe",
            background=T["bg_panel"], bordercolor=T["border"], relief="groove")
        style.configure("TLabelframe.Label",
            background=T["bg_panel"], foreground=T["fg_accent"],
            font=("Segoe UI", 9, "bold"))
        style.configure("TLabel",  background=T["bg_panel"], foreground=T["fg"])
        style.configure("TFrame",  background=T["bg"])
        style.configure("TButton",
            background=T["bg_button"], foreground=T["fg"],
            borderwidth=1, bordercolor=T["border"], padding=(6, 4))
        style.map("TButton", background=[("active", T["bg_button_hover"])])
        style.configure("Accent.TButton",
            background=T["bg_accent"], foreground="#ffffff",
            borderwidth=0, padding=(6, 8), font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton",
            background=[("active", "#388bfd"), ("disabled", T["bg_button"])])
        style.configure("Stop.TButton",
            background=T["bg_stop"], foreground="#ffffff",
            borderwidth=0, padding=(6, 6))
        style.map("Stop.TButton", background=[("active", "#da3633")])
        style.configure("TEntry",
            fieldbackground=T["bg_widget"], foreground=T["fg"],
            insertcolor=T["fg"], bordercolor=T["border"])
        style.configure("TCombobox",
            fieldbackground=T["bg_widget"], foreground=T["fg"],
            selectbackground=T["bg_widget"], arrowcolor=T["fg_accent"])
        style.map("TCombobox",
            fieldbackground=[("readonly", T["bg_widget"])],
            foreground=[("readonly", T["fg"])])
        style.configure("TNotebook",
            background=T["bg"], borderwidth=0, tabmargins=0)
        style.configure("TNotebook.Tab",
            background=T["bg_panel"], foreground=T["fg_dim"],
            padding=(14, 7), borderwidth=0)
        style.map("TNotebook.Tab",
            background=[("selected", T["bg"])],
            foreground=[("selected", T["fg_accent"])])
        style.configure("TSeparator", background=T["border"])
        style.configure("Invalid.TEntry",    fieldbackground=T["fg_error"])
        style.configure("Invalid.TCombobox", fieldbackground=T["fg_error"])

        self.title("Voice-to-Plotter")
        self.state("zoomed")

        self.recognizer = None
        self.converter = TextToPathConverter(config_path=CONFIG_PATH)
        self.generator = GCodeGenerator(config_path=CONFIG_PATH)
        self.plotter = SerialPlotter(config_path=CONFIG_PATH, log_callback=self.log)
        self.logger = SessionLogger()
        self.current_paths = []

        self.create_widgets()
        self.load_config_to_ui()

    def create_widgets(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        tab1 = ttk.Frame(notebook)
        notebook.add(tab1, text="  Steuerung  ")

        tab2 = ttk.Frame(notebook)
        notebook.add(tab2, text="  Vorschau & Einstellungen  ")

        self._build_control_tab(tab1)
        self._build_alignment_tab(tab2)

    def _build_control_tab(self, parent):
        T = self.THEME

        sidebar = ttk.Frame(parent, width=290)
        sidebar.pack(side="left", fill="y", padx=(10, 0), pady=10)
        sidebar.pack_propagate(False)

        ttk.Separator(parent, orient="vertical").pack(side="left", fill="y", padx=8, pady=10)

        main = ttk.Frame(parent)
        main.pack(side="right", fill="both", expand=True, padx=(0, 10), pady=10)

        # Connection
        conn = ttk.LabelFrame(sidebar, text="Verbindung")
        conn.pack(fill="x", pady=(0, 8))
        conn.columnconfigure(1, weight=1)

        ttk.Label(conn, text="Port:").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        self.port_var = tk.StringVar()
        ports = self.plotter.list_ports()
        self.port_cb = ttk.Combobox(conn, textvariable=self.port_var, values=ports, width=12)
        self.port_cb.grid(row=0, column=1, padx=4, pady=6, sticky="ew")
        ttk.Button(conn, text="↻", command=self.refresh_ports, width=3).grid(
            row=0, column=2, padx=(2, 6))

        self.connect_btn = ttk.Button(conn, text="Verbinden", command=self.toggle_connection)
        self.connect_btn.grid(row=1, column=0, columnspan=3, padx=6, pady=(0, 8), sticky="ew")

        # Speech recognition
        voice = ttk.LabelFrame(sidebar, text="Spracherkennung")
        voice.pack(fill="x", pady=8)
        voice.columnconfigure(1, weight=1)

        ttk.Label(voice, text="Modell:").grid(row=0, column=0, padx=6, pady=5, sticky="w")
        self.model_var = tk.StringVar(value="medium")
        self.model_cb = ttk.Combobox(voice, textvariable=self.model_var,
            values=["small", "medium", "large", "turbo"], state="readonly")
        self.model_cb.grid(row=0, column=1, padx=6, pady=5, sticky="ew")

        ttk.Label(voice, text="Gerät:").grid(row=1, column=0, padx=6, pady=5, sticky="w")
        self.device_var = tk.StringVar(value="auto")
        self.device_cb = ttk.Combobox(voice, textvariable=self.device_var,
            values=["auto", "cpu", "cuda"], state="readonly")
        self.device_cb.grid(row=1, column=1, padx=6, pady=5, sticky="ew")

        ttk.Label(voice, text="Threads:").grid(row=2, column=0, padx=6, pady=5, sticky="w")
        self.threads_var = tk.IntVar(value=12)
        self.threads_entry = ttk.Entry(voice, textvariable=self.threads_var)
        self.threads_entry.grid(row=2, column=1, padx=6, pady=5, sticky="ew")

        self.voice_btn = ttk.Button(voice, text="Spracherkennung starten",
                                    command=self.toggle_voice)
        self.voice_btn.grid(row=3, column=0, columnspan=2, padx=6, pady=(2, 8), sticky="ew")

        # Actions
        actions = ttk.LabelFrame(sidebar, text="Aktionen")
        actions.pack(fill="x", pady=8)

        ttk.Button(actions, text="⌂  Home  (G28)", command=self.home_plotter).pack(
            fill="x", padx=8, pady=(8, 4))
        self.plot_btn = ttk.Button(actions, text="▶  PLOTTEN STARTEN",
                                   command=self.start_plot, style="Accent.TButton")
        self.plot_btn.pack(fill="x", padx=8, pady=4)
        ttk.Button(actions, text="■  STOP / NOT-AUS",
                   command=self.stop_plot, style="Stop.TButton").pack(
            fill="x", padx=8, pady=(4, 10))

        # Text input
        text_frame = ttk.LabelFrame(main, text="Erkannter Text / Eingabe")
        text_frame.pack(fill="x", pady=(0, 8))

        self.text_input = tk.Text(text_frame, height=8,
            bg=T["bg_widget"], fg=T["fg"],
            insertbackground=T["fg"], relief="flat",
            font=("Segoe UI", 11), padx=8, pady=6)
        self.text_input.pack(fill="both", expand=True, padx=6, pady=(6, 4))

        ttk.Button(text_frame, text="Vorschau aktualisieren",
                   command=self.update_preview).pack(anchor="e", padx=8, pady=(0, 8))

        # Log console
        log_frame = ttk.LabelFrame(main, text="Log / Konsole")
        log_frame.pack(fill="both", expand=True)

        self.log_out = scrolledtext.ScrolledText(log_frame, state="disabled",
            font=("Consolas", 9), bg=T["bg_log"], fg=T["fg_accent"],
            insertbackground=T["fg"], relief="flat", padx=6, pady=6)
        self.log_out.pack(fill="both", expand=True, padx=6, pady=6)

    def _build_alignment_tab(self, parent):
        T = self.THEME
        parent.columnconfigure(0, weight=0)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)

        A5_PX_W, A5_PX_H = 350, int(350 * 1.4142)

        canvas_frame = ttk.LabelFrame(parent, text="A5-Vorschau")
        canvas_frame.grid(row=0, column=0, sticky="ns", padx=(10, 5), pady=10)

        self.align_canvas = tk.Canvas(
            canvas_frame, width=A5_PX_W, height=A5_PX_H,
            bg="white", highlightthickness=1,
            highlightbackground=T["border"]
        )
        self.align_canvas.pack(padx=8, pady=8)

        right = ttk.Frame(parent)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)

        # Font size
        font_frame = ttk.LabelFrame(right, text="Schrift")
        font_frame.pack(fill="x", pady=(0, 8))
        font_frame.columnconfigure(1, weight=1)

        ttk.Label(font_frame, text="Größe:").grid(row=0, column=0, padx=6, pady=8, sticky="w")
        self.font_size_var = tk.StringVar(value="1.0")
        self.font_size_entry = ttk.Entry(font_frame, textvariable=self.font_size_var, width=8)
        self.font_size_entry.grid(row=0, column=1, padx=6, pady=8, sticky="w")
        ttk.Button(font_frame, text="Anwenden",
                   command=self._apply_font_size).grid(row=0, column=2, padx=(0, 6), pady=8)
        self.font_size_var.trace_add("write", self._on_font_size_changed)

        # Offset calibration
        off_frame = ttk.LabelFrame(right, text="Start-Offset (mm)")
        off_frame.pack(fill="x", pady=8)
        off_frame.columnconfigure(1, weight=1)

        ttk.Label(off_frame, text="X:").grid(row=0, column=0, padx=6, pady=8, sticky="w")
        self.offset_x_var = tk.StringVar(value="0.0")
        ttk.Entry(off_frame, textvariable=self.offset_x_var, width=10).grid(
            row=0, column=1, padx=6, pady=8, sticky="w")

        ttk.Label(off_frame, text="Y:").grid(row=1, column=0, padx=6, pady=8, sticky="w")
        self.offset_y_var = tk.StringVar(value="0.0")
        ttk.Entry(off_frame, textvariable=self.offset_y_var, width=10).grid(
            row=1, column=1, padx=6, pady=8, sticky="w")

        self.offset_x_var.trace_add("write",
            lambda *_: (self._update_alignment_canvas(), self._save_ui_config()))
        self.offset_y_var.trace_add("write",
            lambda *_: (self._update_alignment_canvas(), self._save_ui_config()))

        # Plotter settings — writing_speed / air_speed (from stt-overhaul)
        plotter_frame = ttk.LabelFrame(right, text="Plotter-Einstellungen")
        plotter_frame.pack(fill="x", pady=8)
        plotter_frame.columnconfigure(1, weight=1)

        ttk.Label(plotter_frame, text="Stift HOCH (mm):").grid(
            row=0, column=0, padx=6, pady=6, sticky="w")
        self.z_up_var = tk.StringVar(value="5.0")
        self.z_up_entry = ttk.Entry(plotter_frame, textvariable=self.z_up_var, width=8)
        self.z_up_entry.grid(row=0, column=1, padx=6, pady=6, sticky="w")

        ttk.Label(plotter_frame, text="Stift RUNTER (mm):").grid(
            row=1, column=0, padx=6, pady=6, sticky="w")
        self.z_down_var = tk.StringVar(value="0.0")
        self.z_down_entry = ttk.Entry(plotter_frame, textvariable=self.z_down_var, width=8)
        self.z_down_entry.grid(row=1, column=1, padx=6, pady=6, sticky="w")

        ttk.Label(plotter_frame, text="Schreib-Speed (Z unten):").grid(
            row=2, column=0, padx=6, pady=6, sticky="w")
        self.writing_speed_var = tk.StringVar(value="1000")
        self.writing_speed_entry = ttk.Entry(plotter_frame, textvariable=self.writing_speed_var, width=8)
        self.writing_speed_entry.grid(row=2, column=1, padx=6, pady=6, sticky="w")

        ttk.Label(plotter_frame, text="Luft-Speed (Z oben):").grid(
            row=3, column=0, padx=6, pady=6, sticky="w")
        self.air_speed_var = tk.StringVar(value="3000")
        self.air_speed_entry = ttk.Entry(plotter_frame, textvariable=self.air_speed_var, width=8)
        self.air_speed_entry.grid(row=3, column=1, padx=6, pady=6, sticky="w")

        ttk.Button(plotter_frame, text="Speichern", command=self.save_settings).grid(
            row=4, column=0, columnspan=2, padx=6, pady=(2, 8), sticky="ew")

        ttk.Button(right, text="Vorschau aktualisieren",
                   command=self._update_alignment_canvas).pack(fill="x", pady=(8, 0))

    def _update_alignment_canvas(self):
        self.align_canvas.delete("all")
        if not self.current_paths:
            return
        try:
            ox = float(self.offset_x_var.get())
            oy = float(self.offset_y_var.get())
        except ValueError:
            return

        A5_PX_H = int(350 * 1.4142)
        SCALE = 2.0

        for path in self.current_paths:
            if len(path) < 2:
                continue
            pts = []
            for (x, y) in path:
                pts.append((x + ox) * SCALE)
                pts.append(A5_PX_H - (y + oy) * SCALE)
            self.align_canvas.create_line(pts, fill=self.THEME["fg_plot_line"], width=1)

    def load_config_to_ui(self):
        _default = {
            "whisper": {"model_size": "medium", "device": "auto", "threads": 12, "language": "de"},
            "stt_settings": {"silence_threshold": 0.01, "silence_duration": 0.8,
                             "min_speech_duration": 0.5, "max_buffer_seconds": 30,
                             "undo_keyword": "Dino"},
            "plotter": {"z_up": 5.0, "z_down": 0.0, "writing_speed": 1000, "air_speed": 3000,
                        "port": "", "baudrate": 115200, "offset_x": 0.0, "offset_y": 0.0},
            "paths": {"audio_input": "data/input/audio/", "gcode_output": "data/output/gcode/"},
            "vectorization": {"scale": 1.0, "line_spacing": 15.0, "char_spacing": 5.0,
                              "printable_width_mm": 130.0},
        }
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            cfg = _default
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=4)

        p = cfg.get("plotter", {})
        w = cfg.get("whisper", {})
        v = cfg.get("vectorization", {})
        self.port_var.set(p.get("port", ""))
        self.model_var.set(w.get("model_size", "medium"))
        self.threads_var.set(w.get("threads", 12))
        self.device_var.set(w.get("device", "auto"))
        self.z_up_var.set(p.get("z_up", 5.0))
        self.z_down_var.set(p.get("z_down", 0.0))
        self.writing_speed_var.set(p.get("writing_speed", 1000))
        self.air_speed_var.set(p.get("air_speed", 3000))
        self.font_size_var.set(v.get("scale", 1.0))
        self.offset_x_var.set(p.get("offset_x", 0.0))
        self.offset_y_var.set(p.get("offset_y", 0.0))

    def validate_fields(self):
        valid = True
        fields = [
            (self.z_up_var, self.z_up_entry, "Stift HOCH"),
            (self.z_down_var, self.z_down_entry, "Stift RUNTER"),
            (self.writing_speed_var, self.writing_speed_entry, "Schreib-Speed"),
            (self.air_speed_var, self.air_speed_entry, "Luft-Speed"),
            (self.port_var, self.port_cb, "Port")
        ]

        for var, widget, name in fields:
            val = var.get().strip()
            if not val:
                if isinstance(widget, ttk.Entry) or isinstance(widget, ttk.Combobox):
                    widget.configure(style="Invalid.TEntry" if isinstance(widget, ttk.Entry) else "Invalid.TCombobox")
                try: widget.config(background="red")
                except: pass
                self.log(f"WARNUNG: Feld '{name}' muss ausgefüllt werden.")
                valid = False
            else:
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
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)

            cfg["plotter"]["port"] = self.port_var.get()
            cfg["plotter"]["z_up"] = float(self.z_up_var.get())
            cfg["plotter"]["z_down"] = float(self.z_down_var.get())
            cfg["plotter"]["writing_speed"] = int(self.writing_speed_var.get())
            cfg["plotter"]["air_speed"] = int(self.air_speed_var.get())
            cfg["plotter"]["offset_x"] = float(self.offset_x_var.get() or 0)
            cfg["plotter"]["offset_y"] = float(self.offset_y_var.get() or 0)
            cfg["whisper"]["model_size"] = self.model_var.get()
            cfg["whisper"]["threads"] = self.threads_var.get()
            cfg["whisper"]["device"] = self.device_var.get()
            cfg.setdefault("vectorization", {})["scale"] = float(self.font_size_var.get() or 1.0)

            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=4)

            self.plotter.load_config()
            self.generator.load_config()
            self.converter.load_config()
            if self.recognizer:
                self.recognizer.reload_config()
            self.log("Einstellungen gespeichert.")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Einstellungen nicht speichern: {e}")

    def _save_ui_config(self):
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
            cfg.setdefault("plotter", {})["offset_x"] = float(self.offset_x_var.get())
            cfg.setdefault("plotter", {})["offset_y"] = float(self.offset_y_var.get())
            cfg.setdefault("vectorization", {})["scale"] = float(self.font_size_var.get())
            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=4)
        except (ValueError, FileNotFoundError, json.JSONDecodeError):
            pass

    def _on_font_size_changed(self, *_):
        try:
            scale = float(self.font_size_var.get())
            self.converter.settings["scale"] = scale
            self.update_preview()
        except ValueError:
            pass

    def _apply_font_size(self):
        try:
            scale = float(self.font_size_var.get())
        except ValueError:
            messagebox.showwarning("Ungültig", "Schriftgröße muss eine gültige Zahl sein.")
            return
        self.converter.settings["scale"] = scale
        self._save_ui_config()
        self.update_preview()
        self.log(f"Schriftgröße übernommen: {scale}")

    def log(self, message, category="app"):
        self.log_out.config(state="normal")
        self.log_out.insert("end", f"{time.strftime('%H:%M:%S')} {message}\n")
        self.log_out.see("end")
        self.log_out.config(state="disabled")
        self.logger.write(category, message)

    def refresh_ports(self):
        ports = self.plotter.list_ports()
        self.port_cb["values"] = ports
        if ports:
            self.port_cb["width"] = max(len(p) for p in ports)
            self.port_cb.current(0)

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

            def load_and_start():
                try:
                    if not self.recognizer:
                        self.recognizer = SpeechRecognizer(
                            config_path=CONFIG_PATH,
                            callback=self._on_speech_recognized,
                            status_callback=self._on_status_update
                        )
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

    def _on_speech_recognized(self, result):
        self.after(0, lambda r=result: self._handle_stt_result(r))

    def _handle_stt_result(self, result):
        if result.get("undo"):
            self._undo_last_sentence()
            return
        text = result["text"]
        confidence = result["confidence"]
        self.text_input.insert("end", f"{text}\n")
        self.log(f"Erkannt ({confidence:.1f}% Konfidenz): {text}", category="stt_transkripte")
        self.update_preview()

    def _undo_last_sentence(self):
        content = self.text_input.get("1.0", "end-1c")
        lines = content.split("\n")
        while lines and not lines[-1].strip():
            lines.pop()
        if lines:
            removed = lines.pop()
            self.text_input.delete("1.0", "end")
            new_text = "\n".join(lines)
            if new_text:
                self.text_input.insert("1.0", new_text + "\n")
            self.log(f"UNDO: '{removed}' gelöscht.", category="stt_transkripte")
            self.update_preview()
        else:
            self.log("UNDO: Kein Text zum Löschen vorhanden.", category="stt_transkripte")

    def _on_status_update(self, message):
        self.after(0, lambda: self.log(message, category="whisper_system"))

    def update_preview(self):
        text = self.text_input.get("1.0", "end").strip()
        if not text:
            return

        max_w = self.converter.settings.get("printable_width_mm", 130.0)
        wrapped = self.converter.wrap_text(text, max_w)
        self.current_paths = self.converter.text_to_paths(wrapped, start_x=10, start_y=205)

        self._update_alignment_canvas()

    def start_plot(self):
        if not self.validate_fields():
            return

        if not self.current_paths:
            messagebox.showwarning("Kein Text", "Bitte geben Sie Text ein oder nutzen Sie die Spracherkennung.")
            return

        if not self.plotter.ser or not self.plotter.ser.is_open:
            messagebox.showwarning("Nicht verbunden", "Bitte verbinden Sie zuerst den Plotter.")
            return

        try:
            ox = float(self.offset_x_var.get())
            oy = float(self.offset_y_var.get())
        except ValueError:
            ox, oy = 0.0, 0.0

        shifted_paths = [[(x + ox, y + oy) for x, y in path] for path in self.current_paths]
        gcode = self.generator.generate_gcode(shifted_paths)
        self.plotter.start_plotting(gcode)

    def stop_plot(self):
        self.plotter.stop_plotting()
        if self.plotter.ser and self.plotter.ser.is_open:
            self.plotter.ser.write(b"M112\n")

    def home_plotter(self):
        if self.plotter.ser and self.plotter.ser.is_open:
            self.plotter.send_line("G28")

    def on_closing(self):
        if self.recognizer:
            self.recognizer.stop()
            self.recognizer.logger.close()
        self.plotter.disconnect()
        self.logger.close()
        self.destroy()

if __name__ == "__main__":
    app = PlotterUI()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
