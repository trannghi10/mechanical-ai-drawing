with open("backend/services/change_service.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print(f"Total lines in change_service.py: {len(lines)}")

# Search for relevant keywords
keywords = ["unresolved", "complete_product_backup", "candidate_assemblies", "assembly_projection", "co_stretch", "propagate"]
matches = []
for i, line in enumerate(lines):
    for kw in keywords:
        if kw in line.lower():
            matches.append((i+1, kw, line.strip()))
            break

print(f"Found {len(matches)} matches")
for line_no, kw, line in matches[:30]:
    print(f"Line {line_no} [{kw}]: {line[:100]}")
