requirements=["portablemc>4.5","BeautifulSoup4","requests","TkinterWeb","lxml"]


import platform
assert platform.system() in ["Windows","Linux"], "Not supported on your system"
from portablemc.standard import Version, DownloadProgressEvent, StreamRunner, VersionNotFoundError, DownloadStartEvent, \
    DownloadCompleteEvent, Context
from portablemc.forge import ForgeVersion, _NeoForgeVersion
from portablemc.fabric import FabricVersion
from portablemc.optifine import OptifineVersion, get_compatible_versions as of_version_dict, \
    get_offline_versions as of_offline_dict, OptifinePatchEvent, OptifineStartInstallEvent
import json
#import sys
import threading
import os
import uuid
from pathlib import Path
#from tkinter import *
from tkinter.ttk import *
from tkinter import ttk, Frame, Canvas, Tk, Button, Misc
from tkinter import font

from bs4 import BeautifulSoup
# import custom widgets
from switchs import SwitchButton
from ctkwidgets import *
from NewsFrame import TkMcNews
from McOptions import SettingsFrame
from Modrinthframe import ModsFrame
from launcher_paths import (build_profile, ensure_profile_folders, instance_dir_for,
                            mods_dir_for, normalize_profile, profile_label, safe_profile_name,
                            unique_profile_name, version_and_loader)

from cache_system import *
from time import time_ns
import tkinter as tk

tbegin=time_ns()
print("Python part starting... Finished imports...")
print(f"Phase 1 (imports) finished after {(time_ns()-tbegin)/1000000} milliseconds")
# Le cache des versions est rafraîchi par l'écran de démarrage (voir main()) une fois la
# fenêtre affichée: l'interface ne reste donc plus bloquée plusieurs secondes au lancement.
# de plus, le launcher a accès à ces fichiers sans Internet
class SplashWindow(tk.Toplevel):
    """Écran de démarrage: s'affiche immédiatement et rend compte du chargement du
    cache des versions, qui se fait en arrière-plan pendant que la fenêtre se construit.

    C'est un Toplevel et non un second Tk: deux interpréteurs Tcl ne peuvent pas
    partager leurs images Tk, et le lanceur en utilise beaucoup.
    """

    def __init__(self, master):
        super().__init__(master)
        self.title("mcLaunch")
        self.configure(bg="#1E2020")
        self.overrideredirect(True)
        width, height = 460, 190
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        self.geometry(f"{width}x{height}+{(screen_w-width)//2}+{(screen_h-height)//2}")
        tk.Label(self, text="mcLaunch", font=("Helvetica", 26, "bold"),
                 bg="#1E2020", fg="green").pack(pady=(26, 2))
        self.status = tk.StringVar(self, value="Démarrage...")
        tk.Label(self, textvariable=self.status, bg="#1E2020", fg="white",
                 font=("Helvetica", 11)).pack()
        self.bar = CenteredProgressBar(self, width=380, height=14, bg="#2E3030",
                                       progress_color="green")
        self.bar.pack(pady=16)
        self.bar.set_maximum(100)
        self.bar.set(0)
        self.attributes("-topmost", True)
        self.update()  # force le dessin: la boucle d'évènements n'est pas encore lancée

    def progress(self, message, fraction=None):
        """Callback compatible avec cache_system.refresh_cache()."""
        def apply():
            self.status.set(message)
            if fraction is not None:
                self.bar.set(max(0, min(100, fraction*100)))
        try:
            self.after(0, apply)
        except RuntimeError:
            pass
class ProfileShow(ttk.Frame):
    def __init__(self,parent,content,app=None):
        self.main_app = app
        self.main_content = content
        buttonstylenormal={
            "background":"#2E3030",
            "activebackground":"#3E4040"
        }
        buttonstyleerror={
            "background":"#AA0000",
            "activebackground":"#BB0000"
        }
        super().__init__(parent,padding=10)
        iconname=content["type"]
        if iconname in ["alpha","beta"]:
            iconname="old"
        self.image=geticon(iconname,(64,64))
        self.deleteimage=geticon("delete",(32,32))
        self.editimage=geticon("edit",(32,32))
        self.icon=Label(self,borderwidth=0,image=self.image)
        self.name_label=Label(self,text=content["name"])
        self.version_label=Label(self,text=content["version"])
        self.type_label=Label(self,text=content["type"])
        if hasattr(content["loader"],"__len__") and len(content["loader"]) and content["type"].lower() in ("optifine","fabric","forge","neoforge","quilt"):
            self.loader_label = Label(self, text=content["loader"])
            self.loader_label.grid(row=1,column=3)
        self.edit_button=Button(self,image=self.editimage,command=self.editp,relief="flat",**buttonstylenormal)
        self.delete_button=Button(self,image=self.deleteimage,command=self.deletep, relief="flat",**buttonstyleerror)
        self.icon.grid(row=0,column=0,sticky="w",rowspan=2)
        self.name_label.grid(row=0,column=1,sticky="w",columnspan=3)
        self.version_label.grid(row=1,column=2,sticky="nsew")
        self.type_label.grid(row=1,column=1,sticky="nsew")
        #self.loader_label.grid(row=1,column=4,sticky="nsew")
        self.edit_button.grid(row=0,column=4,sticky="nsew",rowspan=2)
        self.delete_button.grid(row=0,column=5,sticky="nsew",rowspan=2)
        self.columnconfigure(0,weight=1)
        self.columnconfigure(1,weight=1)
        self.columnconfigure(2,weight=1)
        self.columnconfigure(3,weight=1)
    def deletep(self):
        self.main_app.delete_profile(self.main_content)
        self.destroy()

    def editp(self):
        self.main_app.edit_profile(self.main_content)
        self.destroy()


class ProfileEdit(ttk.Frame):
    """Profile Editor with bug fixes and optimized code structure."""

    # Version type configuration - centralized to reduce code duplication
    VERSION_CONFIGS = {
        "Vanilla": {"key": "release", "has_loader": False},
        "Snapshot": {"key": "snapshot", "has_loader": False},
        "Alpha": {"key": "old_alpha", "has_loader": False},
        "Beta": {"key": "old_beta", "has_loader": False},
        "Fabric": {"key": "release", "has_loader": True, "support_key": "fabric_support"},
        "Quilt": {"key": "release", "has_loader": True, "support_key": "quilt_support"},
        "Forge": {"key": None, "has_loader": True},
        "NeoForge": {"key": None, "has_loader": False},
        "Optifine": {"key": None, "has_loader": True},
    }

    def __init__(self, *args, command=None, **kw):
        super().__init__(*args, **kw)
        self.state = None
        self.command = command
        # Load all data upfront (keeps original synchronous behavior)
        self.official_version_list = get_version_list()
        self.fabric_support = get_fabric_support()
        self.fabric_loaders = get_fabric_loaders()
        self.quilt_support = get_fabric_support("https://meta.quiltmc.org/v3/versions")
        self.quilt_loaders = get_fabric_loaders("https://meta.quiltmc.org/v3/versions")
        self.forge_versions = get_forge_versions()
        self.neoforge_versions = get_neoforge_versions()
        self.optifine_versions = get_optifine_versions()
        # NeoForge's maven list only contains NeoForge versions; the Minecraft version
        # they belong to is derived from the version number (see cache_system).
        self.neoforge_by_game = neoforge_game_versions()
        self._versions_cache = {}
        self._create_ui()
    def set_content(self, params):
        """
        Populate all widgets from a dictionary of parameters.
        
        Args:
            params (dict): Dictionary containing profile data with keys:
                - name: Profile name
                - type: Version type (vanilla, fabric, forge, etc.)
                - version: Minecraft version
                - loader: Loader version
                - isolated: Boolean for isolated folder
                - enable_demo: Boolean for demo mode
                - enable_multiplayer: Boolean for multiplayer
                - enable_chat: Boolean for chat
                - enable_quick_play: Boolean for quick play
                - quick_play: Dict with quick play config (name for solo, host/port for mp)
        """
        # A profile coming from the configuration (or from a modpack) can be incomplete:
        # `normalize_profile` fills the missing keys so every widget below is consistent.
        params = normalize_profile(params) or {}
        # Set version type (triggers dependent updates)
        self.backup = params.copy()
        version_type = params.get("type", "vanilla").capitalize()
        if version_type not in self.VERSION_CONFIGS:
            version_type = "Vanilla"
        
        self.version_type_s.set(version_type)
        self.on_type_select()  # Trigger updates for loader, etc.
        
        # Set version
        version = params.get("version", "latest")
        self.version_s.set(version)
        
        # Trigger version change if needed (updates loader options)
        if self.VERSION_CONFIGS[version_type]["has_loader"]:
            self._on_version_change(None)
        
        # Set loader if visible
        loader = params.get("loader", "recommended")
        if self.loader_s.winfo_exists():
            self.loader_s.set(loader if loader else "recommended")
        
        # Set game options
        self.isolated_c.set(params.get("isolated", False))
        self.enable_demo_s.set(params.get("enable_demo", False))
        self.enable_multiplayer_s.set(params.get("enable_multiplayer", True))
        self.enable_chat_s.set(params.get("enable_chat", True))
        
        # Set quick play
        enable_quick_play = params.get("enable_quick_play", False)
        self.enable_quick_play_s.set(enable_quick_play)
        self.quick_play_toggle(enable_quick_play)
        
        # Set quick play details
        quick_play = params.get("quick_play", {})
        if enable_quick_play:
            if isinstance(quick_play, dict):
                if "name" in quick_play:
                    # Solo mode
                    self.quick_play_type_s.set("Solo")
                    self.quick_play_name_e.delete(0, "end")
                    self.quick_play_name_e.insert(0, quick_play["name"])
                    self._on_quick_play_type_change(None)
                elif "host" in quick_play:
                    # Multiplayer mode
                    self.quick_play_type_s.set("Multijoueur")
                    self.quick_play_name_e.delete(0, "end")
                    self.quick_play_name_e.insert(0, quick_play.get("host", ""))
                    self.quick_play_mp_port_e.delete(0, "end")
                    self.quick_play_mp_port_e.insert(0, str(quick_play.get("port", 25565)))
                    self._on_quick_play_type_change(None)
        
        # Set profile name (do this last so it can be overridden)
        self.profile_name_entry.delete(0, "end")
        self.profile_name_entry.insert(0, params.get("name", ""))
        self.quit_edit = self.save_from_backup
        self.backbutton.configure(command=self.quit_edit)

    def save_from_backup(self):
        """Save profile from backup."""
        self.set_content(self.backup)
        if self.save_profile(self.backup):
            self.destroy()
        else:
            self.profile_name_label.configure(foreground="red")


    def _create_ui(self):
        """Create and layout all UI widgets."""
        self.version_selection_f = ttk.Frame(self)

        # Version selection widgets
        self.version_type_l = Label(self.version_selection_f, text="Type de version:")
        self.version_type_s = Combobox(
            self.version_selection_f,
            values=list(self.VERSION_CONFIGS.keys()),
            state="readonly"
        )
        self.version_type_s.set("Vanilla")
        self.version_type_s.bind("<<ComboboxSelected>>", self.on_type_select)

        self.version_l = Label(self.version_selection_f, text="Version de Minecraft:")
        self.version_s = Combobox(self.version_selection_f, state="readonly")
        self.version_s.set("latest")

        self.loader_l = Label(self.version_selection_f, text="Version du loader:")
        self.recommendation_loader = Label(
            self.version_selection_f,
            text="Il vaut mieux garder la valeur recommandée pour la version du loader sur les versions non-officielles, sauf pour résoudre des problèmes de compatibilité de mods.",
            justify="left"
        )
        self.loader_s = Combobox(self.version_selection_f, state="readonly")

        # Game options
        self.profile_name_label = Label(self.version_selection_f, text="Nom du profile:")
        self.profile_name_entry = Entry(self.version_selection_f)

        self.isolated_l = Label(self.version_selection_f, text="Isoler le dossier de version :\n(utile pour les modpacks notamment)")
        self.isolated_c = SwitchButton(self.version_selection_f, value=False)

        self.enable_demo_l = Label(self.version_selection_f, text="Mode demo:")
        self.enable_demo_s = SwitchButton(self.version_selection_f, value=False)

        self.enable_multiplayer_l = Label(self.version_selection_f, text="Autoriser multijoueur:")
        self.enable_multiplayer_s = SwitchButton(self.version_selection_f)

        self.enable_chat_l = Label(self.version_selection_f, text="Fonctionnalités de chat:")
        self.enable_chat_s = SwitchButton(self.version_selection_f)

        self.enable_quick_play_l = Label(self.version_selection_f, text="Quick play:")
        self.enable_quick_play_s = SwitchButton(self.version_selection_f, command=self.quick_play_toggle, value=False)

        self.quick_play_type_l = Label(self.version_selection_f, text="Type de Quick Play:")
        self.quick_play_type_s = Combobox(
            self.version_selection_f,
            values=["Multijoueur", "Solo"],
            state="readonly"
        )
        self.quick_play_type_s.set("Solo")
        self.quick_play_type_s.bind("<<ComboboxSelected>>", self._on_quick_play_type_change)

        self.quick_play_mp_l = Label(self.version_selection_f, text="Adresse ipV4 ou dns du serveur:")
        self.quick_play_sp_l = Label(self.version_selection_f, text="Nom du monde:")
        self.quick_play_name_e = Entry(self.version_selection_f)

        self.quick_play_mp_port_l = Label(self.version_selection_f, text="Port:")
        self.quick_play_mp_port_e = Entry(self.version_selection_f)

        # Buttons
        self.nextbutton = Button(
            self.version_selection_f,
            background="green",
            text="Suivant →",
            borderwidth=4,
            activebackground="#00AA00",
            command=self.on_next
        )
        self.backbutton = ttk.Button(
            self.version_selection_f,
            style="launcher.ErrorButton",
            text="Annuler...",
            command=self.quit_edit
        )

        # Layout
        self.version_selection_f.pack(fill="both", expand=True, padx=50)
        self.version_selection_f.columnconfigure(0, weight=1)
        self.version_selection_f.columnconfigure(1, weight=1)

        # Initial grid
        self._layout_version_selection()

    def _layout_version_selection(self):
        """Layout version selection widgets."""
        self.version_type_l.grid(row=1, sticky="w")
        self.version_type_s.grid(row=1, column=1, sticky="ew")
        self.version_l.grid(sticky="w", row=2, column=0)
        self.version_s.grid(row=2, column=1, sticky="ew", pady=4)
        self.recommendation_loader.grid(row=4, columnspan=2, sticky="w")
        self.nextbutton.grid(row=30, column=1, sticky="e")
        self.backbutton.grid(row=30, column=0, sticky="w")

    def _get_versions_by_type(self, version_type):
        """Versions available for a type, memoised (the lists never change meanwhile).

        The Forge/NeoForge/OptiFine lists contain thousands of entries; without the
        cache, every combobox switch rebuilt them from scratch and the "Nouvelle
        version..." editor took seconds to open.
        """
        cached = self._versions_cache.get(version_type)
        if cached is None:
            cached = self._build_versions_by_type(version_type)
            self._versions_cache[version_type] = cached
        return list(cached)

    def _build_versions_by_type(self, version_type):
        """Get versions filtered by type - centralized to avoid code duplication."""
        config = self.VERSION_CONFIGS.get(version_type)

        if not config:
            return []

        # Handle special types (Forge, NeoForge, Optifine)
        if config["key"] is None:
            if version_type == "Forge":
                return list(self.forge_versions.keys())
            elif version_type == "NeoForge":
                # Only the Minecraft versions NeoForge actually supports, not the 1786
                # raw NeoForge builds (which are not Minecraft versions at all).
                return list(self.neoforge_by_game.keys())
            elif version_type == "Optifine":
                return list(self.optifine_versions.keys())
            return []

        # Handle standard types with optional support filter
        versions = [
            name for name, settings in self.official_version_list.items()
            if settings["type"] == config["key"]
        ]

        # Filter by support list if applicable
        if "support_key" in config:
            support_list = getattr(self, config["support_key"])
            versions = [v for v in versions if v in support_list]

        return versions

    def on_type_select(self, e=None):
        """Handle version type selection."""
        self.version_type_s.selection_clear()
        self.loader_l.grid_forget()
        self.loader_s.grid_forget()
        self.version_s.unbind("<<ComboboxSelected>>")

        version_type = self.version_type_s.get()
        config = self.VERSION_CONFIGS[version_type]

        # Update available versions
        versions = self._get_versions_by_type(version_type)
        self.version_s.configure(values=versions)
        self.version_s.set("latest")

        # Setup loader if needed
        if config["has_loader"]:
            self._setup_loader(version_type)
            self.loader_l.grid(row=3, column=0, sticky="w")
            self.loader_s.grid(row=3, column=1, sticky="ew")

            # Add binding for version change if needed
            if version_type in ("Forge", "Optifine", "NeoForge"):
                self.version_s.bind("<<ComboboxSelected>>", self._on_version_change)

    def _setup_loader(self, version_type):
        """Setup loader combobox values."""
        loaders = []

        if version_type == "Fabric":
            loaders = ["recommended"] + self.fabric_loaders
        elif version_type == "Quilt":
            loaders = ["recommended"] + self.quilt_loaders
        elif version_type == "Forge":
            if self.forge_versions:
                first_key = next(iter(self.forge_versions))
                loaders = ["recommended"] + self.forge_versions[first_key]
        elif version_type == "Optifine":
            if self.optifine_versions:
                first_key = next(iter(self.optifine_versions))
                loaders = ["recommended"] + [v.edition for v in self.optifine_versions[first_key]]
        elif version_type == "NeoForge":
            if self.neoforge_by_game:
                first_key = next(iter(self.neoforge_by_game))
                loaders = ["recommended"] + self.neoforge_by_game[first_key]

        self.loader_s.configure(values=loaders)
        self.loader_s.set("recommended")

    def _on_version_change(self, event):
        """Update loader when version changes (Forge/Optifine)."""
        self.version_s.selection_clear()
        version_type = self.version_type_s.get()
        version = self.version_s.get()

        if version == "latest":
            versions = self._get_versions_by_type(version_type)
            version = versions[0] if versions else None

        if not version:
            return

        if version_type == "Forge":
            loaders = ["recommended"] + self.forge_versions.get(version, [])
            self.loader_s.configure(values=loaders)
            self.loader_s.set("recommended")
        elif version_type == "Optifine":
            loaders = ["recommended"] + [v.edition for v in self.optifine_versions.get(version, [])]
            self.loader_s.configure(values=loaders)
            self.loader_s.set("recommended")
        elif version_type == "NeoForge":
            # The NeoForge build number is tied to the Minecraft version: 1.21.1 -> 21.1.x
            loaders = ["recommended"] + list(self.neoforge_by_game.get(version, []))
            self.loader_s.configure(values=loaders)
            self.loader_s.set("recommended")

    def _on_quick_play_type_change(self, event):
        """Handle quick play type change."""
        self.quick_play_type_s.selection_clear()
        self.quick_play_toggle(self.enable_quick_play_s.get())

    def quick_play_toggle(self, val=True):
        """Toggle quick play options visibility."""
        if not val:
            self.quick_play_type_l.grid_forget()
            self.quick_play_type_s.grid_forget()
            self.quick_play_mp_l.grid_forget()
            self.quick_play_mp_port_l.grid_forget()
            self.quick_play_mp_port_e.grid_forget()
            self.quick_play_sp_l.grid_forget()
            self.quick_play_name_e.grid_forget()
            return

        self.quick_play_type_l.grid(row=7, column=0, sticky="w")
        self.quick_play_type_s.grid(row=7, column=1, sticky="we")
        self.quick_play_name_e.grid(row=8, column=1, sticky="ew")

        if self.quick_play_type_s.get() == "Solo":
            self.quick_play_sp_l.grid(row=8, column=0, sticky="w")
            self.quick_play_mp_l.grid_forget()
            self.quick_play_mp_port_l.grid_forget()
            self.quick_play_mp_port_e.grid_forget()
        else:
            self.quick_play_sp_l.grid_forget()
            self.quick_play_mp_l.grid(row=8, column=0, sticky="w")
            self.quick_play_mp_port_l.grid(row=9, column=0, sticky="w")
            self.quick_play_mp_port_e.grid(row=9, column=1, sticky="ew")

    def on_next(self):
        """Handle next/save button."""
        if self.state is None:
            self._show_options_screen()
        elif self.state == "save":
            self._save_profile()

    def _show_options_screen(self):
        """Transition to options screen."""
        # Hide version selection widgets
        self.version_type_l.grid_forget()
        self.version_type_s.grid_forget()
        self.version_l.grid_forget()
        self.version_s.grid_forget()
        self.loader_l.grid_forget()
        self.loader_s.grid_forget()
        self.recommendation_loader.grid_forget()

        # Generate profile name
        version_name = self._generate_profile_name()

        # Show options
        self.profile_name_label.grid(row=0, column=0, sticky="w")
        self.profile_name_entry.grid(row=0, column=1, sticky="ew")
        self.profile_name_entry.delete(0, "end")
        self.profile_name_entry.insert(0, version_name)

        self.isolated_l.grid(row=1, column=0, sticky="w")
        self.isolated_c.grid(row=1, column=1, sticky="e", pady=6)
        self.enable_demo_l.grid(row=2, column=0, sticky="w")
        self.enable_demo_s.grid(row=2, column=1, sticky="e", pady=6)
        self.enable_multiplayer_l.grid(row=4, column=0, sticky="w")
        self.enable_multiplayer_s.grid(row=4, column=1, sticky="e", pady=6)
        self.enable_chat_l.grid(row=5, column=0, sticky="w")
        self.enable_chat_s.grid(row=5, column=1, sticky="e", pady=6)
        self.enable_quick_play_l.grid(row=6, column=0, sticky="w")
        self.enable_quick_play_s.grid(row=6, column=1, sticky="e", pady=6)

        self.nextbutton.configure(text="Sauvegarder")
        self.state = "save"

    def _generate_profile_name(self):
        """Generate a profile name based on selected options."""
        version_type = self.version_type_s.get()
        version = self.version_s.get()

        if version == "latest":
            versions = self._get_versions_by_type(version_type)
            version = versions[0] if versions else version

        loader = ""
        if self.VERSION_CONFIGS[version_type]["has_loader"]:
            loader = " " + self.get_latest_loader()

        return f"{version_type} {version}{loader}".strip()

    def _save_profile(self):
        """Save the profile and call command callback."""
        result = {
            "name": self.profile_name_entry.get().strip(),
            "type": self.version_type_s.get().lower(),
            "version": self._resolve_version(),
            "loader": self._resolve_loader(),
            "isolated": self.isolated_c.get(),
            "enable_demo": self.enable_demo_s.get(),
            "enable_multiplayer": self.enable_multiplayer_s.get(),
            "enable_chat": self.enable_chat_s.get(),
            "enable_quick_play": self.enable_quick_play_s.get(),
        }
        # Quick play is only stored when it is actually used; `normalize_profile` adds an
        # empty dict otherwise, so the launcher can always do `profile["quick_play"]`.
        if result["enable_quick_play"]:
            result["quick_play"] = self._get_quick_play_config()
        result = normalize_profile(result)
        if not result["name"]:
            result["name"] = f"{result['type'].capitalize()} {result['version']}".strip()

        if self.save_profile(result):
            self.destroy()
        else:
            self.profile_name_label.configure(foreground="red")

    def _resolve_version(self):
        """Resolve the actual version string."""
        version = self.version_s.get()
        if version != "latest":
            return version

        versions = self._get_versions_by_type(self.version_type_s.get())
        return versions[0] if versions else version

    def _resolve_loader(self):
        """Resolve the loader to actual value."""
        # Only try to get loader if it's visible
        """if not self.loader_s.winfo_viewable():
            return ""
        """

        loader = self.loader_s.get()
        if loader == "recommended":
            return self.get_latest_loader()
        return loader

    def _get_quick_play_config(self):
        """Build quick play configuration."""
        if self.quick_play_type_s.get() == "Solo":
            return {"name": self.quick_play_name_e.get()}
        else:
            return {
                "host": self.quick_play_name_e.get(),
                "port": int(self.quick_play_mp_port_e.get())
            }

    def get_latest_loader(self):
        """Get the latest loader version."""
        version_type = self.version_type_s.get()
        version = self.version_s.get()

        if version == "latest":
            versions = self._get_versions_by_type(version_type)
            version = versions[0] if versions else None

        if not version:
            return ""

        if version_type == "Fabric":
            return self.fabric_loaders[0] if self.fabric_loaders else ""
        elif version_type == "Quilt":
            return self.quilt_loaders[0] if self.quilt_loaders else ""
        elif version_type == "Forge":
            if version in self.forge_versions:
                return self.forge_versions[version][0] if self.forge_versions[version] else ""
        elif version_type == "Optifine":
            if version in self.optifine_versions:
                return self.optifine_versions[version][0].edition if self.optifine_versions[version] else ""
        elif version_type == "NeoForge":
            builds = self.neoforge_by_game.get(version) or []
            return builds[0] if builds else ""

        return ""

    def save_profile(self, result):
        """Save profile via callback."""
        if self.command is not None:
            return self.command(result)
        return False

    def quit_edit(self):
        """Cancel edit - EXACT original behavior."""
        if self.command is not None:
            return self.command(quit)  # IMPORTANT: pass 'quit' object, not string
        else:
            self.destroy()

class Myapp(Tk):
    active_start_thread=None
    progress=0
    def __init__(self, splash_progress=None):
        self.splash_progress = splash_progress or (lambda message, fraction=None: None)
        self.max_download_size = None
        self.downloaded_size = 0
        self.download_threads_speed = []
        self.profile=None
        self.game_running = False
        super().__init__()
        # L'écran de démarrage est un enfant de cette fenêtre (voir SplashWindow) et
        # remplace l'ancien "loading screen" qui était encore à faire.
        self.splash = None
        self.withdraw()
        try:
            self.splash = SplashWindow(self)
        except Exception as e:  # noqa: BLE001 - the launcher must start even without splash
            print(f"Ecran de démarrage indisponible: {e}")
        self.splash_progress("Préparation de l'interface...", 0.05)
        self.v_list=get_version_list()
        try:
            with open(os.path.join(mc_directory,"mcLaunch_profiles.json"),"r") as f:
                self.launcher_conf=json.load(f)
        except:
            self.launcher_conf={"name":"Steve","uuid":str(uuid.uuid4()),"accounts":{"Steve":{"pseudo":"Steve","uuid":str(uuid.uuid4())}},"profiles":self.genprofiles()}
        if not "onlineaccount" in self.launcher_conf.keys():
            self.launcher_conf["onlineaccount"]=None
        if not "profiles" in self.launcher_conf.keys():
            self.launcher_conf["profiles"]=self.genprofiles()
        else:
            self.launcher_conf["profiles"]=self.genprofiles(self.launcher_conf["profiles"])
        # Un profil peut être stocké comme simple nom de version ou être incomplet
        # (ancienne version du lanceur, fichier modifié à la main, installateur de
        # modpacks): on les normalise tous, le code de lancement et les onglets Versions
        # et Mods ne manipulent donc que des dictionnaires complets.
        self.launcher_conf["profiles"] = [q for q in
                                          (normalize_profile(q) for q in self.launcher_conf["profiles"])
                                          if q]
        #self.config={}
        self.progressmessage=tk.StringVar()
        self.progressbar=CenteredProgressBar(self,textvariable=self.progressmessage,bg="#2E3030",fg="white",progress_color="green")
        self.progressbar.set(0)
        self.geometry("950x600")
        self.minsize(950,600)
        self.title("Minecraft Launcher")
        self.helv18 = font.Font(family='Helvetica', size=18, weight='bold')
        self.helv12 = font.Font(family='Helvetica', size=12, weight='bold')
        # Création d'un style personnalisé
        self.style = ttk.Style()
        self.style.theme_use('default')  # Utilisation d'un thème agréable avec les personnalisations
        self.style.map('TCombobox', fieldbackground=[('readonly', '#2E3030')])
        self.style.map('TCombobox', background=[('readonly', '#2E3030')])
        self.style.map('TCombobox', selectbackground=[('readonly', '#2E3030')])
        # Modification du style de la Combobox
        self.style.configure(
            "TCombobox",
            relief="flat",             # Met le relief à plat
            borderwidth=0,             # Supprime les bordures
            padding=2,                 # Optionnel : ajoute un peu de rembourrage
            background="#2E3030",
            fieldbackground="#2E3030",
            selectbackground="#2E3030",
            foreground="white",
            highlightbackground = "#1E2020",highlightcolor= "#1E2020",
            arrowcolor="#AAAAAA"
        )
        self.style.configure(
            "TScrollbar",
            gripcount=0,             # Supprime les grips (si présents)
            relief="flat",           # Style plat
            borderwidth=0,           # Pas de bordures
            troughcolor="white",     # Couleur de la zone de fond
            background="#c0c0c0",    # Couleur du curseur
            arrowcolor="#666666"     # Couleur des flèches
            )
        self.style.configure(
            "TFrame",
            background="#2E3030"
        )
        self.style.configure(
            "launcher.ErrorButton",
            background="red",
            highlightbackground = "red",
            highlightcolor= "red",
            foreground="white"
        )
        self.style.map("launcher.ErrorButton", foreground=[('active', 'white')], background=[('active', '#FF0000')])
        self.style.layout("launcher.ErrorButton",layoutspec=self.style.layout("TButton"))
        self.style.configure('TLabel', background="#2e3030", foreground="white",highlightbackground = "#1E2020",highlightcolor= "#1E2020")
        self.style.map('TScrollbar', background=[('active', '#a0a0a0')])
        # Vertical left frame containing the buttons

        self.tabsf=Frame(self, bg="#1E2020",width=400)
        self.tabsf.pack_propagate(False)
        self.tabsf.pack(side="left",fill="both")
        self.current_tab="news"
        # Tabs
        self.tabs_news=Button(self.tabsf,text="Actualités",command=lambda t="news": self.show_current_tab(t))
        self.tabs_news.pack(fill="x",side="top")
        
        self.tabs_profiles=Button(self.tabsf,text="Versions",command=lambda t="versions": self.show_current_tab(t))
        self.tabs_profiles.pack(fill="x",side="top")

        self.tabs_mods=Button(self.tabsf,text="Mods&Modpacks",command=lambda t="mods": self.show_current_tab(t))
        self.tabs_mods.pack(fill="x",side="top")
        
        self.tabs_options=Button(self.tabsf,text="Options",command=lambda t="options": self.show_current_tab(t))
        self.tabs_options.pack(fill="x",side="top")

        self.tabsf.configure(width=200)
        self.startbutton=Button(self.tabsf,text="Lancer le jeu",command=self.start_mc,fg="black",bg="green",borderwidth=5,font=self.helv12,height=2,width=18,activebackground="#009900",highlightbackground = "#1E2020",highlightcolor= "#1E2020")
        self.startbutton["state"]="disabled"
        # Selection du profile
        self.official_version_list=get_version_list()
        self.profileselect=Combobox(self.tabsf,values=[p["name"] for p in self.launcher_conf["profiles"]]+["Nouveau profile..."]+[name for name,settings in self.official_version_list.items() if settings["type"]=="release"],state="readonly")
        self.profileselect.bind("<<ComboboxSelected>>", self.on_profile_selection)
        self.profileselect.pack(side="bottom",fill="x")
        self.profileselect.set("Selectionner un profil...")
        # Le profil sélectionné est restauré au démarrage (l'ancien code plantait si le
        # fichier contenait une simple chaîne au lieu d'un dictionnaire).
        self.launcher_conf["selected_profile"] = normalize_profile(
            self.launcher_conf.get("selected_profile"))
        if self.launcher_conf["selected_profile"] is not None:
            self.profile = self.launcher_conf["selected_profile"]
            self.profileselect.set(self.profile["name"])
            self.startbutton["state"]="normal"
        self.startbutton.pack(side="bottom",padx=10,pady=10)
        
        # Barre de statut du bas affichée lors du téléchargement
        print(f"Phase 2 finished after {(time_ns()-tbegin)/1000000} milliseconds")
        # Contenu des onglets
        self.splash_progress("Chargement des actualités...", 0.30)
        self.mcnews=TkMcNews(self)
        self.mcnews.pack(side="right",fill="both")
        # Onglet Mods & Modpacks (recherche Modrinth, installation de mods et modpacks)
        self.splash_progress("Préparation de l'onglet Mods & Modpacks...", 0.40)
        self.modsframe=ModsFrame(self, app=self)

        self.profiles_f=ScrollableFrame(self)
        #self.newprofile_f=Frame(self.profiles_f.scrollable_frame)
        
        #self.newprofile_f.pack(fill="both",side="top")
        #self.profile_f_l=Frame(self.profiles_f)
        for p in self.launcher_conf["profiles"]:
            ProfileShow(self.profiles_f.scrollable_frame,p,self).pack(fill="x")
        self.profile_e = ProfileEdit(self.profiles_f.scrollable_frame, command=self.validate_profile)
        self.addprofile_b=Button(self.profiles_f.scrollable_frame,text="Nouvelle version...",fg="black",bg="green",borderwidth=10,font=self.helv18,height=2,width=25,activebackground="#009900",command=self.create_new_profile)
        self.addprofile_b.pack()
        #self.profile_f_l.pack(fill="both",expand=True)
        #self.profile_e=ProfileEdit(self.newprofile_f,command=self.validate_profile)
        #self.profile_e.pack(fill="both")
        self.splash_progress("Chargement des options et des comptes...", 0.55)
        self.optstab=SettingsFrame(self,self.launcher_conf)
        # affichage
        self.splash_progress("Affichage de la fenêtre...", 0.65)
        self.show_current_tab()
        self.tabsf.configure(width=300)
        startupdelta=(time_ns()-tbegin)/1000000
        print(f"Startup took {startupdelta} milliseconds")
        self.bind("<Configure>",self.on_resize)
        # Dernière étape: rafraîchir le cache des versions sans bloquer l'interface.
        self.start_background_init()

    def call_main(self, function, *args, delay=0, **kwargs):
        """Exécute `function` dans le fil principal (appelable depuis un thread).

        `after` n'est pas thread-safe: l'ancien code planifiait `_finish_startup` depuis
        le thread de rafraîchissement du cache, ce qui pouvait tuer l'interpréteur
        ("Tcl_AsyncDelete: async handler deleted by the wrong thread") quand la fenêtre
        était fermée juste après. Un minuteur de secours garantit que l'appel a lieu.
        """
        state = {"done": False}

        def run():
            state["done"] = True
            try:
                function(*args, **kwargs)
            except Exception as e:  # noqa: BLE001
                print(f"Erreur dans la tâche planifiée: {e}")

        watchdog = None
        try:
            watchdog = self.after(delay + 3000 if delay else 3000, run)
            self.after(delay, run)
        except RuntimeError:
            if not state["done"] and watchdog is not None:
                try:
                    self.after_cancel(watchdog)
                except Exception:  # noqa: BLE001
                    pass

    def splash_progress(self, message, fraction=None):
        """Rend compte de l'avancement du démarrage (appelé aussi par cache_system)."""
        splash = getattr(self, "splash", None)
        if splash is None:
            return
        try:
            splash.progress(message, fraction)
        except Exception:  # noqa: BLE001
            pass

    def start_background_init(self):
        """Rafraîchit le cache des versions en tâche de fond, puis ferme l'écran de démarrage."""
        def worker():
            try:
                refresh_cache(progress=self.splash_progress)
            except Exception as e:  # noqa: BLE001 - hors ligne: on garde le cache existant
                print(f"Cache des versions incomplet: {e}")
            self.call_main(self._finish_startup, delay=300)
        threading.Thread(target=worker, daemon=True).start()

    def _finish_startup(self):
        self.splash_progress("Prêt.", 1.0)
        splash, self.splash = getattr(self, "splash", None), None
        if splash is not None:
            try:
                splash.destroy()
            except Exception:  # noqa: BLE001
                pass
        self.deiconify()
        self.lift()
        # Le cache des versions vient d'être téléchargé: les listes construites au
        # démarrage (à partir d'un manifeste Mojang absent ou incomplet) sont refaites,
        # sans quoi l'éditeur de versions n'affichait que quelques entrées.
        self.reload_version_data()
        self.refresh_profiles_ui()
        print(f"Interface prête après {(time_ns()-tbegin)/1000000} millisecondes")

    def reload_version_data(self):
        """Recharge les listes de versions (après le rafraîchissement du cache)."""
        self.official_version_list = get_version_list()
        self.v_list = self.official_version_list
        if hasattr(self, "profiles_f"):
            self.profile_e.official_version_list = self.official_version_list
            self.profile_e.fabric_support = get_fabric_support()
            self.profile_e.fabric_loaders = get_fabric_loaders()
            self.profile_e.quilt_support = get_fabric_support("https://meta.quiltmc.org/v3/versions")
            self.profile_e.quilt_loaders = get_fabric_loaders("https://meta.quiltmc.org/v3/versions")
            self.profile_e.forge_versions = get_forge_versions()
            self.profile_e.neoforge_versions = get_neoforge_versions()
            self.profile_e.neoforge_by_game = neoforge_game_versions()
            self.profile_e.optifine_versions = get_optifine_versions()
            self.profile_e._versions_cache = {}
            if not self.profile_e.winfo_ismapped():
                # Ne pas réinitialiser les listes si l'utilisateur est en train de créer
                # un profil à la main.
                self.profile_e.on_type_select()
        if hasattr(self, "modsframe"):
            self.modsframe._load_game_versions()

    def on_resize(self, event):
        if hasattr(event,"width"):
            self.progressbar.configure(width=event.width,height=15)

    # ------------------------------------------------------------------ settings
    GAME_KEYS = ("enable_demo", "enable_multiplayer", "enable_chat", "enable_quick_play")

    def _profile_settings(self, profile):
        """Complète les réglages manquants d'un profil (profils créés par un modpack,
        profils importés d'une ancienne version du lanceur, ...)."""
        normalized = normalize_profile(profile)
        return normalized if normalized is not None else profile

    # ------------------------------------------------------------------- launching
    def start_mc(self, in_thread=False):
        if not in_thread:
            if self.active_start_thread is not None and self.active_start_thread.is_alive():
                self.message("Information", "Le jeu est déjà en cours de lancement.")
                return
            self.active_start_thread=threading.Thread(target=self.start_mc, args=(True,), daemon=True)
            self.progressbar.place(anchor="sw",x=0,rely=1,relwidth=1,height=25)
            self.progressbar.set(0)
            Misc.lift(self.progressbar)
            self.progressbar.set_maximum(100)
            self.progressmessage.set("Lancement du jeu...")
            self.active_start_thread.start()
            return
        if self.profile is None:
            self.message("Erreur", "Aucun profil sélectionné.")
            self.after(0, self._hide_progressbar)
            return
        try:
            self.progressmessage.set("Préparation de la version...")
            env = self.build_environment(self.profile)
            env.auth_session=self.optstab.get_auth()
            try:
                env.resolution=tuple(int(v) for v in self.optstab.get_resolution().split("x"))
            except (ValueError, AttributeError):
                print("Résolution invalide, la résolution par défaut sera utilisée.")
            if self.profile.get("enable_multiplayer") is False:
                env.disable_multiplayer=True
            if self.profile.get("enable_chat") is False:
                env.disable_chat=True
            if self.profile.get("enable_demo") is True:
                env.demo=True
            if self.profile.get("enable_quick_play") is True:
                quick_play = self.profile.get("quick_play") or {}
                if quick_play.get("host"):
                    env.set_quick_play_multiplayer(host=quick_play["host"],
                                                   port=int(quick_play.get("port", 25565)))
                elif quick_play.get("name"):
                    env.set_quick_play_singleplayer(level_name=quick_play["name"])
            env=env.install(watcher=self)
            env.jvm_args += self.optstab.get_jvm_args()
            self.progressmessage.set("Lancement de Minecraft...")
            self.after(0, self._enter_game_mode)
            self.game_running = True
            env.run(runner=StreamRunner())
        except Exception as e:  # noqa: BLE001 - l'utilisateur doit voir l'erreur, pas un crash
            import traceback
            traceback.print_exc()
            self.message("Erreur de lancement", f"Impossible de lancer le jeu: {e}")
        finally:
            self.game_running = False
            self.after(0, self._leave_game_mode)

    def _enter_game_mode(self):
        """Le jeu prend le relais: on cache la fenêtre du lanceur."""
        self.progressbar.place_forget()
        self.withdraw()

    def _leave_game_mode(self):
        self.progressbar.place_forget()
        try:
            self.deiconify()
            self.lift()
        except Exception:  # noqa: BLE001
            pass

    def _hide_progressbar(self):
        self.progressbar.place_forget()

    def build_environment(self, profile):
        """Construit l'objet `Version` de portablemc correspondant à un profil.

        `profile` est soit une chaîne (nom de version officielle), soit un profil modpack.
        """
        # Un profil peut être incomplet (modpack, ancien profil): on complète toujours.
        profile = normalize_profile(profile)
        if profile is None:
            raise ValueError("Aucun profil à lancer.")
        self.profile = profile
        self._profile_settings(profile)
        if isinstance(profile, str):
            return Version(profile)
        ctx = Context()
        if profile.get("isolated") is True:
            # le dossier de version est créé automatiquement
            ctx = Context(work_dir = Path(mc_directory) / "versions" / profile["name"])
        profile_type = str(profile.get("type", "vanilla")).lower()
        if profile_type in ("vanilla", "snapshot", "alpha", "beta"):
            env = Version(profile["version"], context=ctx)
        elif profile_type == "forge":
            vname = profile["version"]
            if profile.get("loader") and profile["loader"] != "recommended":
                vname = vname + "-" + profile["loader"]
            env = ForgeVersion(vname, context=ctx)
        elif profile_type == "fabric":
            args = [profile["version"]]
            if profile.get("loader") and profile["loader"] != "recommended":
                args = [profile["version"], profile["loader"]]
            env = FabricVersion.with_fabric(*args, context=ctx)
        elif profile_type == "quilt":
            args = [profile["version"]]
            if profile.get("loader") and profile["loader"] != "recommended":
                args = [profile["version"], profile["loader"]]
            env = FabricVersion.with_quilt(*args, context=ctx)
        elif profile_type == "optifine":
            loader = profile.get("loader") or "latest"
            env = OptifineVersion(version=profile["version"] + ":" + loader, context=ctx)
        elif profile_type == "neoforge":
            # NeoForge est identifié par sa propre version (21.1.256 pour Minecraft 1.21.1):
            # portablemc ne sait dériver que les versions 1.x, on utilise donc directement
            # la version NeoForge choisie, ou la plus récente connue pour cette version de
            # Minecraft (les versions 26.x n'ont pas de dérivation automatique).
            build = str(profile.get("loader") or "")
            if not build or build == "recommended":
                candidates = neoforge_game_versions().get(profile["version"]) or []
                build = candidates[0] if candidates else profile["version"]
            env = _NeoForgeVersion(build, context=ctx)
        else:
            raise ValueError(f"Type de profil inconnu: {profile_type!r}")
        return env

    def show_current_tab(self,selection=None):
        
        if selection in ["news","versions","mods","options"]: self.current_tab=selection
        ts=(self.tabs_news,self.tabs_profiles,self.tabs_mods,self.tabs_options)
        for t in ts: # remet les onglets dans leur état original
            t["state"]="normal"
            t['font']=self.helv18
            t.configure(background="#1E2020",highlightbackground = "#1E2020",highlightcolor= "#1E2020", foreground="green",relief="flat",width=15,height=2,activebackground="#2E3030",activeforeground="green",borderwidth=0)
        tab_contents=[self.mcnews,self.profiles_f,self.optstab, self.modsframe]
        for tc in tab_contents:
            tc.pack_forget()
        match self.current_tab:
            case "news":
                self.tabs_news["state"]="disabled"
                self.tabs_news.configure(background="green", disabledforeground="white",relief="flat",width=15,height=2)
                self.mcnews.pack(side="left",fill="both",expand=True) # affiche le contenu
            case "versions":
                self.tabs_profiles["state"]="disabled"
                self.tabs_profiles.configure(background="green", disabledforeground="white",relief="flat",width=15,height=2)
                self.profiles_f.pack(side="left",fill="both",expand=True)
                self.profiles_f.scroll_to_top()
            case "mods":
                self.tabs_mods["state"]="disabled"
                self.tabs_mods.configure(background="green", disabledforeground="white",relief="flat",width=15,height=2)
                self.modsframe.pack(side="left", fill="both", expand=True)
            case "options":
                self.tabs_options["state"]="disabled"
                self.tabs_options.configure(background="green", disabledforeground="white",relief="flat",width=15,height=2)
                self.optstab.pack(side="left",fill="both",expand=True)

    def genprofiles(self,current_list=[]):
        r=current_list
        return r

    def find_profile(self, name):
        """Le profil portant ce nom (dictionnaire normalisé), ou None."""
        if not name:
            return None
        for profile in self.launcher_conf["profiles"]:
            profile = normalize_profile(profile)
            if profile is not None and profile["name"] == name:
                return profile
        return None

    def select_profile(self, name, show_versions_tab=False):
        """Cible un profil (ou une version officielle) à partir de son nom.

        Renvoie True si la sélection a réussi. C'est le point d'entrée unique: liste
        déroulante du bas, sélecteur de l'onglet Mods et liens
        ``mclaunch://target/<profil>`` passent tous par ici, l'onglet Mods est donc
        toujours synchronisé avec le profil réellement utilisé pour l'installation.
        """
        profile = self.find_profile(name)
        if profile is None and name in self.official_version_list:
            profile = normalize_profile(name)
        if profile is None:
            return False
        self.profile = profile
        self.launcher_conf["selected_profile"] = profile
        self.startbutton["state"] = "normal"
        self.profileselect.set(profile["name"])
        if show_versions_tab:
            self.show_current_tab("profiles")
        self.sync_mods_frame()
        try:
            self.save_options()
        except Exception as e:  # noqa: BLE001 - la configuration sera réessayée à la fermeture
            print(f"Impossible de sauvegarder le profil sélectionné: {e}")
        return True

    def sync_mods_frame(self):
        """Prévient l'onglet Mods que le profil ciblé a changé (il filtre là-dessus)."""
        if hasattr(self, "modsframe"):
            self.modsframe.set_target_profile(self.profile)

    def on_profile_selection(self,event):
        self.profileselect.selection_clear()
        selection=self.profileselect.get()
        self.startbutton["state"]="disabled"
        if selection == "Nouveau profile...":
            self.profileselect.set("Selectionner un profile...")
            self.show_current_tab("profiles")
            self.create_new_profile()
            self.profile=None
            return
        if not self.select_profile(selection):
            self.message("Error","Impossible de trouver le profile spécifié. Quelque chose s'est mal passé dans le lanceur.")
    def message(self,msgt,content):
        print(f"{msgt}: {content}")
    def create_new_profile(self):
        self.profile_e.pack(fill="both")
        self.addprofile_b.pack_forget()
        self.profiles_f.scroll_to_bottom()

    def update_profile_list(self):
        """Conservée pour compatibilité: reconstruit la liste et le sélecteur."""
        self.refresh_profiles_ui()
    def validate_profile(self,content):
        if content==quit:
            self.profile_e.destroy()
            self.profile_e = ProfileEdit(self.profiles_f.scrollable_frame, command=self.validate_profile)
            self.addprofile_b.pack()
            self.refresh_profiles_ui()
            return True
        list_names=[p["name"] for p in self.launcher_conf["profiles"]]
        if not content["name"] in list_names:
            self.launcher_conf["profiles"].append(content)
            ProfileShow(self.profiles_f.scrollable_frame, content,self).pack(fill="x")
            print("New profile created: ",content)
            self.profile_e.destroy()
            self.profile_e = ProfileEdit(self.profiles_f.scrollable_frame, command=self.validate_profile)
            self.addprofile_b.pack()
            self.refresh_profiles_ui()
            return True
        else:
            return False
    def delete_profile(self,content):
        """Supprime un profil (accepte le dictionnaire du profil ou son nom)."""
        content = normalize_profile(content)
        if content is None:
            return
        name = content["name"]
        names = self.profile_names()
        if name not in names:
            return
        # suppression par nom: l'objet peut avoir été remplacé par refresh_profiles_ui
        del self.launcher_conf["profiles"][names.index(name)]
        selected = self.launcher_conf.get("selected_profile")
        selected = normalize_profile(selected)
        if selected is not None and selected.get("name") == name:
            self.launcher_conf.pop("selected_profile", None)
        if self.profile is not None and self.profile.get("name") == name:
            self.profile = None
            self.startbutton["state"] = "disabled"
            self.profileselect.set("Selectionner un profil...")
        self.refresh_profiles_ui()
        try:
            self.save_options()
        except Exception as e:  # noqa: BLE001
            print(f"Sauvegarde impossible: {e}")

    def edit_profile(self,content):
        """Ouvre l'éditeur pré-rempli (le profil est supprimé puis recréé à la sauvegarde)."""
        content = normalize_profile(content)
        if content is None:
            return
        self.profile_e.set_content(content)
        self.delete_profile(content)
        self.profile_e.pack(fill="both")
        self.addprofile_b.pack_forget()
        self.profiles_f.scroll_to_bottom()

    # ------------------------------------------------------------ profils : helpers
    def profile_names(self):
        names = []
        for profile in self.launcher_conf["profiles"]:
            profile = normalize_profile(profile)
            if profile is not None:
                names.append(profile["name"])
        return names

    def profile_selector_values(self):
        """Valeurs de la liste déroulante du bas: profils + "Nouveau profile..." + versions."""
        return (self.profile_names() + ["Nouveau profile..."] +
                [name for name, settings in self.official_version_list.items()
                 if settings["type"] == "release"])

    def refresh_profiles_ui(self):
        """Reconstruit la liste des profils (versions, mods, sélecteur)."""
        if not hasattr(self, "profiles_f"):
            return
        self.profileselect.configure(values=self.profile_selector_values())
        for child in list(self.profiles_f.scrollable_frame.winfo_children()):
            if isinstance(child, ProfileShow):
                child.destroy()
        for profile in self.launcher_conf["profiles"]:
            profile = normalize_profile(profile)
            if profile is None:
                continue
            ProfileShow(self.profiles_f.scrollable_frame, profile, self).pack(fill="x")
        self.sync_mods_frame()
        print(f"Profils: {self.profile_names()}")

    def register_profile(self, profile: dict, select: bool = True):
        """Ajoute un profil à la configuration (utilisé par l'installateur de modpacks)."""
        profile = normalize_profile(profile)
        if profile is None:
            return None
        if profile["name"] in self.profile_names():
            profile["name"] = unique_profile_name(profile["name"], self.profile_names())
        self.launcher_conf["profiles"].append(profile)
        print(f"Nouveau profil: {profile}")
        try:
            self.save_options()
        except Exception as e:  # noqa: BLE001
            print(f"Sauvegarde impossible: {e}")
        self.refresh_profiles_ui()
        if select:
            self.select_profile(profile["name"])
        return profile

    def finalise_modpack_profile(self, profile: dict, result: dict):
        """Après installation d'un modpack: renseigne la version exacte du loader."""
        loader = result.get("loader") or profile.get("loader") or ""
        loader_version = result.get("loader_version") or ""
        if loader_version:
            loader = loader_version
        if loader:
            profile["loader"] = loader
        if result.get("mc_version"):
            profile["version"] = result["mc_version"]
        profile["type"] = (result.get("loader") or profile.get("type") or "vanilla")
        if profile["type"] in ("", None):
            profile["type"] = "vanilla"
        profile = normalize_profile(profile) or profile
        ensure_profile_folders(profile)
        self.save_options()
        self.refresh_profiles_ui()
        self.select_profile(profile["name"])
        print(f"Profil modpack prêt: {profile}")

    def ask_optional_files(self, pack_name: str, optional_files) -> list:
        """Demande à l'utilisateur quels fichiers optionnels d'un modpack installer.

        Returns the list of selected paths, or None if the user cancelled.
        """
        result = {"value": None}
        top = tk.Toplevel(self)
        top.title(f"Fichiers optionnels — {pack_name}")
        top.configure(bg="#2E3030")
        top.transient(self)
        tk.Label(top, text=f"Le modpack « {pack_name} » contient des fichiers optionnels.",
                 bg="#2E3030", fg="white", font=self.helv12).pack(padx=16, pady=(14, 4))
        tk.Label(top, text="Choisissez ceux à installer (Ctrl+A ne sert à rien ici, c'est une liste).",
                 bg="#2E3030", fg="#9a9a9a").pack(padx=16)
        frame = tk.Frame(top, bg="#2E3030")
        frame.pack(fill="both", expand=True, padx=16, pady=10)
        listbox = tk.Listbox(frame, selectmode="extended", width=70, height=14,
                             bg="#1E2020", fg="white", selectbackground="#30b6a2")
        for entry in optional_files:
            listbox.insert("end", entry["path"])
        listbox.pack(side="left", fill="both", expand=True)
        scroll = tk.Scrollbar(frame, command=listbox.yview)
        scroll.pack(side="right", fill="y")
        listbox.configure(yscrollcommand=scroll.set)

        def validate(all_of_them=False):
            if all_of_them:
                result["value"] = [entry["path"] for entry in optional_files]
            else:
                result["value"] = [listbox.get(i) for i in listbox.curselection()]
            top.destroy()

        buttons = tk.Frame(top, bg="#2E3030")
        buttons.pack(fill="x", padx=16, pady=(0, 14))
        tk.Button(buttons, text="Tout installer", bg="green", fg="black", borderwidth=0,
                  command=lambda: validate(True)).pack(side="left")
        tk.Button(buttons, text="Installer la sélection", bg="#2E3030", fg="white", borderwidth=0,
                  command=validate).pack(side="left", padx=6)
        tk.Button(buttons, text="Ne rien installer d'optionnel", bg="#2E3030", fg="white",
                  borderwidth=0, command=lambda: validate(False)).pack(side="left", padx=6)
        tk.Button(buttons, text="Annuler", bg="#AA0000", fg="white", borderwidth=0,
                  command=lambda: top.destroy()).pack(side="right")
        top.update_idletasks()
        top.grab_set()
        self.wait_window(top)
        return result["value"]

    def update(self):
        super().update()
        # CenteredProgressBar.set() exige un maximum: sans lui, l'appel levait une
        # exception à chaque rafraîchissement de la fenêtre.
        if getattr(self.progressbar, "_max", 0) in (None, 0):
            self.progressbar.set_maximum(100)
        self.progressbar.set(self.progress)

    def handle(self,event):
        if type(event)==DownloadStartEvent:
            self.progressbar.set_maximum(event.size)
            self.max_download_size=event.size
            self.downloaded_size = {}
            self.download_threads_speed = [0]*event.threads_count
            self.progressbar.set(0)

        elif type(event)==DownloadProgressEvent:
            if not event.entry in self.downloaded_size:
                self.downloaded_size[event.entry]=0
            self.downloaded_size[event.entry]=event.size
            self.download_threads_speed[event.thread_id]=event.speed if event.done is not None else 0
            self.progressbar.set(sum(self.downloaded_size.values()))

            self.progressbar._textvariable.set(f"{sum(self.downloaded_size.values())/1048576:.2f}/{self.max_download_size/1048576:.0f} Mo Téléchargés à {sum(self.download_threads_speed)/1048576:.2f} Mo/s")
            #print(event.speed, f"{sum(self.downloaded_size.values())/1048576:.2f}/{self.max_download_size/1048576:.2f} Mo Téléchargés", event.count, event.done, event.thread_id, self.downloaded_size)
        elif type(event)==DownloadCompleteEvent:
            self.progressbar.set(self.max_download_size)
            self.progressbar._textvariable.set(f"Téléchargement terminé.")
        elif type(event)==OptifineStartInstallEvent:
            self.progressbar.set(0)
            self.progressbar._textvariable.set(f"Installation de Optifine...")
        elif type(event)==OptifinePatchEvent:
            self.progressbar.set_maximum(event.total)
            self.progressbar.set(event.done)
        else:
            self.progressbar._textvariable.set(f"Mise en place des fichiers nécessaires...")

    def save_options(self):
        with open(os.path.join(mc_directory,"mcLaunch_profiles.json"),"w") as cf:
            json.dump(self.launcher_conf,cf)
def main():
    app = Myapp()
    try:
        app.mainloop()
    finally:
        # La configuration doit être sauvée même si la fenêtre est fermée brutalement.
        try:
            app.save_options()
            print("Configuration sauvegardée.")
        except Exception as e:  # noqa: BLE001
            print(f"Impossible de sauvegarder la configuration: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
