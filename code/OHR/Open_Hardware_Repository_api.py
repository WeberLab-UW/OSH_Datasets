BASE_URL = "https://ohwr.org/api/v4/projects"
params = {
    "per_page": 100,
    "page": 1
}

all_repos = []

while True:
    response = requests.get(BASE_URL, params=params)
    if response.status_code != 200:
        break
    
    data = response.json()
    if not data:
        break
    
    all_repos.extend(data)
    params["page"] += 1  # Move to next page

# Save as JSON
with open("OHR_repos.json", "w") as f:
    json.dump(all_repos, f, indent=4)

print(f"Scraped {len(all_repos)} repositories from Open Hardware Repository.")

## 564 Repositories 
