import requests
from bs4 import BeautifulSoup
import tkinter as tk
from tkinterweb import HtmlFrame
import webbrowser
import os
import sys
from threading import Thread
import re
from testmodrinth import *
DIRECTORY=os.path.dirname(os.path.realpath(__file__))


class TkMcNews(HtmlFrame):
    def __init__(self,parent):
        super().__init__(parent, horizontal_scrollbar=None,messages_enabled = False, javascript_enabled=True)
        self.configure(on_link_click=self.lclk)
        self.tl=Thread(target=self.load)
        self.after(0,self.tl.start)
        #self.load_news()
    def load(self,failmessage=True):
        self.mcversion = "1.20.1"
        self.mcloader = "fabric"
        search_terms = "JEI"
        limit = 100  # Number of results per page
        page = 1    # Page number
        facets = [[f"versions:{self.mcversion}"],["project_type:mod"],[f"categories:{self.mcloader}"]]
        mods = search_modrinth_projects(search_terms, facets, limit=100, page=1)
        #for mod in mods['hits']:
        #    print(mod['title'], mod['description'])
        self.load_html(html_from_hits(mods["hits"]))

    def lclk(self,url):
        if url.startswith("modrinth-install://"):
            project_id = url.split("://")[1]
            #print(project_id)
            #print(get_project_data(project_id))
            print(get_project_dependencies(project_id))
            #print(download_mod(project_id))
            print(list_needed_mods(project_id, mc_version=self.mcversion))
        
        
if __name__=="__main__":
    root = tk.Tk()
    nf=TkMcNews(root)
    nf.pack(fill="both", expand=True)
    root.mainloop()
    
