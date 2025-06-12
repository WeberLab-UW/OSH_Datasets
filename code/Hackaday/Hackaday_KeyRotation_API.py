#!/usr/bin/env python3

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple
import json
from datetime import datetime

import pandas as pd
import requests
import requests.adapters

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HackadayClient:
    BASE_URL = "https://dev.hackaday.io/v2"
    DEFAULT_TIMEOUT = 30
    MAX_RETRIES = 3
    
    def __init__(
        self, 
        api_keys: List[str], 
        requests_per_hour: int = 900,  # Conservative limit
        max_workers: Optional[int] = None
    ):
        if not api_keys:
            raise ValueError("At least one API key is required")
        
        self.api_keys = api_keys
        self.requests_per_hour = requests_per_hour
        self.min_delay = 4.0 / len(api_keys)  # Conservative delay
        
        # Simple tracking - just count total requests
        self.total_requests = 0
        self.hour_start = time.time()
        self.max_requests_per_hour = len(api_keys) * requests_per_hour
        self.request_lock = threading.Lock()
        
        # Reduce workers significantly
        self.max_workers = max_workers or min(len(api_keys) * 2, 10)
        
        # Simple session
        self.session = requests.Session()
        
        logger.info(f"Initialized client with {len(api_keys)} API keys")
        logger.info(f"Rate limit: {requests_per_hour} requests/hour per key")
        logger.info(f"Combined capacity: {self.max_requests_per_hour} requests/hour")
        logger.info(f"Max workers: {self.max_workers}")

    def _get_next_key(self) -> Optional[str]:
        """Get next API key with simple round-robin"""
        with self.request_lock:
            current_time = time.time()
            
            # Check if we need to reset the hour
            if current_time - self.hour_start >= 3600:
                self.total_requests = 0
                self.hour_start = current_time
                logger.info("Hour reset - request counter reset to 0")
            
            # Check if we're at the limit
            if self.total_requests >= self.max_requests_per_hour:
                wait_time = 3600 - (current_time - self.hour_start)
                if wait_time > 0:
                    logger.warning(f"Hit hourly limit of {self.max_requests_per_hour}. Need to wait {wait_time:.0f} seconds")
                    return None
            
            # Increment counter and return key
            self.total_requests += 1
            key_index = self.total_requests % len(self.api_keys)
            return self.api_keys[key_index]

    def _make_request(self, url: str, retries: int = 0) -> Optional[Dict]:
        if retries >= self.MAX_RETRIES:
            logger.error(f"Max retries exceeded for URL: {url}")
            return None
        
        time.sleep(self.min_delay)
        
        try:
            response = self.session.get(url, timeout=self.DEFAULT_TIMEOUT)
            
            if response.status_code == 429:
                logger.warning(f"Rate limited (429) - waiting 60 seconds")
                time.sleep(60)
                return self._make_request(url, retries + 1)
            
            if response.status_code != 200:
                logger.warning(f"HTTP {response.status_code} for URL: {url}")
                return None
            
            return response.json()
            
        except requests.exceptions.Timeout:
            logger.warning(f"Request timeout, retry {retries + 1}")
            time.sleep(2 ** retries)
            return self._make_request(url, retries + 1)
        except Exception as e:
            logger.error(f"Request error: {e}")
            time.sleep(2 ** retries)
            return self._make_request(url, retries + 1)

    def get_project_links(self, project_id: str) -> Tuple[str, List[str]]:
        api_key = self._get_next_key()
        if not api_key:
            # Hit rate limit
            raise Exception("Rate limit exceeded")
        
        url = f"{self.BASE_URL}/projects/{project_id}/links?api_key={api_key}"
        
        data = self._make_request(url)
        if not data:
            return project_id, []

        try:
            repo_domains = ["github.com", "gitlab.com"]
            repo_links = [
                link.get("url") for link in data
                if link.get("url") and any(domain in link.get("url", "") for domain in repo_domains)
            ]
            return project_id, repo_links
        except Exception as e:
            logger.error(f"Error processing links for project {project_id}: {e}")
            return project_id, []

    def search_projects(self, search_term: str, limit: int = 100) -> List[Dict]:
        all_projects = []
        offset = 0
        
        while True:
            api_key = self._get_next_key()
            if not api_key:
                logger.warning("Hit rate limit during project search")
                break
                
            url = (
                f"{self.BASE_URL}/search?search_term={search_term}"
                f"&limit={limit}&offset={offset}&api_key={api_key}"
            )
            
            data = self._make_request(url)
            if not data:
                break

            projects = data.get("results", [])
            if not projects:
                break

            all_projects.extend(projects)
            offset += limit
            
            logger.info(f"Fetched {len(all_projects)} projects")

        return all_projects

    def process_projects_safely(self, project_ids: List[str], start_index: int = 0) -> Dict[str, List[str]]:
        """Process projects with safe rate limiting"""
        results = {}
        
        logger.info(f"Processing {len(project_ids)} projects starting from index {start_index}")
        
        for i, project_id in enumerate(project_ids[start_index:], start_index):
            try:
                pid, repo_links = self.get_project_links(project_id)
                results[pid] = repo_links
                
                # Progress reporting
                if (i + 1) % 100 == 0:
                    with self.request_lock:
                        rate = self.total_requests / ((time.time() - self.hour_start) / 3600)
                    logger.info(f"Progress: {i+1}/{len(project_ids)} ({(i+1)/len(project_ids)*100:.1f}%) - Rate: {rate:.0f}/hour")
                
            except Exception as e:
                if "Rate limit exceeded" in str(e):
                    logger.warning(f"Hit rate limit at project {i+1}. Waiting 1 hour...")
                    time.sleep(3610)  # Wait just over an hour
                    logger.info("Resuming after rate limit pause...")
                    # Retry this project
                    try:
                        pid, repo_links = self.get_project_links(project_id)
                        results[pid] = repo_links
                    except:
                        logger.error(f"Failed to process project {project_id} after rate limit pause")
                        results[project_id] = []
                else:
                    logger.error(f"Error processing project {project_id}: {e}")
                    results[project_id] = []
        
        return results

    def close(self):
        self.session.close()


class ProjectDataProcessor:
    def __init__(self, client: HackadayClient):
        self.client = client
        self.checkpoint_file = "simple_checkpoint.json"
        self.results_file = "incremental_results.csv"

    def save_checkpoint(self, completed_index: int, total_projects: int) -> None:
        """Save simple checkpoint"""
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'completed_index': completed_index,
            'total_projects': total_projects
        }
        
        try:
            with open(self.checkpoint_file, 'w') as f:
                json.dump(checkpoint_data, f, indent=2)
            logger.info(f"Saved checkpoint: {completed_index}/{total_projects}")
        except Exception as e:
            logger.error(f"Error saving checkpoint: {e}")

    def load_checkpoint(self) -> int:
        """Load checkpoint and return starting index"""
        if not os.path.exists(self.checkpoint_file):
            return 0
            
        try:
            with open(self.checkpoint_file, 'r') as f:
                checkpoint_data = json.load(f)
            
            completed_index = checkpoint_data.get('completed_index', 0)
            logger.info(f"Loaded checkpoint: resuming from index {completed_index}")
            return completed_index
        except Exception as e:
            logger.error(f"Error loading checkpoint: {e}")
            return 0

    def save_incremental_results(self, df: pd.DataFrame, all_results: Dict[str, List[str]], completed_index: int) -> None:
        """Save results incrementally"""
        try:
            df_with_repos = self.add_repo_links_to_dataframe(df, all_results)
            df_with_repos.to_csv(self.results_file, index=False)
            
            self.save_checkpoint(completed_index, len(df))
            
            logger.info(f"Saved incremental results: {len(df_with_repos)} projects with repo links")
        except Exception as e:
            logger.error(f"Error saving incremental results: {e}")

    def load_existing_results(self) -> Dict[str, List[str]]:
        """Load existing results"""
        if not os.path.exists(self.results_file):
            return {}
        
        try:
            df = pd.read_csv(self.results_file)
            results = {}
            
            for _, row in df.iterrows():
                project_id = str(row.get('rid') or row.get('id') or '')
                github_links = row.get('github_links', '')
                
                if github_links and github_links.strip():
                    links = [link.strip() for link in github_links.split(',') if link.strip()]
                    results[project_id] = links
                else:
                    results[project_id] = []
            
            logger.info(f"Loaded {len(results)} existing results")
            return results
        except Exception as e:
            logger.error(f"Error loading existing results: {e}")
            return {}

    def extract_project_ids(self, df: pd.DataFrame) -> List[str]:
        project_ids = []
        for _, row in df.iterrows():
            project_id = row.get('rid') or row.get('id')
            if project_id:
                project_ids.append(str(project_id))
        return project_ids

    def add_repo_links_to_dataframe(
        self, 
        df: pd.DataFrame, 
        repo_results: Dict[str, List[str]]
    ) -> pd.DataFrame:
        github_links_list = []
        
        for _, row in df.iterrows():
            project_id = str(row.get('rid') or row.get('id') or '')
            if project_id in repo_results:
                links = repo_results[project_id]
                github_links_list.append(", ".join(links) if links else "")
            else:
                github_links_list.append("")
        
        df_copy = df.copy()
        df_copy["github_links"] = github_links_list
        return df_copy[df_copy["github_links"] != ""]

    def save_final_results(self, df: pd.DataFrame, output_path: str) -> None:
        try:
            df.to_csv(output_path, index=False)
            logger.info(f"Saved {len(df)} projects to {output_path}")
        except Exception as e:
            logger.error(f"Error saving final results to {output_path}: {e}")
            raise


def validate_api_keys(api_keys: List[str]) -> List[str]:
    valid_keys = []
    
    for i, key in enumerate(api_keys, 1):
        if not key or "your_" in key.lower():
            logger.warning(f"Key {i}: Not provided or placeholder")
            continue
            
        test_url = f"https://dev.hackaday.io/v2/search?search_term=test&limit=1&api_key={key}"
        
        try:
            response = requests.get(test_url, timeout=10)
            if response.status_code == 200:
                logger.info(f"Key {i}: Valid ({key[:8]}...)")
                valid_keys.append(key)
            else:
                logger.warning(f"Key {i}: Invalid (status {response.status_code})")
        except requests.exceptions.RequestException as e:
            logger.error(f"Key {i}: Connection error - {e}")
        
        time.sleep(1)
    
    return valid_keys


def load_project_data(file_path: Optional[str] = None) -> Optional[pd.DataFrame]:
    if file_path and os.path.exists(file_path):
        try:
            return pd.read_csv(file_path)
        except Exception as e:
            logger.error(f"Error loading project data from {file_path}: {e}")
            return None
    
    logger.warning("No project data file found")
    return None


def main():
    # Configuration
    API_KEYS = [
        "6c3b75f36f059d5e",
        "e5bcc5d9d52ece3e",
        "9d3c6f9bb37ad664",
        "3827bd4158a73618",
        "d275895df08f6d68",
        "aefa4953324eacbe",
        "9c10b8b498697a25",
        "d13e264d5e8b9965",
        "39829e5453347957"
    ]
    
    SEARCH_TERM = "hardware"
    PROJECT_DATA_FILE = "hardware_projects.csv"
    OUTPUT_FILE = "hackaday_projects_with_repos_FINAL.csv"
    FORCE_REFRESH = False
    
    try:
        # Validate API keys
        logger.info("Validating API keys...")
        valid_keys = validate_api_keys(API_KEYS)
        
        if len(valid_keys) < 1:
            logger.error("No valid API keys found")
            return
        
        logger.info(f"Found {len(valid_keys)} valid API keys")
        
        # Initialize client and processor
        client = HackadayClient(valid_keys, requests_per_hour=900)  # Conservative
        processor = ProjectDataProcessor(client)
        
        # Load project data
        if not FORCE_REFRESH and os.path.exists(PROJECT_DATA_FILE):
            logger.info(f"Loading existing project data from {PROJECT_DATA_FILE}")
            df = load_project_data(PROJECT_DATA_FILE)
        else:
            logger.info(f"Fetching projects from Hackaday API...")
            projects = client.search_projects(SEARCH_TERM)
            
            if not projects:
                logger.error("No projects found")
                return
            
            logger.info(f"Retrieved {len(projects)} projects")
            df = pd.DataFrame(projects)
            df.to_csv(PROJECT_DATA_FILE, index=False)
        
        if df is None:
            logger.error("Could not load project data")
            return
        
        # Extract project IDs
        project_ids = processor.extract_project_ids(df)
        logger.info(f"Found {len(project_ids)} projects to process")
        
        # Load existing progress
        start_index = processor.load_checkpoint()
        existing_results = processor.load_existing_results()
        
        logger.info(f"Starting from project {start_index + 1} of {len(project_ids)}")
        
        # Process remaining projects
        if start_index < len(project_ids):
            new_results = client.process_projects_safely(project_ids, start_index)
            
            # Combine results
            all_results = {**existing_results, **new_results}
            
            # Save final results
            processor.save_incremental_results(df, all_results, len(project_ids))
            
            df_final = processor.add_repo_links_to_dataframe(df, all_results)
            processor.save_final_results(df_final, OUTPUT_FILE)
            
            projects_with_repos = len(df_final)
            total_projects = len(df)
            percentage = (projects_with_repos / total_projects * 100) if total_projects > 0 else 0
            
            logger.info(f"SUCCESS! Found repo links for {projects_with_repos}/{total_projects} projects ({percentage:.1f}%)")
        else:
            logger.info("All projects already processed")
        
        # Clean up
        for file in [processor.checkpoint_file, processor.results_file]:
            if os.path.exists(file):
                os.remove(file)
                logger.info(f"Cleaned up {file}")
        
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise
    finally:
        if 'client' in locals():
            client.close()


if __name__ == "__main__":
    main()