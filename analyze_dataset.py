#!/usr/bin/env python3
"""
Descriptive Statistics Analysis for OHX Dataset
"""

import json
import pandas as pd
import numpy as np
import re
from collections import Counter, defaultdict
import matplotlib.pyplot as plt
import seaborn as sns

def load_data(file_path):
    """Load JSON data from file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

def extract_cost_value(cost_str):
    """Extract numeric cost value from cost string"""
    if not cost_str or pd.isna(cost_str):
        return None
    
    # Remove common currency symbols and clean the string
    cost_str = str(cost_str).strip()
    
    # Handle ranges (take the first value)
    if '-' in cost_str and not cost_str.startswith('-'):
        cost_str = cost_str.split('-')[0].strip()
    
    # Extract numeric values using regex
    numbers = re.findall(r'[\d,]+\.?\d*', cost_str)
    if numbers:
        # Remove commas and convert to float
        try:
            value = float(numbers[0].replace(',', ''))
            return value
        except ValueError:
            return None
    return None

def extract_currency(cost_str):
    """Extract currency from cost string"""
    if not cost_str or pd.isna(cost_str):
        return None
    
    cost_str = str(cost_str).strip()
    
    # Common currency patterns
    if '$' in cost_str or 'USD' in cost_str.upper():
        return 'USD'
    elif '€' in cost_str or 'EUR' in cost_str.upper():
        return 'EUR'
    elif '£' in cost_str or 'GBP' in cost_str.upper():
        return 'GBP'
    else:
        return 'Unknown'

def analyze_subject_areas(data):
    """Analyze subject areas distribution"""
    subject_areas = []
    for project in data:
        spec_table = project.get('specifications_table', {})
        subject_area = spec_table.get('Subject area', '')
        if subject_area:
            # Split by bullet points and clean
            areas = re.split(r'[•·\n]', subject_area)
            for area in areas:
                area = area.strip()
                if area and len(area) > 3:  # Filter out very short entries
                    subject_areas.append(area)
    
    return Counter(subject_areas)

def analyze_hardware_types(data):
    """Analyze hardware types distribution"""
    hardware_types = []
    for project in data:
        spec_table = project.get('specifications_table', {})
        hw_type = spec_table.get('Hardware type', '')
        if hw_type:
            # Split by bullet points and clean
            types = re.split(r'[•·\n]', hw_type)
            for hw_t in types:
                hw_t = hw_t.strip()
                if hw_t and len(hw_t) > 3:
                    hardware_types.append(hw_t)
    
    return Counter(hardware_types)

def analyze_licenses(data):
    """Analyze open source licenses"""
    licenses = []
    for project in data:
        spec_table = project.get('specifications_table', {})
        license_field = spec_table.get('Open source license', '') or spec_table.get('Open-source license', '')
        if license_field:
            licenses.append(license_field.strip())
    
    return Counter(licenses)

def analyze_costs(data):
    """Analyze hardware costs"""
    costs = []
    currencies = []
    
    for project in data:
        spec_table = project.get('specifications_table', {})
        cost_field = spec_table.get('Cost of hardware', '')
        
        if cost_field:
            cost_value = extract_cost_value(cost_field)
            currency = extract_currency(cost_field)
            
            if cost_value is not None:
                costs.append(cost_value)
                currencies.append(currency)
    
    return costs, currencies

def analyze_repositories(data):
    """Analyze source file repositories"""
    repo_types = []
    repo_count = 0
    
    for project in data:
        spec_table = project.get('specifications_table', {})
        repo_field = spec_table.get('Source file repository', '') or spec_table.get('Source File Repository', '')
        
        if repo_field and repo_field.strip():
            repo_count += 1
            repo_field = repo_field.lower()
            
            if 'osf.io' in repo_field or 'osf' in repo_field:
                repo_types.append('OSF')
            elif 'zenodo' in repo_field:
                repo_types.append('Zenodo')
            elif 'mendeley' in repo_field or '10.17632' in repo_field:
                repo_types.append('Mendeley Data')
            elif 'github' in repo_field:
                repo_types.append('GitHub')
            elif 'figshare' in repo_field:
                repo_types.append('Figshare')
            else:
                repo_types.append('Other')
    
    return repo_count, Counter(repo_types)

def analyze_bill_of_materials(data):
    """Analyze bill of materials statistics"""
    bom_lengths = []
    projects_with_bom = 0
    
    for project in data:
        bom = project.get('bill_of_materials', [])
        if bom:
            projects_with_bom += 1
            bom_lengths.append(len(bom))
    
    return projects_with_bom, bom_lengths

def print_statistics():
    """Main function to print all statistics"""
    print("="*60)
    print("OHX DATASET DESCRIPTIVE STATISTICS")
    print("="*60)
    
    # Load data
    file_path = '/Users/nmweber/Desktop/OSH_Datasets/data/cleaned/ohx_allPubs_extract.json'
    data = load_data(file_path)
    
    print(f"\n📊 BASIC DATASET INFORMATION")
    print(f"Total number of projects: {len(data)}")
    
    # Analyze costs
    print(f"\n💰 COST ANALYSIS")
    costs, currencies = analyze_costs(data)
    if costs:
        costs_array = np.array(costs)
        print(f"Projects with cost information: {len(costs)}")
        print(f"Cost statistics:")
        print(f"  - Mean: ${costs_array.mean():.2f}")
        print(f"  - Median: ${np.median(costs_array):.2f}")
        print(f"  - Min: ${costs_array.min():.2f}")
        print(f"  - Max: ${costs_array.max():.2f}")
        print(f"  - Standard deviation: ${costs_array.std():.2f}")
        
        print(f"\nCurrency distribution:")
        currency_counter = Counter(currencies)
        for currency, count in currency_counter.most_common():
            print(f"  - {currency}: {count} ({count/len(currencies)*100:.1f}%)")
    
    # Analyze repositories
    print(f"\n🗂️  REPOSITORY ANALYSIS")
    repo_count, repo_types = analyze_repositories(data)
    print(f"Projects with repository information: {repo_count}")
    print(f"Repository type distribution:")
    for repo_type, count in repo_types.most_common():
        print(f"  - {repo_type}: {count} ({count/repo_count*100:.1f}%)")
    
    # Analyze subject areas
    print(f"\n🔬 SUBJECT AREAS (Top 10)")
    subject_areas = analyze_subject_areas(data)
    for area, count in subject_areas.most_common(10):
        print(f"  - {area}: {count}")
    
    # Analyze hardware types
    print(f"\n🔧 HARDWARE TYPES (Top 10)")
    hw_types = analyze_hardware_types(data)
    for hw_type, count in hw_types.most_common(10):
        print(f"  - {hw_type}: {count}")
    
    # Analyze licenses
    print(f"\n📄 OPEN SOURCE LICENSES (Top 10)")
    licenses = analyze_licenses(data)
    for license_type, count in licenses.most_common(10):
        print(f"  - {license_type}: {count}")
    
    # Analyze bill of materials
    print(f"\n📋 BILL OF MATERIALS ANALYSIS")
    projects_with_bom, bom_lengths = analyze_bill_of_materials(data)
    print(f"Projects with bill of materials: {projects_with_bom}")
    if bom_lengths:
        bom_array = np.array(bom_lengths)
        print(f"BOM statistics:")
        print(f"  - Mean components: {bom_array.mean():.1f}")
        print(f"  - Median components: {np.median(bom_array):.1f}")
        print(f"  - Min components: {bom_array.min()}")
        print(f"  - Max components: {bom_array.max()}")
        print(f"  - Standard deviation: {bom_array.std():.1f}")
    
    # Repository references analysis
    print(f"\n🔗 REPOSITORY REFERENCES ANALYSIS")
    repo_refs_count = 0
    platform_counter = Counter()
    
    for project in data:
        repo_refs = project.get('repository_references', [])
        if repo_refs:
            repo_refs_count += len(repo_refs)
            for ref in repo_refs:
                platform = ref.get('platform', 'Unknown')
                platform_counter[platform] += 1
    
    print(f"Total repository references: {repo_refs_count}")
    print(f"Platform distribution:")
    for platform, count in platform_counter.most_common():
        print(f"  - {platform}: {count} ({count/repo_refs_count*100:.1f}%)")
    
    print(f"\n" + "="*60)
    print("ANALYSIS COMPLETE")
    print("="*60)

if __name__ == "__main__":
    print_statistics()