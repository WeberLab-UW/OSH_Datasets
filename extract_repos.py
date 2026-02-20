#!/usr/bin/env python3
"""
Extract repository information from OHX dataset
"""

import json

def extract_repository_info(file_path, output_path):
    """Extract repository information from projects"""
    
    # Load data
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    repos = []
    projects_with_repos = 0
    
    for i, project in enumerate(data):
        spec_table = project.get('specifications_table', {})
        
        # Check multiple possible field names for repository
        repo_field = (spec_table.get('Source file repository', '') or 
                     spec_table.get('Source File Repository', '') or
                     spec_table.get('Source file repository', ''))
        
        if repo_field and repo_field.strip():
            projects_with_repos += 1
            paper_title = project.get('paper_title', f'Project {i+1}')
            
            # Clean the repository field
            repo_clean = repo_field.strip()
            
            repos.append({
                'project_number': i + 1,
                'paper_title': paper_title,
                'repository': repo_clean
            })
    
    # Write to output file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"Repository Information for {projects_with_repos} OHX Projects\n")
        f.write("=" * 60 + "\n\n")
        
        for repo_info in repos:
            f.write(f"Project {repo_info['project_number']}: {repo_info['paper_title']}\n")
            f.write(f"Repository: {repo_info['repository']}\n")
            f.write("-" * 60 + "\n\n")
    
    print(f"Extracted repository information for {projects_with_repos} projects")
    print(f"Output saved to: {output_path}")
    
    return projects_with_repos

if __name__ == "__main__":
    input_file = '/Users/nmweber/Desktop/OSH_Datasets/data/cleaned/ohx_allPubs_extract.json'
    output_file = '/Users/nmweber/Desktop/OSH_Datasets/ohx_repos.txt'
    
    extract_repository_info(input_file, output_file)