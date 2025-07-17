# %%
import os
import json
import time
import pandas as pd
from urllib.parse import urlparse
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import requests
from datetime import datetime
import logging
from typing import Union, Dict, Any, List
import re
import time
import json 
import csv

# %%
def process_doi(doi: str):
    # Lower Case
    doi = doi.lower()

    # Remove https
    if "https://doi.org/" in doi:
        doi = doi.replace("https://doi.org/", "")

    return doi

def fetch_paper_metadata(doi: str, mailto: str) -> dict: 
    url = f"https://api.openalex.org/works/doi:{doi}"
    
    params = {
        'mailto' : mailto,
    }

    response = requests.get(url, params=params)
    time.sleep(0.5) 

    if response.status_code == 200: 
        return response.json()
    else: 
        raise Exception(f"Failed to fetch paper:{doi}")
    

def main():
    CSV_PATH = "./CSV_PATH.csv"
    mailto = 'YOUR_EMAIL_HERE'

    try:
        if not os.path.exists(CSV_PATH):
            print(f"❌ Error: File '{CSV_PATH}' not found.")
            return
        df = pd.read_csv(CSV_PATH)
    except Exception as e:
        print(f"❌ Error reading CSV file: {e}")
        return

    df['doi'] = df['doi'].astype(str).str.strip().str.lower()
    df = df[df['doi'].notna() & (df['doi'] != '')]

    all_paper_metadata = []

    for i, doi in enumerate(df['doi']):
        try:
            print(f"[{i+1}] Looping over: {doi}")
            processed_doi = process_doi(doi)
            print(f" → Processed DOI: {processed_doi}")

            paper_metadata = fetch_paper_metadata(processed_doi, mailto)

            if not isinstance(paper_metadata, dict):
                print(f"⚠️ Skipping invalid metadata for {processed_doi}")
                continue

            print(f" ✓ Appending metadata for {processed_doi}")
            all_paper_metadata.append(paper_metadata)

            print(f" → Total collected so far: {len(all_paper_metadata)}\n")

        except Exception as e:
            print(f"❌ Error analyzing DOI {doi}: {e}\n")

    print(f"✅ Finished! Total papers collected: {len(all_paper_metadata)}")

    with open('openalex_metadata.json', 'w') as f:
        json.dump(all_paper_metadata, f, indent=2)
    
    with open('openalex_metadata.csv', 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerows(all_paper_metadata)

    return all_paper_metadata 


if __name__ == "__main__":
    main()

