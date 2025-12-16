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

from cache_system import *
from time import time_ns
tbegin=time_ns()
print("Python part starting... Finished imports...")
refresh_cache() # prend un peu de temps on startup, mais évite de tout retélécharger plusieurs fois
print(f"Phase 1 (cache creation) finished after {(time_ns()-tbegin)/1000000} milliseconds")
# de plus, le launcher a accès à ces fichiers sans Internet
#plusieurs definitions de variables globales auront lieu ici.
#TODO: add a loading screen that disapears when the window has charged
class TaskProgressBar(Canvas):
    def __init__(self,parent):
        super().__init__(parent)
        self.rectangle=self.create_rectangle(0,0,0,self.winfo_height(),fill="green")
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
        """Get versions filtered by type - centralized to avoid code duplication."""
        config = self.VERSION_CONFIGS.get(version_type)

        if not config:
            return []

        # Handle special types (Forge, NeoForge, Optifine)
        if config["key"] is None:
            if version_type == "Forge":
                return list(self.forge_versions.keys())
            elif version_type == "NeoForge":
                return list(self.neoforge_versions)
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
            if version_type in ("Forge", "Optifine"):
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
            "name": self.profile_name_entry.get(),
            "type": self.version_type_s.get().lower(),
            "version": self._resolve_version(),
            "loader": self._resolve_loader(),
            "isolated": self.isolated_c.get(),
            "enable_demo": self.enable_demo_s.get(),
            "enable_multiplayer": self.enable_multiplayer_s.get(),
            "enable_chat": self.enable_chat_s.get(),
            "enable_quick_play": self.enable_quick_play_s.get(),
            "quick_play": self._get_quick_play_config(),
        }

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
            return self.neoforge_versions[0] if self.neoforge_versions else ""

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
    def __init__(self):
        self.max_download_size = None
        self.downloaded_size = 0
        self.download_threads_speed = []
        self.profile=""
        super().__init__()
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
        if "selected_profile" in self.launcher_conf.keys():
            self.profileselect.set(self.launcher_conf["selected_profile"]["name"])
            self.startbutton["state"]="normal"
            self.profile=self.launcher_conf["selected_profile"]
        self.startbutton.pack(side="bottom",padx=10,pady=10)
        
        # Barre de statut du bas affichée lors du téléchargement
        print(f"Phase 2 finished after {(time_ns()-tbegin)/1000000} milliseconds")
        # Contenu des onglets
        self.mcnews=TkMcNews(self)
        self.mcnews.pack(side="right",fill="both")
        self.modsframe=Frame(self)
        self.mod_search_entry=Entry(self.modsframe, width=20)
        self.mod_search_entry.pack()

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
        self.optstab=SettingsFrame(self,self.launcher_conf)
        # affichage
        self.show_current_tab()
        self.tabsf.configure(width=300)
        startupdelta=(time_ns()-tbegin)/1000000
        print(f"Startup took {startupdelta} milliseconds")
        self.bind("<Configure>",self.on_resize)

    def on_resize(self, event):
        if hasattr(event,"width"):
            self.progressbar.configure(width=event.width,height=15)

    def start_mc(self, in_thread=False):
        if not in_thread:
            self.active_start_thread=threading.Thread(target=self.start_mc, args=(True,))
            self.progressbar.place(anchor="sw",x=0,rely=1,relwidth=1,height=25)
            self.progressbar.set(0)
            Misc.lift(self.progressbar)
            self.progressbar.set_maximum(100)
            self.progressmessage.set("Lancement du jeu...")
            self.active_start_thread.start()
            return
        if self.profile is not None:
            #self.withdraw()
            if type(self.profile)==str:

                env = Version(self.profile)
                env.auth_session=self.optstab.get_auth()
                env=env.install(watcher=self)
                #env.run()

            elif type(self.profile)==dict:
                ctx = Context()
                if "isolated" in self.profile.keys() and self.profile["isolated"] is True:
                    ctx = Context(work_dir = Path(mc_directory) / "versions" / self.profile["name"]) # le dossier de version est créé automatiquement
                match self.profile["type"]:
                    case "vanilla" | "snapshot" | "alpha" | "beta":
                        env=Version(self.profile["version"], context=ctx)
                    case "forge":
                        vname = self.profile["version"]
                        if not self.profile["loader"] == "recommended":
                            vname = vname + "-" + self.profile["loader"]
                        env=ForgeVersion(vname, context=ctx)
                    case "fabric":
                        args = [self.profile["version"]]
                        vname = self.profile["version"]
                        if not self.profile["loader"] == "recommended":
                            args = [vname, self.profile["loader"]]
                        env=FabricVersion.with_fabric(*args, context=ctx)
                    case "quilt":
                        args= [self.profile["version"]]
                        vname = self.profile["version"]
                        if not self.profile["loader"] == "recommended":
                            args= [vname,self.profile["loader"]]
                        env=FabricVersion.with_quilt(*args, context=ctx)
                    case "optifine":
                        args={"version":self.profile["version"] + ":" + self.profile["loader"]}
                        env=OptifineVersion(**args, context=ctx)
                    case "neoforge":
                        vname = self.profile["version"]
                        env=_NeoForgeVersion(vname, context=ctx)
                
                env.auth_session=self.optstab.get_auth()
                env.resolution=tuple([int(v) for v in self.optstab.get_resolution().split("x")])
                if self.profile["enable_multiplayer"] is False:
                    env.disable_multiplayer=True
                if self.profile["enable_chat"] is False:
                    env.disable_chat=True
                if self.profile["enable_demo"] is True:
                    env.demo=True
                if self.profile["enable_quick_play"] is True:
                    if "port" in self.profile["quick_play"].keys():
                        env.set_quick_play_multiplayer(host=self.profile["quick_play"]["host"],port=int(self.profile["quick_play"]["port"]))
                    else:
                        env.set_quick_play_singleplayer(level_name=self.profile["quick_play"]["name"])
                env=env.install(watcher=self)
            env.jvm_args += self.optstab.get_jvm_args()
            self.withdraw()
            self.progressbar.place_forget()
            env.run(runner=StreamRunner())
            self.deiconify()
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

    def on_profile_selection(self,event):
        self.profileselect.selection_clear()
        selection=self.profileselect.get()
        self.startbutton["state"]="disabled"
        if selection == "Nouveau profile...":
            self.profileselect.set("Selectionner un profile...")
            self.show_current_tab("profiles")
            self.create_new_profile()
            self.profile=None
        else:
            for p in self.launcher_conf["profiles"]:
                if p["name"]==selection:
                    self.profile=p
                    self.startbutton["state"]="normal"
                    self.launcher_conf["selected_profile"]=p
                    return
            if selection in self.official_version_list:
                self.profile=selection
                self.startbutton["state"]="normal"
            else:
                self.message("Error","Impossible de trouver le profile spécifié. Quelque chose s'est mal passé dans le lanceur.")
    def message(self,msgt,content):
        print(f"{msgt}: {content}")
    def create_new_profile(self):
        self.profile_e.pack(fill="both")
        #self.update_profile_list()
        self.addprofile_b.pack_forget()
        self.profiles_f.scroll_to_bottom()
        self.profileselect.configure(
            values=[p["name"] for p in self.launcher_conf["profiles"]] + [name for
                                                                                                   name, settings in
                                                                                                   self.official_version_list.items()
                                                                                                   if settings[
                                                                                                       "type"] == "release"]
        )
    def update_profile_list(self):
        self.profileselect.configure(
            values=[p["name"] for p in self.launcher_conf["profiles"]] +
                   ["Nouveau profile..."] + [name for
                                           name, settings in
                                           self.official_version_list.items()
                                           if settings[
                                               "type"] == "release"]
        )
        for c in self.profiles_f.scrollable_frame.winfo_children():
            if isinstance(c, ProfileShow):
                c.destroy()
        for p in self.launcher_conf["profiles"]:
            ProfileShow(self.profiles_f.scrollable_frame, p,self).pack(fill="x")
    def validate_profile(self,content):
        if content==quit:
            self.profile_e.destroy()
            self.profile_e = ProfileEdit(self.profiles_f.scrollable_frame, command=self.validate_profile)
            self.addprofile_b.pack()
            #self.update_profile_list()
            return True
        list_names=[p["name"] for p in self.launcher_conf["profiles"]]
        if not content["name"] in list_names:
            self.launcher_conf["profiles"].append(content)
            ProfileShow(self.profiles_f.scrollable_frame, content,self).pack(fill="x")
            print("New profile created: ",content)
            self.profile_e.destroy()
            self.profile_e = ProfileEdit(self.profiles_f.scrollable_frame, command=self.validate_profile)
            self.addprofile_b.pack()
            self.profileselect.configure(
            values=[p["name"] for p in self.launcher_conf["profiles"]] +
                   ["Nouveau profile..."] + [name for
                                           name, settings in
                                           self.official_version_list.items()
                                           if settings[
                                               "type"] == "release"]
            )
            #self.update_profile_list()
            return True
        else:
            return False
    def delete_profile(self,content):
        name=content["name"]
        if name in [p["name"] for p in self.launcher_conf["profiles"]]:
            del self.launcher_conf["profiles"][self.launcher_conf["profiles"].index(content)]
            self.profileselect.configure(
            values=[p["name"] for p in self.launcher_conf["profiles"]] +
                   ["Nouveau profile..."] + [name for
                                           name, settings in
                                           self.official_version_list.items()
                                           if settings[
                                               "type"] == "release"]
            )
            #self.update_profile_list()

    def edit_profile(self,content):
        self.profile_e.set_content(content)
        self.delete_profile(content)
        self.profile_e.pack(fill="both")
        #self.update_profile_list()
        self.addprofile_b.pack_forget()
        self.profiles_f.scroll_to_bottom()

    def update(self):
        super().update()
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
if __name__ == "__main__":
    app = Myapp()
    #print(get_version_list())
    app.mainloop()
    app.save_options()
