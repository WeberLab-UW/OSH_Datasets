#!/usr/bin/env python3

import time
import json
import re
from datetime import datetime
from collections import defaultdict
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
from bs4 import BeautifulSoup

class KitspaceScraper:
    def __init__(self, headless=True):
        self.project_urls = set()
        self.last_count = 0
        self.no_change_count = 0
        self.headless = headless
        
    def setup_driver(self):
        """Setup Chrome webdriver with options"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-setuid-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1200,800")
        
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    
    def scrape_all_projects(self):
        """Main scraping function with infinite scroll"""
        driver = self.setup_driver()
        
        try:
            print("Navigating to Kitspace...")
            driver.get("https://kitspace.org/")
            
            # Wait for project grid to load
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-cy="cards-grid"]'))
            )
            
            print("Starting infinite scroll...")
            self.infinite_scroll(driver)
            
            # Extract all project URLs
            urls = self.extract_project_urls(driver)
            
            print(f"\nTotal unique project URLs found: {len(urls)}")
            return sorted(list(urls))
            
        except Exception as e:
            print(f"Error during scraping: {e}")
            raise
        finally:
            driver.quit()
    
    def infinite_scroll(self, driver):
        """Handle infinite scroll until no new content loads"""
        max_attempts = 100
        
        for attempt in range(max_attempts):
            # Count current projects
            current_count = len(driver.find_elements(By.CSS_SELECTOR, '[data-cy="project-card"]'))
            print(f"Scroll attempt {attempt + 1}: {current_count} projects loaded")
            
            # Check if new projects loaded
            if current_count == self.last_count:
                self.no_change_count += 1
                if self.no_change_count >= 3:
                    print("No new projects loaded after 3 attempts. Finished scrolling.")
                    break
            else:
                self.no_change_count = 0
                self.last_count = current_count
            
            # Scroll to bottom
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            
            # Wait for new content
            time.sleep(2)
    
    def extract_project_urls(self, driver):
        """Extract all project URLs from the page"""
        project_cards = driver.find_elements(By.CSS_SELECTOR, '[data-cy="project-card"]')
        urls = set()
        
        for card in project_cards:
            href = card.get_attribute('href')
            if href and '//' in href:
                # Extract path from full URL
                path = href.split('kitspace.org')[-1]
                if path.startswith('/'):
                    urls.add(path)
        
        return urls
    
    def save_results(self, urls, filename='kitspace_projects.json'):
        """Save results to JSON file"""
        results = {
            'timestamp': datetime.now().isoformat(),
            'total_projects': len(urls),
            'projects': [
                {
                    'url': url,
                    'full_url': f'https://kitspace.org{url}'
                }
                for url in urls
            ]
        }
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"Results saved to {filename}")
        return results
    
    def analyze_results(self, urls):
        """Analyze projects by organization"""
        by_org = defaultdict(list)
        
        for url in urls:
            parts = url.split('/')
            if len(parts) >= 2:
                org = parts[1]
                by_org[org].append(url)
        
        print("\nTop organizations by project count:")
        sorted_orgs = sorted(by_org.items(), key=lambda x: len(x[1]), reverse=True)
        for org, projects in sorted_orgs[:10]:
            print(f"{org}: {len(projects)} projects")
        
        return by_org

class LightweightScraper:
    """Faster scraper for initial page only (no infinite scroll)"""
    
    def scrape_initial_projects(self):
        """Scrape just the initial page load"""
        try:
            response = requests.get('https://kitspace.org/', timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all project cards
            project_cards = soup.find_all('a', {'data-cy': 'project-card'})
            urls = []
            
            for card in project_cards:
                href = card.get('href')
                if href and href.startswith('/'):
                    urls.append(href)
            
            return sorted(list(set(urls)))
            
        except Exception as e:
            print(f"Lightweight scraping failed: {e}")
            return []

def main():
    """Main execution function"""
    print("Kitspace Project Scraper")
    print("1. Full scrape (with infinite scroll)")
    print("2. Quick scrape (initial page only)")
    
    choice = input("Choose option (1 or 2): ").strip()
    
    if choice == "2":
        # Quick scrape
        scraper = LightweightScraper()
        urls = scraper.scrape_initial_projects()
        print(f"Found {len(urls)} initial projects")
        
        # Save and display results
        results = {
            'timestamp': datetime.now().isoformat(),
            'total_projects': len(urls),
            'projects': [{'url': url, 'full_url': f'https://kitspace.org{url}'} for url in urls]
        }
        
        with open('kitspace_initial_projects.json', 'w') as f:
            json.dump(results, f, indent=2)
        
    else:
        # Full scrape
        scraper = KitspaceScraper(headless=True)
        urls = scraper.scrape_all_projects()
        
        # Save results
        scraper.save_results(urls)
        
        # Analyze results
        scraper.analyze_results(urls)
    
    # Display sample results
    print(f"\nFirst 10 project URLs:")
    for i, url in enumerate(urls[:10], 1):
        print(f"{i}. https://kitspace.org{url}")

if __name__ == "__main__":
    main()