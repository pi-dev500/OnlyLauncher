import requests
from bs4 import BeautifulSoup
import os
import json
from pathlib import Path
import platform
from portablemc.optifine import OptifineVersion, get_compatible_versions as of_version_dict, \
    get_offline_versions as of_offline_dict
from portablemc.standard import VersionNotFoundError


class Watcher:
    def handle(self, event):
        pass

if platform.system() == "Windows":
    mc_directory = os.path.expanduser(os.path.join("~", "AppData", "Roaming", ".minecraft"))
else:
    mc_directory = os.path.expanduser("~/.minecraft")

import threading as mt
Path(mc_directory).mkdir(parents=True, exist_ok=True)


# === MEMORY CACHE SYSTEM ===
class MemoryCache:
    """Cache en mémoire pour éviter les accès SSD répétés"""
    _cache = {}
    _lock = mt.Lock()

    @classmethod
    def get(cls, key):
        with cls._lock:
            return cls._cache.get(key)

    @classmethod
    def set(cls, key, value):
        with cls._lock:
            cls._cache[key] = value

    @classmethod
    def exists(cls, key):
        with cls._lock:
            return key in cls._cache

    @classmethod
    def clear(cls, key=None):
        with cls._lock:
            if key:
                cls._cache.pop(key, None)
            else:
                cls._cache.clear()


def hash(path):
    return hex(sum([ord(c) for c in path]))


def download(addr):
    try:
        content = "".join(i.decode() for i in requests.get(addr).iter_content(1024))
        cache_path = os.path.join(mc_directory, "launcher_cache", hash(addr))
        with open(cache_path, "w") as cachefile:
            cachefile.write(content)
        # Mettre en cache mémoire aussi
        MemoryCache.set(f"download:{addr}", content)
    except Exception as e:
        cache_path = os.path.join(mc_directory, "launcher_cache", hash(addr))
        if os.path.exists(cache_path):
            print(f"Using cached {addr} stored in {hash(addr)} because of error: {e}")
        else:
            raise Exception(f"Impossible de récupérer {addr}")


def refresh_cache():
    adresses = (
        "https://launchermeta.mojang.com/mc/game/version_manifest.json",
        "https://meta.fabricmc.net/v2/versions",
        "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml",
        "https://meta.quiltmc.org/v3/versions",
        "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
    )

    def optifine():
        try:
            optifine_versions = of_version_dict(Path(mc_directory))
        except VersionNotFoundError:
            optifine_versions = of_offline_dict(Path(mc_directory) / "versions")
        return optifine_versions

    os.makedirs(os.path.join(mc_directory, "launcher_cache"), exist_ok=True)
    commands = [mt.Thread(target=download, args=[addr]) for addr in adresses]
    for c in commands:
        c.start()

    optifine_versions = optifine()
    MemoryCache.set("optifine_versions", optifine_versions)

    for c in commands:
        c.join()

    # Clear version list cache to force refresh
    MemoryCache.clear("version_list")
    MemoryCache.clear("fabric_support")
    MemoryCache.clear("fabric_loaders")
    MemoryCache.clear("forge_versions")
    MemoryCache.clear("neoforge_versions")


class cached_content:
    def __init__(self, filepath):
        self.filepath = filepath
        try:
            with open(self.filepath, "r") as f:
                self.text = f.read()
            self.status_code = 200
        except:
            self.status_code = 404

    @staticmethod
    def get(url):
        filename = hash(url)
        return cached_content(os.path.join(mc_directory, "launcher_cache", filename))

    def json(self):
        with open(self.filepath, "r") as f:
            content = json.load(f)
        return content

    def raw_content(self):
        with open(self.filepath, "r") as f:
            content = f.read()
        return content


def get_version_list():
    """Récupère la liste des versions avec cache mémoire et disque"""
    # Vérifier le cache mémoire d'abord
    cached = MemoryCache.get("version_list")
    if cached is not None:
        return cached

    manifest_url = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
    try:
        list_versions = cached_content.get(manifest_url).json()
        with open(os.path.join(mc_directory, "version_manifest.json"), "w") as m:
            json.dump(list_versions, m)
    except:
        try:
            with open(os.path.join(mc_directory, "version_manifest.json"), "r") as m:
                list_versions = json.load(m)
        except:
            list_versions = {"versions": []}

    versions = {}
    for i in list_versions["versions"]:
        versions[i["id"]] = {"type": i["type"], "url": i["url"]}

    # Mettre en cache mémoire
    MemoryCache.set("version_list", versions)
    return versions


def get_fabric_support(url="https://meta.fabricmc.net/v2/versions"):
    """Récupère les versions Minecraft supportées par Fabric"""
    # Vérifier le cache mémoire d'abord
    cached = MemoryCache.get("fabric_support")
    if cached is not None:
        return cached

    try:
        response = cached_content.get(url)
        if response.status_code == 200:
            result = [v["version"] for v in response.json()["game"]]
            MemoryCache.set("fabric_support", result)
            return result
    except:
        pass
    return []


def get_fabric_loaders(url="https://meta.fabricmc.net/v2/versions"):
    """Récupère les versions des loaders Fabric"""
    # Vérifier le cache mémoire d'abord
    cached = MemoryCache.get("fabric_loaders")
    if cached is not None:
        return cached

    try:
        response = cached_content.get(url)
        if response.status_code == 200:
            result = [v["version"] for v in response.json()["loader"]]
            MemoryCache.set("fabric_loaders", result)
            return result
    except:
        pass
    return []


def get_forge_versions():
    """Récupère les versions Forge avec cache mémoire et disque"""
    # Vérifier le cache mémoire d'abord
    cached = MemoryCache.get("forge_versions")
    if cached is not None:
        return cached

    url = "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml"
    response = cached_content.get(url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'xml')
        forges = soup.find_all('version')

        versions = dict()
        for forge in forges:
            mc_v = forge.text.split('-')[0]
            if not mc_v in versions.keys():
                versions[mc_v] = list()
            versions[mc_v].append(forge.text.split('-')[1])

        reordered_versions = [v for v in get_version_list().keys() if v in versions.keys()]
        versions = {v: versions[v] for v in reordered_versions if v in versions.keys()}

        # Mettre en cache mémoire
        MemoryCache.set("forge_versions", versions)
        return versions
    else:
        print('Erreur lors de la requête HTTP')


def get_neoforge_versions():
    """Récupère les versions NeoForge avec cache mémoire et disque"""
    # Vérifier le cache mémoire d'abord
    cached = MemoryCache.get("neoforge_versions")
    if cached is not None:
        return cached

    url = "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
    response = cached_content.get(url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "xml")
        neoforges = soup.find_all('version')

        versions = [v.text for v in neoforges]

        # Mettre en cache mémoire
        MemoryCache.set("neoforge_versions", versions)
        return versions
    else:
        print('Erreur lors de la requête HTTP')


def wget(url, file, watcher=Watcher):
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
    with open(local_filename, "wb") as f:
        for chunk in r.iter_content(chunk_size=512 * 1024):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
    return local_filename


def get_optifine_versions():
    """Récupère les versions OptiFine depuis le cache mémoire"""
    return MemoryCache.get("optifine_versions")