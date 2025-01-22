import requests
from bs4 import BeautifulSoup
import os
import json
from pathlib import Path
import platform

class Watcher:
    def handle(self,event):
        pass
if platform.system()=="Windows":
    mc_directory=os.path.expanduser(os.path.join("~","AppData","Roaming",".minecraft"))
else:
    mc_directory=os.path.expanduser("~/.minecraft")
import threading as mt
Path(mc_directory).mkdir(parents=True,exist_ok=True)

def hash(path):
    return hex(sum([ord(c) for c in path]))
def download(addr):
    try:
        content = "".join(i.decode() for i in requests.get(addr).iter_content(1024))
        with open(os.path.join(mc_directory, "launcher_cache", hash(addr)), "w") as cachefile:
            cachefile.write(content)
    except Exception as e:
        if os.path.exists(os.path.join(mc_directory, "launcher_cache", hash(addr))):
            print(f"Using cached {addr} stored in {hash(addr)} because of error: {e}")
        else:
            raise Exception(f"Impossible de récupérer {addr}")
def refresh_cache():
    adresses=(
        "https://launchermeta.mojang.com/mc/game/version_manifest.json",
        "https://meta.fabricmc.net/v2/versions",
        "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml",
        "https://meta.quiltmc.org/v3/versions",
        "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml",
        'https://optifine.net/downloads'
    )
    os.makedirs(os.path.join(mc_directory,"launcher_cache"),exist_ok=True)
    commands = [mt.Thread(target=download, args=[addr]) for addr in adresses]
    for c in commands:
        c.start()
    for c in commands:
        c.join()
    return

class cached_content:
    def __init__(self,filepath):
        self.filepath=filepath
        try:
            with open(self.filepath,"r") as f:
                self.text= f.read()
            self.status_code=200
        except:
            self.status_code=404
    @staticmethod
    def get(url):
        filename=hash(url)
        return cached_content(os.path.join(mc_directory,"launcher_cache",filename))
    def json(self):
        with open(self.filepath,"r") as f:
            content=json.load(f)
        return content
    def raw_content(self):
        with open(self.filepath,"r") as f:
            content=f.read()
        return content


def get_version_list():
    manifest_url = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
    try:
        list_versions = cached_content.get(manifest_url).json()
        with open(os.path.join(mc_directory, "version_manifest.json"), "w") as m:
            json.dump(list_versions, m)
    except:
        with open(os.path.join(mc_directory, "version_manifest.json"), "r") as m:
            list_versions = json.load(m)
    versions = {}
    for i in list_versions["versions"]:
        versions[i["id"]] = {"type": i["type"], "url": i["url"]}
    return versions


def get_fabric_support(url="https://meta.fabricmc.net/v2/versions"):
    response = cached_content.get(url)
    if response.status_code == 200:
        return [v["version"] for v in response.json()["game"]]
    else:
        return []


def get_fabric_loaders(url="https://meta.fabricmc.net/v2/versions"):
    response = cached_content.get(url)
    if response.status_code == 200:
        return [v["version"] for v in response.json()["loader"]]
    else:
        return []


def get_forge_versions():
    url = "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml"
    response = cached_content.get(url)
    if response.status_code == 200:
        # Analyse le contenu HTML de la page avec BeautifulSoup
        soup = BeautifulSoup(response.text, 'xml')

        # Recherche les balises <a> contenant les liens de téléchargement
        forges = soup.find_all('version')

        # Parcours des liens de téléchargement et récupération des noms de fichiers
        versions = dict()
        for forge in forges:
            mc_v = forge.text.split('-')[0]
            if not mc_v in versions.keys():
                versions[mc_v] = list()
            versions[mc_v].append(forge.text.split('-')[1])
        reordered_versions = [v for v in get_version_list().keys() if v in versions.keys()]

        versions = {v: versions[v] for v in reordered_versions if v in versions.keys()}
        return versions

    else:
        print('Erreur lors de la requête HTTP')


def get_neoforge_versions():
    url = "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
    response = cached_content.get(url)
    if response.status_code == 200:
        # Analyse le contenu HTML de la page avec BeautifulSoup
        soup = BeautifulSoup(response.text, "xml")

        # Recherche les balises contenant les versions
        neoforges = soup.find_all('version')

        # Parcours des liens de téléchargement et récupération des noms de fichiers
        versions = [v.text for v in neoforges]
        return versions

    else:
        print('Erreur lors de la requête HTTP')

def wget(url,file,watcher=Watcher):
    """
    wget-like function to download a file from a given url.
    will support an event handler to be called when the download progress is updated.
    Args:
        url (str): The URL to download.
        file (str): The name of the file to be saved locally.

    Returns:
        str: The name of the file saved locally.
    """
    local_filename = file
    r = requests.get(url)
    with open(local_filename,"wb") as f:
        for chunk in r.iter_content(chunk_size=512 * 1024):
            if chunk: # filter out keep-alive new chunks
                f.write(chunk)
    return local_filename