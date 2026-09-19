#!/usr/bin/env python3
"""Offline regression checks: real git/processes; GitHub transport fixture only."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / 'kit/bin'


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], text=True, capture_output=True, **kwargs)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.env = dict(os.environ, GH_FIXTURE=str(self.dir), GIT_AUTHOR_NAME='Test',
                        GIT_AUTHOR_EMAIL='test@example.invalid', GIT_COMMITTER_NAME='Test',
                        GIT_COMMITTER_EMAIL='test@example.invalid')
        self.fake = self.dir / 'fake'
        self.fake.mkdir()
        gh = self.fake / 'gh'
        gh.write_text('''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys
p=pathlib.Path(os.environ['GH_FIXTURE']); a=sys.argv[1:]
c=json.loads((p/'gh.json').read_text())
if a[:2]==['repo','clone']:
    tail=a[a.index('--')+1:]
    sys.exit(subprocess.call(['git','clone',*tail,c['source'],a[3]]))
if a[:2]==['pr','view']:
    if a[-1]=='state':
        print(json.dumps({'state':c.get('merged_state','MERGED')})); sys.exit(0)
    count=p/'view-count'; n=int(count.read_text())+1 if count.exists() else 1; count.write_text(str(n))
    meta=c['meta'].copy()
    if n>=c.get('drift_at',999): meta['headRefOid']='f'*40
    print(json.dumps(meta)); sys.exit(c.get('view_exit',0))
if a[:2]==['pr','checks']:
    print(json.dumps(c.get('checks',[]))); sys.exit(c.get('checks_exit',0))
if a[:2]==['pr','merge']:
    (p/'merge-args').write_text(json.dumps(a)); sys.exit(c.get('merge_exit',0))
sys.exit(99)
''')
        gh.chmod(0o755)
        self.env['PATH'] = str(self.fake) + ':' + self.env['PATH']
        self.repo = self.dir / 'repo'
        self.repo.mkdir()
        self.git('init', '-q', '-b', 'flow/card')
        (self.repo / 'a.txt').write_text('original\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Initial')
        self.sha = self.git('rev-parse', 'HEAD').stdout.strip()
        self.config = {'meta': {'state':'OPEN', 'isDraft':False, 'headRefOid':self.sha,
                               'headRefName':'flow/card', 'baseRefName':'main'},
                       'checks':[{'name':'tests','bucket':'pass'}]}
        self.save()

    def git(self, *args, repo=None):
        p = run('git', '-C', repo or self.repo, *args, env=self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def save(self):
        (self.dir / 'gh.json').write_text(json.dumps(self.config))

    def tool(self, name, *args, **kwargs):
        return run(BIN / name, *args, env=self.env, **kwargs)

    def merge(self):
        self.save()
        return self.tool('merge-reviewed-pr', 'https://github.com/test/repo/pull/1', self.repo,
                         'flow/card', 'main', self.sha, 'true', 'merge')

    def no_merge(self):
        p = self.merge()
        self.assertNotEqual(p.returncode, 0, p.stdout)
        self.assertFalse((self.dir / 'merge-args').exists())


class Verdicts(Fixture):
    def parse(self, value, mode='acceptance'):
        path = self.dir / 'envelope.json'
        path.write_text(json.dumps({'is_error':False,'result':value if isinstance(value,str) else json.dumps(value)}))
        return self.tool('parse-verdict', mode, path)

    def test_acceptance_schema_and_consistency(self):
        good = {'gaps':[], 'gaps_summary':'', 'verdicts':{'spec':'pass','quality':'approved'}}
        self.assertEqual(self.parse(good).returncode, 0)
        quoted=dict(good, gaps=['IMPORTANT: worker says BLOCKED: missing env'],
                    verdicts={'spec':'fail','quality':'approved'})
        self.assertEqual(self.parse(quoted).returncode, 0)
        bad = [dict(good, verdicts={'spec':'fail','quality':'rejected'}),
               dict(good, verdicts='BROKEN'), dict(good, verdicts=None),
               dict(good, verdicts={'spec':'maybe','quality':'approved'}),
               dict(good, gaps=['defect']), dict(good, minor=False),
               dict(good, learnings=False), {'gaps':[], 'gaps_summary':''}]
        for value in bad:
            with self.subTest(value=value):
                self.assertEqual(self.parse(value).returncode, 4)

    def test_no_fallback_to_earlier_approval(self):
        good = {'gaps':[], 'gaps_summary':'', 'verdicts':{'spec':'pass','quality':'approved'}}
        for tail in [json.dumps(good), '{"gaps": [], "verdicts": "bad"}', '{broken}', 'BLOCKED: checks failed']:
            self.assertEqual(self.parse(json.dumps(good)+'\n'+tail).returncode, 4)
        self.assertEqual(self.parse(json.dumps(good)+' '+json.dumps(good)).returncode, 4)

    def test_critic_unknown_or_inconsistent_decisions(self):
        for value in [{'verdict':'not_approved','findings':[]},
                      {'verdict':'approved','findings':['real defect']},
                      {'verdict':'rejected','findings':[]},
                      {'verdict':'rejected','findings':['NIT: wording']},
                      {'verdict':'approved','findings':[1]}]:
            with self.subTest(value=value):
                self.assertEqual(self.parse(value,'critic').returncode,4)
        self.assertEqual(self.parse({'verdict':'approved','findings':['NIT: wording']},'critic').returncode,0)


class Protocol(unittest.TestCase):
    def test_invalid_plan_requires_renewed_approval_and_retains_work(self):
        # Markdown IS this product's controller: pin the repaired transition.
        flow=(ROOT/'kit/commands/flow-run.md').read_text()
        recovery=flow.split('A phase-A `BLOCKED` caused by an invalid PLAN',1)[1].split('2. **Spawn test critic**',1)[0]
        self.assertIn('`Plan Proposed`',recovery)
        self.assertIn("wait for the human's",recovery)
        self.assertIn('Retain evidence',recovery)
        self.assertNotIn('move the card back to',recovery)
        self.assertNotIn('remove the worktree and branch',recovery)

    def test_resumed_acceptance_keeps_original_sha(self):
        flow=(ROOT/'kit/commands/flow-run.md').read_text()
        acceptance=flow.split('### Step 2.3 — Acceptance check (subagent)',1)[1]
        self.assertIn('retain the ORIGINAL recorded SHA',acceptance)
        self.assertIn('Missing recorded SHA -> Blocked',acceptance)


class Merge(Fixture):
    def test_merge_binds_reviewed_sha(self):
        p = self.merge()
        self.assertEqual(p.returncode, 0, p.stderr)
        args = json.loads((self.dir/'merge-args').read_text())
        self.assertEqual(args[-2:], ['--match-head-commit',self.sha])
        self.assertNotIn('--delete-branch',args)

    def test_wrong_remote_sha(self):
        self.config['meta']['headRefOid']='f'*40
        self.no_merge()

    def test_wrong_base_or_branch_or_state(self):
        for key, value in [('baseRefName','release'),('headRefName','other'),('state','CLOSED'),('isDraft',True)]:
            old=self.config['meta'][key]; self.config['meta'][key]=value
            self.no_merge(); self.config['meta'][key]=old

    def test_changed_local_commit(self):
        self.git('commit','--allow-empty','-qm','Later')
        self.no_merge()

    def test_dirty_tracked_file(self):
        (self.repo/'a.txt').write_text('uncommitted\n')
        self.no_merge()

    def test_missing_or_nonpassing_ci(self):
        cases=[[], None, {}] + [[{'bucket':b}] for b in ['fail','pending','skipping','cancel','unknown']]
        for checks in cases:
            with self.subTest(checks=checks):
                self.config['checks']=checks
                self.no_merge()

    def test_ci_transport_error(self):
        self.config['checks_exit']=1
        self.no_merge()

    def test_remote_changes_while_checking_ci(self):
        self.config['drift_at']=2
        self.no_merge()

    def test_queued_is_not_done(self):
        self.config['merged_state']='OPEN'
        p=self.merge()
        self.assertNotEqual(p.returncode,0)
        self.assertIn('not confirmed',p.stderr)

    def test_failed_merge_is_not_done(self):
        self.config['merge_exit']=1
        self.assertNotEqual(self.merge().returncode,0)

    def test_explicit_ci_opt_out(self):
        self.config['checks']=[]; self.save()
        p=self.tool('merge-reviewed-pr','https://github.com/test/repo/pull/1',self.repo,
                    'flow/card','main',self.sha,'false','squash')
        self.assertEqual(p.returncode,0,p.stderr)


class Recovery(Fixture):
    def status(self, path):
        p=self.tool('stage-status',path)
        self.assertEqual(p.returncode,0,p.stderr)
        return json.loads(p.stdout)

    def test_completed_result_consumed_without_relaunch(self):
        attempt=self.dir/'attempt'
        counter=self.dir/'counter'
        script='printf x >> "$1"; printf \'{"result":"ok"}\\n\''
        self.assertEqual(self.status(attempt)['action'],'start')
        p=self.tool('run-stage',attempt,'--','bash','-c',script,'_',counter)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.status(attempt),{'action':'consume','exit_code':0})
        p=self.tool('run-stage',attempt,'--','bash','-c',script,'_',counter)
        self.assertEqual(p.returncode,73)
        self.assertEqual(counter.read_text(),'x')
        self.assertIn('ok',(attempt/'result.json').read_text())

    def test_failed_worker_exit_is_preserved(self):
        attempt=self.dir/'failed'
        self.assertEqual(self.tool('run-stage',attempt,'--','bash','-c','exit 7').returncode,7)
        self.assertEqual(self.status(attempt),{'action':'consume','exit_code':7})

    def test_incomplete_and_corrupt_claims_never_restart(self):
        attempt=self.dir/'incomplete'; attempt.mkdir()
        self.assertEqual(self.status(attempt)['action'],'inspect')
        dangling=self.dir/'dangling'; dangling.symlink_to(self.dir/'absent')
        self.assertEqual(self.status(dangling)['action'],'inspect')
        (attempt/'owner.json').write_text('{bad')
        self.assertEqual(self.status(attempt)['action'],'inspect')
        (attempt/'exit-code').write_text('0')
        self.assertEqual(self.status(attempt)['action'],'inspect')

    def test_live_and_killed_process(self):
        attempt=self.dir/'live'
        with open(self.dir/'launcher.log','w') as log:
            p=subprocess.Popen([str(BIN/'run-stage'),str(attempt),'--','sleep','20'],
                               env=self.env,stdout=log,stderr=log,start_new_session=True)
            try:
                deadline=time.monotonic()+5
                while not (attempt/'owner.json').exists() and time.monotonic()<deadline:
                    time.sleep(.02)
                self.assertEqual(self.status(attempt)['action'],'wait')
                self.assertEqual(self.tool('run-stage',attempt,'--','true').returncode,73)
            finally:
                os.killpg(p.pid,signal.SIGKILL)
                p.wait(timeout=5)
        self.assertEqual(self.status(attempt)['action'],'inspect')


class Sync(Fixture):
    def setUp(self):
        super().setUp()
        self.source=self.dir/'source'; self.source.mkdir()
        shutil.copytree(ROOT/'kit',self.source/'kit')
        shutil.copytree(ROOT/'scripts',self.source/'scripts')
        self.git('init','-q','-b','main',repo=self.source)
        self.git('add','.',repo=self.source)
        self.git('commit','-qm','First',repo=self.source)
        self.first=self.git('rev-parse','HEAD',repo=self.source).stdout.strip()
        self.git('tag','v1',repo=self.source)
        (self.source/'kit/commands/second.md').write_text('second')
        self.git('add','.',repo=self.source); self.git('commit','-qm','Second',repo=self.source)
        self.second=self.git('rev-parse','HEAD',repo=self.source).stdout.strip()
        self.config['source']=self.source.as_uri(); self.save()
        (self.repo/'.claude/prompts').mkdir(parents=True)
        (self.repo/'.claude/prompts/ui-design.md').write_text('project-owned')
        shutil.copy(ROOT/'docs/tracker.example.github.json',self.repo/'.claude/tracker.json')

    def sync(self, ref):
        return run(ROOT/'scripts/workflow-kit-sync',cwd=self.repo,env=dict(self.env,KIT_REF=ref))

    def test_old_full_sha_branch_and_tag(self):
        for ref, expected in [(self.first,self.first),('main',self.second),('v1',self.first)]:
            with self.subTest(ref=ref):
                p=self.sync(ref); self.assertEqual(p.returncode,0,p.stderr)
                self.assertIn(expected,(self.repo/'.claude/KIT_REVISION').read_text())
                self.assertEqual((self.repo/'.claude/prompts/ui-design.md').read_text(),'project-owned')
                self.assertEqual((self.repo/'.claude/commands/second.md').exists(),expected==self.second)

    def test_unknown_sha_does_not_mutate_consumer(self):
        p=self.sync('f'*40)
        self.assertNotEqual(p.returncode,0)
        self.assertFalse((self.repo/'.claude/commands').exists())
        self.assertFalse((self.repo/'.claude/KIT_REVISION').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
