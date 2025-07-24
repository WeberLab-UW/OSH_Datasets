import requests
import json
import re
from urllib.parse import urlparse
from typing import List, Dict, Any
import time

class OSFMetadataFetcher:
    def __init__(self):
        self.base_url = "https://api.osf.io/v2"
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/vnd.api+json',
            'Content-Type': 'application/vnd.api+json'
        })
    
    def extract_project_id(self, url: str) -> str:
        """Extract OSF project ID from URL"""
        pattern = r'osf\.io/([a-zA-Z0-9]{5,})'
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        raise ValueError(f"Could not extract project ID from URL: {url}")
    
    def fetch_project_metadata(self, project_id: str) -> Dict[str, Any]:
        """Fetch basic project metadata with embedded data"""
        url = f"{self.base_url}/nodes/{project_id}/"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
    
    def fetch_project_analytics(self, project_id: str) -> Dict[str, Any]:
        """Fetch project analytics and metrics"""
        url = f"{self.base_url}/nodes/{project_id}/analytics/"
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return {}
    
    def fetch_project_subjects(self, project_id: str) -> List[Dict[str, Any]]:
        """Fetch project subjects/disciplines"""
        url = f"{self.base_url}/nodes/{project_id}/subjects/"
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                data = response.json()
                subjects = []
                for subject in data.get('data', []):
                    subjects.append({
                        'text': subject['attributes']['text'],
                        'parents': subject['attributes'].get('parents', [])
                    })
                return subjects
        except Exception as e:
            print(f"Error fetching subjects: {e}")
        return []
    
    def fetch_storage_providers(self, project_id: str) -> List[str]:
        """Fetch available storage providers for the project"""
        url = f"{self.base_url}/nodes/{project_id}/files/"
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                data = response.json()
                providers = []
                for provider in data.get('data', []):
                    providers.append(provider['attributes']['name'])
                return providers
        except Exception as e:
            print(f"Error fetching storage providers: {e}")
        return ['osfstorage']  # Default fallback
    
    def fetch_project_logs(self, project_id: str) -> Dict[str, Any]:
        """Fetch project logs for activity metrics"""
        url = f"{self.base_url}/nodes/{project_id}/logs/"
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return {}
    
    def fetch_file_structure(self, project_id: str) -> Dict[str, Any]:
        """Fetch file structure for all storage providers"""
        providers = self.fetch_storage_providers(project_id)
        all_files = {}
        
        for provider in providers:
            print(f"Fetching files from provider: {provider}")
            files_url = f"{self.base_url}/nodes/{project_id}/files/{provider}/"
            
            def get_files_recursive(folder_url: str, level: int = 0) -> List[Dict]:
                if level > 10:  # Prevent infinite recursion
                    return []
                
                try:
                    print(f"Fetching: {folder_url}")
                    response = self.session.get(folder_url)
                    print(f"Response status: {response.status_code}")
                    
                    if response.status_code != 200:
                        print(f"Error response: {response.text}")
                        return []
                    
                    data = response.json()
                    print(f"Found {len(data.get('data', []))} items")
                    
                    files = []
                    for item in data.get('data', []):
                        if not isinstance(item, dict):
                            continue
                        attrs = item.get('attributes', {})
                        if not isinstance(attrs, dict):
                            continue
                            
                        file_info = {
                            'name': attrs.get('name', ''),
                            'kind': attrs.get('kind', ''),
                            'size': attrs.get('size'),
                            'modified': attrs.get('date_modified'),
                            'created': attrs.get('date_created'),
                            'path': attrs.get('materialized_path', ''),
                            'provider': provider,
                            'downloads': 0  # Will be updated if metrics available
                        }
                        
                        # Try to get download metrics
                        version_info = attrs.get('current_version', {})
                        if isinstance(version_info, dict):
                            metrics = version_info.get('metrics', {})
                            if isinstance(metrics, dict):
                                file_info['downloads'] = metrics.get('downloads', 0)
                        
                        # Handle folders recursively
                        if attrs.get('kind') == 'folder':
                            relationships = item.get('relationships', {})
                            files_rel = relationships.get('files', {})
                            if files_rel and 'links' in files_rel:
                                related_link = files_rel['links'].get('related', {})
                                if isinstance(related_link, dict):
                                    folder_files_url = related_link.get('href', '')
                                elif isinstance(related_link, str):
                                    folder_files_url = related_link
                                else:
                                    folder_files_url = ''
                                
                                if folder_files_url:
                                    file_info['children'] = get_files_recursive(folder_files_url, level + 1)
                        
                        files.append(file_info)
                    
                    return files
                except Exception as e:
                    print(f"Error fetching files from {folder_url}: {e}")
                    return []
            
            provider_files = get_files_recursive(files_url)
            if provider_files:
                all_files[provider] = provider_files
        
        return all_files
    
    def fetch_contributors(self, project_id: str) -> List[Dict[str, Any]]:
        """Fetch project contributors"""
        url = f"{self.base_url}/nodes/{project_id}/contributors/"
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                data = response.json()
                contributors = []
                for contrib in data.get('data', []):
                    user_data = contrib.get('embeds', {}).get('users', {}).get('data', {})
                    contributors.append({
                        'name': user_data.get('attributes', {}).get('full_name', 'Unknown'),
                        'permission': contrib['attributes'].get('permission'),
                        'bibliographic': contrib['attributes'].get('bibliographic', False)
                    })
                return contributors
        except:
            pass
        return []
    
    def fetch_citations(self, project_id: str) -> Dict[str, Any]:
        """Fetch citation information"""
        url = f"{self.base_url}/nodes/{project_id}/citation/"
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return {}
    
    def count_total_downloads(self, file_structure: Dict[str, List[Dict]]) -> int:
        """Count total downloads across all files in all providers"""
        def count_files_recursive(files: List[Dict]) -> int:
            total = 0
            for item in files:
                total += item.get('downloads', 0)
                if item.get('children'):
                    total += count_files_recursive(item['children'])
            return total
        
        total_downloads = 0
        for files in file_structure.values():
            total_downloads += count_files_recursive(files)
        return total_downloads
    
    def count_total_files(self, file_structure: Dict[str, List[Dict]]) -> int:
        """Count total files across all providers"""
        def count_files_recursive(files: List[Dict]) -> int:
            count = 0
            for item in files:
                if item.get('kind') == 'file':
                    count += 1
                if item.get('children'):
                    count += count_files_recursive(item['children'])
            return count
        
        total_files = 0
        for files in file_structure.values():
            total_files += count_files_recursive(files)
        return total_files
    
    def process_project(self, url: str) -> Dict[str, Any]:
        """Process a single OSF project URL and return comprehensive metadata"""
        try:
            project_id = self.extract_project_id(url)
            print(f"Processing project: {project_id}")
            
            # Fetch basic metadata with embedded data
            metadata = self.fetch_project_metadata(project_id)
            project_data = metadata.get('data', {})
            attributes = project_data.get('attributes', {})
            embeds = project_data.get('embeds', {})
            
            # Extract license information
            license_info = {}
            if 'license' in embeds and embeds['license']['data']:
                license_data = embeds['license']['data']['attributes']
                license_info = {
                    'name': license_data.get('name', ''),
                    'text': license_data.get('text', ''),
                    'url': license_data.get('url', '')
                }
            
            # Extract subjects
            subjects = []
            if 'subjects' in embeds and embeds['subjects']['data']:
                for subject in embeds['subjects']['data']:
                    subjects.append({
                        'text': subject['attributes']['text'],
                        'parents': subject['attributes'].get('parents', [])
                    })
            else:
                # Fallback to separate API call
                subjects = self.fetch_project_subjects(project_id)
            
            # Fetch additional data
            analytics = self.fetch_project_analytics(project_id)
            logs = self.fetch_project_logs(project_id)
            file_structure = self.fetch_file_structure(project_id)
            contributors = self.fetch_contributors(project_id)
            citations = self.fetch_citations(project_id)
            
            # Calculate metrics
            total_downloads = self.count_total_downloads(file_structure)
            total_files = self.count_total_files(file_structure)
            log_count = len(logs.get('data', []))
            
            result = {
                'project_id': project_id,
                'url': url,
                'title': attributes.get('title', ''),
                'description': attributes.get('description', ''),
                'created': attributes.get('date_created'),
                'modified': attributes.get('date_modified'),
                'public': attributes.get('public', False),
                'tags': attributes.get('tags', []),
                'category': attributes.get('category'),
                'fork': attributes.get('fork', False),
                'registration': attributes.get('registration', False),
                'preprint': attributes.get('preprint', False),
                'license': license_info,
                'subjects': subjects,
                'metrics': {
                    'total_downloads': total_downloads,
                    'activity_logs': log_count,
                    'contributor_count': len(contributors),
                    'file_count': total_files,
                    'storage_providers': list(file_structure.keys()) if file_structure else []
                },
                'contributors': contributors,
                'file_structure': file_structure,
                'analytics': analytics,
                'citation': citations
            }
            
            return result
            
        except Exception as e:
            print(f"Error processing {url}: {e}")
            return {
                'url': url,
                'error': str(e)
            }
    
    def process_urls(self, urls: List[str], delay: float = 2.0) -> List[Dict[str, Any]]:
        """Process multiple OSF URLs with rate limiting and retry logic"""
        results = []
        
        for i, url in enumerate(urls):
            print(f"Processing {i+1}/{len(urls)}: {url}")
            
            # Retry logic for rate limiting
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    result = self.process_project(url)
                    results.append(result)
                    break
                except Exception as e:
                    if "429" in str(e) and attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 30  # 30, 60, 90 seconds
                        print(f"  Rate limited, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                        time.sleep(wait_time)
                    else:
                        print(f"  Failed after {attempt + 1} attempts: {e}")
                        results.append({
                            'url': url,
                            'error': str(e)
                        })
                        break
            
            # Rate limiting between requests
            if i < len(urls) - 1:
                time.sleep(delay)
            
            # Save checkpoint every 10 projects
            if (i + 1) % 10 == 0:
                checkpoint_file = f'osf_checkpoint_{i+1}.json'
                with open(checkpoint_file, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False, default=str)
                print(f"  Checkpoint saved: {checkpoint_file}")
        
        return results
    
    def save_results(self, results: List[Dict[str, Any]], filename: str = 'osf_metadata.json'):
        """Save results to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        print(f"Results saved to {filename}")

def main():
    # Read URLs from file
    urls = []
    try:
        with open('/Users/nmweber/Desktop/OSH_Datasets/improved_normalized_osf_links.txt', 'r') as f:
            urls = [f"https://{line.strip()}" for line in f if line.strip()]
        print(f"Loaded {len(urls)} URLs from improved_normalized_osf_links.txt")
    except FileNotFoundError:
        print("Error: osf_ohx_links.txt not found")
        return
    
    fetcher = OSFMetadataFetcher()
    results = fetcher.process_urls(urls, delay=2.0)  # Increased delay to handle rate limiting
    
    # Print summary
    successful = 0
    failed = 0
    for result in results:
        if 'error' not in result:
            successful += 1
            print(f"\n✓ Project: {result['title']}")
            print(f"  Downloads: {result['metrics']['total_downloads']}")
            print(f"  Files: {result['metrics']['file_count']}")
            print(f"  Contributors: {result['metrics']['contributor_count']}")
            print(f"  License: {result['license'].get('name', 'Not specified')}")
            print(f"  Subjects: {[s['text'] for s in result['subjects']]}")
            print(f"  Storage providers: {result['metrics']['storage_providers']}")
        else:
            failed += 1
            print(f"\n✗ Error processing {result['url']}: {result['error']}")
    
    print(f"\n=== Summary ===")
    print(f"Total URLs processed: {len(urls)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    
    # Save detailed results
    fetcher.save_results(results, 'osf_ohx_metadata.json')

if __name__ == "__main__":
    main()