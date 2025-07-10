import requests
from bs4 import BeautifulSoup
import json
import time
import re
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin
import logging
import argparse

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OpenHardwareScraper:
    def __init__(self, base_url: str = "https://www.openhardware.io/", delay: float = 2.0):
        self.base_url = base_url
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def load_project_names(self, filename: str) -> List[str]:
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            logger.error(f"File {filename} not found")
            return []

    def build_url(self, page_name: str) -> str:
        page_name = page_name.lstrip('/')
        return urljoin(self.base_url, page_name)

    def clean_text(self, text: str) -> str:
        """Clean text by removing null bytes and other encoding artifacts"""
        if not text:
            return ""
        # Remove null bytes and other common encoding artifacts
        cleaned = text.replace('\x00', '').replace('\u0000', '')
        cleaned = cleaned.replace('', '').replace('\ufffd', '')
        # Clean up extra whitespace
        cleaned = ' '.join(cleaned.split())
        return cleaned.strip()

    def extract_text_or_none(self, element) -> Optional[str]:
        if not element:
            return None
        raw_text = element.get_text(strip=True)
        return self.clean_text(raw_text) if raw_text else None

    def extract_number_from_text(self, text: str) -> Optional[int]:
        if not text:
            return None
        match = re.search(r'\d+', text.replace(',', ''))
        return int(match.group()) if match else None

    def parse_project_metadata(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        data = {}
        title_elem = soup.find('div', class_='title')
        data['project_name'] = self.extract_text_or_none(title_elem)
        data['project_url'] = url
        creator_elem = soup.find('div', class_='creator')
        if creator_elem:
            author_link = creator_elem.find('a')
            if author_link:
                author_text = author_link.get_text(strip=True)
                data['project_author'] = author_text.replace('by ', '')
            else:
                data['project_author'] = None
        else:
            data['project_author'] = None
        return data

    def find_github_link(self, soup: BeautifulSoup) -> Optional[str]:
        github_links = soup.find_all('a', href=re.compile(r'github\.com', re.IGNORECASE))
        if github_links:
            return github_links[0].get('href')
        text_content = soup.get_text()
        github_match = re.search(r'https?://github\.com/[^\s\)]+', text_content, re.IGNORECASE)
        if github_match:
            return github_match.group()
        return None

    def parse_overview_section(self, soup: BeautifulSoup) -> Dict[str, Any]:
        data = {
            'license': None,
            'created': None,
            'updated': None,
            'views': None,
            'github': None,
            'homepage': None
        }
        overview = soup.find('div', class_='overview')
        if not overview:
            return data
        rows = overview.find_all('div', class_='row')
        for row in rows:
            left = row.find('div', class_='left')
            right = row.find('div', class_='right')
            if not left or not right:
                continue
            original_key = left.get_text(strip=True)
            key = original_key.lower().rstrip(':')
            if 'license' in key:
                data['license'] = right.get_text(strip=True)
            elif 'created' in key:
                data['created'] = right.get_text(strip=True)
            elif 'updated' in key:
                data['updated'] = right.get_text(strip=True)
            elif 'views' in key:
                views_text = right.get_text(strip=True)
                data['views'] = self.extract_number_from_text(views_text) or 0
            elif 'github' in key:
                github_link = right.find('a')
                if github_link and github_link.get('href'):
                    href = github_link.get('href')
                    if href.startswith('/') and not href.startswith('//'):
                        href = f"https://github.com{href}"
                    data['github'] = href
                else:
                    data['github'] = None
            elif 'homepage' in key:
                homepage_link = right.find('a')
                if homepage_link and homepage_link.get('href'):
                    data['homepage'] = homepage_link.get('href')
                else:
                    homepage_text = right.get_text(strip=True)
                    if homepage_text.startswith('http'):
                        data['homepage'] = homepage_text
                    else:
                        data['homepage'] = None
        return data

    def parse_statistics(self, soup: BeautifulSoup) -> Dict[str, int]:
        stats = {
            'likes': 0,
            'collects': 0,
            'comments': 0,
            'downloads': 0
        }
        action_rows = soup.find_all('div', class_='actionRow')
        for row in action_rows:
            row_id = row.get('id', '').lower()
            count_elem = row.find('span', class_='count')
            if not count_elem:
                continue
            count_text = count_elem.get_text(strip=True)
            count = self.extract_number_from_text(count_text) or 0
            if 'like' in row_id or 'like' in ' '.join(row.get('class', [])):
                stats['likes'] = count
            elif 'collect' in row_id or 'collect' in ' '.join(row.get('class', [])):
                stats['collects'] = count
            elif 'comment' in row_id or 'comment' in ' '.join(row.get('class', [])):
                stats['comments'] = count
            elif 'download' in row_id or 'download' in ' '.join(row.get('class', [])):
                stats['downloads'] = count
            else:
                row_text = row.get_text(strip=True).lower()
                if 'like' in row_text and stats['likes'] == 0:
                    stats['likes'] = count
                elif 'collect' in row_text and stats['collects'] == 0:
                    stats['collects'] = count
                elif 'comment' in row_text and stats['comments'] == 0:
                    stats['comments'] = count
                elif 'download' in row_text and stats['downloads'] == 0:
                    stats['downloads'] = count
        return stats

    def parse_design_files(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        files = []
        design_tab = soup.find('div', id='tabs-design')
        if not design_tab:
            return files
        
        table = design_tab.find('table')
        if not table:
            return files
        
        # Find all tr elements that contain td elements (data rows, not header rows)
        data_rows = table.find_all('tr')
        data_rows = [row for row in data_rows if row.find('td')]
        
        for row in data_rows:
            cells = row.find_all('td')
            if len(cells) >= 3:
                # Extract name from first cell
                name_cell = cells[0]
                link = name_cell.find('a')
                
                if link:
                    # Remove the icon element and get clean text
                    icon = link.find('i')
                    if icon:
                        icon.decompose()  # Remove the icon element
                    name = link.get_text(strip=True)
                else:
                    name = name_cell.get_text(strip=True)
                
                # Extract size and downloads
                size = cells[1].get_text(strip=True)
                downloads = self.extract_number_from_text(cells[2].get_text(strip=True)) or 0
                
                if name:  # Only add if we have a valid name
                    files.append({
                        'name': name,
                        'size': size,
                        'downloads': downloads
                    })
        
        return files
    
    def parse_bill_of_materials(self, soup: BeautifulSoup) -> tuple[List[Dict[str, Any]], Optional[float]]:
        bom = []
        total_cost = None
        bom_tab = soup.find('div', id='tabs-bom')
        if not bom_tab:
            return bom, total_cost
        
        table = bom_tab.find('table')
        if not table:
            return bom, total_cost
        
        # Extract headers from the table
        headers = []
        header_row = table.find('thead')
        if header_row:
            header_cells = header_row.find_all('th')
            headers = [self.clean_text(cell.get_text(strip=True)) for cell in header_cells]
        
        # Remove empty headers and clean up any encoding issues
        cleaned_headers = []
        for header in headers:
            # Clean up common encoding issues and empty headers
            cleaned_header = header.replace('��', '').strip()
            if cleaned_header:  # Only keep non-empty headers
                cleaned_headers.append(cleaned_header)
            else:
                cleaned_headers.append(f"Column_{len(cleaned_headers) + 1}")  # Fallback name
        
        # Find all data rows (those containing td elements)
        all_rows = table.find_all('tr')
        data_rows = [row for row in all_rows if row.find('td')]
        
        for row in data_rows:
            cells = row.find_all('td')
            if not cells:  # Skip rows with no data cells
                continue
                
            cell_texts = [self.clean_text(cell.get_text(strip=True)) for cell in cells]
            
            # Create a row dictionary mapping headers to values
            row_data = {}
            
            # Map each cell to its corresponding header
            for i, cell_text in enumerate(cell_texts):
                if i < len(cleaned_headers):
                    header_name = cleaned_headers[i]
                else:
                    # If more cells than headers, create generic column names
                    header_name = f"Column_{i + 1}"
                
                row_data[header_name] = cell_text if cell_text else None
            
            # Check if this might be a total cost row (look for "total" in any cell)
            is_total_row = any('total' in str(cell).lower() for cell in cell_texts if cell)
            if is_total_row:
                # Try to extract a numeric value that might be the total cost
                for cell_text in cell_texts:
                    if cell_text:
                        # Look for patterns like "123.45", "$123.45", "123,45", etc.
                        import re
                        cost_match = re.search(r'[\d,]+\.?\d*', cell_text.replace('$', '').replace(',', ''))
                        if cost_match:
                            try:
                                total_cost = float(cost_match.group().replace(',', ''))
                                break
                            except ValueError:
                                continue
                continue  # Don't add total rows to the BOM data
            
            # Skip obviously empty rows (all values are None or empty)
            if all(not value for value in row_data.values()):
                continue
            
            # Skip header-like rows that might appear in data (e.g., repeated headers)
            first_cell = cell_texts[0].lower() if cell_texts else ""
            if any(header_word in first_cell for header_word in ['id', 'name', 'designator', 'qty', 'quantity', 'component']):
                # But only skip if it looks exactly like headers (check if other cells match header pattern)
                if len(cell_texts) >= 3 and any(header.lower() in cell_texts[1].lower() for header in ['name', 'value', 'component']):
                    continue
            
            # Add the row to our BOM data
            bom.append(row_data)
        
        # If no headers were found, create generic headers based on the first data row
        if not cleaned_headers and bom:
            first_row = bom[0]
            cleaned_headers = [f"Column_{i+1}" for i in range(len(first_row))]
            # Update all rows to use the generic headers
            for i, row in enumerate(bom):
                old_row = row.copy()
                bom[i] = {}
                for j, (key, value) in enumerate(old_row.items()):
                    header_name = cleaned_headers[j] if j < len(cleaned_headers) else f"Column_{j+1}"
                    bom[i][header_name] = value
        
        return bom, total_cost

    def scrape_project(self, page_name: str) -> Optional[Dict[str, Any]]:
        url = self.build_url(page_name)
        logger.info(f"Scraping: {url}")
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            data = {}
            metadata = self.parse_project_metadata(soup, url)
            data.update(metadata)
            overview = self.parse_overview_section(soup)
            data.update(overview)
            if not data.get('github'):
                data['github'] = self.find_github_link(soup)
            data['statistics'] = self.parse_statistics(soup)
            data['design_files'] = self.parse_design_files(soup)
            bom, total_cost = self.parse_bill_of_materials(soup)
            data['bill_of_materials'] = bom
            data['total_cost'] = total_cost
            logger.info(f"Successfully scraped: {data.get('project_name', 'Unknown')} - "
                       f"Likes: {data['statistics']['likes']}, "
                       f"Downloads: {data['statistics']['downloads']}, "
                       f"GitHub: {'Yes' if data.get('github') else 'No'}")
            return data
        except requests.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None

    def scrape_all_projects(self, filename: str = 'hardware.txt', output_file: str = 'scraped_projects.json'):
        project_names = self.load_project_names(filename)
        if not project_names:
            logger.error("No project names found to scrape")
            return
        logger.info(f"Found {len(project_names)} projects to scrape")
        results = []
        failed_urls = []
        for i, page_name in enumerate(project_names, 1):
            logger.info(f"Processing {i}/{len(project_names)}: {page_name}")
            data = self.scrape_project(page_name)
            if data:
                results.append(data)
            else:
                failed_urls.append(page_name)
            if i < len(project_names):
                logger.info(f"Waiting {self.delay} seconds before next request...")
                time.sleep(self.delay)
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(results)} projects to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
        if failed_urls:
            logger.warning(f"Failed to scrape {len(failed_urls)} projects:")
            for url in failed_urls:
                logger.warning(f"  - {url}")
            with open('failed_projects.txt', 'w', encoding='utf-8') as f:
                for url in failed_urls:
                    f.write(f"{url}\n")
            logger.info("Failed URLs saved to failed_projects.txt")

    def scrape_single_project(self, page_name: str, output_file: Optional[str] = None):
        logger.info(f"Scraping single project: {page_name}")
        data = self.scrape_project(page_name)
        if data:
            print("\n" + "="*60)
            print("SCRAPED PROJECT DATA")
            print("="*60)
            print(json.dumps(data, indent=2, ensure_ascii=False))
            print("="*60)
            if output_file:
                try:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    logger.info(f"Saved project data to {output_file}")
                except Exception as e:
                    logger.error(f"Failed to save to file: {e}")
        else:
            logger.error(f"Failed to scrape project: {page_name}")

def main():
    parser = argparse.ArgumentParser(description='Scrape OpenHardware.io projects')
    parser.add_argument('--single', '-s', type=str, 
                       help='Scrape a single project (e.g., "view/32993/Hematuria-Meter")')
    parser.add_argument('--file', '-f', type=str, default='hardware.txt',
                       help='File containing project page names (default: hardware.txt)')
    parser.add_argument('--output', '-o', type=str, default='scraped_projects.json',
                       help='Output JSON file (default: scraped_projects.json)')
    parser.add_argument('--delay', '-d', type=float, default=2.0,
                       help='Delay between requests in seconds (default: 2.0)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    scraper = OpenHardwareScraper(delay=args.delay)
    if args.single:
        output_file = None
        if args.output != 'scraped_projects.json':
            output_file = args.output
        scraper.scrape_single_project(args.single, output_file)
    else:
        scraper.scrape_all_projects(args.file, args.output)

if __name__ == "__main__":
    main()
