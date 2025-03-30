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
    
def get_available_project_versions(project_id, mc_versions=[], loaders=[], featured=True):
    url = f"https://api.modrinth.com/v2/project/{project_id}/version"
    params = {
        "loaders": json.dumps(loaders),
        "game_versions": json.dumps(mc_versions),
        "featured": featured
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
    html = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Mods</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background-color: #1e1e1e;
                color: #ffffff;
                margin: 0;
                padding: 20px;
            }
            .modrinth-style {
                background-color: #2a2a2a;
                padding: 15px;
                margin-bottom: 10px;
                display: flex;
                align-items: center;
            }
            
            .mod-icon {
                width: 64px;
                height: 64px;
                margin-right: 15px;
            }
            .mod-content {
                display: flex;
                flex-direction: column;
                width: 100%;
            }
            .install-button {
                display: flex;
                flex-direction: column;
            }
            .mod-header {
                display: flex;
                align-items: center;
            }
            .mod-title {
                font-size: 24px;
                margin: 5px 10px 5px 0;
            }
            .author {
                font-size: 16px;
                color: #aaaaaa;
            }
            .download-count, .description, .mc-versions {
                font-size: 14px;
                color: #aaaaaa;
            }
            .green-button {
                display: inline-block;
                padding: 10px 20px;
                background-color: #30b6a2;
                color: #ffffff;
                text-decoration: none;
                border-radius: 3px;
                transition: background-color 0.3s ease;
            }
            .mod-link {
                text-decoration: none;
                color: #ffffff;
            }
        </style>
    </head>
    <body>
    """

    for hit in hits:
        html += '<div class="modrinth-style">'
        html += f'<img src="{hit["icon_url"]}" class="mod-icon">'
        html += '<div class="mod-content">'
        html += f'<a class="mod-link" href="project-preview://{hit["project_id"]}">'
        html += '<div class="mod-header">'
        html += f'<h2 class="mod-title">{hit["title"]}</h2>'
        html += f'<div class="author">Par {hit["author"]}</div>'
        html += '</div>'  # Close mod-header div
        html += f'<div class="download-count">{hit["downloads"]} Téléchargements</div>'
        html += f'<div class="description">{hit["description"]}</div>'
        html += f'<div class="mc-versions">Versions compatibles: {", ".join(hit["versions"])}</div>'
        html += '</a></div>'  # Close mod-content div
        html += f'<div class="install-button"><a class="green-button" href="modrinth-install://{hit["project_id"]}">Installer</a></div>'
        html += '</div>'  # Close modrinth-style div

    html += """
    </body>
    </html>
    """
    return html
        
    
# Example usage
search_terms = "JEI"
limit = 100  # Number of results per page
page = 1    # Page number
facets = [["versions:1.20"],["project_type:mod"]]
mods = search_modrinth_projects(search_terms, facets, limit=100, page=1)
for mod in mods['hits']:
    print(mod['title'], mod['description'])
    
with open("search_results.html", "w") as f:
    f.write(html_from_hits(mods["hits"]))
print(mods["total_hits"],"Résultats")
print(mods['hits'][0])