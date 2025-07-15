import xml.etree.ElementTree as ET
import json
import re

def extract_articles(xml_file_path):
    tree = ET.parse(xml_file_path)
    root = tree.getroot()
    
    articles = []
    for article in root.findall('.//article'):
        article_data = {
            'paper_title': extract_title(article),
            'specifications_table': extract_specifications_table(article),
            'bill_of_materials': extract_bill_of_materials(article),
            'repository_references': extract_repository_references(article)
        }
        articles.append(article_data)
    
    return articles

def extract_title(article):
    title_elem = article.find('.//article-title')
    if title_elem is not None:
        return clean_text(title_elem.text or '')
    return ''

def extract_specifications_table(article):
    specs = {}
    
    # First try: look for sections with "specifications table" in title
    for section in article.findall('.//sec'):
        title_elem = section.find('.//title')
        if title_elem is not None and 'specifications table' in (title_elem.text or '').lower():
            table = section.find('.//table')
            if table is not None:
                specs = parse_specifications_table(table)
                if specs:
                    break
    
    # Second try: look for paragraphs containing "specifications table" and find nearby tables
    if not specs:
        for p in article.findall('.//p'):
            # Check all text content in the paragraph, not just direct text
            p_text_parts = []
            for text in p.itertext():
                if text.strip():
                    p_text_parts.append(text.strip())
            p_full_text = ' '.join(p_text_parts).lower()
            
            if 'specifications table' in p_full_text:
                # Look for table in the same paragraph or table-wrap
                table = p.find('.//table')
                if table is not None:
                    specs = parse_specifications_table(table)
                    if specs:
                        break
    
    # Third try: look for tables that look like specifications tables
    if not specs:
        for table in article.findall('.//table'):
            # Check if this looks like a specs table by examining all rows for indicators
            is_specs_table = False
            
            # First, check if any cell contains "specifications table"
            for row in table.findall('.//tr'):
                for cell in row.findall('.//td') + row.findall('.//th'):
                    cell_text_parts = []
                    for text in cell.itertext():
                        if text.strip():
                            cell_text_parts.append(text.strip())
                    cell_full_text = ' '.join(cell_text_parts).lower()
                    if 'specifications table' in cell_full_text:
                        is_specs_table = True
                        break
                if is_specs_table:
                    break
            
            # If not found by "specifications table", check for typical specs keywords
            if not is_specs_table:
                specs_keywords = ['hardware name', 'subject area', 'hardware type', 'cost', 'license']
                for row in table.findall('.//tr'):
                    cells = row.findall('.//td') + row.findall('.//th')
                    if len(cells) >= 1:
                        first_cell_text_parts = []
                        for text in cells[0].itertext():
                            if text.strip():
                                first_cell_text_parts.append(text.strip())
                        first_cell_text = ' '.join(first_cell_text_parts).lower()
                        if any(keyword in first_cell_text for keyword in specs_keywords):
                            is_specs_table = True
                            break
            
            if is_specs_table:
                specs = parse_specifications_table(table)
                if specs:
                    break
    
    return specs

def parse_specifications_table(table):
    """Parse a specifications table and return key-value pairs."""
    specs = {}
    
    # Look for table rows
    rows = table.findall('.//tr')
    for row in rows:
        cells = row.findall('.//td') + row.findall('.//th')
        if len(cells) >= 2:
            # Extract key from first cell
            key_parts = []
            for text in cells[0].itertext():
                if text.strip():
                    key_parts.append(text.strip())
            key = ' '.join(key_parts)
            
            # Extract value from second cell
            value = get_cell_value_with_links(cells[1])
            
            # Skip header rows that span multiple columns or contain "specifications table"
            if (key and value and 
                'specifications table' not in key.lower() and
                not (len(cells) == 1 and cells[0].get('colspan'))):
                specs[key] = value
    
    return specs

def extract_bill_of_materials(article):
    bom = []
    
    # First try: look for sections with "bill of materials" in title
    for section in article.findall('.//sec'):
        title_elem = section.find('.//title')
        if title_elem is not None and 'bill of materials' in (title_elem.text or '').lower():
            table = section.find('.//table')
            if table is not None:
                bom = parse_bill_of_materials_table(table)
                if bom:
                    break
    
    # Second try: prioritize table captions with "bill of materials" 
    if not bom:
        bom_tables = []
        for caption in article.findall('.//caption'):
            caption_text_parts = []
            for text in caption.itertext():
                if text.strip():
                    caption_text_parts.append(text.strip())
            caption_full_text = ' '.join(caption_text_parts).lower()
            
            if 'bill of materials' in caption_full_text or 'bill of material' in caption_full_text:
                # Find the table associated with this caption
                table_wrap = caption.getparent() if hasattr(caption, 'getparent') else None
                if table_wrap is not None:
                    table = table_wrap.find('.//table')
                    if table is not None:
                        parsed_bom = parse_bill_of_materials_table(table)
                        if parsed_bom:
                            bom_tables.append(parsed_bom)
        
        # If we found multiple BOM tables, combine them or take the largest one
        if bom_tables:
            # Take the table with the most entries
            bom = max(bom_tables, key=len)
    
    # Third try: look for paragraphs containing "bill of materials" (only if no caption match)
    if not bom:
        for p in article.findall('.//p'):
            p_text_parts = []
            for text in p.itertext():
                if text.strip():
                    p_text_parts.append(text.strip())
            p_full_text = ' '.join(p_text_parts).lower()
            
            if 'bill of materials' in p_full_text or 'bill of material' in p_full_text:
                table = p.find('.//table')
                if table is not None:
                    # Make sure this isn't a design files table by checking headers
                    parsed_bom = parse_bill_of_materials_table(table)
                    if parsed_bom and is_valid_bom_table(parsed_bom):
                        bom = parsed_bom
                        break
    
    return bom

def parse_bill_of_materials_table(table):
    """Parse a bill of materials table and return list of component dictionaries."""
    bom = []
    
    # Extract headers
    headers = []
    header_row = table.find('.//thead//tr') or table.find('.//tr')
    if header_row is not None:
        for cell in header_row.findall('.//th') + header_row.findall('.//td'):
            # Extract all text including from nested elements like <bold>
            header_parts = []
            for text in cell.itertext():
                if text.strip():
                    header_parts.append(text.strip())
            header_text = ' '.join(header_parts)
            headers.append(clean_text(header_text))
    
    # Extract data rows
    tbody = table.find('.//tbody')
    if tbody is not None:
        rows = tbody.findall('.//tr')
    else:
        # If no tbody, get all rows except the first (header) row
        all_rows = table.findall('.//tr')
        rows = all_rows[1:] if len(all_rows) > 1 else []
    
    for row in rows:
        cells = row.findall('.//td') + row.findall('.//th')
        if cells:
            item = {}
            for i, cell in enumerate(cells):
                header = headers[i] if i < len(headers) else f'column_{i}'
                value = get_cell_value_with_links(cell)
                item[header] = value
            
            # Only add rows that have meaningful content (not just empty cells or totals)
            if any(v.strip() for v in item.values()) and not is_total_row(item):
                bom.append(item)
    
    return bom

def is_total_row(item):
    """Check if this row is a total/summary row that should be skipped."""
    for key, value in item.items():
        if key.lower() in ['total', 'grand total', 'subtotal'] or value.lower() in ['total', 'grand total', 'subtotal']:
            return True
        # Check if all cells except the last few are empty (typical of total rows)
        non_empty_values = [v for v in item.values() if v.strip()]
        if len(non_empty_values) <= 2 and any('total' in v.lower() for v in non_empty_values):
            return True
    return False

def is_valid_bom_table(bom_data):
    """Check if the extracted table is actually a bill of materials table, not a design files table."""
    if not bom_data:
        return False
    
    # Check the headers to see if this looks like a BOM table
    first_item = bom_data[0] if bom_data else {}
    headers = list(first_item.keys())
    
    # Common BOM headers
    bom_indicators = [
        'designator', 'component', 'part', 'number', 'quantity', 
        'cost', 'price', 'total', 'source', 'supplier', 'material'
    ]
    
    # Design files table headers (things we want to avoid)
    design_file_indicators = [
        'design file name', 'file type', 'location of the file'
    ]
    
    # Count matches
    bom_matches = sum(1 for header in headers for indicator in bom_indicators 
                     if indicator in header.lower())
    design_matches = sum(1 for header in headers for indicator in design_file_indicators 
                        if indicator in header.lower())
    
    # If we have design file indicators, this is probably not a BOM table
    if design_matches > 0:
        return False
    
    # If we have BOM indicators, this is probably a BOM table
    if bom_matches >= 2:  # Need at least 2 BOM-like headers
        return True
    
    return False

def extract_repository_references(article):
    references = []
    platforms = ['github', 'gitlab', 'zenodo']
    seen_links = set()
    seen_contexts = set()
    
    # Search through all external links first
    for link in article.findall('.//ext-link'):
        href = link.get('xlink:href') or link.get('href') or ''
        link_text = clean_text(''.join(link.itertext()) or '')
        
        for platform in platforms:
            if platform.lower() in href.lower() or platform.lower() in link_text.lower():
                if href and href not in seen_links:
                    context = get_link_context(link)
                    references.append({
                        'platform': platform,
                        'context': context,
                        'link': href,
                        'link_text': link_text
                    })
                    seen_links.add(href)
                    seen_contexts.add(context[:50])
    
    # Search through text content for platform mentions (only if no link found)
    for elem in article.iter():
        if elem.text:
            text_lower = elem.text.lower()
            for platform in platforms:
                if platform in text_lower:
                    context = get_text_context(elem)
                    context_start = context[:50] if context else ''
                    # Only add if we haven't seen this context before
                    if context_start and context_start not in seen_contexts:
                        references.append({
                            'platform': platform,
                            'context': context,
                            'link': None,
                            'link_text': ''
                        })
                        seen_contexts.add(context_start)
    
    return references

def get_cell_value_with_links(cell):
    # Get all text content from the cell, including nested elements
    text_parts = []
    for text in cell.itertext():
        if text.strip():
            text_parts.append(text.strip())
    value = ' '.join(text_parts)
    
    # Add links found in cell
    for link in cell.findall('.//ext-link'):
        href = link.get('xlink:href') or link.get('href')
        if href and href not in value:
            value += f" [{href}]"
    
    return clean_text(value)

def get_link_context(link):
    # Try to get parent paragraph or section
    parent = link
    for _ in range(5):  # Go up max 5 levels
        if hasattr(parent, 'getparent'):
            parent = parent.getparent()
        else:
            break
        if parent is None:
            break
        if parent.tag in ['p', 'sec', 'td', 'th']:
            text_parts = []
            for text in parent.itertext():
                if text.strip():
                    text_parts.append(text.strip())
            full_text = ' '.join(text_parts)
            return clean_text(full_text)[:300] if full_text else ''
    
    # Fallback: return the link's own text
    link_text = ''.join(link.itertext()).strip()
    return clean_text(link_text) if link_text else ''

def get_text_context(element):
    parent = element
    if hasattr(element, 'getparent'):
        parent = element.getparent()
    if parent is not None:
        text_parts = []
        for text in parent.itertext():
            if text.strip():
                text_parts.append(text.strip())
        full_text = ' '.join(text_parts)
        return clean_text(full_text)[:200] if full_text else ''
    
    # Fallback to element's own text
    element_text = element.text or ''
    return clean_text(element_text)

def clean_text(text):
    if not text:
        return ''
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def main():
    xml_file = 'data/ohx-allPubs.xml'
    articles = extract_articles(xml_file)
    
    with open('extracted_articles.json', 'w', encoding='utf-8') as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)
    
    return articles

if __name__ == "__main__":
    main()