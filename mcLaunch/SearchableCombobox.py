#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 25 20:54:14 2024

@author: pi-dev500
"""

from tkinter import *
from PIL import Image, ImageTk

class CustomDropDown(Frame):
    def __init__(self, parent, values=[]) -> None:
        super().__init__(parent)
        self.entry=Entry(self)
        self.entry["state"]="disabled"
        self.entry.pack(side="right",expand=True,fill="both")
        self.button=Button(self,text="▼",width=30,command=self.drop)
        self.button.pack(expand=True,side="left",fill="both")
    def drop(self):
        pass
if __name__=="__main__":
    # Create the main window
    root = tk.Tk()
    root.title("Searchable Dropdown")
    
    options = ["Apple", "Banana", "Cherry", "Date", "Grapes", "Kiwi", "Mango", "Orange", "Peach", "Pear"]
    sc=SearchableComboBox(root,options)
    sc.pack(expand=True)
    # Run the Tkinter event loop
    root.geometry('220x150')
    root.mainloop()