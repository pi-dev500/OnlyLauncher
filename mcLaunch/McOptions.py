#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Nov 30 12:27:39 2024

@author: pi-dev500
"""

from tkinter import *
from tkinter import PhotoImage
from PIL import ImageTk, Image
from tkinter.ttk import Combobox
from portablemc.auth import MicrosoftAuthSession, OfflineAuthSession
#from portablemc_login import PortableMCLauncher as MSA
import urllib.parse
from ctkwidgets import *
from uuid import uuid4
import os
import sys
import psutil
from threading import Thread
import subprocess
import json

# Get the current memory usage
mem = psutil.virtual_memory()
total_memory = mem.total / (1024 ** 2)  # in MB
selfdir=os.path.dirname(os.path.realpath(__file__))
DIRECTORY = os.path.dirname(os.path.realpath(__file__))

def get_portblemc_auth():
    jsonauth = subprocess.check_output([sys.executable, os.path.join(DIRECTORY, "portablemc_login.py")])
    return json.loads(jsonauth)
    
class AccountDisplay(Frame):
    def __init__(self,parent,account,selectcommand=lambda: None,deletecommand=lambda c: None,state="normal"):
        self.background = "green" if state == "selected" else "#2E3030"
        self.activebackground = "#00A000" if state == "selected" else "#3E4050"
        super().__init__(parent,bg=self.background)
        self.deletecommand=deletecommand
        self.account=account

        self.type="offline" if "pseudo" in account.keys() else "microsoft"
        if self.type == "offline":
            self.type_logo_img=geticon("snapshot",(32,32))
            self.type_logo=Label(self,image=self.type_logo_img,bg=self.background)
            self.name=Label(self,text=account["pseudo"],bg=self.background)
        else:
            self.type_logo_img=geticon("minecrosoft",(32,32))
            self.type_logo=Label(self,image=self.type_logo_img,bg=self.background)
            self.name=Label(self,text=account["profile_name"],bg=self.background)
        self.type_logo.grid(row=0,column=0)
        self.name.grid(row=0,column=1)
        self.delete_image=geticon("delete",(32,32))
        self.delete_button=Button(self,image=self.delete_image,command=self.deletecommand,relief="flat",bg=self.background,activebackground=self.activebackground,borderwidth=0,highlightcolor="#2E3030",highlightbackground="#2E3030")
        self.delete_button.grid(row=0,column=2)
        self.columnconfigure(1,weight=1)
        self.bind("<Button-1>",lambda e: selectcommand())
        self.name.bind("<Button-1>",lambda e: selectcommand())

    def __setitem__(self, key, value):
        if key=="state":
            self.background = "green" if value == "selected" else "#2E3030"
            self.activebackground = "#00A000" if value == "selected" else "#3E4050"
            self.configure(bg=self.background)
            self.type_logo.configure(bg=self.background)
            self.name.configure(bg=self.background)
            self.delete_button.configure(bg=self.background,activebackground=self.activebackground)


class MemorySelect(Frame):
    def __init__(self, parent, *args,initial_value=1024,command=None, **kw):
        super().__init__(parent, *args, **kw)
        self.memory_var = tk.StringVar(value=f"{initial_value}M")
        self.command = command
        style = ttk.Style()
        style.configure("Custom.Horizontal.TScale", troughcolor="#2E3030", background="#2E3030",
                        sliderthickness=15, sliderlength=10, gripcount=0)
        max_mem=(total_memory/3)*2
        cursor_max=round(max_mem/256)
        self.memory_slider = ttk.Scale(self, from_=1, to=cursor_max, orient="horizontal",
                                       style="Custom.Horizontal.TScale",
                                       command=self.on_slider_change)
        self.memory_slider.set(int(initial_value/256))
        self.memory_slider.grid(sticky="ew")

        self.memory_label = Label(self, textvariable=self.memory_var, bg="#2E3030", fg="white")
        self.memory_label.grid(sticky="ew")
        self.columnconfigure(0, weight=1)

    def on_slider_change(self, value):
        self.memory_var.set(f"{int(float(value))*256}M")
        if self.command is not None:
            self.command()

    def get(self):
        return int(float(self.memory_slider.get()))*256


class ResolutionSelect(Frame):
    def __init__(self,parent,*args,initial_value="800x600",command=None,**kw):
        """
        Constructeur de la frame de s lection de résolution.

        Parameters
        ----------
        parent : tkinter.widget
            Le widget parent de la frame.
        initial_value : str, optional
            La valeur initiale de la résolution. Par défaut, "800x600". La valeur
            est décomposé en deux nombres séparés par un "x". Les valeurs
            sont ensuite stockées dans des Entry pour pouvoir tre modifiées.
        *args :
            Argument(s) supplémentaire(s) passé au constructeur de la classe
            parente.
        **kw :
            Argument(s) supplémentaire(s) passé au constructeur de la classe
            parente.
        """
        super().__init__(parent,*args,**kw)
        vcmd = (self.register(self.callback))
        w,h=initial_value.split("x")
        self.command=command
        self.widthstr=StringVar()
        self.heightstr=StringVar()
        self.widthstr.set(w)
        self.heightstr.set(h)
        self.widthe=Entry(self, validate='all', validatecommand=(vcmd, '%P'), textvariable=self.widthstr)
        self.widthe.grid(sticky="ew")
        self.xlabel=Label(self,text="x")
        self.xlabel.grid(row=0,column=1)
        self.heighte=Entry(self, validate='all', validatecommand=(vcmd, '%P'), textvariable=self.heightstr)
        self.heighte.grid(row=0,column=2,sticky="ew")
        self.widthstr.trace("w", lambda _,__,___: self.command() if self.command is not None else None)
        self.heightstr.trace("w", lambda _,__,___: self.command() if self.command is not None else None)
        self.columnconfigure(0,weight=1)
        self.columnconfigure(2,weight=1)

    def callback(self, P):
        if str.isdigit(P) or P == "":
            return True
        else:
            return False

    def get(self):
        return f"{self.widthe.get()}x{self.heighte.get()}"


class SettingsFrame(Frame):
    def __init__(self,parent,opts):

        """
        Constructeur de la classe SettingsFrame.

        Parameters
        ----------
        parent : tkinter.widget
            Le widget parent de la frame.
        opts : dict
            Un dictionnaire contenant les options du launcher. Les clés sont
            "accounts", "profiles" et "onlineaccount". Les valeurs associées sont
            un dictionnaire pour "accounts", un autre dictionnaire pour "profiles"
            et une chaîne de caractères pour "onlineaccount".

        Notes
        -----
        La frame est divisée en deux onglets : "Jeu" et "Comptes". L'onglet "Jeu"
        contient un sélecteur de résolution pour le lancement du jeu, tandis que
        l'onglet "Comptes" contient un bouton pour ajouter un compte, un sélecteur
        de type de compte (offline ou Microsoft) et un champ de saisie pour le
        pseudo du compte. Lorsque le bouton "Valider" est cliqué, le compte est
        ajouté aux options du launcher.
        """
        super().__init__(parent)

        self.opts=opts
        if not "sel_account" in self.opts.keys():
            self.opts["sel_account"] = "Steve"
        self.saccounts=dict()
        self.tabsf=Frame(self)
        self.tab_accounts=Button(self.tabsf,text="Comptes",relief=FLAT,borderwidth=0,background="#2E3030",foreground="white",activebackground="#3E4040",activeforeground="white",disabledforeground="white",command=lambda: self.tab_select("account"),highlightbackground = "#1E2020",highlightcolor= "#1E2020")
        self.tab_accounts.grid(sticky="nsew")
        self.tab_game=Button(self.tabsf,text="Jeu",relief=FLAT,borderwidth=0,background="#3E4040",foreground="white",activebackground="#3E4040",activeforeground="white",disabledforeground="white",command=lambda: self.tab_select("game"),highlightbackground = "#1E2020",highlightcolor= "#1E2020")
        self.tab_game["state"]="disabled"
        self.tab_game.grid(row=0,column=1,sticky="nsew")
        self.tabsf.pack(fill="x")
        self.tabsf.columnconfigure(0,weight=1)
        self.tabsf.columnconfigure(1,weight=1)
        #Game tab
        self.tab_game_c=Frame(self)
        self.resolution_l=Label(self.tab_game_c,text="Résolution du jeu au lancement:")
        self.resolution_l.grid(sticky="w")
        self.resolution_s=ResolutionSelect(self.tab_game_c,initial_value=self.opts["resolution"] if "resolution" in self.opts.keys() else "800x600")
        self.resolution_s.grid(row=0,column=1,sticky="ew")
        self.memory_l=Label(self.tab_game_c,text="Mémoire du jeu disponible\n(valeur recommandée: entre 1024 et 8192):")
        self.memory_l.grid(row=1,sticky="w")
        self.memory_s=MemorySelect(self.tab_game_c,initial_value=self.opts["memory"] if "memory" in self.opts.keys() else 1024)
        self.memory_s.grid(row=1,column=1,sticky="ew")
        self.tab_game_c.columnconfigure(0,weight=2)
        self.tab_game_c.columnconfigure(1,weight=1)
        self.tab_game_c.pack(fill="both")
        self.memory_s.command=self.updatejson
        self.resolution_s.command=self.updatejson
        #Accounts tab
        self.tab_account_c=Frame(self)
        image_add=ImageTk.PhotoImage(Image.open(os.path.join(selfdir,"images","plus.png")).resize((30,30)))
        self.add_account_b=Label(self.tab_account_c,image=image_add )# ,relief="flat",command=self.add_account)
        self.add_account_b.image=image_add
        self.add_account_b.bind("<Button-1>",lambda e: self.add_account())
        #self.add_account_b=Button(self.tab_account_c,text="Ajouter un compte",command=self.add_account)
        self.new_account_frame=Frame(self,width=self.winfo_width(),height=self.winfo_height())
        bg=ImageTk.PhotoImage(Image.open(os.path.join(selfdir,"images","mcbg.jpg")))
        self.new_account_bg=Label(self.new_account_frame,image=bg)
        self.new_account_bg.image=bg
        self.new_account_bg.place(x=-5,y=-5)
        close_img=ImageTk.PhotoImage(Image.open(os.path.join(selfdir,"images","close.png")).resize((30,30)))
        self.new_account_cbtn=Label(self.new_account_frame,image=close_img)
        self.new_account_cbtn.image=close_img
        self.new_account_cbtn.bind("<Button-1>",lambda e: self.close_new_account_frame())
        self.new_account_cbtn.place(relx=1,y=0,anchor="ne")
        self.intra_new_account=Frame(self.new_account_frame,width=400, height=400,bg="#2E3030")
        #self.intra_new_account.pack_propagate(False)
        self.intra_new_account.grid_propagate(False)
        self.intra_new_account.pack(expand=True)
        self.new_account_titleim=ImageTk.PhotoImage(Image.open(os.path.join(selfdir,"images","Logintitle.png")).resize((400,90)))
        self.new_account_l=Label(self.intra_new_account,image=self.new_account_titleim,background="#2E3030")
        self.new_account_l.image=self.new_account_titleim
        self.new_account_l.grid(columnspan=2)
        self.new_account_type_l=Label(self.intra_new_account,text="Type de compte:",background="#2E3030",foreground="white")
        self.new_account_type_l.grid(sticky="w",pady=5)
        self.new_account_type=Combobox(self.intra_new_account,values=["offline","Microsoft"],state="readonly")
        self.new_account_type.bind("<<ComboboxSelected>>",self.set_nacctype)
        self.new_account_type.set("offline")
        self.new_account_type.grid(row=1,column=1,sticky="we",padx=5)
        self.pseudo_l=Label(self.intra_new_account,text="Pseudo:",background="#2E3030",foreground="white")
        self.pseudo_l.grid(sticky="w",pady=5)
        self.offlineacc_pseudo=Entry(self.intra_new_account)
        self.offlineacc_pseudo.bind("<Return>",lambda e :self.validate_new_account())
        self.offlineacc_pseudo.grid(row=2,column=1,sticky="we",padx=5)
        self.intra_new_account.columnconfigure(0,weight=1)
        self.intra_new_account.columnconfigure(1,weight=1)
        self.validate_b=Button(self.intra_new_account,text="Valider",background="green",activebackground="#00AA00",command=self.validate_new_account,highlightbackground = "#1E2020",highlightcolor= "#1E2020")
        self.intra_new_account.rowconfigure(3,weight=1)
        self.validate_b.grid(row=3,column=1,sticky="se", padx=10, pady=10)

        Label(self.tab_account_c, text="Comptes:").grid(row=0,column=0,sticky="w")
        self.add_account_b.grid(row=0,column=1,sticky="e")
        self.list_accounts_f=ScrollableFrame(self.tab_account_c)
        self.list_accounts_f.grid(row=1,column=0,columnspan=2, rowspan=2,sticky="nsew")
        self.tab_account_c.columnconfigure(0,weight=1)
        self.tab_account_c.columnconfigure(1,weight=1)
        self.tab_account_c.rowconfigure(1,weight=2)
        self.show_accounts_list()

    def add_account(self):
        self.tab_account_c.pack_forget()
        self.tabsf.pack_forget()
        self.new_account_frame.pack(fill="both",expand=True)

    def validate_new_account(self):
        if self.new_account_type.get() == "offline":
            pseudo=self.offlineacc_pseudo.get()

            if pseudo=="":
                return
            if not pseudo in self.opts["accounts"].keys():
                self.opts["accounts"][pseudo] = {
                    "pseudo": pseudo,
                    "uuid": str(uuid4())
                }
                self.saccounts[pseudo]=AccountDisplay(self.list_accounts_f.scrollable_frame,self.opts["accounts"][pseudo],selectcommand=lambda acc=pseudo: self.select_account(acc),deletecommand=lambda acc=pseudo: self.delete_account(acc))
                self.saccounts[pseudo].pack(fill="x")
            else:
                return
        else:
            def authenticate():
                ret = get_portblemc_auth()
                if ret != None:
                    pseudo = ret["profile_name"]
                    self.opts[accounts][pseudo] = ret
                    self.saccounts[pseudo]=AccountDisplay(self.list_accounts_f.scrollable_frame,self.opts["accounts"][pseudo],selectcommand=lambda acc=pseudo: self.select_account(acc),deletecommand=lambda acc=pseudo: self.delete_account(acc))
                    self.saccounts[pseudo].pack(fill="x")
            root = self.winfo_toplevel()  # Get closest parent window (usually root)
            root.withdraw()  # Hide the window
            authenticate()
            root.deiconify()  # Show the window
        self.close_new_account_frame()
    def close_new_account_frame(self):
        self.new_account_frame.pack_forget()
        self.tabsf.pack(fill="x")
        self.tab_account_c.pack(fill="both", expand=True)
        #self.show_accounts_list()
    def get_auth(self):
        if not len(self.opts["accounts"])==0:
            if self.opts["sel_account"] in self.opts["accounts"].keys():
                if "type" in self.opts["accounts"][self.opts["sel_account"]].keys() and self.opts["accounts"][self.opts["sel_account"]]["type"] == "microsoft":
                    p = self.opts["accounts"][self.opts["sel_account"]]
                    auths = MicrosoftAuthSession.__new__() # auth back to minecraft
                    for field in auths.fields:
                        setattr(auths, field, p[field])
                    auths.fixes()
                    return auths
                else:
                    return OfflineAuthSession(self.opts["accounts"][self.opts["sel_account"]]["pseudo"],self.opts["accounts"][self.opts["sel_account"]]["uuid"])
        else:
            return OfflineAuthSession("Steve", str(uuid4()))
    def set_nacctype(self,event=None):
        if self.new_account_type.get() == "offline":
            self.pseudo_l.grid(row=2,column=0,sticky="w")
            self.offlineacc_pseudo.grid(row=2,column=1,sticky="we")
            self.validate_b.configure(text="Valider")
        else:
            self.offlineacc_pseudo.grid_forget()
            self.pseudo_l.grid_forget()
            self.validate_b.configure(text="Se connecter à Minecraft\npar compte Microsoft")
    def tab_select(self,tabname):
        """
    Permet de changer l'onglet actif entre "Jeu" et "Comptes".

    Args:
        tabname (str): Soit "game" pour l'onglet "Jeu", soit "account" pour
            l'onglet "Comptes".
        """
        if tabname=="game":
            self.tab_game["state"]="disabled"
            self.tab_game["background"]="#4E5050"
            self.tab_account_c.pack_forget()
            self.tab_game_c.pack(fill="both",expand=True)
            self.tab_accounts["state"]="normal"
            self.tab_accounts["background"]="#2E3030"
        else:
            self.tab_accounts["state"]="disabled"
            self.tab_accounts["background"]="#4E5050"
            self.tab_game_c.pack_forget()
            self.tab_account_c.pack(fill="both",expand=True)
            self.tab_game["state"]="normal"
            self.tab_game["background"]="#2E3030"

    def show_accounts_list(self):

        for child in self.list_accounts_f.scrollable_frame.winfo_children():
            child.destroy()
        for account in self.opts["accounts"].keys():
            if account != self.opts["sel_account"]:
                self.saccounts[account]=AccountDisplay(self.list_accounts_f.scrollable_frame,self.opts["accounts"][account],selectcommand=lambda acc=account: self.select_account(acc),deletecommand=lambda acc=account: self.delete_account(acc))
                self.saccounts[account].pack(fill="x")
                #Button(self.list_accounts_f.scrollable_frame,background="#2E3030",activebackground="#3E4040",activeforeground="white",foreground="white",text=account,relief="flat",command=lambda acc=account: self.select_account(acc)).pack(fill="x")
            else:
                self.saccounts[account]=AccountDisplay(self.list_accounts_f.scrollable_frame,self.opts["accounts"][account],selectcommand=lambda acc=account: self.select_account(acc),deletecommand=lambda acc=account: self.delete_account(acc),state="selected")
                self.saccounts[account].pack(fill="x")
                #Button(self.list_accounts_f.scrollable_frame,background="green",disabledforeground="black",text=account,relief="flat",state="disabled").pack(fill="x")

    def select_account(self,account):
        if self.opts["sel_account"] in self.opts["accounts"].keys():
            self.saccounts[self.opts["sel_account"]]["state"]="normal"
        self.opts["sel_account"]=account
        self.saccounts[self.opts["sel_account"]]["state"]="selected"
        #self.show_accounts_list()

    def delete_account(self,account):
        if len(self.opts["accounts"])==1:
            return # TODO: add back steve account if there is none remaining after deletion
        if account in self.opts["accounts"].keys():
            del self.opts["accounts"][account]
            self.saccounts[account].destroy()
            del self.saccounts[account]
        if self.opts["sel_account"]==account:
            new_selected=list(self.opts["accounts"].keys())[0]
            self.opts["sel_account"]=new_selected
            self.saccounts[new_selected]["state"]="selected"
        #self.show_accounts_list()
    def get_resolution(self):
        return self.resolution_s.get()
    def updatejson(self):
        self.opts["resolution"] = self.get_resolution()
        self.opts["memory"] = self.memory_s.get()
    def get_jvm_args(self):
        return [f"-Xmx{self.memory_s.get()}M",
                # Et mettre java en français.
                "-Duser.language=fr", "-Duser.country=FR"]