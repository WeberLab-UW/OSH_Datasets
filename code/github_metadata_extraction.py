# %%
# from timeout_decorator import timeout
from tempfile import TemporaryDirectory
import subprocess
import os
import pandas as pd
from urllib.parse import urlparse
import re
import os 
import requests
import json
from typing import Dict, List, Any, Optional
from typing import Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

# %%
# This script extracts the owner and repository name from a list of GitHub URLs -- this is needed because using the Git API requires the ower and repo name
def extract_owner_and_repo(url):
    url_parts = url.strip().split('/')
    # this apppoach my be quite brittle, may need to alteratively use regex
    if url_parts[2] == 'github.com':
        owner = url_parts[3]
        repo = url_parts[4]
        return owner,repo
    else:
        return None, None

if __name__ == "__main__":
    # Revise this to take in a csv file of Git urls
    git_repo_urls = [
        "https://github.com/aw/hw-micro3d",
        "https://github.com/ManiacalLabs/AllPixel/wiki",
        "https://github.com/system76/thelio",
        "https://github.com/PiSupply/Pi-Crust/tree/master/hardware/pi-crust-protohat",
        "https://github.com/meganetaaan/stack-chan"
    ]

    extracted_owners_repos = []

    for url in git_repo_urls:
        owner, repo = extract_owner_and_repo(url)
        if owner and repo:
            extracted_owners_repos.append((owner, repo))
        else:
            print(f"Invalid URL: {url}")
    
    #print("Extracted Owners and Repositories:")
    #print(extracted_owners_repos)

    owner_repo_df = pd.DataFrame(extracted_owners_repos, columns=['Owner', 'Repo'])
    print(owner_repo_df)
    owner_repo_df.to_csv('github_owners_repos.csv', index=False)

# %%
# STATUS: This script pulls down the contents of the README.md file from a git repository given the readme_url

# Fetching the README metadata 
def fetch_readme_metadata(readme_url):
    readme_url_response = requests.get(readme_url)
    if readme_url_response.status_code != 200:
        raise Exception(f"Failed to fetch URL: {readme_url}, Status Code: {readme_url_response.status_code}")

    return readme_url_response.text

# Fetching the decoded README contenets using download_url
def fetch_readme_contents(download_url, output_dir):
    download_url_response = requests.get(download_url)

    if download_url_response.status_code != 200:
        raise Exception(f"Failed to fetch URL: {download_url}, Status Code: {download_url_response.status_code}")

    # Save to to local directory
    filename = os.path.join(output_dir, os.path.basename(urlparse(download_url).path))
    with open(filename, 'wb') as file:
        file.write(download_url_response.content)
    print(f"File downloaded and saved to {filename}")
    
    return download_url_response.text

def main():
    # Revise to loop through a series of URLs 
    readme_url = "https://api.github.com/repos/0xCB-dev/0xCB-1337/contents/README.md"
    readme_contents = fetch_readme_metadata(readme_url)
    print(readme_contents)

    readme_dict = json.loads(readme_contents)
    
    # Revise to loop through a series of Readme metadata
    download_url = readme_dict['download_url']
    contents = fetch_readme_contents(download_url, output_dir="./downloads")
    output_dir = "./downloads"
    print(contents)
 
    os.makedirs(output_dir, exist_ok=True)

if __name__ == "__main__":
    main()

# %%
# STATUS: This script fetches metadata from a Git repository given the owner and repository name, and saves the results to a JSON file. The script works properly.

class GitHubAPIClient:
    def __init__(self, token: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "User-Agent": "GitHub-Repo-Analyzer/1.0"
        })
        if token:
            self.session.headers.update({
                "Authorization": f"Bearer {token}"
            })

    # List of endpoints of interest
    def fetch_all_endpoints(self, owner: str, repo: str) -> List[str]:
        return [
            f"https://api.github.com/repos/{owner}/{repo}",
            f"https://api.github.com/repos/{owner}/{repo}/contributors",
            f"https://api.github.com/repos/{owner}/{repo}/issues",
            f"https://api.github.com/repos/{owner}/{repo}/pulls?state=open",
            f"https://api.github.com/repos/{owner}/{repo}/pulls?state=closed",
            f"https://api.github.com/repos/{owner}/{repo}/releases",
            f"https://api.github.com/repos/{owner}/{repo}/branches",
            f"https://api.github.com/repos/{owner}/{repo}/tags",
            f"https://api.github.com/repos/{owner}/{repo}/community/profile",
            f"https://api.github.com/repos/{owner}/{repo}/contents/README.md"
        ]

    # Formatting the endpoints, not a required function 
    def prepare_endpoints(self, owner: str, repo: str) -> List[str]:
        return self.fetch_all_endpoints(owner, repo)

    # Making the API calls using the endpoints
    def _fetch_single_endpoint(self, endpoint: str) -> Any:
        try:
            response = self.session.get(endpoint)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"HTTP {response.status_code} for {endpoint}")
                return None
        except Exception as e:
            print(f"Error fetching {endpoint}: {e}")
            return None

    # Implements concurrent fetching of data from the API 
    def fetch_all_data(self, prepared_endpoints: List[str], concurrent: bool = True) -> Dict[str, Any]:
        results = {}
        if concurrent:
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_endpoint = {
                    executor.submit(self._fetch_single_endpoint, endpoint): endpoint
                    for endpoint in prepared_endpoints
                }
                for future in as_completed(future_to_endpoint):
                    endpoint = future_to_endpoint[future]
                    try:
                        results[endpoint] = future.result()
                    except Exception as e:
                        results[endpoint] = None
                        print(f"Error with {endpoint}: {e}")
        else:
            for endpoint in prepared_endpoints:
                results[endpoint] = self._fetch_single_endpoint(endpoint)
        return results

    # Main function -- plugs in the owner and repo name to the endpoints and fetches the data
    def analyze_repository(self, owner: str, repo: str, concurrent: bool = True) -> Dict[str, Any]:
        prepared_endpoints = self.prepare_endpoints(owner, repo)
        return self.fetch_all_data(prepared_endpoints, concurrent)

    # Structures the API results into the desired format
    def structure_api_results(self, results: Dict[str, Any], owner, repo) -> Dict[str, Any]:
        print(f"[DEBUG] Structuring API results for {owner}/{repo}")
        # print(f"[DEBUG] Top-level keys: {list(results.keys())}")

        try:
            if results is None:
                return {}

            repo_data = results.get(f"https://api.github.com/repos/{owner}/{repo}")
            contributors = results.get(f"https://api.github.com/repos/{owner}/{repo}/contributors")
            issues = results.get(f"https://api.github.com/repos/{owner}/{repo}/issues")
            open_prs = results.get(f"https://api.github.com/repos/{owner}/{repo}/pulls?state=open")
            closed_prs = results.get(f"https://api.github.com/repos/{owner}/{repo}/pulls?state=closed")
            releases = results.get(f"https://api.github.com/repos/{owner}/{repo}/releases")
            branches = results.get(f"https://api.github.com/repos/{owner}/{repo}/branches")
            tags = results.get(f"https://api.github.com/repos/{owner}/{repo}/tags")
            community_profile = results.get(f"https://api.github.com/repos/{owner}/{repo}/community/profile")
            readme = results.get(f"https://api.github.com/repos/{owner}/{repo}/contents/README.md")

            # Structure the results while also handiing missing data
            structured_results = {
                "repository": {
                    "name": repo_data.get("name") if repo_data else None,
                    "full_name": repo_data.get("full_name") if repo_data else None,
                    "description": repo_data.get("description", "") if repo_data else "",
                    "url": repo_data.get("html_url") if repo_data else None,
                    "created_at": repo_data.get("created_at") if repo_data else None,
                    "updated_at": repo_data.get("updated_at") if repo_data else None
                },
                "metrics": {
                    "stars": repo_data.get("stargazers_count") if repo_data else 0,
                    "forks": repo_data.get("forks_count") if repo_data else 0,
                    "watchers": repo_data.get("watchers_count") if repo_data else 0,
                    "total_issues": len(issues) if issues else 0,
                    "open_prs": len(open_prs) if open_prs else 0,
                    "closed_prs": len(closed_prs) if closed_prs else 0,
                    "total_prs": (len(open_prs) if open_prs else 0) + (len(closed_prs) if closed_prs else 0),
                    "total_releases": len(releases) if releases else 0,
                    "total_branches": len(branches) if branches else 0,
                    "total_tags": len(tags) if tags else 0,
                    "contributor_count": len(contributors) if contributors else 0
                },
                "contributors": contributors if contributors else [],
                "branches": [branch["name"] for branch in branches if branch and "name" in branch] if branches else [],
                "tags": tags if tags else [],
                "community_profile": community_profile,
                "readme": readme
            }

            if structured_results["repository"]["name"]:
                return structured_results
            else:
                print(f"[DEBUG] Missing repo_data for {owner}/{repo}")
                return {}

        except Exception as e:
            print(f"Error while structuring API results: {e}")
            return {}

    # Save results to json 
    def save_to_json(self, analytics: Dict[str, Any], filename: str = None):
        if filename is None:
            repo_name = 'repository'
            for endpoint, data in analytics.items():
                if data and isinstance(data, dict) and 'name' in data:
                    repo_name = data['name']
                    break
            filename = f"{repo_name}_results.json"

        with open(filename, 'w') as f:
            json.dump(analytics, f, indent=2)
        print(f"Results saved to {filename}")


def main():
    # This csv contains the owner and repo names of 4 git repositories
    csv_path = "./github_owners_repos.csv"

    try:
        if not os.path.exists(csv_path):
            print(f"Error: File '{csv_path}' not found.")
            return
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return

    client = GitHubAPIClient(token="TOKEN_HERE") 

    git_metadata = []
    output_dir = "downloaded_repo_metadata"
    os.makedirs(output_dir, exist_ok=True)

    for owner, repo in zip(df['Owner'], df['Repo']):
        print(f"Processing Repo: {owner}/{repo}")

        try:
            # Fetch the endpoints and then return only the structured results
            raw_metadata = client.analyze_repository(owner, repo, concurrent=True)
            structured_metadata = client.structure_api_results(raw_metadata, owner, repo)

            if structured_metadata:
                structured_metadata['Owner'] = owner
                structured_metadata['Repo'] = repo
                git_metadata.append(structured_metadata)

                file_path = os.path.join(output_dir, f"{owner}_{repo}_analysis.json")
                with open(file_path, "w") as f:
                    json.dump(structured_metadata, f, indent=2)
            else:
                print(f"No valid data for {owner}/{repo}")

        except Exception as e:
            print(f"Error processing {owner}/{repo}: {e}")
            continue

    # Save structured metadata 
    final_output_path = os.path.join(output_dir, "all_repositories_metadata.json")
    with open(final_output_path, "w") as f:
        json.dump(git_metadata, f, indent=2)
    print(f"All metadata saved to {final_output_path}")


if __name__ == "__main__":
    main()


