"""Test de bout en bout du branchement dans le vrai `mcLaunch/__main__.py`.

On charge le module réel du lanceur (avec un double pour `tkinterweb`, absent de
cet environnement), puis on appelle la vraie méthode `Myapp._report_crash`
depuis un thread, comme le fait `start_mc`. On vérifie qu'une fenêtre de crash
apparaît réellement dans la boucle d'événements Tk.
"""

from __future__ import annotations

import importlib.util
import queue
import sys
import threading
import time
import tkinter as tk
import types
from pathlib import Path

import pytest
from crash_report import CrashDialog, build_report

LAUNCHER_DIR = Path(__file__).resolve().parents[1] / "mcLaunch"


@pytest.fixture(scope="module")
def launcher_module():
    """Charge `mcLaunch/__main__.py` sous un nom distinct."""
    stub = types.ModuleType("tkinterweb")

    class HtmlFrame(tk.Frame):  # double minimal, jamais utilisé ici
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

    stub.HtmlFrame = HtmlFrame
    sys.modules.setdefault("tkinterweb", stub)

    sys.path.insert(0, str(LAUNCHER_DIR))
    spec = importlib.util.spec_from_file_location("launcher_main", LAUNCHER_DIR / "__main__.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(LAUNCHER_DIR))
    return module


@pytest.fixture
def app(launcher_module):
    """Une vraie fenêtre Tk portant les vraies méthodes de rapport de crash."""
    try:
        tk.Tk().destroy()
    except tk.TclError as exc:  # pragma: no cover
        pytest.skip(f"pas d'affichage disponible: {exc}")

    class FakeApp(tk.Tk):
        _report_crash = launcher_module.Myapp._report_crash
        _show_crash = launcher_module.Myapp._show_crash
        _poll_crash_queue = launcher_module.Myapp._poll_crash_queue
        _start_crash_poller = launcher_module.Myapp._start_crash_poller

    instance = FakeApp()
    instance.withdraw()
    instance._crash_queue = queue.Queue()
    instance._crash_poller = None
    instance._start_crash_poller()
    yield instance
    instance.destroy()


def _pump(root, predicate, timeout=5.0):
    """Fait tourner la boucle Tk jusqu'à ce que `predicate` soit vrai."""
    deadline = time.monotonic() + timeout
    found = None
    while time.monotonic() < deadline:
        root.update()
        found = predicate()
        if found:
            break
        time.sleep(0.02)
    return found


def test_real_report_crash_from_thread_opens_a_dialog(app):
    report = build_report(exit_code=1, lines=["fin"], errors=["ERREUR: mod manquant"])
    seen = []

    def grab_dialog():
        """Ferme la fenêtre modale dès qu'elle apparaît (boucle imbriquée)."""
        dialog = next((w for w in app.winfo_children() if isinstance(w, CrashDialog)), None)
        if dialog is None:
            app.after(50, grab_dialog)
            return
        seen.append((dialog.get_text(), dialog))
        dialog.destroy()

    app.after(50, grab_dialog)
    worker = threading.Thread(target=app._report_crash, args=(report,), daemon=True)
    worker.start()

    _pump(app, lambda: bool(seen))
    assert seen, "aucune fenêtre de crash affichée"
    text, dialog = seen[0]
    assert "ERREUR: mod manquant" in text
    assert not dialog.winfo_exists()
    worker.join(timeout=5)


def test_start_mc_uses_the_reporting_runner(launcher_module):
    """Le lancement passe bien par le runner instrumenté, plus par StreamRunner brut."""
    source = (LAUNCHER_DIR / "__main__.py").read_text(encoding="utf-8")
    assert "run_game_with_report(self, env, interactive=False)" in source
    assert "env.run(runner=StreamRunner())" not in source
