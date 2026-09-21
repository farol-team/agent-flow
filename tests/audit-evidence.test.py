#!/usr/bin/env python3
"""Offline audit evidence: real git and helpers, only GitHub transport mocked."""
import copy
import json
from pathlib import Path
import runpy
import unittest

SHARED = runpy.run_path(str(Path(__file__).with_name('review-gates.test.py')))
Fixture, ROOT = SHARED['Fixture'], SHARED['ROOT']


class Evidence(Fixture):
    def setUp(self):
        super().setUp()
        self.git('remote', 'add', 'origin', 'https://github.com/test/repo.git')
        path = self.repo / '.github/workflows/ios.yml'
        path.parent.mkdir(parents=True)
        path.write_text('name: iOS\non: pull_request\njobs:\n  ios:\n    runs-on: macos-15\n    steps:\n      - name: Test iOS\n        run: xcodebuild test\n')
        self.git('add', '.'); self.git('commit', '-qm', 'Add iOS verification')
        self.sha = self.git('rev-parse', 'HEAD').stdout.strip()
        self.pr = 'https://github.com/test/repo/pull/1'
        self.config['meta'].update(headRefOid=self.sha, url=self.pr, title='Add iOS', body='Card: issue\n## What\n## Why\n## Test plan')
        self.config['checks'] = [{'name':'ios', 'bucket':'pass', 'link':'https://github.com/test/repo/actions/runs/10/job/20'}]
        self.run_data = {'id':10, 'run_attempt':1, 'event':'pull_request', 'path':'.github/workflows/ios.yml',
                         'head_sha':self.sha, 'status':'completed', 'conclusion':'success',
                         'repository':{'full_name':'test/repo'}, 'head_repository':{'full_name':'test/repo'},
                         'pull_requests':[{'number':1, 'head':{'sha':self.sha}, 'base':{'sha':self.config['meta']['baseRefOid']}}]}
        self.job_data = {'id':20, 'run_id':10, 'run_attempt':1, 'name':'ios', 'head_sha':self.sha,
                         'status':'completed', 'conclusion':'success', 'labels':['macos-15'],
                         'steps':[{'name':'Test iOS', 'number':1, 'status':'completed', 'conclusion':'success'}]}
        self.config['api'] = {'repos/test/repo/actions/runs/10':self.run_data,
                              'repos/test/repo/actions/jobs/20':self.job_data}
        gh = self.fake / 'gh'
        source = gh.read_text().replace("sys.exit(99)", "if a[0]=='api':\n    print(json.dumps(c['api'][a[1]])); sys.exit(0)\nsys.exit(99)")
        gh.write_text(source)
        self.spec = {'command':'xcodebuild test', 'workflow':'.github/workflows/ios.yml',
                     'job':'ios', 'step':'Test iOS', 'runner':'macos-15', 'reason':'macOS unavailable in Linux audit'}
        self.plan = self.dir / 'plan.md'
        self.write_plan()
        self.evidence = self.dir / 'evidence.json'
        self.tracker = self.dir / 'tracker.json'; self.tracker.write_text('{"review":{}}')
        self.manifest = self.dir / 'manifest.json'
        self.verdict = self.dir / 'verdict.json'
        self.save()

    def write_plan(self):
        self.plan.write_text('[meta] PLAN\n## Tests\n- `python3 -m unittest`\n- Remote CI: ' + json.dumps(self.spec) + '\n## Out of scope\nOther features.\n')

    def collect(self, expect=0):
        self.save()
        p = self.tool('audit-evidence', 'collect', '--repo', self.repo, '--pr', self.pr,
                      '--head', self.sha, '--plan', self.plan, '--output', self.evidence)
        self.assertEqual(p.returncode, expect, p.stdout + p.stderr)
        return p

    def create(self, expect=0):
        p = self.tool('review-manifest', 'create', '--repo', self.repo, '--base', 'origin/main', '--head', self.sha,
                      '--plan', self.plan, '--config', self.tracker, '--kit', ROOT/'kit',
                      '--evidence', self.evidence, '--output', self.manifest)
        self.assertEqual(p.returncode, expect, p.stdout + p.stderr)
        if expect == 0:
            m = json.loads(self.manifest.read_text())
            self.verdict.write_text(json.dumps({'gaps':[], 'gaps_summary':'', 'minor':[],
                'verdicts':{'spec':'pass','quality':'approved'}, 'review':{'identity':m['identity'],
                'files':[{'id':i['id'], 'status':'reviewed','rules':[], 'summary':'Reviewed source and platform command.'} for i in m['data']['items']],
                'findings':[], 'cross_file':{'status':'reviewed','summary':'Reviewed interactions.'}}}))

    def test_collect_freezes_authoritative_run_job_workflow_and_plan(self):
        self.collect(); payload = json.loads(self.evidence.read_text())['data']
        self.assertEqual(payload['head'], self.sha)
        self.assertEqual(payload['remote'][0]['run']['id'], 10)
        self.assertEqual(payload['remote'][0]['job']['id'], 20)
        self.assertIn('xcodebuild test', payload['remote'][0]['workflow_source'])
        self.collect(expect=4)  # never overwrite an existing approval input

    def test_missing_pending_skipped_failed_ci_rejected(self):
        good = copy.deepcopy(self.config['checks'])
        for bucket in ['pending','skipping','fail','cancel']:
            self.config['checks'] = copy.deepcopy(good); self.config['checks'][0]['bucket'] = bucket
            self.collect(expect=4)
        self.config['checks'] = []; self.collect(expect=4)

    def test_absent_or_ambiguous_required_job_is_not_success(self):
        good = copy.deepcopy(self.config['checks'])
        for checks in [[dict(good[0],name='lint')], good + good]:
            self.config['checks'] = checks; self.collect(expect=4)

    def test_wrong_run_job_head_attempt_platform_and_step_fail_closed(self):
        for target, key, value in [(self.run_data,'head_sha','f'*40), (self.run_data,'conclusion','failure'),
            (self.run_data,'path','.github/workflows/other.yml'), (self.run_data,'repository',{'full_name':'other/repo'}),
            (self.run_data,'pull_requests',[]),
            (self.run_data,'pull_requests',[{'number':1,'head':{'sha':self.sha},'base':{'sha':'f'*40}}]),
            (self.job_data,'head_sha','f'*40), (self.job_data,'run_attempt',2), (self.job_data,'run_id',99),
            (self.job_data,'labels',['ubuntu-latest']), (self.job_data,'steps',[]),
            (self.job_data,'steps',[{'name':'Test iOS','status':'completed','conclusion':'skipped'}])]:
            old = target[key]; target[key] = value
            with self.subTest(key=key, value=value): self.collect(expect=4)
            target[key] = old

    def test_manifest_binds_evidence_and_validates_inputs_without_verdict(self):
        self.collect(); self.create()
        p = self.tool('review-manifest','inputs','--repo',self.repo,'--base','origin/main','--head',self.sha,'--manifest',self.manifest)
        self.assertEqual(p.returncode,0,p.stderr)
        payload = json.loads(self.evidence.read_text()); payload['data']['pr']['body'] = 'tampered'
        self.evidence.write_text(json.dumps(payload))
        p = self.tool('review-manifest','inputs','--repo',self.repo,'--base','origin/main','--head',self.sha,'--manifest',self.manifest)
        self.assertEqual(p.returncode,4,p.stderr)

    def test_changed_plan_wrong_repo_or_base_invalidates_evidence(self):
        for kind in ['plan','repo','base']:
            with self.subTest(kind=kind):
                if self.evidence.exists(): self.evidence.unlink()
                self.collect()
                if kind == 'plan': self.plan.write_text(self.plan.read_text()+'Changed requirement\n')
                if kind == 'repo': self.git('remote','set-url','origin','https://github.com/other/repo.git')
                if kind == 'base': self.git('update-ref','refs/remotes/origin/main',self.sha)
                self.create(expect=4)
                self.write_plan(); self.git('remote','set-url','origin','https://github.com/test/repo.git')
                self.git('update-ref','refs/remotes/origin/main',self.config['meta']['baseRefOid'])

    def test_remote_declaration_requires_snapshot_even_if_create_omits_flag(self):
        p = self.tool('review-manifest','create','--repo',self.repo,'--base','origin/main','--head',self.sha,
            '--plan',self.plan,'--config',self.tracker,'--kit',ROOT/'kit','--output',self.manifest)
        self.assertEqual(p.returncode,4,p.stderr)

    def test_invalid_declarations_do_not_silently_fall_back_to_local_or_other_ci(self):
        for text in ['## Tests\n- Remote CI: {}', '## Other\n- Remote CI: {}',
                     '## Tests\nRemote CI: {}', '## Tests\n- Remote CI: {"command":"x", "command":"y"}']:
            self.plan.write_text(text)
            self.collect(expect=4)

    def test_offline_protocol_retains_fresh_local_tests_and_platform_probe(self):
        prompt = (ROOT/'kit/prompts/acceptance-check.md').read_text()
        self.assertIn('run it locally in THIS audit', prompt)
        self.assertIn('a local failure is always a gap', prompt)
        self.assertIn('fresh local tool/platform probe', prompt)
        self.assertIn('cannot mask failure', prompt)
        self.assertIn('do not call network tools', prompt)

    def test_folded_workflow_commands_are_bound_without_requiring_yaml_parser(self):
        path = self.repo/'.github/workflows/ios.yml'
        path.write_text(path.read_text().replace('run: xcodebuild test', 'run: >-\n          xcodebuild\n          test'))
        self.git('add','.'); self.git('commit','-qm','Fold workflow command')
        self.sha = self.git('rev-parse','HEAD').stdout.strip()
        self.config['meta']['headRefOid'] = self.sha
        self.run_data['head_sha'] = self.sha
        self.run_data['pull_requests'][0]['head']['sha'] = self.sha
        self.job_data['head_sha'] = self.sha
        self.collect(); self.create()

    def test_duplicate_json_keys_in_complete_declaration_are_rejected(self):
        entry = json.dumps(self.spec)[:-1] + ', "job":"ios"}'
        self.plan.write_text('## Tests\n- Remote CI: '+entry+'\n')
        self.collect(expect=4)

    def test_metadata_only_snapshot_supports_offline_pr_review(self):
        self.plan.write_text('[meta] PLAN\n## Tests\n- `python3 -m unittest`\n')
        self.collect(); self.create()
        self.assertEqual(json.loads(self.evidence.read_text())['data']['remote'], [])

    def test_merge_rechecks_required_run_and_pr_body_even_when_ci_green(self):
        self.collect(); self.create()
        for kind in ['body','run','job','checks']:
            previous = copy.deepcopy(self.config)
            if kind == 'body': self.config['meta']['body'] = 'Changed after review'
            if kind == 'run': self.config['api']['repos/test/repo/actions/runs/10']['run_attempt'] = 2
            if kind == 'job': self.config['api']['repos/test/repo/actions/jobs/20']['steps'][0]['conclusion'] = 'skipped'
            if kind == 'checks': self.config['checks'] = [{'name':'unrelated','bucket':'pass','link':'other'}]
            self.save()
            p = self.tool('merge-reviewed-pr', self.pr, self.repo, 'flow/card', 'main', self.sha,
                          'true','merge',self.manifest,self.verdict)
            with self.subTest(kind=kind):
                self.assertNotEqual(p.returncode,0,p.stdout+p.stderr)
                self.assertFalse((self.dir/'merge-args').exists())
            self.config = previous
        self.save()
        p = self.tool('merge-reviewed-pr',self.pr,self.repo,'flow/card','main',self.sha,'true','merge',self.manifest,self.verdict)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
