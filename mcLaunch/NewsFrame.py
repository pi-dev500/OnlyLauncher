import requests
from bs4 import BeautifulSoup
import tkinter as tk
from tkinterweb import HtmlFrame
import webbrowser
import os
import sys
from threading import Thread
import re

DIRECTORY = os.path.dirname(os.path.realpath(__file__))

def extract_youtube_video_id(url):
    regex_pattern = r'(?:v=|be\/|embed\/)([\w-]{11})'
    match = re.search(regex_pattern, url)
    return match.group(1) if match else None

def get_yt_image(yturl):
    id = extract_youtube_video_id(yturl)
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
    def __init__(self, parent):
        super().__init__(parent, horizontal_scrollbar=None, messages_enabled=False, javascript_enabled=True)
        self.configure(on_link_click=webbrowser.open)

        # Smooth scrolling inertia attributes
        self.scroll_speed = 0
        self._inertia_running = False

        # Bind mouse wheel events for smooth scrolling
        self.bind("<Enter>", self._bind_mousewheel)
        self.bind("<Leave>", self._unbind_mousewheel)
        self._mousewheel_bound = False

        # Start loading news in background
        self.tl = Thread(target=self.load_news, daemon=True)
        self.after(0, self.tl.start)

    def _bind_mousewheel(self, event=None):
        """Bind mousewheel events when mouse enters the HtmlFrame."""
        if not self._mousewheel_bound:
            self.bind_all("<MouseWheel>", self._on_mousewheel)
            self.bind_all("<Button-4>", self._on_mousewheel)
            self.bind_all("<Button-5>", self._on_mousewheel)
            self._mousewheel_bound = True

    def _unbind_mousewheel(self, event=None):
        """Unbind mousewheel events when mouse leaves the HtmlFrame."""
        if self._mousewheel_bound:
            self.unbind_all("<MouseWheel>")
            self.unbind_all("<Button-4>")
            self.unbind_all("<Button-5>")
            self._mousewheel_bound = False

    def _on_mousewheel(self, event):
        """Handle mousewheel events and start inertia scrolling."""
        # Determine scroll direction and magnitude
        if event.num == 4:  # Linux scroll up
            self._start_inertia(-2)
        elif event.num == 5:  # Linux scroll down
            self._start_inertia(2)
        elif event.delta != 0:  # Windows/Mac
            speed = -int(event.delta / 10)
            self._start_inertia(speed)

    def _start_inertia(self, initial_speed):
        """Start or accumulate inertia scroll speed."""
        self.scroll_speed += initial_speed

        # Only start the loop if it's not already running
        if not self._inertia_running:
            self._inertia_running = True
            self._run_inertia()

    def _run_inertia(self):
        """Run the inertia scroll loop with velocity decay."""
        # Stop if speed is near zero
        if abs(self.scroll_speed) < 0.5:
            self.scroll_speed = 0
            self._inertia_running = False
            return

        # Scroll by integer part of speed using tkhtml3's yview
        movement = int(self.scroll_speed)
        if movement != 0:
            try:
                # Use the html widget's yview method (tkhtml3 native)
                self.html.yview("scroll", movement, "units")
            except Exception as e:
                print(f"Scroll error: {e}")

        # Apply velocity decay (friction)
        self.scroll_speed *= 0.9

        # Schedule next frame (~15ms for smooth 60fps-ish feel)
        self.after(15, self._run_inertia)

    def load_news(self, failmessage=True):
        """Load news from minecraft.fr with error handling."""
        try:
            url = "https://minecraft.fr/categorie/news/"
            response = requests.get(url)
            soup = BeautifulSoup(response.content, 'html.parser')

            # Rechercher la section d'intérêt avec les classes spécifiées
            posts_section = soup.find('div', class_="paginated_content")

            # Ajouter des headers customisés pour le style
            custom_head = ""
            try:
                with open(os.path.join(DIRECTORY, "mcfrheaders.html"), "r", encoding="utf-8") as file:
                    custom_head = file.read()
            except FileNotFoundError:
                pass  # If file doesn't exist, continue without it

            # Recomposer le HTML filtré avec le head personnalisé
            self.filtered_html = f"<html>{custom_head}<body><div class=\"posts-blog-feed-module post-module et_pb_extra_module masonry et_pb_posts_blog_feed_masonry_0 paginated et_pb_extra_module\">"

            if posts_section:
                posts_section = replace_youtube_iframes(str(posts_section))
                with open("cache.html", "w") as f:
                    f.write(str(posts_section))
                self.filtered_html += str(posts_section)

            self.filtered_html += "</div></body></html>"

            with open(os.path.join(DIRECTORY, "cache.html"), "w", encoding="utf-8") as c:
                c.write(self.filtered_html)

            print("Actualités récupérées depuis minecraft.fr")

        except Exception as e:
            print(e)
            if failmessage:
                print("Impossible de télécharger le flux d'actualités, il semble que l'ordinateur n'a pas accès à Internet")
            self.filtered_html = "<html><head></head><body><h1>Pas de connexion internet.</h1><p>Impossible de récupérer les actualités.</p></body></html>"
            # Retry after 5 seconds
            self.after(5000, lambda: self.load_news(False))

        # Load HTML into the frame
        self.after(1, lambda: self.load_html(self.filtered_html))

    def destroy(self):
        """Clean up bindings before destroying the widget."""
        self._unbind_mousewheel()
        super().destroy()


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Minecraft News Viewer")
    root.geometry("900x600")

    nf = TkMcNews(root)
    nf.pack(fill="both", expand=True)

    root.mainloop()
