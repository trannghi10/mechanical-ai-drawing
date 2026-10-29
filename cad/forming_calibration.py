"""Calibrate an effective neutral axis from an actual formed section and blank.

This is an empirical source-process rule, not a material K-factor catalogue.
Only a closed concentric strip with two axis-aligned legs is supported.
"""
import math
from cad.geometry import near
from cad.curved_profiles import primitives, profile_from


def neutral_length(items, k):
    if not 0 <= k <= 1 or len(items) != 8:
        raise ValueError('Cần mặt cắt uốn đủ hai cung, bốn chân và hai mép')
    profile_from(items)
    arcs = sorted((e for e in items if e['type'] == 'ARC'), key=lambda e: e['geometry']['radius'])
    lines = [e for e in items if e['type'] == 'LINE']
    if len(arcs) != 2 or len(lines) != 6:
        raise ValueError('Mặt cắt hiệu chỉnh không đúng cấu trúc')
    inner, outer = [e['geometry'] for e in arcs]
    if not near(inner['center'], outer['center'], 1e-5) or not 0 < inner['radius'] < outer['radius']:
        raise ValueError('Cần hai cung đồng tâm có độ dày dương')
    radius = inner['radius'] + k*(outer['radius']-inner['radius'])
    center = inner['center']; ends = []; legs = []; used = set()
    for key in ('start', 'end'):
        pair = []
        for arc in arcs:
            p = primitives(arc)[0][key]
            hits = [e for e in lines if any(near(e['geometry'][field], p, 1e-5) for field in ('start', 'end'))]
            if len(hits) != 1 or hits[0]['ref'] in used:
                raise ValueError('Chân cung không có liên kết đầu mút duy nhất')
            leg = hits[0]; used.add(leg['ref']); g = leg['geometry']
            other = g['end'] if near(g['start'], p, 1e-5) else g['start']
            axes = [i for i in (0, 1) if abs(other[i]-p[i]) > 1e-5]
            if len(axes) != 1:
                raise ValueError('Chân uốn chưa thẳng theo trục')
            pair.append((p, other, axes[0]))
        (ip, ic, axis), (op, oc, outer_axis) = pair
        if axis != outer_axis or abs(ip[2]-op[2]) > 1e-5:
            raise ValueError('Hai chân trong/ngoài không song song đồng phẳng')
        caps = [e for e in lines if (near(e['geometry']['start'], ic, 1e-5) and near(e['geometry']['end'], oc, 1e-5)) or
                (near(e['geometry']['end'], ic, 1e-5) and near(e['geometry']['start'], oc, 1e-5))]
        if len(caps) != 1:
            raise ValueError('Không xác định được mép đóng nguồn của cặp chân')
        used.add(caps[0]['ref']); cross = 1-axis
        cross_value = ip[cross] + k*(op[cross]-ip[cross])
        square = radius**2 - (cross_value-center[cross])**2
        if square <= 1e-10 or (ip[axis]-center[axis])*(op[axis]-center[axis]) <= 0:
            raise ValueError('Nhánh giao của chân và trục trung hòa mơ hồ')
        q = list(center); q[cross] = cross_value
        q[axis] += math.copysign(math.sqrt(square), ip[axis]-center[axis])
        cap = ic[axis] + k*(oc[axis]-ic[axis])
        legs.append(abs(q[axis]-cap))
        ends.append(math.atan2(q[1]-center[1], q[0]-center[0]))
    if len(used) != 6:
        raise ValueError('Mặt cắt có chân/mép chưa gán đầy đủ')
    sweep = (ends[1]-ends[0]) % (2*math.pi)
    if not 1e-6 < sweep < 2*math.pi-1e-6:
        raise ValueError('Cung trung hòa suy biến')
    return radius*sweep + sum(legs)


def calibrate(before, after, nominal, tolerance):
    """Keep every source tolerance possibility; choose a contained new interval."""
    if tolerance.get('dimtol') != 1 or tolerance.get('dimlim', 0) or any(tolerance.get(key,-1) not in range(0,9) for key in ('dimdec','dimtdec')):
        raise ValueError('Phôi cần dung sai và độ chính xác DIM native rõ ràng')
    upper = tolerance.get('dimtp'); lower = tolerance.get('dimtm')
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 for v in (nominal, upper, lower)):
        raise ValueError('Dung sai phôi không hợp lệ')
    source_range = [nominal-lower, nominal+upper]
    old = [neutral_length(before, i/32) for i in range(33)]
    new = [neutral_length(after, i/32) for i in range(33)]
    if any(b <= a for a, b in zip(old, old[1:])) or any(b <= a for a, b in zip(new, new[1:])):
        raise ValueError('Quy tắc trung hòa không đơn điệu trong miền hiệu chỉnh')
    if source_range[0] < old[0]-1e-6 or source_range[1] > old[-1]+1e-6:
        raise ValueError('Chiều dài phôi nguồn nằm ngoài miền trung hòa vật lý 0 ≤ K ≤ 1')
    def root(value):
        lo, hi = 0., 1.
        for _ in range(52):
            mid = (lo+hi)/2
            if neutral_length(before, mid) < value: lo = mid
            else: hi = mid
        return (lo+hi)/2
    ks = [root(v) for v in source_range]
    lengths = [neutral_length(after, k) for k in ks]
    precision = 10**-tolerance['dimdec']
    feasible = [lengths[1]-upper, lengths[0]+lower]
    # Prefer the calibrated source nominal, then constrain rounding so every
    # possible source tolerance value remains in the new tolerance window.
    low_tick=math.ceil((feasible[0]-1e-9)/precision)
    high_tick=math.floor((feasible[1]+1e-9)/precision)
    if low_tick>high_tick:
        raise ValueError('Không thể giữ dung sai nguồn ở độ chính xác DIM hiện tại')
    target=max(low_tick,min(high_tick,round(neutral_length(after,root(nominal))/precision)))*precision
    return dict(policy='source_calibrated_neutral_axis', effective_k_interval=ks,
                source_blank_interval_mm=source_range, target_blank_interval_mm=lengths,
                target_nominal_mm=round(target, tolerance['dimdec']), native_tolerance=tolerance,
                source_nominal_mm=nominal, tolerance_contained=True)
