"""Offline smoke checks that v27b reuses and restores the certified v27 runner."""
import importlib.util
import sys
import types
import unittest
import json
import tempfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch

SRC=Path(__file__).resolve().parents[1]

class WrapperTests(unittest.TestCase):
    def import_stubbed(self):
        base=types.ModuleType('price_backfill_v27')
        def pick_missing(items,rules,*,limit=100,now=None,cooldown_hours=24):
            return items[:limit]
        def apply_observation(original, observation, *, checked_at):
            return {**original,'price_status':'ok','price_czk':19.9},True
        base.pick_missing=pick_missing
        base.apply_observation=apply_observation
        base.inspect_saved=lambda page, row: {'status':'price_unverified'}
        base.priced=lambda row: row.get('price_status')=='ok'
        state={}
        def run(args):
            state['picked']=base.pick_missing(args.items,{},limit=100)
            state['applied']=base.apply_observation({'store':'Rohlík'}, {'status':'ok'},checked_at='2026-10-22T10:00:00+00:00')
            state['fallback_installed']=base.inspect_saved.__name__=='improved_observation'
            return args.status
        base.run=run
        maintenance=types.ModuleType('maintenance_v26')
        def hours_since(row, key='last_monitor_attempt_at', now=None):
            if key not in row:return float('inf')
            return ((now or datetime.now(timezone.utc))-datetime.fromisoformat(row[key])).total_seconds()/3600
        maintenance.hours_since=hours_since
        details=types.ModuleType('price_details_v27b')
        def improved_observation(page,row):return {'status':'ok','price':19.9}
        details.improved_observation=improved_observation
        with patch.dict(sys.modules,{'price_backfill_v27':base,'maintenance_v26':maintenance,'price_details_v27b':details}):
            spec=importlib.util.spec_from_file_location('temp_backfill_v27b', SRC/'price_backfill_v27b.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            return base,module,state

    def test_24h_dedicated_cooldown_and_no_previous_parser_cooldown(self):
        base,mod,state=self.import_stubbed()
        now=datetime(2026,10,22,10,tzinfo=timezone.utc)
        fresh={'url':'one'}
        tried={'url':'two','monitor_v27b_last_probe_at':(now-timedelta(hours=1)).isoformat()}
        old={'url':'three','monitor_v27b_last_probe_at':(now-timedelta(hours=25)).isoformat()}
        self.assertEqual(mod.pick_new_parser([fresh,tried,old],{},limit=10,now=now),[fresh,old])

    def _args(self, folder, status=0, products=None):
        source=Path(folder)/'source.json';report=Path(folder)/'report.json'
        items=products if products is not None else [{'url':'x','store':'Rohlík'}]
        source.write_text(json.dumps({'items':items,'rules':[]}),encoding='utf8')
        return types.SimpleNamespace(items=items,status=status,catalog=str(source),report=str(report),limit=100)

    def test_run_adds_provenance_and_restores_underlying_functions(self):
        base,mod,state=self.import_stubbed()
        orig_pick=base.pick_missing;orig_apply=base.apply_observation;orig_inspect=base.inspect_saved
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(mod.run(self._args(folder)),0)
        self.assertEqual(base.pick_missing,orig_pick)
        self.assertEqual(base.apply_observation,orig_apply)
        self.assertEqual(base.inspect_saved,orig_inspect)
        self.assertTrue(state['fallback_installed'])
        item,good=state['applied']
        self.assertTrue(good)
        self.assertEqual(item['price_czk'],19.9)
        self.assertEqual(item['monitor_v27b_last_probe_at'],'2026-10-22T10:00:00+00:00')

    def test_zero_prices_is_report_only_not_fake_success(self):
        base,mod,state=self.import_stubbed()
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(mod.run(self._args(folder,status=2)),0)

    def test_repeat_run_in_24h_writes_report_no_source_edit(self):
        base,mod,state=self.import_stubbed()
        with tempfile.TemporaryDirectory() as folder:
            now=datetime.now(timezone.utc)
            item={'url':'x','store':'Rohlík','monitor_v27b_last_probe_at':now.isoformat()}
            args=self._args(folder,status=0,products=[item])
            before=Path(args.catalog).read_bytes()
            self.assertEqual(mod.run(args),0)
            self.assertEqual(Path(args.catalog).read_bytes(),before)
            report=json.loads(Path(args.report).read_text(encoding='utf8'))
            self.assertEqual(report['newly_priced'],0)
            self.assertEqual(report['attempted'],0)

if __name__=='__main__': unittest.main()
