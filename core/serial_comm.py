import serial
import serial.tools.list_ports
import time
import json
import threading
import queue

class SerialPlotter:
    """
    Steuert die serielle Kommunikation mit dem Plotter (GRBL).
    Sendet G-Code Zeilen und wartet auf Bestätigung ('ok').
    """

    def __init__(self, config_path="data/config.json", log_callback=None):
        self.config_path = config_path
        self.log_callback = log_callback
        self.ser = None
        self.running = False
        self.gcode_queue = queue.Queue()
        self.worker_thread = None

        self.load_config()

    def load_config(self):
        """Lädt serielle Einstellungen aus der JSON-Datei."""
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
                plotter_cfg = config.get("plotter", {})
                self.port = plotter_cfg.get("port", "")
                self.baudrate = plotter_cfg.get("baudrate", 115200)
        except Exception:
            self.port = ""
            self.baudrate = 115200

    def list_ports(self):
        """Gibt eine Liste der verfügbaren COM-Ports zurück."""
        ports = []
        for p in serial.tools.list_ports.comports():
            label = p.device
            if p.description and p.description != "n/a":
                label = f"{p.device} — {p.description}"
            ports.append(label)
        return ports

    def connect(self, port=None, baudrate=None):
        if port: self.port = port.split(" — ")[0].strip()  # strip description, keep only "COM5"
        if baudrate: self.baudrate = baudrate

        if not self.port:
            self._log("Fehler: Kein Port ausgewählt.")
            return False

        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            # Kurz warten, damit GRBL booten kann
            time.sleep(2)
            self.ser.flushInput()
            self._log(f"Verbunden mit {self.port} bei {self.baudrate} Baud.")
            return True
        except Exception as e:
            self._log(f"Verbindungsfehler: {e}")
            self.ser = None
            return False

    def disconnect(self):
        """Trennt die Verbindung zum Plotter."""
        self.stop_plotting()
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None
            self._log("Verbindung getrennt.")

    def _log(self, message):
        """Hilfsmethode zum Loggen von Nachrichten."""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(f"[SerialPlotter] {message}")

    def send_line(self, line):
        """Sendet eine einzelne G-Code Zeile und wartet auf 'ok'."""
        if not self.ser or not self.ser.is_open:
            self._log("Fehler: Nicht verbunden.")
            return False

        clean_line = line.strip()
        if not clean_line:
            return True

        try:
            # G-Code senden
            self.ser.write((clean_line + "\n").encode())
            self._log(f">>> {clean_line}")

            # Auf Bestätigung warten
            while self.running:  # ← check flag every iteration
                response = self.ser.readline().decode().strip()  # timeout=1 on Serial means this returns after 1s max
                if response:
                    self._log(f"<<< {response}")
                    if response.lower().startswith("ok"):
                        return True
                    elif "error" in response.lower():
                        self._log(f"Plotter Fehler: {response}")
                        return False
            return False
        except Exception as e:
            self._log(f"Fehler beim Senden: {e}")
            return False

    def start_plotting(self, gcode_lines):
        """Startet den Plot-Vorgang in einem Hintergrund-Thread."""
        if not self.ser or not self.ser.is_open:
            self._log("Fehler: Nicht verbunden.")
            return False

        if self.running:
            self._log("Warnung: Ein Plot-Vorgang läuft bereits.")
            return False

        self.running = True
        self.worker_thread = threading.Thread(
            target=self._plot_worker,
            args=(gcode_lines,),
            daemon=True
        )
        self.worker_thread.start()
        return True

    def stop_plotting(self):
        """Stoppt den aktuellen Plot-Vorgang."""
        self.running = False
        # Do NOT join — we need to return immediately so the
        # emergency M112 in ui_main can be sent right away
        self.worker_thread = None
        self._log("Plotting gestoppt.")

    def _plot_worker(self, gcode_lines):
        """Worker-Thread, der die G-Code Zeilen nacheinander abarbeitet."""
        self._log("Starte Plot-Vorgang...")
        for line in gcode_lines:
            if not self.running:
                break
            if not self.send_line(line):
                self._log("Abbruch wegen Fehler.")
                break

        self.running = False
        self._log("Plot-Vorgang beendet.")

if __name__ == "__main__":
    # Test-Code (ohne echte Hardware)
    plotter = SerialPlotter()
    ports = plotter.list_ports()
    print(f"Verfügbare Ports: {ports}")

    # Beispielhafter Aufruf (würde fehlschlagen ohne echten Port)
    # if ports:
    #     plotter.connect(ports[0])
    #     plotter.start_plotting(["G1 X10 Y10", "G1 X0 Y0"])
