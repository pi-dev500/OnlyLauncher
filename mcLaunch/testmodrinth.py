import requests

def search_modrinth_mods(version, search_terms, limit=10, page=1):
    url = "https://api.modrinth.com/v2/search"
    params = {
        "query": search_terms,
        "game_versions": version,
        "limit": limit,
        "offset": (page - 1) * limit
    }
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        mods = response.json()
        return mods
    else:
        return f"Error: {response.status_code}"

# Example usage
version = "1.20"
search_terms = "magic"
limit = 100  # Number of results per page
page = 1    # Page number

mods = search_modrinth_mods(version, search_terms, limit, page)
for mod in mods['hits']:
    print(mod['title'], mod['description'])
print(len(mods["hits"]),"Résultats")
print(mods['hits'][0])