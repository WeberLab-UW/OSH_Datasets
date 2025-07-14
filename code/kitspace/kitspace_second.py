#!/usr/bin/env python3

import requests
import json
import time
import argparse
import sys
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

def extract_json_data(soup):
    try:
        script_tag = soup.find('script', {'id': '__NEXT_DATA__'})
        if script_tag:
            json_text = script_tag.string
            return json.loads(json_text)
    except (json.JSONDecodeError, AttributeError):
        pass
    return None

def scrape_project_data(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        project_data = {
            'url': url,
            'project_name': None,
            'repository_link': None,
            'description': None,
            'bill_of_materials': [],
            'gerber_file_link': None,
            'error': None
        }
        
        next_data = extract_json_data(soup)
        
        title_elem = soup.find('div', {'data-cy': 'project-title'})
        if title_elem:
            project_data['project_name'] = title_elem.get_text(strip=True)
        elif next_data and 'props' in next_data:
            try:
                props = next_data['props']['pageProps']
                project_data['project_name'] = props.get('projectName')
            except (KeyError, TypeError):
                try:
                    props = next_data['props']['pageProps']['singleProject']
                    project_data['project_name'] = props.get('projectName')
                except (KeyError, TypeError):
                    pass
        
        desc_meta = soup.find('meta', {'name': 'description'})
        if desc_meta:
            project_data['description'] = desc_meta.get('content')
        elif next_data and 'props' in next_data:
            try:
                props = next_data['props']['pageProps']
                project_data['description'] = props.get('ogDescription')
            except (KeyError, TypeError):
                try:
                    props = next_data['props']['pageProps']['singleProject']
                    project_data['description'] = props.get('ogDescription')
                except (KeyError, TypeError):
                    pass
        
        github_elem = soup.find('div', {'data-cy': 'original-url'})
        if github_elem:
            github_link = github_elem.find('a')
            if github_link:
                href = github_link.get('href')
                if href and any(host in href for host in ['github.com', 'gitlab.com', 'bitbucket.org']):
                    project_data['repository_link'] = href
        
        if not project_data['repository_link'] and next_data:
            try:
                repo_data = next_data['props']['pageProps']['repo']
                original_url = repo_data.get('original_url')
                if original_url and any(host in original_url for host in ['github.com', 'gitlab.com', 'bitbucket.org']):
                    project_data['repository_link'] = original_url
            except (KeyError, TypeError):
                pass
            
            try:
                single_project_data = next_data['props']['pageProps']['singleProject']['repo']
                original_url = single_project_data.get('original_url')
                if original_url and any(host in original_url for host in ['github.com', 'gitlab.com', 'bitbucket.org']):
                    project_data['repository_link'] = original_url
            except (KeyError, TypeError):
                pass
        
        if next_data and 'props' in next_data:
            bom_info = None
            try:
                bom_info = next_data['props']['pageProps']['bomInfo']
            except (KeyError, TypeError):
                try:
                    bom_info = next_data['props']['pageProps']['singleProject']['bomInfo']
                except (KeyError, TypeError):
                    pass
            
            if bom_info and 'bom' in bom_info and 'lines' in bom_info['bom']:
                for line in bom_info['bom']['lines']:
                    bom_item = {
                        'reference': line.get('reference', ''),
                        'quantity': line.get('quantity', ''),
                        'description': line.get('description', ''),
                        'manufacturer': '',
                        'mpn': '',
                        'retailers': line.get('retailers', {})
                    }
                    
                    part_numbers = line.get('partNumbers', [])
                    if part_numbers and len(part_numbers) > 0:
                        bom_item['manufacturer'] = part_numbers[0].get('manufacturer', '')
                        bom_item['mpn'] = part_numbers[0].get('part', '')
                    
                    project_data['bill_of_materials'].append(bom_item)
        
        if not project_data['bill_of_materials']:
            bom_table = soup.find('table', class_=re.compile(r'TsvTable'))
            if bom_table:
                headers = []
                header_row = bom_table.find('thead')
                if header_row:
                    headers = [th.get_text(strip=True) for th in header_row.find_all('th')]
                
                tbody = bom_table.find('tbody')
                if tbody:
                    for row in tbody.find_all('tr'):
                        cells = row.find_all('td')
                        if cells and len(cells) >= len(headers):
                            bom_item = {}
                            for i, header in enumerate(headers):
                                if i < len(cells):
                                    cell_text = cells[i].get_text(strip=True)
                                    bom_item[header.lower().replace(' ', '_')] = cell_text
                            project_data['bill_of_materials'].append(bom_item)
        
        if next_data and 'props' in next_data:
            zip_url = None
            try:
                zip_url = next_data['props']['pageProps'].get('zipUrl')
            except (KeyError, TypeError):
                try:
                    zip_url = next_data['props']['pageProps']['singleProject'].get('zipUrl')
                except (KeyError, TypeError):
                    pass
            
            if zip_url:
                project_data['gerber_file_link'] = zip_url
        
        if not project_data['gerber_file_link']:
            gerber_link = soup.find('a', {'href': lambda x: x and 'gerbers.zip' in x})
            if gerber_link:
                href = gerber_link.get('href')
                if href.startswith('http'):
                    project_data['gerber_file_link'] = href
                else:
                    project_data['gerber_file_link'] = urljoin(url, href)
        
        return project_data
        
    except requests.RequestException as e:
        return {
            'url': url,
            'project_name': None,
            'repository_link': None,
            'description': None,
            'bill_of_materials': [],
            'gerber_file_link': None,
            'error': f'Request error: {str(e)}'
        }
    except Exception as e:
        return {
            'url': url,
            'project_name': None,
            'repository_link': None,
            'description': None,
            'bill_of_materials': [],
            'gerber_file_link': None,
            'error': f'Parsing error: {str(e)}'
        }

def scrape_projects_from_json(json_data, delay=1.0):
    if isinstance(json_data, str):
        json_data = json.loads(json_data)
    
    projects = json_data.get('projects', [])
    results = {
        'timestamp': json_data.get('timestamp'),
        'total_projects': len(projects),
        'scraped_data': []
    }
    
    for i, project in enumerate(projects):
        full_url = project.get('full_url')
        if not full_url:
            continue
            
        print(f"Scraping {i+1}/{len(projects)}: {full_url}")
        
        project_data = scrape_project_data(full_url)
        results['scraped_data'].append(project_data)
        
        if project_data['error']:
            print(f"  Error: {project_data['error']}")
        else:
            print(f"  Project: {project_data['project_name']}")
            print(f"  BOM items: {len(project_data['bill_of_materials'])}")
            print(f"  Repository: {project_data['repository_link']}")
        
        if i < len(projects) - 1:
            time.sleep(delay)
    
    return results

def load_json_data(input_path):
    try:
        if input_path.startswith(('http://', 'https://')):
            response = requests.get(input_path, timeout=30)
            response.raise_for_status()
            return response.json()
        else:
            with open(input_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading JSON data from {input_path}: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description='Scrape Kitspace project data from a single URL or list of URLs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scraper.py -i projects.json -o results.json
  python scraper.py -i https://example.com/projects.json -o /path/to/output.json
  python scraper.py -i projects.json -o results.json --delay 3
  python scraper.py -u https://kitspace.org/weirdgyn/Driverino-Shield -o result.json
        """
    )
    
    parser.add_argument('-u', '--url',
                       help='Single Kitspace project URL to scrape (alternative to -i)')
    parser.add_argument('-i', '--input', 
                       help='Path to JSON file or URL containing project URLs')
    parser.add_argument('-o', '--output',
                       required=True, 
                       help='Output file path for scraped data')
    parser.add_argument('--delay',
                       type=float,
                       default=2.0,
                       help='Delay between requests in seconds (default: 2.0)')
    
    args = parser.parse_args()
    
    if not args.input and not args.url:
        parser.error("Either -i/--input or -u/--url must be specified")
    
    if args.url:
        print(f"Scraping single URL: {args.url}")
        project_data = scrape_project_data(args.url)
        
        results = {
            'timestamp': None,
            'total_projects': 1,
            'scraped_data': [project_data]
        }
        
        if project_data['error']:
            print(f"  Error: {project_data['error']}")
        else:
            print(f"  Project: {project_data['project_name']}")
            print(f"  BOM items: {len(project_data['bill_of_materials'])}")
            print(f"  Repository: {project_data['repository_link']}")
    else:
        print(f"Loading project data from: {args.input}")
        json_data = load_json_data(args.input)
        
        if 'projects' not in json_data:
            print("Error: JSON file must contain a 'projects' key")
            sys.exit(1)
        
        print(f"Found {len(json_data['projects'])} projects to scrape")
        
        results = scrape_projects_from_json(json_data, delay=args.delay)
    
    print(f"Saving results to: {args.output}")
    try:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving results: {e}")
        sys.exit(1)
    
    print(f"\nScraping complete! Results saved to {args.output}")
    print(f"Successfully scraped {len(results['scraped_data'])} projects")
    
    successful = sum(1 for item in results['scraped_data'] if item['error'] is None)
    failed = len(results['scraped_data']) - successful
    print(f"Successful: {successful}, Failed: {failed}")
    
    for item in results['scraped_data']:
        if item['error'] is None and item['bill_of_materials']:
            print(f"\nSample BOM data from {item['project_name']}:")
            for bom_item in item['bill_of_materials'][:3]:
                print(f"  {bom_item}")
            break

if __name__ == "__main__":
    main()