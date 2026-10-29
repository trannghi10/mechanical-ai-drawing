# -*- coding: utf-8 -*-
import json

with open('scratch/dauphine_plan.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

p = d['plan']
with open('scratch/inner_plan.txt', 'w', encoding='utf-8') as out:
    out.write(f"summary: {p.get('summary')}\n")
    out.write(f"target_part: {p.get('target_part')}\n")
    out.write(f"edits: {len(p.get('edits', []))}\n")
    out.write(f"dependencies: {len(p.get('dependencies', []))}\n")
    out.write(f"operations: {len(p.get('operations', []))}\n")
    out.write(f"questions: {p.get('questions')}\n")
    out.write(f"warnings: {p.get('warnings')}\n")
    out.write(f"resize_recipes: {len(p.get('resize_recipes', []))}\n")
    out.write(f"curved_wall_recipes: {len(p.get('curved_wall_recipes', []))}\n")

print('Done')
