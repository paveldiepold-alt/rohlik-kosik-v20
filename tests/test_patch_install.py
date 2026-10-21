"""Checks critical transformations without requiring network/repo clone."""
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

PATCH=Path(__file__).resolve().parents[1]/'apply_taxonomy_patch.py'
FIXTURE='''def main():
    current=load(DATA/'catalog_latest.json',{})
    items={x['store']+'|'+x['url']:x for x in current.get('items',[]) if isinstance(x,dict) and x.get('url') and x.get('store')}
    if True:
        if True:
            if True:
                if True:
                    if True:
                        if True:
                            if True:
                                detail_checked+=1
                                multibuy=[]
                                items[k]={**product, 'cycle':state['cycle'],
                                          'price_status':row['status']}

def snapshot():
    all_items = cleaned_items

    verified_current=sum(1 for x in all_items)
'''
# Actual v20 indentation is the same for guarded insertion points. Use a
# fixture with real source indentation for effective integration assurance.
REAL_FIXTURE='''def main():
    current=load(DATA/'catalog_latest.json',{})
    items={x['store']+'|'+x['url']:x for x in current.get('items',[]) if isinstance(x,dict) and x.get('url') and x.get('store')}
    if True:
                        detail_checked+=1
                        multibuy=[]
                        items[k]={**product, 'cycle':state['cycle'],
                                  'price_status':row['status']}

def snapshot():
    all_items = cleaned_items

    verified_current=sum(1 for x in all_items)
'''

class PatchTests(unittest.TestCase):
 def test_patch_and_idempotency(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'catalog_monitor.py'
   p.write_text(REAL_FIXTURE,encoding='utf-8')
   run=lambda:subprocess.run([sys.executable,str(PATCH),str(p)],capture_output=True,text=True)
   first=run()
   self.assertEqual(first.returncode,0,first.stderr+first.stdout)
   contents=p.read_text()
   self.assertIn('store_taxonomy import extract_shop_context',contents)
   self.assertIn('store_taxonomy import partition_items',contents)
   self.assertIn('catalog_taxonomy_review.json',contents)
   second=run()
   self.assertEqual(second.returncode,0,second.stderr+second.stdout)
   self.assertEqual(contents,p.read_text())
 def test_fail_closed_on_unexpected_source(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'catalog_monitor.py'
   p.write_text('print("unknown version")\n')
   r=subprocess.run([sys.executable,str(PATCH),str(p)],capture_output=True,text=True)
   self.assertNotEqual(r.returncode,0)
   self.assertEqual(p.read_text(),'print("unknown version")\n')

if __name__=='__main__':unittest.main()
