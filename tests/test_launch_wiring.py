"""Tests du branchement du rapport de crash dans le lanceur.

Symptôme visé : `env.run(runner=StreamRunner())` avalait la sortie du jeu et
n'évaluait jamais le code de sortie, donc un crash était totalement silencieux.

Ces tests pilotent un faux environnement qui simule un jeu qui plante, et
vérifient qu'un rapport est construit puis affiché.
"""

from __future__ import annotations

import tkinter as tk

import crash_report
import pytest


class FakeProcess:
    """Imite le `Popen` renvoyé par le runner de portablemc."""

    def __init__(self, returncode: int) -> None:
        self.returncode = returncode
        self.stdout = iter(())


class FakeEnvironment:
    """Imite `Environment` au seam qu'utilise `run_game` : `run(runner)`.

    portablemc fait `env.run(runner)` -> `runner.run(env)` -> préparation des
    natives -> `process_wait`. On court-circuite la préparation (qui exige une
    vraie installation) pour ne tester que l'orchestration et le rapport.
    """

    def __init__(self, returncode: int, context=None) -> None:
        self.returncode = returncode
        self.context = context
        self.runner = None

    def run(self, runner=None) -> None:
        self.runner = runner
        runner.process_stream_event("Fin du flux du jeu\n")
        runner._run_process(FakeProcess(self.returncode))


class FakeContext:
    def __init__(self, work_dir) -> None:
        self.work_dir = work_dir


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover
        pytest.skip(f"pas d'affichage disponible: {exc}")
    window.withdraw()
    yield window
    window.destroy()


def test_logging_runner_records_lines_and_exit_code():
    runner = crash_report.LoggingStreamRunner()
    process = FakeProcess(returncode=1)
    runner.process_stream_thread = lambda proc: None  # pas de flux réel
    runner._run_process(process)
    assert runner.exit_code == 1


def test_logging_runner_captures_streamed_events():
    runner = crash_report.LoggingStreamRunner()
    runner.exit_code = 1  # le jeu a quitté anormalement

    class Event:
        level = "ERROR"
        message = "Missing or unsupported mandatory dependencies"
        throwable = "java.lang.RuntimeException: boom"

    runner.process_stream_event(Event())
    report = runner.build_report()
    assert report.is_crash is True
    assert "Missing or unsupported mandatory dependencies" in report.format_text()
    assert "java.lang.RuntimeException: boom" in report.format_text()


def test_streamed_plain_lines_are_kept():
    runner = crash_report.LoggingStreamRunner()
    runner.process_stream_event("ligne brute\n")
    assert runner.lines == ["ligne brute"]


def test_runner_reuses_portablemc_run_method():
    """Régression : définir `run()` dans la base masquait celui de portablemc (MRO),
    ce qui levait NotImplementedError au lieu de lancer le jeu."""
    from portablemc.standard import StreamRunner

    assert crash_report.LoggingStreamRunner.run is StreamRunner.run
    assert issubclass(crash_report.LoggingStreamRunner, StreamRunner)


def test_runner_keeps_portablemc_stream_parsing():
    """Le parsing log4j XML de portablemc reste utilisé (pas de remplacement brut)."""
    xml = (
        '<log4j:Event logger="net.minecraft" level="ERROR" timestamp="1" thread="main">\n'
        "<log4j:Message>Erreur fatale</log4j:Message>\n"
        "<log4j:Throwable>java.lang.RuntimeException: boom</log4j:Throwable>\n"
        "</log4j:Event>\n"
    )

    class Proc:
        class _Stdout:
            def __init__(self):
                self._lines = iter(xml.splitlines(keepends=True))

            def readline(self):
                return next(self._lines, "")

        stdout = _Stdout()

    runner = crash_report.LoggingStreamRunner()
    runner.process_stream_thread(Proc())  # pipeline réel de portablemc
    assert any("Erreur fatale" in e for e in runner.errors), runner.errors
    assert any("java.lang.RuntimeException: boom" in e for e in runner.errors)


def test_successful_game_does_not_report_a_crash():
    runner = crash_report.LoggingStreamRunner()
    runner._run_process(FakeProcess(returncode=0))
    assert runner.build_report().is_crash is False


def test_run_environment_shows_dialog_on_crash(root):
    """Le vrai chemin : un jeu qui sort en code 1 doit ouvrir la fenêtre."""
    env = FakeEnvironment(returncode=1, context=FakeContext(work_dir=None))
    shown = []

    def fake_show(master, report):
        shown.append(report)

    opened = []
    root.after(300, lambda: [opened.append(c) or c.destroy() for c in root.winfo_children()])
    original = crash_report.show_crash_dialog
    crash_report.show_crash_dialog = fake_show
    try:
        crash_report.run_game(root, env)
    finally:
        crash_report.show_crash_dialog = original
    assert shown, "aucune fenêtre de crash n'a été demandée"
    assert shown[0].exit_code == 1


def test_run_environment_shows_nothing_on_success(root):
    env = FakeEnvironment(returncode=0)
    shown = []
    original = crash_report.show_crash_dialog
    crash_report.show_crash_dialog = lambda master, report: shown.append(report)
    try:
        assert crash_report.run_game(root, env) is None
    finally:
        crash_report.show_crash_dialog = original
    assert shown == []


def test_non_interactive_run_returns_report_without_opening_a_window(root):
    """Chemin utilisé par le lanceur : pas de fenêtre créée hors thread principal."""
    env = FakeEnvironment(returncode=1)
    shown = []
    original = crash_report.show_crash_dialog
    crash_report.show_crash_dialog = lambda master, report: shown.append(report)
    try:
        report = crash_report.run_game(root, env, interactive=False)
    finally:
        crash_report.show_crash_dialog = original
    assert shown == []
    assert report is not None and report.exit_code == 1


def test_latest_log_path_points_into_the_game_directory(tmp_path):
    context = FakeContext(work_dir=tmp_path)
    path = crash_report.latest_log_path(context)
    assert path == tmp_path / "logs" / "latest.log"


def test_latest_log_path_is_none_without_context():
    assert crash_report.latest_log_path(None) is None


def test_read_latest_log_returns_tail(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "latest.log").write_text("\n".join(f"l{i}" for i in range(10)), encoding="utf-8")
    lines = crash_report.read_latest_log(tmp_path / "logs" / "latest.log", tail=3)
    assert lines == ["l7", "l8", "l9"]


def test_read_latest_log_tolerates_missing_file(tmp_path):
    assert crash_report.read_latest_log(tmp_path / "absent.log") == []
