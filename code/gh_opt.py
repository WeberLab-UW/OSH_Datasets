#!/usr/bin/env python3

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
            if rate_limit_remaining == 0:
                print("Rate limit hit, rotating token...")
                self.token_manager.rotate_token()
                return True
            elif 'rate limit exceeded' in response.text.lower():
                print("Rate limit exceeded, rotating token...")
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
    
    def get_repository_endpoints(self, owner: str, repo: str) -> List[str]:
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
            f"{base_url}/contents/README.md",
            f"{base_url}/languages",
            f"{base_url}/topics"
        ]
    
    def fetch_repository_data(self, owner: str, repo: str) -> Dict[str, Any]:
        endpoints = self.get_repository_endpoints(owner, repo)
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
        
        return self._structure_repository_data(results, owner, repo)
    
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
        readme = raw_data.get(f"{base_url}/contents/README.md", {}) or {}
        languages = raw_data.get(f"{base_url}/languages", {}) or {}
        topics = raw_data.get(f"{base_url}/topics", {}) or {}
        
        actual_issues = [item for item in issues if 'pull_request' not in item]
        open_prs = [item for item in pulls if item.get('state') == 'open']
        closed_prs = [item for item in pulls if item.get('state') == 'closed']
        
        return {
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
            }
        }
    
    def process_repositories(self, repositories: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
        results = []
        failed_repos = []
        
        print(f"Processing {len(repositories)} repositories with {self.max_workers} workers...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_repo = {
                executor.submit(self.fetch_repository_data, owner, repo): (owner, repo)
                for owner, repo in repositories
            }
            
            for i, future in enumerate(as_completed(future_to_repo), 1):
                owner, repo = future_to_repo[future]
                try:
                    repo_data = future.result()
                    if repo_data and repo_data.get("repository", {}).get("name"):
                        results.append(repo_data)
                        print(f"✓ [{i}/{len(repositories)}] Completed: {owner}/{repo}")
                    else:
                        failed_repos.append((owner, repo))
                        print(f"✗ [{i}/{len(repositories)}] Failed: {owner}/{repo}")
                except Exception as e:
                    failed_repos.append((owner, repo))
                    print(f"✗ [{i}/{len(repositories)}] Error {owner}/{repo}: {e}")
        
        if failed_repos:
            print(f"\nFailed to process {len(failed_repos)} repositories:")
            for owner, repo in failed_repos:
                print(f"  - {owner}/{repo}")
        
        return results


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


def load_repositories_from_csv(csv_path: str) -> List[Tuple[str, str]]:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    df = pd.read_csv(csv_path)
    
    if 'Owner' in df.columns and 'Repo' in df.columns:
        repositories = [(row['Owner'], row['Repo']) for _, row in df.iterrows()]
    elif 'url' in df.columns or 'URL' in df.columns:
        url_col = 'url' if 'url' in df.columns else 'URL'
        repositories = []
        for _, row in df.iterrows():
            owner, repo = extract_owner_and_repo(row[url_col])
            if owner and repo:
                repositories.append((owner, repo))
    else:
        raise ValueError("CSV must contain either 'Owner'/'Repo' columns or 'url'/'URL' column")
    
    return repositories


def save_results(results: List[Dict[str, Any]], output_dir: str = "github_data"):
    os.makedirs(output_dir, exist_ok=True)
    
    for repo_data in results:
        repo_info = repo_data.get("repository", {})
        owner = repo_info.get("owner", "unknown")
        name = repo_info.get("name", "unknown")
        
        filename = f"{owner}_{name}_data.json"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(repo_data, f, indent=2, ensure_ascii=False)
    
    combined_path = os.path.join(output_dir, "all_repositories_data.json")
    with open(combined_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    summary = {
        "total_repositories": len(results),
        "processing_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "repositories": [
            {
                "owner": repo["repository"]["owner"],
                "name": repo["repository"]["name"],
                "stars": repo["metrics"]["stars"],
                "forks": repo["metrics"]["forks"],
                "language": repo["repository"]["language"]
            } for repo in results
        ]
    }
    
    summary_path = os.path.join(output_dir, "summary.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"\nResults saved to {output_dir}/:")
    print(f"  - {len(results)} individual repository files")
    print(f"  - all_repositories_data.json (combined data)")
    print(f"  - summary.json (overview)")


def main():
    CSV_PATH = "github_owners_repos.csv"
    TOKEN_FILE = "github_tokens.yaml"  # Use .yaml for gh-tokens-loader or .txt for simple format
    OUTPUT_DIR = "github_data"
    MAX_WORKERS = 8
    
    try:
        print("Loading repositories...")
        repositories = load_repositories_from_csv(CSV_PATH)
        print(f"Found {len(repositories)} repositories to process")
        
        print("Initializing GitHub API client...")
        client = OptimizedGitHubAPIClient(
            token_file=TOKEN_FILE if os.path.exists(TOKEN_FILE) else None,
            max_workers=MAX_WORKERS
        )
        
        start_time = time.time()
        results = client.process_repositories(repositories)
        end_time = time.time()
        
        save_results(results, OUTPUT_DIR)
        
        print(f"\n{'='*50}")
        print(f"Processing completed in {end_time - start_time:.2f} seconds")
        print(f"Successfully processed: {len(results)}/{len(repositories)} repositories")
        print(f"Average time per repository: {(end_time - start_time)/len(repositories):.2f} seconds")
        
    except Exception as e:
        print(f"Error in main execution: {e}")
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
        raise


if __name__ == "__main__":
    main()
