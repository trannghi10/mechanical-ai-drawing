"""Verify measured clearance equations across different drawing projections."""
import json
import math
from pydantic import BaseModel, ConfigDict
from cad.geometry import near


class FitRule(BaseModel):
    model_config = ConfigDict(extra='forbid')
    thickness_dimension_ref: str
    outside_dimension_ref: str
    mating_dimension_ref: str


def measurement(record, geometry):
    if record.get('type') != 'DIMENSION':
        raise ValueError('Ràng buộc lắp ghép cần DIMENSION đo thật')
    p, q = geometry['defpoint2'], geometry['defpoint3']
    delta = [b-a for a, b in zip(p, q)]
    if record.get('dimension_type', 0) == 1:
        value = math.sqrt(sum(v*v for v in delta))
    else:
        angle = math.radians(geometry['angle'])
        value = abs(delta[0]*math.cos(angle)+delta[1]*math.sin(angle))
    factor = record.get('linear_factor', 1)
    value *= abs(factor)
    if not math.isfinite(value) or value <= 0:
        raise ValueError('Kích thước lắp ghép không hợp lệ')
    return value


def validate_fits(operations, rules, context):
    records = {r['ref']: r for r in context['entities']}
    by_ref = {}
    for operation in operations:
        if operation.action == 'replace_geometry':
            if operation.ref in by_ref:
                raise ValueError('Thao tác kích thước lắp ghép trùng lặp')
            by_ref[operation.ref] = operation
    for rule in rules:
        refs = (rule.thickness_dimension_ref, rule.outside_dimension_ref, rule.mating_dimension_ref)
        if len(set(refs)) != 3 or any(ref not in records for ref in refs):
            raise ValueError('Ràng buộc lắp ghép thiếu ba kích thước riêng biệt trong phạm vi')
        old_values, new_values = [], []
        for ref in refs:
            record = records[ref]
            before = record.get('geometry')
            if not before:
                raise ValueError('Thiếu geometry kích thước cho ràng buộc lắp ghép')
            operation = by_ref.get(ref)
            if operation and not near(json.loads(operation.before), before):
                raise ValueError('Kích thước trước sửa không khớp nguồn')
            after = json.loads(operation.after) if operation else before
            if after.get('text') not in ('', '<>'):
                raise ValueError('Không dùng số ghi đè để kiểm tra khe hở lắp ghép')
            old_values.append(measurement(record, before))
            new_values.append(measurement(record, after))
        old_t, old_outer, old_mate = old_values
        new_t, new_outer, new_mate = new_values
        if rule.thickness_dimension_ref not in by_ref or rule.mating_dimension_ref not in by_ref:
            raise ValueError('Thiếu thao tác đổi độ dày hoặc kích thước chi tiết lắp')
        if not math.isclose(old_outer, new_outer, abs_tol=1e-6):
            raise ValueError('Đổi độ dày phải giữ kích thước ngoài theo ràng buộc này')
        old_gap = old_outer - 2*old_t - old_mate
        new_gap = new_outer - 2*new_t - new_mate
        if old_gap < -1e-6 or new_gap < -1e-6:
            raise ValueError('Chi tiết lắp vượt lòng trong của hộp')
        if not math.isclose(old_gap, new_gap, abs_tol=1e-6):
            raise ValueError('Bản sửa không giữ khe hở lắp ghép ban đầu')
    return operations
