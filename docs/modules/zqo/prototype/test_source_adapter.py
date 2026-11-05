"""Real source compilation, lineage integrity and source rejection regressions."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from source_adapter import prepare_source, SourceRejected
from publication import Catalog, validate, digest
from yht_model import scene, seal

WINDOW = {'start': '2026-11-05T08:05:00Z', 'end': '2026-11-05T08:15:00Z'}


def prepare(source):
    return prepare_source(source, WINDOW, [[0,0,10],[450,450,120]], [20,20,70], [420,420,70])


class SourceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.source = seal(scene())

    def test_source_manifest_profiles_and_window_survive_reopen(self):
        original = deepcopy(self.source)
        s, q = prepare(self.source)
        self.assertEqual(self.source, original)
        self.assertEqual(len(s['risk_data']['profile_inputs']), len(self.source['ground_zones']))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'catalog.sqlite'
            db = Catalog(path); rid = db.publish(s,q,expected=None,request_id='source')
            loaded = Catalog(path).pin(rid)['snapshot']
        self.assertEqual(loaded['lineage']['source_snapshot'], original)
        self.assertEqual(loaded['lineage']['source_release']['manifest'], original['manifest'])
        self.assertEqual(loaded['lineage']['source_sha256'], digest(original))
        self.assertEqual(loaded['risk_data']['compiled_window'], q['window'])
        self.assertNotEqual(loaded['versions']['scene'], original['versions']['scene'])
        mapping = loaded['lineage']['version_mapping']
        self.assertEqual(mapping['risk_data']['source_versions']['exposure'], original['versions']['exposure'])

    def test_inconsistent_lineage_is_rejected(self):
        s, q = prepare(self.source)
        for name in ('query_versions', 'source_snapshot', 'compiled_window', 'source_release', 'version_mapping'):
            bad = deepcopy(s)
            if name == 'query_versions': bad['lineage'][name]['scene'] = 'wrong'
            elif name == 'source_snapshot': bad['lineage'][name]['scene_id'] = 'wrong'
            elif name == 'compiled_window': bad['lineage'][name][1] = '2026-11-05T08:20:00Z'
            elif name == 'source_release': bad['lineage'][name]['manifest']['owner'] = 'wrong'
            else: bad['lineage'][name]['scene']['source_versions']['terrain'] = 'wrong'
            with self.subTest(name=name), self.assertRaisesRegex(ValueError,'lineage_'):
                validate(bad,q)

    def test_unknown_exposure_rejected_without_background_substitution(self):
        self.source['ground_zones'][0].update(q=None, exposure_e=None, consequence_c=None)
        with self.assertRaises(SourceRejected) as caught:
            prepare(seal(self.source))
        self.assertEqual(caught.exception.stage, 'quality')
        self.assertTrue(caught.exception.quality['warnings'])

    def test_incomplete_coverage_rejected(self):
        self.source['coverage'][0]['complete'] = False
        with self.assertRaises(SourceRejected): prepare(seal(self.source))

    def test_nonflat_terrain_rejected_by_export(self):
        self.source['terrain']['flat'] = False
        with self.assertRaises(SourceRejected) as caught: prepare(seal(self.source))
        self.assertEqual(caught.exception.stage, 'export')
        self.assertIn('unsupported_terrain', str(caught.exception))

    def test_source_mutation_without_reseal_rejected(self):
        self.source['buildings'][0]['name'] = 'unsealed mutation'
        with self.assertRaises(SourceRejected) as caught: prepare(self.source)
        self.assertTrue(any(x['rule']=='VER-001' for x in caught.exception.quality['errors']))


if __name__ == '__main__': unittest.main()
