import pandas as pd
import json
import ast
import html
from typing import Any, Union

def clean_list_column(value: Any) -> str:
    if pd.isna(value) or value == '' or value is None:
        return '[]'
    
    value_str = str(value).strip()
    
    if value_str == '[]':
        return '[]'
    
    try:
        parsed_list = ast.literal_eval(value_str)
        return json.dumps(parsed_list, ensure_ascii=False)
    
    except (ValueError, SyntaxError):
        try:
            fixed_value = value_str.replace("'", '"')
            parsed_list = json.loads(fixed_value)
            return json.dumps(parsed_list, ensure_ascii=False)
        except:
            return json.dumps([value_str])

def clean_citations_column(value: Any) -> str:
    if pd.isna(value) or value == '' or value is None:
        return '[]'
    
    value_str = str(value).strip()
    
    if value_str == '[]':
        return '[]'
    
    try:
        parsed_citations = ast.literal_eval(value_str)
        return json.dumps(parsed_citations, ensure_ascii=False)
    
    except (ValueError, SyntaxError):
        return '[]'

def clean_html_entities(value: Any) -> str:
    if pd.isna(value) or value is None:
        return None
    
    value_str = str(value)
    return html.unescape(value_str)

def clean_text_field(value: Any) -> Union[str, None]:
    if pd.isna(value) or value == '':
        return None
    
    value_str = str(value).strip()
    value_str = html.unescape(value_str)
    
    return value_str if value_str else None

def clean_csv_for_postgres(input_file: str, output_file: str):
    df = pd.read_csv(input_file)
    
    list_columns = ['additionalType', 'projectKeywords']
    citation_columns = ['citations']
    
    for col in list_columns:
        if col in df.columns:
            df[col] = df[col].apply(clean_list_column)
    
    for col in citation_columns:
        if col in df.columns:
            df[col] = df[col].apply(clean_citations_column)
    
    text_columns = ['projectName', 'projectDescription', 'publicContact', 
                   'projectWebsite', 'documentationUrl', 'responsibleParty']
    
    for col in text_columns:
        if col in df.columns:
            df[col] = df[col].apply(clean_text_field)
    
    remaining_text_cols = df.select_dtypes(include=['object']).columns
    remaining_text_cols = [col for col in remaining_text_cols 
                          if col not in list_columns + citation_columns + text_columns]
    
    for col in remaining_text_cols:
        df[col] = df[col].apply(clean_text_field)
    
    df.to_csv(output_file, index=False, na_rep='NULL')

if __name__ == "__main__":
    input_csv = "OSHWA/OSHWA_projects.csv"
    output_csv = "OSHWA/OSHWA_projects_cleaned.csv"
    
    clean_csv_for_postgres(input_csv, output_csv)