# -*- coding: utf-8 -*-
import json

with open('scratch/dauphine_plan.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

with open('scratch/plan_keys.txt', 'w', encoding='utf-8') as out:
    for k, v in d.items():
        if isinstance(v, (str, int, float, bool, type(None))):
            out.write(f'{k}: {v}\n')
        elif isinstance(v, list):
            out.write(f'{k}: list of {len(v)}\n')
        elif isinstance(v, dict):
            out.write(f'{k}: dict with keys {list(v.keys())[:5]}\n')

print('Done')
