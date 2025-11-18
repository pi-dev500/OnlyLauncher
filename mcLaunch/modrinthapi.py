import requests
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import html as _html
import re

# ===== MARKDOWN TO HTML CONVERTER (IMPROVED) =====

def markdown_to_html(markdown_text: str) -> str:
    """
    Convert markdown to HTML with proper handling of images, links, and embedded HTML.
    Supports: headers, bold, italic, links, code blocks, inline code, lists, etc.
    """
    if not markdown_text:
        return ""
    
    html = markdown_text
    
    # Store code blocks to preserve them
    code_blocks = []
    def store_code_block(match):
        code_blocks.append(match.group(0))
        return f"__CODE_BLOCK_{len(code_blocks)-1}__"
    
    # Code blocks (triple backticks) - preserve these first
    html = re.sub(
        r'```[a-z]*\n(.*?)\n```',
        store_code_block,
        html,
        flags=re.DOTALL
    )
    
    # Image markdown ![alt](url) - convert to <img> tags
    html = re.sub(
        r'!\[([^\]]*)\]\(([^)]+)\)',
        r'<img src="\2" alt="\1" style="max-width: 100%; height: auto; border-radius: 8px; margin: 12px 0;">',
        html
    )
    
    # Links [text](url) - convert to <a> tags
    html = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        r'<a href="\2">\1</a>',
        html
    )
    
    # Remove duplicate <a> tags that might be wrapping images (from raw HTML)
    html = re.sub(
        r'<a[^>]*>\s*<a[^>]*>([^<]*)</a>\s*</a>',
        r'<a href="#">\1</a>',
        html
    )
    
    # Inline code (single backticks)
    html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)
    
    # Headers - must be at start of line
    html = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    
    # Bold **text** or __text__
    html = re.sub(r'\*\*([^*]+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'__([^_]+?)__', r'<strong>\1</strong>', html)
    
    # Italic *text* or _text_ (must be careful not to match URLs with underscores)
    html = re.sub(r'(?<!/)(\*)([^*]+?)\1(?!/)', r'<em>\2</em>', html)
    html = re.sub(r'(?<!/)(_)([^_]+?)\1(?!/)', r'<em>\2</em>', html)
    
    # Horizontal rules
    html = re.sub(r'^---+$', r'<hr style="border: none; border-top: 1px solid #2a2a2a; margin: 24px 0;">', html, flags=re.MULTILINE)
    
    # Line breaks (double newline = paragraph break)
    # Split by double newlines first
    paragraphs = re.split(r'\n\n+', html)
    html = ''.join(f'<p>{p}</p>' if p.strip() and not p.strip().startswith('<') else p for p in paragraphs)
    
    # Unordered lists - collect consecutive list items
    html = re.sub(r'^- (.+?)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'(<li>.*?</li>)', lambda m: '<ul>' + m.group(1) + '</ul>', html, flags=re.DOTALL)
    
    # Ordered lists
    html = re.sub(r'^\d+\. (.+?)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'(<li>.*?</li>)', lambda m: '<ol>' + m.group(1) + '</ol>', html, flags=re.DOTALL)
    
    # Remove multiple consecutive <p> tags
    html = re.sub(r'</p>\s*<p>', '</p><p>', html)
    
    # Restore code blocks
    for i, block in enumerate(code_blocks):
        code_match = re.search(r'```([a-z]*)\n(.*?)\n```', block, re.DOTALL)
        if code_match:
            lang = code_match.group(1)
            code = code_match.group(2)
            formatted = f'<pre><code class="language-{lang}">{code}</code></pre>'
        else:
            formatted = block
        html = html.replace(f'__CODE_BLOCK_{i}__', formatted)
    
    return html

# ===== EXISTING FUNCTIONS FROM YOUR CODE =====

def search_modrinth_projects(search_terms, facets=(), index="relevance", limit=100, page=1) -> dict | str:
    url = "https://api.modrinth.com/v2/search"
    params = {
        "query": search_terms,
        "facets": json.dumps(facets),
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
    if len(mc_versions) == 0:
        del params["game_versions"]
    if len(loaders) == 0:
        del params["loaders"]
    response = requests.get(url, params=params) 
    if response.status_code == 200:
        versions = response.json()
        return versions
    else:
        return f"Error: {response.status_code}"
    
def get_project_dependencies(project_id_or_slug) -> dict | str:
    url = f"https://api.modrinth.com/v2/project/{project_id_or_slug}/dependencies"
    params = {}
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

def get_versions_from_ids(version_ids=[]) -> list | str:
    url = "https://api.modrinth.com/v2/versions"
    params = {"ids": json.dumps(version_ids)}
    response = requests.get(url, params=params) 
    if response.status_code == 200:
        versions = response.json()
        return versions
    else:
        return f"Error: {response.status_code}"

# ===== MOD DOWNLOADING AND DEPENDENCY RESOLUTION =====

def resolve_dependencies(project_id: str, mc_version: str = "1.21.8", loader: str = "fabric", 
                        visited: Optional[set] = None) -> List[Tuple[str, str, str, str]]:
    """
    Recursively resolve all dependencies for a mod.
    Returns: List of tuples (project_id, version_id, project_name, file_name)
    """
    if visited is None:
        visited = set()
    
    if project_id in visited:
        return []
    
    visited.add(project_id)
    needed_mods = []
    
    try:
        versions = get_available_project_versions(project_id, mc_versions=[mc_version], loaders=[loader])
        if not versions:
            print(f"Warning: No versions found for {project_id}")
            return []
        
        version_data = versions[0]
        project_data = get_project_data(project_id)
        
        files = version_data.get("files", [])
        if files:
            file_name = files[0]["filename"]
            needed_mods.append((
                project_id,
                version_data["id"],
                project_data.get("name", project_id),
                file_name
            ))
        
        dependencies = version_data.get("dependencies", [])
        for dep in dependencies:
            if dep.get("dependency_type") == "required":
                dep_project_id = dep.get("project_id")
                if dep_project_id and dep_project_id not in visited:
                    sub_deps = resolve_dependencies(dep_project_id, mc_version, loader, visited)
                    needed_mods.extend(sub_deps)
        
    except Exception as e:
        print(f"Error resolving dependencies for {project_id}: {e}")
    
    return needed_mods

def download_version_file(version_data: dict, output_dir: str) -> bool:
    """
    Download a mod file from version data.
    Returns: True if successful, False otherwise
    """
    files = version_data.get("files", [])
    if not files:
        print("No files available for this version")
        return False
    
    primary_file = None
    for file in files:
        if file.get("primary"):
            primary_file = file
            break
    
    if not primary_file:
        primary_file = files[0]
    
    file_url = primary_file.get("url")
    file_name = primary_file.get("filename")
    
    if not file_url or not file_name:
        print("Invalid file data")
        return False
    
    output_path = os.path.join(output_dir, file_name)
    
    try:
        print(f"Downloading {file_name}...")
        response = requests.get(file_url, stream=True)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        print(f"✓ Downloaded: {file_name}")
        return True
    except Exception as e:
        print(f"✗ Failed to download {file_name}: {e}")
        return False

def download_mod_with_dependencies(project_id: str, output_dir: str, 
                                   mc_version: str = "1.21.8", loader: str = "fabric") -> List[str]:
    """
    Download a mod and all its dependencies to the specified folder.
    Returns: List of downloaded file names
    """
    os.makedirs(output_dir, exist_ok=True)
    downloaded_files = []
    
    try:
        print(f"Resolving dependencies for {project_id}...")
        mods_to_download = resolve_dependencies(project_id, mc_version, loader)
        
        if not mods_to_download:
            print("No mods to download")
            return []
        
        print(f"Found {len(mods_to_download)} mod(s) to download\n")
        
        for proj_id, version_id, proj_name, file_name in mods_to_download:
            print(f"Processing: {proj_name}")
            version_data = get_version_from_id(version_id)
            
            if isinstance(version_data, dict):
                if download_version_file(version_data, output_dir):
                    downloaded_files.append(file_name)
            else:
                print(f"✗ Error fetching version data: {version_data}")
        
        print(f"\n✓ Download complete! {len(downloaded_files)} file(s) downloaded.")
        return downloaded_files
        
    except Exception as e:
        print(f"Error downloading mods: {e}")
        return []

# ===== HTML PREVIEW GENERATION (ENHANCED WITH MARKDOWN & SHARP STYLING) =====

def html_from_hits(hits):
    """Generate HTML preview from search hits."""
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

def html_from_project_data(project_data: dict, mc_version: str = "1.21.8", loader: str = "fabric") -> str:
    """
    Generate HTML preview for a single mod with detailed information.
    Includes: markdown-converted description, compatibility, authors, categories, etc.
    Enhanced with sharper styling and modern design.
    """
    project_id = project_data.get("id", "unknown")
    title = _html.escape(project_data.get("title", "Untitled"))
    description = _html.escape(project_data.get("description", "No description"))
    icon_url = _html.escape(project_data.get("icon_url", "https://via.placeholder.com/256"))
    author = _html.escape(project_data.get("author", "Unknown"))
    downloads = project_data.get("downloads", 0)
    
    categories = project_data.get("categories", [])
    categories_str = ", ".join(_html.escape(cat) for cat in categories) if categories else "N/A"
    
    game_versions = project_data.get("game_versions", [])
    versions_str = ", ".join(_html.escape(v) for v in game_versions[-5:]) if game_versions else "N/A"
    
    client_side = project_data.get("client_side", "unknown")
    server_side = project_data.get("server_side", "unknown")
    
    # Convert markdown body to HTML (do NOT escape - we want the HTML)
    body_raw = project_data.get("body", "")
    body_html = markdown_to_html(body_raw) if body_raw else description
    
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    background: #0d0d0d;
    color: #e8e8e8;
    line-height: 1.6;
    letter-spacing: 0.3px;
  }}
  
  .container {{ 
    max-width: 1400px; 
    margin: 0 auto; 
    padding: 24px;
  }}
  
  /* HEADER SECTION */
  .header {{
    background: linear-gradient(135deg, #1a1a1a 0%, #0f0f0f 100%);
    border-radius: 12px;
    padding: 32px;
    margin-bottom: 32px;
    border: 1px solid #2a2a2a;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
  }}
  
  .header-content {{
    display: flex;
    gap: 40px;
    align-items: flex-start;
  }}
  
  .mod-icon {{
    width: 280px;
    height: 280px;
    border-radius: 12px;
    object-fit: cover;
    border: 2px solid #30b6a2;
    box-shadow: 0 12px 32px rgba(48, 182, 162, 0.15);
    flex-shrink: 0;
  }}
  
  .header-info {{
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 20px;
  }}
  
  .title {{
    font-size: 2.8em;
    font-weight: 700;
    color: #30b6a2;
    margin-bottom: 8px;
    letter-spacing: -0.5px;
  }}
  
  .author-info {{
    font-size: 1em;
    color: #a8a8a8;
    font-weight: 400;
  }}
  
  .author-info strong {{
    color: #30b6a2;
  }}
  
  /* STATS GRID */
  .stats {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin: 8px 0;
  }}
  
  .stat {{
    background: rgba(48, 182, 162, 0.08);
    padding: 16px;
    border-radius: 8px;
    border: 1px solid rgba(48, 182, 162, 0.2);
    transition: all 0.3s ease;
  }}
  
  .stat:hover {{
    background: rgba(48, 182, 162, 0.12);
    border-color: rgba(48, 182, 162, 0.4);
  }}
  
  .stat-label {{
    font-size: 0.75em;
    color: #808080;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    font-weight: 600;
    margin-bottom: 8px;
  }}
  
  .stat-value {{
    font-size: 1.6em;
    color: #30b6a2;
    font-weight: 700;
    letter-spacing: -0.3px;
  }}
  
  /* BUTTONS */
  .buttons {{
    display: flex;
    gap: 12px;
    margin-top: 12px;
    flex-wrap: wrap;
  }}
  
  .btn {{
    padding: 12px 28px;
    border: none;
    border-radius: 8px;
    font-size: 0.95em;
    cursor: pointer;
    text-decoration: none;
    display: inline-block;
    font-weight: 600;
    transition: all 0.25s ease;
    letter-spacing: 0.5px;
  }}
  
  .btn-primary {{
    background: #30b6a2;
    color: #0d0d0d;
    border: 2px solid #30b6a2;
  }}
  
  .btn-primary:hover {{
    background: #2a9a8a;
    border-color: #2a9a8a;
    box-shadow: 0 8px 24px rgba(48, 182, 162, 0.25);
  }}
  
  .btn-secondary {{
    background: transparent;
    color: #30b6a2;
    border: 2px solid #30b6a2;
  }}
  
  .btn-secondary:hover {{
    background: rgba(48, 182, 162, 0.1);
    box-shadow: 0 8px 24px rgba(48, 182, 162, 0.15);
  }}
  
  /* COMPATIBILITY SECTION */
  .compatibility {{
    background: linear-gradient(135deg, #1a1a1a 0%, #0f0f0f 100%);
    border-radius: 12px;
    padding: 28px;
    margin-bottom: 32px;
    border: 1px solid #2a2a2a;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
  }}
  
  .compat-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 20px;
    margin-top: 20px;
  }}
  
  .compat-item {{
    background: rgba(48, 182, 162, 0.05);
    padding: 18px;
    border-radius: 8px;
    border: 1px solid rgba(48, 182, 162, 0.15);
    transition: all 0.3s ease;
  }}
  
  .compat-item:hover {{
    background: rgba(48, 182, 162, 0.08);
    border-color: rgba(48, 182, 162, 0.3);
  }}
  
  .compat-label {{
    font-size: 0.75em;
    color: #808080;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    font-weight: 600;
    margin-bottom: 10px;
  }}
  
  .compat-value {{
    font-size: 1em;
    color: #e8e8e8;
    font-weight: 500;
    line-height: 1.5;
  }}
  
  /* DESCRIPTION SECTION */
  .description {{
    background: linear-gradient(135deg, #1a1a1a 0%, #0f0f0f 100%);
    border-radius: 12px;
    padding: 32px;
    margin-bottom: 32px;
    border: 1px solid #2a2a2a;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
  }}
  
  .section-title {{
    font-size: 1.6em;
    font-weight: 700;
    color: #30b6a2;
    margin-bottom: 20px;
    padding-bottom: 12px;
    border-bottom: 2px solid #30b6a2;
    letter-spacing: -0.3px;
  }}
  
  .description-text {{
    color: #d0d0d0;
    line-height: 1.8;
    font-size: 0.95em;
  }}
  
  /* MARKDOWN STYLING */
  .description-text h1,
  .description-text h2,
  .description-text h3 {{
    color: #30b6a2;
    margin: 20px 0 12px 0;
    font-weight: 700;
    letter-spacing: -0.3px;
  }}
  
  .description-text h1 {{ font-size: 1.8em; }}
  .description-text h2 {{ font-size: 1.5em; }}
  .description-text h3 {{ font-size: 1.2em; }}
  
  .description-text p {{
    margin-bottom: 12px;
  }}
  
  .description-text strong {{
    color: #30b6a2;
    font-weight: 700;
  }}
  
  .description-text em {{
    color: #a8d5d0;
    font-style: italic;
  }}
  
  .description-text code {{
    background: rgba(48, 182, 162, 0.1);
    color: #30b6a2;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: "Courier New", monospace;
    font-size: 0.9em;
  }}
  
  .description-text pre {{
    background: #0d0d0d;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 16px;
    overflow-x: auto;
    margin: 16px 0;
  }}
  
  .description-text pre code {{
    background: none;
    color: #30b6a2;
    padding: 0;
  }}
  
  .description-text ul,
  .description-text ol {{
    margin: 12px 0 12px 24px;
  }}
  
  .description-text li {{
    margin-bottom: 8px;
  }}
  
  .description-text a {{
    color: #30b6a2;
    text-decoration: none;
    border-bottom: 1px solid rgba(48, 182, 162, 0.3);
    transition: all 0.2s ease;
  }}
  
  .description-text a:hover {{
    border-bottom-color: #30b6a2;
  }}
  
  .description-text img {{
    max-width: 100%;
    height: auto;
    border-radius: 8px;
    margin: 16px 0;
    display: block;
  }}
  
  .description-text hr {{
    border: none;
    border-top: 1px solid #2a2a2a;
    margin: 24px 0;
  }}
  
  /* FOOTER */
  .footer {{
    text-align: center;
    padding: 24px;
    color: #606060;
    font-size: 0.85em;
    border-top: 1px solid #2a2a2a;
    margin-top: 32px;
  }}
  
  /* RESPONSIVE */
  @media (max-width: 1024px) {{
    .compat-grid {{
      grid-template-columns: 1fr;
    }}
  }}
  
  @media (max-width: 768px) {{
    .header-content {{
      flex-direction: column;
      align-items: center;
      text-align: center;
    }}
    
    .mod-icon {{
      width: 220px;
      height: 220px;
    }}
    
    .title {{
      font-size: 2.2em;
    }}
    
    .stats {{
      grid-template-columns: 1fr;
    }}
    
    .buttons {{
      justify-content: center;
    }}
    
    .header {{
      padding: 24px;
    }}
    
    .description {{
      padding: 20px;
    }}
  }}
</style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="header-content">
        <img src="{icon_url}" alt="{title}" class="mod-icon">
        <div class="header-info">
          <div class="title">{title}</div>
          <div class="author-info">Par <strong>{author}</strong></div>
          
          <div class="stats">
            <div class="stat">
              <div class="stat-label">Téléchargements</div>
              <div class="stat-value">{downloads:,}</div>
            </div>
            <div class="stat">
              <div class="stat-label">Type Client</div>
              <div class="stat-value">{_html.escape(client_side)}</div>
            </div>
            <div class="stat">
              <div class="stat-label">Type Serveur</div>
              <div class="stat-value">{_html.escape(server_side)}</div>
            </div>
          </div>
          
          <div class="buttons">
            <a href="#" class="btn btn-primary">Télécharger</a>
            <a href="#" class="btn btn-secondary">Visiter Modrinth</a>
          </div>
        </div>
      </div>
    </div>
    
    <div class="compatibility">
      <div class="section-title">Compatibilité</div>
      <div class="compat-grid">
        <div class="compat-item">
          <div class="compat-label">Versions Minecraft Supportées</div>
          <div class="compat-value">{versions_str}</div>
        </div>
        <div class="compat-item">
          <div class="compat-label">Catégories</div>
          <div class="compat-value">{categories_str}</div>
        </div>
      </div>
    </div>
    
    <div class="description">
      <div class="section-title">Description</div>
      <div class="description-text">{body_html}</div>
    </div>
  </div>
</body>
</html>
"""
    
    return html

def get_mod_preview_html(project_id: str) -> str:
    """
    Fetch project data and generate an HTML preview with markdown support.
    """
    try:
        print(f"Fetching project data for {project_id}...")
        project_data = get_project_data(project_id)
        
        if isinstance(project_data, str):
            print(f"Error: {project_data}")
            return ""
        
        return html_from_project_data(project_data)
        
    except Exception as e:
        print(f"Error generating preview: {e}")
        return ""

def save_mod_preview_html(project_id: str, output_file: str = "mod_preview.html") -> bool:
    """
    Download project data and save an HTML preview with markdown support.
    """
    try:
        print(f"Fetching project data for {project_id}...")
        project_data = get_project_data(project_id)
        
        if isinstance(project_data, str):
            print(f"Error: {project_data}")
            return False
        
        html_content = html_from_project_data(project_data)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"✓ HTML preview saved to: {output_file}")
        return True
        
    except Exception as e:
        print(f"Error generating preview: {e}")
        return False

# ===== EXAMPLE USAGE =====

if __name__ == "__main__":
    # Example 1: Download a mod with all dependencies
    # download_mod_with_dependencies("fabric-api", "./mods", mc_version="1.21.8", loader="fabric")
    
    # Example 2: Generate HTML preview for a mod
    # save_mod_preview_html("sodium", "sodium_preview.html")
    
    # Example 3: Search for mods and generate preview from hits
    # results = search_modrinth_projects("sodium")
    # if isinstance(results, dict) and "hits" in results:
    #     with open("search_results.html", "w", encoding="utf-8") as f:
    #         f.write(html_from_hits(results["hits"][:10]))
    
    pass
