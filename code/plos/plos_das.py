#!/usr/bin/env python3

import requests
import pandas as pd
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import re
import time
import sys
import os

class PLOSDataAvailabilityExtractor:
    def __init__(self, delay=1.0):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'PLOS Data Availability Statement Extractor 1.0'
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
    
    def extract_data_availability_statement(self, xml_content, doi):
        try:
            # Parse with BeautifulSoup to handle XML properly
            soup = BeautifulSoup(xml_content, 'xml')
            
            # Method 1: Look for the specific custom-meta with id="data-availability"
            data_availability_meta = soup.find('custom-meta', {'id': 'data-availability'})
            if data_availability_meta:
                meta_value = data_availability_meta.find('meta-value')
                if meta_value:
                    # Get text content, which handles nested XML elements like <xref>
                    text = meta_value.get_text(strip=True)
                    if text:
                        return text
            
            # Method 2: Look for custom-meta with meta-name containing "Data Availability"
            for meta in soup.find_all('custom-meta'):
                meta_name = meta.find('meta-name')
                if meta_name and 'data availability' in meta_name.get_text().lower():
                    meta_value = meta.find('meta-value')
                    if meta_value:
                        text = meta_value.get_text(strip=True)
                        if text:
                            return text
            
            # Method 3: Fallback - look for sections with data availability
            for sec in soup.find_all('sec'):
                sec_type = sec.get('sec-type', '').lower()
                if 'data' in sec_type and 'availability' in sec_type:
                    text = sec.get_text(strip=True)
                    # Remove title if present
                    title = sec.find('title')
                    if title:
                        title_text = title.get_text()
                        text = text.replace(title_text, '').strip()
                    if text:
                        return text
                
                # Check section titles
                title = sec.find('title')
                if title and 'data availability' in title.get_text().lower():
                    text = sec.get_text(strip=True)
                    title_text = title.get_text()
                    text = text.replace(title_text, '').strip()
                    if text:
                        return text
                        
            return None
            
        except Exception as e:
            return None
    
    def process_dois(self, dois, output_file=None):
        results = []
        
        for i, doi in enumerate(dois):
            print(f"Processing {i+1}/{len(dois)}: {doi}")
            
            if i > 0:
                time.sleep(self.delay)
            
            xml_content = self.fetch_article_xml(doi)
            
            if xml_content:
                data_statement = self.extract_data_availability_statement(xml_content, doi)
                if data_statement:
                    print(f"✓ Found: {data_statement[:100]}...")
                else:
                    print(f"✗ No data availability statement found")
            else:
                data_statement = None
                print(f"✗ Failed to fetch XML")
            
            results.append({
                'DOI': doi,
                'Data_Availability_Statement': data_statement
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
        print("Usage: python plos_extractor.py <input_file> [output_file]")
        print("       python plos_extractor.py <single_doi>")
        print("\nInput file should contain one DOI per line")
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
            output_file = "data_availability_output.csv"
    
    extractor = PLOSDataAvailabilityExtractor(delay=1.0)
    df = extractor.process_dois(dois, output_file)
    
    total = len(df)
    found = len(df[df['Data_Availability_Statement'].notna()])
    print(f"\nSummary:")
    print(f"Total DOIs processed: {total}")
    print(f"Data availability statements found: {found}")
    print(f"Success rate: {found/total*100:.1f}%")

if __name__ == "__main__":
    main()