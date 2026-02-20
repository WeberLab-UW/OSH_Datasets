import json

def extract_repositories(json_file_path, output_file_path):
    with open(json_file_path, 'r') as file:
        data = json.load(file)
    
    repositories = []
    
    for project in data:
        if 'specifications_table' in project:
            repo = project['specifications_table'].get('Source file repository')
            if repo:
                repositories.append(repo)
    
    with open(output_file_path, 'w') as output_file:
        for repo in repositories:
            output_file.write(repo + '\n')
    
    print(f"Extracted {len(repositories)} repositories to {output_file_path}")

if __name__ == "__main__":
    input_file = "data/cleaned/ohx_allPubs_extract.json"  # Update with your JSON file path
    output_file = "ohx_repsource.txt"
    
    extract_repositories(input_file, output_file)