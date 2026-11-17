"""Tests du rapport de crash et de sa fenêtre.

Le symptôme visé : quand le jeu plante, l'utilisateur ne voit rien (l'ancien
`message()` ne faisait qu'un `print`). Ces tests décrivent le comportement
attendu : un rapport qui dit *pourquoi* et une fenêtre qui l'affiche.

Les tests d'interface tournent sur un vrai serveur X (`DISPLAY=:0`) : ils
créent une vraie fenêtre Tk, lisent son contenu, cliquent sur ses boutons.
"""

from __future__ import annotations

import tkinter as tk

import pytest
from crash_report import CrashDialog, build_report


# --------------------------------------------------------------------------- modèle
def test_exit_code_zero_is_not_a_crash():
    report = build_report(exit_code=0, lines=["Fin normale"], errors=[])
    assert report is not None
    assert report.is_crash is False


def test_nonzero_exit_code_is_a_crash():
    report = build_report(exit_code=1, lines=["boom"], errors=[])
    assert report.is_crash is True


def test_format_text_mentions_exit_code_errors_and_log_path():
    report = build_report(
        exit_code=1,
        lines=["[10:00:00] [main/INFO]: Starting", "[10:00:01] [main/ERROR]: Failed"],
        errors=["[main/ERROR]: Failed to start"],
        log_file="/tmp/latest.log",
    )
    text = report.format_text()
    assert "code de sortie 1" in text
    assert "Failed to start" in text
    assert "/tmp/latest.log" in text


def test_format_text_keeps_only_the_tail_of_the_log():
    lines = [f"ligne {i}" for i in range(5000)]
    report = build_report(exit_code=1, lines=lines, errors=[])
    text = report.format_text()
    assert "ligne 4999" in text
    assert "ligne 0" not in text
    assert "5000" in text or "dernières lignes" in text


def test_format_text_is_bounded_even_with_huge_stacktraces():
    errors = ["Exception at " + "x" * 10_000 for _ in range(200)]
    report = build_report(exit_code=1, lines=["a"], errors=errors)
    text = report.format_text()
    assert len(text) < 80_000


def test_format_text_without_log_file_says_so():
    report = build_report(exit_code=2, lines=["a"], errors=[], log_file=None)
    text = report.format_text()
    assert "Journal complet" not in text
    assert "code de sortie 2" in text


def test_report_survives_empty_input():
    report = build_report(exit_code=1, lines=[], errors=[])
    assert "code de sortie 1" in report.format_text()


# ------------------------------------------------------------------------- interface
@pytest.fixture
def root():
    """Une vraie racine Tk ; skip si aucun affichage n'est disponible."""
    try:
        window = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - dépend de la machine
        pytest.skip(f"pas d'affichage disponible: {exc}")
    window.withdraw()
    yield window
    window.destroy()


def test_dialog_displays_the_report(root):
    report = build_report(exit_code=1, lines=["ligne finale"], errors=["ERREUR: mod absent"])
    dialog = CrashDialog(root, report)
    dialog.update_idletasks()
    assert dialog.winfo_exists()
    assert "ERREUR: mod absent" in dialog.get_text()
    dialog.destroy()


def test_dialog_copy_button_fills_the_clipboard(root):
    report = build_report(exit_code=1, lines=["fin"], errors=["ERREUR: boom"])
    dialog = CrashDialog(root, report)
    dialog.copy_to_clipboard()
    assert "ERREUR: boom" in root.clipboard_get()
    dialog.destroy()


def test_dialog_close_button_destroys_it(root):
    dialog = CrashDialog(root, build_report(exit_code=1, lines=[], errors=[]))
    dialog.close()
    assert not dialog.winfo_exists()


def test_show_crash_dialog_opens_a_window_and_returns(root):
    from crash_report import show_crash_dialog

    report = build_report(exit_code=1, lines=["fin"], errors=["ERREUR: boom"])
    opened = []

    def close_soon():
        # La fenêtre est modale : on la ferme depuis la boucle Tk.
        for child in root.winfo_children():
            opened.append(child)
            child.destroy()

    root.after(300, close_soon)
    show_crash_dialog(root, report)
    assert opened, "aucune fenêtre de crash n'a été affichée"
