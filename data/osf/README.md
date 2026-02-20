# OSF Comprehensive Metadata Collection - Final Deliverables

## Overview
This directory contains the complete OSF (Open Science Framework) metadata collection system and dataset, developed through comprehensive API analysis and validation.

## Final Files

### 1. `osf_ohx_links.txt` (7.2KB)
- **Description**: Original OSF links extracted from OHX (Open Hardware eXtended) papers
- **Content**: 208 OSF project URLs in various formats (DOI, direct links, etc.)
- **Purpose**: Source data for the metadata collection project

### 2. `osf_project_urls_validated.txt` (2.7KB)
- **Description**: Normalized and validated OSF project URLs
- **Content**: 208 validated OSF project URLs in standardized `osf.io/[project_id]` format
- **Validation**: All URLs confirmed to return HTTP 200 status through multiple API endpoints
- **Success Rate**: 100% (208/208 projects accessible)

### 3. `osf_comprehensive_metadata_collector.py` (22.6KB)
- **Description**: Production-ready Python script for comprehensive OSF metadata collection
- **Features**:
  - Multi-endpoint support (nodes, registrations, preprints)
  - Comprehensive data collection (analytics, citations, licenses, file structures)
  - Rate limiting and error handling
  - Progress checkpointing
  - Recursive file structure crawling with download metrics
- **Usage**: `python3 osf_comprehensive_metadata_collector.py`

### 4. `osf_comprehensive_metadata_dataset.json` (2.2MB)
- **Description**: Complete metadata dataset for all 208 OSF projects
- **Success Rate**: 100% (208/208 projects successfully processed)
- **Data Collected Per Project**:
  - Basic metadata (title, description, dates, visibility)
  - Project classification (node/registration/preprint)
  - Contributors with permissions and bibliographic status
  - Subjects/disciplines and tags
  - License information (name, text, URL)
  - File structures with download metrics
  - Storage providers and analytics
  - Citation information
  - Activity logs and comprehensive metrics

## Key Achievements

### ✅ 100% Success Rate
- Successfully processed all 208 OSF projects
- Resolved all API endpoint issues (nodes vs registrations vs preprints)
- No failed requests in final dataset

### ✅ Comprehensive Data Collection
- **Analytics & Metrics**: Project analytics, activity logs, download counts
- **Citations**: Full citation information for all projects
- **Licenses**: Complete license details (name, text, URL)
- **File Structures**: Recursive file hierarchies with download metrics
- **Storage Providers**: All storage backends used by projects
- **Contributors**: Full contributor details with permissions and names

### ✅ Production Quality
- Robust error handling and rate limiting
- Multi-endpoint validation for different project types
- Progress checkpointing for large-scale collection
- Clean, documented, and maintainable code

## Technical Implementation

### Multi-Endpoint Strategy
The system automatically detects and handles three OSF project types:
1. **Nodes** (`/v2/nodes/{id}/`) - Regular OSF projects
2. **Registrations** (`/v2/registrations/{id}/`) - Registered/published projects  
3. **Preprints** (`/v2/preprints/{id}/`) - Preprint publications

### Data Validation
- All 208 original URLs validated through OSF API
- Multiple endpoint testing to ensure accessibility
- Comprehensive error handling for edge cases

### Performance Optimization
- Rate limiting (2-second delays) to respect OSF API guidelines
- Progress checkpointing every 5 projects
- Efficient recursive file structure traversal

## Usage Examples

### Loading the Dataset
```python
import json

with open('osf_comprehensive_metadata_dataset.json', 'r') as f:
    osf_projects = json.load(f)

print(f"Loaded {len(osf_projects)} OSF projects")

# Example: Find projects with the most downloads
projects_by_downloads = sorted(osf_projects, 
                              key=lambda x: x['metrics']['total_downloads'], 
                              reverse=True)
```

### Running the Collector
```bash
python3 osf_comprehensive_metadata_collector.py
```

## Dataset Schema
Each project in the dataset contains:
```json
{
  "project_id": "string",
  "url": "string", 
  "endpoint_type": "node|registration|preprint",
  "title": "string",
  "description": "string",
  "created": "ISO8601 datetime",
  "modified": "ISO8601 datetime",
  "public": boolean,
  "tags": ["string"],
  "category": "string",
  "license": {
    "name": "string",
    "text": "string", 
    "url": "string"
  },
  "subjects": [{"text": "string", "parents": ["string"]}],
  "metrics": {
    "total_downloads": integer,
    "activity_logs": integer,
    "contributor_count": integer,
    "file_count": integer,
    "storage_providers": ["string"]
  },
  "contributors": [{"name": "string", "permission": "string", "bibliographic": boolean}],
  "file_structure": {...},
  "analytics": {...},
  "citation": {...}
}
```

---
*Generated: July 23, 2025*
*Collection completed with 100% success rate (208/208 projects)*