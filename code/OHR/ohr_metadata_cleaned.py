# %%
import requests
import json
import pandas as pd
from pandas import json_normalize

def fetch_all_ohr_projects(): 
    BASE_URL = "https://gitlab.com/api/v4/groups/ohwr/projects?include_subgroups=true"
    params = {
        "per_page": 100,
        "page": 1
    }

    all_projects = []

    while True:
        response = requests.get(BASE_URL, params=params)
        if response.status_code != 200:
            break
        
        data = response.json()
        if not data:
            break
        
        all_projects.extend(data)
        params["page"] += 1  # Move to next page

    return all_projects

def filter_metadata(all_projects):
    metadata = []
    for project in all_projects: 
        namespace = project.get("namespace", {})
        project_data = {
            "id": project.get("id"),
            "description": project.get("description"),
            "name": project.get("name"),
            "path": project.get("path"),
            "path_with_namespace": project.get("path_with_namespace"),
            "created_at": project.get("created_at"),
            "default_branch": project.get("default_branch"),
            "tag_list": project.get("tag_list"),
            "topics": project.get("topics"),
            "ssh_url_to_repo": project.get("ssh_url_to_repo"),
            "http_url_to_repo": project.get("http_url_to_repo"),
            "web_url": project.get("web_url"),
            "readme_url": project.get("readme_url"),
            "forks_count": project.get("forks_count"),
            "star_count": project.get("star_count"),
            "empty_repo": project.get("empty_repo"),
            "archived": project.get("archived"),
            "visibility": project.get("visibility"),
            "creator_id": project.get("creator_id"),
            "open_issues_count": project.get("open_issues_count"),
            "namespace.id": namespace.get("id"),
            "namespace.name": namespace.get("name"),
            "namespace.path": namespace.get("path"),
            "namespace.kind": namespace.get("kind"),
            "namespace.full_path": namespace.get("full_path"),
            "namespace.parent_id": namespace.get("parent_id"),
            "namespace.web_url": namespace.get("web_url"),
        }

        metadata.append(project_data)

    return metadata

def main():
    all_projects = fetch_all_ohr_projects()
    metadata = filter_metadata(all_projects)
    
    # Convert to DataFrame
    df = json_normalize(metadata)
    
    # Save to CSV
    df.to_csv("OHR_repos_metadata.csv", index=False)
    print(f"Metadata saved to OHR_repos_metadata.csv with {len(df)} entries.")

if __name__ == "__main__":
    main()



