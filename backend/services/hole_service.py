import json
from cad.geometry import near
from cad.hole_resize import resize


def compile_recipes(plan,context):
    if not plan.hole_recipes or plan.questions:return plan
    from backend.services.change_service import EditProposal
    by={o.ref:o for o in plan.operations};seen=set()
    for recipe in plan.hole_recipes:
        if recipe.circle_ref in seen:raise ValueError('Recipe lỗ trùng')
        seen.add(recipe.circle_ref)
        for op in resize(recipe,context):
            previous=by.get(op.ref)
            if previous and (previous.action!=op.action or not near(json.loads(previous.before),json.loads(op.before)) or not near(json.loads(previous.after),json.loads(op.after))):raise ValueError('Recipe lỗ xung đột thao tác: '+op.ref)
            if not previous:plan.operations.append(op);by[op.ref]=op
            plan.edits=[e for e in plan.edits if e.entity_ref!=op.ref]
            plan.edits.append(EditProposal(entity_ref=op.ref,part_number=recipe.part_code,purpose='geometry',before=op.before,after=op.after,reason=op.reason))
    return plan
