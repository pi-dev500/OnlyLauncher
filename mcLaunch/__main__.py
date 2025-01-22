requirements=["portablemc","BeautifulSoup4","requests","TkinterWeb","lxml"]


import platform
assert platform.system() in ["Windows","Linux"], "Not supported on your system"
from portablemc.standard import Version, DownloadProgressEvent, StreamRunner
from portablemc.forge import ForgeVersion, _NeoForgeVersion
from portablemc.fabric import FabricVersion
from portablemc.optifine import OptifineVersion, get_compatible_versions as of_version_dict
import json
#import sys

import os
import uuid
from pathlib import Path
#from tkinter import *
from tkinter.ttk import *
from tkinter import ttk, Frame, Canvas, Tk, Button
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
class ProfileShow(Frame):
    def __init__(self,parent,content,app=None):
        super().__init__(parent,pady=10,padx=10)
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
        self.loader_label=Label(self,text=content["loader"])
        self.edit_button=Button(self,image=self.editimage,command=lambda: app.edit_profile(content),relief="flat",padx=10)
        self.delete_button=Button(self,image=self.deleteimage,command=lambda: app.delete_profile(content), relief="flat",padx=10)
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
    def destroyt(self): # destruct the widget only if it's a profileshow
        self.destroy()
        self.icon.destroy()
        self.name_label.destroy()
        self.version_label.destroy()
        self.type_label.destroy()
        self.loader_label.destroy()
        self.edit_button.destroy()
        self.delete_button.destroy()


class ProfileEdit(Frame): # La frame pour créer et éditer des profiles
    def __init__(self,*args,command=None,**kw):
        super().__init__(*args,**kw)
        self.state=None
        self.command=command
        self.official_version_list=get_version_list()
        self.fabric_support=get_fabric_support()
        self.fabric_loaders=get_fabric_loaders()
        self.quilt_support=get_fabric_support("https://meta.quiltmc.org/v3/versions")
        self.quilt_loaders=get_fabric_loaders("https://meta.quiltmc.org/v3/versions")
        self.forge_versions=get_forge_versions()
        self.neoforge_versions=get_neoforge_versions()
        self.optifine_versions=of_version_dict()
        self.version_selection_f=Frame(self) # la frame managée par grid qui contient le formulaire de création.
        #---A partir d'ici, première partie (selection de version)
        self.version_type_l=Label(self.version_selection_f,text="Type de version:")
        self.version_type_l.grid(row=1,sticky="w")
        self.version_type_s=Combobox(self.version_selection_f,values=["Vanilla","Snapshot","Alpha","Beta","Forge","NeoForge","Fabric","Quilt","Optifine"],state="readonly")
        self.version_type_s.set("Vanilla")
        self.version_type_s.grid(row=1,column=1,sticky="ew")
        self.version_type_s.bind("<<ComboboxSelected>>", self.on_type_select)
        self.version_l=Label(self.version_selection_f,text="Version de Minecraft:")
        self.version_l.grid(sticky="w",row=2,column=0)
        self.version_s=Combobox(self.version_selection_f,values=[name for name,settings in self.official_version_list.items() if settings["type"]=="release"],state="readonly")
        self.version_s.set("latest")
        self.version_s.grid(row=2,column=1,sticky="ew",pady=4)
        self.loader_l=Label(self.version_selection_f,text="Version du loader:")
        self.recomendation_loader=Label(self.version_selection_f,text="Il vaut mieux garder la valeur recommandée pour la version du loader sur les versions\nnon-officielles, sauf pour résoudre des problèmes de compatibilité de mods.",justify="left")
        self.recomendation_loader.grid(row=4,columnspan=2,sticky="w")
        self.loader_s=Combobox(self.version_selection_f,state="readonly")
        self.nextbutton=Button(self.version_selection_f,background="green",text="Suivant →",borderwidth=4,activebackground="#00AA00",command=self.on_next)
        self.nextbutton.grid(row=30,column=1,sticky="e")
        #---A partir d'ici, arguments de fix de version
        self.disable_leg_proxy_fix_l=Label(self.version_selection_f,text="Désactiver FIX_LEGACY_PROXY")
        self.disable_leg_proxy_fix_c=Checkbutton(self.version_selection_f)
        #---Options du jeu
        self.profile_name_label=Label(self.version_selection_f,text="Nom du profile:")
        self.profile_name_entry=Entry(self.version_selection_f)
        self.enable_demo_l=Label(self.version_selection_f,text="Mode demo:")
        self.enable_demo_s=SwitchButton(self.version_selection_f,value=False)
        self.enable_multiplayer_l=Label(self.version_selection_f,text="Autoriser multijoueur:")
        self.enable_multiplayer_s=SwitchButton(self.version_selection_f)
        self.enable_chat_l=Label(self.version_selection_f,text="Fonctionnalités de chat:")
        self.enable_chat_s=SwitchButton(self.version_selection_f)
        self.enable_quick_play_l=Label(self.version_selection_f,text="Quick play:")
        self.enable_quick_play_s=SwitchButton(self.version_selection_f,command=self.quick_play_toggle,value=False)
        self.quick_play_type_l=Label(self.version_selection_f,text="Type de Quick Play:")
        self.quick_play_type_s=Combobox(self.version_selection_f,values=["Multijoueur", "Solo"],state="readonly")
        self.quick_play_type_s.set("Solo")
        self.quick_play_type_s.bind("<<ComboboxSelected>>",lambda e: self.quick_play_toggle())
        self.quick_play_mp_l=Label(self.version_selection_f,text="Adresse ipV4 ou dns du serveur:")
        self.quick_play_sp_l=Label(self.version_selection_f,text="Nom du monde:")
        self.quick_play_name_e=Entry(self.version_selection_f)
        self.quick_play_mp_port_l=Label(self.version_selection_f,text="Port:")
        self.quick_play_mp_port_e=Entry(self.version_selection_f)
        # affichage du formulaire
        self.version_selection_f.pack(fill="both",expand=True,padx=50)
        self.version_selection_f.columnconfigure(0,weight=1)
        self.version_selection_f.columnconfigure(1,weight=1)

        self.loader_s.bind("<<ComboboxSelected>>",self.cbbselectionclear)
        self.quick_play_type_s.bind("<<ComboboxSelected>>",self.cbbselectionclear)
    def cbbselectionclear(self,ev=None):
        self.loader_s.selection_clear()
        self.quick_play_type_s.selection_clear()

    def on_type_select(self,e=None):
        self.version_type_s.selection_clear()
        self.loader_s.grid_forget()
        self.loader_l.grid_forget()
        self.version_s.unbind("<<ComboboxSelected>>")
        match self.version_type_s.get():
            case "Vanilla":
                self.version_s.configure(values=[name for name,settings in self.official_version_list.items() if settings["type"]=="release"])
            case "Snapshot":
                self.version_s.configure(values=[name for name,settings in self.official_version_list.items() if settings["type"]=="snapshot"])
            case "Alpha":
                self.version_s.configure(values=[name for name,settings in self.official_version_list.items() if settings["type"]=="old_alpha"])
            case "Beta":
                self.version_s.configure(values=[name for name,settings in self.official_version_list.items() if settings["type"]=="old_beta"])
            case "Fabric":
                allowedversions=[name for name,settings in self.official_version_list.items() if settings["type"]=="release" and name in self.fabric_support]
                self.version_s.configure(values=allowedversions)
                if not self.version_s.get() in allowedversions:
                    self.version_s.set("latest")
                self.loader_s.grid(row=3,column=1,sticky="ew")
                self.loader_l.grid(row=3,column=0,sticky="w")
                self.loader_s.configure(values=["recommended"]+self.fabric_loaders)
                self.loader_s.set("recommended")
            case "Quilt":
                self.version_s.configure(values=[name for name,settings in self.official_version_list.items() if settings["type"]=="release" and name in self.quilt_support])
                self.loader_s.grid(row=3,column=1,sticky="ew")
                self.loader_l.grid(row=3,column=0,sticky="w")
                self.loader_s.configure(values=["recommended"]+self.quilt_loaders)
                self.loader_s.set("recommended")
            case "Forge":
                self.version_s.configure(values=list(self.forge_versions.keys()))
                self.version_s.set("latest")
                self.version_s.bind("<<ComboboxSelected>>", self.on_forgeorof_version_selected)
                self.loader_s.grid(row=3,column=1,sticky="ew")
                self.loader_l.grid(row=3,column=0,sticky="w")
                self.loader_s.configure(values=["recommended"]+self.forge_versions[list(self.forge_versions.keys())[0]])
                self.loader_s.set("recommended")
            case "NeoForge":
                self.version_s.configure(values=self.neoforge_versions)
                self.version_s.set("latest")
            case "Optifine":
                self.version_s.configure(values=list(self.optifine_versions.keys()))
                self.version_s.set("latest")
                self.version_s.bind("<<ComboboxSelected>>", self.on_forgeorof_version_selected)
                self.loader_s.grid(row=3,column=1,sticky="ew")
                self.loader_l.grid(row=3,column=0,sticky="w")
                self.loader_s.configure(values=["recommended"]+[v.edition for v in self.optifine_versions[list(self.optifine_versions.keys())[0]]])
                self.loader_s.set("recommended")
    def on_forgeorof_version_selected(self,event):
        if self.version_type_s.get()=="Forge":
            version=self.version_s.get()
            if version=="latest":
                version=list(self.forge_versions.keys())[0]
            self.loader_s.configure(values=["recomended"]+self.forge_versions[version])
            self.loader_s.set("recomended")
        elif self.version_type_s.get()=="Optifine":
            version=self.version_s.get()
            if version=="latest":
                version=list(self.forge_versions.keys())[0]
            self.loader_s.configure(values=["recomended"]+[v.edition for v in self.optifine_versions[version]])
            self.loader_s.set("recomended")
    def quick_play_toggle(self,val=True):
        if val:
            self.quick_play_type_l.grid(row=5,column=0,sticky="w")
            self.quick_play_type_s.grid(row=5,column=1,sticky="we")
            
            self.quick_play_name_e.grid(row=6,column=1,sticky="ew")
            if self.quick_play_type_s.get()=="Solo":
                self.quick_play_sp_l.grid(row=6,column=0,sticky="w")
                self.quick_play_mp_l.grid_forget()
                self.quick_play_mp_port_l.grid_forget()
                self.quick_play_mp_port_e.grid_forget()
            else:
                self.quick_play_sp_l.grid_forget()
                self.quick_play_mp_l.grid(row=6,column=0,sticky="w")
                self.quick_play_mp_port_l.grid(row=7,column=0,sticky="w")
                self.quick_play_mp_port_e.grid(row=7,column=1,sticky="ew")
        else:
            self.quick_play_mp_l.grid_forget()
            self.quick_play_mp_port_l.grid_forget()
            self.quick_play_mp_port_e.grid_forget()
            self.quick_play_sp_l.grid_forget()
            self.quick_play_type_l.grid_forget()
            self.quick_play_type_s.grid_forget()
            self.quick_play_name_e.grid_forget()

    def on_next(self):
        match self.state:
            case None: # Nouveau profile, vient de selectionner la version voulue
                # effacer la grid
                self.version_type_l.grid_forget()
                self.version_type_s.grid_forget()
                self.version_l.grid_forget()
                self.version_s.grid_forget()
                self.loader_l.grid_forget()
                self.loader_s.grid_forget()
                self.recomendation_loader.grid_forget()
                # afficher les options
                self.profile_name_label.grid(row=0,column=0,sticky="w")
                self.profile_name_entry.grid(row=0,column=1,sticky="ew")
                self.profile_name_entry.delete(0,"end")
                loader_vers=""
                match self.version_type_s.get():
                    case "Quilt":
                        version_name="Quilt "+(self.version_s.get() if not self.version_s.get()=="latest" else self.quilt_support[0])+" "+self.get_latest_loader()
                    case "Fabric":
                        version_name="Fabric "+(self.version_s.get() if not self.version_s.get()=="latest" else self.fabric_support[0])+" "+self.get_latest_loader()
                    case "Forge":
                        version_name="Forge "+(self.version_s.get() if not self.version_s.get()=="latest" else list(self.forge_versions.keys())[0])+" "+self.get_latest_loader()
                    case "Optifine":
                        version_name="Optifine "+(self.version_s.get() if not self.version_s.get()=="latest" else self.getlatest("optifine"))
                        #TODO
                    case "NeoForge":
                        version_name="NeoForge "+(self.version_s.get() if not self.version_s.get()=="latest" else self.neoforge_versions[0])
                    case "Snapshot":
                        version_name="Snapshot "+(self.version_s.get() if not self.version_s.get()=="latest" else [v for v in self.official_version_list.keys() if self.official_version_list[v]["type"]=="snapshot"][0])
                    case "Alpha":
                        version_name="Alpha "+(self.version_s.get() if not self.version_s.get()=="latest" else [v for v in self.official_version_list.keys() if self.official_version_list[v]["type"]=="old_alpha"][0])
                    case "Beta":
                        version_name="Beta "+(self.version_s.get() if not self.version_s.get()=="latest" else [v for v in self.official_version_list.keys() if self.official_version_list[v]["type"]=="old_beta"][0])
                    case "Vanilla":
                        version_name="Minecraft "+(self.version_s.get() if not self.version_s.get()=="latest" else [v for v in self.official_version_list.keys() if self.official_version_list[v]["type"]=="release"][0])
                    case _: # you'v got troll
                        version_name="Troll "+(self.version_s.get() if not self.version_s.get()=="latest" else [v for v in self.official_version_list.keys() if self.official_version_list[v]["type"]=="release"][0])

                self.profile_name_entry.insert(0,version_name+" "+loader_vers)
                self.enable_demo_l.grid(row=1,column=0,sticky="w")
                self.enable_demo_s.grid(row=1,column=1,sticky="e",pady=6)
                self.enable_multiplayer_l.grid(row=2,column=0,sticky="w")
                self.enable_multiplayer_s.grid(row=2,column=1,sticky="e",pady=6)
                self.enable_chat_l.grid(row=3,column=0,sticky="w")
                self.enable_chat_s.grid(row=3,column=1,sticky="e",pady=6)
                self.enable_quick_play_l.grid(row=4,column=0,sticky="w")
                self.enable_quick_play_s.grid(row=4,column=1,sticky="e",pady=6)
                self.nextbutton.configure(text="Sauvegarder")
                self.state="save"
            case "save":
                #self.pack_forget()
                #self.grid_forget()
                result={}
                result["name"]=self.profile_name_entry.get()
                result["type"]=self.version_type_s.get().lower()
                result["version"]=self.version_s.get() if not self.version_s.get()=="latest" else self.getlatest(result["type"])
                result["loader"]=self.loader_s.get()
                if result["loader"]=="recommended":
                    result["loader"]=self.get_latest_loader()
                result["enable_demo"]=self.enable_demo_s.get()
                result["enable_multiplayer"]=self.enable_multiplayer_s.get()
                result["enable_chat"]=self.enable_chat_s.get()
                result["enable_quick_play"]=self.enable_quick_play_s.get()
                result["quick_play"]={"name":self.quick_play_name_e.get()} if self.quick_play_type_s.get()=="Solo" else {"host":self.quick_play_name_e.get(),"port":int(self.quick_play_mp_port_e.get())}
                #self.launcher_conf["profiles"][self.profile_name_entry.get()]=result
                if self.save_profile(result):
                    self.destroy()
                else:
                    self.profile_name_label.configure(fg="red")
    def getlatest(self,type):
        match type:
            case "vanilla":
                return [v for v in self.official_version_list.keys() if self.official_version_list[v]["type"]=="release"][0]
            case "snapshot":
                return [v for v in self.official_version_list.keys() if self.official_version_list[v]["type"]=="snapshot"][0]
            case "alpha":
                return [v for v in self.official_version_list.keys() if self.official_version_list[v]["type"]=="old_alpha"][0]
            case "beta":
                return [v for v in self.official_version_list.keys() if self.official_version_list[v]["type"]=="old_beta"][0]
            case "forge":
                return [str(v) for v in self.forge_versions.keys()][0]
            case "neoforge":
                return [str(v) for v in self.neoforge_versions][0]
            case "fabric":
                return self.fabric_support[0]
            case "quilt":
                return self.quilt_support[0]
            case "optifine":
                return list(self.optifine_versions.keys())[0]
    def get_latest_loader(self):
        sel_loader=self.loader_s.get()
        mc_ver=self.version_s.get()
        match self.version_type_s.get():
            case "Optifine":
                if mc_ver=="latest":
                    mc_ver=list(self.optifine_versions.keys())[0]
                return self.optifine_versions[mc_ver][0].edition
            case "Forge":
                if mc_ver=="latest":
                    mc_ver=list(self.forge_versions.keys())[0]
                return self.forge_versions[mc_ver][0]
            case "NeoForge":
                if mc_ver=="latest":
                    mc_ver=list(self.neoforge_versions.keys())[0]
                return self.neoforge_versions[mc_ver][0]
            case "Fabric":
                return self.fabric_loaders[0]
            case "Quilt":
                return self.quilt_loaders[0]
            case _:
                return None
    def save_profile(self,result):
        if self.command is not None:
            return self.command(result)
        else:
            return False
class Myapp(Tk):
    def __init__(self):
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
        self.geometry("950x600")
        self.minsize(950,600)
        self.title("Minecraft Launcher")
        self.helv18 = font.Font(family='Helvetica', size=18, weight='bold')
        self.helv12 = font.Font(family='Helvetica', size=12, weight='bold')
        # Création d'un style personnalisé
        style = ttk.Style()
        style.theme_use('default')  # Utilisation d'un thème agréable avec les personnalisations
        style.map('TCombobox', fieldbackground=[('readonly', '#2E3030')])
        style.map('TCombobox', background=[('readonly', '#2E3030')])
        style.map('TCombobox', selectbackground=[('readonly', '#2E3030')])
        # Modification du style de la Combobox
        style.configure(
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
        style.configure(
            "TScrollbar",
            gripcount=0,             # Supprime les grips (si présents)
            relief="flat",           # Style plat
            borderwidth=0,           # Pas de bordures
            troughcolor="white",     # Couleur de la zone de fond
            background="#c0c0c0",    # Couleur du curseur
            arrowcolor="#666666"     # Couleur des flèches
            )
        style.configure('TLabel', background="#2e3030", foreground="white",highlightbackground = "#1E2020",highlightcolor= "#1E2020")
        style.map('TScrollbar', background=[('active', '#a0a0a0')])
        # Vertical left frame containing the buttons

        self.tabsf=Frame(self, bg="#1E2020",width=400)
        self.tabsf.pack_propagate(False)
        self.tabsf.pack(side="left",fill="both")
        self.current_tab="news"
        # Tabs
        self.tabs_news=Button(self.tabsf,text="Actualités",command=lambda t="news": self.show_current_tab(t))
        self.tabs_news.pack(fill="x",side="top")
        
        self.tabs_profiles=Button(self.tabsf,text="Profiles",command=lambda t="profiles": self.show_current_tab(t))
        self.tabs_profiles.pack(fill="x",side="top")

        self.tabs_mods=Button(self.tabsf,text="Mods&Modpacks",command=lambda t="mods": self.show_current_tab(t))
        self.tabs_mods.pack(fill="x",side="top")
        
        self.tabs_options=Button(self.tabsf,text="Options",command=lambda t="options": self.show_current_tab(t))
        self.tabs_options.pack(fill="x",side="top")

        self.tabsf.configure(width=200)
        self.startbutton=Button(self.tabsf,text="Lancer le jeu",command=self.start_mc,fg="black",bg="green",borderwidth=5,font=self.helv12,height=1,width=10,activebackground="#009900")
        self.startbutton["state"]="disabled"
        # Selection du profile
        self.official_version_list=get_version_list()
        self.profileselect=Combobox(self.tabsf,values=[p["name"] for p in self.launcher_conf["profiles"]]+["Nouveau profile..."]+[name for name,settings in self.official_version_list.items() if settings["type"]=="release"],state="readonly")
        self.profileselect.bind("<<ComboboxSelected>>", self.on_profile_selection)
        self.profileselect.pack(side="bottom",fill="x")
        self.startbutton.pack(side="bottom",padx=10,pady=10)
        self.profileselect.set("Selectionner un profil...")
        # Barre de statut du bas affichée lors du téléchargement
        print(f"Phase 2 finished after {(time_ns()-tbegin)/1000000} milliseconds")
        # Contenu des onglets
        self.mcnews=TkMcNews(self)
        self.mcnews.pack(side="right",fill="both")
        self.profiles_f=ScrollableFrame(self)
        #self.newprofile_f=Frame(self.profiles_f.scrollable_frame)
        self.addprofile_b=Button(self.profiles_f.scrollable_frame,text="Nouveau profile...",fg="black",bg="green",borderwidth=10,font=self.helv18,height=2,width=25,activebackground="#009900",command=self.create_new_profile)
        self.addprofile_b.pack()
        #self.newprofile_f.pack(fill="both",side="top")
        #self.profile_f_l=Frame(self.profiles_f)
        for p in self.launcher_conf["profiles"]:
            ProfileShow(self.profiles_f.scrollable_frame,p,self).pack(fill="x")
        #self.profile_f_l.pack(fill="both",expand=True)
        #self.profile_e=ProfileEdit(self.newprofile_f,command=self.validate_profile)
        #self.profile_e.pack(fill="both")
        self.optstab=SettingsFrame(self,self.launcher_conf)
        # affichage
        self.show_current_tab()
        self.tabsf.configure(width=300)
        startupdelta=(time_ns()-tbegin)/1000000
        print(f"Startup took {startupdelta} milliseconds")

    def start_mc(self):
        if self.profile is not None:
            self.withdraw()
            if type(self.profile)==str:

                env = Version(self.profile)
                env.auth_session=self.optstab.get_auth()
                env=env.install(watcher=self)
                #env.run()

            elif type(self.profile)==dict:
                match self.profile["type"]:
                    case "vanilla" | "snapshot" | "alpha" | "beta":

                        env=Version(self.profile["version"])
                    case "forge":
                        vname = self.profile["version"]
                        if not self.profile["loader"] == "recommended":
                            vname = vname + "-" + self.profile["loader"]
                        env=ForgeVersion(vname)
                    case "fabric":
                        args = [self.profile["version"]]
                        vname = self.profile["version"]
                        if not self.profile["loader"] == "recommended":
                            args = [vname, self.profile["loader"]]
                        env=FabricVersion.with_fabric(*args)
                    case "quilt":
                        args= [self.profile["version"]]
                        vname = self.profile["version"]
                        if not self.profile["loader"] == "recommended":
                            args= [vname,self.profile["loader"]]
                        env=FabricVersion.with_quilt(*args)
                    case "optifine":
                        args={"version":self.profile["version"] + ":" + self.profile["loader"]}
                        env=OptifineVersion(**args)
                    case "neoforge":
                        vname = self.profile["version"]
                        env=_NeoForgeVersion(vname)
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
            env.run(runner=StreamRunner())
            self.deiconify()
    def show_current_tab(self,selection=None):
        
        if selection in ["news","profiles","mods","options"]: self.current_tab=selection
        ts=(self.tabs_news,self.tabs_profiles,self.tabs_mods,self.tabs_options)
        for t in ts: # remet les onglets dans leur état original
            t["state"]="normal"
            t['font']=self.helv18
            t.configure(background="#1E2020",highlightbackground = "#1E2020",highlightcolor= "#1E2020", foreground="green",relief="flat",width=15,height=2,activebackground="#2E3030",activeforeground="green",borderwidth=0)
        tab_contents=[self.mcnews,self.profiles_f,self.optstab]
        for tc in tab_contents:
            tc.pack_forget()
        match self.current_tab:
            case "news":
                self.tabs_news["state"]="disabled"
                self.tabs_news.configure(background="green", disabledforeground="white",relief="flat",width=15,height=2)
                self.mcnews.pack(side="left",fill="both",expand=True) # affiche le contenu
            case "profiles":
                self.tabs_profiles["state"]="disabled"
                self.tabs_profiles.configure(background="green", disabledforeground="white",relief="flat",width=15,height=2)
                self.profiles_f.pack(side="left",fill="both",expand=True)
            case "mods":
                self.tabs_mods["state"]="disabled"
                self.tabs_mods.configure(background="green", disabledforeground="white",relief="flat",width=15,height=2)
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
                    return
            if selection in self.official_version_list:
                self.profile=selection
                self.startbutton["state"]="normal"
            else:
                self.message("Error","Impossible de trouver le profile spécifié. Quelque chose s'est mal passé dans le lanceur.")
    def message(self,msgt,content):
        print(f"{msgt}: {content}")
    def create_new_profile(self):
        self.profile_e = ProfileEdit(self.profiles_f.scrollable_frame, command=self.validate_profile)
        self.profile_e.pack(fill="both")
        self.update_profile_list()
        self.addprofile_b.pack_forget()
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
            if hasattr(c, 'destroyt') and callable(c.destroyt):
                c.destroyt()
        for p in self.launcher_conf["profiles"]:
            ProfileShow(self.profiles_f.scrollable_frame, p,self).pack(fill="x")
    def validate_profile(self,content):
        list_names=[p["name"] for p in self.launcher_conf["profiles"]]
        if not content["name"] in list_names:
            self.launcher_conf["profiles"].append(content)

            print("New profile created: ",content)
            self.profile_e.destroy()
            self.addprofile_b.pack()
            self.update_profile_list()
            return True
        else:
            return False
    def delete_profile(self,content):
        name=content["name"]
        if name in [p["name"] for p in self.launcher_conf["profiles"]]:
            del self.launcher_conf["profiles"][self.launcher_conf["profiles"].index(content)]
            self.update_profile_list()

    def edit_profile(self,content):
        pass

    def handle(self,event):
        if type(event)==DownloadProgressEvent:
            print(event.speed, event.size, event.count)
        else:
            print(event)

    def save_options(self):
        with open(os.path.join(mc_directory,"mcLaunch_profiles.json"),"w") as cf:
            json.dump(self.launcher_conf,cf)
if __name__ == "__main__":
    app = Myapp()
    #print(get_version_list())
    app.mainloop()
    app.save_options()
