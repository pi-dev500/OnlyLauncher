#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Nov 27 18:44:20 2024

@author: pi-dev500
"""
from tkinter import *
from tkinter import ttk
import os
class SwitchButton(ttk.Label):
    def __init__(self,*args,value=True,command=None,**kw):
        # basic custom slide Switch Button, made of a label and 2 images
        self.image_on=PhotoImage(file=os.path.join(os.path.dirname(__file__),"on.png")).subsample(6,6)
        self.image_off=PhotoImage(file=os.path.join(os.path.dirname(__file__),"off.png")).subsample(6,6)
        super().__init__(*args,**kw,relief="flat",borderwidth=0)
        self.bind("<Button-1>",self.on_click)
        self.value=value
        if self.value:
            self.configure(image=self.image_on)
        else:
            self.configure(image=self.image_off)
        self.command=command
    def on_click(self,ev=None):
        self.value = not self.value
        if self.value:
            self.configure(image=self.image_on)
        else:
            self.configure(image=self.image_off)
            
        if self.command is not None:
            self.command(self.value)
    def get(self):
        return self.value
        
if __name__=="__main__":
    root=Tk()
    sw=SwitchButton(root)
    sw.pack()
    root.mainloop()