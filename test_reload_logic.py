"""
Direkter Pfad-Test fuer reload_config. Mockt nur whisper.load_model und
sounddevice, laesst alles andere echt laufen.
"""
import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ── Mocks aufsetzen BEVOR speech_to_text geladen wird ──────────────────
sys.modules["sounddevice"] = MagicMock()

import whisper  # noqa: E402
whisper.load_model = MagicMock(return_value=MagicMock())

from core.speech_to_text import SpeechRecognizer  # noqa: E402


def make_config(model="medium", device="cpu", threads=12):
    return {
        "whisper": {"model_size": model, "device": device, "threads": threads, "language": "de"},
        "stt_settings": {},
    }


def write_config(path, **changes):
    cfg = make_config()
    cfg["whisper"].update(changes)
    with open(path, "w") as f:
        json.dump(cfg, f)


def fresh_recognizer():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    write_config(path)
    rec = SpeechRecognizer(config_path=path)
    return rec, path


def expect(condition, label):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}")
    return condition


total_pass = 0
total_fail = 0


def run_test(name, fn):
    global total_pass, total_fail
    print(f"\n>>> {name}")
    try:
        results = fn()
        if all(results):
            total_pass += 1
        else:
            total_fail += 1
    except Exception as e:
        print(f"  [EXC] {e}")
        total_fail += 1


def test_threads_only():
    """Bug 1: nur threads geaendert -> _apply_thread_settings(), KEIN load_model()."""
    rec, path = fresh_recognizer()
    try:
        rec._apply_thread_settings = MagicMock()
        rec.load_model = MagicMock()
        rec.stop = MagicMock()
        rec.start = MagicMock()

        write_config(path, threads=4)
        rec.reload_config()

        return [
            expect(rec._apply_thread_settings.called, "_apply_thread_settings called"),
            expect(not rec.load_model.called, "load_model NOT called"),
            expect(rec.threads == 4, f"threads updated to 4 (got {rec.threads})"),
            expect(not rec.stop.called, "stop NOT called (was not running)"),
        ]
    finally:
        os.unlink(path)


def test_no_change():
    """Wenn nichts sich aendert: keine load_model, keine apply_threads."""
    rec, path = fresh_recognizer()
    try:
        rec._apply_thread_settings = MagicMock()
        rec.load_model = MagicMock()

        rec.reload_config()  # config unveraendert

        return [
            expect(not rec._apply_thread_settings.called, "_apply_thread_settings NOT called"),
            expect(not rec.load_model.called, "load_model NOT called"),
        ]
    finally:
        os.unlink(path)


def test_model_change():
    """Modell-Wechsel: load_model UND _apply_thread_settings."""
    rec, path = fresh_recognizer()
    try:
        rec._apply_thread_settings = MagicMock()
        rec.load_model = MagicMock()

        write_config(path, model="small")
        rec.reload_config()

        return [
            expect(rec.load_model.called, "load_model called"),
            expect(rec._apply_thread_settings.called, "_apply_thread_settings called"),
            expect(rec.model_size == "small", f"model_size updated (got {rec.model_size})"),
        ]
    finally:
        os.unlink(path)


def test_running_pause_resume_on_model_change():
    """Bug 4: running=True + Modell-Wechsel -> stop, load_model, start."""
    rec, path = fresh_recognizer()
    try:
        rec.running = True
        call_order = []
        rec._apply_thread_settings = MagicMock(side_effect=lambda: call_order.append("apply_threads"))
        rec.load_model = MagicMock(side_effect=lambda *a, **k: call_order.append("load_model"))
        def fake_stop():
            call_order.append("stop")
            rec.running = False
        def fake_start():
            call_order.append("start")
            rec.running = True
        rec.stop = MagicMock(side_effect=fake_stop)
        rec.start = MagicMock(side_effect=fake_start)

        write_config(path, model="small")
        rec.reload_config()

        return [
            expect("stop" in call_order, "stop called"),
            expect("load_model" in call_order, "load_model called"),
            expect("start" in call_order, "start called"),
            expect(call_order.index("stop") < call_order.index("load_model"),
                   f"stop BEFORE load_model (order: {call_order})"),
            expect(call_order.index("load_model") < call_order.index("start"),
                   f"load_model BEFORE start (order: {call_order})"),
        ]
    finally:
        os.unlink(path)


def test_running_threads_only():
    """Bug 1 + 4: running=True + nur threads -> stop, apply_threads, start."""
    rec, path = fresh_recognizer()
    try:
        rec.running = True
        call_order = []
        rec._apply_thread_settings = MagicMock(side_effect=lambda: call_order.append("apply_threads"))
        rec.load_model = MagicMock(side_effect=lambda *a, **k: call_order.append("load_model"))
        def fake_stop():
            call_order.append("stop"); rec.running = False
        def fake_start():
            call_order.append("start"); rec.running = True
        rec.stop = MagicMock(side_effect=fake_stop)
        rec.start = MagicMock(side_effect=fake_start)

        write_config(path, threads=8)
        rec.reload_config()

        return [
            expect("stop" in call_order, "stop called"),
            expect("apply_threads" in call_order, "apply_threads called"),
            expect("start" in call_order, "start called"),
            expect("load_model" not in call_order, "load_model NOT called"),
        ]
    finally:
        os.unlink(path)


def test_not_running_no_stop_start():
    """running=False: kein stop/start, nur reload."""
    rec, path = fresh_recognizer()
    try:
        rec.running = False
        rec._apply_thread_settings = MagicMock()
        rec.load_model = MagicMock()
        rec.stop = MagicMock()
        rec.start = MagicMock()

        write_config(path, threads=8)
        rec.reload_config()

        return [
            expect(not rec.stop.called, "stop NOT called"),
            expect(not rec.start.called, "start NOT called"),
            expect(rec._apply_thread_settings.called, "apply_threads called"),
        ]
    finally:
        os.unlink(path)


if __name__ == "__main__":
    run_test("test_threads_only", test_threads_only)
    run_test("test_no_change", test_no_change)
    run_test("test_model_change", test_model_change)
    run_test("test_running_pause_resume_on_model_change", test_running_pause_resume_on_model_change)
    run_test("test_running_threads_only", test_running_threads_only)
    run_test("test_not_running_no_stop_start", test_not_running_no_stop_start)

    print(f"\n=== {total_pass} pass, {total_fail} fail ===")
    sys.exit(0 if total_fail == 0 else 1)
