#!/usr/bin/env python3

import requests
import pandas as pd
from bs4 import BeautifulSoup
import re
import time
import sys
import os

class PLOSGitRepoExtractor:
    def __init__(self, delay=1.0):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'PLOS Git Repository Link Extractor 1.0'
        })
        
    def get_journal_from_doi(self, doi):
        if 'journal.pone' in doi:
            return 'plosone'
        elif 'journal.pmed' in doi:
            return 'plosmedicine'
        elif 'journal.pcbi' in doi:
            return 'ploscompbiol'
        elif 'journal.pgen' in doi:
            return 'plosgenetics'
        elif 'journal.ppat' in doi:
            return 'plospathogens'
        elif 'journal.pbio' in doi:
            return 'plosbiology'
        elif 'journal.pntd' in doi:
            return 'plosntds'
        else:
            return 'plosone'
    
    def construct_xml_url(self, doi):
        journal = self.get_journal_from_doi(doi)
        return f"https://journals.plos.org/{journal}/article/file?id={doi}&type=manuscript"
    
    def fetch_article_xml(self, doi):
        url = self.construct_xml_url(doi)
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException:
            return None
    
    def extract_git_repo_links_with_context(self, xml_content, doi):
        try:
            # Parse with BeautifulSoup
            soup = BeautifulSoup(xml_content, 'xml')
            
            # Get all text content from the article
            full_text = soup.get_text(separator=' ', strip=True)
            
            # Clean up whitespace
            full_text = re.sub(r'\s+', ' ', full_text)
            
            # Find all GitHub and GitLab links with various patterns
            git_patterns = [
                # GitHub patterns
                r'https?://(?:www\.)?github\.com/[^\s\)\]\,\;]+',
                r'https?://[^\s/]*\.github\.io/[^\s\)\]\,\;]*',
                r'(?:^|\s)github\.com/[^\s\)\]\,\;]+',
                r'(?:^|\s)www\.github\.com/[^\s\)\]\,\;]+',
                
                # GitLab patterns (gitlab.com and self-hosted instances)
                r'https?://(?:www\.)?gitlab\.com/[^\s\)\]\,\;]+',
                r'https?://[^\s/]*\.gitlab\.io/[^\s\)\]\,\;]*',
                r'https?://gitlab\.[^\s/]+/[^\s\)\]\,\;]+',  # self-hosted gitlab instances
                r'(?:^|\s)gitlab\.com/[^\s\)\]\,\;]+',
                r'(?:^|\s)www\.gitlab\.com/[^\s\)\]\,\;]+',
            ]
            
            results = []
            
            for pattern in git_patterns:
                matches = re.finditer(pattern, full_text, re.IGNORECASE)
                
                for match in matches:
                    repo_url = match.group().strip()
                    start_pos = match.start()
                    end_pos = match.end()
                    
                    # Determine the platform type
                    platform = self._determine_platform(repo_url)
                    
                    # Extract context around the Git repository link
                    context = self._extract_context_around_link(full_text, start_pos, end_pos, repo_url)
                    
                    if context and repo_url:
                        results.append({
                            'repo_url': repo_url,
                            'platform': platform,
                            'context': context,
                            'position': start_pos
                        })
            
            # Remove duplicates (same URL found multiple times)
            unique_results = []
            seen_urls = set()
            
            for result in results:
                if result['repo_url'] not in seen_urls:
                    seen_urls.add(result['repo_url'])
                    unique_results.append(result)
            
            return unique_results
            
        except Exception as e:
            return []
    
    def _determine_platform(self, url):
        """Determine if the URL is from GitHub, GitLab, or other Git platform"""
        url_lower = url.lower()
        if 'github' in url_lower:
            return 'GitHub'
        elif 'gitlab' in url_lower:
            return 'GitLab'
        else:
            return 'Git Repository'
    
    def _extract_context_around_link(self, text, start_pos, end_pos, repo_url):
        # Define how much context to extract (characters before and after)
        context_chars = 300
        
        # Find sentence boundaries around the link
        before_start = max(0, start_pos - context_chars)
        after_end = min(len(text), end_pos + context_chars)
        
        # Extract the context
        context = text[before_start:after_end]
        
        # Try to find better sentence boundaries
        context = self._find_sentence_boundaries(context, repo_url)
        
        # Clean up the context
        context = context.strip()
        context = re.sub(r'\s+', ' ', context)
        
        return context
    
    def _find_sentence_boundaries(self, context, repo_url):
        # Split into sentences using common delimiters
        sentences = re.split(r'[.!?]+\s+', context)
        
        # Find which sentence(s) contain the Git repository URL
        url_sentences = []
        for sentence in sentences:
            if repo_url in sentence or self._url_likely_in_sentence(sentence, repo_url):
                url_sentences.append(sentence.strip())
        
        if url_sentences:
            # Return the sentence(s) containing the URL
            result = '. '.join(url_sentences)
            # Make sure it ends with punctuation
            if not result.endswith(('.', '!', '?')):
                result += '.'
            return result
        else:
            # Fallback to original context if sentence detection fails
            return context
    
    def _url_likely_in_sentence(self, sentence, repo_url):
        # Extract the repository part of the URL for partial matching
        # Handle both GitHub and GitLab patterns
        patterns = [
            r'github\.com/([^/\s]+/[^/\s]+)',
            r'gitlab\.com/([^/\s]+/[^/\s]+)',
            r'gitlab\.[^/\s]+/([^/\s]+/[^/\s]+)'
        ]
        
        for pattern in patterns:
            repo_match = re.search(pattern, repo_url)
            if repo_match:
                repo_part = repo_match.group(1)
                if repo_part in sentence:
                    return True
        return False
    
    def process_dois(self, dois, output_file=None):
        results = []
        
        for i, doi in enumerate(dois):
            print(f"Processing {i+1}/{len(dois)}: {doi}")
            
            if i > 0:
                time.sleep(self.delay)
            
            xml_content = self.fetch_article_xml(doi)
            
            if xml_content:
                repo_links = self.extract_git_repo_links_with_context(xml_content, doi)
                
                if repo_links:
                    print(f"✓ Found {len(repo_links)} Git repository link(s)")
                    for link_info in repo_links:
                        results.append({
                            'DOI': doi,
                            'Repository_URL': link_info['repo_url'],
                            'Platform': link_info['platform'],
                            'Context': link_info['context']
                        })
                else:
                    print(f"✗ No Git repository links found")
                    results.append({
                        'DOI': doi,
                        'Repository_URL': None,
                        'Platform': None,
                        'Context': None
                    })
            else:
                print(f"✗ Failed to fetch XML")
                results.append({
                    'DOI': doi,
                    'Repository_URL': None,
                    'Platform': None,
                    'Context': None
                })
        
        df = pd.DataFrame(results)
        
        if output_file:
            df.to_csv(output_file, index=False)
            print(f"\nResults saved to {output_file}")
        
        return df

def read_dois_from_file(file_path):
    dois = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                doi = line.strip()
                if doi and not doi.startswith('#'):
                    dois.append(doi)
        return dois
    except FileNotFoundError:
        print(f"Error: File {file_path} not found")
        return []

def main():
    if len(sys.argv) < 2:
        print("Usage: python git_repo_extractor.py <input_file> [output_file]")
        print("       python git_repo_extractor.py <single_doi>")
        print("\nInput file should contain one DOI per line")
        print("Extracts GitHub and GitLab repository links with context")
        sys.exit(1)
    
    input_arg = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if os.path.isfile(input_arg):
        dois = read_dois_from_file(input_arg)
        if not dois:
            print("No valid DOIs found in input file")
            sys.exit(1)
    else:
        dois = [input_arg]
        if not output_file:
            output_file = "git_repo_links_output.csv"
    
    extractor = PLOSGitRepoExtractor(delay=1.0)
    df = extractor.process_dois(dois, output_file)
    
    total = len(df)
    found_links = len(df[df['Repository_URL'].notna()])
    unique_dois_with_links = len(df[df['Repository_URL'].notna()]['DOI'].unique())
    
    # Count by platform
    github_count = len(df[df['Platform'] == 'GitHub'])
    gitlab_count = len(df[df['Platform'] == 'GitLab'])
    
    print(f"\nSummary:")
    print(f"Total DOIs processed: {len(set(df['DOI']))}")
    print(f"DOIs with Git repository links: {unique_dois_with_links}")
    print(f"Total repository links found: {found_links}")
    print(f"  - GitHub links: {github_count}")
    print(f"  - GitLab links: {gitlab_count}")
    print(f"Success rate: {unique_dois_with_links/len(set(df['DOI']))*100:.1f}%")

if __name__ == "__main__":
    main()