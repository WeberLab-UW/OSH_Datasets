# %%
import requests
import json
import pandas as pd
from pandas import json_normalize
import time

# %%
def get_all_oshwa_projects(api_key, delay=0.1):
    url = "https://certificationapi.oshwa.org/api/projects"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    all_projects = []
    offset = 0
    limit = 1000  # Maximum allowed per request
    
    while True:
        params = {
            'limit': limit,
            'offset': offset
        }
        
        print(f"Fetching projects {offset} to {offset + limit - 1}...")
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            projects = data.get('items', [])
            total = data.get('total', 0)
            
            print(f"Retrieved {len(projects)} projects. Total available: {total}")
            
            if not projects:  # No more projects
                break
                
            all_projects.extend(projects)
            
            # Check if we've retrieved all projects
            if len(all_projects) >= total or len(projects) < limit:
                break
                
            offset += limit
            
            # Add a small delay to be respectful to the API
            time.sleep(delay)
            
        else:
            print(f"Error {response.status_code}: {response.text}")
            break
    
    print(f"Total projects retrieved: {len(all_projects)}")
    return all_projects

# Usage
projects = get_all_oshwa_projects("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjY3MjkwOTY5NWJjMTg4MDAxNGQ3MWQ4MiIsImlhdCI6MTc1MDg5NTY3NiwiZXhwIjoxNzU5NTM1Njc2fQ.hudQVLEQefdOOQZfg_CpTM_0xfOK_YCAGxYOYH7u9NA")

# %%
## Save to Json
with open("OSHWA_projects.json", "w") as f:
    json.dump(projects, f, indent=4)

# %%
## Save to CSV
def flatten_json(json_data):
    flattened_data = json_normalize(json_data)
    return flattened_data

def json_to_csv(json_file, csv_file):
    with open(json_file, 'r') as f:
        json_data = json.load(f)

    # Flatten JSON data
    flattened_data = flatten_json(json_data)
    
    # Write flattened data to CSV
    flattened_data.to_csv(csv_file, index=False)

json_file = 'OSHWA_projects.json'
csv_file = 'OSHWA_projects.csv'
json_to_csv(json_file, csv_file)


