#!/usr/bin/env python3
"""
Extract Mendeley Data repositories from OHX dataset
"""

import json
import re

def extract_mendeley_urls(repo_text):
    """Extract Mendeley URLs from repository text"""
    mendeley_urls = []
    
    if not repo_text:
        return mendeley_urls
    
    # Convert to lowercase for pattern matching
    repo_lower = repo_text.lower()
    
    # Check if this is a Mendeley repository
    is_mendeley = False
    
    # Check for Mendeley indicators
    if ('mendeley' in repo_lower or 
        'data.mendeley.com' in repo_lower or 
        '10.17632/' in repo_text):
        is_mendeley = True
    
    if is_mendeley:
        # Extract URLs using regex patterns
        
        # Pattern 1: Direct Mendeley Data URLs
        mendeley_patterns = [
            r'https://data\.mendeley\.com/datasets/[^\s\]]+',
            r'http://data\.mendeley\.com/datasets/[^\s\]]+',
            r'https://doi\.org/10\.17632/[^\s\]]+',
            r'http://doi\.org/10\.17632/[^\s\]]+',
            r'https://dx\.doi\.org/10\.17632/[^\s\]]+',
            r'http://dx\.doi\.org/10\.17632/[^\s\]]+',
            r'doi\.org/10\.17632/[^\s\]]+',
            r'dx\.doi\.org/10\.17632/[^\s\]]+',
            r'10\.17632/[^\s\]]+',
        ]
        
        for pattern in mendeley_patterns:
            matches = re.findall(pattern, repo_text, re.IGNORECASE)
            for match in matches:
                # Clean up the URL
                url = match.strip().rstrip('.,;')
                
                # Normalize URLs
                if url.startswith('10.17632/'):
                    url = 'https://doi.org/' + url
                elif url.startswith('doi.org/10.17632/'):
                    url = 'https://' + url
                elif url.startswith('dx.doi.org/10.17632/'):
                    url = 'https://' + url
                
                mendeley_urls.append(url)
    
    return mendeley_urls

def extract_mendeley_repositories(file_path, output_path):
    """Extract Mendeley Data repositories from projects"""
    
    # Load data
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    mendeley_urls = []
    
    for project in data:
        spec_table = project.get('specifications_table', {})
        
        # Check multiple possible field names for repository
        repo_field = (spec_table.get('Source file repository', '') or 
                     spec_table.get('Source File Repository', '') or
                     spec_table.get('Source file repository', ''))
        
        if repo_field and repo_field.strip():
            urls = extract_mendeley_urls(repo_field)
            mendeley_urls.extend(urls)
    
    # Remove duplicates while preserving order
    unique_urls = []
    seen = set()
    for url in mendeley_urls:
        if url not in seen:
            unique_urls.append(url)
            seen.add(url)
    
    # Write to output file
    with open(output_path, 'w', encoding='utf-8') as f:
        for url in unique_urls:
            f.write(url + '\n')
    
    print(f"Extracted {len(unique_urls)} unique Mendeley Data repository URLs")
    print(f"Output saved to: {output_path}")
    
    return len(unique_urls)

if __name__ == "__main__":
    input_file = '/Users/nmweber/Desktop/OSH_Datasets/data/cleaned/ohx_allPubs_extract.json'
    output_file = '/Users/nmweber/Desktop/OSH_Datasets/mendeley_repos.txt'
    
    extract_mendeley_repositories(input_file, output_file)