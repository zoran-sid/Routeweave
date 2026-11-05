"""ZQO-owned adapter: YHT quality/export -> LQ compilation -> release lineage."""
from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'yht' / 'prototype'))
from quality import check_scene
from export_zc import export_snapshot
from export_lq import profiles_from_scene
from publication import prepare_risk, validate, digest


class SourceRejected(ValueError):
    def __init__(self, stage, reason, quality):
        super().__init__(reason)
        self.stage, self.quality = stage, quality


def prepare_source(source, window, bounds, start, goal, query_id='five-module'):
    """Consume a sealed source, without resealing or changing its quality flags.

    This integration accepts only quality-clean, complete zero-base flat inputs.
    Warnings block this adapter because its projection cannot represent unknown
    heights as unknown geometry. The original YHT policy is left unchanged.
    """
    source = deepcopy(source)
    report = check_scene(source)
    if not report['ok'] or report['warnings']:
        raise SourceRejected('quality', 'source_quality_rejected', report)
    try:
        snapshot, query = export_snapshot(source, window, bounds, start, goal, query_id)
        profiles = profiles_from_scene(source, z_top=bounds[1][2])
    except ValueError as exc:
        raise SourceRejected('export', str(exc), report) from exc
    snapshot, query = prepare_risk(snapshot, query, profiles)
    source_release = {'versions': deepcopy(source['versions']),
                      'manifest': deepcopy(source['manifest'])}
    dependencies = {
        'scene': ['scene', 'terrain', 'sources'],
        'airspace': ['scene', 'airspace', 'sources'],
        'risk_data': ['scene', 'exposure', 'sources'],
        'risk_model': [],
        'planner_config': [],
    }
    transforms = {
        'scene': 'YHT export_snapshot: clipped bounding boxes, zero-base flat terrain',
        'airspace': 'YHT export_snapshot: published volumes overlapping the task window',
        'risk_data': 'YHT profiles_from_scene -> LQ compile_profiles -> ZQO compiled_window',
        'risk_model': 'LQ q=E*C whole-window maximum; YHT threshold/footprint settings',
        'planner_config': 'YHT export_snapshot settings: 20m grid, 5m buffer, 10m/s, lambda=0',
    }
    snapshot['lineage'] = {
        'schema': 'zqo-source-lineage-1',
        'source_release': source_release,
        'source_snapshot': source,
        'source_sha256': digest(source),
        'query_versions': deepcopy(snapshot['versions']),
        'compiled_window': list(query['window']),
        'projection': {'window': deepcopy(window), 'bounds': deepcopy(bounds),
                       'coordinate_system': source['crs'],
                       'terrain': 'flat-zero-base', 'geometry': 'conservative-bounding-box'},
        'quality': report,
        'version_mapping': {
            key: {'query_version': snapshot['versions'][key],
                  'source_versions': {dep: source['versions'][dep] for dep in deps},
                  'transform': transforms[key]}
            for key, deps in dependencies.items()
        },
    }
    validate(snapshot, query)
    return snapshot, query
