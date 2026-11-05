"""LQ exposure-profile adapter for the existing ZC planner (stdlib only)."""
from copy import deepcopy
from pathlib import Path
import sys
from math import isfinite

ZC = Path(__file__).resolve().parents[2] / 'zc' / 'prototype'
sys.path.insert(0, str(ZC))
from planner import instant, valid_box, assess_segment, plan
from scenarios import bind, fixture


def score(exposure, consequence):
    """Dimensionless synthetic consequence-weighted exposure, never probability."""
    if exposure is None or consequence is None:
        return None
    if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not isfinite(x)
           or not 0 <= x <= 1 for x in (exposure, consequence)):
        raise ValueError('invalid_exposure_or_consequence')
    return exposure * consequence


def compile_profiles(snapshot, query, profiles):
    """Whole-window maximum, with full temporal coverage required per region.

    Input absence/invalidity raises ValueError; caller returns unknown, not safe.
    Background is explicitly inherited from the ZC synthetic fixture.
    Profiles describe deviations from that complete background, not a real map.
    """
    s, q = deepcopy(snapshot), deepcopy(query)
    start, end = map(instant, q['window'])
    if start >= end:
        raise ValueError('invalid_window')
    zones, seen = [], set()
    if not profiles:
        raise ValueError('missing_profiles')
    for region in profiles:
        if not region.get('source') or region['id'] in seen or not valid_box(region['box']):
            raise ValueError('invalid_region')
        seen.add(region['id'])
        cursor, values, uncertain = start, [], False
        intervals = []
        for period in region['periods']:
            a, b = map(instant, period['valid'])
            if a >= b:
                raise ValueError('invalid_period')
            v = score(period['E'], period['C'])
            if a < end and start < b:
                intervals.append((max(a, start), min(b, end), v))
        for a, b, v in sorted(intervals, key=lambda p: (p[0], p[1])):
            if a > cursor:
                uncertain = True
            cursor = max(cursor, b)
            uncertain |= v is None
            if v is not None:
                values.append(v)
        uncertain |= cursor < end
        # Preserve known hazard evidence even if another period is missing.
        zones.append({'id': region['id'], 'box': deepcopy(region['box']),
                      'q': max(values, default=0), 'source': region['source']})
        if uncertain:
            zones.append({'id': region['id'] + ':unknown', 'box': deepcopy(region['box']),
                          'q': None, 'source': region['source']})
    s['risk_data']['zones'] = zones
    s['risk_data']['source'] = 'synthetic-lq-v1'
    s['risk_data']['profile_inputs'] = deepcopy(profiles)
    s['risk_model']['source'] = 'LQ: q=E*C, whole-window maximum, synthetic-lq-v1'
    # Rebind all changed payloads, including profile provenance and model identity.
    return bind(s, q)


def evaluate(snapshot, query, profiles, a, b):
    try:
        s, q = compile_profiles(snapshot, query, profiles)
        return assess_segment(s, q, a, b)
    except (ValueError, KeyError, TypeError, IndexError, OverflowError) as exc:
        return {'state': 'unknown', 'reason': 'lq_invalid_input:' + str(exc),
                'risk_proxy': None, 'versions': snapshot.get('versions', {})}


def can_publish(actor, author, role):
    """Policy simulation: a safety reviewer may not publish their own draft."""
    return role == 'safety_reviewer' and actor != author
