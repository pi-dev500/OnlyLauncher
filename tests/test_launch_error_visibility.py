"""Régression : une erreur de lancement doit être visible dans l'exe fenêtré.

Symptôme visé : dans le binaire PyInstaller ``--windowed``, ``sys.stdout`` vaut
``None``. ``Myapp.message()`` ne faisait qu'un ``print`` : l'échec de lancement
partait dans le vide et l'utilisateur ne voyait « rien se passer ».

Ces tests vérifient qu'un message produit un artefact visible (boîte de dialogue)
et qu'une erreur est journalisée sur disque même sans console.
"""

from __future__ import annotations

import importlib.util
import sys
import tkinter as tk
import types
from pathlib import Path

import pytest

LAUNCHER_DIR = Path(__file__).resolve().parents[1] / "mcLaunch"


@pytest.fixture(scope="module")
def launcher_module():
    """Charge `mcLaunch/__main__.py` avec un double pour `tkinterweb`."""
    stub = types.ModuleType("tkinterweb")

    class HtmlFrame(tk.Frame):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

    stub.HtmlFrame = HtmlFrame
    sys.modules.setdefault("tkinterweb", stub)

    sys.path.insert(0, str(LAUNCHER_DIR))
    spec = importlib.util.spec_from_file_location(
        "launcher_main_visibility", LAUNCHER_DIR / "__main__.py"
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(LAUNCHER_DIR))
    return module


@pytest.fixture
def app(launcher_module):
    """Vraie fenêtre Tk portant la vraie méthode `message`."""
    try:
        probe = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover
        pytest.skip(f"pas d'affichage disponible: {exc}")
    probe.destroy()

    class FakeApp(tk.Tk):
        message = launcher_module.Myapp.message

    instance = FakeApp()
    instance.withdraw()
    yield instance
    instance.destroy()


def test_message_opens_a_dialog_not_just_a_print(app, monkeypatch, launcher_module):
    """Le symptôme exact : en fenêtré, `print` ne montre rien.

    On remplace `print` par un puits (comme un stdout à ``None``) et on vérifie
    qu'une boîte de dialogue est tout de même demandée.
    """
    shown = []
    monkeypatch.setattr(
        launcher_module.messagebox,
        "showerror",
        lambda title, text, **kw: shown.append((title, text)),
    )
    monkeypatch.setattr(
        launcher_module.messagebox,
        "showinfo",
        lambda title, text, **kw: shown.append((title, text)),
    )
    monkeypatch.setattr("builtins.print", lambda *a, **k: None)

    app.message("Erreur de lancement", "Impossible de lancer le jeu: boom")

    assert shown, "aucune boîte de dialogue : l'erreur reste invisible"
    title, text = shown[0]
    assert "Erreur de lancement" in title
    assert "boom" in text


def test_message_survives_a_missing_display(monkeypatch, launcher_module):
    """Une boîte de dialogue impossible à afficher ne doit pas lever."""
    def boom(*args, **kwargs):
        raise tk.TclError("no display")

    monkeypatch.setattr(launcher_module.messagebox, "showerror", boom)
    monkeypatch.setattr(launcher_module.messagebox, "showinfo", boom)

    class Bare:
        message = launcher_module.Myapp.message

    Bare().message("Erreur", "tant pis")  # ne doit pas lever


def test_launch_failure_is_written_to_a_log(launcher_module, tmp_path, monkeypatch):
    """Sans console, l'erreur doit rester consultable sur le disque."""
    log = tmp_path / "onlylauncher.log"
    launcher_module.configure_logging(log)

    import logging

    logging.getLogger(launcher_module.LOGGER_NAME).error("Impossible de lancer le jeu: boom")

    assert log.exists()
    assert "Impossible de lancer le jeu: boom" in log.read_text(encoding="utf-8")
