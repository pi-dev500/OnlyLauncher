import requests
from bs4 import BeautifulSoup
import tkinter as tk
from tkinterweb import HtmlFrame
import webbrowser
import os
import sys
from threading import Thread
DIRECTORY=os.path.dirname(os.path.realpath(sys.argv[0]))

class TkMcNews(HtmlFrame):
    def __init__(self,parent):
        super().__init__(parent, horizontal_scrollbar=None,messages_enabled = False)
        self.on_link_click(webbrowser.open)
        self.tl=Thread(target=self.load_news)
        self.after(0,self.tl.start)
        #self.load_news()
    def load_news(self,failmessage=True):
        # Récupérer le contenu de la page
        try:
            url = "https://minecraft.fr/categorie/news/"
            response = requests.get(url)
            soup = BeautifulSoup(response.content, 'html.parser')

            # Rechercher la section d'intérêt avec les classes spécifiées
            posts_section = soup.find('div',class_="paginated_content")#'posts-blog-feed-module post-module et_pb_extra_module masonry et_pb_posts_blog_feed_masonry_0 paginated et_pb_extra_module')

            # Ajouter des headers customisés pour le style
            with open(os.path.join(DIRECTORY,"mcfrheaders.html"), "r", encoding="utf-8") as file:
                custom_head = file.read()

            # Recomposer le HTML filtré avec le head personnalisé #{custom_head}
            self.filtered_html = f"<html>{custom_head}<body><div class=\"posts-blog-feed-module post-module et_pb_extra_module masonry et_pb_posts_blog_feed_masonry_0 paginated et_pb_extra_module\">"
            if posts_section:
                self.filtered_html += str(posts_section)
            self.filtered_html += "</div></body></html>"
            print("Actualités récupérées depuis minecraft.fr")
        except Exception as e:
            print(e)
            if failmessage:
                print("Impossible de télécharger le flux d'actualités, il semble que l'ordinateur n'a pas accès à Internet")
            self.filtered_html="<html><head></head><body><h1>Pas de connexion internet. \n Impossible de récupérer les actualités.</body></html>"
            self.after(5000,lambda: self.load_news(False))
        self.after(1,lambda:self.load_html(self.filtered_html))
        
        
if __name__=="__main__":
    root = tk.Tk()
    nf=TkMcNews(root)
    nf.pack(fill="both", expand=True)
    root.mainloop()
    
