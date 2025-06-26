import requests
import json
import sys
import csv
from typing import Dict, List, Any, Optional
import time

class GitHubAnalyzer:
    
    def __init__(self, token: Optional[str] = None):
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "User-Agent": "GitHub-Repo-Analyzer/1.0"
        })
        
        if token:
            self.session.headers.update({
                "Authorization": f"Bearer {token}"
            })
    
    def get_paginated_data(self, url: str, per_page: int = 100) -> List[Dict[str, Any]]:
        all_data = []
        page = 1
        
        while True:
            params = {"per_page": per_page, "page": page}
            response = self.session.get(url, params=params)
            
            if response.status_code != 200:
                break
                
            data = response.json()
            if not data:
                break
                
            all_data.extend(data)
            
            if len(data) < per_page:
                break
                
            page += 1
            time.sleep(0.1)
        
        return all_data
    
    def get_repo_basic_info(self, owner: str, repo: str) -> Dict[str, Any]:
        url = f"{self.base_url}/repos/{owner}/{repo}"
        response = self.session.get(url)
        
        if response.status_code != 200:
            raise Exception(f"Failed to fetch repository info: {response.status_code}")
        
        return response.json()
    
    def get_contributors(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/repos/{owner}/{repo}/contributors"
        return self.get_paginated_data(url)
    
    def get_issues_count(self, owner: str, repo: str) -> Dict[str, int]:
        open_url = f"{self.base_url}/repos/{owner}/{repo}/issues"
        open_issues = self.get_paginated_data(open_url + "?state=open")
        open_issues = [issue for issue in open_issues if 'pull_request' not in issue]
        
        closed_issues = self.get_paginated_data(open_url + "?state=closed")
        closed_issues = [issue for issue in closed_issues if 'pull_request' not in issue]
        
        return {
            "open": len(open_issues),
            "closed": len(closed_issues),
            "total": len(open_issues) + len(closed_issues)
        }
    
    def get_pulls_count(self, owner: str, repo: str) -> Dict[str, int]:
        open_prs = self.get_paginated_data(f"{self.base_url}/repos/{owner}/{repo}/pulls?state=open")
        closed_prs = self.get_paginated_data(f"{self.base_url}/repos/{owner}/{repo}/pulls?state=closed")
        
        return {
            "open": len(open_prs),
            "closed": len(closed_prs),
            "total": len(open_prs) + len(closed_prs)
        }
    
    def get_releases(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/repos/{owner}/{repo}/releases"
        return self.get_paginated_data(url)
    
    def get_branches(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/repos/{owner}/{repo}/branches"
        return self.get_paginated_data(url)
    
    def get_tags(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/repos/{owner}/{repo}/tags"
        return self.get_paginated_data(url)
    
    def get_community_profile(self, owner: str, repo: str) -> Dict[str, Any]:
        url = f"{self.base_url}/repos/{owner}/{repo}/community/profile"
        response = self.session.get(url)
        
        if response.status_code != 200:
            return {}
        
        return response.json()
    
    def analyze_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        repo_info = self.get_repo_basic_info(owner, repo)
        contributors = self.get_contributors(owner, repo)
        issues_data = self.get_issues_count(owner, repo)
        prs_data = self.get_pulls_count(owner, repo)
        releases = self.get_releases(owner, repo)
        branches = self.get_branches(owner, repo)
        tags = self.get_tags(owner, repo)
        community_profile = self.get_community_profile(owner, repo)
        
        return {
            "repository": {
                "name": repo_info["name"],
                "full_name": repo_info["full_name"],
                "description": repo_info.get("description", ""),
                "url": repo_info["html_url"],
                "created_at": repo_info["created_at"],
                "updated_at": repo_info["updated_at"]
            },
            "metrics": {
                "stars": repo_info["stargazers_count"],
                "forks": repo_info["forks_count"],
                "watchers": repo_info["watchers_count"],
                "total_issues": issues_data["total"],
                "open_issues": issues_data["open"],
                "closed_issues": issues_data["closed"],
                "total_prs": prs_data["total"],
                "open_prs": prs_data["open"],
                "closed_prs": prs_data["closed"],
                "total_releases": len(releases),
                "total_branches": len(branches),
                "total_tags": len(tags),
                "contributor_count": len(contributors)
            },
            "contributors": contributors,
            "branches": [branch["name"] for branch in branches],
            "tags": [tag["name"] for tag in tags],
            "community_profile": community_profile
        }


def save_to_json(analytics: Dict[str, Any], filename: str = None):
    if filename is None:
        filename = f"{analytics['repository']['name']}_analytics.json"
    
    with open(filename, 'w') as f:
        json.dump(analytics, f, indent=2)


def save_to_csv(analytics: Dict[str, Any], filename: str = None):
    if filename is None:
        filename = f"{analytics['repository']['name']}_analytics.csv"
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        
        writer.writerow(['metric', 'value'])
        writer.writerow(['name', analytics['repository']['name']])
        writer.writerow(['full_name', analytics['repository']['full_name']])
        writer.writerow(['description', analytics['repository']['description']])
        writer.writerow(['url', analytics['repository']['url']])
        writer.writerow(['created_at', analytics['repository']['created_at']])
        writer.writerow(['updated_at', analytics['repository']['updated_at']])
        
        for key, value in analytics['metrics'].items():
            writer.writerow([key, value])
        
        writer.writerow(['branches', ';'.join(analytics['branches'])])
        writer.writerow(['tags', ';'.join(analytics['tags'])])
        
        for i, contributor in enumerate(analytics['contributors']):
            writer.writerow([f'contributor_{i+1}_login', contributor['login']])
            writer.writerow([f'contributor_{i+1}_contributions', contributor['contributions']])


def main():
    if len(sys.argv) != 2:
        sys.exit(1)
    
    repo_path = sys.argv[1]
    
    if "/" not in repo_path:
        sys.exit(1)
    
    owner, repo = repo_path.split("/", 1)
    
    import os
    token = os.getenv("GITHUB_TOKEN")
    
    analyzer = GitHubAnalyzer(token)
    
    try:
        analytics = analyzer.analyze_repository(owner, repo)
        save_to_json(analytics)
        save_to_csv(analytics)
        
    except Exception as e:
        sys.exit(1)


if __name__ == "__main__":
    main()
