# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.abspath('.'))

base = r'd:\mechanical-ai-drawing\storage\documents'
found = []
for doc in os.listdir(base):
    p = os.path.join(base, doc, 'planning-jobs')
    if os.path.exists(p):
        for j in os.listdir(p):
            jf = os.path.join(p, j)
            try:
                with open(jf, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                    found.append({
                        'doc': doc,
                        'job': j,
                        'request': d.get('request'),
                        'status': d.get('status'),
                        'message': d.get('message'),
                        'target_resolution': d.get('target_resolution'),
                        'time': os.path.getmtime(jf)
                    })
            except Exception as e:
                pass

found.sort(key=lambda x: x['time'], reverse=True)
with open(r'd:\mechanical-ai-drawing\scratch\recent_jobs.json', 'w', encoding='utf-8') as f:
    json.dump(found[:10], f, ensure_ascii=False, indent=2)

print('Saved recent jobs:', len(found))
