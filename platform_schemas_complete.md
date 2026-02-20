# Complete Platform Schema Documentation

## 1. OpenHardware.io

### Project Fields
- `project_name` - Project title
- `project_url` - Platform URL  
- `project_author` - Creator name
- `license` - License type
- `created` - Creation date (empty in examples)
- `updated` - Update date (empty in examples)
- `views` - View count
- `github` - GitHub repository URL
- `homepage` - External website URL

### Statistics Object
- `statistics.likes` - Like count
- `statistics.collects` - Collection count  
- `statistics.comments` - Comment count
- `statistics.downloads` - Download count

### Design Files Array
Each file contains:
- `name` - File name
- `size` - File size with units
- `downloads` - Download count for individual file

### Bill of Materials Array
Variable structure, but typically includes:
- `Designator` - Component reference
- `Mid X` - X coordinate
- `Mid Y` - Y coordinate  
- `Layer` - PCB layer
- `Rotation` - Component rotation
- Plus 19 unnamed columns (`Column_6` through `Column_19`)

### Other Fields
- `total_cost` - Total project cost (often null)

## 2. Kitspace

### Project Fields
- `url` - Kitspace project URL
- `project_name` - Project name
- `repository_link` - GitHub/GitLab repository URL
- `description` - Project description
- `gerber_file_link` - Link to Tracespace PCB viewer
- `error` - Processing error message (null if successful)

### Bill of Materials Array
Each BOM item contains:
- `reference` - Component designator (R1, C1, etc.)
- `quantity` - Number of components
- `description` - Component description
- `manufacturer` - Manufacturer name
- `mpn` - Manufacturer part number

### Retailers Object (within each BOM item)
- `retailers.Digikey` - Digikey part number
- `retailers.Mouser` - Mouser part number
- `retailers.RS` - RS Components part number
- `retailers.Newark` - Newark part number
- `retailers.Farnell` - Farnell part number
- `retailers.LCSC` - LCSC part number
- `retailers.JLC Assembly` - JLC Assembly part number

## 3. Hackaday.io

### Project Fields
- `title` - Project title
- `summary` - Brief project summary
- `description` - Full project description
- `image` - Project image URL
- `userName` - Creator's username
- `userId` - Creator's user ID
- `type` - Content type (e.g., "project project")
- `id` - Project ID
- `rid` - Resource ID
- `created` - Creation timestamp
- `updated` - Last update timestamp
- `followersCount` - Number of followers
- `likesCount` - Number of likes
- `viewsCount` - Number of views
- `tags` - Array of project tags
- `components` - Array of component names
- `_version_` - Version number
- `feedChecked` - Feed check status
- `location` - Project location
- `body` - Project body content
- `projectId` - Alternative project ID
- `projectName` - Alternative project name field
- `url` - Project URL
- `github_links` - GitHub repository links

## 4. OSHWA (Open Source Hardware Association)

### Certification Fields
- `oshwaUid` - Unique OSHWA certification ID (e.g., "US000001")
- `responsibleParty` - Certifying entity/person
- `country` - Country code
- `publicContact` - Public contact email

### Project Fields
- `projectName` - Project name
- `projectWebsite` - Project website URL
- `projectVersion` - Version number
- `projectDescription` - Project description
- `certificationDate` - ISO format certification date
- `previousVersions` - Array of previous version UIDs

### Categorization
- `primaryType` - Primary hardware type
- `additionalType` - Array of additional types
- `projectKeywords` - Array of keywords

### Documentation & Licensing
- `citations` - Array of citations
- `documentationUrl` - Documentation URL
- `hardwareLicense` - Hardware license type
- `softwareLicense` - Software license type
- `documentationLicense` - Documentation license type

## 5. GitLab Repository

### Repository Fields
- `id` - Repository ID
- `description` - Repository description
- `name` - Repository name
- `name_with_namespace` - Full repository name with namespace
- `path` - Repository path
- `path_with_namespace` - Full path with namespace
- `created_at` - Creation timestamp
- `default_branch` - Default branch name
- `tag_list` - List of tags
- `topics` - Array of topics
- `ssh_url_to_repo` - SSH clone URL
- `http_url_to_repo` - HTTP clone URL
- `web_url` - Web interface URL
- `readme_url` - README file URL
- `forks_count` - Number of forks
- `star_count` - Number of stars
- `empty_repo` - Boolean for empty repository
- `archived` - Boolean for archived status
- `visibility` - Visibility level
- `creator_id` - Creator's user ID
- `open_issues_count` - Number of open issues

### Namespace Fields
- `namespace.id` - Namespace ID
- `namespace.name` - Namespace name
- `namespace.path` - Namespace path
- `namespace.kind` - Namespace type
- `namespace.full_path` - Full namespace path
- `namespace.parent_id` - Parent namespace ID
- `namespace.web_url` - Namespace web URL

## 6. Open Hardware X (Academic Journal)

### Paper Fields
- `paper_title` - Academic paper title

### Specifications Table Object
- `specifications_table.Hardware name` - Device/project name
- `specifications_table.Subject area` - Research field/discipline
- `specifications_table.Hardware type` - Type of hardware
- `specifications_table.Closest commercial analog` - Commercial equivalent
- `specifications_table.Open source license` - License type
- `specifications_table.Cost of hardware` - Total cost with currency
- `specifications_table.Source file repository` - Repository DOI or URL
- `specifications_table.Open-source license` - Alternative license field

### Bill of Materials Array
Variable structure across papers:

**Style 1 (Components with designators):**
- `Designator` - Component reference
- `Component` - Component type
- `Qty` - Quantity
- `Unit cost` - Price per unit
- `Total cost` - Line total
- `Source of materials` - Supplier link

**Style 2 (Components with comments):**
- `Designator` - Component references
- `Comment` - Component description
- `Quantity` - Number needed
- `Cost/unit (USD)` - Unit price in USD
- `Total cost (USD)` - Line total in USD
- `Supplier` - Supplier name
- `Supplier Part No.` - Supplier part number

**Style 3 (Simple structure):**
- `Component` - Component name/type
- `Specification` - Component specifications
- `Unit cost (€)` - Unit price in EUR
- `Total (€)` - Line total in EUR

### Repository References Array
Each reference contains:
- `platform` - Platform name (e.g., "zenodo")
- `context` - Reference context/URL
- `link` - Direct link (often null)
- `link_text` - Link display text

## 7. Journal of Open Hardware
*Note: Specific schema not provided in examples, but expected to be similar to Open Hardware X with fields like:*
- `title` - Paper title
- `abstract` - Paper abstract
- `authors` - Author list
- `doi_url` - DOI URL
- `hardware_cost` - Total hardware cost
- `license` - License type
- `published_date` - Publication date
- `repository` - Repository URL

## 8. MDPI Hardware
*Note: Specific schema not provided in examples, but expected to be similar to other journals with fields like:*
- `paper_title` - Paper title
- `abstract` - Paper abstract
- `authors` - Author list
- `doi` - Digital Object Identifier
- `total_cost` - Total project cost
- `license` - License type
- `publication_date` - Publication date
- `code_repository` - Code repository URL

## Common Patterns Across Platforms

### Identifiers
- Most platforms use numeric IDs internally
- Academic platforms use DOIs
- OSHWA uses structured UIDs

### Timestamps
- Unix timestamps: Hackaday
- ISO format: OSHWA, GitLab
- Empty/missing: OpenHardware.io

### Social Metrics
- Named differently: likes/stars, followers/watchers
- Not all platforms track engagement

### BOMs
- Highly variable structure
- Different currency formats
- Supplier data ranges from none to comprehensive

### Licensing
- Single field: Most platforms
- Multiple fields: OSHWA (hardware, software, documentation)
- Nested in table: Academic journals