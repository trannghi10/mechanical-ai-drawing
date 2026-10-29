import os, shutil, json
from pathlib import Path

doc_dir = Path('storage/documents/5a1955b75d4345b69d19d38b7cfaf75c/revisions')
cleaned_jobs = 0
cleaned_dirs = 0

for rev in doc_dir.iterdir():
    if not rev.is_dir(): continue
    
    # Remove export-selection dir
    sel_dir = rev / 'export-selection'
    if sel_dir.exists():
        shutil.rmtree(sel_dir, ignore_errors=True)
        cleaned_dirs += 1
        print(f"Removed export-selection in {rev.name[:8]}")
        
    # Remove reopen-selection dir
    reopen_sel = rev / 'reopen-selection'
    if reopen_sel.exists():
        shutil.rmtree(reopen_sel, ignore_errors=True)
        print(f"Removed reopen-selection in {rev.name[:8]}")
        
    # Remove selection jobs
    jobs_dir = rev / 'download-jobs'
    if jobs_dir.exists():
        for jf in list(jobs_dir.glob('*.json')):
            try:
                d = json.loads(jf.read_text(encoding='utf-8'))
                if d.get('scope') == 'selection' or 'export-selection' in d.get('file', ''):
                    jf.unlink()
                    cleaned_jobs += 1
                    print(f"Removed selection job {jf.name} in {rev.name[:8]}")
            except Exception as e:
                print(f"Error reading {jf}: {e}")

print(f"Total cleaned: {cleaned_dirs} dirs, {cleaned_jobs} jobs.")
