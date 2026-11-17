"""Rapport de crash Minecraft et fenêtre d'affichage.

Le lanceur démarrait le jeu avec ``env.run(runner=StreamRunner())`` : le runner
avalait la sortie standard et **le code de sortie n'était jamais évalué**. Un
crash se soldait donc par un retour silencieux à la fenêtre du lanceur.

Ce module apporte trois choses :

* :class:`LoggingStreamRunner` conserve la sortie du jeu en mémoire et retient
  son code de sortie ;
* :func:`build_report` décide s'il y a eu crash et met en forme un rapport
  court (code de sortie, erreurs, fin du journal) ;
* :func:`show_crash_dialog` affiche ce rapport dans une fenêtre Tk avec un
  bouton *Copier*.

Il ne dépend ni de portablemc ni du reste du lanceur, ce qui le rend testable
seul ; le branchement se fait dans ``__main__`` via :func:`run_game`.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import ttk

#: Nombre de lignes de journal conservées en mémoire pendant une partie.
MAX_LINES = 4000
#: Nombre de lignes de journal affichées dans le rapport.
TAIL_LINES = 120
#: Nombre maximum de messages d'erreur détaillés dans le rapport.
MAX_ERRORS = 15
#: Taille maximale d'une trace d'exception individuelle.
MAX_THROWABLE_CHARS = 3000
#: Couleurs de la fenêtre, alignées sur le reste du lanceur.
BACKGROUND = "#1E2020"
FOREGROUND = "#E6E6E6"
ACCENT = "#00A000"


@dataclass
class CrashReport:
    """Résultat d'une partie : code de sortie, erreurs vues et journal."""

    exit_code: int
    lines: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    log_file: str | None = None

    @property
    def is_crash(self) -> bool:
        """Vrai si le jeu ne s'est pas terminé normalement."""
        return self.exit_code != 0

    def format_text(self) -> str:
        """Met le rapport en forme pour l'affichage et le presse-papiers."""
        parts = [
            f"Minecraft s'est arrêté avec le code de sortie {self.exit_code}.",
            "",
        ]
        if self.errors:
            parts.append(f"Erreurs signalées par le jeu ({len(self.errors)}) :")
            parts.append("")
            for error in self.errors[:MAX_ERRORS]:
                parts.append(_clip(error, MAX_THROWABLE_CHARS))
                parts.append("")
            if len(self.errors) > MAX_ERRORS:
                parts.append(f"... et {len(self.errors) - MAX_ERRORS} autre(s) erreur(s).")
                parts.append("")
        else:
            parts.append("Le jeu n'a signalé aucune erreur explicite avant de quitter.")
            parts.append("")

        if self.lines:
            tail = self.lines[-TAIL_LINES:]
            parts.append(f"Fin du journal ({len(tail)} dernières lignes sur {len(self.lines)}) :")
            parts.append("")
            parts.append("\n".join(tail))
            parts.append("")

        if self.log_file:
            parts.append(f"Journal complet : {self.log_file}")
        else:
            parts.append("Le jeu n'a écrit aucun journal exploitable sur le disque.")
        return _clip("\n".join(parts), 60000)


def _clip(text: str, limit: int) -> str:
    """Tronque un texte trop long en gardant le début et la fin."""
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n[... {len(text) - limit} caractères coupés ...]\n{text[-half:]}"


def build_report(
    exit_code: int,
    lines: Iterable[str],
    errors: Iterable[str],
    log_file: str | None = None,
) -> CrashReport:
    """Construit un :class:`CrashReport` à partir de ce que le runner a vu."""
    return CrashReport(
        exit_code=int(exit_code),
        lines=list(lines)[-MAX_LINES:],
        errors=list(errors),
        log_file=str(log_file) if log_file else None,
    )


def latest_log_path(context) -> Path | None:
    """Chemin de ``logs/latest.log`` du dossier de jeu, ou ``None`` sans contexte."""
    work_dir = getattr(context, "work_dir", None)
    if work_dir is None:
        return None
    return Path(work_dir) / "logs" / "latest.log"


def read_latest_log(path: Path | None, tail: int | None = None) -> list[str]:
    """Lit le journal écrit par le jeu ; renvoie ``[]`` s'il est absent ou illisible."""
    if path is None:
        return []
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    return lines[-tail:] if tail else lines


class _LoggingStreamRunnerBase:
    """Runner de portablemc qui conserve la sortie du jeu et son code de sortie.

    Hérite de ``StreamRunner`` quand portablemc est disponible (parsing des logs
    log4j XML de Minecraft), sinon retombe sur un comportement minimal pour
    rester importable et testable seul.
    """

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.errors: list[str] = []
        self.exit_code: int | None = None

    # -- collecte -----------------------------------------------------------
    def _append(self, line: str) -> None:
        self.lines.append(line)
        if len(self.lines) > MAX_LINES:
            del self.lines[: len(self.lines) - MAX_LINES]

    def process_stream_event(self, event) -> None:
        """Reçoit une ligne brute (str) ou un ``XmlStreamEvent`` de portablemc."""
        if isinstance(event, str):
            self._append(event.rstrip("\n"))
            return
        message = getattr(event, "message", None) or ""
        level = str(getattr(event, "level", "") or "").upper()
        self._append(message)
        if level in ("ERROR", "FATAL"):
            throwable = getattr(event, "throwable", None)
            self.errors.append(f"[{level}] {message}" + (f"\n{throwable}" if throwable else ""))

    def _run_process(self, process) -> None:
        """Attend la fin du processus puis retient son code de sortie."""
        with suppress(Exception):  # on veut le code de sortie même si wait() échoue
            process.wait()
        self.exit_code = process.returncode

    def build_report(self, context=None) -> CrashReport:
        """Construit le rapport de la partie qui vient de se terminer."""
        code = 0 if self.exit_code is None else self.exit_code
        log_file = latest_log_path(context)
        # La sortie du jeu est plus fiable que le fichier : on ne lit ce dernier
        # que si le flux n'a rien donné (sortie redirigée, plantage très précoce).
        lines = self.lines or read_latest_log(log_file, tail=TAIL_LINES)
        return build_report(code, lines, self.errors, log_file)

    # -- héritage portablemc ------------------------------------------------
    # `run()` n'est volontairement pas défini ici : la classe finale hérite de
    # `StreamRunner.run`, qui prépare le répertoire des natives et lance le
    # processus. Le définir ici le masquerait (MRO) et le jeu ne démarrerait pas.


def _make_runner_class():
    """Construit le runner final, en héritant de ``StreamRunner`` si possible."""
    try:
        from portablemc.standard import StreamRunner
    except Exception:  # noqa: BLE001 - module absent : runner autonome
        StreamRunner = object  # type: ignore[assignment,misc]

    class _Runner(_LoggingStreamRunnerBase, StreamRunner):
        """Runner branché sur le flux de portablemc.

        `process_stream_thread` n'est **pas** redéfini : celui de ``StreamRunner``
        parse les logs log4j XML et rappelle ``self.process_stream_event``, donc
        nos erreurs sont bien collectées. Le redéfinir perdrait ce parsing.
        """

        def process_wait(self, process) -> None:
            """Attend la fin du jeu via portablemc puis retient son code de sortie."""
            super().process_wait(process)
            self.exit_code = process.returncode

    return _Runner


#: Runner concret, construit à l'import selon la présence de portablemc.
LoggingStreamRunner = _make_runner_class()


def show_crash_dialog(master: tk.Misc, report: CrashReport) -> CrashDialog:
    """Affiche le rapport dans une fenêtre modale et attend sa fermeture."""
    dialog = CrashDialog(master, report)
    try:
        dialog.grab_set()
    except tk.TclError:  # pragma: no cover - fenêtre déjà détruite
        pass
    master.wait_window(dialog)
    return dialog


def run_game(master: tk.Misc, env, *, interactive: bool = True) -> CrashReport | None:
    """Lance le jeu via un runner instrumenté et rapporte un éventuel crash.

    Renvoie le rapport si le jeu s'est arrêté anormalement, sinon ``None``.
    Avec ``interactive=False`` aucune fenêtre n'est créée : c'est ce qu'utilise
    le lanceur, qui exécute le jeu dans un thread et doit afficher la fenêtre
    depuis le thread principal (Tk n'est pas thread-safe).
    """
    runner = LoggingStreamRunner()
    env.run(runner=runner)
    report = runner.build_report(getattr(env, "context", None))
    if not report.is_crash:
        return None
    if interactive:
        show_crash_dialog(master, report)
    return report


class CrashDialog(tk.Toplevel):
    """Fenêtre affichant le rapport de crash, avec copie et fermeture."""

    def __init__(self, master: tk.Misc, report: CrashReport) -> None:
        super().__init__(master)
        self.report = report
        self.title("Minecraft s'est arrêté")
        self.configure(background=BACKGROUND)
        self.geometry("900x600")
        self.minsize(520, 320)
        self._build_widgets(report.format_text())

    def _build_widgets(self, text: str) -> None:
        """Construit l'en-tête, la zone de texte et les boutons."""
        header = ttk.Label(
            self,
            text="Le jeu s'est arrêté de façon inattendue.",
            font=("TkDefaultFont", 12, "bold"),
            foreground=ACCENT,
        )
        header.pack(anchor="w", padx=12, pady=(12, 4))

        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=12, pady=4)
        self.text = tk.Text(
            container,
            wrap="none",
            background="#141414",
            foreground=FOREGROUND,
            insertbackground=FOREGROUND,
            borderwidth=0,
            font=("TkFixedFont", 9),
        )
        scroll_y = ttk.Scrollbar(container, orient="vertical", command=self.text.yview)
        scroll_x = ttk.Scrollbar(container, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        self.text.insert("1.0", text)
        self.text.configure(state="disabled")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=12, pady=(4, 12))
        ttk.Button(buttons, text="Copier le rapport", command=self.copy_to_clipboard).pack(side="left")
        ttk.Button(buttons, text="Fermer", command=self.close).pack(side="right")

    def get_text(self) -> str:
        """Contenu affiché dans la zone de texte (utile aux tests)."""
        return self.text.get("1.0", "end-1c")

    def copy_to_clipboard(self) -> None:
        """Copie le rapport complet dans le presse-papiers."""
        self.clipboard_clear()
        self.clipboard_append(self.report.format_text())

    def close(self) -> None:
        """Ferme la fenêtre."""
        self.destroy()
