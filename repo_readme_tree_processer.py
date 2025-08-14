# %%
import os
import json
import time
import yaml
import pandas as pd
from urllib.parse import urlparse
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import requests
from datetime import datetime
from ghapi.all import GhApi
from py_ascii_tree import ascii_tree
from collections import Counter

# %%
#######################
# GitHub Token Manager
#######################

class GitHubTokenManager:
    def __init__(self, token_file: Optional[str] = None):
        self.tokens = []
        self.current_index = 0
        self.lock = Lock()

        if token_file and os.path.exists(token_file):
            self.tokens = self._load_tokens(token_file)
        else:
            token = os.getenv('GITHUB_TOKEN')
            if not token:
                raise ValueError("No GitHub token provided. Set GITHUB_TOKEN env var or provide token_file")
            self.tokens = [token]

        if not self.tokens:
            raise ValueError("No valid tokens found")

        print(f"Loaded {len(self.tokens)} GitHub tokens")

    def _load_tokens(self, token_file: str) -> List[str]:
        tokens = []
        try:
            if token_file.endswith('.yaml') or token_file.endswith('.yml'):
                with open(token_file, 'r') as f:
                    data = yaml.safe_load(f)
                    if 'tokens' in data:
                        for user_data in data['tokens'].values():
                            token = user_data.get('token')
                            expiration = user_data.get('expiration_date')
                            if token and self._is_token_valid(expiration):
                                tokens.append(token)
                    else:
                        raise ValueError("YAML file must have 'tokens' key")
            else:
                with open(token_file, 'r') as f:
                    for line in f:
                        token = line.strip()
                        if token and not token.startswith('#'):
                            tokens.append(token)
        except yaml.YAMLError as e:
            print(f"Error parsing YAML file: {e}")
            print("Trying to load as simple text file...")
            with open(token_file, 'r') as f:
                for line in f:
                    token = line.strip()
                    if token and not token.startswith('#'):
                        tokens.append(token)
        except Exception as e:
            print(f"Error loading token file: {e}")

        return tokens

    def _is_token_valid(self, expiration_date: Optional[str]) -> bool:
        if not expiration_date:
            return True
        try:
            exp_date = datetime.strptime(expiration_date, '%Y-%m-%d')
            return exp_date.date() > datetime.now().date()
        except:
            return True

    def get_token(self) -> str:
        with self.lock:
            token = self.tokens[self.current_index]
            return token

    def rotate_token(self):
        if len(self.tokens) > 1:
            with self.lock:
                self.current_index = (self.current_index + 1) % len(self.tokens)
                print(f"Rotated to token {self.current_index + 1}/{len(self.tokens)}")

# %%
####################
# GitHub API Client
####################

class OptimizedGitHubAPIClient:
    def __init__(self, token_file: Optional[str] = None, max_workers: int = 10):
        self.max_workers = max_workers
        self.token_manager = GitHubTokenManager(token_file)
        self.session_template = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "GitHub-Repo-Analyzer/2.0",
            "X-GitHub-Api-Version": "2022-11-28"
        }

    def _get_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(self.session_template)
        token = self.token_manager.get_token()
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session

    def _handle_rate_limit(self, response: requests.Response) -> bool:
        if response.status_code == 403:
            rate_limit_remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
            if rate_limit_remaining == 0 or 'rate limit exceeded' in response.text.lower():
                print("Rate limit hit, rotating token...")
                self.token_manager.rotate_token()
                return True
        elif response.status_code == 401:
            print("Authentication failed, rotating token...")
            self.token_manager.rotate_token()
            return True
        return False

    def _fetch_endpoint_with_retry(self, endpoint: str, max_retries: int = 3) -> Optional[Any]:
        for attempt in range(max_retries):
            try:
                session = self._get_session()
                response = session.get(endpoint, timeout=30)
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
                elif self._handle_rate_limit(response):
                    continue
                else:
                    print(f"HTTP {response.status_code} for {endpoint}")
                    return None
            except requests.exceptions.RequestException as e:
                print(f"Request error for {endpoint} (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        return None

    def get_repository_endpoints(self, owner: str, repo: str, tree_sha: str) -> List[str]:
        base_url = f"https://api.github.com/repos/{owner}/{repo}"
        return [
            base_url,
            f"{base_url}/contributors",
            f"{base_url}/issues?state=all&per_page=100",
            f"{base_url}/pulls?state=all&per_page=100",
            f"{base_url}/releases",
            f"{base_url}/branches",
            f"{base_url}/tags",
            f"{base_url}/community/profile",
            f"{base_url}/readme",
            f"{base_url}/git/trees/{tree_sha}?recursive=1",
            f"{base_url}/languages",
            f"{base_url}/topics"
        ]

    # Setup "parallel processing"
    def fetch_repository_data(self, owner: str, repo: str) -> Dict[str, Any]:
        base_url = f"https://api.github.com/repos/{owner}/{repo}"
        repo_data = self._fetch_endpoint_with_retry(base_url)
        if not repo_data:
            return {}
        default_branch = repo_data.get("default_branch", "main")

        endpoints = self.get_repository_endpoints(owner, repo, default_branch)
        results = {base_url: repo_data}

        with ThreadPoolExecutor(max_workers=min(len(endpoints), 5)) as executor:
            future_to_endpoint = {
                executor.submit(self._fetch_endpoint_with_retry, endpoint): endpoint
                for endpoint in endpoints
            }
            for future in as_completed(future_to_endpoint):
                endpoint = future_to_endpoint[future]
                try:
                    results[endpoint] = future.result()
                except Exception as e:
                    print(f"Error fetching {endpoint}: {e}")
                    results[endpoint] = None

        return self._structure_repository_data(results, owner, repo)

    # Define the metadata fields to be returned
    def _structure_repository_data(self, raw_data: Dict[str, Any], owner: str, repo: str) -> Dict[str, Any]:
        base_url = f"https://api.github.com/repos/{owner}/{repo}"
    
        repo_data = raw_data.get(base_url, {}) or {}
        contributors = raw_data.get(f"{base_url}/contributors", []) or []
        issues = raw_data.get(f"{base_url}/issues?state=all&per_page=100", []) or []
        pulls = raw_data.get(f"{base_url}/pulls?state=all&per_page=100", []) or []
        releases = raw_data.get(f"{base_url}/releases", []) or []
        branches = raw_data.get(f"{base_url}/branches", []) or []
        tags = raw_data.get(f"{base_url}/tags", []) or []
        community = raw_data.get(f"{base_url}/community/profile", {}) or {}
        readme = raw_data.get(f"{base_url}/readme", {}) or {}
        languages = raw_data.get(f"{base_url}/languages", {}) or {}
        topics = raw_data.get(f"{base_url}/topics", {}) or {}

        actual_issues = [item for item in issues if 'pull_request' not in item]
        open_prs = [item for item in pulls if item.get('state') == 'open']
        closed_prs = [item for item in pulls if item.get('state') == 'closed']

        ## PULLING DOWN THE REPO TREE + CREATE REP SUMMARY 
        ## Proposed Logic: get the default branch, and then find the specific SHA for that branch
        default_branch = repo_data.get("default_branch", "main")

        # Resolve the commit SHA for the default branch
        tree_sha = None
        if branches and isinstance(branches, list):
        # Find the branch object matching the default branch
            branch_info = next((b for b in branches if b.get("name") == default_branch), None)
            if branch_info:
                tree_sha = branch_info.get("commit", {}).get("sha")

        # Fallback if branches endpoint is empty or missing
        if not tree_sha:
            branch_info = raw_data.get(f"{base_url}/branches/{default_branch}", {})
            tree_sha = branch_info.get("commit", {}).get("sha")

        # Fetch the repository tree if we have a SHA
        repo_tree = {}
        if default_branch:
            tree_endpoint = f"{base_url}/git/trees/{default_branch}?recursive=1"
            repo_tree = raw_data.get(tree_endpoint, {}) or {}
            print(f"DEBUG - Using endpoint: {tree_endpoint}")
            print(f"DEBUG - Found in raw_data: {tree_endpoint in raw_data}")
        
        if repo_tree:
            print(f"DEBUG - repo_tree keys: {list(repo_tree.keys())}")
    
        if not isinstance(repo_tree, dict):
            repo_tree = {}

        repo_tree_summary = {
            "exists": bool(repo_tree),
            "file_count": len(repo_tree.get("tree", [])) if repo_tree else 0,
            "total_size": sum(
                item.get("size", 0)
                for item in repo_tree.get("tree", [])
                if item.get("type") == "blob"
            ) if repo_tree else 0,
            "url": repo_tree.get("url") if repo_tree else None
        }

        # Create LLM-friendly tree structure
        llm_tree = []
        if "tree" in repo_tree:
            for entry in repo_tree["tree"]:
                llm_tree.append({
                    "path": entry["path"],
                    "type": entry["type"],   # 'blob' (file) or 'tree' (folder)
                    "size": entry.get("size", 0)
                })

        result = {
            "repository": {
                "owner": owner,
                "name": repo,
                "full_name": repo_data.get("full_name"),
                "description": repo_data.get("description", ""),
                "url": repo_data.get("html_url"),
                "clone_url": repo_data.get("clone_url"),
                "created_at": repo_data.get("created_at"),
                "updated_at": repo_data.get("updated_at"),
                "pushed_at": repo_data.get("pushed_at"),
                "size": repo_data.get("size", 0),
                "default_branch": repo_data.get("default_branch"),
                "language": repo_data.get("language"),
                "license": repo_data.get("license", {}).get("name") if repo_data.get("license") else None,
                "archived": repo_data.get("archived", False),
                "disabled": repo_data.get("disabled", False),
                "private": repo_data.get("private", False)
            },
            "metrics": {
                "stars": repo_data.get("stargazers_count", 0),
                "forks": repo_data.get("forks_count", 0),
                "watchers": repo_data.get("watchers_count", 0),
                "open_issues": repo_data.get("open_issues_count", 0),
                "total_issues": len(actual_issues),
                "open_prs": len(open_prs),
                "closed_prs": len(closed_prs),
                "total_prs": len(pulls),
                "releases_count": len(releases),
                "branches_count": len(branches),
                "tags_count": len(tags),
                "contributors_count": len(contributors)
            },
            "activity": {
                "contributors": [
                    {
                        "login": c.get("login"),
                        "contributions": c.get("contributions", 0),
                     "type": c.get("type")
                    } for c in contributors[:10]
                ],
                "recent_releases": [
                    {
                        "tag_name": r.get("tag_name"),
                        "name": r.get("name"),
                        "published_at": r.get("published_at"),
                        "prerelease": r.get("prerelease", False)
                    } for r in releases[:5]
                ],
                "languages": languages,
                "topics": topics.get("names", []) if isinstance(topics, dict) else []
            },
            "community": {
                "health_percentage": community.get("health_percentage"),
                "description": community.get("description"),
                "documentation": community.get("documentation"),
                "files": community.get("files", {})
            },
            "readme": {
                "exists": bool(readme),
                "size": readme.get("size", 0) if readme else 0,
                "download_url": readme.get("download_url") if readme else None
            },
            "repo_tree": {
                "summary": repo_tree_summary,
                "repo_url": repo_tree.get("url") if repo_tree else None
            }
        }
    
    # Create temporary tree so that we can return the LLM friendly version
        if repo_tree and "tree" in repo_tree:
            result["_temp_tree_data"] = {
                "raw_tree": repo_tree,
                "llm_tree": llm_tree
            }


        return result

    def process_repositories(self, repositories: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        results = []
        failed_repos = []
        print(f"Processing {len(repositories)} repositories with {self.max_workers} workers...")

    # Submit tasks to ThreadPoolExecutor with projectID, owner, repo
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_repo = {
                executor.submit(self.fetch_repository_data, repo_info["owner"], repo_info["repo"]): repo_info
                for repo_info in repositories
            }

            for i, future in enumerate(as_completed(future_to_repo), 1):
                repo_info = future_to_repo[future]
                owner = repo_info["owner"]
                repo = repo_info["repo"]
                project_id = repo_info.get("projectID", "unknown_project")

                try:
                    repo_data = future.result()
                    if repo_data and repo_data.get("repository", {}).get("name"):
                        # Attach projectID to the repo data for grouping later
                        repo_data["projectID"] = project_id
                        results.append(repo_data)
                        print(f"✓ [{i}/{len(repositories)}] Completed: {owner}/{repo} (Project: {project_id})")
                    else:
                        failed_repos.append(repo_info)
                        print(f"✗ [{i}/{len(repositories)}] Failed: {owner}/{repo} (Project: {project_id})")
                except Exception as e:
                    failed_repos.append(repo_info)
                    print(f"✗ [{i}/{len(repositories)}] Error {owner}/{repo} (Project: {project_id}): {e}")

    # Log failed repositories
        if failed_repos:
            print(f"\nFailed to process {len(failed_repos)} repositories:")
            for repo_info in failed_repos:
                print(f"  - {repo_info['owner']}/{repo_info['repo']} (Project: {repo_info.get('projectID', 'unknown')})")

        return results

# %%
########################################
# Misc. Functions
########################################

# Strip url to extract the Owner and Repo names
def extract_owner_and_repo(url: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        url = url.strip().rstrip('/')
        parts = url.split('/')
        if 'github.com' in url:
            github_index = next(i for i, part in enumerate(parts) if 'github.com' in part)
            if github_index + 2 < len(parts):
                owner = parts[github_index + 1]
                repo = parts[github_index + 2]
                if repo.endswith('.git'):
                    repo = repo[:-4]
                return owner, repo
    except (ValueError, IndexError):
        pass
    return None, None

# Read in CSV 

def load_repositories_from_csv(csv_path: str) -> List[Dict[str, Any]]:
    """
    Load repositories from a CSV file containing a 'documentationUrl' column.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = pd.read_csv(csv_path)
    
    # DEBUG: Print CSV info
    print(f"\n=== CSV DEBUG INFO ===")
    print(f"CSV shape: {df.shape}")
    print(f"CSV columns: {df.columns.tolist()}")
    
    # Show first few rows of each column
    for col in df.columns:
        print(f"\nColumn '{col}' - first 3 values:")
        print(f"  {df[col].head(3).tolist()}")
        print(f"  Unique values: {df[col].nunique()}")

    # Ensure a URL column exists
    if 'documentationUrl' in df.columns:
        url_col = 'documentationUrl'
    elif 'url' in df.columns:
        url_col = 'url'
    else:
        raise ValueError("CSV must contain a 'documentationUrl' or 'url' column.")

    repositories = []
    project_ids_assigned = []
    skipped_urls = []

    # Extract owner and repo from each URL
    for idx, row in df.iterrows():
        url = str(row[url_col]).strip()
        if not url or url.lower() == "nan":
            skipped_urls.append(f"Row {idx}: Empty or nan URL")
            continue

        owner, repo = extract_owner_and_repo(url)
        if not owner or not repo:
            skipped_urls.append(f"Row {idx}: Could not extract owner/repo from '{url}'")
            continue
            
        # Debug each projectId assignment
        raw_project_id = row.get('projectId', None)
        if pd.notna(raw_project_id) and str(raw_project_id).strip():
            project_id = str(raw_project_id).strip()
        else:
            project_id = f"{owner}_{repo}"
            
        print(f"Row {idx}: URL='{url}' -> {owner}/{repo}, ProjectID='{project_id}'")
        project_ids_assigned.append(project_id)
        
        repositories.append({
            "projectID": project_id,
            "owner": owner,
            "repo": repo,
            "full_name": f"{owner}/{repo}",
            "source": row.get('Source', None),
            "title": row.get('Title', None)
        })

    # Show skipped URLs
    if skipped_urls:
        print(f"\n=== SKIPPED URLs ({len(skipped_urls)}) ===")
        for skip in skipped_urls:
            print(f"  {skip}")

    # DEBUG: Show projectID distribution
    from collections import Counter
    project_counts = Counter(project_ids_assigned)
    print(f"\n=== PROJECT DISTRIBUTION ===")
    print(f"Total repositories: {len(repositories)}")
    print(f"Unique projects: {len(project_counts)}")
    for project_id, count in project_counts.most_common():
        print(f"  Project '{project_id}': {count} repositories")

    return repositories

def save_all_repo_data(results, repositories_csv_data, output_dir="data"):
    """
    Enhanced debug version of save_all_repo_data
    """
    os.makedirs(output_dir, exist_ok=True)
    failed_repos = []

    print(f"\n=== SAVE DEBUG INFO ===")
    print(f"Input results: {len(results)} repositories")
    print(f"Input CSV data: {len(repositories_csv_data)} repositories")

    # Create lookup: owner/repo -> projectID
    project_lookup = {}
    for csv_repo in repositories_csv_data:
        try:
            repo_full_name = f"{csv_repo['owner']}/{csv_repo['repo']}"
            project_lookup[repo_full_name] = csv_repo.get('projectID', f"fallback_{repo_full_name}")
        except Exception as e:
            print(f"DEBUG: Error processing CSV entry {csv_repo}: {e}")

    print(f"Project lookup created: {len(project_lookup)} entries")

    # Group repositories by projectID
    projects = {}
    for i, repo_data in enumerate(results):
        if not isinstance(repo_data, dict) or "repository" not in repo_data:
            failed_repos.append({"index": i, "error": "Invalid repo_data structure"})
            continue

        owner = repo_data["repository"].get("owner", "unknown")
        name = repo_data["repository"].get("name", "unknown")
        repo_full_name = f"{owner}/{name}"
        project_id = repo_data.get("projectID") or project_lookup.get(repo_full_name, f"fallback_{owner}_{name}")

        print(f"Processing {repo_full_name}: projectID = '{project_id}'")

        if project_id not in projects:
            projects[project_id] = []

        projects[project_id].append({
            "repo_data": repo_data,
            "owner": owner,
            "name": name,
            "original_index": i,
            "project_id": project_id
        })

    print(f"\nGrouped into {len(projects)} projects:")
    for pid, repos in projects.items():
        print(f"  Project '{pid}': {len(repos)} repositories")

    # Save data for each project
    master_index = []
    readme_count = 0
    tree_count = 0
    
    for project_id, repos in projects.items():
        project_dir = os.path.join(output_dir, str(project_id))
        os.makedirs(project_dir, exist_ok=True)

        project_info = {
            "project_id": project_id,
            "repository_count": len(repos),
            "repositories": []
        }

        for repo_idx, repo_info in enumerate(repos, 1):
            repo_data = repo_info["repo_data"]
            owner = repo_info["owner"]
            name = repo_info["name"]

            try:
                # Save metadata
                metadata_path = os.path.join(project_dir, f"{repo_idx:02d}_metadata.json")
                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(repo_data, f, indent=2, ensure_ascii=False)

                repo_entry = {
                    "repo_index": f"{repo_idx:02d}",
                    "owner": owner,
                    "name": name,
                    "full_name": f"{owner}/{name}",
                    "repo_url": repo_data["repository"].get("html_url", ""),
                    "processed_successfully": True
                }

                # Debug README processing
                readme_info = repo_data.get("readme", {})
                print(f"  {owner}/{name} - README info: {readme_info}")
                
                if readme_info.get("download_url"):
                    try:
                        readme_text = fetch_readme_contents(readme_info)
                        readme_path = os.path.join(project_dir, f"{repo_idx:02d}_readme.md")
                        with open(readme_path, "w", encoding="utf-8") as f:
                            f.write(readme_text)
                        repo_entry["has_readme"] = True
                        repo_entry["readme_file"] = f"{repo_idx:02d}_readme.md"
                        readme_count += 1
                        print(f"    ✅ README saved")
                    except Exception as e:
                        repo_entry["has_readme"] = False
                        repo_entry["readme_error"] = str(e)
                        failed_repos.append({"repo": f"{owner}/{name}", "error": f"README error: {e}"})
                        print(f"    ❌ README failed: {e}")
                else:
                    repo_entry["has_readme"] = False
                    print(f"    ⚠️  No README download_url")

                # Debug tree processing
                temp_tree_data = repo_data.pop("_temp_tree_data", None)
                print(f"  {owner}/{name} - Tree data: {bool(temp_tree_data)}")
                
                if temp_tree_data:
                    raw_tree = temp_tree_data.get("raw_tree")
                    if raw_tree:
                        tree_json_path = os.path.join(project_dir, f"{repo_idx:02d}_repo_tree.json")
                        with open(tree_json_path, "w", encoding="utf-8") as f:
                            json.dump(raw_tree, f, indent=2, ensure_ascii=False)
                        repo_entry["tree_json_file"] = f"{repo_idx:02d}_repo_tree.json"

                        if "tree" in raw_tree:
                            paths = [file["path"] for file in raw_tree["tree"]]
                            if paths:
                                ascii_tree_str = ascii_tree(paths)
                                tree_txt_path = os.path.join(project_dir, f"{repo_idx:02d}_repo_tree.txt")
                                with open(tree_txt_path, "w", encoding="utf-8") as f:
                                    f.write(ascii_tree_str)
                                repo_entry["has_tree"] = True
                                repo_entry["tree_file"] = f"{repo_idx:02d}_repo_tree.txt"
                                tree_count += 1
                                print(f"    ✅ Tree saved ({len(paths)} files)")
                            else:
                                repo_entry["has_tree"] = False
                                print(f"    ⚠️  Tree data empty")
                else:
                    repo_entry["has_tree"] = False
                    print(f"    ⚠️  No tree data")

                project_info["repositories"].append(repo_entry)

            except Exception as e:
                failed_repos.append({"repo": f"{owner}/{name}", "error": str(e)})
                print(f"    ❌ Processing failed: {e}")

        master_index.append(project_info)

    # Save master index
    master_index_path = os.path.join(output_dir, "master_index.json")
    with open(master_index_path, "w", encoding="utf-8") as f:
        json.dump(master_index, f, indent=2, ensure_ascii=False)

    # Save failed repos log
    if failed_repos:
        failed_path = os.path.join(output_dir, "failed_repos.json")
        with open(failed_path, "w", encoding="utf-8") as f:
            json.dump(failed_repos, f, indent=2, ensure_ascii=False)

    print(f"\n=== FINAL SUMMARY ===")
    print(f"Projects created: {len(projects)}")
    print(f"Total repositories: {sum(len(r) for r in projects.values())}")
    print(f"READMEs successfully saved: {readme_count}")
    print(f"Trees successfully saved: {tree_count}")
    print(f"Master index saved to: {master_index_path}")

    return master_index, failed_repos


def get_project_content_for_llm(output_dir="data", project_id=None):
    """
    Dynamically combines README and tree files for a specific project for LLM processing.
    Returns the content as strings instead of saving to disk.
    """
    master_index_path = os.path.join(output_dir, "master_index.json")
    
    if not os.path.exists(master_index_path):
        print("Master index not found. Run save_all_repo_data first.")
        return None
    
    with open(master_index_path, "r", encoding="utf-8") as f:
        master_index = json.load(f)
    
    if project_id is None:
        # Return list of available projects
        return [project["project_id"] for project in master_index]
    
    # Find specific project
    for project in master_index:
        if project["project_id"] == project_id:
            project_dir = os.path.join(output_dir, str(project_id))
            
            # Collect all READMEs
            combined_readme = f"# Combined READMEs for Project: {project_id}\n\n"
            combined_readme += f"This project contains {project['repository_count']} repositories.\n\n"
            combined_readme += "=" * 80 + "\n\n"
            
            # Collect all repo trees  
            combined_tree = f"Combined Repository Trees for Project: {project_id}\n\n"
            combined_tree += f"This project contains {project['repository_count']} repositories.\n\n"
            combined_tree += "=" * 80 + "\n\n"
            
            has_readmes = False
            has_trees = False
            
            for repo in project["repositories"]:
                if repo.get("has_readme", False):
                    readme_path = os.path.join(project_dir, repo["readme_file"])
                    if os.path.exists(readme_path):
                        with open(readme_path, "r", encoding="utf-8") as f:
                            readme_content = f.read()
                        
                        combined_readme += f"## Repository {repo['repo_index']}: {repo['full_name']}\n\n"
                        combined_readme += "-" * 60 + "\n\n"
                        combined_readme += readme_content
                        combined_readme += "\n\n" + "=" * 80 + "\n\n"
                        has_readmes = True
                
                if repo.get("has_tree", False):
                    tree_path = os.path.join(project_dir, repo["tree_file"])
                    if os.path.exists(tree_path):
                        with open(tree_path, "r", encoding="utf-8") as f:
                            tree_content = f.read()
                        
                        combined_tree += f"Repository {repo['repo_index']}: {repo['full_name']}\n"
                        combined_tree += "-" * 60 + "\n"
                        combined_tree += tree_content
                        combined_tree += "\n" + "=" * 80 + "\n\n"
                        has_trees = True
            
            return {
                "project_id": project_id,
                "repository_count": project["repository_count"],
                "combined_readme": combined_readme if has_readmes else None,
                "combined_tree": combined_tree if has_trees else None,
                "has_readmes": has_readmes,
                "has_trees": has_trees
            }
    
    print(f"Project '{project_id}' not found.")
    return None

def create_llm_input_for_project(output_dir="data", project_id=None, include_trees=True):
    """
    Creates a single string ready for LLM input combining READMEs and optionally trees.
    """
    content = get_project_content_for_llm(output_dir, project_id)
    if not content:
        return None
    
    llm_input = f"PROJECT: {content['project_id']}\n"
    llm_input += f"Repository Count: {content['repository_count']}\n\n"
    
    if content['has_readmes']:
        llm_input += "READMES:\n"
        llm_input += content['combined_readme'] + "\n"
    
    if include_trees and content['has_trees']:
        llm_input += "REPOSITORY TREES:\n"
        llm_input += content['combined_tree'] + "\n"
    
    return llm_input


def main():
    CSV_PATH = "YOUR_CSV_HERE"
    TOKEN_FILE = "github_tokens.yaml"
    OUTPUT_DIR = "github_data_3"
    MAX_WORKERS = 8

    try:
        print("Loading repositories from CSV...")
        # FIXED: load_repositories_from_csv returns dictionaries, not tuples
        repositories = load_repositories_from_csv(CSV_PATH)
        print(f"Found {len(repositories)} repositories to process")

        client = OptimizedGitHubAPIClient(token_file=TOKEN_FILE, max_workers=MAX_WORKERS)

        start_time = time.time()
    
        results = client.process_repositories(repositories)
        processing_end_time = time.time()

        valid_results = [r for r in results if isinstance(r, dict) and "repository" in r]
        print(f"\nAPI Processing complete: {len(valid_results)}/{len(repositories)} valid repositories")
        print(f"Processing time: {processing_end_time - start_time:.2f} seconds")

        print("\nSaving individual repository data...")
        save_start_time = time.time()
    
        master_index, failed_repos = save_all_repo_data(valid_results, repositories, OUTPUT_DIR)
        save_end_time = time.time()
        print(f"Data saving time: {save_end_time - save_start_time:.2f} seconds")

        total_time = save_end_time - start_time
        successful_projects = len([p for p in master_index if any(r.get('processed_successfully', False) for r in p['repositories'])])
        repos_with_readme = sum(len([r for r in p['repositories'] if r.get('has_readme', False)]) for p in master_index)
        repos_with_tree = sum(len([r for r in p['repositories'] if r.get('has_tree', False)]) for p in master_index)

        print("\n" + "="*60)
        print("PROCESSING SUMMARY")
        print("="*60)
        print(f"Total repositories processed: {len(repositories)}")
        print(f"Successfully processed projects: {successful_projects}")
        print(f"Failed processing: {len(failed_repos)}")
        print(f"Repositories with README: {repos_with_readme}")
        print(f"Repositories with tree data: {repos_with_tree}")
        print(f"\nTotal processing time: {total_time:.2f} seconds")
        print(f"Average time per repository: {total_time / max(1, len(valid_results)):.2f} seconds")

        print(f"\nOutput files:")
        print(f"  • Project folders: {OUTPUT_DIR}/")
        print(f"  • Master index: {OUTPUT_DIR}/master_index.json")
        print(f"  • Individual enumerated files per project")

        if failed_repos:
            print(f"  • Failed repos log: {OUTPUT_DIR}/failed_repos.json")
            print(f"\nWarning: {len(failed_repos)} repositories failed processing")

        available_projects = get_project_content_for_llm(OUTPUT_DIR)
        if available_projects:
            print(f"\n✅ Available projects for LLM annotation:")
            for project in available_projects:
                print(f"  • {project}")
            print(f"\nUse create_llm_input_for_project('{OUTPUT_DIR}', 'project_id') to get content")

    except Exception as e:
        print(f"Fatal error in main(): {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()


