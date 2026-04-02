from core.text_vectorization import TextToPathConverter
from core.gcode_converter import GCodeGenerator
from core.serial_comm import SerialPlotter

def verify_pipeline():
    print("Starte Verifizierung der Pipeline...")

    # 1. Test Text to Paths
    converter = TextToPathConverter()
    paths = converter.text_to_paths("OK")
    print(f"Text 'OK' hat {len(paths)} Pfade.")
    if len(paths) == 0:
        print("FEHLER: Keine Pfade generiert.")
        return

    # 2. Test Path to G-Code
    generator = GCodeGenerator()
    gcode = generator.generate_gcode(paths)
    print(f"Generierter G-Code hat {len(gcode)} Zeilen.")

    # Stichprobe Z-Bewegung
    z_moves = [line for line in gcode if "Z" in line]
    print(f"Z-Bewegungen gefunden: {len(z_moves)}")
    if len(z_moves) < 2:
        print("FEHLER: Keine Z-Bewegungen für Stift hoch/runter.")
        return

    # 3. Test Serial (nur Struktur)
    plotter = SerialPlotter()
    ports = plotter.list_ports()
    print(f"Verfügbare Ports: {ports}")

    print("Pipeline-Verifizierung ERFOLGREICH.")

if __name__ == "__main__":
    verify_pipeline()
