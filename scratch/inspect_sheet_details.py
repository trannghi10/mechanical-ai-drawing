import sys
import os
sys.path.insert(0, os.path.abspath('.'))
import json
sys.stdout.reconfigure(encoding='utf-8')
from backend.storage import DocumentStore

doc_id = '34ee84f35e1a44fb81c56044397a0fff'
sheets = DocumentStore().load_sheets(doc_id)
print(f'Total sheets: {len(sheets)}')
target_ids = ['3AAABC', '3AC12B', '3B3987', '3ACF75', '3D337A', '3A0786', '3A2D0F', '3A3E3F', '3A3EDF', '3A499E', '3A5A28', '3A5ACA', '3A76E8', '3A7775']

for s in sheets:
    if s['id'] in target_ids:
        print(f"ID: #{s['id']}, current name: {s.get('name')}, codes: {s.get('source_codes')}")
        for t in s.get('texts', [])[:15]:
            print(f"   {repr(t)}")
        print('-'*40)
