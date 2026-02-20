#!/usr/bin/env python3
"""
MendeleyData Metadata Fetcher - Combined Approach

This script provides two methods to fetch metadata from MendeleyData projects:

1. OAI-PMH Harvester (Recommended - No authentication required)
   - Uses Open Archives Initiative Protocol
   - Base URL: https://data.mendeley.com/oai
   - Returns Dublin Core metadata
   - Simpler to use, no OAuth setup needed

2. REST API (More detailed data, requires OAuth)
   - Uses Mendeley's REST API
   - Requires OAuth token setup
   - Returns more detailed metadata including file information
   - May include usage statistics (views, downloads)

Usage:
    python mendeley_fetcher.py --method oai --urls urls.txt
    python mendeley_fetcher.py --method api --token YOUR_TOKEN --urls urls.txt
"""

import re
import csv
import json
import time
import argparse
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, urlparse
from typing import List, Dict, Optional, Iterator, Union
from datetime import datetime


class MendeleyOAIHarvester:
    """OAI-PMH based harvester - no authentication required"""
    
    def __init__(self):
        self.base_url = "https://data.mendeley.com/oai"
        self.session = requests.Session()
        self.namespaces = {
            'oai': 'http://www.openarchives.org/OAI/2.0/',
            'dc': 'http://purl.org/dc/elements/1.1/',
            'oai_dc': 'http://www.openarchives.org/OAI/2.0/oai_dc/',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
        }
    
    def make_request(self, verb: str, **params) -> Optional[ET.Element]:
        """Make OAI-PMH request and return parsed XML"""
        params['verb'] = verb
        url = f"{self.base_url}?{urlencode(params)}"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            
            # Check for OAI errors
            error_elem = root.find('.//oai:error', self.namespaces)
            if error_elem is not None:
                print(f"OAI Error: {error_elem.get('code')} - {error_elem.text}")
                return None
                
            return root
            
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}")
            return None
        except ET.ParseError as e:
            print(f"XML parsing error: {e}")
            return None
    
    def extract_dataset_id_from_identifier(self, identifier: str) -> Optional[str]:
        """Extract dataset ID from OAI identifier"""
        match = re.search(r'datasets/([a-zA-Z0-9]+)', identifier)
        return match.group(1) if match else None
    
    def parse_dublin_core_record(self, record_elem: ET.Element) -> Dict:
        """Parse Dublin Core metadata from OAI record"""
        metadata = record_elem.find('.//oai_dc:dc', self.namespaces)
        if not metadata:
            return {}
        
        record_data = {}
        
        # Collect all Dublin Core elements
        for elem in metadata:
            tag = elem.tag.replace('{http://purl.org/dc/elements/1.1/}', '')
            if elem.text:
                if tag not in record_data:
                    record_data[tag] = []
                record_data[tag].append(elem.text.strip())
        
        return record_data
    
    def harvest_records(self, metadata_prefix: str = 'oai_dc', from_date: str = None, 
                       until_date: str = None, set_spec: str = None,
                       resumption_token: str = None) -> Iterator[Dict]:
        """Harvest records from the repository"""
        params = {'metadataPrefix': metadata_prefix}
        
        if resumption_token:
            params = {'resumptionToken': resumption_token}
        else:
            if from_date:
                params['from'] = from_date
            if until_date:
                params['until'] = until_date
            if set_spec:
                params['set'] = set_spec
        
        root = self.make_request('ListRecords', **params)
        if not root:
            return
        
        # Process records
        for record in root.findall('.//oai:record', self.namespaces):
            header = record.find('.//oai:header', self.namespaces)
            if header is None or header.get('status') == 'deleted':
                continue
            
            # Extract header information
            identifier = header.find('oai:identifier', self.namespaces)
            datestamp = header.find('oai:datestamp', self.namespaces)
            
            record_info = {
                'method': 'oai',
                'oai_identifier': identifier.text if identifier is not None else '',
                'datestamp': datestamp.text if datestamp is not None else '',
                'dataset_id': '',
                'mendeley_url': '',
                'metadata': self.parse_dublin_core_record(record)
            }
            
            # Extract dataset ID and construct URL
            if record_info['oai_identifier']:
                dataset_id = self.extract_dataset_id_from_identifier(record_info['oai_identifier'])
                if dataset_id:
                    record_info['dataset_id'] = dataset_id
                    record_info['mendeley_url'] = f"https://data.mendeley.com/datasets/{dataset_id}"
            
            yield record_info
        
        # Check for resumption token
        resumption = root.find('.//oai:resumptionToken', self.namespaces)
        if resumption is not None and resumption.text:
            yield from self.harvest_records(resumption_token=resumption.text)
    
    def search_by_urls(self, urls: List[str]) -> List[Dict]:
        """Find records matching specific MendeleyData URLs"""
        dataset_ids = set()
        for url in urls:
            match = re.search(r'data\.mendeley\.com/datasets/([a-zA-Z0-9]+)', url)
            if match:
                dataset_ids.add(match.group(1))
        
        if not dataset_ids:
            print("No valid dataset IDs found in URLs")
            return []
        
        print(f"Searching for {len(dataset_ids)} datasets in OAI repository...")
        
        matching_records = []
        for record in self.harvest_records():
            if record['dataset_id'] in dataset_ids:
                matching_records.append(record)
                print(f"Found: {record['dataset_id']}")
                
                # Remove found ID to avoid searching for it again
                dataset_ids.discard(record['dataset_id'])
                if not dataset_ids:  # All found
                    break
        
        return matching_records


class MendeleyAPIFetcher:
    """REST API based fetcher - requires OAuth token"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.mendeley.com"
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/vnd.mendeley-public-dataset.1+json'
        })
    
    def extract_dataset_id(self, url: str) -> Optional[str]:
        """Extract dataset ID from MendeleyData URL"""
        patterns = [
            r'data\.mendeley\.com/datasets/([a-zA-Z0-9]+)',
            r'staging-data\.mendeley\.com/datasets/([a-zA-Z0-9]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def get_dataset_metadata(self, dataset_id: str, version: Optional[int] = None) -> Optional[Dict]:
        """Fetch metadata for a specific dataset"""
        endpoint = f"{self.base_url}/datasets/{dataset_id}"
        
        params = {
            'fields': 'id,version,name,description,contributors,categories,tags,data_licence,files,created_date,published_date,doi'
        }
        
        if version:
            params['version'] = version
            
        try:
            response = self.session.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching dataset {dataset_id}: {e}")
            return None
    
    def get_dataset_files(self, dataset_id: str, version: Optional[int] = None) -> List[Dict]:
        """Get detailed file information for a dataset"""
        metadata = self.get_dataset_metadata(dataset_id, version)
        if not metadata:
            return []
        
        files_info = []
        if 'files' in metadata:
            for file_item in metadata['files']:
                file_info = {
                    'filename': file_item.get('filename', 'Unknown'),
                    'description': file_item.get('description', ''),
                    'size': file_item.get('content_details', {}).get('size', 0),
                    'content_type': file_item.get('content_details', {}).get('content_type', ''),
                    'download_url': file_item.get('content_details', {}).get('download_url', '')
                }
                files_info.append(file_info)
        
        return files_info
    
    def get_dataset_statistics(self, dataset_id: str) -> Dict:
        """Attempt to get dataset statistics"""
        stats = {
            'views': 'N/A',
            'downloads': 'N/A', 
            'citations': 'N/A',
            'note': 'Metrics may not be available via public API'
        }
        
        # Try alternative endpoints for statistics
        stats_endpoints = [
            f"{self.base_url}/datasets/{dataset_id}/stats",
            f"{self.base_url}/datasets/{dataset_id}/metrics"
        ]
        
        for endpoint in stats_endpoints:
            try:
                response = self.session.get(endpoint)
                if response.status_code == 200:
                    data = response.json()
                    stats.update(data)
                    stats['note'] = 'Retrieved from API'
                    break
            except:
                continue
                
        return stats
    
    def process_url(self, url: str) -> Optional[Dict]:
        """Process a single MendeleyData URL and extract all available metadata"""
        dataset_id = self.extract_dataset_id(url)
        if not dataset_id:
            print(f"Could not extract dataset ID from URL: {url}")
            return None
        
        print(f"Processing dataset: {dataset_id}")
        
        metadata = self.get_dataset_metadata(dataset_id)
        if not metadata:
            return None
        
        files_info = self.get_dataset_files(dataset_id)
        statistics = self.get_dataset_statistics(dataset_id)
        
        result = {
            'method': 'api',
            'mendeley_url': url,
            'dataset_id': dataset_id,
            'name': metadata.get('name', 'Unknown'),
            'description': metadata.get('description', ''),
            'version': metadata.get('version', 1),
            'doi': metadata.get('doi', ''),
            'created_date': metadata.get('created_date', ''),
            'published_date': metadata.get('published_date', ''),
            'contributors': [
                f"{contrib.get('first_name', '')} {contrib.get('last_name', '')}"
                for contrib in metadata.get('contributors', [])
            ],
            'categories': metadata.get('categories', []),
            'tags': metadata.get('tags', []),
            'licence': metadata.get('data_licence', ''),
            'file_count': len(files_info),
            'files': files_info,
            'statistics': statistics,
            'raw_metadata': metadata
        }
        
        return result
    
    def process_urls_from_list(self, urls: List[str]) -> List[Dict]:
        """Process multiple URLs"""
        results = []
        for url in urls:
            result = self.process_url(url.strip())
            if result:
                results.append(result)
            time.sleep(1)  # Rate limiting
        return results


class MendeleyDataFetcher:
    """Combined fetcher supporting both OAI-PMH and REST API methods"""
    
    def __init__(self, method: str = 'oai', access_token: str = None):
        self.method = method
        
        if method == 'oai':
            self.harvester = MendeleyOAIHarvester()
            self.api_fetcher = None
        elif method == 'api':
            if not access_token:
                raise ValueError("Access token required for API method")
            self.harvester = None
            self.api_fetcher = MendeleyAPIFetcher(access_token)
        else:
            raise ValueError("Method must be 'oai' or 'api'")
    
    def process_urls_from_list(self, urls: List[str]) -> List[Dict]:
        """Process URLs using the selected method"""
        if self.method == 'oai':
            return self.harvester.search_by_urls(urls)
        else:
            return self.api_fetcher.process_urls_from_list(urls)
    
    def process_urls_from_file(self, file_path: str) -> List[Dict]:
        """Process URLs from a file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                urls = [line.strip() for line in f.readlines() if line.strip()]
            return self.process_urls_from_list(urls)
        except FileNotFoundError:
            print(f"File not found: {file_path}")
            return []
    
    def save_results_to_json(self, results: List[Dict], output_file: str):
        """Save results to JSON file"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Results saved to: {output_file}")
    
    def save_results_to_csv(self, results: List[Dict], output_file: str):
        """Save results to CSV file"""
        if not results:
            return
        
        # Determine fieldnames based on method
        if self.method == 'oai':
            fieldnames = [
                'oai_identifier', 'dataset_id', 'mendeley_url', 'datestamp',
                'title', 'creator', 'description', 'subject', 'publisher',
                'date', 'type', 'format', 'rights', 'doi'
            ]
        else:
            fieldnames = [
                'mendeley_url', 'dataset_id', 'name', 'description', 'version', 'doi',
                'created_date', 'published_date', 'contributors', 'categories',  
                'tags', 'licence', 'file_count', 'views', 'downloads', 'citations'
            ]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in results:
                if self.method == 'oai':
                    # Handle OAI results
                    metadata = result.get('metadata', {})
                    
                    # Find DOI from identifiers
                    doi = ''
                    for identifier in metadata.get('identifier', []):
                        if identifier.startswith('10.'):
                            doi = identifier
                            break
                    
                    row = {
                        'oai_identifier': result.get('oai_identifier', ''),
                        'dataset_id': result.get('dataset_id', ''),
                        'mendeley_url': result.get('mendeley_url', ''),
                        'datestamp': result.get('datestamp', ''),
                        'title': '; '.join(metadata.get('title', [])),
                        'creator': '; '.join(metadata.get('creator', [])),
                        'description': '; '.join(metadata.get('description', []))[:500],
                        'subject': '; '.join(metadata.get('subject', [])),
                        'publisher': '; '.join(metadata.get('publisher', [])),
                        'date': '; '.join(metadata.get('date', [])),
                        'type': '; '.join(metadata.get('type', [])),
                        'format': '; '.join(metadata.get('format', [])),
                        'rights': '; '.join(metadata.get('rights', [])),
                        'doi': doi
                    }
                else:
                    # Handle API results
                    row = {
                        'mendeley_url': result.get('mendeley_url', ''),
                        'dataset_id': result.get('dataset_id', ''),
                        'name': result.get('name', ''),
                        'description': (result.get('description', '') or '')[:500],
                        'version': result.get('version', ''),
                        'doi': result.get('doi', ''),
                        'created_date': result.get('created_date', ''),
                        'published_date': result.get('published_date', ''),
                        'contributors': '; '.join(result.get('contributors', [])),
                        'categories': '; '.join(result.get('categories', [])),
                        'tags': '; '.join(result.get('tags', [])),
                        'licence': result.get('licence', ''),
                        'file_count': result.get('file_count', 0),
                        'views': result.get('statistics', {}).get('views', 'N/A'),
                        'downloads': result.get('statistics', {}).get('downloads', 'N/A'),
                        'citations': result.get('statistics', {}).get('citations', 'N/A')
                    }
                
                writer.writerow(row)
        
        print(f"Results saved to: {output_file}")


def main():
    """Main function with command line interface"""
    parser = argparse.ArgumentParser(
        description='Fetch metadata from MendeleyData projects',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Using OAI-PMH (recommended - no authentication needed)
    python %(prog)s --method oai --urls urls.txt
    python %(prog)s --method oai --url "https://data.mendeley.com/datasets/abc123"
    
    # Using REST API (requires OAuth token)
    python %(prog)s --method api --token YOUR_TOKEN --urls urls.txt
    python %(prog)s --method api --token YOUR_TOKEN --url "https://data.mendeley.com/datasets/abc123"
        """
    )
    
    parser.add_argument('--method', choices=['oai', 'api'], default='oai',
                       help='Method to use: oai (OAI-PMH, no auth) or api (REST API, requires token)')
    parser.add_argument('--token', help='OAuth access token (required for api method)')
    parser.add_argument('--url', help='Single URL to process')
    parser.add_argument('--urls', help='File containing URLs (one per line)')
    parser.add_argument('--output', default='mendeley_results', 
                       help='Output filename prefix (default: mendeley_results)')
    parser.add_argument('--format', choices=['json', 'csv', 'both'], default='both',
                       help='Output format (default: both)')
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.method == 'api' and not args.token:
        parser.error("--token is required when using --method api")
    
    if not args.url and not args.urls:
        parser.error("Either --url or --urls must be specified")
    
    # Initialize fetcher
    try:
        fetcher = MendeleyDataFetcher(method=args.method, access_token=args.token)
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    
    # Process URLs
    if args.url:
        urls = [args.url]
        results = fetcher.process_urls_from_list(urls)
    else:
        results = fetcher.process_urls_from_file(args.urls)
    
    if not results:
        print("No results found")
        return 1
    
    # Save results
    print(f"\nProcessed {len(results)} datasets using {args.method.upper()} method")
    
    if args.format in ['json', 'both']:
        fetcher.save_results_to_json(results, f"{args.output}.json")
    
    if args.format in ['csv', 'both']:
        fetcher.save_results_to_csv(results, f"{args.output}.csv")
    
    # Print summary
    print(f"\nSummary:")
    for result in results:
        if args.method == 'oai':
            titles = result.get('metadata', {}).get('title', ['Untitled'])
            title = titles[0] if titles else 'Untitled'
        else:
            title = result.get('name', 'Untitled')
        
        print(f"- {title} (ID: {result.get('dataset_id', 'Unknown')})")
    
    return 0


if __name__ == "__main__":
    exit(main())