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
    """Page "Actualités" de minecraft.fr.

    Le site peut être indisponible ou changer de structure: dans ce cas la dernière page
    correctement téléchargée (cache.html) est réaffichée au lieu d'un simple message
    d'erreur, et le téléchargement est retenté quelques fois.
    """

    #: Nombre maximum de tentatives quand minecraft.fr est injoignable.
    MAX_ATTEMPTS = 3

    def __init__(self, parent):
        super().__init__(parent, horizontal_scrollbar="auto", messages_enabled=False,
                         javascript_enabled=False, on_link_click=self._on_link_click,
                         on_navigate_fail=self._on_link_click)
        self.filtered_html = ""

        # Smooth scrolling inertia attributes
        self.scroll_speed = 0
        self._inertia_running = False
        self.todo_scroll = 0

        # Bind mouse wheel events for smooth scrolling
        self.bind("<Enter>", self._bind_mousewheel)
        self.bind("<Leave>", self._unbind_mousewheel)
        self._mousewheel_bound = False

        # Start loading news in background
        self.tl = Thread(target=self.load_news, daemon=True)
        self.after(0, self.tl.start)

    def _on_link_click(self, url):
        """Les liens normaux vont au navigateur, `mclaunch://news/reload` recharge la page."""
        url = str(url)
        if url.startswith("mclaunch://news/reload"):
            Thread(target=self.load_news, kwargs={"failmessage": False}, daemon=True).start()
            return
        webbrowser.open(url)

    def _show_html(self, html):
        """Charge du HTML dans le fil principal (le widget n'est pas thread-safe)."""
        state = {"done": False}
        watchdog = None

        def run():
            state["done"] = True
            try:
                self.load_html(html)
            except Exception as e:  # noqa: BLE001
                print(f"Affichage des actualités impossible: {e}")
        try:
            watchdog = self.after(3000, run)
            self.after(0, run)
        except RuntimeError:
            if not state["done"] and watchdog is not None:
                try:
                    self.after_cancel(watchdog)
                except Exception:  # noqa: BLE001
                    pass

    def _load_cached_news(self):
        """Réaffiche la dernière page correctement récupérée. False si aucune."""
        try:
            with open(os.path.join(DIRECTORY, "cache.html"), "r", encoding="utf-8") as f:
                cached = f.read()
        except OSError:
            return False
        if "posts-blog-feed-module" not in cached and "paginated_content" not in cached:
            return False
        self.filtered_html = cached
        return True

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
            self._start_inertia(-20)
        elif event.num == 5:  # Linux scroll down
            self._start_inertia(20)
        elif event.delta != 0:  # Windows/Mac
            speed = -int(event.delta * 10)
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
        self.html.config(yscrollincrement=1)
        if abs(self.todo_scroll) > 1:
            self.html.yview("scroll", self.todo_scroll, "units")
            self.todo_scroll = 0
        if abs(self.scroll_speed) < 0.001:
            self.scroll_speed = 0
            self._inertia_running = False
            self.html.yview("scroll", self.todo_scroll, "units")
            self.todo_scroll = 0
            return

        # Scroll by integer part of speed using tkhtml3's yview
        movement = int(self.scroll_speed / 2)
        if movement != 0:
            try:
                if abs(movement) > 0.1:
                # Use the html widget's yview method (tkhtml3 native)
                    self.html.yview("scroll", movement, "units")
                else:
                    self.todo_scroll += movement
            except Exception as e:
                print(f"Scroll error: {e}")
        dire = 1 if self.scroll_speed > 0 else -1

        # Apply velocity decay (friction)
        self.scroll_speed = min(abs(self.scroll_speed), 100) * dire
        self.scroll_speed *= 0.9

        # Schedule next frame (~15ms for smooth 60fps-ish feel)
        self.after(15, self._run_inertia)

    def load_news(self, failmessage=True, attempt=0):
        """Charge les actualités de minecraft.fr (avec repli sur la dernière page reçue)."""
        try:
            url = "https://minecraft.fr/categorie/news/"
            response = requests.get(
                url, timeout=10,
                headers={"User-Agent": "OnlyLauncher/mcLaunch "
                                       "(https://github.com/pi-dev500/OnlyLauncher)"})
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Rechercher la section d'intérêt avec les classes spécifiées
            posts_section = soup.find('div', class_="paginated_content")
            if posts_section is None:
                # Le site a changé de structure: on tente les conteneurs voisins avant
                # d'abandonner, sinon la page restait vide.
                for alternative in ("et_pb_posts_blog_feed_masonry", "posts-blog-feed-module",
                                    "entry-content", "main"):
                    posts_section = soup.find("div", class_=alternative) or soup.find(alternative)
                    if posts_section is not None:
                        print(f"Actualités: structure inconnue, repli sur <div class={alternative!r}>")
                        break
            if posts_section is None:
                raise ValueError("section d'actualités introuvable (site mis à jour ?)")

            # Ajouter des headers customisés pour le style
            custom_head = ""
            try:
                with open(os.path.join(DIRECTORY, "mcfrheaders.html"), "r", encoding="utf-8") as file:
                    custom_head = file.read()
            except FileNotFoundError:
                pass  # If file doesn't exist, continue without it

            # Recomposer le HTML filtré avec le head personnalisé
            self.filtered_html = f"<html>{custom_head}<body><div class=\"posts-blog-feed-module post-module et_pb_extra_module masonry et_pb_posts_blog_feed_masonry_0 paginated et_pb_extra_module\">"
            self.filtered_html += replace_youtube_iframes(str(posts_section))
            self.filtered_html += "</div></body></html>"

            with open(os.path.join(DIRECTORY, "cache.html"), "w", encoding="utf-8") as c:
                c.write(self.filtered_html)

            print("Actualités récupérées depuis minecraft.fr")
            self._show_html(self.filtered_html)
            return

        except Exception as e:
            print(f"Actualités indisponibles: {e}")
            if failmessage:
                print("Impossible de télécharger le flux d'actualités "
                      "(minecraft.fr est peut-être hors service, ou l'ordinateur est hors ligne).")
            # Repli: la dernière page correctement récupérée reste affichée.
            if self._load_cached_news():
                self._show_html(self.filtered_html)
                return

        attempt_note = ("Nouvelle tentative en cours…" if attempt < self.MAX_ATTEMPTS
                        else "Le site minecraft.fr est probablement hors service.")
        self.filtered_html = (
            "<html><head><style>body{background:#1e1e1e;color:#e8e8e8;font-family:sans-serif;"
            "padding:24px} h1{color:#30b6a2} a{color:#30b6a2}</style></head><body>"
            "<h1>Actualités indisponibles.</h1>"
            "<p>Impossible de récupérer les actualités depuis minecraft.fr.</p>"
            f"<p>{attempt_note}</p>"
            '<p><a href="mclaunch://news/reload">Réessayer maintenant</a></p>'
            "</body></html>")
        if attempt < self.MAX_ATTEMPTS:
            # Retry after 5 seconds
            try:
                self.after(5000, lambda: self.load_news(False, attempt + 1))
            except RuntimeError:
                pass
        self._show_html(self.filtered_html)

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
