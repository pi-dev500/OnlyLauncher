"""
"Mods & Modpacks" tab of mcLaunch.

`ModrinthBrowser` is an embeddable HTML view (tkinterweb) that displays the pages
produced by `modrinthapi` and turns the `mclaunch://` links they contain into real
launcher actions:

    search/<query>          run a new search
    detail/<project_id>     show the details of a project
    install/<project_id>    install the project in the currently targeted profile
    install-version/<id>    install one precise version
    download/<project_id>   only download the file into the instance `mods` folder
    deps/<project_id>       install the missing required dependencies
    new-profile/<id>        create a new isolated profile and install the modpack in it
    target[/<profile>]      change (or show) the targeted profile
    home                    back to the front page
    installed               list the mods already installed in the targeted profile
    delmod/<fichier>        delete one installed mod file (its name, URL encoded)
    togglemod/<fichier>     enable/disable one mod (renames it .disabled)
    delmod-all[/ok]         delete every mod of the profile (needs the "ok" link)
    delmod-disabled[/ok]    delete only the disabled mods (needs the "ok" link)
    togglemod-all/<on|off>  enable/disable every mod of the profile
    openmods                open the profile's mods folder in the file manager
    site/<project_type>     open the project page in a web browser
    page=<n>                (query parameter) go to another page of the results

The widget is deliberately dumb: all the logic lives in `ModsFrame`, which owns the
search state (query, game version, loader, page) and does the network work in
background threads so the interface never freezes.

The search is *profile aware*: the targeted profile gives the Minecraft version and the
loader used to filter the results, and the mods are installed in that profile's own
instance folder (see `launcher_paths`). Changing the profile in the "Versions" tab or in
the game-version selector immediately updates the filter and refreshes the page.
"""

from __future__ import annotations

import collections
import html as _html
import os
import subprocess
import threading
import traceback
import urllib.parse
import webbrowser
from typing import Optional

import tkinter as tk
from tkinter import ttk
from tkinter import Button, Entry, Frame, Label, StringVar
from tkinterweb import HtmlFrame

import modrinthapi
from launcher_paths import (
    LOADERS, build_profile, ensure_profile_folders, instance_dir_for, mods_dir_for,
    normalize_profile, profile_label, safe_profile_name, unique_profile_name,
    version_and_loader,
)

#: Number of results per page.
PER_PAGE = 20

#: Project types offered in the toolbar (Modrinth facet values).
PROJECT_TYPES = ("mods", "modpacks", "shaders", "resourcepacks", "datapacks")

#: Label of the "no filter" entry of the Minecraft version combobox.
ANY_VERSION = "Toutes"

#: Label of the "no loader" entry of the loader combobox.
ANY_LOADER = "Aucun"

#: Delay (ms) between two passes of the main-thread task queue.
QUEUE_POLL_DELAY = 50


class ModrinthBrowser(HtmlFrame):
    """HTML view with the launcher styling and link handling."""

    def __init__(self, parent, app=None, **kwargs):
        # NOTE: tkinterweb validates every option type strictly; scrollbar options
        # only accept "auto", "dynamic" or a bool, so we simply keep the defaults.
        super().__init__(parent, messages_enabled=False, javascript_enabled=False,
                         on_link_click=self._on_link_click,
                         on_navigate_fail=self._on_navigate_fail, **kwargs)
        self.app = app
        self.owner: Optional["ModsFrame"] = None

    def _on_link_click(self, url):
        if self.owner is None:
            webbrowser.open(url)
            return
        self.owner.handle_link(url)

    def _on_navigate_fail(self, url):
        # Any navigation we did not intercept goes to the system browser instead of
        # replacing our page with an error message.
        if self.owner is not None and str(url).startswith("mclaunch://"):
            self.owner.handle_link(url)
        else:
            webbrowser.open(url)

    def show_html(self, html: str):
        self.load_html(html)


class ModsFrame(ttk.Frame):
    """Search / install interface for Modrinth mods and modpacks.

    The frame works on three layers:

    * the toolbar holds the search criteria; it is kept in sync with the targeted
      profile unless the user explicitly overrides a criterion;
    * `_run_async` runs every network operation in a worker thread and queues the
      requests instead of dropping them when one is already running;
    * the HTML produced by `modrinthapi` is displayed by `ModrinthBrowser`.
    """

    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.app = app
        self.query = StringVar(value="")
        self.mc_version = StringVar(value="")
        self.loader = StringVar(value=ANY_LOADER)
        self.project_type = StringVar(value="mods")
        self.status = StringVar(value="Prêt.")
        self.page = 1
        self.total_hits = 0
        self.last_results: dict = {}
        #: home | search (an "other" page - project sheet, report, ... - stops the
        #: automatic refresh so that changing the profile never throws the user out
        #: of the page he is currently reading)
        self.state = "home"
        self._busy = False
        self._job_lock = threading.Lock()
        self._pending_jobs: list = []
        # Tkinter n'est pas thread-safe: les threads de travail ne touchent jamais aux
        # widgets, ils déposent leur tâche ici et la boucle principale l'exécute.
        self._ui_queue = collections.deque()
        self._ui_poller = None
        self._alive = True
        self._game_versions: list = []
        self._version_cache: dict = {}
        self._auto_version = True
        self._auto_loader = True
        self._setting_boxes = False
        self.target_profile: Optional[dict] = None
        self._target_mc = ""
        self._target_loader = ""

        self._build_ui()
        self._start_queue_poller()
        self.show_target_profile()
        self.show_home()
        self.after(150, self._load_game_versions)

    # ------------------------------------------------------------------ UI setup
    def _build_ui(self):
        top = Frame(self, bg="#2E3030")
        top.pack(fill="x", padx=8, pady=6)

        Label(top, text="Rechercher :", bg="#2E3030", fg="white").grid(row=0, column=0, sticky="w")
        entry = Entry(top, textvariable=self.query, width=26)
        entry.grid(row=0, column=1, sticky="we", padx=4)
        entry.bind("<Return>", lambda e: self.new_search())

        Button(top, text="Chercher", bg="green", fg="black", borderwidth=0,
               activebackground="#00AA00", command=self.new_search).grid(row=0, column=2, padx=4)

        Label(top, text="Type :", bg="#2E3030", fg="white").grid(row=0, column=3, sticky="e")
        self.type_box = ttk.Combobox(top, state="readonly", width=12, values=list(PROJECT_TYPES))
        self.type_box.set("mods")
        self.type_box.bind("<<ComboboxSelected>>", lambda e: self.new_search())
        self.type_box.grid(row=0, column=4, padx=4)

        Label(top, text="Minecraft :", bg="#2E3030", fg="white").grid(row=0, column=5, sticky="e")
        self.version_box = ttk.Combobox(top, state="readonly", width=12, values=[ANY_VERSION])
        self.version_box.set(ANY_VERSION)
        self.version_box.bind("<<ComboboxSelected>>", self._on_version_box)
        self.version_box.grid(row=0, column=6, padx=4)

        Label(top, text="Loader :", bg="#2E3030", fg="white").grid(row=0, column=7, sticky="e")
        self.loader_box = ttk.Combobox(top, state="readonly", width=10,
                                       values=[ANY_LOADER] + [l.capitalize() for l in LOADERS])
        self.loader_box.set(ANY_LOADER)
        self.loader_box.bind("<<ComboboxSelected>>", self._on_loader_box)
        self.loader_box.grid(row=0, column=8, padx=4)

        Button(top, text="Profil ciblé ▾", bg="#2E3030", fg="white", borderwidth=0,
               activebackground="#3E4040", activeforeground="white",
               command=self.ask_target_profile).grid(row=0, column=9, padx=4)

        Button(top, text="Réinitialiser les filtres", bg="#2E3030", fg="white", borderwidth=0,
               activebackground="#3E4040", activeforeground="white",
               command=self.reset_filters).grid(row=0, column=10, padx=4)

        self.target_label = Label(top, text="", bg="#2E3030", fg="#30b6a2",
                                  anchor="w", justify="left", wraplength=900)
        self.target_label.grid(row=1, column=0, columnspan=11, sticky="w", pady=(4, 0))

        nav = Frame(self, bg="#2E3030")
        nav.pack(fill="x", padx=8)
        self.prev_button = Button(nav, text="< Page précédente", bg="#2E3030", fg="white",
                                  borderwidth=0, activebackground="#3E4040", activeforeground="white",
                                  command=lambda: self.goto_page(self.page - 1))
        self.prev_button.pack(side="left")
        self.next_button = Button(nav, text="Page suivante >", bg="#2E3030", fg="white",
                                  borderwidth=0, activebackground="#3E4040", activeforeground="white",
                                  command=lambda: self.goto_page(self.page + 1))
        self.next_button.pack(side="left", padx=6)
        Button(nav, text="Accueil", bg="#2E3030", fg="white", borderwidth=0,
               activebackground="#3E4040", activeforeground="white",
               command=self.show_home).pack(side="left", padx=6)
        Button(nav, text="Mes mods installés", bg="#2E3030", fg="white", borderwidth=0,
               activebackground="#3E4040", activeforeground="white",
               command=self.show_installed).pack(side="left", padx=6)

        # The status bar lives on its own row: packed on the right of the pagination
        # row it used to widen the frame until the "Profil ciblé" button was clipped.
        status_bar = Frame(self, bg="#2E3030")
        status_bar.pack(fill="x", padx=8)
        Label(status_bar, textvariable=self.status, bg="#2E3030", fg="#9a9a9a",
              anchor="w", justify="left", wraplength=900).pack(fill="x")

        self.browser = ModrinthBrowser(self, app=self.app)
        self.browser.owner = self
        self.browser.pack(fill="both", expand=True, padx=8, pady=6)
        self._refresh_nav()

    def destroy(self):
        self._alive = False
        if self._ui_poller is not None:
            try:
                self.after_cancel(self._ui_poller)
            except Exception:  # noqa: BLE001
                pass
            self._ui_poller = None
        super().destroy()

    def _refresh_nav(self):
        pages = max(1, (self.total_hits + PER_PAGE - 1) // PER_PAGE)
        self.prev_button.configure(state="normal" if self.page > 1 else "disabled")
        self.next_button.configure(state="normal" if self.page < pages else "disabled")

    # -------------------------------------------------------------- toolbar state
    def _on_version_box(self, event=None):
        """The user chose a Minecraft version by hand: stop following the profile."""
        self._auto_version = False
        self.mc_version.set(self.version_box.get())
        self.new_search()

    def _on_loader_box(self, event=None):
        self._auto_loader = False
        self.loader.set(self.loader_box.get())
        self.new_search()

    def _set_version_box(self, value: str):
        """Set the Minecraft filter without marking it as user-chosen."""
        self._setting_boxes = True
        try:
            self.version_box.set(value)
            self.mc_version.set(value)
        finally:
            self._setting_boxes = False

    def _set_loader_box(self, value: str):
        self._setting_boxes = True
        try:
            self.loader_box.set(value)
            self.loader.set(value)
        finally:
            self._setting_boxes = False

    def reset_filters(self):
        """Follow the targeted profile again for the version and the loader."""
        self._auto_version = self._auto_loader = True
        self.loader_box.set(ANY_LOADER)
        self.loader.set(ANY_LOADER)
        profile = self._current_target_profile()
        mc_version, loader = version_and_loader(profile)
        self._set_version_box(mc_version or ANY_VERSION)
        self._set_loader_box(loader.capitalize() if loader else ANY_LOADER)
        self.new_search()

    def _load_game_versions(self):
        """Fill the game version combobox from the (cached) Mojang manifest."""
        try:
            from cache_system import get_version_list
            self._game_versions = list(get_version_list().keys())
        except Exception as e:  # noqa: BLE001
            print(f"[mods] liste des versions indisponible: {e}")
            self._game_versions = []
        if self._game_versions:
            current = self.version_box.get()
            self.version_box.configure(values=[ANY_VERSION] + self._game_versions)
            self.version_box.set(current if current else ANY_VERSION)
        self._apply_target_to_toolbar()

    # ---------------------------------------------------------------- threads/UI
    def _start_queue_poller(self):
        """Démarre la boucle qui exécute les tâches déposées par les threads.

        `after` ne peut être appelé que depuis le fil principal: un thread de travail qui
        appelait `self.after(0, ...)` faisait échouer l'affichage de la page avec
        "main thread is not in main loop" (le résultat de la recherche n'apparaissait
        alors jamais). La boucle ci-dessous tourne en permanence dans le fil principal
        et vide la file d'attente.
        """
        if self._ui_poller is not None or not self._alive:
            return

        def poll():
            self._ui_poller = None
            if not self._alive:
                return
            while True:
                try:
                    task = self._ui_queue.popleft()
                except IndexError:
                    break
                try:
                    task()
                except tk.TclError:
                    pass
                except Exception as e:  # noqa: BLE001
                    print(f"[mods] tâche en attente en échec: {e}")
            try:
                self._ui_poller = self.after(QUEUE_POLL_DELAY, poll)
            except tk.TclError:
                self._ui_poller = None

        try:
            self._ui_poller = self.after(QUEUE_POLL_DELAY, poll)
        except tk.TclError:
            self._ui_poller = None

    def _call_main(self, function, *args, **kwargs):
        """Exécute `function` dans le fil principal, depuis n'importe quel fil.

        Depuis un thread, la tâche est simplement mise en file: c'est la seule façon
        fiable de toucher aux widgets (voir `_start_queue_poller`).
        """
        if threading.current_thread() is threading.main_thread():
            try:
                function(*args, **kwargs)
            except tk.TclError:
                pass
            return
        self._ui_queue.append(lambda: function(*args, **kwargs))

    def _set_status(self, message: str):
        self._call_main(self.status.set, message)

    def _show(self, html: str):
        self._call_main(self.browser.show_html, html)

    def _run_async(self, job, description: str = "", replace: bool = False):
        """Run `job` in a worker thread; queue it if another job is already running.

        Previously a request made while a job was running was *dropped* (and the user
        got an "Une opération est déjà en cours…" message), which is why a "Chercher"
        click right after the startup refresh did nothing.
        """
        with self._job_lock:
            if self._busy:
                if replace:
                    self._pending_jobs = [(job, description)]
                    self._set_status("Mise à jour de l'affichage…")
                else:
                    self._pending_jobs.append((job, description))
                return
            self._busy = True
        if description:
            self._set_status(description)
        self._start_worker(job)

    def _start_worker(self, job):
        def wrapper():
            try:
                job()
            except Exception as e:  # noqa: BLE001 - never kill a worker silently
                traceback.print_exc()
                self._set_status(f"Erreur: {e}")
            finally:
                with self._job_lock:
                    pending = None
                    if self._pending_jobs:
                        pending = self._pending_jobs[-1]
                        self._pending_jobs = []
                    self._busy = pending is not None
                if pending is not None:
                    self._start_worker(pending[0])
        threading.Thread(target=wrapper, daemon=True).start()

    # ------------------------------------------------------------------- target
    def _current_target_profile(self):
        """The profile the installs should go into (selected one, else the first one)."""
        app = self.app
        if app is None:
            return None
        profile = normalize_profile(getattr(app, "profile", None))
        if profile is not None:
            return profile
        profiles = app.launcher_conf.get("profiles") or []
        return normalize_profile(profiles[0]) if profiles else None

    def target_description(self) -> str:
        profile = self._current_target_profile()
        if profile is None:
            return ""
        if not profile.get("isolated"):
            return f"{profile_label(profile)} (dossier de jeu principal partagé)"
        return f"{profile_label(profile)} (instance isolée)"

    def _apply_target_to_toolbar(self):
        """Push the targeted profile into the toolbar, unless the user overrode it."""
        profile = self.target_profile
        mc_version, loader = version_and_loader(profile)
        self._target_mc = mc_version or ""
        self._target_loader = loader or ""
        if self._auto_version:
            if self._target_mc and self._target_mc in (self.version_box.cget("values") or ()):
                self._set_version_box(self._target_mc)
            elif self._target_mc:
                # version missing from the (unrefreshed) Mojang manifest: keep it anyway
                values = list(self.version_box.cget("values") or ())
                if self._target_mc not in values:
                    self.version_box.configure(values=[ANY_VERSION, self._target_mc] + values[1:])
                self._set_version_box(self._target_mc)
            else:
                self._set_version_box(ANY_VERSION)
        if self._auto_loader:
            self._set_loader_box(loader.capitalize() if loader else ANY_LOADER)

    def show_target_profile(self):
        """Update the "targeted profile" label (used by the toolbar button)."""
        profile = self._current_target_profile()
        self.target_profile = profile
        self.target_label.configure(
            text=f"Profil ciblé : {self.target_description() or 'aucun'}"
                 "    (installez via « Installer », ou changez de profil dans l'onglet Versions)")
        self._apply_target_to_toolbar()

    def set_target_profile(self, profile=None):
        """Called by the main window when the selected profile changes.

        The filter follows the new profile and the current page is refreshed, so the
        results always belong to the profile the mods will be installed into.
        """
        self.show_target_profile()
        if self.state == "search":
            self.page = 1
            self.do_search()
        elif self.state == "home":
            self.show_home()

    def ask_target_profile(self):
        """Let the user pick the targeted profile from the Mods tab itself."""
        app = self.app
        if app is None:
            return
        profiles = [normalize_profile(p) for p in (app.launcher_conf.get("profiles") or [])]
        profiles = [p for p in profiles if p]
        if not profiles:
            self._show(modrinthapi.installation_report_html(
                "Aucun profil", ["Créez d'abord un profil dans l'onglet Versions."], success=False))
            return
        current = self._current_target_profile() or {}
        top = tk.Toplevel(self)
        top.title("Profil ciblé")
        top.configure(bg="#2E3030")
        top.transient(self.winfo_toplevel())
        tk.Label(top, text="Dans quel profil faut-il installer les mods et les modpacks ?",
                 bg="#2E3030", fg="white").pack(padx=16, pady=(14, 6))
        listbox = tk.Listbox(top, width=70, height=min(14, max(3, len(profiles))),
                             bg="#1E2020", fg="white", selectbackground="#30b6a2")
        for profile in profiles:
            listbox.insert("end", profile_label(profile))
        selected_index = 0
        for index, profile in enumerate(profiles):
            if profile.get("name") == current.get("name"):
                selected_index = index
        listbox.selection_set(selected_index)
        listbox.pack(fill="both", expand=True, padx=16)
        info = tk.Label(top, text="", bg="#2E3030", fg="#9a9a9a", justify="left", wraplength=520)
        info.pack(padx=16, pady=(6, 0), anchor="w")

        def refresh_info(event=None):
            selection = listbox.curselection()
            if not selection:
                return
            profile = profiles[selection[0]]
            info.configure(text=f"Dossier des mods : {mods_dir_for(profile)}")

        listbox.bind("<<ListboxSelect>>", refresh_info)
        refresh_info()

        def validate():
            selection = listbox.curselection()
            top.destroy()
            if not selection:
                return
            profile = profiles[selection[0]]
            if app is not None and hasattr(app, "select_profile"):
                app.select_profile(profile["name"])
            else:
                self.set_target_profile(profile)
            self.show_target_profile()
            self.set_target_profile(profile)

        buttons = tk.Frame(top, bg="#2E3030")
        buttons.pack(fill="x", padx=16, pady=12)
        tk.Button(buttons, text="Cibler ce profil", bg="green", fg="black",
                  command=validate).pack(side="left")
        tk.Button(buttons, text="Annuler", bg="#2E3030", fg="white",
                  command=top.destroy).pack(side="right")
        top.update_idletasks()
        top.grab_set()
        self.wait_window(top)

    # ------------------------------------------------------------- version cache
    def _project_versions(self, project_id: str, mc_version: str, loader: str):
        """`(versions, warning)` of a project for a game version/loader, memoised.

        The Modrinth API is queried with both filters; when nothing matches we fall back
        on every version so the user always sees something, and a warning explains why
        the list is not filtered.
        """
        key = (project_id, mc_version or "", loader or "")
        cached = self._version_cache.get(key)
        if cached is not None:
            return cached
        versions = modrinthapi.get_available_project_versions(
            project_id, [mc_version] if mc_version else [], [loader] if loader else [])
        warning = ""
        if not versions:
            versions = modrinthapi.get_available_project_versions(project_id)
            if versions and (mc_version or loader):
                warning = (f"Aucune version publiée pour Minecraft {mc_version or '?'} / "
                           f"{loader or '?'} : toutes les versions sont affichées, "
                           "l'installation risque d'échouer au lancement.")
            elif not versions:
                warning = "Aucune version publiée (API Modrinth injoignable ?)."
        if len(self._version_cache) > 200:
            self._version_cache.clear()
        self._version_cache[key] = (versions, warning)
        return versions, warning

    # --------------------------------------------------------------- search UI
    def _facets(self):
        mappings = {"mods": "mod", "modpacks": "modpack", "shaders": "shader",
                    "resourcepacks": "resourcepack", "datapacks": "datapack"}
        facets = [[f"project_type:{mappings.get(self.type_box.get(), 'mod')}"]]
        if self.mc_version.get() and self.mc_version.get() != ANY_VERSION:
            facets.append([f"versions:{self.mc_version.get()}"])
        if self.loader.get() and self.loader.get() != ANY_LOADER:
            facets.append([f"categories:{self.loader.get().lower()}"])
        return facets

    def new_search(self):
        """Read the toolbar and start a new search on page 1."""
        if not self._setting_boxes:
            if self.version_box.get() != self.mc_version.get():
                self._auto_version = False
            if self.loader_box.get() != self.loader.get():
                self._auto_loader = False
        self.mc_version.set(self.version_box.get())
        self.loader.set(self.loader_box.get())
        self.page = 1
        self.do_search()

    def goto_page(self, page: int):
        if page < 1:
            return
        self.page = page
        self.do_search()

    def do_search(self):
        query = self.query.get().strip()
        facets = self._facets()
        page = self.page
        mc_version = "" if self.mc_version.get() in ("", ANY_VERSION) else self.mc_version.get()
        loader = "" if self.loader.get() in ("", ANY_LOADER) else self.loader.get().lower()
        project_type = self.type_box.get()

        def job():
            self._set_status("Recherche en cours…")
            results = modrinthapi.search_modrinth_projects(query, facets, limit=PER_PAGE, page=page)
            self.total_hits = int(results.get("total_hits") or 0)
            self.last_results = results
            self.state = "search"
            self._show(modrinthapi.html_from_hits(
                results.get("hits", []), page=page, per_page=PER_PAGE,
                total_hits=self.total_hits, query=query,
                error=results.get("error", ""), mc_version=mc_version, loader=loader,
                target_profile=self.target_description(), project_type=project_type))
            self._set_status(f"{len(results.get('hits', []))} résultat(s) pour "
                             f"{project_type} · {mc_version or 'toutes versions'}"
                             f" · {loader or 'tous loaders'}.")
            self._call_main(self._refresh_nav)

        self._run_async(job, "Recherche en cours…")

    def show_home(self):
        """Default page: the most downloaded content for the targeted profile."""
        profile = self._current_target_profile()
        mc_version, loader = version_and_loader(profile)
        mc_filter = [mc_version] if mc_version else []
        loader_filter = [loader] if loader else []

        def job():
            self._set_status("Chargement des suggestions…")
            modpacks = modrinthapi.search_modrinth_projects(
                "", [["project_type:modpack"]] + ([mc_filter] if mc_filter else []),
                index="downloads", limit=6, page=1)
            facets = [["project_type:mod"]]
            if mc_filter:
                facets.append(mc_filter)
            if loader_filter:
                facets.append(loader_filter)
            mods = modrinthapi.search_modrinth_projects("", facets, index="downloads",
                                                        limit=6, page=1)
            self.state = "home"
            html = [
                "<!DOCTYPE html><html lang=\"fr\"><head><meta charset=\"UTF-8\">"
                f"<title>Mods</title><style>{modrinthapi.HTML_STYLE}</style></head><body>",
                f'<div class="toolbar">Profil ciblé : <strong>'
                f'{modrinthapi._escape(self.target_description() or "aucun")}</strong><br>'
                'Les mods s\'installent dans le dossier <code>mods/</code> de ce profil, les '
                'modpacks créent une instance isolée complète. Les suggestions ci-dessous '
                'sont filtrées sur sa version de Minecraft et son loader.</div>',
            ]
            if not mc_version and not loader:
                html.append('<div class="notice">Aucune version de Minecraft n\'est connue '
                            'pour ce profil : les suggestions ne sont pas filtrées.</div>')
            for title, hits in (("Modpacks les plus téléchargés", modpacks.get("hits", [])),
                                ("Mods les plus téléchargés", mods.get("hits", []))):
                html.append(f"<h2>{title}</h2>")
                if not hits:
                    html.append('<div class="empty">Aucune donnée (pas de connexion ?)</div>')
                for hit in hits:
                    html.append(modrinthapi.hit_card_html(hit))
            html.append("</body></html>")
            self._show("".join(html))
            self._set_status("Prêt.")

        self._run_async(job, "Chargement…")

    # ------------------------------------------------------------ detail pages
    def show_project(self, project_id: str):
        profile = self._current_target_profile()
        mc_version, loader = version_and_loader(profile)

        def job():
            self._set_status(f"Chargement de {project_id}…")
            project_data = modrinthapi.get_project_data(project_id)
            if not isinstance(project_data, dict):
                self._show(modrinthapi.installation_report_html(
                    "Projet introuvable", [str(project_data)], success=False))
                return
            versions, warning = self._project_versions(project_id, mc_version or "", loader or "")
            version_data = versions[0] if versions else None
            dependencies = modrinthapi.get_project_dependencies(project_id)
            missing = []
            if project_data.get("project_type") == "mod" and mc_version:
                try:
                    missing = modrinthapi.get_missing_dependencies(
                        project_id, mods_dir_for(profile), mc_version, loader)
                except Exception as e:  # noqa: BLE001
                    print(f"[mods] dépendances indisponibles: {e}")
            html = modrinthapi.html_from_project_data(
                project_data, mc_version or "", loader or "", version_data, dependencies,
                missing_deps=missing, target_profile=self.target_description(),
                warning=warning,
                version_count=len(versions))
            self._show(html)
            self._set_status("Prêt.")
        self._run_async(job, "Chargement de la fiche…")

    def show_versions(self, project_id: str):
        profile = self._current_target_profile()
        mc_version, loader = version_and_loader(profile)

        def job():
            self._set_status("Chargement des versions…")
            project_data = modrinthapi.get_project_data(project_id)
            versions = modrinthapi.get_available_project_versions(project_id)
            self._show(modrinthapi.version_picker_html(project_data, versions,
                                                       mc_version or "", loader or ""))
            self._set_status(f"{len(versions)} version(s).")
        self._run_async(job, "Chargement des versions…")

    # ------------------------------------------------------------- installation
    def install_project(self, project_id: str, version_id: Optional[str] = None):
        """Install a project (and its required dependencies) into the target profile."""
        profile = self._current_target_profile()
        if profile is None:
            self._show(modrinthapi.installation_report_html(
                "Aucun profil", ["Sélectionnez d'abord un profil dans l'onglet Versions."],
                success=False))
            return
        mc_version, loader = version_and_loader(profile)

        def job():
            self._set_status("Installation en cours…")
            if loader == "optifine":
                self._show(modrinthapi.installation_report_html(
                    "Installation impossible",
                    ["Les mods ne peuvent pas être installés dans un profil OptiFine."],
                    success=False))
                return
            mods_dir = mods_dir_for(profile)
            os.makedirs(mods_dir, exist_ok=True)
            report = []
            installed_project = project_id
            if version_id:
                version_data = modrinthapi.get_version_from_id(version_id)
                if not isinstance(version_data, dict):
                    self._show(modrinthapi.installation_report_html(
                        "Version introuvable", [f"La version {version_id} n'existe plus."],
                        success=False))
                    return
                installed_project = version_data.get("project_id") or project_id
                if modrinthapi.download_version_file(version_data, mods_dir, progress=self._progress):
                    file = modrinthapi.pick_primary_file(version_data)
                    report.append(f"{file['filename'] if file else version_data.get('name')} installé.")
                else:
                    report.append("Échec de l'installation de la version demandée.")
            else:
                if not mc_version:
                    report.append("Le profil ciblé n'a pas de version de Minecraft connue : "
                                  "la version la plus récente du projet a été utilisée.")
                installed = modrinthapi.download_mod_with_dependencies(
                    project_id, mods_dir, mc_version or "", loader, progress=self._progress)
                report.extend(installed or ["Rien à installer."])
            project_data = modrinthapi.get_project_data(installed_project)
            title = project_data.get("title", installed_project) if isinstance(project_data, dict) else installed_project
            report.append(f"Dossier : {mods_dir}")
            self._show(modrinthapi.installation_report_html(
                f"{title} installé dans « {profile.get('name')} »", report, success=bool(report)))
            self._set_status("Installation terminée.")
            self._call_main(self.refresh_after_install)
        self._run_async(job, "Installation…")

    def refresh_after_install(self):
        """Called on the main thread once an install finished (keeps the app consistent)."""
        profile = self.target_profile
        if profile is not None:
            ensure_profile_folders(profile)
        app = self.app
        if app is not None and hasattr(app, "save_options"):
            try:
                app.save_options()
            except Exception as e:  # noqa: BLE001
                print(f"[mods] sauvegarde impossible: {e}")

    def download_project(self, project_id: str):
        """Only download the file into the target profile, without installing deps."""
        profile = self._current_target_profile()
        mc_version, loader = version_and_loader(profile)

        def job():
            self._set_status("Téléchargement…")
            versions, warning = self._project_versions(project_id, mc_version or "", loader or "")
            version_data = versions[0] if versions else None
            if not version_data:
                self._show(modrinthapi.installation_report_html(
                    "Téléchargement impossible", ["Aucune version disponible."], success=False))
                return
            target = mods_dir_for(profile)
            os.makedirs(target, exist_ok=True)
            ok = modrinthapi.download_version_file(version_data, target, progress=self._progress)
            file = modrinthapi.pick_primary_file(version_data) or {}
            name = file.get("filename", "?")
            lines = [f"{name} -> {target}"] if ok else [name, warning or "Échec du téléchargement."]
            self._show(modrinthapi.installation_report_html(
                "Téléchargement terminé" if ok else "Échec du téléchargement", lines, success=ok))
            self._set_status("Téléchargement terminé." if ok else "Échec du téléchargement.")
        self._run_async(job, "Téléchargement…")

    def install_dependencies(self, project_id: str):
        profile = self._current_target_profile()
        mc_version, loader = version_and_loader(profile)
        mods_dir = mods_dir_for(profile)

        def job():
            self._set_status("Installation des dépendances…")
            missing = modrinthapi.get_missing_dependencies(project_id, mods_dir,
                                                           mc_version or "", loader or "")
            if not missing:
                self._show(modrinthapi.installation_report_html(
                    "Dépendances", ["Toutes les dépendances obligatoires sont déjà présentes."]))
                return
            installed = modrinthapi.download_several_mods_with_dependencies(
                [dep[0] for dep in missing], mods_dir, mc_version or "", loader or "",
                progress=self._progress)
            self._show(modrinthapi.installation_report_html(
                "Dépendances installées", installed or ["Aucun fichier installé."],
                success=bool(installed)))
            self._set_status("Dépendances installées.")
        self._run_async(job, "Dépendances…")

    # ----------------------------------------------------------------- modpacks
    def install_modpack(self, project_id: str, create_profile: bool = False,
                        version_id: Optional[str] = None, mc_version: str = "", loader: str = ""):
        """Install a modpack into a (new) isolated profile and register that profile."""
        app = self.app

        def job():
            self._set_status("Préparation du modpack…")
            project_data = modrinthapi.get_project_data(project_id)
            title = project_data.get("title", project_id) if isinstance(project_data, dict) else project_id

            profile = None
            if create_profile or app is None:
                # 1. find out which MC version / loader the pack needs
                versions = modrinthapi.get_available_project_versions(
                    project_id, [mc_version] if mc_version else [], [loader] if loader else [])
                if not versions:
                    versions = modrinthapi.get_available_project_versions(project_id)
                if not versions:
                    self._show(modrinthapi.installation_report_html(
                        "Modpack indisponible", [f"Aucune version publiée pour {title}."],
                        success=False))
                    return
                pack_mc, pack_loader, _ = modrinthapi.resolve_modpack(versions[0])
                name = unique_profile_name(safe_profile_name(title),
                                           [p["name"] if isinstance(p, dict) else p
                                            for p in (app.launcher_conf.get("profiles") or [])])
                profile = build_profile(name, pack_mc or mc_version or "latest",
                                        pack_loader or loader, "", isolated=True)
                if app is not None:
                    self._call_main(app.register_profile, profile, True)
            else:
                profile = self._current_target_profile()
                if isinstance(profile, dict) and not profile.get("isolated"):
                    self.ask_isolate_profile = True
                    self._call_main(self._confirm_isolate, project_id, title)
                    return
                if profile is not None:
                    profile["isolated"] = True

            instance_dir = instance_dir_for(profile)
            ensure_profile_folders(profile)

            # optional files: ask the main thread for a selection
            selected_paths = None
            optional = modrinthapi.get_modpack_optional_files(project_id, version_id)
            if optional and app is not None:
                selection = self._ask_main(lambda: app.ask_optional_files(title, optional))
                if selection is None:
                    self._set_status("Installation annulée.")
                    return
                selected = set(selection)
                selected_paths = [entry["path"] for entry in optional
                                  if entry["path"] in selected]

            result = modrinthapi.install_modpack(
                project_id, instance_dir,
                mc_version or (profile.get("version") if isinstance(profile, dict) else "") or "",
                loader or (profile.get("loader") if isinstance(profile, dict) else "") or "",
                progress=self._progress, selected_paths=selected_paths, version_id=version_id)

            lines = [
                f"Dossier d'instance : {instance_dir}",
                f"Version de Minecraft : {result.get('mc_version') or '?'}",
                f"Loader : {result.get('loader') or 'aucun'} {result.get('loader_version') or ''}",
                f"Fichiers installés : {len(result.get('installed', []))}",
            ]
            if result.get("skipped"):
                lines.append(f"Fichiers ignorés : {len(result['skipped'])}")
            if result.get("error"):
                lines.append(f"Erreur : {result['error']}")

            if app is not None and isinstance(profile, dict):
                self._call_main(app.finalise_modpack_profile, profile, result)
            self._show(modrinthapi.installation_report_html(
                f"Modpack « {result.get('name') or title} »", lines,
                success=not result.get("error")))
            self._set_status("Modpack installé." if not result.get("error") else "Échec du modpack.")
        self._run_async(job, "Installation du modpack…")

    def _ask_main(self, function):
        """Run a modal dialog on the main thread and return its result."""
        box = {"done": False, "value": None}

        def run():
            try:
                box["value"] = function()
            except Exception as e:  # noqa: BLE001
                print(f"[mods] dialogue impossible: {e}")
            finally:
                box["done"] = True

        self._call_main(run)
        while not box["done"]:
            threading.Event().wait(0.1)
        return box["value"]

    def _confirm_isolate(self, project_id: str, title: str):
        """Propose to isolate a shared profile before installing a modpack into it."""
        top = tk.Toplevel(self)
        top.title("Profil isolé requis")
        top.configure(bg="#2E3030")
        top.transient(self.winfo_toplevel())
        tk.Label(top, text=f"« {title} » est un modpack : il écraserait votre installation\n"
                           "principale s'il était installé dans un profil non isolé.",
                 bg="#2E3030", fg="white", justify="left").pack(padx=16, pady=(14, 8), anchor="w")
        result = {"value": None}

        def choose(isolate):
            result["value"] = isolate
            top.destroy()

        buttons = tk.Frame(top, bg="#2E3030")
        buttons.pack(fill="x", padx=16, pady=(0, 14))
        tk.Button(buttons, text="Créer un nouveau profil isolé", bg="green", fg="black",
                  command=lambda: choose(True)).pack(side="left")
        tk.Button(buttons, text="Annuler", bg="#2E3030", fg="white",
                  command=lambda: choose(False)).pack(side="right")
        top.update_idletasks()
        top.grab_set()
        self.wait_window(top)
        if result["value"]:
            self.install_modpack(project_id, create_profile=True)
        else:
            self._set_status("Installation annulée.")

    def show_modpack_versions(self, project_id: str):
        self.show_versions(project_id)

    # ------------------------------------------------- installed mods (manage)
    def show_installed(self, notice: str = ""):
        """List the mods installed in the target profile, with delete/enable buttons.

        The list comes from `modrinthapi.installed_mods_info`, which recognises each file
        by its SHA-1 (``POST /version_files``) so the user sees the real mod name instead
        of the jar name, knowing which files come from Modrinth and which do not.
        """
        profile = self._current_target_profile()
        mods_dir = mods_dir_for(profile)
        target = self.target_description()

        def job():
            info = modrinthapi.installed_mods_info(mods_dir)
            self.state = "other"
            self._show(modrinthapi.installed_mods_html(
                mods_dir, target_profile=target, mods=info["mods"],
                unknown=info["unknown"], notice=notice, error=info["error"]))
            count = len(info["mods"])
            disabled = sum(1 for mod in info["mods"] if not mod["enabled"])
            suffix = f", dont {disabled} désactivé(s)" if disabled else ""
            self._set_status(f"{count} fichier(s) dans le profil ciblé{suffix}.")

        self._run_async(job, "Lecture des mods installés…", replace=True)

    def delete_installed_mod(self, file_name: str):
        """Delete one mod file of the target profile (the "Supprimer" button)."""
        profile = self._current_target_profile()
        mods_dir = mods_dir_for(profile)
        try:
            modrinthapi.delete_mod(mods_dir, file_name)
        except (OSError, ValueError) as e:
            self._show(modrinthapi.installation_report_html(
                "Suppression impossible", [f"{file_name} : {e}"], success=False))
            self._set_status(f"Suppression impossible : {e}")
            return
        self._set_status(f"{file_name} supprimé.")
        self.show_installed(notice=f"« {file_name} » a été supprimé du profil.")

    def toggle_installed_mod(self, file_name: str):
        """Disable/enable a mod by renaming it (``mod.jar`` <-> ``mod.jar.disabled``).

        Disabling is the reversible alternative to deleting: the file stays on the disk
        but Minecraft ignores it, which is what one wants when hunting a crash.
        """
        profile = self._current_target_profile()
        mods_dir = mods_dir_for(profile)
        currently_enabled = not modrinthapi.is_disabled_mod_file(file_name)
        try:
            new_name = modrinthapi.set_mod_enabled(mods_dir, file_name, not currently_enabled)
        except (OSError, ValueError) as e:
            self._set_status(f"Impossible de modifier le mod : {e}")
            self._show(modrinthapi.installation_report_html(
                "Modification impossible", [f"{file_name} : {e}"], success=False))
            return
        verb = "désactivé" if currently_enabled else "activé"
        self._set_status(f"{file_name} {verb}.")
        self.show_installed(notice=f"« {file_name} » → « {new_name} » : mod {verb}.")

    def toggle_all_installed_mods(self, enable: bool):
        """Enable (or disable) every mod of the profile at once."""
        profile = self._current_target_profile()
        mods_dir = mods_dir_for(profile)

        def job():
            # Only the files whose current state differs are renamed, otherwise the report
            # would count mods that were already in the wanted state.
            names = [name for name in modrinthapi.list_mods_for_deletion(mods_dir)
                     if modrinthapi.is_disabled_mod_file(name) == enable]
            if not names:
                verb = "activés" if enable else "désactivés"
                self._set_status(f"Aucun mod à modifier : ils sont déjà tous {verb}.")
                self.show_installed(notice=f"Aucun changement : tous les mods étaient déjà {verb}.")
                return
            renamed, errors = modrinthapi.set_mods_enabled(mods_dir, names, enable)
            verb = "activés" if enable else "désactivés"
            lines = [f"{len(renamed)} mod(s) {verb}."]
            lines.extend(errors)
            self._show(modrinthapi.installation_report_html(
                f"Mods {verb}", lines, success=not errors))
            self._set_status(
                f"{len(renamed)} mod(s) {verb} "
                f"(dossier {mods_dir}) — « Actualiser la liste » pour les revoir.")

        self._run_async(job, "Mise à jour des mods…", replace=True)

    def delete_installed_mods(self, scope: str = "all", confirmed: bool = False):
        """Delete every mod of the profile, or only the disabled ones.

        A bulk deletion always goes through `confirm_delete_html`, which renders the list
        of the files about to be erased: a single mis-click cannot wipe a profile.
        """
        profile = self._current_target_profile()
        mods_dir = mods_dir_for(profile)
        if not os.path.isdir(mods_dir):
            self._set_status("Ce profil n'a pas encore de dossier « mods ».")
            return
        names = modrinthapi.list_mods_for_deletion(mods_dir)
        if scope == "disabled":
            names = [name for name in names if modrinthapi.is_disabled_mod_file(name)]
        if not names:
            self._set_status("Aucun fichier à supprimer.")
            return

        if not confirmed:
            self.state = "other"
            self._show(modrinthapi.confirm_delete_html(
                mods_dir, scope, names, target_profile=self.target_description()))
            self._set_status(f"{len(names)} fichier(s) — suppression à confirmer.")
            return

        def job():
            deleted, errors = modrinthapi.delete_mods(mods_dir, names)
            lines = [f"{len(deleted)} fichier(s) supprimé(s) de {mods_dir}."]
            lines.extend(errors)
            self.state = "other"
            self._show(modrinthapi.installation_report_html(
                "Suppression terminée" if not errors else "Suppression partielle",
                lines, success=not errors))
            self._set_status(f"{len(deleted)} fichier(s) supprimé(s).")
            self.refresh_after_install()

        self._run_async(job, "Suppression…", replace=True)

    def open_mods_folder(self):
        """Open the target profile's `mods` folder in the file manager."""
        profile = self._current_target_profile()
        mods_dir = mods_dir_for(profile)
        try:
            os.makedirs(mods_dir, exist_ok=True)
        except OSError as e:
            self._set_status(f"Impossible de créer {mods_dir} : {e}")
            return
        for command in (("xdg-open", mods_dir), ("gio", "open", mods_dir)):
            try:
                subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                self._set_status(f"Dossier des mods ouvert : {mods_dir}")
                return
            except OSError:
                continue
        self._set_status(f"Aucun gestionnaire de fichiers disponible — dossier : {mods_dir}")

    # ------------------------------------------------------------------- links
    def handle_link(self, url: str):
        """Decode a link coming from the embedded HTML page."""
        if not url:
            return
        if url.startswith(("http://", "https://")):
            webbrowser.open(url)
            return

        prefix = f"{modrinthapi.LINK_SCHEME}://"
        legacy = {"modrinth-install://": "install", "project-preview://": "detail"}
        action = argument = ""
        for scheme, name in legacy.items():
            if url.startswith(scheme):
                action, argument = name, url[len(scheme):]
                break
        else:
            if not url.startswith(prefix):
                return
            rest = url[len(prefix):]
            action, _, argument = rest.partition("/")

        base_argument, _, raw_query = argument.partition("?")
        query = {}
        for item in raw_query.split("&"):
            if "=" in item:
                key, _, value = item.partition("=")
                query[key] = value

        # Les liens sont écrits dans la page HTML: ils sont encodés (et leurs esperluettes
        # transformées en &amp; par le moteur HTML). Sans ce décodage, la recherche portait
        # sur "sodium%20extra" et ne renvoyait aucun résultat.
        action = _html.unescape(action).strip("/").lower()
        base_argument = _html.unescape(urllib.parse.unquote(base_argument))
        query = {key: _html.unescape(urllib.parse.unquote_plus(value))
                 for key, value in query.items()}
        if action == "search":
            if base_argument:
                self.query.set(base_argument)
                self.new_search()
            elif query.get("page"):
                self.goto_page(int(query["page"]))
            elif query.get("type"):
                self.type_box.set(query["type"])
                self.new_search()
            else:
                self.goto_page(1)
        elif action == "page":
            self.goto_page(int(base_argument or query.get("page", 1)))
        elif action == "detail":
            self.show_project(base_argument)
        elif action == "versions":
            self.show_versions(base_argument)
        elif action in ("install", "install-version"):
            if action == "install-version":
                self.install_project("", version_id=base_argument)
            else:
                self.install_in_new_profile_or_target(base_argument,
                                                      new_window=query.get("type") == "modpack")
        elif action == "download":
            self.download_project(base_argument)
        elif action == "deps":
            self.install_dependencies(base_argument)
        elif action == "modpack":
            self.install_modpack(base_argument, create_profile=True)
        elif action == "new-profile":
            self.install_modpack(base_argument, create_profile=True)
        elif action == "target":
            if base_argument:
                app = self.app
                if app is not None and hasattr(app, "select_profile") and app.select_profile(base_argument):
                    self.set_target_profile()
                else:
                    self._set_status(f"Profil introuvable : {base_argument}")
            else:
                self.ask_target_profile()
        elif action == "home":
            self.show_home()
        elif action == "installed":
            self.show_installed()
        elif action == "delmod":
            self.delete_installed_mod(base_argument)
        elif action == "togglemod":
            self.toggle_installed_mod(base_argument)
        elif action == "delmod-all":
            self.delete_installed_mods("all", confirmed=base_argument == "ok")
        elif action == "delmod-disabled":
            self.delete_installed_mods("disabled", confirmed=base_argument == "ok")
        elif action == "togglemod-all":
            self.toggle_all_installed_mods(base_argument not in ("off", "0", "false", "non"))
        elif action == "openmods":
            self.open_mods_folder()
        elif action == "site":
            webbrowser.open("https://modrinth.com/" + (base_argument or ""))
        elif action == "open":
            webbrowser.open(argument)
        else:
            print(f"[mods] lien inconnu: {url}")

    def install_in_new_profile_or_target(self, project_id: str, new_window: bool = False):
        """Route an "Installer" click: modpacks get their own isolated profile."""
        if new_window:
            self.install_modpack(project_id, create_profile=True)
            return

        def job():
            project_data = modrinthapi.get_project_data(project_id)
            project_type = "mod"
            if isinstance(project_data, dict):
                project_type = project_data.get("project_type", "mod")
            self._call_main(self._route_install, project_id, project_type)
        self._run_async(job, "Préparation de l'installation…")

    def _route_install(self, project_id: str, project_type: str):
        if project_type == "modpack":
            self.install_modpack(project_id, create_profile=True)
        else:
            self.install_project(project_id)

    def _progress(self, message: str, fraction=None):
        if message:
            suffix = f" ({fraction * 100:.0f}%)" if isinstance(fraction, (int, float)) else ""
            self._set_status(f"{message}{suffix}")
