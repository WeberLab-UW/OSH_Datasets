#!/usr/bin/env python3
import requests
import json
import re
from typing import List, Dict, Any
import time
from urllib.parse import urlparse

class CleanOSFMetadataFetcher:
    def __init__(self):
        self.base_url = "https://api.osf.io/v2"
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/vnd.api+json',
            'User-Agent': 'OSF-Research-Tool/1.0'
        })
    
    def extract_project_id(self, url: str) -> str:
        """Extract OSF project ID from URL"""
        pattern = r'osf\.io/([a-zA-Z0-9]{5,})'
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        raise ValueError(f"Could not extract project ID from URL: {url}")
    
    def fetch_project_metadata(self, project_id: str) -> Dict[str, Any]:
        """Fetch basic project metadata from multiple endpoint types"""
        endpoints = [
            f"{self.base_url}/nodes/{project_id}/",
            f"{self.base_url}/registrations/{project_id}/",
            f"{self.base_url}/preprints/{project_id}/"
        ]
        
        last_error = None
        for endpoint in endpoints:
            try:
                response = self.session.get(endpoint)
                if response.status_code == 200:
                    data = response.json()
                    # Add endpoint type info
                    if '/nodes/' in endpoint:
                        data['endpoint_type'] = 'node'
                    elif '/registrations/' in endpoint:
                        data['endpoint_type'] = 'registration'
                    elif '/preprints/' in endpoint:
                        data['endpoint_type'] = 'preprint'
                    return data
                else:
                    last_error = f"HTTP {response.status_code}"
            except Exception as e:
                last_error = str(e)
        
        raise Exception(f"All endpoints failed. Last error: {last_error}")
    
    def fetch_project_subjects(self, project_id: str, endpoint_type: str = 'node') -> List[Dict[str, Any]]:
        """Fetch project subjects/disciplines"""
        if endpoint_type == 'registration':
            url = f"{self.base_url}/registrations/{project_id}/subjects/"
        elif endpoint_type == 'preprint':
            url = f"{self.base_url}/preprints/{project_id}/subjects/"
        else:
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
            print(f"Error fetching subjects for {project_id}: {e}")
        return []
    
    def fetch_contributors(self, project_id: str, endpoint_type: str = 'node') -> List[Dict[str, Any]]:
        """Fetch project contributors"""
        if endpoint_type == 'registration':
            url = f"{self.base_url}/registrations/{project_id}/contributors/"
        elif endpoint_type == 'preprint':
            url = f"{self.base_url}/preprints/{project_id}/contributors/"
        else:
            url = f"{self.base_url}/nodes/{project_id}/contributors/"
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                data = response.json()
                contributors = []
                for contrib in data.get('data', []):
                    # Get user info from relationships
                    user_link = contrib.get('relationships', {}).get('users', {}).get('links', {}).get('related', {})
                    if isinstance(user_link, dict):
                        user_href = user_link.get('href', '')
                    else:
                        user_href = user_link
                    
                    contributor_info = {
                        'permission': contrib['attributes'].get('permission'),
                        'bibliographic': contrib['attributes'].get('bibliographic', False),
                        'user_id': contrib.get('id', ''),
                        'user_link': user_href
                    }
                    
                    # Try to get user name if available
                    if user_href:
                        try:
                            user_response = self.session.get(user_href)
                            if user_response.status_code == 200:
                                user_data = user_response.json()
                                contributor_info['name'] = user_data.get('data', {}).get('attributes', {}).get('full_name', 'Unknown')
                            else:
                                contributor_info['name'] = 'Unknown'
                        except:
                            contributor_info['name'] = 'Unknown'
                    else:
                        contributor_info['name'] = 'Unknown'
                    
                    contributors.append(contributor_info)
                    time.sleep(0.1)  # Small delay between user lookups
                return contributors
        except Exception as e:
            print(f"Error fetching contributors for {project_id}: {e}")
        return []
    
    def fetch_project_analytics(self, project_id: str, endpoint_type: str = 'node') -> Dict[str, Any]:
        """Fetch project analytics and metrics"""
        if endpoint_type == 'registration':
            url = f"{self.base_url}/registrations/{project_id}/analytics/"
        elif endpoint_type == 'preprint':
            url = f"{self.base_url}/preprints/{project_id}/analytics/"
        else:
            url = f"{self.base_url}/nodes/{project_id}/analytics/"
        
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching analytics for {project_id}: {e}")
        return {}

    def fetch_project_logs(self, project_id: str, endpoint_type: str = 'node') -> Dict[str, Any]:
        """Fetch project logs for activity metrics"""
        if endpoint_type == 'registration':
            url = f"{self.base_url}/registrations/{project_id}/logs/"
        elif endpoint_type == 'preprint':
            # Preprints don't have logs in the same way
            return {}
        else:
            url = f"{self.base_url}/nodes/{project_id}/logs/"
        
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching logs for {project_id}: {e}")
        return {}

    def fetch_citations(self, project_id: str, endpoint_type: str = 'node') -> Dict[str, Any]:
        """Fetch citation information"""
        if endpoint_type == 'registration':
            url = f"{self.base_url}/registrations/{project_id}/citation/"
        elif endpoint_type == 'preprint':
            url = f"{self.base_url}/preprints/{project_id}/citation/"
        else:
            url = f"{self.base_url}/nodes/{project_id}/citation/"
        
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching citations for {project_id}: {e}")
        return {}

    def fetch_storage_providers(self, project_id: str, endpoint_type: str = 'node') -> List[str]:
        """Fetch available storage providers for the project"""
        if endpoint_type == 'registration':
            url = f"{self.base_url}/registrations/{project_id}/files/"
        elif endpoint_type == 'preprint':
            # Preprints don't have file storage providers in the same way
            return []
        else:
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
            print(f"Error fetching storage providers for {project_id}: {e}")
        return ['osfstorage']  # Default fallback

    def fetch_file_structure(self, project_id: str, endpoint_type: str = 'node') -> Dict[str, Any]:
        """Fetch file structure for all storage providers"""
        if endpoint_type == 'preprint':
            return {}  # Preprints don't have file structures in the same way
            
        providers = self.fetch_storage_providers(project_id, endpoint_type)
        all_files = {}
        
        for provider in providers:
            if endpoint_type == 'registration':
                files_url = f"{self.base_url}/registrations/{project_id}/files/{provider}/"
            else:
                files_url = f"{self.base_url}/nodes/{project_id}/files/{provider}/"
            
            def get_files_recursive(folder_url: str, level: int = 0) -> List[Dict]:
                if level > 10:  # Prevent infinite recursion
                    return []
                
                try:
                    response = self.session.get(folder_url)
                    if response.status_code != 200:
                        return []
                    
                    data = response.json()
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

    def count_files_simple(self, project_id: str, endpoint_type: str = 'node') -> int:
        """Simple file count"""
        if endpoint_type == 'registration':
            url = f"{self.base_url}/registrations/{project_id}/files/osfstorage/"
        elif endpoint_type == 'preprint':
            # Preprints don't have file listings in the same way
            return 0
        else:
            url = f"{self.base_url}/nodes/{project_id}/files/osfstorage/"
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                data = response.json()
                return len(data.get('data', []))
        except Exception as e:
            print(f"Error counting files for {project_id}: {e}")
        return 0
    
    def process_project(self, url: str) -> Dict[str, Any]:
        """Process a single OSF project URL and return comprehensive metadata"""
        try:
            project_id = self.extract_project_id(url)
            print(f"  Processing project: {project_id}")
            
            # Fetch basic metadata
            metadata = self.fetch_project_metadata(project_id)
            project_data = metadata.get('data', {})
            attributes = project_data.get('attributes', {})
            endpoint_type = metadata.get('endpoint_type', 'node')
            embeds = project_data.get('embeds', {})
            
            # Extract license information
            license_info = {}
            if 'license' in embeds and embeds['license'].get('data'):
                license_data = embeds['license']['data']['attributes']
                license_info = {
                    'name': license_data.get('name', ''),
                    'text': license_data.get('text', ''),
                    'url': license_data.get('url', '')
                }
            
            # Get subjects (try embedded first, fallback to API)
            subjects = []
            if 'subjects' in embeds and embeds['subjects'].get('data'):
                for subject in embeds['subjects']['data']:
                    subjects.append({
                        'text': subject['attributes']['text'],
                        'parents': subject['attributes'].get('parents', [])
                    })
            else:
                # Fallback to separate API call
                subjects = self.fetch_project_subjects(project_id, endpoint_type)
            time.sleep(0.5)  # Rate limiting
            
            # Fetch comprehensive data
            contributors = self.fetch_contributors(project_id, endpoint_type)
            time.sleep(0.5)  # Rate limiting
            
            analytics = self.fetch_project_analytics(project_id, endpoint_type)
            time.sleep(0.5)  # Rate limiting
            
            logs = self.fetch_project_logs(project_id, endpoint_type)
            time.sleep(0.5)  # Rate limiting
            
            file_structure = self.fetch_file_structure(project_id, endpoint_type)
            time.sleep(0.5)  # Rate limiting
            
            citations = self.fetch_citations(project_id, endpoint_type)
            time.sleep(0.5)  # Rate limiting
            
            # Calculate metrics
            total_downloads = self.count_total_downloads(file_structure)
            total_files = self.count_total_files(file_structure)
            log_count = len(logs.get('data', []))
            
            result = {
                'project_id': project_id,
                'url': url,
                'endpoint_type': endpoint_type,
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
                'citation': citations,
                'collection_date': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return result
            
        except Exception as e:
            print(f"  Error processing {url}: {e}")
            return {
                'url': url,
                'project_id': project_id if 'project_id' in locals() else 'unknown',
                'error': str(e),
                'collection_date': time.strftime('%Y-%m-%d %H:%M:%S')
            }
    
    def process_urls_batch(self, urls: List[str], start_index: int = 0) -> List[Dict[str, Any]]:
        """Process URLs with proper rate limiting"""
        results = []
        
        # Load existing results if resuming
        if start_index > 0:
            try:
                with open('osf_metadata_progress.json', 'r') as f:
                    results = json.load(f)
                print(f"Resuming from project {start_index + 1}, loaded {len(results)} existing results")
            except:
                print("Could not load existing results, starting fresh")
                results = []
        
        for i in range(start_index, len(urls)):
            url = urls[i]
            print(f"Processing {i+1}/{len(urls)}: {url}")
            
            result = self.process_project(url)
            results.append(result)
            
            # Save progress every 5 projects
            if (i + 1) % 5 == 0:
                with open('osf_metadata_progress.json', 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False, default=str)
                print(f"  Progress saved: {i+1}/{len(urls)} completed")
            
            # Rate limiting between projects
            if i < len(urls) - 1:
                time.sleep(2.0)  # 2 second delay between projects
        
        return results
    
    def save_final_results(self, results: List[Dict[str, Any]]):
        """Save final results"""
        # Save complete results
        with open('osf_ohx_metadata_final.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        
        # Print summary
        successful = len([r for r in results if 'error' not in r])
        failed = len([r for r in results if 'error' in r])
        
        print(f"\n=== Final Summary ===")
        print(f"Total projects: {len(results)}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print(f"Success rate: {successful/len(results)*100:.1f}%")
        
        if successful > 0:
            print(f"\nExample results:")
            for r in results[:3]:
                if 'error' not in r:
                    print(f"  - {r['title']} ({r['endpoint_type']})")
                    print(f"    Downloads: {r['metrics']['total_downloads']}")
                    print(f"    Files: {r['metrics']['file_count']}")
                    print(f"    Contributors: {r['metrics']['contributor_count']}")
                    print(f"    License: {r['license'].get('name', 'Not specified')}")
                    print(f"    Subjects: {[s['text'] for s in r['subjects']]}")
                    print(f"    Storage providers: {r['metrics']['storage_providers']}")

def main():
    # Read URLs from file
    urls = []
    try:
        with open('/Users/nmweber/Desktop/OSH_Datasets/improved_normalized_osf_links.txt', 'r') as f:
            urls = [f"https://{line.strip()}" for line in f if line.strip()]
        print(f"Loaded {len(urls)} URLs")
    except FileNotFoundError:
        print("Error: improved_normalized_osf_links.txt not found")
        return
    
    fetcher = CleanOSFMetadataFetcher()
    
    # Allow resuming from a specific index if needed
    start_index = 0  # Change this to resume from a specific project
    
    results = fetcher.process_urls_batch(urls, start_index)
    fetcher.save_final_results(results)

if __name__ == "__main__":
    main()