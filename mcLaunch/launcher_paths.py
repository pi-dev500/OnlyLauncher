"""
Filesystem and profile helpers shared by the launcher tabs.

The launcher stores its profiles in `mcLaunch_profiles.json`. A profile is either a
plain string (an official Mojang version name) or a dict:

    {"name": ..., "type": "vanilla|snapshot|forge|fabric|quilt|neoforge|optifine",
     "version": "1.20.1", "loader": "...", "isolated": bool,
     "enable_demo": bool, "enable_multiplayer": bool, "enable_chat": bool,
     "enable_quick_play": bool, "quick_play": {...}}

This module centralises the questions "where do the mods of that profile live?" and
"which Minecraft version / loader does that profile use?", which are needed by the
profile editor, the Mods tab and the modpack installer.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Tuple

from cache_system import mc_directory

#: Loader names understood by `__main__.Myapp.start_mc`.
LOADERS = ("fabric", "quilt", "forge", "neoforge", "optifine")

#: Modpack manifest loader ids -> launcher loader names (kept in sync with modrinthapi)
MODPACK_LOADER_IDS = {
    "fabric-loader": "fabric",
    "quilt-loader": "quilt",
    "forge": "forge",
    "neoforge": "neoforge",
}


def instance_dir_for(profile) -> str:
    """Absolute instance folder of a profile (its `.minecraft`)."""
    if isinstance(profile, dict):
        if profile.get("isolated"):
            return os.path.join(mc_directory, "versions", str(profile.get("name", "profile")))
        return mc_directory
    return mc_directory


def mods_dir_for(profile) -> str:
    """Absolute `mods` folder of a profile."""
    return os.path.join(instance_dir_for(profile), "mods")


def config_dir_for(profile) -> str:
    return os.path.join(instance_dir_for(profile), "config")


def version_and_loader(profile) -> Tuple[Optional[str], str]:
    """Return ``(minecraft_version, loader_name)`` of a profile.

    In the launcher's profile schema the loader *name* is stored in ``type`` (fabric,
    forge, ...) and ``loader`` holds the loader *version* (0.16.0, 65.0.0, ...). Both are
    accepted here so that the mods tab also works with profiles written by hand.
    """
    if isinstance(profile, str):
        return profile, ""
    if isinstance(profile, dict):
        loader = ""
        for candidate in (profile.get("type"), profile.get("loader")):
            text = str(candidate or "").lower()
            if text in LOADERS:
                loader = text
                break
        return profile.get("version"), loader
    return None, ""


def loader_version(profile) -> str:
    """Version of the mod loader of a profile ("0.16.0", "65.0.0", ...), or ""."""
    if not isinstance(profile, dict):
        return ""
    if version_and_loader(profile)[1] == "":
        return ""
    return str(profile.get("loader") or "")


def safe_profile_name(name: str) -> str:
    """Turn any modpack name into something usable as a folder/profile name."""
    cleaned = re.sub(r"[^\w .+\-]", "", str(name or "")).strip().strip(".")
    return cleaned[:48] or "modpack"


def unique_profile_name(base_name: str, existing_names) -> str:
    """`base_name`, `base_name (2)`, `base_name (3)`, ... so that it is unused."""
    existing = {str(n).casefold() for n in existing_names}
    name = base_name
    counter = 2
    while name.casefold() in existing:
        name = f"{base_name} ({counter})"
        counter += 1
    return name


def build_profile(name: str, mc_version: str, loader: str = "", loader_version: str = "",
                  isolated: bool = True, profile_type: Optional[str] = None, **extra) -> dict:
    """Create a profile dict installable by the launcher.

    This is what the Mods tab uses to turn a modpack into a ready-to-launch profile,
    and what the "nouvelle version" button uses for modpack-derived profiles.
    """
    loader = (loader or "").lower()
    if loader not in LOADERS:
        loader = ""
    profile_type = (profile_type or (loader or "vanilla")).lower()
    if profile_type in ("alpha", "beta"):
        profile_type = "snapshot"
    profile = {
        "name": name,
        "type": profile_type,
        "version": mc_version,
        "loader": loader_version if loader else "",
        "isolated": bool(isolated),
        "enable_demo": False,
        "enable_multiplayer": True,
        "enable_chat": True,
        "enable_quick_play": False,
        "quick_play": {},
    }
    profile.update(extra)
    return profile


def ensure_profile_folders(profile) -> str:
    """Create the instance folder of a profile (and its mods folder) and return it."""
    instance = Path(instance_dir_for(profile))
    (instance / "mods").mkdir(parents=True, exist_ok=True)
    return str(instance)


def describe_profile(profile) -> str:
    """Short human readable label, used in logs and status messages."""
    if isinstance(profile, str):
        return profile
    if isinstance(profile, dict):
        mc_version, loader = version_and_loader(profile)
        label = str(profile.get("name") or "?")
        details = str(mc_version or "?")
        if loader:
            details = f"{details} {loader}"
            if profile.get("loader"):
                details = f"{details} {profile['loader']}"
        return f"{label} ({details})"
    return "aucun profil"

def normalize_profile(profile) -> Optional[dict]:
    """Return a *complete* profile dict, whatever the input representation.

    The launcher historically stored profiles either as a plain version name (a str)
    or as a dict with a varying set of keys. Every consumer (launch code, Mods tab,
    profile list) expects a dict, so all of them go through this function.
    """
    if profile is None or profile == "":
        return None
    if isinstance(profile, str):
        profile = {"name": profile, "type": "vanilla", "version": profile, "loader": ""}
    if not isinstance(profile, dict):
        return None
    profile = dict(profile)
    profile.setdefault("name", profile.get("version") or "profil")
    version = profile.get("version") or "latest"
    profile["version"] = version
    profile_type = str(profile.get("type") or "vanilla").lower()
    if profile_type in ("alpha", "beta"):
        profile_type = "snapshot"
    if profile_type not in (("vanilla", "snapshot", "optifine") + LOADERS):
        profile_type = "vanilla"
    profile["type"] = profile_type
    loader = str(profile.get("loader") or "")
    profile["loader"] = loader if profile_type in LOADERS else ""
    profile["isolated"] = bool(profile.get("isolated", False))
    profile["enable_demo"] = bool(profile.get("enable_demo", False))
    profile["enable_multiplayer"] = bool(profile.get("enable_multiplayer", True))
    profile["enable_chat"] = bool(profile.get("enable_chat", True))
    profile["enable_quick_play"] = bool(profile.get("enable_quick_play", False))
    if not isinstance(profile.get("quick_play"), dict):
        profile["quick_play"] = {}
    return profile


def profile_label(profile) -> str:
    """One line description of a profile, e.g. "Fabric 1.21.1 - 1.21.1 fabric 0.16.0"."""
    profile = normalize_profile(profile)
    if profile is None:
        return "aucun profil"
    mc_version, loader = version_and_loader(profile)
    details = str(mc_version or "?")
    if loader:
        details += f" {loader}"
        if profile.get("loader"):
            details += f" {profile['loader']}"
    return f"{profile.get('name')} — {details}"
