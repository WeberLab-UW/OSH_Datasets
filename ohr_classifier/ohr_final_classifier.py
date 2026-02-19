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
"""Pass #1: Feature Extraction"""

def analyze_gitlab_project_structure(project_id, token, branch: str):
    """Pull down Gitlab repository tree"""
    
    url = f"https://gitlab.com/api/v4/projects/{project_id}/repository/tree"
    headers = {'PRIVATE-TOKEN': token}
    
    params = {
        'recursive': True,
        'ref': branch, # Typically default is master, but there are a few cases where it is different
        'per_page': 100
    }
    
    all_items = []
    page = 1
    
    while True:
        params['page'] = page
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            break
        items = response.json()
        if not items:
            break
        all_items.extend(items)
        page += 1
        
        if len(items) < params['per_page']:
            break
    
    # Organize the data
    files = [item for item in all_items if item['type'] == 'blob']
    folders = [item for item in all_items if item['type'] == 'tree']
    
    # Fetch the file exentions, file names, and folder names
    file_extensions = {}
    file_names = set()
    folder_names = set()
    
    # file extentions
    for file in files:
        ext = os.path.splitext(file['name'])[1].lower()
        if ext:
            file_extensions[ext] = file_extensions.get(ext, 0) + 1
    
    # file names
    for file in files: 
        file_name = os.path.basename(file['path'])
        file_names.add(file_name)

    # folder names
    for folder in folders:
        folder_name = os.path.basename(folder['path'])
        folder_names.add(folder_name)
    
    return {
        'project_id': project_id,
        'total_files': len(files),
        'total_folders': len(folders),
        'files': files,
        'folders': folders,
        'file_extensions': file_extensions,
        'file_names': list(file_names),
        'folder_names': list(folder_names),
        'all_file_paths': [f['path'] for f in files],
        'all_folder_paths': [f['path'] for f in folders]
    }

def extract_project_features_simple(project_id, token, project_name: str, branch: str) -> Dict[str, Any]:
    """Extract features from the GitLab projects and classify them as hardware or not hardware."""
    
    project_data = analyze_gitlab_project_structure(project_id, token, branch)

    # Check project name exclusions first
    words = re.split(r'[\s_-]+', project_name.lower())
    project_name_exclusion = {'gateware', 'software', 'firmware', 'gw', 'sw', 'fw'}
    
    if any(exclusion in words for exclusion in project_name_exclusion):
        classification = 'not_hardware'
        return {
            'project_id': project_id,
            'file_extensions': list(project_data['file_extensions'].keys()),
            'file_names': [file['name'] for file in project_data['files']],
            'classification': classification
        }
    
    # Hardware file indicators (fixed missing dots)
    hardware_extensions = {
        '.pcb', '.sch', '.brd', '.gbr', '.drl', '.kicad_pcb', '.lib', 
        '.SchDoc', '.PcbDoc', '.PcbLib', '.PrjPCB', '.ipt', '.step', 
        '.stl', '.dwg', '.ucf'  
    }

    # Hardware folders
    hardware_folders = {'hardware', 'pcb', 'eagle', 'kicad', 'gerber',
                        'hw', 'layout', 'schematics', 'schematic', 'board',
                        'rtl', 'pcb_design', 'cad'}
    
    # Extract file names
    file_names = [file['name'] for file in project_data['files']]
    
    # Classification logic (name exclusions already handled above)
    if any(ext in hardware_extensions for ext in project_data['file_extensions']):
        classification = 'hardware'
    elif any(folder in hardware_folders for folder in {name.lower() for name in project_data['folder_names']}):
        classification = 'hardware'
    elif set(file_names).issubset({'README.md', 'readme.md', 'Readme.md', '.ohwr.yaml'}) and len(file_names) <= 2 and len(file_names) > 0:
        classification = 'ambiguous'
    elif project_data['total_files'] == 0 and project_data['total_folders'] == 0:
        classification = 'empty_respository'
    elif not project_data['files'] and not project_data['folders']:
        classification = 'no_respository'
    else:
        classification = 'not_hardware'
    
    return {
        'project_id': project_id,
        'file_extensions': list(project_data['file_extensions'].keys()),
        'file_names': file_names,
        'classification': classification
    }

def round_1():
    CSV_PATH = "./OHR_repos.csv"

    try:
        if not os.path.exists(CSV_PATH):
            print(f"Error: File '{CSV_PATH}' not found.")
            return
        df = pd.read_csv(CSV_PATH)
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return

    round_1_classifications = []

    for project_id, project_name, branch, path in zip(df["id"], df["name"], df["default_branch"], df["path_with_namespace"]):
        try:
            project_data = extract_project_features_simple(project_id, "YOUR_TOKEN_HERE", project_name, branch)
            
            round_1_classifications.append({
                'project_id': project_id,
                'name': project_name,
                'path': path,
                'data': project_data,
                'classification': project_data['classification'],
            })
            # print(f"Project {project_id} classification = {project_data['classification']}")
        except Exception as e:
            print(f"Error analyzing project {project_id}: {e}")
    
    return round_1_classifications

# %%
"""PASS #2: For ambiguous projects, fetch project description, README, and Wiki and classify based on their content"""

class GitLabAPIClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Private-Token": token,
            "User-Agent": "GitLab-Repo-Fetcher/1.0"
        })

    def fetch_project_description(self, project_id: str) -> Optional[Dict[str, Any]]:
        url = f"https://gitlab.com/api/v4/projects/{project_id}"
        response = self.session.get(url)

        if response.status_code == 200:
            parse_response = response.json()
            return {
                'description': parse_response.get('description'),
                'name': parse_response.get('name'),
                'project_id': parse_response.get('id'),
                'branch': parse_response.get('default_branch'),
                'path': parse_response.get('path_with_namespace'),
            }
        else:
            raise Exception(f"Failed to fetch project metadata: {response.status_code}")

    def fetch_readme_file(self, project_id: str, branch: str) -> Optional[str]:
        url = f"https://gitlab.com/api/v4/projects/{project_id}/repository/files/README.md/raw"
        params = {'ref': branch}
        response = self.session.get(url, params=params)

        if response.status_code == 200:
            return response.text
        elif response.status_code == 404:
            print(f"{project_id}: May not have a README page.")
            return None
        else:
            raise Exception(f"Failed to fetch README file: {response.status_code}")

    def fetch_wiki_home_file(self, path: str, page_slug: str) -> Optional[str]:
        project_identifier = path.replace("/", "%2F")
        wiki_url = f"https://gitlab.com/api/v4/projects/{project_identifier}/wikis/{page_slug}"
        response = self.session.get(wiki_url)

        if response.status_code == 200:
            return response.json().get('content', '')
        elif response.status_code == 404:
            print(f"{path}: May not have a Wiki page.")
            return None
        else:
            raise Exception(f"Failed to fetch Wiki page: {response.status_code}")

# %%
def gather_project_information(project_id: str, client: GitLabAPIClient, path: str, branch: str, page_slug: str):
    context = {
        'project_metadata': None,
        'readme_content': None,
        'wiki_content': None
    }

    metadata = client.fetch_project_description(project_id)
    if metadata:
        context['project_metadata'] = metadata

    readme_content = client.fetch_readme_file(project_id, branch)
    if readme_content:
        context['readme_content'] = readme_content

    wiki_content = client.fetch_wiki_home_file(path, page_slug)
    if wiki_content:
        context['wiki_content'] = wiki_content

    return context


def combine_all_project_information(context: Dict[str, Any]) -> str:
    combined_text = []

    metadata = context.get('project_metadata', {})
    if metadata:
        combined_text.append(metadata.get('description', ''))

    if context.get('readme_content'):
        combined_text.append(context['readme_content'])

    if context.get('wiki_content'):
        combined_text.append(context['wiki_content'])

    return ' '.join(combined_text).lower()


def evaluate_project_information(combined_text: str) -> Dict[str, Any]:
    hardware_keywords = {
        'strong': ['schematics', 'schematic', 'pcb', 'circuit', 'breakout board', 'fpga mezzanine card',
                   'hardware design', 'sch', 'sch diagram', 'kicad', 'bom', 'bill of materials', 'mechanical design',
                   'assembly details', 'eda'],
        'medium': ['hardware', 'microcontroller', 'i/o', 'layout'],
        'weak': ['prototype', 'board', 'chip', 'design', 'device']
    }

    hw_score = 0

    for strength, keywords in hardware_keywords.items():
        weight = {'strong': 3, 'medium': 2, 'weak': 1}[strength]
        hw_score += sum(combined_text.count(keyword) * weight for keyword in keywords)

    if hw_score >= 20:
        classification = 'hardware'
    elif hw_score >= 11:
        classification = 'ambiguous'
    else:
        classification = 'not hardware'

    return {
        'hw_score': hw_score,
        'classification': classification,
    }


# %%
def examine_ambiguous_projects(round_1_classifications):
    TOKEN = "YOUR_TOKEN_HERE"
    client = GitLabAPIClient(token=TOKEN)
    round_2_classifications = []  # Changed from project_information


    for project in round_1_classifications:
        
        if project['classification'] == 'ambiguous':  # Changed from 'still ambiguous'
            try:
                project_id = project['project_id']
                metadata = client.fetch_project_description(project_id)

                if metadata:
                    path = metadata.get('path', '')
                    branch = metadata.get('branch', 'master')

                    context = gather_project_information(
                        project_id=project_id,
                        client=client,
                        path=path,
                        branch=branch,
                        page_slug="Home"
                    )

                    combined_text = combine_all_project_information(context)
                    classifications = evaluate_project_information(combined_text)

                    update_data = {
                        'project_id': project_id,
                        'name': metadata.get('name', ''),
                        'path': path,
                        'classification': classifications['classification'],
                        'hw_score': classifications['hw_score'],
                        #'readme_content': context.get('readme_content', ''),
                        #'wiki_content': context.get('wiki_content', ''),
                        #'description': metadata.get('description', '')
                    }
                    round_2_classifications.append(update_data)

                    print(f"Project {project_id} updated classification = {classifications['classification']}, score = {classifications['hw_score']}")

            except Exception as e:
                print(f"Skipping project {project_id} due to error: {e}")
                continue  # ensures project is skipped entirely

    return round_2_classifications

# %%
def update_classifications(round_1_classifications, round_2_classifications):
    """Update round 1 results with refined classifications from round 2"""
    
    # Create a lookup dictionary from round 2 results
    round_2_lookup = {result['project_id']: result for result in round_2_classifications}
    
    # Update round 1 results
    for result in round_1_classifications:
        project_id = result['project_id']
        if project_id in round_2_lookup:
            result['classification'] = round_2_lookup[project_id]['classification']
            result['hw_score'] = round_2_lookup[project_id]['hw_score']
            #result['readme_content'] = round_2_lookup[project_id]['readme_content']
            #result['wiki_content'] = round_2_lookup[project_id]['wiki_content']
            #result['description'] = round_2_lookup[project_id]['description']
    
    return round_1_classifications

def structure_results(round_1_classifications):
    structured_results = []

    for result in round_1_classifications:
        structured_project = {
            'project_id': result.get('project_id', ''),
            'name': result.get('name', ''),
            'path': result.get('path', ''),
            'classification': result.get('classification', ''),
            'hw_score': result.get('hw_score', 0)
        }
        structured_results.append(structured_project)

    return structured_results

def main(): 
    round_1_classifications = round_1()
    round_2_classifications = examine_ambiguous_projects(round_1_classifications)
    merged_results = update_classifications(round_1_classifications, round_2_classifications)
    final_structure_results = structure_results(merged_results)

    return final_structure_results

if __name__ == "__main__":
    results = main()
    df = pd.DataFrame(results)
    df
    #print(json.dumps(results, indent=2))  
 
    with open('final_classifications.json', 'w') as f:
        json.dump(results, f, indent=2)


