"""TTF-One-Stroke-Font-Loader.

Liest TrueType-Schriften (.ttf/.otf) und liefert Glyphen als Polylinien
(Listen von (x, y)-Punkten) — kompatibel zur HersheyFonts-API, die der
TextToPathConverter erwartet.

Quadratische und kubische Bezier-Kurven werden in lineare Segmente
zerlegt. Koordinaten werden so normalisiert, dass die Cap-Height etwa
21 Einheiten entspricht (Hershey-Konvention), damit der bestehende
'scale'-Parameter aus data/config.json weiterhin Sinn ergibt.
"""

import os

from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen


HERSHEY_CAP_HEIGHT_UNITS = 21.0


class _StrokePen(BasePen):
    """Sammelt Konturen als Polylinien. Subteilt Bezier in Liniensegmente."""

    def __init__(self, glyph_set, segments_per_curve=8):
        super().__init__(glyph_set)
        self._segments = segments_per_curve
        self.strokes = []
        self._current = []

    def _moveTo(self, pt):
        self._flush()
        self._current = [pt]

    def _lineTo(self, pt):
        self._current.append(pt)

    def _qCurveToOne(self, pt1, pt2):
        p0 = self._current[-1] if self._current else (0.0, 0.0)
        for i in range(1, self._segments + 1):
            t = i / self._segments
            mt = 1.0 - t
            x = mt * mt * p0[0] + 2 * mt * t * pt1[0] + t * t * pt2[0]
            y = mt * mt * p0[1] + 2 * mt * t * pt1[1] + t * t * pt2[1]
            self._current.append((x, y))

    def _curveToOne(self, pt1, pt2, pt3):
        p0 = self._current[-1] if self._current else (0.0, 0.0)
        for i in range(1, self._segments + 1):
            t = i / self._segments
            mt = 1.0 - t
            x = (mt ** 3) * p0[0] + 3 * (mt ** 2) * t * pt1[0] \
                + 3 * mt * (t ** 2) * pt2[0] + (t ** 3) * pt3[0]
            y = (mt ** 3) * p0[1] + 3 * (mt ** 2) * t * pt1[1] \
                + 3 * mt * (t ** 2) * pt2[1] + (t ** 3) * pt3[1]
            self._current.append((x, y))

    def _closePath(self):
        if self._current and self._current[0] != self._current[-1]:
            self._current.append(self._current[0])
        self._flush()

    def _endPath(self):
        self._flush()

    def _flush(self):
        if len(self._current) >= 2:
            self.strokes.append(self._current)
        self._current = []


class TTFFontLoader:
    """Lädt eine TTF/OTF-Datei und liefert Strokes pro Zeichen.

    API ist angelehnt an HersheyFonts.strokes_for_text, sodass das Backend
    austauschbar bleibt.
    """

    def __init__(self, path, segments_per_curve=5, dedupe_epsilon=0.05):
        self.path = path
        self.segments_per_curve = segments_per_curve
        self.dedupe_epsilon = dedupe_epsilon
        self.font = TTFont(path)
        self.glyph_set = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap() or {}
        self.upem = self.font["head"].unitsPerEm

        os2 = self.font.get("OS/2")
        cap = getattr(os2, "sCapHeight", 0) if os2 else 0
        if not cap:
            cap = int(0.7 * self.upem)
        # Cap-Height -> 21 Einheiten (Hershey-Skala)
        self.norm = cap / HERSHEY_CAP_HEIGHT_UNITS if cap else self.upem / 30.0
        self._stroke_cache = {}
        self._width_cache = {}

    def _glyph_name(self, ch):
        return self.cmap.get(ord(ch))

    def strokes_for_text(self, text):
        """Yield Polylinien für jeden Buchstaben in 'text'.

        Y wird gespiegelt (positiv = unten), damit das Ergebnis dieselbe
        Konvention hat wie HersheyFonts und die Transformation im
        TextToPathConverter unverändert funktioniert.
        """
        for ch in text:
            for stroke in self._cached_strokes(ch):
                yield stroke

    def _cached_strokes(self, ch):
        if ch in self._stroke_cache:
            return self._stroke_cache[ch]
        name = self._glyph_name(ch)
        if name is None:
            self._stroke_cache[ch] = []
            return []
        pen = _StrokePen(self.glyph_set, self.segments_per_curve)
        try:
            self.glyph_set[name].draw(pen)
        except Exception:
            self._stroke_cache[ch] = []
            return []
        norm = self.norm
        eps = self.dedupe_epsilon
        normalized = []
        for stroke in pen.strokes:
            dedup = []
            for (x, y) in stroke:
                nx, ny = x / norm, -y / norm
                if dedup and abs(nx - dedup[-1][0]) < eps and abs(ny - dedup[-1][1]) < eps:
                    continue
                dedup.append((nx, ny))
            if len(dedup) >= 2:
                normalized.append(dedup)
        self._stroke_cache[ch] = normalized
        return normalized

    def char_width(self, ch):
        """Advance-Breite des Zeichens, im selben (Hershey-ähnlichen) Maß."""
        if ch in self._width_cache:
            return self._width_cache[ch]
        name = self._glyph_name(ch)
        if name is None:
            self._width_cache[ch] = 0.0
            return 0.0
        try:
            advance, _lsb = self.font["hmtx"][name]
        except KeyError:
            self._width_cache[ch] = 0.0
            return 0.0
        w = advance / self.norm
        self._width_cache[ch] = w
        return w


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "data/input/fonts/HeftyRewardSingleLine-JRqWx.ttf"
    loader = TTFFontLoader(p)
    s = list(loader.strokes_for_text("ABO"))
    print(f"{len(s)} Strokes für 'ABO'")
    print(f"Beispiel-Stroke (0..3 Punkte): {s[0][:3] if s else '—'}")
    print(f"Breite 'A': {loader.char_width('A'):.2f}")
