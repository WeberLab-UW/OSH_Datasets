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
import logging

# %%
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
class OptimizedGitLabAPIClient:
    
    def __init__(self, token_file: Optional[str] = None, max_workers: int = 10):
        self.max_workers = max_workers
        self.token_manager = GitHubTokenManager(token_file)
        
        self.session_template = {
            "Accept": "application/json",
            "User-Agent": "GitLab-Repo-Analyzer/2.0"
        }
    
    def _get_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(self.session_template)
        
        token = self.token_manager.get_token()
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def _handle_rate_limit(self, response: requests.Response) -> bool:
        if response.status_code == 429:  # GitLab uses 429 for rate limiting
            print("Rate limit hit, waiting...")
            time.sleep(60)  # Wait 1 minute
            return True
        elif response.status_code == 401:
            print("Authentication failed")
            return False
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
    
    def fetch_all_endpoints(self, project_id: str) -> List[str]:
        base_url = f"https://gitlab.com/api/v4/projects/{project_id}"
        return [
            base_url,  # Gets project info
            f"{base_url}/repository/contributors",
            f"{base_url}/issues?state=all&per_page=100",
            f"{base_url}/merge_requests?state=all&per_page=100",  # Fixed missing comma
            f"{base_url}/releases",
            f"{base_url}/repository/branches",
            f"{base_url}/repository/tags",
            f"{base_url}/repository/tree"
        ]

    def fetch_repository_data(self, project_id: str) -> Dict[str, Any]:
        endpoints = self.fetch_all_endpoints(project_id)  # Fixed method name
        results = {}
        
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
        
        return self._structure_repository_data(results, project_id)
    
    def _structure_repository_data(self, raw_data: Dict[str, Any], project_id: str) -> Dict[str, Any]:
        base_url = f"https://gitlab.com/api/v4/projects/{project_id}"

        repo_data = raw_data.get(base_url, {}) or {}
        contributors = raw_data.get(f"{base_url}/repository/contributors", []) or []
        issues = raw_data.get(f"{base_url}/issues?state=all&per_page=100", []) or []
        merge_requests = raw_data.get(f"{base_url}/merge_requests?state=all&per_page=100", []) or []
        releases = raw_data.get(f"{base_url}/releases", []) or []
        branches = raw_data.get(f"{base_url}/repository/branches", []) or []
        tags = raw_data.get(f"{base_url}/repository/tags", []) or []
        tree = raw_data.get(f"{base_url}/repository/tree", []) or []

        return {
            "repository": {
                "name": repo_data.get("name", ""),
                "id": repo_data.get("id", ""),
                "full_name": repo_data.get("path_with_namespace", ""),  # GitLab field
                "description": repo_data.get("description", ""),
                "url": repo_data.get("web_url", ""),
                "clone_url": repo_data.get("ssh_url_to_repo", ""),  # GitLab field
                "http_clone_url": repo_data.get("http_url_to_repo", ""),
                "created_at": repo_data.get("created_at"),
                "updated_at": repo_data.get("last_activity_at"),  # GitLab field
                "size": repo_data.get("statistics", {}).get("repository_size", 0),
                "default_branch": repo_data.get("default_branch"),
                "archived": repo_data.get("archived", False),
                "visibility": repo_data.get("visibility", "private")
            },
            "metrics": {
                "stars": repo_data.get("star_count", 0),  # GitLab field
                "forks": repo_data.get("forks_count", 0),
                "open_issues": repo_data.get("open_issues_count", 0),
                "releases_count": len(releases),
                "branches_count": len(branches),
                "tags_count": len(tags),
                "contributors_count": len(contributors)
            },
            "activity": {
                "contributors": [
                    {
                        "name": c.get("name", ""),
                        "email": c.get("email", ""),
                        "commits": c.get("commits", 0),
                        "additions": c.get("additions", 0),
                        "deletions": c.get("deletions", 0)
                    } for c in contributors[:10]
                ],
                "recent_releases": [
                    {
                        "tag_name": r.get("tag_name"),
                        "name": r.get("name"),
                        "released_at": r.get("released_at"),
                        "description": r.get("description")
                    } for r in releases[:5]
                ]
            },
            "readme": {
                "readme_url": repo_data.get("readme_url", ""),
            },
            "wiki": {
                "wiki_enabled": repo_data.get("wiki_enabled", False),
            },
            "repo_tree": {
                "repo_tree": tree,
            }

        }
    
    def process_repositories(self, project_ids: List[str]) -> List[Dict[str, Any]]:
        results = []
        failed_repos = []
        
        print(f"Processing {len(project_ids)} repositories with {self.max_workers} workers...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_repo = {
                executor.submit(self.fetch_repository_data, project_id): project_id
                for project_id in project_ids
            }
            
            for i, future in enumerate(as_completed(future_to_repo), 1):
                project_id = future_to_repo[future]
                try:
                    repo_data = future.result()
                    if repo_data and repo_data.get("repository", {}).get("name"):
                        results.append(repo_data)
                        print(f"✓ [{i}/{len(project_ids)}] Completed: {project_id}")
                    else:
                        failed_repos.append(project_id)
                        print(f"✗ [{i}/{len(project_ids)}] Failed: {project_id}")
                except Exception as e:
                    failed_repos.append(project_id)
                    print(f"✗ [{i}/{len(project_ids)}] Error {project_id}: {e}")
        
        if failed_repos:
            print(f"\nFailed to process {len(failed_repos)} repositories:")
            for project_id in failed_repos:
                print(f"  - {project_id}")
        
        return results
    
    def save_results(self, results: List[Dict[str, Any]], output_dir: str = "gitlab_data"):
        os.makedirs(output_dir, exist_ok=True)
        
        for repo_data in results:
            repo_info = repo_data.get("repository", {})
            name = repo_info.get("name", "unknown")
            
            filename = f"{name}_data.json"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(repo_data, f, indent=2, ensure_ascii=False)
        
        combined_path = os.path.join(output_dir, "all_repositories_data.json")
        with open(combined_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\nResults saved to {output_dir}/:")
        print(f"  - {len(results)} individual repository files")
        print(f"  - all_repositories_data.json (combined data)")

# %%
def main():
    CSV_PATH = "./osh_test.csv"
    TOKEN_FILE = "gitlab_tokens.yaml" # Use .yaml for gh-tokens-loader or .txt for simple format
    OUTPUT_DIR = "gitlab_data"
    MAX_WORKERS = 8

    try:
        if not os.path.exists(CSV_PATH):
            print(f"Error: File '{CSV_PATH}' not found.")
            return
        df = pd.read_csv(CSV_PATH)
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return
    
    try:
        print("Initializing GitLab API client...")
        client = OptimizedGitLabAPIClient(
            token_file=TOKEN_FILE if os.path.exists(TOKEN_FILE) else None,
            max_workers=MAX_WORKERS
        )

        project_ids = [str(pid) for pid in df["id"].dropna()]
        print(f"Found {len(project_ids)} project IDs to process.")

        start_time = time.time()
        results = client.process_repositories(project_ids)
        end_time = time.time()

        client.save_results(results, OUTPUT_DIR)
        
        print(f"\n{'='*50}")
        print(f"Processing completed in {end_time - start_time:.2f} seconds")
        print(f"Successfully processed: {len(results)}/{len(project_ids)} repositories")
        print(f"Average time per repository: {(end_time - start_time)/len(project_ids):.2f} seconds")
    except Exception as e:
        print(f"Error during processing: {e}")
        
        print("\nToken file format options:")
        print("1. YAML format (github_tokens.yaml):")
        print("   tokens:")
        print("     user1:")
        print("       token: 'ghp_your_token_here'")
        print("       expiration_date: null")
        print("     user2:")
        print("       token: 'ghp_another_token'")
        print("       expiration_date: '2025-12-31'")
        print("\n2. Simple text format (github_tokens.txt):")
        print("   ghp_your_first_token")
        print("   ghp_your_second_token")
        print("\n3. Environment variable:")
        print("   export GITHUB_TOKEN=ghp_your_token")
        print("\nNote: Built-in token management - no external dependencies required!")


if __name__ == "__main__":
    main()


