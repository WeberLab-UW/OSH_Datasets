import json
import csv
import sys

def json_to_csv(json_file_path, csv_file_path):
    """Convert JSON file to CSV with proper handling of nested structures."""
    
    with open(json_file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    
    if not data:
        print("No data found in JSON file")
        return
    
    fieldnames = [
        'project_name',
        'project_url', 
        'project_author',
        'license',
        'created',
        'updated',
        'views',
        'github',
        'homepage',
        'likes',
        'collects',
        'comments',
        'downloads',
        'design_files_count',
        'design_files',
        'bill_of_materials_count',
        'bill_of_materials',
        'total_cost'
    ]
    
    with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for item in data:
            row = {
                'project_name': item.get('project_name', ''),
                'project_url': item.get('project_url', ''),
                'project_author': item.get('project_author', ''),
                'license': item.get('license', ''),
                'created': item.get('created', ''),
                'updated': item.get('updated', ''),
                'views': item.get('views', ''),
                'github': item.get('github', ''),
                'homepage': item.get('homepage', ''),
                'total_cost': item.get('total_cost', '')
            }
            
            statistics = item.get('statistics', {})
            row['likes'] = statistics.get('likes', '')
            row['collects'] = statistics.get('collects', '')
            row['comments'] = statistics.get('comments', '')
            row['downloads'] = statistics.get('downloads', '')
            
            design_files = item.get('design_files', [])
            row['design_files_count'] = len(design_files)
            row['design_files'] = json.dumps(design_files) if design_files else ''
            
            bom = item.get('bill_of_materials', [])
            row['bill_of_materials_count'] = len(bom)
            row['bill_of_materials'] = json.dumps(bom) if bom else ''
            
            writer.writerow(row)
    
    print(f"Successfully converted {json_file_path} to {csv_file_path}")
    print(f"Processed {len(data)} projects")

def json_to_csv_expanded(json_file_path, output_prefix):
    """Create separate CSV files for main data, design files, and BOM."""
    
    with open(json_file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    
    if not data:
        print("No data found in JSON file")
        return
    
    main_fieldnames = [
        'project_name',
        'project_url',
        'project_author',
        'license',
        'created',
        'updated', 
        'views',
        'github',
        'homepage',
        'likes',
        'collects',
        'comments',
        'downloads',
        'total_cost'
    ]
    
    with open(f'{output_prefix}_main.csv', 'w', newline='', encoding='utf-8') as main_csv:
        main_writer = csv.DictWriter(main_csv, fieldnames=main_fieldnames)
        main_writer.writeheader()
        
        design_files_data = []
        bom_data = []
        
        for item in data:
            row = {
                'project_name': item.get('project_name', ''),
                'project_url': item.get('project_url', ''),
                'project_author': item.get('project_author', ''),
                'license': item.get('license', ''),
                'created': item.get('created', ''),
                'updated': item.get('updated', ''),
                'views': item.get('views', ''),
                'github': item.get('github', ''),
                'homepage': item.get('homepage', ''),
                'total_cost': item.get('total_cost', '')
            }
            
            statistics = item.get('statistics', {})
            row['likes'] = statistics.get('likes', '')
            row['collects'] = statistics.get('collects', '')
            row['comments'] = statistics.get('comments', '')
            row['downloads'] = statistics.get('downloads', '')
            
            main_writer.writerow(row)
            
            for design_file in item.get('design_files', []):
                design_file_row = {
                    'project_name': item.get('project_name', ''),
                    'file_name': design_file.get('name', ''),
                    'file_size': design_file.get('size', ''),
                    'file_downloads': design_file.get('downloads', '')
                }
                design_files_data.append(design_file_row)
            
            for bom_item in item.get('bill_of_materials', []):
                bom_row = {'project_name': item.get('project_name', '')}
                bom_row.update(bom_item)
                bom_data.append(bom_row)
    
    if design_files_data:
        with open(f'{output_prefix}_design_files.csv', 'w', newline='', encoding='utf-8') as df_csv:
            df_fieldnames = ['project_name', 'file_name', 'file_size', 'file_downloads']
            df_writer = csv.DictWriter(df_csv, fieldnames=df_fieldnames)
            df_writer.writeheader()
            df_writer.writerows(design_files_data)
        print(f"Created {output_prefix}_design_files.csv with {len(design_files_data)} entries")
    
    if bom_data:
        all_keys = set()
        for row in bom_data:
            all_keys.update(row.keys())
        bom_fieldnames = sorted(list(all_keys))
        
        with open(f'{output_prefix}_bom.csv', 'w', newline='', encoding='utf-8') as bom_csv:
            bom_writer = csv.DictWriter(bom_csv, fieldnames=bom_fieldnames)
            bom_writer.writeheader()
            bom_writer.writerows(bom_data)
        print(f"Created {output_prefix}_bom.csv with {len(bom_data)} entries")
    
    print(f"Created {output_prefix}_main.csv with {len(data)} projects")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Convert JSON hardware projects to CSV format')
    parser.add_argument('function', choices=['json_to_csv', 'json_to_csv_expanded'], 
                       help='Function to execute')
    parser.add_argument('input_file', help='Input JSON file path')
    parser.add_argument('output_prefix', help='Output file prefix (for expanded mode) or full CSV filename (for simple mode)')
    
    args = parser.parse_args()
    
    if args.function == 'json_to_csv':
        json_to_csv(args.input_file, args.output_prefix)
    elif args.function == 'json_to_csv_expanded':
        json_to_csv_expanded(args.input_file, args.output_prefix)