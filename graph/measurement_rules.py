"""Solve source-measured linear constraints; never accept a model supplied constant."""
import math
import numpy as np
from pydantic import BaseModel, ConfigDict
from graph.fit_constraints import measurement


class MeasurementTerm(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dimension_ref: str
    coefficient: float


class MeasurementEquation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    terms: list[MeasurementTerm]
    evidence_refs: list[str]


def solve(context, equations, requested):
    records = {e['ref']: e for e in context['entities']}
    refs = set(requested)
    for equation in equations:
        if not equation.evidence_refs or not set(equation.evidence_refs) <= records.keys():
            raise ValueError('Phương trình liên kết thiếu bằng chứng trong phạm vi')
        terms = equation.terms
        if len(terms) < 2 or len({t.dimension_ref for t in terms}) != len(terms):
            raise ValueError('Phương trình cần các kích thước riêng biệt')
        if any(not math.isfinite(t.coefficient) or abs(t.coefficient) < 1e-12 for t in terms):
            raise ValueError('Hệ số ràng buộc không hợp lệ')
        if not {t.dimension_ref for t in terms} <= set(equation.evidence_refs):
            raise ValueError('Các kích thước phải nằm trong bằng chứng liên kết')
        refs.update(t.dimension_ref for t in terms)
    if not refs:
        return {}
    if len(refs)>64:
        raise ValueError('Quá nhiều kích thước trong một hệ ràng buộc')
    refs = sorted(refs)
    old = {}
    for ref in refs:
        record = records.get(ref, {})
        if record.get('dimension_type', 0) not in (0, 1) or not record.get('geometry'):
            raise ValueError('Ràng buộc chỉ hỗ trợ DIMENSION linear/aligned có geometry')
        if record['geometry'].get('text') not in ('', '<>'):
            raise ValueError('Không dùng kích thước có số ghi đè làm ràng buộc')
        old[ref] = measurement(record, record['geometry'])
    rows, rhs = [], []
    for equation in equations:
        coeffs = {term.dimension_ref: term.coefficient for term in equation.terms}
        rows.append([coeffs.get(ref, 0.) for ref in refs])
        rhs.append(sum(coeffs[ref] * old[ref] for ref in coeffs))
    for ref, value in requested.items():
        if not math.isfinite(value) or value <= 0:
            raise ValueError('Kích thước mới phải dương và hữu hạn')
        rows.append([1. if name == ref else 0. for name in refs])
        rhs.append(value)
    if not np.isfinite(rows).all() or not np.isfinite(rhs).all():
        raise ValueError('Hệ ràng buộc vượt giới hạn số học')
    if not rows or np.linalg.matrix_rank(rows) != len(refs):
        raise ValueError('Ràng buộc chưa có nghiệm duy nhất; cần chỉ rõ kích thước giữ cố định')
    try:answer, *_ = np.linalg.lstsq(np.asarray(rows), np.asarray(rhs), rcond=None)
    except np.linalg.LinAlgError as error:
        raise ValueError('Không giải được hệ ràng buộc ổn định') from error
    if not np.allclose(np.asarray(rows) @ answer, rhs, rtol=0, atol=1e-6):
        raise ValueError('Yêu cầu kích thước xung đột với ràng buộc liên kết')
    if any(not math.isfinite(v) or v <= 0 for v in answer):
        raise ValueError('Ràng buộc tạo kích thước không hợp lệ')
    return dict(zip(refs, map(float, answer)))


def validate_equations(operations, equations, context):
    import json
    records = {e['ref']: e for e in context['entities']}
    changed = {op.ref: op for op in operations if op.action == 'replace_geometry'}
    for equation in equations:
        # Validate references and coefficient shape, without requiring a unique solution.
        refs = {term.dimension_ref for term in equation.terms}
        if not refs <= records.keys() or any(records[ref].get('type')!='DIMENSION' or not records[ref].get('geometry') for ref in refs):
            raise ValueError('Phương trình chứa kích thước ngoài phạm vi hoặc không đo được')
        before = {ref: measurement(records[ref], records[ref]['geometry']) for ref in refs}
        solve(context, [equation], before)
        old_sum = new_sum = 0.
        for term in equation.terms:
            record = records[term.dimension_ref]
            after = json.loads(changed[term.dimension_ref].after) if term.dimension_ref in changed else record['geometry']
            if after.get('text') not in ('', '<>'):
                raise ValueError('Kích thước liên kết phải đo thật sau sửa')
            old_sum += term.coefficient * before[term.dimension_ref]
            new_sum += term.coefficient * measurement(record, after)
        if not math.isclose(old_sum, new_sum, rel_tol=0, abs_tol=1e-6):
            raise ValueError('Bản sửa không giữ phương trình liên kết nguồn')
