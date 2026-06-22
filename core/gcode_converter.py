import json
import os

class GCodeGenerator:
    """
    Konvertiert Vektorpfade (Punktlisten) in GRBL-kompatiblen G-Code.
    Verwendet Z-Achse für Stift hoch/runter Logik.
    """

    def __init__(self, config_path="data/config.json"):
        self.config_path = config_path
        self.load_config()

    def load_config(self):
        """Lädt Plotter-Einstellungen aus der JSON-Datei."""
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
                plotter_cfg = config.get("plotter", {})
                self.z_up = plotter_cfg.get("z_up", 5.0)
                self.z_down = plotter_cfg.get("z_down", 0.0)
                self.writing_speed = plotter_cfg.get("writing_speed", 1000)
                self.air_speed = plotter_cfg.get("air_speed", 3000)
                self.start_gcode = plotter_cfg.get("start_gcode", ["G21", "G90", "G28"])
                self.end_gcode = plotter_cfg.get("end_gcode", ["G1 Z5.0", "G28 X0 Y0", "M84"])
        except Exception:
            self.z_up = 5.0
            self.z_down = 0.0
            self.writing_speed = 1000
            self.air_speed = 3000
            self.start_gcode = ["G21", "G90", "G28"]
            self.end_gcode = ["G1 Z5.0", "G28 X0 Y0", "M84"]

    def generate_gcode(self, all_paths):
        """
        Hauptmethode: Konvertiert eine Liste von Pfaden in G-Code Zeilen.
        Jeder Pfad in 'all_paths' ist eine Liste von (x, y) Tupeln.
        """
        gcode = []

        # Start-Setup (Metrisch, Absolute Koordinaten, Home)
        for line in self.start_gcode:
            gcode.append(line)

        # Sicherstellen, dass der Stift oben ist (Travel-Move -> air_speed)
        gcode.append(f"G1 Z{self.z_up} F{self.air_speed}")

        for path in all_paths:
            if not path:
                continue

            # 1. Zu erstem Punkt des Pfades fahren (Stift oben -> air_speed)
            start_x, start_y = path[0]
            gcode.append(f"G1 X{start_x:.3f} Y{start_y:.3f} F{self.air_speed}")

            # 2. Stift runter (danach gilt writing_speed fürs Zeichnen)
            gcode.append(f"G1 Z{self.z_down} F{self.writing_speed}")

            # 3. Den Pfad abfahren (Zeichnen -> writing_speed)
            for point in path[1:]:
                x, y = point
                gcode.append(f"G1 X{x:.3f} Y{y:.3f} F{self.writing_speed}")

            # 4. Stift wieder hoch nach Ende des Pfades (Travel-Move -> air_speed)
            gcode.append(f"G1 Z{self.z_up} F{self.air_speed}")

        # Ende-Sequenz
        for line in self.end_gcode:
            gcode.append(line)

        return gcode

    def save_gcode_to_file(self, gcode_lines, filepath):
        """Speichert die G-Code Zeilen in einer Datei."""
        try:
            with open(filepath, "w") as f:
                for line in gcode_lines:
                    f.write(line + "\n")
            print(f"G-Code erfolgreich gespeichert in: {filepath}")
            return True
        except Exception as e:
            print(f"Fehler beim Speichern der G-Code Datei: {e}")
            return False

if __name__ == "__main__":
    # Test-Code
    generator = GCodeGenerator()
    test_paths = [[(0,0), (10,0), (10,10), (0,10), (0,0)], [(20,20), (30,30)]]
    gcode = generator.generate_gcode(test_paths)
    for line in gcode[:15]:
        print(line)
    print("...")
