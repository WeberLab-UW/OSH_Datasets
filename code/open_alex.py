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


# %%
def process_doi(doi: str):
    # Lower Case
    doi = doi.lower()

    # Remove https
    if "https://doi.org/" in doi:
        doi = doi.replace("https://doi.org/", "")

    return doi

def fetch_paper_metadata(doi: str) -> dict: 
    url = f"https://api.openalex.org/works/doi:{doi}"
    
    try: 
        response = requests.get(url)
        response.raise_for_status()

        meta_data = response.json()

        authors = [a['author']['display_name'] for a in meta_data.get('authorships', []) if 'author' in a]
        primary_topic = [p.get('display_name') for p in meta_data.get('topics', []) if p.get('display_name') is not None]

        return {
            'doi': doi,
            'title': meta_data.get('title', None), 
            'authors': authors,
            'source': meta_data.get('source', None),
            'publication_year': meta_data.get('publication_year', None),
            'publication_date': meta_data.get('publication_date', None),
            'language': meta_data.get('language', None),
            'fwci': meta_data.get('fwci', None),
            'cited_by_count': meta_data.get('cited_by_count', None), 
            'citation_normalized_percentile.value': meta_data.get('citation_normalized_percentile.value', None),
            'is_retracted': meta_data.get('is_retracted', None),
            'versions': meta_data.get('versions', None),
            'biblio.volume': meta_data.get('biblio', {}).get('volume', None),
            'biblio.issue': meta_data.get('biblio', None).get('issue', None),
            'primary_topic': primary_topic,
            'primary_location': meta_data.get('primary_location', {}).get('source', {}).get('display_name', None),
        }

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred for DOI {doi}: {http_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"Request error occurred for DOI {doi}: {req_err}")
    except ValueError as json_err:
        print(f"JSON decoding error for DOI {doi}: {json_err}")
    except Exception as err:
        print(f"Unexpected error for DOI {doi}: {err}")

    
    return {
        'doi': doi,
        'title': None, 
        'authors': None,
        'publication_year': None,
        'publication_date': None,
        'language': None,
        'fwci': None,
        'cited_by_count': None, 
        'citation_normalized_percentile.value': None,
        'is_retracted': None,
        'versions': None,
        'biblio.volume': None,
        'biblio.issue': None,
        'primary_topic': None,
        'primary_location': None,
    }

def main():
    CSV_PATH = "./lit_sample.csv"

    try:
        if not os.path.exists(CSV_PATH):
            print(f"❌ Error: File '{CSV_PATH}' not found.")
            return
        df = pd.read_csv(CSV_PATH)
    except Exception as e:
        print(f"❌ Error reading CSV file: {e}")
        return

    # Clean DOI column: remove whitespace, lowercase, drop missing
    if 'doi' not in df.columns:
        print("❌ Error: 'doi' column not found in CSV.")
        return

    df['doi'] = df['doi'].astype(str).str.strip().str.lower()
    df = df[df['doi'].notna() & (df['doi'] != '')]

    all_paper_metadata = []

    for i, doi in enumerate(df['doi']):
        try:
            print(f"[{i+1}] Looping over: {doi}")
            processed_doi = process_doi(doi)
            print(f" → Processed DOI: {processed_doi}")

            paper_metadata = fetch_paper_metadata(processed_doi)

            if not isinstance(paper_metadata, dict):
                print(f"⚠️ Skipping invalid metadata for {processed_doi}")
                continue

            print(f" ✓ Appending metadata for {processed_doi}")
            all_paper_metadata.append(paper_metadata)

            print(f" → Total collected so far: {len(all_paper_metadata)}\n")

        except Exception as e:
            print(f"❌ Error analyzing DOI {doi}: {e}\n")

    print(f"✅ Finished! Total papers collected: {len(all_paper_metadata)}")

    with open('open_alex_sample.json', 'w') as f:
        json.dump(all_paper_metadata, f, indent=2)

    return all_paper_metadata 


if __name__ == "__main__":
    main()


# %%



