#!/usr/bin/env python3
"""Behavioral coverage for immutable review inputs, grouping and source anchors."""
import copy
import json
from pathlib import Path
import runpy
import shutil
import unittest

SHARED = runpy.run_path(str(Path(__file__).with_name('review-gates.test.py')))
Fixture, ROOT = SHARED['Fixture'], SHARED['ROOT']


class Manifest(Fixture):
    def setUp(self):
        super().setUp()
        self.base = self.sha
        self.kit=self.dir/'kit'; shutil.copytree(ROOT/'kit',self.kit)
        self.plan=self.dir/'plan.md'; self.plan.write_text('An approved, language-independent plan.\n')
        self.cfg={'review':{'rules':[], 'groups':[], 'exclude':[]}}
        self.tracker=self.dir/'tracker.json'
        self.manifest=self.dir/'review.json'
        self.verdict=self.dir/'verdict.json'
        for name, value in [('src/a.txt','alpha\nbeta\n'), ('tests/a.txt','test\n'), ('docs/readme.md','documentation\n')]:
            path=self.repo/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(value)
        self.git('add','.'); self.git('commit','-qm','Add changes')
        self.sha=self.git('rev-parse','HEAD').stdout.strip()

    def create(self, expect=0):
        self.tracker.write_text(json.dumps(self.cfg))
        p=self.tool('review-manifest','create','--repo',self.repo,'--base','origin/main','--head',self.sha,
                    '--config',self.tracker,'--plan',self.plan,'--kit',self.kit,'--output',self.manifest)
        self.assertEqual(p.returncode,expect,p.stderr)
        if expect == 0:
            self.m=json.loads(self.manifest.read_text())
        return p

    def result(self):
        return {'gaps':[], 'gaps_summary':'', 'minor':[], 'verdicts':{'spec':'pass','quality':'approved'}, 'review':{
            'identity':self.m['identity'], 'findings':[],
            'cross_file':{'status':'reviewed','summary':'Checked producer/consumer compatibility across groups.'},
            'files':[{'id':i['id'],'status':'excluded' if i['exclusion'] else 'reviewed',
                      'summary':i['exclusion'] or 'Inspected changed behavior and tests.', 'rules':i['rules']}
                     for i in self.m['data']['items']]}}

    def check(self, result=None, action='verify', expect=0):
        if result is not None:
            self.verdict.write_text(json.dumps(result))
        p=self.tool('review-manifest',action,'--repo',self.repo,'--base','origin/main','--head',self.sha,
                    '--manifest',self.manifest,'--verdict',self.verdict)
        self.assertEqual(p.returncode,expect,p.stdout+p.stderr)
        return p

    def test_complete_review_and_exclusion_accounting(self):
        self.cfg['review']['exclude']=[{'paths':['docs/**'],'reason':'Documentation reviewed in separate editorial process.'}]
        self.create(); p=self.check(self.result())
        self.assertEqual(json.loads(p.stdout)['excluded'],1)
        self.assertEqual(json.loads(p.stdout)['total'],3)

    def test_missing_duplicate_unknown_and_invented_exclusion(self):
        self.create()
        for kind in ['missing','duplicate','unknown','excluded']:
            r=self.result(); files=r['review']['files']
            if kind=='missing': files.pop()
            if kind=='duplicate': files.append(copy.deepcopy(files[0]))
            if kind=='unknown': files[0]['id']='unknown'
            if kind=='excluded': files[0]['status']='excluded'
            with self.subTest(kind=kind): self.check(r,expect=4)

    def test_failure_or_timeout_is_not_approval(self):
        self.create(); r=self.result(); r['review']['files'][0]['status']='failed'
        r['review']['files'][0]['summary']='Review exhausted its budget.'
        p=self.check(r,expect=3)
        self.assertFalse(json.loads(p.stdout)['accepted'])
        r=self.result(); r['review']['cross_file']['status']='failed'
        self.check(r,expect=3)

    def test_rules_are_additive_and_segment_globs_do_not_overmatch(self):
        self.cfg['review']['rules']=[
            {'id':'all','paths':['**'],'text':'Preserve public contracts.'},
            {'id':'text','paths':['**/*.txt'],'text':'Check text behavior.'},
            {'id':'root-only','paths':['*.txt'],'text':'Root files only.'}]
        self.create()
        item=next(i for i in self.m['data']['items'] if i['path']=='src/a.txt')
        self.assertEqual(item['rules'],['all','text'])
        r=self.result(); self.check(r)
        next(i for i in r['review']['files'] if i['id']==item['id'])['rules']=['text']
        self.check(r,expect=4)

    def test_group_limits_and_unassigned_files(self):
        self.cfg['review'].update(max_files_per_group=1,
            groups=[{'id':'feature','paths':['src/**','tests/**']}])
        self.create()
        groups=self.m['data']['groups']; ids=[i for g in groups for i in g['items']]
        self.assertEqual(len(ids),3); self.assertEqual(len(set(ids)),3)
        self.assertTrue(all(len(g['items'])==1 for g in groups))
        self.assertIn('default',[g['label'] for g in groups])

    def test_group_byte_budget_splits_without_losing_items(self):
        self.create()
        largest=max(i['diff_bytes'] for i in self.m['data']['items'])
        self.manifest.unlink(); self.cfg['review']['max_diff_bytes_per_group']=largest
        self.create(); items={i['id']:i for i in self.m['data']['items']}
        self.assertGreater(len(self.m['data']['groups']),1)
        assigned=[]
        for group in self.m['data']['groups']:
            self.assertLessEqual(sum(items[i]['diff_bytes'] for i in group['items']),largest)
            assigned.extend(group['items'])
        self.assertEqual(set(assigned),set(items))
        self.assertEqual(len(assigned),len(items))

    def test_oversized_file_is_retained_and_disclosed(self):
        self.cfg['review']['max_diff_bytes_per_group']=1
        self.create()
        self.assertEqual(len(self.m['data']['groups']),3)
        self.assertTrue(all(g['oversized'] for g in self.m['data']['groups']))
        self.assertEqual(sum(len(g['items']) for g in self.m['data']['groups']),3)

    def test_identity_changes_for_plan_config_prompts_and_constitution(self):
        for part in ['plan','config','prompt','constitution']:
            with self.subTest(part=part):
                if self.manifest.exists(): self.manifest.unlink()
                self.create(); result=self.result()
                path={'plan':self.plan,'config':self.tracker,'prompt':self.kit/'prompts/acceptance-check.md',
                      'constitution':self.kit/'constitution.md'}[part]
                old=path.read_bytes() if path.exists() else None
                if part=='config': path.write_text(json.dumps({'review':{'max_files_per_group':2}}))
                else: path.write_bytes((old or b'')+b'Changed requirement\n')
                self.check(result,expect=4)
                if old is None: path.unlink()
                else: path.write_bytes(old)

    def test_head_and_base_drift_invalidate_identity(self):
        self.create(); result=self.result()
        self.git('commit','--allow-empty','-qm','New head')
        self.sha=self.git('rev-parse','HEAD').stdout.strip()
        self.check(result,expect=4)
        self.sha=self.m['data']['head']
        self.git('update-ref','refs/remotes/origin/main',self.sha)
        self.check(result,expect=4)

    def test_source_quote_is_verified(self):
        self.create(); item=next(i for i in self.m['data']['items'] if i['path']=='src/a.txt')
        r=self.result(); r['gaps']=['IMPORTANT [c8:src/a.txt:missing-case]: defect']
        r['verdicts']['quality']='rejected'
        r['review']['findings']=[{'fingerprint':'c8:src/a.txt:missing-case','severity':'important',
             'item_id':item['id'],'side':'new','line_start':1,'line_end':2,'quote':'alpha\nbeta'}]
        self.check(r,action='check')
        self.check(r,expect=3)
        r['review']['findings'][0]['quote']='invented evidence'
        self.check(r,action='check',expect=4)
        r['review']['findings']=[]
        self.check(r,action='check',expect=4)

    def test_deleted_renamed_binary_and_unusual_paths_are_in_inventory(self):
        # Establish files in the base, then change/remove/rename them.
        self.git('update-ref','refs/remotes/origin/main',self.sha)
        self.git('mv','src/a.txt','src/renamed.txt')
        self.git('rm','tests/a.txt')
        for name in ['literal[1].txt', 'space name.txt', 'line\nbreak.txt']:
            (self.repo/name).write_text('exact path\n')
        (self.repo/'image.bin').write_bytes(b'\x00\x01\x02')
        self.git('add','.');self.git('commit','-qm','Rename delete and add')
        self.sha=self.git('rev-parse','HEAD').stdout.strip()
        self.create(); items=self.m['data']['items']
        self.assertEqual(len(items),6)
        self.assertTrue(any(i['status'].startswith('R') and i['old_path']=='src/a.txt' for i in items))
        deleted=next(i for i in items if i['status']=='D')
        self.assertEqual(deleted['old_path'],'tests/a.txt')
        r=self.result(); r['minor']=['[c8:tests/a.txt:removed-test] note']
        r['review']['findings']=[{'fingerprint':'c8:tests/a.txt:removed-test','severity':'minor',
            'item_id':deleted['id'],'side':'old','line_start':1,'line_end':1,'quote':'test'}]
        self.check(r)

    def test_rename_out_of_excluded_path_is_reviewed(self):
        self.git('update-ref','refs/remotes/origin/main',self.sha)
        self.git('mv','docs/readme.md','src/readme.md')
        self.git('commit','-qm','Move into source')
        self.sha=self.git('rev-parse','HEAD').stdout.strip()
        self.cfg['review']['exclude']=[{'paths':['docs/**'],'reason':'Editorial review elsewhere'}]
        self.create()
        item=self.m['data']['items'][0]
        self.assertIsNone(item['exclusion'])
        self.assertEqual(item['path'],'src/readme.md')
        self.check(self.result())

    def test_empty_report_and_wrong_identity_do_not_pass(self):
        self.create(); r=self.result()
        r['review']['identity']='wrong'
        self.check(r,expect=4)
        r.pop('review')
        self.check(r,expect=4)

    def test_source_range_side_and_ledger_must_agree(self):
        self.create(); item=next(i for i in self.m['data']['items'] if i['path']=='src/a.txt')
        r=self.result(); r['minor']=['[c8:src/a.txt:wording] note']
        finding={'fingerprint':'c8:src/a.txt:wording','severity':'minor','item_id':item['id'],
                 'side':'new','line_start':1,'line_end':1,'quote':'alpha'}
        r['review']['findings']=[finding]; self.check(r)
        for key,value in [('line_start',0),('line_end',99),('side','old'),('severity','important')]:
            bad=copy.deepcopy(r);bad['review']['findings'][0][key]=value
            with self.subTest(key=key): self.check(bad,expect=4)

    def test_manifest_is_immutable_and_tampering_rejected(self):
        self.create(); original=self.manifest.read_bytes()
        self.create(expect=4)
        self.assertEqual(self.manifest.read_bytes(),original)
        r=self.result(); self.m['data']['items'].pop()
        self.manifest.write_text(json.dumps(self.m))
        self.check(r,expect=4)

    def test_different_repository_invalidates_result(self):
        self.create(); r=self.result()
        self.git('remote','add','origin','https://example.invalid/another/repository.git')
        self.check(r,expect=4)

    def test_duplicate_json_keys_are_not_silently_overwritten(self):
        self.create(); r=self.result()
        self.tracker.write_text('{"review":{},"review":{}}')
        self.check(r,expect=4)

    def test_unknown_policy_keys_and_missing_reasons_rejected(self):
        for review in [{'typo':True},{'exclude':[{'paths':['**'],'reason':''}]},
                       {'max_files_per_group':True},{'rules':[{'id':'x','paths':['../x'],'text':'x'}]}]:
            self.cfg['review']=review
            self.create(expect=4)


if __name__=='__main__':
    unittest.main(verbosity=2)
