"""
Modrinth API client for mcLaunch / OnlyLauncher.

This module provides everything the "Mods & Modpacks" tab needs:

* low level REST wrappers around the public Modrinth API v2,
* dependency resolution,
* direct mod download and install (with a proper file picker: only the primary
  file of a version is used, and it is verified with its SHA-1 when available),
* full `.mrpack` (Modrinth modpack) installation into an isolated instance,
* HTML rendering helpers used by the embedded browser widget (tkinterweb).

The link scheme used by the generated HTML is `mclaunch://<action>/<argument>`;
it is decoded by `ModrinthBrowser.handle_link` (see Modrinthframe.py). The two
legacy schemes `modrinth-install://<id>` and `project-preview://<id>` are still
understood so that HTML pages cached by older versions keep working.
"""

from __future__ import annotations

import hashlib
import html as _html
import json
import os
import re
import shutil
import tempfile
import urllib.parse
import zipfile
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

# ===== CONSTANTS =====

MODRINTH_API = "https://api.modrinth.com/v2"
# Modrinth asks every API consumer to identify itself.
USER_AGENT = "pi-dev500/OnlyLauncher/mcLaunch (https://github.com/pi-dev500/OnlyLauncher)"
DEFAULT_TIMEOUT = 20

#: Custom link scheme used inside the pages rendered in the launcher.
LINK_SCHEME = "mclaunch"

ProgressCallback = Optional[Callable[[str, Optional[float]], None]]


def _report(progress: ProgressCallback, message: str, fraction: Optional[float] = None) -> None:
    """Call the progress callback, never raising if it is broken."""
    if progress is None:
        return
    try:
        progress(message, fraction)
    except Exception:  # noqa: BLE001 - progress reporting must never break an install
        pass


def _request(endpoint: str, params: Optional[dict] = None, timeout: int = DEFAULT_TIMEOUT):
    """GET a Modrinth API endpoint.

    Always returns a python object: the decoded JSON on success, or a dict with an
    ``"error"`` key on failure, so callers can just test for `"error"` instead of
    handling three different failure modes.
    """
    url = endpoint if endpoint.startswith("http") else f"{MODRINTH_API}{endpoint}"
    try:
        response = requests.get(url, params=params or {},
                                headers={"User-Agent": USER_AGENT}, timeout=timeout)
    except requests.RequestException as e:
        return {"error": f"Réseau indisponible: {e}"}
    if response.status_code != 200:
        return {"error": f"Erreur HTTP {response.status_code}"}
    try:
        return response.json()
    except ValueError as e:
        return {"error": f"Réponse invalide: {e}"}


def _encode_list(items: Iterable[str]) -> str:
    return json.dumps(list(items))


# ===== LOW LEVEL REST WRAPPERS =====

def search_modrinth_projects(search_terms: str = "", facets: Sequence = (),
                             index: str = "relevance", limit: int = 20,
                             page: int = 1) -> dict:
    """Search projects. Returns a dict with at least a "hits" list."""
    limit = max(1, min(int(limit), 100))
    page = max(1, int(page))
    result = _request("/search", {
        "query": search_terms or "",
        "facets": _encode_list(facets or ()),
        "limit": limit,
        "offset": (page - 1) * limit,
        "index": index,
    })
    if "error" in result:
        return {"hits": [], "total_hits": 0, "offset": 0, "limit": limit, "error": result["error"]}
    result.setdefault("hits", [])
    return result


def random_projects(count: int = 20) -> list:
    result = _request("/projects_random", {"count": max(1, min(int(count), 100))})
    return result if isinstance(result, list) else []


def get_project_data(project_id: str):
    return _request(f"/project/{project_id}")


def get_projects(project_ids: Sequence[str]) -> list:
    result = _request("/projects", {"ids": _encode_list(project_ids)})
    return result if isinstance(result, list) else []


def get_available_project_versions(project_id: str, mc_versions: Sequence[str] = (),
                                   loaders: Sequence[str] = (), featured: bool = False) -> list:
    params = {}
    if mc_versions:
        params["game_versions"] = _encode_list(mc_versions)
    if loaders:
        params["loaders"] = _encode_list(loaders)
    if featured:
        params["featured"] = "true"
    result = _request(f"/project/{project_id}/version", params)
    return result if isinstance(result, list) else []


def get_project_dependencies(project_id_or_slug: str):
    """Projects on which this project depends (Modrinth "get dependencies" route)."""
    result = _request(f"/project/{project_id_or_slug}/dependencies")
    return result if isinstance(result, dict) else {"projects": []}


def get_version(project_id_or_slug: str, version_id_or_number: str):
    return _request(f"/project/{project_id_or_slug}/version/{version_id_or_number}")


def get_version_from_id(version_id: str):
    return _request(f"/version/{version_id}")


def get_versions_from_ids(version_ids: Sequence[str]) -> list:
    if not version_ids:
        return []
    result = _request("/versions", {"ids": _encode_list(version_ids)})
    return result if isinstance(result, list) else []


def get_tag_game_versions() -> list:
    result = _request("/tag/game_version")
    return result if isinstance(result, list) else []


def get_tag_loaders() -> list:
    result = _request("/tag/loader")
    return result if isinstance(result, list) else []


def get_tag_categories() -> list:
    result = _request("/tag/category")
    return result if isinstance(result, list) else []


def get_latest_version_for(project_id: str, mc_version: str = "", loader: str = ""):
    """Best version of a project for the given game version / loader.

    Returns the first matching version dict, or None when nothing matches. If the
    filtered request returns nothing, we fall back on the latest version so the user
    still gets a chance to install something.
    """
    versions = get_available_project_versions(project_id, [mc_version] if mc_version else [],
                                             [loader] if loader else [])
    if versions:
        return versions[0]
    versions = get_available_project_versions(project_id)
    return versions[0] if versions else None


# ===== FILE / INSTALL HELPERS =====

def pick_primary_file(version_data: dict) -> Optional[dict]:
    """Return the primary file of a version (the first one if none is flagged)."""
    files = (version_data or {}).get("files") or []
    if not files:
        return None
    for file in files:
        if file.get("primary"):
            return file
    return files[0]


def download_file(url: str, destination: str, progress: ProgressCallback = None,
                  label: str = "", expected_size: int = 0, expected_sha1: str = "",
                  timeout: int = 60) -> bool:
    """Stream a file to `destination`, reporting progress. Returns True on success."""
    destination = str(destination)
    os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
    tmp_path = destination + ".part"
    try:
        with requests.get(url, stream=True, timeout=timeout,
                          headers={"User-Agent": USER_AGENT}) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length") or expected_size or 0)
            done = 0
            digest = hashlib.sha1()
            with open(tmp_path, "wb") as out:
                for chunk in response.iter_content(chunk_size=128 * 1024):
                    if not chunk:
                        continue
                    out.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    fraction = (done / total) if total else None
                    _report(progress, f"Téléchargement de {label or os.path.basename(destination)}…", fraction)
        if expected_sha1 and digest.hexdigest().lower() != expected_sha1.lower():
            os.remove(tmp_path)
            _report(progress, f"Fichier corrompu (SHA-1 invalide): {label}", None)
            return False
        os.replace(tmp_path, destination)
        return True
    except (requests.RequestException, OSError) as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        _report(progress, f"Échec du téléchargement de {label or destination}: {e}", None)
        return False


def download_version_file(version_data: dict, output_dir: str, progress: ProgressCallback = None) -> bool:
    """Download the primary file of a version into `output_dir`."""
    file = pick_primary_file(version_data)
    if not file:
        _report(progress, "Aucun fichier disponible pour cette version.", None)
        return False
    hashes = file.get("hashes") or {}
    return download_file(
        file["url"],
        os.path.join(output_dir, file["filename"]),
        progress=progress,
        label=file["filename"],
        expected_size=file.get("size", 0),
        expected_sha1=hashes.get("sha1", ""),
    )


def list_installed_files(mods_dir: str) -> set:
    """Set of file names (and mod file names without extension) present in a mods folder."""
    if not os.path.isdir(mods_dir):
        return set()
    result = set()
    for name in os.listdir(mods_dir):
        result.add(name.lower())
        result.add(os.path.splitext(name)[0].lower())
    return result


# ===== DEPENDENCY RESOLUTION =====

def resolve_dependencies(project_id: str, mc_version: str = "", loader: str = "",
                         visited: Optional[set] = None,
                         output_dir: Optional[str] = None) -> List[Tuple[str, str, str, str, str]]:
    """Recursively resolve the required dependencies of a project.

    Returns a list of tuples ``(project_id, version_id, project_name, file_name, url)``,
    the requested mod being first. When `output_dir` is given, dependencies whose file
    is already present in that folder are skipped (that is also the case for every
    parent in the `visited` set, which prevents duplicated downloads).
    """
    if visited is None:
        visited = set()
    if project_id in visited:
        return []
    visited.add(project_id)

    installed = list_installed_files(output_dir) if output_dir else set()
    needed: List[Tuple[str, str, str, str, str]] = []

    version_data = None
    if mc_version or loader:
        versions = get_available_project_versions(project_id,
                                                 [mc_version] if mc_version else [],
                                                 [loader] if loader else [])
        if versions:
            version_data = versions[0]
    if version_data is None:
        versions = get_available_project_versions(project_id)
        version_data = versions[0] if versions else None
    if not version_data:
        _report(None, f"Aucune version disponible pour {project_id}", None)
        return []

    file = pick_primary_file(version_data)
    project_data = get_project_data(project_id)
    project_name = project_data.get("title", project_id) if isinstance(project_data, dict) else project_id

    if file:
        already_there = file["filename"].lower() in installed or \
            os.path.splitext(file["filename"])[0].lower() in installed
        if not already_there:
            needed.append((project_id, version_data["id"], project_name,
                           file["filename"], file["url"]))

    for dep in version_data.get("dependencies", []):
        if dep.get("dependency_type") != "required":
            continue
        dep_project_id = dep.get("project_id")
        if not dep_project_id or dep_project_id in visited:
            continue
        needed.extend(resolve_dependencies(dep_project_id, mc_version, loader, visited, output_dir))

    # de-duplicate on (project, file name) while keeping the requested mod first
    seen = set()
    unique = []
    for entry in needed:
        key = (entry[0], entry[3].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)
    return unique


def get_missing_dependencies(project_id: str, mods_dir: str, mc_version: str = "",
                             loader: str = "") -> List[Tuple[str, str, str, str]]:
    """Required dependencies of `project_id` that are NOT yet installed in `mods_dir`.

    Returns tuples ``(project_id, title, version_id, file_name)`` ready to be displayed.
    """
    missing = []
    for dep in resolve_dependencies(project_id, mc_version, loader, None, mods_dir)[1:]:
        missing.append((dep[0], dep[2], dep[1], dep[3]))
    return missing


def download_several_mods_with_dependencies(project_ids: Sequence[str], output_dir: str,
                                             mc_version: str = "", loader: str = "",
                                             progress: ProgressCallback = None) -> List[str]:
    """Install several projects and their required dependencies into `output_dir`."""
    os.makedirs(output_dir, exist_ok=True)
    visited: set = set()
    jobs: List[Tuple[str, str, str, str, str]] = []
    for rank, project_id in enumerate(project_ids):
        _report(progress, f"Résolution des dépendances de {project_id}…", 0.1)
        for job in resolve_dependencies(project_id, mc_version, loader, visited, output_dir):
            if job not in jobs:
                jobs.append(job)
        if rank == 0 and jobs:
            jobs[0] = (job if False else jobs[0])  # keep the requested project first

    installed: List[str] = []
    total = max(1, len(jobs))
    for index, (proj_id, version_id, proj_name, file_name, url) in enumerate(jobs):
        _report(progress, f"Installation de {proj_name} ({index + 1}/{total})…", index / total)
        file = pick_primary_file(get_version_from_id(version_id) or {}) or {
            "url": url, "filename": file_name, "hashes": {}, "size": 0}
        if download_version_file({"files": [file]}, output_dir, progress=progress):
            installed.append(file["filename"])
    _report(progress, f"{len(installed)} fichier(s) installé(s).", 1.0)
    return installed


def download_mod_with_dependencies(project_id: str, output_dir: str, mc_version: str = "",
                                   loader: str = "", progress: ProgressCallback = None) -> List[str]:
    """Install one project and its required dependencies into `output_dir`."""
    return download_several_mods_with_dependencies([project_id], output_dir, mc_version, loader, progress)


# ===== MODPACK (.mrpack) INSTALLATION =====

#: Modrinth modpack dependency id -> loader name used by the launcher profiles
_MODPACK_LOADERS = {
    "fabric-loader": "fabric",
    "quilt-loader": "quilt",
    "forge": "forge",
    "neoforge": "neoforge",
}


def resolve_modpack(version_data: dict) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return ``(mc_version, loader, loader_version)`` announced by a modpack version.

    The values come from the version's ``game_versions``/``loaders``; the exact loader
    build announced in the pack manifest is only known after installation.
    """
    loaders = [l.lower() for l in (version_data or {}).get("loaders", [])]
    game_versions = (version_data or {}).get("game_versions", []) or []
    mc_version = game_versions[0] if game_versions else None
    loader = None
    for candidate in ("fabric", "quilt", "neoforge", "forge"):
        if candidate in loaders:
            loader = candidate
            break
    return mc_version, loader, None


def parse_mrpack_index(index: dict) -> dict:
    """Extract the useful data from a ``modrinth.index.json`` file."""
    dependencies = index.get("dependencies", {}) or {}
    loader = None
    loader_version = None
    for dep_id, loader_name in _MODPACK_LOADERS.items():
        if dep_id in dependencies:
            loader = loader_name
            loader_version = dependencies[dep_id]
            break
    return {
        "name": index.get("name", ""),
        "version_id": index.get("versionId", ""),
        "summary": index.get("summary", ""),
        "mc_version": dependencies.get("minecraft"),
        "loader": loader,
        "loader_version": loader_version,
        "files": index.get("files", []) or [],
    }


def _safe_relative_path(relative_path: str) -> Optional[str]:
    """Guard against zip-slip: reject absolute paths and any '..' component."""
    path = str(relative_path).replace("\\", "/").strip()
    if not path or path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        return None
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    return os.path.join(*parts)


def install_modpack(project_id: str, instance_dir: str, mc_version: str = "",
                    loader: str = "", progress: ProgressCallback = None,
                    selected_paths: Optional[Sequence[str]] = None,
                    version_id: Optional[str] = None) -> dict:
    """Download and install a Modrinth modpack into `instance_dir`.

    The instance folder is a normal Minecraft instance directory (the one used by the
    launcher for isolated profiles), i.e. `mods/`, `config/`, ... live inside it.

    `selected_paths` limits the files taken from the manifest to the given list of
    relative paths (used to honour the optional files chosen by the user).

    Returns a dict: ``{name, mc_version, loader, loader_version, installed, skipped, error}``.
    """
    os.makedirs(instance_dir, exist_ok=True)
    outcome = {"name": "", "mc_version": mc_version, "loader": loader, "loader_version": None,
               "installed": [], "skipped": [], "error": None}

    _report(progress, "Recherche de la dernière version du modpack…", 0.02)
    versions = get_available_project_versions(project_id,
                                             [mc_version] if mc_version else [],
                                             [loader] if loader else [])
    if not versions:
        versions = get_available_project_versions(project_id)
    if not versions:
        outcome["error"] = "Aucune version de ce modpack n'est disponible."
        _report(progress, outcome["error"], None)
        return outcome

    version_data = None
    if version_id:
        version_data = get_version_from_id(version_id)
        if not isinstance(version_data, dict):
            version_data = None
    if version_data is None:
        version_data = versions[0]

    pack_file = pick_primary_file(version_data)
    if not pack_file or not pack_file.get("filename", "").lower().endswith(".mrpack"):
        outcome["error"] = "Cette version ne fournit pas de fichier .mrpack."
        _report(progress, outcome["error"], None)
        return outcome

    tmp_dir = tempfile.mkdtemp(prefix="mclaunch-mrpack-")
    archive_path = os.path.join(tmp_dir, pack_file["filename"])
    try:
        _report(progress, f"Téléchargement du modpack {pack_file['filename']}…", 0.05)
        hashes = pack_file.get("hashes") or {}
        if not download_file(pack_file["url"], archive_path, progress=progress,
                             label=pack_file["filename"], expected_size=pack_file.get("size", 0),
                             expected_sha1=hashes.get("sha1", "")):
            outcome["error"] = "Échec du téléchargement du modpack."
            return outcome

        _report(progress, "Lecture du manifeste du modpack…", 0.15)
        with zipfile.ZipFile(archive_path) as archive:
            try:
                index = json.loads(archive.read("modrinth.index.json").decode("utf-8"))
            except (KeyError, ValueError) as e:
                outcome["error"] = f"Manifeste illisible: {e}"
                return outcome

            manifest = parse_mrpack_index(index)
            outcome["name"] = manifest["name"] or project_id
            outcome["mc_version"] = mc_version or manifest["mc_version"]
            outcome["loader"] = loader or manifest["loader"]
            outcome["loader_version"] = manifest["loader_version"]

            # ---- 1. overrides / client-overrides (no download needed) ----
            for folder in ("overrides", "client-overrides"):
                for member in archive.namelist():
                    if not member.startswith(folder + "/") or member.endswith("/"):
                        continue
                    relative = _safe_relative_path(member[len(folder) + 1:])
                    if relative is None:
                        continue
                    destination = os.path.join(instance_dir, relative)
                    os.makedirs(os.path.dirname(destination), exist_ok=True)
                    with archive.open(member) as source, open(destination, "wb") as target:
                        shutil.copyfileobj(source, target)
                    outcome["installed"].append(relative)

            # ---- 2. files listed in the manifest ----
            candidates = []
            for entry in manifest["files"]:
                env = entry.get("env") or {}
                if env.get("client") == "unsupported":
                    continue
                relative = _safe_relative_path(entry.get("path", ""))
                if relative is None:
                    _report(progress, f"Chemin ignoré (non sûr): {entry.get('path')!r}", None)
                    continue
                if selected_paths is not None and relative not in selected_paths:
                    outcome["skipped"].append(relative)
                    continue
                downloads = entry.get("downloads") or []
                if not downloads:
                    outcome["skipped"].append(relative)
                    continue
                candidates.append((relative, downloads[0], entry.get("hashes") or {},
                                   entry.get("fileSize", 0)))

        total = max(1, len(candidates))
        for index_, (relative, url, hashes, size) in enumerate(candidates):
            destination = os.path.join(instance_dir, relative)
            base_fraction = 0.2 + 0.75 * (index_ / total)
            _report(progress, f"Installation de {relative} ({index_ + 1}/{total})…", base_fraction)
            if download_file(url, destination, progress=None,
                             label=os.path.basename(relative), expected_size=size,
                             expected_sha1=hashes.get("sha1", "")):
                outcome["installed"].append(relative)
            else:
                outcome["skipped"].append(relative)

        _report(progress, f"Modpack installé ({len(outcome['installed'])} fichier(s)).", 1.0)
        return outcome
    except (OSError, zipfile.BadZipFile) as e:
        outcome["error"] = f"Archive illisible: {e}"
        _report(progress, outcome["error"], None)
        return outcome
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def get_modpack_optional_files(project_id: str, version_id: Optional[str] = None) -> List[dict]:
    """Optional files of a modpack, for a "choose the optional mods" dialog."""
    versions = get_available_project_versions(project_id)
    if not versions:
        return []
    version_data = get_version_from_id(version_id) if version_id else versions[0]
    if not isinstance(version_data, dict):
        return []
    pack_file = pick_primary_file(version_data)
    if not pack_file:
        return []
    tmp_dir = tempfile.mkdtemp(prefix="mclaunch-mrpack-")
    archive_path = os.path.join(tmp_dir, pack_file["filename"])
    optional = []
    try:
        if not download_file(pack_file["url"], archive_path, label=pack_file["filename"]):
            return []
        with zipfile.ZipFile(archive_path) as archive:
            index = json.loads(archive.read("modrinth.index.json").decode("utf-8"))
        for entry in index.get("files", []):
            env = entry.get("env") or {}
            if env.get("client") == "optional":
                optional.append({"path": entry.get("path", ""), "size": entry.get("fileSize", 0)})
    except Exception:  # noqa: BLE001 - optional files are a nice-to-have
        return []
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return optional


# ===== INSTALLED MODS: LISTING, ENABLE/DISABLE, DELETION =====

#: Suffix appended to a mod file to disable it without deleting it.
DISABLED_SUFFIX = ".disabled"

#: Mod file suffixes understood by the launcher (disabled files included).
MOD_FILE_SUFFIXES = (".jar", ".zip", ".jar.disabled", ".zip.disabled")


def is_disabled_mod_file(file_name: str) -> bool:
    """True if `file_name` is a mod disabled by the launcher (``mod.jar.disabled``)."""
    return str(file_name or "").lower().endswith(DISABLED_SUFFIX)


def enabled_mod_name(file_name: str) -> str:
    """Name of the mod without the ``.disabled`` suffix."""
    name = str(file_name or "")
    return name[:-len(DISABLED_SUFFIX)] if is_disabled_mod_file(name) else name


def format_size(size) -> str:
    """Human readable file size ("1.2 Mo")."""
    try:
        value = float(size or 0)
    except (TypeError, ValueError):
        return "?"
    if value < 1024:
        return f"{value:.0f} o"
    for unit in ("Ko", "Mo", "Go"):
        value /= 1024
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} To"


def list_mods_for_deletion(mods_dir: str) -> List[str]:
    """Every mod file of a `mods` folder, sorted by name.

    Only regular files living *directly* inside `mods_dir` are returned: a directory is
    never listed, so the deletion code can never be pointed at a folder by mistake.
    """
    if not os.path.isdir(mods_dir):
        return []
    names = []
    for name in os.listdir(mods_dir):
        if not name.lower().endswith(MOD_FILE_SUFFIXES):
            continue
        full_path = os.path.join(mods_dir, name)
        if os.path.isdir(full_path) and not os.path.islink(full_path):
            continue
        names.append(name)
    return sorted(names, key=str.casefold)


def resolve_mod_path(mods_dir: str, file_name: str) -> str:
    """Absolute path of `file_name` inside `mods_dir`, or raise `ValueError`.

    The names come from links embedded in the HTML pages, so they are treated as
    untrusted input: a name containing a path separator, ``..``, a NUL byte, or that
    resolves outside the profile's `mods` folder is rejected before any file operation.
    """
    name = str(file_name or "").strip()
    if (not name or name in (".", "..") or name != os.path.basename(name)
            or "/" in name or "\\" in name or "\x00" in name):
        raise ValueError(f"nom de fichier invalide : {file_name!r}")
    mods_root = os.path.abspath(mods_dir)
    path = os.path.abspath(os.path.join(mods_root, name))
    if os.path.dirname(path) != mods_root:
        raise ValueError(f"chemin en dehors du dossier de mods : {file_name!r}")
    return path


def delete_mod(mods_dir: str, file_name: str) -> str:
    """Delete one mod file; returns its name. Raises `OSError`/`ValueError` on failure."""
    path = resolve_mod_path(mods_dir, file_name)
    if not os.path.lexists(path):
        raise FileNotFoundError(f"fichier introuvable : {file_name}")
    if os.path.isdir(path) and not os.path.islink(path):
        raise IsADirectoryError(f"dossier refusé : {file_name}")
    os.remove(path)
    return os.path.basename(path)


def delete_mods(mods_dir: str, file_names: Sequence[str]) -> Tuple[List[str], List[str]]:
    """Delete several mod files; returns ``(deleted, errors)``.

    Deletion goes on after a failure, so one locked file cannot stop the rest without the
    user knowing exactly which files were refused.
    """
    deleted: List[str] = []
    errors: List[str] = []
    for name in file_names:
        try:
            deleted.append(delete_mod(mods_dir, name))
        except (OSError, ValueError) as e:
            errors.append(f"{name} : {e}")
    return deleted, errors


def set_mod_enabled(mods_dir: str, file_name: str, enabled: bool) -> str:
    """Enable/disable a mod by removing or adding the ``.disabled`` suffix.

    Disabling is the reversible alternative to deleting a mod: the file stays in the
    profile but is ignored by Minecraft. Returns the new file name.
    """
    path = resolve_mod_path(mods_dir, file_name)
    if not os.path.lexists(path):
        raise FileNotFoundError(f"fichier introuvable : {file_name}")
    current = os.path.basename(path)
    if enabled == (not is_disabled_mod_file(current)):
        return current
    target = enabled_mod_name(current) if enabled else current + DISABLED_SUFFIX
    target_path = resolve_mod_path(mods_dir, target)
    if os.path.lexists(target_path):
        raise FileExistsError(f"un fichier nommé {target} existe déjà")
    os.replace(path, target_path)
    return target


def set_mods_enabled(mods_dir: str, file_names: Sequence[str],
                     enabled: bool) -> Tuple[List[str], List[str]]:
    """Enable/disable several mods; returns ``(renamed, errors)``."""
    renamed: List[str] = []
    errors: List[str] = []
    for name in file_names:
        try:
            renamed.append(set_mod_enabled(mods_dir, name, enabled))
        except (OSError, ValueError) as e:
            errors.append(f"{name} : {e}")
    return renamed, errors


def file_sha1(path: str, chunk_size: int = 1 << 20) -> str:
    """SHA-1 hash of a file, read in chunks so a big mod does not fill the memory."""
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def identify_hashes(hashes: Sequence[str], timeout: int = DEFAULT_TIMEOUT) -> Tuple[dict, str]:
    """Ask Modrinth which version published each file hash.

    Uses ``POST /version_files`` with ``algorithm: "sha1"``, which returns a map from
    hash to version object. Returns ``(map, error)``: identifying the files is best
    effort, so an unreachable Modrinth yields an empty map plus a message instead of
    preventing the folder from being displayed.
    """
    wanted = [h for h in hashes if h]
    if not wanted:
        return {}, ""
    try:
        response = requests.post(f"{MODRINTH_API}/version_files",
                                 json={"hashes": wanted, "algorithm": "sha1"},
                                 headers={"User-Agent": USER_AGENT}, timeout=timeout)
    except requests.RequestException as e:
        return {}, f"Modrinth injoignable : {e}"
    if response.status_code != 200:
        return {}, f"Erreur HTTP {response.status_code}"
    try:
        data = response.json()
    except ValueError as e:
        return {}, f"Réponse invalide : {e}"
    return (data if isinstance(data, dict) else {}), ""


def installed_mods_info(mods_dir: str, identify: bool = True) -> dict:
    """Describe every mod file of a profile's `mods` folder.

    Returns ``{"mods": [...], "unknown": n, "error": str}``. Each entry carries the file
    name, its size, whether it is enabled and, when Modrinth recognises the file, the
    project it comes from (title, icon) plus the version and its game versions/loaders.
    """
    entries = []
    for name in list_mods_for_deletion(mods_dir):
        path = os.path.join(mods_dir, name)
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        entries.append({
            "file_name": name,
            "path": path,
            "size": size,
            "enabled": not is_disabled_mod_file(name),
            "sha1": "",
            "project_id": "",
            "title": "",
            "version_name": "",
            "version_number": "",
            "version_type": "",
            "game_versions": [],
            "loaders": [],
            "icon_url": "",
        })

    error = ""
    if identify and entries:
        for entry in entries:
            try:
                entry["sha1"] = file_sha1(entry["path"])
            except OSError as e:
                print(f"[mods] hash impossible pour {entry['file_name']}: {e}")
        versions, error = identify_hashes([entry["sha1"] for entry in entries])
        for entry in entries:
            version = versions.get(entry["sha1"])
            if not isinstance(version, dict):
                continue
            entry["project_id"] = str(version.get("project_id") or "")
            entry["version_name"] = str(version.get("name") or "")
            entry["version_number"] = str(version.get("version_number") or "")
            entry["version_type"] = str(version.get("version_type") or "")
            entry["game_versions"] = list(version.get("game_versions") or [])
            entry["loaders"] = list(version.get("loaders") or [])

        # The version object carries the project id, not its title: one extra request per
        # chunk of projects gives the real name and icon of each installed mod.
        project_ids = sorted({entry["project_id"] for entry in entries if entry["project_id"]})
        for start in range(0, len(project_ids), 100):
            for project in get_projects(project_ids[start:start + 100]):
                if not isinstance(project, dict):
                    continue
                for entry in entries:
                    if entry["project_id"] == project.get("id"):
                        entry["title"] = str(project.get("title") or "")
                        entry["icon_url"] = str(project.get("icon_url") or "")

    for entry in entries:
        if not entry["title"]:
            entry["title"] = entry["version_name"] or enabled_mod_name(entry["file_name"])

    return {"mods": entries,
            "unknown": sum(1 for entry in entries if not entry["project_id"]),
            "error": error}


def _installed_mod_card_html(mod: dict) -> str:
    """One row of the installed-mods page: metadata + enable/disable/delete buttons."""
    file_name = str(mod.get("file_name") or "")
    enabled = bool(mod.get("enabled", True))
    title = str(mod.get("title") or enabled_mod_name(file_name))
    link_name = urllib.parse.quote(file_name, safe="")

    meta = [_escape(format_size(mod.get("size")))]
    if mod.get("version_number"):
        meta.append("version " + _escape(str(mod["version_number"])))
    if mod.get("game_versions"):
        versions = ", ".join(str(v) for v in list(mod["game_versions"])[:6])
        meta.append("Minecraft " + _escape(versions))
    if mod.get("loaders"):
        meta.append("loaders " + _escape(", ".join(str(l) for l in mod["loaders"])))

    badges = [] if enabled else ['<span class="badge off">désactivé</span>']
    badges.append(f'<span class="badge">{_escape(str(mod["version_type"]))}</span>'
                  if mod.get("version_type") else "")
    badges.append('<span class="badge">Modrinth</span>' if mod.get("project_id")
                  else '<span class="badge">non reconnu</span>')
    badges = [badge for badge in badges if badge]

    icon = str(mod.get("icon_url") or "")
    if icon:
        icon_html = f'<img class="icon" src="{_escape(icon)}" alt="">'
    else:
        # No URL to show: an empty framed box is nicer than a broken-image placeholder
        # (the embedded view has JavaScript disabled, so an onerror fallback never runs).
        icon_html = '<div class="icon"></div>'

    buttons = []
    if mod.get("project_id"):
        buttons.append(f'<a class="btn secondary" href="'
                       f'{_action("detail", str(mod["project_id"]))}">Fiche Modrinth</a>')
    buttons.append(f'<a class="btn secondary" href="{_action("togglemod", link_name)}">'
                   f'{"Activer" if not enabled else "Désactiver"}</a>')
    buttons.append(f'<a class="btn warn" href="{_action("delmod", link_name)}">Supprimer</a>')

    style = "" if enabled else ' style="border-left:3px solid #6b5a1e"'
    return f"""
<div class="card"{style}>
  <div class="row">
    {icon_html}
    <div style="flex:1">
      <div class="title">{_escape(title)}</div>
      <div class="meta">{_escape(file_name)} &middot; {" &middot; ".join(meta)} {" ".join(badges)}</div>
      <div>{" ".join(buttons)}</div>
    </div>
  </div>
</div>"""


def installed_mods_html(mods_dir: str, target_profile: str = "",
                        mods: Sequence[dict] = (), unknown: int = 0,
                        notice: str = "", error: str = "") -> str:
    """Page listing the mods installed in a profile, each with delete/disable buttons."""
    mods = list(mods or ())
    disabled = sum(1 for mod in mods if not mod.get("enabled"))
    total_size = sum(int(mod.get("size") or 0) for mod in mods)

    parts = [f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><title>Mods installés</title>
<style>{_HTML_STYLE}</style></head><body>
<div class="toolbar">
  <a class="btn secondary" href="{_action('home', '')}">Accueil</a>
  <a class="btn secondary" href="{_action('search', '')}">Recherche</a>
  <a class="btn secondary" href="{_action('installed', '')}">Actualiser la liste</a>
  <a class="btn secondary" href="{_action('openmods', '')}">Ouvrir le dossier</a>
</div>
<div class="toolbar">Profil ciblé : <strong>{_escape(target_profile or "aucun")}</strong><br>
  <code>{_escape(mods_dir)}</code><br>
  {len(mods)} fichier(s) &middot; {disabled} désactivé(s) &middot; {_escape(format_size(total_size))}</div>"""]

    if notice:
        parts.append(f'<div class="notice">{_escape(notice)}</div>')
    if error:
        parts.append(f'<div class="notice">Identification Modrinth impossible : '
                     f'{_escape(error)}</div>')
    if unknown:
        parts.append(f'<div class="notice">{unknown} fichier(s) non reconnu(s) par Modrinth '
                     f"(mods venant d'ailleurs, ou version modifiée).</div>")

    if len(mods) > 1:
        bulk = [f'<a class="btn secondary" href="{_action("togglemod-all", "off")}">'
                f'Tout désactiver</a>',
                f'<a class="btn secondary" href="{_action("togglemod-all", "on")}">'
                f'Tout activer</a>']
        if disabled:
            bulk.append(f'<a class="btn warn" href="{_action("delmod-disabled", "")}">'
                        f'Supprimer les {disabled} désactivé(s)</a>')
        bulk.append(f'<a class="btn warn" href="{_action("delmod-all", "")}">'
                    f'Tout supprimer…</a>')
        parts.append('<div class="toolbar">' + " ".join(bulk) + "</div>")

    if not mods:
        parts.append('<div class="empty">Aucun mod installé dans ce profil.</div>')

    for mod in mods:
        parts.append(_installed_mod_card_html(mod))

    parts.append("</body></html>")
    return "".join(parts)


def confirm_delete_html(mods_dir: str, scope: str, names: Sequence[str],
                        target_profile: str = "") -> str:
    """Confirmation page shown before a bulk deletion.

    The embedded view has no JavaScript, so the confirmation is a second page whose link
    carries the ``ok`` argument: a single mis-click can therefore never wipe a folder.
    """
    names = list(names)
    if scope == "all":
        title = f"Supprimer les {len(names)} mod(s) de ce profil ?"
        confirmed = _action("delmod-all", "ok")
    else:
        title = f"Supprimer les {len(names)} mod(s) désactivé(s) ?"
        confirmed = _action("delmod-disabled", "ok")

    listing = "".join(f"<li>{_escape(name)}</li>" for name in names[:300])
    if len(names) > 300:
        listing += f"<li>… et {len(names) - 300} autre(s)</li>"

    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><title>Confirmation</title>
<style>{_HTML_STYLE}</style></head><body>
<div class="toolbar">
  <a class="btn secondary" href="{_action('installed', '')}">&larr; Revenir à la liste</a>
</div>
<div class="card">
  <div class="title" style="color:#e06c4a">{_escape(title)}</div>
  <div class="meta">Profil : <strong>{_escape(target_profile or "aucun")}</strong> &middot;
    dossier <code>{_escape(mods_dir)}</code></div>
  <div class="notice">La suppression est définitive : les fichiers sont effacés du disque
    (ils pourront être réinstallés depuis Modrinth). Pour seulement neutraliser un mod sans
    le perdre, utilisez « Désactiver », qui renomme le fichier en <code>.disabled</code>.</div>
  <ul>{listing}</ul>
  <div>
    <a class="btn warn" href="{confirmed}">Oui, supprimer définitivement</a>
    <a class="btn secondary" href="{_action('installed', '')}">Non, annuler</a>
  </div>
</div></body></html>"""


# ===== MARKDOWN / HTML RENDERING =====

def _escape(text) -> str:
    return _html.escape(str(text if text is not None else ""))


def markdown_to_html(markdown_text: str) -> str:
    """Convert the markdown used in Modrinth descriptions to HTML.

    Inline HTML present in the source is preserved (Modrinth descriptions use it),
    code blocks and images are handled explicitly.
    """
    if not markdown_text:
        return ""

    html = markdown_text
    code_blocks = []

    def store_code_block(match):
        code_blocks.append(match.group(0))
        return f"__CODE_BLOCK_{len(code_blocks) - 1}__"

    html = re.sub(r"```[a-zA-Z0-9_+-]*\n(.*?)\n?```", store_code_block, html, flags=re.DOTALL)
    html = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)",
                  lambda m: '<img src="' + _escape(m.group(2)) + '" alt="' + _escape(m.group(1)) +
                            '" style="max-width:100%;height:auto;border-radius:8px;margin:12px 0;">',
                  html)
    html = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
                  lambda m: '<a href="' + _escape(m.group(2)) + '">' + m.group(1) + "</a>", html)
    html = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", html)
    html = re.sub(r"^### (.*?)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.*?)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.*?)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*([^*]+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"(?<![\\/])(\*)([^*\n]+?)\1(?!/)", r"<em>\2</em>", html)
    html = re.sub(r"^---+$", '<hr style="border:none;border-top:1px solid #2a2a2a;margin:24px 0;">',
                  html, flags=re.MULTILINE)
    html = re.sub(r"^- (.+?)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"^\d+\. (.+?)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"((?:<li>.*?</li>\s*)+)",
                  lambda m: "<ul>" + m.group(1) + "</ul>", html, flags=re.DOTALL)

    paragraphs = []
    for block in re.split(r"\n{2,}", html):
        stripped = block.strip()
        if not stripped:
            continue
        paragraphs.append(stripped if stripped.startswith("<") else f"<p>{stripped}</p>")
    html = "".join(paragraphs)
    html = re.sub(r"</(h1|h2|h3|ul|hr|pre)>\s*<p>", r"</\1><p>", html)

    for index, block in enumerate(code_blocks):
        match = re.search(r"```([a-zA-Z0-9_+-]*)\n(.*?)\n?```", block, re.DOTALL)
        if match:
            language = match.group(1)
            code = _escape(match.group(2))
            formatted = f'<pre><code class="language-{language}">{code}</code></pre>'
        else:
            formatted = block
        html = html.replace(f"__CODE_BLOCK_{index}__", formatted)
    return html


_HTML_STYLE = """
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
         background: #1e1e1e; color: #e8e8e8; margin: 0; padding: 16px;
         line-height: 1.55; letter-spacing: .2px; }
  a { color: #30b6a2; text-decoration: none; }
  .card { background: #2a2a2a; border: 1px solid #333; border-radius: 8px;
          padding: 12px; margin-bottom: 12px; }
  .row { display: flex; gap: 14px; align-items: flex-start; }
  .icon { width: 96px; height: 96px; border-radius: 8px; flex-shrink: 0;
          border: 1px solid #30b6a2; background: #222; }
  .icon-lg { width: 160px; height: 160px; border-radius: 10px; border: 2px solid #30b6a2; }
  .title { font-size: 1.25rem; font-weight: 700; color: #30b6a2; margin: 0 0 4px 0; }
  .meta { font-size: .78rem; color: #9a9a9a; margin: 2px 0; }
  .desc { font-size: .87rem; color: #cccccc; margin: 6px 0 0 0; }
  .btn { display: inline-block; padding: 7px 14px; border-radius: 6px;
         background: #30b6a2; color: #101010; font-weight: 700; font-size: .8rem;
         margin: 4px 6px 0 0; }
  .btn.secondary { background: transparent; color: #30b6a2; border: 1px solid #30b6a2; }
  .btn.warn { background: #b65530; color: #fff; }
  .toolbar { background: #232323; border-radius: 8px; padding: 10px 12px; margin-bottom: 12px;
             display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .pill { background: #333; border-radius: 12px; padding: 2px 10px; font-size: .72rem; color: #ddd; }
  .badge { font-size: .72rem; border-radius: 4px; padding: 2px 6px; background: #3a3a3a; }
  .badge.off { background: #6b5a1e; color: #f0d99a; }
  h1, h2, h3 { color: #30b6a2; }
  .description { background: #262626; border-radius: 8px; padding: 14px; margin-top: 12px; }
  .description img { max-width: 100%; height: auto; border-radius: 8px; }
  .description code { background: rgba(48,182,162,.12); color: #30b6a2; padding: 1px 5px; border-radius: 4px; }
  .description pre { background: #141414; border: 1px solid #333; border-radius: 6px; padding: 10px; overflow-x: auto; }
  .notice { background: #332c1a; border: 1px solid #6b5a1e; border-radius: 6px; padding: 8px 10px;
            color: #f0d99a; font-size: .82rem; margin-bottom: 12px; }
  .empty { color: #9a9a9a; padding: 24px; text-align: center; }
"""


#: Public alias of the stylesheet used by every generated page.
HTML_STYLE = _HTML_STYLE


def _action(action: str, argument: str) -> str:
    return f"{LINK_SCHEME}://{action}/{_escape(argument)}"


def _icon_html(url, css_class: str) -> str:
    """Icon `<img>`, or an empty framed box when there is no usable URL.

    The embedded HTML view runs with JavaScript disabled, so an `onerror` fallback never
    fires: a project without an icon used to show the broken-image placeholder instead.
    """
    url = str(url or "").strip()
    if not url or not url.lower().startswith(("http://", "https://")):
        return f'<div class="{css_class}"></div>'
    return f'<img class="{css_class}" src="{_escape(url)}" alt="">'


def hit_card_html(hit: dict, project_type: str = "") -> str:
    """HTML card for one search hit, with the launcher action buttons."""
    project_id = hit.get("project_id") or hit.get("slug") or ""
    hit_type = hit.get("project_type") or project_type or "mod"
    versions = hit.get("versions", []) or []
    shown_versions = ", ".join(versions[:8]) + ("…" if len(versions) > 8 else "")
    if hit_type == "modpack":
        extra_button = (f'<a class="btn secondary" href="{_action("new-profile", project_id)}">'
                        f'Créer un profil + installer</a>')
    else:
        extra_button = ""
    return f"""
<div class="card">
  <div class="row">
    <a href="{_action('detail', project_id)}">{_icon_html(hit.get('icon_url'), 'icon')}</a>
    <div style="flex:1">
      <a href="{_action('detail', project_id)}"><div class="title">{_escape(hit.get('title'))}</div></a>
      <div class="meta">Par {_escape(hit.get('author'))} &middot; {int(hit.get('downloads') or 0):,} téléchargements
        &middot; <span class="badge">{_escape(hit_type)}</span></div>
      <div class="desc">{_escape(hit.get('description'))}</div>
      <div class="meta">Versions : {_escape(shown_versions)}</div>
      <div>
        <a class="btn" href="{_action('install', project_id)}">Installer</a>
        <a class="btn secondary" href="{_action('detail', project_id)}">Détails</a>
        <a class="btn secondary" href="{_action('versions', project_id)}">Choisir une version</a>
        {extra_button}
      </div>
    </div>
  </div>
</div>"""


def html_from_hits(hits: Sequence[dict], page: int = 1, per_page: int = 20,
                   total_hits: int = 0, query: str = "", error: str = "",
                   mc_version: str = "", loader: str = "", target_profile: str = "",
                   project_type: str = "") -> str:
    """HTML listing the results of a Modrinth search."""
    parts = [f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><title>Mods &amp; Modpacks</title>
<style>{_HTML_STYLE}</style></head><body>"""]

    if error:
        parts.append(f'<div class="notice">Recherche impossible : {_escape(error)}</div>')

    info = []
    if query:
        info.append(f"Recherche : <strong>{_escape(query)}</strong>")
    if project_type:
        info.append(f"type <span class=\"badge\">{_escape(project_type)}</span>")
    info.append(f"Minecraft : <strong>{_escape(mc_version or 'toutes')}</strong>")
    info.append(f"loader : <strong>{_escape(loader or 'tous')}</strong>")
    if total_hits:
        pages = max(1, (total_hits + per_page - 1) // per_page)
        info.append(f"page {page}/{pages}")
        info.append(f"{total_hits} résultat(s)")
    else:
        info.append(f"{len(hits)} affiché(s)")
    parts.append('<div class="toolbar">' + " &middot; ".join(info) + "</div>")

    if target_profile:
        parts.append('<div class="toolbar">Profil ciblé : <strong>'
                     + _escape(target_profile)
                     + '</strong> &middot; <a href="' + _action("installed", "")
                     + '">voir les mods déjà installés</a> &middot; <a href="'
                     + _action("target", "") + '">changer de profil</a></div>')
    else:
        parts.append('<div class="notice">Aucun profil ciblé : les boutons « Installer » '
                     'vous demanderont dans quel profil installer.</div>')

    if not hits:
        parts.append('<div class="empty">Aucun résultat. Essayez d\'autres mots-clés '
                     'ou changez de version de Minecraft.</div>')

    for hit in hits:
        parts.append(hit_card_html(hit, project_type=project_type))

    parts.append("</body></html>")
    return "".join(parts)


def html_from_project_data(project_data: dict, mc_version: str = "", loader: str = "",
                           version_data: Optional[dict] = None,
                           dependencies: Optional[dict] = None,
                           missing_deps: Optional[Sequence[tuple]] = None,
                           installed: bool = False,
                           target_profile: str = "",
                           warning: str = "",
                           version_count: int = 0) -> str:
    """Detailed page for one project, with install buttons wired to the launcher."""
    if not isinstance(project_data, dict):
        return html_from_hits([], error="Projet introuvable.")

    project_id = project_data.get("id", "")
    project_type = project_data.get("project_type", "mod")
    gallery = project_data.get("gallery") or []
    categories = ", ".join(project_data.get("categories", []) or [])
    loaders = ", ".join(project_data.get("loaders", []) or [])
    game_versions = project_data.get("game_versions") or []
    versions_str = ", ".join(game_versions[-12:]) + ("…" if len(game_versions) > 12 else "")

    parts = [f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><title>{_escape(project_data.get('title'))}</title>
<style>{_HTML_STYLE}</style></head><body>
<div class="toolbar">
  <a class="btn secondary" href="{_action('search', '')}">&larr; Retour à la recherche</a>
  <a class="btn secondary" href="{_action('home', '')}">Accueil</a>
  <a class="btn secondary" href="{_action('site', project_type)}">Voir sur Modrinth</a>
  <span class="pill">{_escape(project_type)}</span>
</div>"""]

    if target_profile:
        parts.append(f'<div class="toolbar">Profil ciblé : <strong>{_escape(target_profile)}</strong>'
                     f' &middot; <a href="{_action("installed", "")}">mods déjà installés</a></div>')
    else:
        parts.append('<div class="notice">Aucun profil ciblé : sélectionnez-en un dans la '
                     'liste en bas à gauche ou via <a href="' + _action("target", "")
                     + '">changer de profil</a>.</div>')
    if installed:
        parts.append('<div class="notice">Ce contenu a été installé dans le profil ciblé.</div>')
    if warning:
        parts.append(f'<div class="notice">{_escape(warning)}</div>')

    if missing_deps:
        names = ", ".join(_escape(dep[1]) for dep in missing_deps)
        parts.append(f'<div class="notice">Dépendances obligatoires manquantes : {names}'
                     f'<br><a class="btn" href="{_action("deps", project_id)}">Installer les dépendances</a></div>')

    if version_data:
        file = pick_primary_file(version_data)
        compatible = mc_version in (version_data.get('game_versions') or []) if mc_version else False
        compatible = compatible and (not loader or loader in (version_data.get('loaders') or []))
        if compatible:
            message = (f"Version compatible avec le profil ciblé : "
                       f"<strong>{_escape(version_data.get('version_number'))}</strong>")
        else:
            message = (f"Version la plus récente : "
                       f"<strong>{_escape(version_data.get('version_number'))}</strong> "
                       f"(publiée pour {_escape(', '.join(version_data.get('game_versions', []) or []))})")
        if file:
            message += f" &middot; {_escape(file['filename'])}"
        parts.append(f'<div class="notice">{message}</div>')
    elif mc_version or loader:
        parts.append(f'<div class="notice">Aucune version publiée pour '
                     f'Minecraft {_escape(mc_version or "?")} / {_escape(loader or "?")}. '
                     f'L\'installation utilisera la dernière version disponible.</div>')

    if project_type == "modpack":
        parts.append('<div class="notice">C\'est un modpack : il sera installé dans une '
                     '<strong>instance isolée</strong> (son propre dossier), pour ne pas '
                     'mélanger ses mods avec votre installation principale.</div>')

    parts.append(f"""
<div class="card">
  <div class="row">
    {_icon_html(project_data.get('icon_url'), 'icon-lg')}
    <div style="flex:1">
      <div class="title" style="font-size:1.8rem">{_escape(project_data.get('title'))}</div>
      <div class="meta">{_escape(project_data.get('description'))}</div>
      <div class="meta">{int(project_data.get('downloads') or 0):,} téléchargements &middot;
        {int(project_data.get('followers') or 0):,} abonnés &middot;
        licence {_escape((project_data.get('license') or {}).get('id', '?'))}</div>
      <div class="meta">Catégories : {_escape(categories or 'N/A')}</div>
      <div class="meta">Mod loaders : {_escape(loaders or 'N/A')}</div>
      <div class="meta">Environnement : client={_escape(project_data.get('client_side'))},
        serveur={_escape(project_data.get('server_side'))}</div>
      <div class="meta">Versions de Minecraft : {_escape(versions_str or 'N/A')}</div>
      <div>
        <a class="btn" href="{_action('install', project_id)}">Installer dans le profil ciblé</a>
        <a class="btn secondary" href="{_action('versions', project_id)}">Toutes les versions{' (' + str(version_count) + ')' if version_count else ''}</a>
        <a class="btn secondary" href="{_action('new-profile', project_id)}">Créer un profil + installer</a>
        <a class="btn secondary" href="{_action('download', project_id)}">Télécharger le fichier</a>
      </div>
    </div>
  </div>
</div>""")

    if dependencies and dependencies.get("projects"):
        items = "".join(
            f'<div class="card"><a href="{_action("detail", dep.get("id", ""))}">'
            f'{_escape(dep.get("title", dep.get("id")))}</a> '
            f'<span class="badge">{_escape(dep.get("project_type", "mod"))}</span></div>'
            for dep in dependencies["projects"])
        parts.append(f'<h2>Dépendances déclarées</h2>{items}')

    body = markdown_to_html(project_data.get("body", "")) or _escape(project_data.get("description", ""))
    parts.append(f'<h2>Description</h2><div class="description">{body}</div>')

    if gallery:
        images = "".join(f'<img src="{_escape(url)}" style="max-width:100%;border-radius:8px;margin:8px 0;">'
                         for url in gallery)
        parts.append(f"<h2>Galerie</h2>{images}")

    parts.append("</body></html>")
    return "".join(parts)


def get_mod_preview_html(project_id: str, mc_version: str = "", loader: str = "") -> str:
    """Fetch a project and render its detail page (used by the CLI helpers)."""
    project_data = get_project_data(project_id)
    if not isinstance(project_data, dict):
        return html_from_hits([], error=f"Projet introuvable: {project_id}")
    version_data = get_latest_version_for(project_id, mc_version, loader)
    return html_from_project_data(project_data, mc_version, loader, version_data)


def save_mod_preview_html(project_id: str, output_file: str = "mod_preview.html",
                          mc_version: str = "", loader: str = "") -> bool:
    """Save the detail page of a project to `output_file`."""
    html = get_mod_preview_html(project_id, mc_version, loader)
    if not html:
        return False
    with open(output_file, "w", encoding="utf-8") as handle:
        handle.write(html)
    print(f"Preview saved to: {output_file}")
    return True


def version_picker_html(project_data: dict, versions: Sequence[dict],
                        mc_version: str = "", loader: str = "") -> str:
    """List every version of a project so the user can choose one.

    The versions published for the targeted profile (same Minecraft version and same
    loader) are listed first and marked; the others are still installable.
    """
    def compatible(version: dict) -> bool:
        if mc_version and mc_version not in (version.get("game_versions") or []):
            return False
        if loader and loader not in [l.lower() for l in (version.get("loaders") or [])]:
            return False
        return True

    versions = list(versions)
    if mc_version or loader:
        versions = ([v for v in versions if compatible(v)] +
                    [v for v in versions if not compatible(v)])

    parts = [f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><title>Versions</title>
<style>{_HTML_STYLE}</style></head><body>
<div class="toolbar"><a class="btn secondary" href="{_action('detail', project_data.get('id', ''))}">&larr; Retour</a>
<a class="btn secondary" href="{_action('home', '')}">Accueil</a>
<span class="pill">{len(versions)} version(s)</span></div>"""]
    if mc_version or loader:
        parts.append(f'<div class="toolbar">Les versions compatibles avec le profil ciblé '
                     f'(Minecraft <strong>{_escape(mc_version or "toutes")}</strong>, loader '
                     f'<strong>{_escape(loader or "tous")}</strong>) sont affichées en premier.</div>')
    for version in versions:
        file = pick_primary_file(version)
        badge = ('<span class="badge">compatible</span>' if mc_version or loader else "")
        if version in versions and (mc_version or loader) and not compatible(version):
            badge = '<span class="badge">non compatible</span>'
        parts.append(f"""
<div class="card">
  <div class="title" style="font-size:1rem">{_escape(version.get('name') or version.get('version_number'))} {badge}</div>
  <div class="meta">{_escape(version.get('version_type'))} &middot;
    {_escape(", ".join(version.get('game_versions', []) or []))} &middot;
    {_escape(", ".join(version.get('loaders', []) or []))}</div>
  <div class="meta">{_escape(file['filename']) if file else 'aucun fichier'}</div>
  <a class="btn" href="{_action('install-version', version.get('id', ''))}">Installer cette version</a>
</div>""")
    if not versions:
        parts.append('<div class="empty">Aucune version publiée.</div>')
    parts.append("</body></html>")
    return "".join(parts)


def installation_report_html(title: str, lines: Sequence[str], success: bool = True) -> str:
    """Small page summarising an installation."""
    colour = "#30b6a2" if success else "#e06c4a"
    body = "".join(f"<li>{_escape(line)}</li>" for line in lines)
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><title>{_escape(title)}</title>
<style>{_HTML_STYLE}</style></head><body>
<div class="card">
  <div class="title" style="color:{colour}">{_escape(title)}</div>
  <ul>{body}</ul>
  <div>
    <a class="btn secondary" href="{_action('search', '')}">Retour à la recherche</a>
    <a class="btn secondary" href="{_action('home', '')}">Accueil</a>
    <a class="btn secondary" href="{_action('installed', '')}">Mods installés</a>
  </div>
</div></body></html>"""


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "search":
        results = search_modrinth_projects(" ".join(sys.argv[2:]) or "sodium", limit=5)
        for hit in results.get("hits", []):
            print(f"- {hit['title']} ({hit['downloads']} dl) [{hit['project_id']}]")
    else:
        print(__doc__)
