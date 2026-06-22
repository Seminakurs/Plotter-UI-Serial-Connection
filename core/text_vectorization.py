import json
import os

from HersheyFonts import HersheyFonts

from core.ttf_font_loader import TTFFontLoader, HERSHEY_CAP_HEIGHT_UNITS


# Pfad für externe Schriftarten (TTF/OTF). Hershey-Fonts kommen aus der Lib.
FONTS_DIR = os.path.join("data", "input", "fonts")

# Hand-kuratierte Auswahl der lesbaren Hershey-Fonts.
HERSHEY_PRESETS = [
    ("hershey:rowmand",   "Hershey: Roman Duplex"),
    ("hershey:rowmans",   "Hershey: Roman Simplex"),
    ("hershey:scripts",   "Hershey: Script Simplex"),
    ("hershey:cursive",   "Hershey: Cursive"),
    ("hershey:futural",   "Hershey: Futura"),
    ("hershey:gothicger", "Hershey: Gothic German"),
    ("hershey:timesr",    "Hershey: Times Roman"),
]


class _HersheyBackend:
    """Backend für Hershey-Fonts via HersheyFonts-Bibliothek."""

    def __init__(self, hf):
        self.hf = hf

    def strokes_for_text(self, char):
        return self.hf.strokes_for_text(char)

    def char_width(self, char, strokes):
        # Hershey-API exponiert die Breite nicht direkt — wir nehmen die
        # maximale X-Koordinate aller Strokes als Annäherung.
        width = 0
        for stroke in strokes:
            for (px, _py) in stroke:
                if px > width:
                    width = px
        return width if width > 0 else 10


class _TTFBackend:
    """Backend für TTF/OTF-Fonts via TTFFontLoader (vektorisierte Glyphen)."""

    def __init__(self, loader):
        self.loader = loader

    def strokes_for_text(self, char):
        return self.loader.strokes_for_text(char)

    def char_width(self, char, _strokes):
        w = self.loader.char_width(char)
        return w if w > 0 else 10


class TextToPathConverter:
    """Wandelt Text-Strings in Vektorpfade (Punktlisten) um.

    Unterstützt zwei Backends:
      * Hershey-Fonts (Single-Stroke, Standard) — IDs "hershey:<name>"
      * TTF/OTF aus data/input/fonts/      — IDs "ttf:<dateiname>"

    Bei Auswahl eines TTF-Fonts werden die Glyph-Konturen zuerst zu
    Polylinien vektorisiert (Beziers subteilen), anschließend wandert das
    Ergebnis durch dieselbe Layout- und G-Code-Pipeline wie Hershey.
    """

    DEFAULT_FONT = "hershey:rowmand"

    def __init__(self, config_path="data/config.json"):
        self.config_path = config_path
        self.backend = None
        self.font_id = self.DEFAULT_FONT
        self.load_config()
        # Initiales Backend laden
        self.set_font(self.settings.get("font", self.DEFAULT_FONT))

    def load_config(self):
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
                self.settings = config.get("vectorization", {
                    "scale": 1.0,
                    "line_spacing": 15.0,
                    "char_spacing": 5.0,
                })
        except Exception:
            self.settings = {"scale": 1.0, "line_spacing": 15.0, "char_spacing": 5.0}

    @staticmethod
    def list_available_fonts():
        """Liste verfügbarer Fonts: [(id, display_name), ...].

        Hershey-Presets stehen vorne, danach alle TTF/OTF aus FONTS_DIR.
        """
        fonts = list(HERSHEY_PRESETS)
        if os.path.isdir(FONTS_DIR):
            for entry in sorted(os.listdir(FONTS_DIR)):
                if entry.lower().endswith((".ttf", ".otf")):
                    fonts.append((f"ttf:{entry}", f"TTF: {entry}"))
        return fonts

    def set_font(self, font_id):
        """Wechselt das Backend. Fällt bei Fehlern still zurück auf Hershey."""
        try:
            if font_id.startswith("hershey:"):
                name = font_id.split(":", 1)[1] or "rowmand"
                hf = HersheyFonts()
                hf.load_default_font(name)
                self.backend = _HersheyBackend(hf)
            elif font_id.startswith("ttf:"):
                filename = font_id.split(":", 1)[1]
                path = os.path.join(FONTS_DIR, filename)
                self.backend = _TTFBackend(TTFFontLoader(path))
            else:
                raise ValueError(f"Unbekannte Font-ID: {font_id}")
            self.font_id = font_id
        except Exception as e:
            print(f"Warnung: Font '{font_id}' konnte nicht geladen werden: {e}")
            if self.backend is None and font_id != self.DEFAULT_FONT:
                # Fallback auf Default, damit der Konverter benutzbar bleibt
                self.set_font(self.DEFAULT_FONT)

    def text_to_paths(self, text, start_x=0, start_y=0):
        """Wandelt einen Text in eine Liste von Pfaden um.
        Ein Pfad ist eine Liste von (x, y) Tupeln (Plotter-Koordinaten, Y+ = oben).
        """
        if not self.backend:
            print("Fehler: Kein Font geladen.")
            return []

        all_paths = []
        current_x = start_x
        current_y = start_y
        scale = self.settings.get("scale", 1.0)

        lines = text.split('\n')
        for line_text in lines:
            line_x = current_x
            for char in line_text:
                strokes = list(self.backend.strokes_for_text(char))
                char_width = self.backend.char_width(char, strokes)

                for stroke in strokes:
                    transformed_path = [
                        (line_x + px * scale, current_y - py * scale)
                        for (px, py) in stroke
                    ]
                    all_paths.append(transformed_path)

                line_x += (char_width + self.settings.get("char_spacing", 5.0)) * scale

            # Zeilenvorschub: Hershey-Cap-Height (≈21) ist der gemeinsame
            # Bezugswert — TTF-Glyphen sind auf denselben Maßstab normalisiert.
            line_multiplier = self.settings.get("line_height_multiplier", 1.5)
            current_y -= HERSHEY_CAP_HEIGHT_UNITS * scale * line_multiplier

        return all_paths

    def measure_line_width(self, text_line):
        """Breite einer ungebrochenen Zeile in Plotter-Einheiten (mm)."""
        if not self.backend:
            return 0.0
        scale = self.settings.get("scale", 1.0)
        char_spacing = self.settings.get("char_spacing", 5.0)
        total = 0.0
        for char in text_line:
            strokes = list(self.backend.strokes_for_text(char))
            char_w = self.backend.char_width(char, strokes)
            total += (char_w + char_spacing) * scale
        return total

    def wrap_text(self, text, max_width_mm):
        """Bricht Text auf max_width_mm um, erhält explizite Newlines."""
        lines = []
        for paragraph in text.split('\n'):
            words = paragraph.split(' ')
            current = []
            for word in words:
                candidate = ' '.join(current + [word])
                if current and self.measure_line_width(candidate) > max_width_mm:
                    lines.append(' '.join(current))
                    current = [word]
                else:
                    current.append(word)
            lines.append(' '.join(current))
        return '\n'.join(lines)


if __name__ == "__main__":
    converter = TextToPathConverter()
    sample_text = "ABC"
    paths = converter.text_to_paths(sample_text)
    print(f"Hershey – '{sample_text}' in {len(paths)} Pfade umgewandelt.")

    fonts = TextToPathConverter.list_available_fonts()
    ttf_fonts = [fid for fid, _ in fonts if fid.startswith("ttf:")]
    if ttf_fonts:
        converter.set_font(ttf_fonts[0])
        paths = converter.text_to_paths(sample_text)
        print(f"{ttf_fonts[0]} – '{sample_text}' in {len(paths)} Pfade umgewandelt.")
