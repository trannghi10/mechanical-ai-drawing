import json

plan_path = "storage/documents/5a1955b75d4345b69d19d38b7cfaf75c/change-plans/460befa818244c0b8ba0b7d0db0c9f1f.json"
with open(plan_path, "r", encoding="utf-8") as f:
    plan = json.load(f)

print("Targets:", ascii(str(plan.get("targets"))))
print("Root target ids:", ascii(str(plan.get("root_target_ids"))))
print("Root BOM refs:", ascii(str(plan.get("root_bom_refs"))))
print("Scope links:", ascii(str(plan.get("scope_links"))))
print("Review only ids:", ascii(str(plan.get("review_only_ids"))))
print("Fulfillment review:", ascii(json.dumps(plan.get("fulfillment_review", []), indent=2)))
print("Edit gate:", ascii(json.dumps(plan.get("edit_gate", {}), indent=2)))
