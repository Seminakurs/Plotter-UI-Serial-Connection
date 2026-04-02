import sys
import os

# Vergewissere dich, dass der Projektordner im Python-Pfad ist
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ui.ui_main import PlotterUI

def main():
    """
    Haupteinstiegspunkt für das Voice-to-Plotter Projekt.
    Initialisiert die Benutzeroberfläche und verknüpft die Module.
    """
    print("Starte Voice-to-Plotter Anwendung...")

    # UI starten
    app = PlotterUI()

    # Sauberes Beenden sicherstellen
    app.protocol("WM_DELETE_WINDOW", app.on_closing)

    # Hauptloop starten
    try:
        app.mainloop()
    except KeyboardInterrupt:
        print("Anwendung durch Benutzer beendet.")
        app.on_closing()

if __name__ == "__main__":
    main()
