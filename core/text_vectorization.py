import json
import os
from HersheyFonts import HersheyFonts

class TextToPathConverter:
    """
    Wandelt Text-Strings in Vektorpfade (Punktlisten) um.
    Verwendet standardmäßig Hershey-Fonts für Single-Stroke-Schriften.
    """

    def __init__(self, config_path="data/config.json"):
        self.config_path = config_path
        self.hf = None
        self.load_config()

        # Initialisiere die Hershey-Font Bibliothek
        try:
            self.hf = HersheyFonts()
            # Standardfont laden (z.B. 'rowmand' für Roman Duplex)
            self.hf.load_default_font('rowmand')
        except Exception as e:
            print(f"Warnung: Hershey-Font konnte nicht geladen werden: {e}")

    def load_config(self):
        """Lädt Vektorisierungs-Einstellungen aus der JSON-Datei."""
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
                self.settings = config.get("vectorization", {
                    "scale": 1.0,
                    "line_spacing": 15.0,
                    "char_spacing": 5.0
                })
        except Exception:
            self.settings = {"scale": 1.0, "line_spacing": 15.0, "char_spacing": 5.0}

    def text_to_paths(self, text, start_x=0, start_y=0):
        """
        Hauptmethode: Wandelt einen Text in eine Liste von Pfaden um.
        Ein Pfad ist eine Liste von (x, y) Tupeln.
        """
        if not self.hf:
            print("Fehler: Kein Font geladen.")
            return []

        all_paths = []
        current_x = start_x
        current_y = start_y

        scale = self.settings.get("scale", 1.0)
        # HersheyFonts library uses a coordinate system where Y increases downwards.
        # We might need to invert Y for some plotters, but usually G-Code Y+ is up.
        # Let's assume we want Y+ as up for the plotter.

        lines = text.split('\n')
        for line_text in lines:
            # Die hershey-fonts Library bietet 'strokes_for_text', was direkt eine Liste/Generator
            # von Linien (Strokes) für den gesamten Text zurückgibt.
            # Allerdings brauchen wir die Kontrolle über Positionierung pro Zeichen für exaktes Layout.

            line_x = current_x
            for char in line_text:
                # Hole die Strokes für ein einzelnes Zeichen
                # strokes_for_text gibt einen Generator von (Punktliste) zurück
                strokes = list(self.hf.strokes_for_text(char))

                # Wir müssen die Breite des Zeichens wissen, um zum nächsten zu springen
                # Da HersheyFonts keine direkte 'get_width' für einzelne Zeichen im Textfluss
                # exponiert, die einfach zugänglich ist, berechnen wir die Bounds der Strokes.
                char_width = 0

                for stroke in strokes:
                    transformed_path = []
                    for (px, py) in stroke:
                        # Skalieren und Verschieben
                        # Wir nehmen an, dass Hershey Y nach unten positiv ist.
                        tx = line_x + (px * scale)
                        ty = current_y - (py * scale)
                        transformed_path.append((tx, ty))
                        char_width = max(char_width, px)
                    all_paths.append(transformed_path)

                # Vorschub zum nächsten Zeichen
                # Wenn das Zeichen keine Breite hat (z.B. Leerzeichen), nutzen wir einen Standardwert
                if char_width == 0:
                    char_width = 10

                line_x += (char_width + self.settings.get("char_spacing", 5.0)) * scale

            # Zeilenvorschub für die nächste Zeile im Text
            current_y -= self.settings.get("line_spacing", 15.0) * scale

        return all_paths

if __name__ == "__main__":
    # Test-Code
    converter = TextToPathConverter()
    sample_text = "ABC"
    paths = converter.text_to_paths(sample_text)
    print(f"Text '{sample_text}' in {len(paths)} Pfade umgewandelt.")
