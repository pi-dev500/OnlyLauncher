import re
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

    @classmethod
    def clear_prefix(cls, prefix):
        """Remove every entry whose key starts with the given prefix."""
        with cls._lock:
            for k in [k for k in cls._cache if k.startswith(prefix)]:
                cls._cache.pop(k, None)


def hash(path):
    return hex(sum([ord(c) for c in path]))


LAUNCHER_USER_AGENT = "OnlyLauncher/mcLaunch (https://github.com/pi-dev500/OnlyLauncher)"


def download(addr, retries=2, timeout=20):
    """Downloads `addr` and stores it in the on-disk cache. Returns the downloaded text.

    On network error, the previously cached content is used if it exists (offline
    support), otherwise the exception is propagated.
    """
    cache_path = os.path.join(mc_directory, "launcher_cache", hash(addr))
    last_error = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(addr, timeout=timeout,
                                    headers={"User-Agent": LAUNCHER_USER_AGENT})
            response.raise_for_status()
            content = b"".join(response.iter_content(65536)).decode("utf-8", errors="replace")
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            tmp_path = cache_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as cachefile:
                cachefile.write(content)
            os.replace(tmp_path, cache_path)
            # Mettre en cache mémoire aussi
            MemoryCache.set(f"download:{addr}", content)
            return content

        except Exception as e:  # noqa: BLE001 - we intentionally fall back to the disk cache
            last_error = e
            continue

    if os.path.exists(cache_path):
        print(f"Using cached {addr} stored in {hash(addr)} because of error: {last_error}")
        with open(cache_path, "r", encoding="utf-8", errors="replace") as cachefile:
            return cachefile.read()
    raise Exception(f"Impossible de récupérer {addr}: {last_error}")


def refresh_cache(progress=None):
    """Refresh the on-disk cache of every version source used by the launcher.

    `progress` is an optional callable taking (message: str, fraction: float | None),
    it is called at each step so a splash screen can report what is happening.
    """
    def report(message, fraction=None):
        print(f"[cache] {message}")
        if progress is not None:
            try:
                progress(message, fraction)
            except Exception:  # a broken progress callback must never break the startup
                pass

    adresses = (
        "https://launchermeta.mojang.com/mc/game/version_manifest.json",
        "https://meta.fabricmc.net/v2/versions",
        "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml",
        "https://meta.quiltmc.org/v3/versions",
        "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
    )

    results = {}

    def optifine():
        try:
            results["optifine"] = of_version_dict(Path(mc_directory))
        except VersionNotFoundError:
            results["optifine"] = of_offline_dict(Path(mc_directory) / "versions")
        except Exception as e:  # noqa: BLE001 - OptiFine is optional
            print(f"[cache] OptiFine indisponible: {e}")
            results["optifine"] = {}

    os.makedirs(os.path.join(mc_directory, "launcher_cache"), exist_ok=True)
    report("Téléchargement des listes de versions…", 0.10)
    commands = [mt.Thread(target=download, args=[addr], daemon=True) for addr in adresses]
    optifine_thread = mt.Thread(target=optifine, daemon=True)
    for c in commands:
        c.start()
    optifine_thread.start()

    for i, c in enumerate(commands):
        c.join()
        report("Téléchargement des listes de versions…", 0.10 + 0.30 * (i + 1) / len(commands))

    report("Recherche des versions OptiFine…", 0.45)
    optifine_thread.join()

    # Every derived list must be recomputed from the freshly downloaded files: the
    # cache keys used to be shared between sources (Fabric/Quilt returned the same
    # list), they are now URL-scoped, so we simply drop all of them.
    MemoryCache.clear()
    MemoryCache.set("optifine_versions", results.get("optifine") or {})
    report("Cache des versions prêt.", 0.50)
    return True


class cached_content:
    def __init__(self, filepath):
        self.filepath = filepath
        try:
            with open(self.filepath, "r", encoding="utf-8", errors="replace") as f:
                self.text = f.read()
            self.status_code = 200
        except OSError:
            self.text = ""
            self.status_code = 404

    @staticmethod
    def get(url):
        filename = hash(url)
        return cached_content(os.path.join(mc_directory, "launcher_cache", filename))

    def json(self):
        with open(self.filepath, "r", encoding="utf-8", errors="replace") as f:
            content = json.load(f)
        return content

    def raw_content(self):
        with open(self.filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return content


def get_version_list():
    """Récupère la liste des versions avec cache mémoire et disque"""
    # Vérifier le cache mémoire d'abord
    cached = MemoryCache.get("version_list")
    if cached is not None:
        return cached

    manifest_url = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
    list_versions = {"versions": []}
    try:
        list_versions = cached_content.get(manifest_url).json()
        try:
            with open(os.path.join(mc_directory, "version_manifest.json"), "w", encoding="utf-8") as m:
                json.dump(list_versions, m)
        except OSError as e:
            print(f"[cache] Impossible d'écrire le manifeste local: {e}")
    except Exception as e:
        print(f"[cache] Manifeste Mojang indisponible ({e}), lecture du cache local")
        try:
            with open(os.path.join(mc_directory, "version_manifest.json"), "r", encoding="utf-8") as m:
                list_versions = json.load(m)
        except (OSError, json.JSONDecodeError):
            list_versions = {"versions": []}

    versions = {}
    for i in list_versions["versions"]:
        versions[i["id"]] = {"type": i["type"], "url": i["url"]}

    # Mettre en cache mémoire
    MemoryCache.set("version_list", versions)
    return versions


def get_fabric_support(url="https://meta.fabricmc.net/v2/versions"):
    """Récupère les versions Minecraft supportées par Fabric (ou par Quilt si url est fourni).

    Le cache mémoire est indexé par URL: Fabric et Quilt ont des listes différentes.
    """
    cache_key = f"fabric_support:{url}"
    cached = MemoryCache.get(cache_key)
    if cached is not None:
        return cached

    try:
        response = cached_content.get(url)
        if response.status_code == 200:
            result = [v["version"] for v in response.json()["game"]]
            MemoryCache.set(cache_key, result)
            return result
    except Exception as e:
        print(f"[cache] Liste des versions supportées indisponible ({url}): {e}")
    return []


def get_fabric_loaders(url="https://meta.fabricmc.net/v2/versions"):
    """Récupère les versions des loaders Fabric (ou Quilt si url est fourni).

    Le cache mémoire est indexé par URL: Fabric et Quilt ont des listes différentes.
    """
    cache_key = f"fabric_loaders:{url}"
    cached = MemoryCache.get(cache_key)
    if cached is not None:
        return cached

    try:
        response = cached_content.get(url)
        if response.status_code == 200:
            result = [v["version"] for v in response.json()["loader"]]
            MemoryCache.set(cache_key, result)
            return result
    except Exception as e:
        print(f"[cache] Liste des loaders indisponible ({url}): {e}")
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
        print('Erreur lors de la requête HTTP (Forge)')
        return {}


def neoforge_game_versions():
    """Versions de Minecraft de NeoForge, avec leurs versions NeoForge.

    Renvoie ``{"1.21.1": ["21.1.256", ...], "26.1": [...], ...}``, les versions NeoForge
    étant triées de la plus récente à la plus ancienne.

    La liste maven de NeoForge ne contient que des versions de NeoForge: le numéro de
    version encode la version de Minecraft. Deux schémas coexistent:
      * "21.1.256"     -> NeoForge 21.1 pour Minecraft 1.21.1 (<mc mineure>.<mc correctif>.<n>)
      * "26.1.0.0+..."  -> NeoForge 26.1 pour Minecraft 26.1 (numérotation alignée)
    """
    cached = MemoryCache.get("neoforge_by_game")
    if cached is not None:
        return cached

    mapping = {}
    for full in get_neoforge_versions():
        parts = str(full).split("-")[0].split("+")[0].split(".")
        if len(parts) < 2 or not parts[0].isdigit() or int(parts[0]) <= 0:
            continue
        major = int(parts[0])
        if major >= 1 and len(parts) >= 2 and parts[0] in ("20", "21"):
            # Ancien schéma: NeoForge 20.4.237 <-> Minecraft 1.20.4
            if not parts[1].isdigit():
                continue
            game_version = f"1.{parts[0]}.{parts[1]}"
        elif major >= 2:
            # Nouveau schéma: NeoForge 26.1.0.0 <-> Minecraft 26.1
            if not parts[1].isdigit():
                continue
            game_version = f"{parts[0]}.{parts[1]}"
        else:
            continue
        mapping.setdefault(game_version, []).append(full)

    def sort_key(version):
        # Compare on the numeric groups only: "21.1.256", "26.3.0.46-beta" -> [21,1,256].
        return [int(group) for group in re.findall(r"\d+", str(version))] or [-1]

    for game_version in mapping:
        mapping[game_version] = sorted(set(mapping[game_version]), key=sort_key, reverse=True)
    MemoryCache.set("neoforge_by_game", mapping)
    return mapping


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
        print('Erreur lors de la requête HTTP (NeoForge)')
        return []


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
    """Récupère les versions OptiFine depuis le cache mémoire.

    Renvoie toujours un dict (éventuellement vide): l'appelant utilise `.keys()`
    et `.get()`, un `None` le faisait planter quand le rafraîchissement n'avait
    pas encore rempli le cache.
    """
    return MemoryCache.get("optifine_versions") or {}