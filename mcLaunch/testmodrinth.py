import requests
import json
# https://docs.modrinth.com/api
def search_modrinth_projects(search_terms, facets=(), index="relevance", limit=100, page=1) -> dict | str:
    url = "https://api.modrinth.com/v2/search"
    params = {
        "query": search_terms,
        "facets":json.dumps(facets),
        "limit": limit,
        "offset": (page - 1) * limit,
        "index": index
    }
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        mods = response.json()
        return mods
    else:
        return f"Error: {response.status_code}"
    
def random_projects(count=100) -> list:
    url = "https://api.modrinth.com/v2/projects_random"
    params = {"count": count}
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        mods = response.json()
        return mods
    else:
        return f"Error: {response.status_code}"
    
def get_project_data(project_id):
    url = f"https://api.modrinth.com/v2/project/{project_id}"
    params = {}
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        mod = response.json()
        return mod
    else:
        return f"Error: {response.status_code}"
    
def get_available_project_versions(project_id, mc_versions=[], loaders=[], featured=False):
    url = f"https://api.modrinth.com/v2/project/{project_id}/version"
    params = {
        "loaders": json.dumps(loaders),
        "game_versions": json.dumps(mc_versions)
        }
    if len(mc_versions)==0:
        del params["game_versions"]
    if len(loaders)==0:
        del params["loaders"]
    response = requests.get(url, params=params) 
    if response.status_code == 200:
        versions = response.json()
        return versions
    else:
        return f"Error: {response.status_code}"
    
def get_project_dependencies(project_id_or_slug) -> dict | str:
    """
    Returns a list of dependencies for a given project.
    output example:
    """
    url = f"https://api.modrinth.com/v2/project/{project_id_or_slug}/dependencies"
    params={}
    response = requests.get(url, params=params) 
    if response.status_code == 200:
        deps = response.json()
        return deps
    else:
        return f"Error: {response.status_code}"
    
def get_version(project_id_or_slug, version_id_or_number) -> dict | str:
    url = f"https://api.modrinth.com/v2/project/{project_id_or_slug}/version/{version_id_or_number}"
    params = {}
    response = requests.get(url, params=params) 
    if response.status_code == 200:
        version = response.json()
        return version
    else:
        return f"Error: {response.status_code}"

def get_version_from_id(version_id) -> dict | str:
    url = f"https://api.modrinth.com/v2/version/{version_id}"
    params = {}
    response = requests.get(url, params=params) 
    if response.status_code == 200:
        version = response.json()
        return version
    else:
        return f"Error: {response.status_code}"


def get_versions_from_ids(version_ids=[])-> list | str:
    url = "https://api.modrinth.com/v2/versions"
    params = {"ids": json.dumps(version_ids)}
    response = requests.get(url, params=params) 
    if response.status_code == 200:
        versions = response.json()
        return versions
    else:
        return f"Error: {response.status_code}"


def html_from_hits(hits):
    import html as _html

    html = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Mods</title>
<style>
  body { font-family: Arial, sans-serif; background-color:#1e1e1e; color:#ffffff; margin:0; padding:20px; }
  .modrinth-style { background-color:#2a2a2a; padding:10px; margin-bottom:12px; height: 160px; }
  .mod-table { width:100%; border-collapse:collapse; }
  .mod-table td { vertical-align:top; padding:8px; }
  .mod-icon { display:block; width:140px; height:140px; }
  .mod-link { display:block; text-decoration:none; color:#ffffff; height:100%; }
  .mod-title { font-size:20px; margin:0 0 6px 0; }
  .author, .download-count, .description, .mc-versions { font-size:13px; color:#aaaaaa; margin:3px 0; }
  .green-button { display:inline-block; padding:8px 14px; background-color:#30b6a2; color:#ffffff; text-decoration:none; border:1px solid #1e7c6e; white-space:nowrap; }
</style>
</head>
<body>
"""

    for hit in hits:
        icon_url = _html.escape(hit.get("icon_url", "https://via.placeholder.com/64"))
        title = _html.escape(hit.get("title", "Untitled"))
        author = _html.escape(hit.get("author", "Unknown"))
        downloads = _html.escape(str(hit.get("downloads", "")))
        description = _html.escape(hit.get("description", ""))
        versions = _html.escape(", ".join(hit.get("versions", [])))
        project_id = _html.escape(hit.get("project_id", ""))

        html += f'''
<div class="modrinth-style">
  <table class="mod-table">
    <tr>
      <td colspan="2" style="padding:0;">
        <a class="mod-link" href="project-preview://{project_id}">
          <table style="width:100%; border-collapse:collapse;">
            <tr>
              <td style="width:72px; padding:8px;">
                <img src="{icon_url}" alt="icon" class="mod-icon">
              </td>
              <td style="padding:8px;">
                <h2 class="mod-title">{title}</h2>
                <div class="author">Par {author}</div>
                <div class="download-count">{downloads} Téléchargements</div>
                <div class="description">{description}</div>
                <div class="mc-versions">Versions compatibles: {versions}</div>
              </td>
            </tr>
          </table>
        </a>
      </td>
      <td style="white-space:nowrap; padding:8px; text-align:right;">
        <a class="green-button" href="modrinth-install://{project_id}">Installer</a>
      </td>
    </tr>
  </table>
</div>
'''

    html += "\n</body>\n</html>\n"
    return html

    
def list_needed_mods(project_id, mc_version="1.21.8", loader="fabric") -> list[tuple[str, str]]:
    version = get_available_project_versions(project_id, mc_versions=[mc_version], loaders=[loader])
    if len(version)==0:
        raise Exception("No versions found for this project")
    #print(version)
    deps = version[0]["dependencies"] # assume first is latest
    needed_mods = [(project_id, version[0]["id"])]
    projs = deps
    for proj in projs:
        needed_mods.append((proj["project_id"], proj["version_id"]))
    return needed_mods

def download_mod(project_id, project_version="latest", mc_version="1.21.8", loader="fabric", output_dir="."):
    if project_version=="latest":
        versions = get_available_project_versions(project_id, mc_versions=[mc_version], loaders=[loader])
        if len(versions)==0:
            raise Exception("No versions found for this project")
        project_version = versions[0]
        #print(versions)
    print(project_version)
    version = get_version(project_id, project_version)
    print(version)