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
class GitLabAPIClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Private-Token": token,
            "User-Agent": "GitLab-Repo-Fetcher/1.0"
        })

    def fetch_wiki_home_file(self, name:str, page_slug) -> str:
        project_identifier = (f"ohwr/project/{name}").replace("/", "%2F")
        
        wiki_url = f"https://gitlab.com/api/v4/projects/{project_identifier}/wikis/{page_slug}"
        response = self.session.get(wiki_url)

        if response.status_code == 200:
            return response.json()['content']
        if response.status_code == 404:
            raise Exception(f"{name}: May not not have a wiki page.")
        else:
            raise Exception(f"Failed to fetch file: {response.status_code}")
        
    time.sleep(1)  
    
def main(): 
    csv_path = "./osh_test.csv"
    print("Starting main function...") 

    try:
        if not os.path.exists(csv_path):
            print(f"Error: File '{csv_path}' not found.")
            return
        df = pd.read_csv(csv_path)
        print(f"CSV loaded. Number of entries: {len(df)}") 
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return
    
    try:
        print("Creating API client...")
        client = GitLabAPIClient(token="YOUR_TOKEN_HERE")
    except Exception as e:
        print(f"Failed to initialize client: {e}")
        return

    output_dir = "ohr_wiki_home_files"
    os.makedirs(output_dir, exist_ok=True)

    paths = df["path"].dropna()
    #print(f"Projects to process: {paths.tolist()}")  

    for name in paths:
        try:
            print(f"Fetching wiki home file for project: {name}")
            page_slug = "Home"  
            content = client.fetch_wiki_home_file(name, page_slug)

            output_file = os.path.join(output_dir, f"{name.replace('/', '_')}_wiki_home.md")
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)

            print(f"✅ Saved wiki home file for {name} to {output_file}")
        except Exception as e:
            print(f"❌ Error with project {name}: {e}")

if __name__ == "__main__":
    print("Running script directly...")  
    main()


