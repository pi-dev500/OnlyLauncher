import requests
from bs4 import BeautifulSoup
import tkinter as tk
from tkinterweb import HtmlFrame
import webbrowser
import os
import sys
from threading import Thread
import re
DIRECTORY=os.path.dirname(os.path.realpath(__file__))
def extract_youtube_video_id(url):
    regex_pattern = r'(?:v=|be\/|embed\/)([\w-]{11})'
    match = re.search(regex_pattern, url)
    return match.group(1) if match else None

def get_yt_image(yturl):
    id=extract_youtube_video_id(yturl)
    return f"https://img.youtube.com/vi/{id}/maxresdefault.jpg"


def replace_youtube_iframes(html_content):
    """Replaces YouTube iframes with thumbnail images using regex."""
    pattern = re.compile(r'<iframe[^>]+src=["\'](https?://(?:www\.)?youtube\.com/embed/([\w-]{11})[^"\']*)["\'][^>]*>',
                         re.IGNORECASE)

    def iframe_replacer(match):
        video_url = match.group(1)
        video_id = match.group(2)
        thumbnail_url = get_yt_image(video_url)
        return f'<a href="{video_url}"><img src="{thumbnail_url}" alt="YouTube Video Thumbnail" style="width: 627px"></a>' if thumbnail_url else match.group(0)

    return pattern.sub(iframe_replacer, html_content)
class TkMcNews(HtmlFrame):
    def __init__(self,parent):
        super().__init__(parent, horizontal_scrollbar=None,messages_enabled = False, javascript_enabled=True)
        self.configure(on_link_click=webbrowser.open)
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
                posts_section = replace_youtube_iframes(str(posts_section))
                with open("cache.html","w") as f:
                    f.write(str(posts_section))
                self.filtered_html += str(posts_section)
            self.filtered_html += "</div></body></html>"
            with open(os.path.join(DIRECTORY,"cache.html"), "w", encoding="utf-8") as c:
                c.write(self.filtered_html)
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
