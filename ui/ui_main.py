import os
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import threading
import time

# Absolute path to config — works regardless of working directory
_UI_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_UI_DIR)
CONFIG_PATH = os.path.join(_PROJECT_DIR, "data", "config.json")

# Import core modules
from core.speech_to_text import SpeechRecognizer
from core.text_vectorization import TextToPathConverter
from core.gcode_converter import GCodeGenerator
from core.serial_comm import SerialPlotter

class PlotterUI(tk.Tk):
    def __init__(self):
        super().__init__()
        # ── THEME ── change colors here, nowhere else ──────────────────────
        self.THEME = {
            "bg":           "#1e1e1e",   # window / panel background
            "bg_widget":    "#2d2d2d",   # entry / combobox / text fields
            "bg_log":       "#141414",   # log console background
            "bg_button":    "#3a3a3a",   # button face
            "bg_button_hover": "#505050",
            "fg":           "#d4d4d4",   # normal text
            "fg_accent":    "#9cdcfe",   # labels, log text, section titles
            "fg_error":     "#f44747",   # validation error highlight
            "fg_plot_line": "#4ec9b0",   # vector preview lines on canvas
            "border":       "#444444",
        }
        T = self.THEME  # shorthand used below

        self.configure(bg=T["bg"])
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".",
            background=T["bg"], foreground=T["fg"],
            fieldbackground=T["bg_widget"], bordercolor=T["border"],
            darkcolor=T["bg"], lightcolor=T["bg_widget"])
        style.configure("TLabelframe",       background=T["bg"],   foreground=T["fg"])
        style.configure("TLabelframe.Label", background=T["bg"],   foreground=T["fg_accent"])
        style.configure("TLabel",            background=T["bg"],   foreground=T["fg"])
        style.configure("TFrame",            background=T["bg"])
        style.configure("TButton",           background=T["bg_button"], foreground=T["fg"], borderwidth=1)
        style.map("TButton",                 background=[("active", T["bg_button_hover"])])
        style.configure("TEntry",            fieldbackground=T["bg_widget"], foreground=T["fg"],
                                            insertcolor=T["fg"])
        style.configure("TCombobox",         fieldbackground=T["bg_widget"], foreground=T["fg"],
                                            selectbackground=T["bg_widget"])
        style.map("TCombobox",               fieldbackground=[("readonly", T["bg_widget"])])

        # Validation styles — driven by THEME, don't touch these
        style.configure("Invalid.TEntry",    fieldbackground=T["fg_error"])
        style.configure("Invalid.TCombobox", fieldbackground=T["fg_error"])
        # ────────────────────────────────────────────────────────────────────
        self.title("Fenster")
        self.state("zoomed")
        # Core instances
        self.recognizer = None
        self.converter = TextToPathConverter(config_path=CONFIG_PATH)
        self.generator = GCodeGenerator(config_path=CONFIG_PATH)
        self.plotter = SerialPlotter(config_path=CONFIG_PATH, log_callback=self.log)

        # State
        self.current_paths = []

        self.create_widgets()
        self.load_config_to_ui()


    def create_widgets(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Tab 1 — existing controls
        main_frame = ttk.Frame(notebook)
        notebook.add(main_frame, text="Steuerung")

        # Tab 2 — preview & alignment
        align_frame = ttk.Frame(notebook)
        notebook.add(align_frame, text="Vorschau & Ausrichtung")

        # Main layout: Left (Controls), Right (Preview)
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
        ports = self.plotter.list_ports()
        self.port_cb = ttk.Combobox(conn_frame, textvariable=self.port_var,
            values=ports, width=max((len(p) for p in ports), default=20))
        self.port_cb.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Button(conn_frame, text="Aktualisieren", command=self.refresh_ports).grid(row=0, column=2, padx=5, pady=5)

        self.connect_btn = ttk.Button(conn_frame, text="Verbinden", command=self.toggle_connection)
        self.connect_btn.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="ew")

        # 2. Whisper Frame
        whisper_frame = ttk.LabelFrame(left_panel, text="Spracherkennung (Whisper)")
        whisper_frame.pack(fill="x", pady=10)

        ttk.Label(whisper_frame, text="Modell:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.model_var = tk.StringVar(value="medium")
        _whisper_models = ["small", "medium", "large"]
        self.model_cb = ttk.Combobox(whisper_frame, textvariable=self.model_var,
                                     values=_whisper_models, state="readonly")
        self.model_cb.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

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

        ttk.Label(settings_frame, text="Schriftgröße:").grid(row=3, column=0, padx=5, pady=2, sticky="w")
        self.font_size_var = tk.StringVar(value="1.0")
        self.font_size_entry = ttk.Entry(settings_frame, textvariable=self.font_size_var, width=8)
        self.font_size_entry.grid(row=3, column=1, padx=5, pady=2)
        self.font_size_var.trace_add("write", self._on_font_size_changed)

        ttk.Button(settings_frame, text="Schriftgröße anwenden", command=self._apply_font_size).grid(row=4, column=0, columnspan=2, padx=5, pady=2, sticky="ew")
        ttk.Button(settings_frame, text="Speichern", command=self.save_settings).grid(row=5, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        # 4. Action Frame
        action_frame = ttk.LabelFrame(left_panel, text="Aktionen")
        action_frame.pack(fill="x", pady=10)

        ttk.Button(action_frame, text="Home (G28)", command=self.home_plotter).pack(fill="x", padx=5, pady=2)
        self.plot_btn = ttk.Button(action_frame, text="PLOTTEN STARTEN", command=self.start_plot)
        self.plot_btn.pack(fill="x", padx=5, pady=10)
        ttk.Button(action_frame, text="STOP / Not-Aus", command=self.stop_plot).pack(fill="x", padx=5, pady=2)

        # --- RIGHT PANEL: Preview & Console ---

        # 1. Text Input / Recognized Text
        text_frame = ttk.LabelFrame(right_panel, text="Erkannter Text / Eingabe")
        text_frame.pack(fill="x", pady=10)

        self.text_input = tk.Text(text_frame, height=3,
            bg=self.THEME["bg_widget"], fg=self.THEME["fg"],
            insertbackground=self.THEME["fg"], relief="flat")
        self.text_input.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        ttk.Button(text_frame, text="Vorschau\naktualisieren", command=self.update_preview).pack(side="right", padx=5, pady=5)

        # 3. Console/Log
        log_frame = ttk.LabelFrame(right_panel, text="Log / Konsole")
        log_frame.pack(fill="both", expand=True)

        self.log_out = scrolledtext.ScrolledText(log_frame, height=8, state="disabled",
    font=("Consolas", 9), bg=self.THEME["bg_log"], fg=self.THEME["fg_accent"],
    insertbackground=self.THEME["fg"], relief="flat")
        self.log_out.pack(fill="both", expand=True, padx=5, pady=5)

        self._build_alignment_tab(align_frame)

    def _build_alignment_tab(self, parent):
        T = self.THEME
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)

        A5_PX_W, A5_PX_H = 350, int(350 * 1.4142)

        canvas_frame = ttk.LabelFrame(parent, text="A5-Vorschau")
        canvas_frame.grid(row=0, column=0, sticky="nsew", padx=(5, 10), pady=5)

        self.align_canvas = tk.Canvas(
            canvas_frame, width=A5_PX_W, height=A5_PX_H,
            bg="white", highlightthickness=1,
            highlightbackground=T["border"]
        )
        self.align_canvas.pack(padx=5, pady=5)

        ctrl_frame = ttk.Frame(parent)
        ctrl_frame.grid(row=0, column=1, sticky="n", padx=(0, 5), pady=5)

        off_frame = ttk.LabelFrame(ctrl_frame, text="Start-Offset (mm)")
        off_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(off_frame, text="X:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.offset_x_var = tk.StringVar(value="0.0")
        ttk.Entry(off_frame, textvariable=self.offset_x_var, width=8).grid(row=0, column=1, padx=5)

        ttk.Label(off_frame, text="Y:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.offset_y_var = tk.StringVar(value="0.0")
        ttk.Entry(off_frame, textvariable=self.offset_y_var, width=8).grid(row=1, column=1, padx=5)

        self.offset_x_var.trace_add("write", lambda *_: (self._update_alignment_canvas(), self._save_ui_config()))
        self.offset_y_var.trace_add("write", lambda *_: (self._update_alignment_canvas(), self._save_ui_config()))

        ttk.Button(ctrl_frame, text="Vorschau aktualisieren",
                   command=self._update_alignment_canvas).pack(fill="x", pady=5)

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
            "plotter": {"z_up": 5.0, "z_down": 0.0, "feedrate": 1500, "port": "",
                        "baudrate": 115200, "offset_x": 0.0, "offset_y": 0.0},
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
        self.feed_var.set(p.get("feedrate", 1500))
        self.font_size_var.set(v.get("scale", 1.0))
        self.offset_x_var.set(p.get("offset_x", 0.0))
        self.offset_y_var.set(p.get("offset_y", 0.0))

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
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)

            cfg["plotter"]["port"] = self.port_var.get()
            cfg["plotter"]["z_up"] = float(self.z_up_var.get())
            cfg["plotter"]["z_down"] = float(self.z_down_var.get())
            cfg["plotter"]["feedrate"] = int(self.feed_var.get())
            cfg["plotter"]["offset_x"] = float(self.offset_x_var.get() or 0)
            cfg["plotter"]["offset_y"] = float(self.offset_y_var.get() or 0)
            cfg["whisper"]["model_size"] = self.model_var.get()
            cfg["whisper"]["threads"] = self.threads_var.get()
            cfg["whisper"]["device"] = self.device_var.get()
            cfg.setdefault("vectorization", {})["scale"] = float(self.font_size_var.get() or 1.0)

            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=4)

            # Update instances
            self.plotter.load_config()
            self.generator.load_config()
            self.converter.load_config()
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

    def log(self, message):
        self.log_out.config(state="normal")
        self.log_out.insert("end", f"{time.strftime('%H:%M:%S')} {message}\n")
        self.log_out.see("end")
        self.log_out.config(state="disabled")

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

            # Modellladen in separatem Thread, um UI nicht zu blockieren
            def load_and_start():
                try:
                    if not self.recognizer:
                        self.recognizer = SpeechRecognizer(config_path=CONFIG_PATH, callback=self._on_speech_recognized)

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

        # Word-wrap then vectorise
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
        # Not-Aus an Plotter senden
        if self.plotter.ser and self.plotter.ser.is_open:
            self.plotter.ser.write(b"M112\n")

    def home_plotter(self):
        if self.plotter.ser and self.plotter.ser.is_open:
            self.plotter.send_line("G28")

    def on_closing(self):
        if self.recognizer:
            self.recognizer.stop()
        self.plotter.disconnect()
        self.destroy()

