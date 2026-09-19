#!/usr/bin/env python3
"""Executor contract tests: real processes and durable claims, fixture CLIs only."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / 'kit/bin'
SESSION = '12345678-1234-1234-1234-123456789abc'


class Executors(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo with spaces'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        self.fake = self.root / 'fake'
        self.fake.mkdir()
        source = r'''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys, time
root = pathlib.Path(os.environ['FIXTURE'])
args = sys.argv[1:]
with (root/'calls').open('a') as f:
    f.write(json.dumps({'cli': pathlib.Path(sys.argv[0]).name, 'args': args, 'cwd': os.getcwd(), 'prompt': sys.stdin.read(), 'temp': os.environ.get('TMPDIR'), 'cache': os.environ.get('XDG_CACHE_HOME')})+'\n')
mode = os.environ.get('MODE', 'ok')
if mode == 'timeout':
    child = subprocess.Popen(['sleep', '60'])
    (root/'descendant').write_text(str(child.pid))
    time.sleep(60)
if mode == 'exit':
    print('provider failed', file=sys.stderr)
    sys.exit(7)
if mode == 'malformed':
    print('{bad')
    sys.exit(0)
session = '12345678-1234-1234-1234-123456789abc'
result = os.environ.get('FINAL', 'PR_URL=https://github.com/test/repo/pull/1')
if pathlib.Path(sys.argv[0]).name == 'claude':
    value = {'type':'result', 'subtype':'success', 'is_error':False, 'result':result,
             'session_id':session, 'total_cost_usd':0.12, 'num_turns':3}
    if mode == 'error': value['is_error'] = True
    if mode == 'limit': value['subtype'] = 'error_max_turns'
    if mode == 'empty': value['result'] = ''
    print(json.dumps(value))
else:
    events = [dict(type='thread.started',thread_id=session), dict(type='turn.started'),
              dict(type='item.completed',item=dict(type='agent_message',text='Earlier commentary')),
              dict(type='item.completed',item=dict(type='agent_message',text=result)),
              dict(type='turn.completed',usage=dict(input_tokens=10,cached_input_tokens=2,output_tokens=3))]
    if mode == 'partial': events.pop()
    if mode == 'error': events.append(dict(type='turn.failed',error=dict(message='failed after output')))
    if mode == 'duplicate-turn': events += events[1:]
    if mode == 'wrong-session': events[0]['thread_id'] = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
    if mode == 'missing-thread': events.pop(0)
    if mode != 'missing-final':
        pathlib.Path(args[args.index('--output-last-message')+1]).write_text('different' if mode == 'mismatch' else result)
    for event in events: print(json.dumps(event))
'''
        for name in ['claude', 'codex']:
            p = self.fake / name
            p.write_text(source)
            p.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.fake) + ':' + os.environ['PATH'], FIXTURE=str(self.root))
        self.config = self.root / 'tracker.json'
        self.cfg = {'executor': {'default': 'claude', 'timeout_seconds': 10, 'codex_sandbox': 'workspace-write'},
                    'worker': {'model': '', 'max_turns': 100, 'resume_sessions': True},
                    'acceptance': {'model': '', 'max_turns': 50}}
        self.prompt = self.root / 'prompt.md'
        self.prompt.write_text('Literal prompt: $(touch never) `false`\nSecond line.')

    def run_tool(self, *args, env=None):
        return subprocess.run([str(BIN/'run-agent'), *map(str,args)], text=True, capture_output=True,
                              env=env or self.env)

    def launch(self, name='attempt', role='worker', resume=None, mode='ok', final=None):
        self.config.write_text(json.dumps(self.cfg))
        args = ['run', '--attempt', self.root/name, '--config', self.config,
                '--worktree', self.repo, '--prompt-file', self.prompt, '--role', role]
        if resume: args += ['--resume-from', self.root/resume]
        env = dict(self.env, MODE=mode)
        if final is not None: env['FINAL'] = final
        return self.run_tool(*args, env=env)

    def result(self, name='attempt'):
        return json.loads((self.root/name/'result.json').read_text())

    def calls(self):
        return [json.loads(line) for line in (self.root/'calls').read_text().splitlines()]

    def test_claude_worker_and_literal_prompt(self):
        self.cfg['worker']['model'] = 'chosen-model'
        p = self.launch()
        self.assertEqual(p.returncode, 0, p.stderr)
        call = self.calls()[0]
        self.assertEqual(call['cwd'], str(self.repo))
        self.assertEqual(call['prompt'], self.prompt.read_text())
        self.assertIn('chosen-model', call['args'])
        self.assertIn('--max-turns', call['args'])
        self.assertEqual(self.result()['executor'], 'claude')
        self.assertEqual(self.result()['total_cost_usd'], .12)

    def test_codex_worker_normalizes_only_final_message(self):
        self.cfg['executor']['default'] = 'codex'
        p = self.launch()
        self.assertEqual(p.returncode, 0, p.stderr)
        args = self.calls()[0]['args']
        self.assertIn('workspace-write', args)
        self.assertIn('approval_policy="never"', args)
        self.assertNotIn('--max-turns', args)
        result = self.result()
        self.assertEqual(result['result'], 'PR_URL=https://github.com/test/repo/pull/1')
        self.assertIsNone(result['total_cost_usd'])
        self.assertIsNone(result['num_turns'])
        self.assertEqual(result['usage']['input_tokens'], 10)
        self.assertTrue((self.root/'attempt/provider.stdout').exists())

    def test_mixed_executors_and_fresh_readonly_audits(self):
        self.cfg['acceptance']['executor'] = 'codex'
        self.cfg['executor']['codex_sandbox'] = 'danger-full-access'
        for role in ['critic', 'acceptance']:
            p = self.launch(role, role=role)
            self.assertEqual(p.returncode, 0, p.stderr)
            args = self.calls()[-1]['args']
            self.assertNotIn('--sandbox', args)
            self.assertIn('default_permissions="agent-flow-audit"', args)
            request = json.loads((self.root/role/'request.json').read_text())
            scratch = Path(request['audit_temp'])
            self.addCleanup(lambda p=scratch: __import__('shutil').rmtree(p, ignore_errors=True))
            self.assertTrue(scratch.is_dir())
            self.assertEqual(scratch.stat().st_mode & 0o777, 0o700)
            self.assertNotIn(self.repo, scratch.parents)
            self.assertEqual(self.calls()[-1]['temp'], str(scratch))
            self.assertEqual(self.calls()[-1]['cache'], str(scratch/'cache'))
            permissions = next(a for a in args if a.startswith('permissions='))
            self.assertIn('":root" = "read"', permissions)
            self.assertIn(json.dumps(str(scratch)) + ' = "write"', permissions)
            self.assertIn('enabled = false', permissions)
            self.assertNotIn(str(self.repo), permissions)
            self.assertNotIn('danger-full-access', args)
            self.assertNotIn('resume', args)

    def test_claude_audit_disables_edit_tools(self):
        self.assertEqual(self.launch(role='acceptance').returncode, 0)
        self.assertIn('--disallowedTools', self.calls()[0]['args'])

    def test_explicit_codex_worker_sandbox(self):
        self.cfg['executor'].update(default='codex', codex_sandbox='danger-full-access')
        self.assertEqual(self.launch().returncode, 0)
        self.assertIn('danger-full-access', self.calls()[0]['args'])

    def test_duplicate_attempt_never_launches_again(self):
        self.assertEqual(self.launch().returncode, 0)
        self.assertEqual(self.launch().returncode, 73)
        self.assertEqual(len(self.calls()), 1)
        status = subprocess.run([str(BIN/'stage-status'), str(self.root/'attempt')], text=True, capture_output=True)
        self.assertEqual(json.loads(status.stdout), {'action':'consume','exit_code':0})

    def test_exact_resume_for_each_executor(self):
        for provider in ['claude', 'codex']:
            self.cfg['executor']['default'] = provider
            first, second = provider+'1', provider+'2'
            self.assertEqual(self.launch(first).returncode, 0)
            p = self.launch(second, resume=first)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn(SESSION, self.calls()[-1]['args'])
            self.assertNotIn('--last', self.calls()[-1]['args'])

    def test_resume_rejects_executor_or_config_drift(self):
        self.assertEqual(self.launch('first').returncode, 0)
        self.cfg['worker']['model'] = 'changed'
        self.assertNotEqual(self.launch('second', resume='first').returncode, 0)
        self.cfg['worker']['model'] = ''
        self.cfg['executor']['default'] = 'codex'
        self.assertNotEqual(self.launch('third', resume='first').returncode, 0)
        self.assertEqual(len(self.calls()), 1)

    def test_resume_rejects_failed_or_incomplete_parent(self):
        self.assertNotEqual(self.launch('first', mode='exit').returncode, 0)
        self.assertNotEqual(self.launch('second', resume='first').returncode, 0)
        (self.root/'incomplete').mkdir()
        self.assertNotEqual(self.launch('third', resume='incomplete').returncode, 0)
        self.assertEqual(len(self.calls()), 1)

    def test_auditor_cannot_resume_worker(self):
        self.assertEqual(self.launch('first').returncode, 0)
        self.assertNotEqual(self.launch('second', role='acceptance', resume='first').returncode, 0)
        self.assertEqual(len(self.calls()), 1)

    def test_worker_resume_opt_out(self):
        self.cfg['worker']['resume_sessions'] = False
        self.assertEqual(self.launch('first').returncode, 0)
        self.assertNotEqual(self.launch('second', resume='first').returncode, 0)
        self.assertEqual(len(self.calls()), 1)

    def test_config_errors_before_claim(self):
        cases = [dict(default='other'), dict(default='codex', timeout_seconds=0),
                 dict(default='claude', timeout_seconds=True), dict(default='codex', codex_sandbox='unknown'),
                 dict(default='claude', typo=True)]
        for i, config in enumerate(cases):
            self.cfg['executor'] = config
            p = self.launch('bad'+str(i))
            self.assertNotEqual(p.returncode, 0)
            self.assertFalse((self.root/('bad'+str(i))).exists())
        self.assertFalse((self.root/'calls').exists())

    def test_missing_executable_before_claim(self):
        (self.fake/'codex').unlink()
        self.cfg['executor']['default'] = 'codex'
        self.env['PATH'] = str(self.fake) + ':/usr/bin:/bin'
        self.assertNotEqual(self.launch().returncode, 0)
        self.assertFalse((self.root/'attempt').exists())

    def test_cli_errors_preserve_raw_output_and_terminal_status(self):
        for provider in ['claude', 'codex']:
            self.cfg['executor']['default'] = provider
            p = self.launch(provider, mode='exit')
            self.assertEqual(p.returncode, 7, p.stderr)
            self.assertTrue(self.result(provider)['is_error'])
            self.assertIn('provider failed', (self.root/provider/'provider.stderr.log').read_text())
            self.assertEqual((self.root/provider/'exit-code').read_text().strip(), '7')

    def test_claude_invalid_or_limited_result_is_not_success(self):
        for mode in ['malformed', 'error', 'limit', 'empty']:
            self.assertNotEqual(self.launch(mode, mode=mode).returncode, 0)
            self.assertTrue(self.result(mode)['is_error'])

    def test_codex_partial_failed_ambiguous_or_mismatched_stream_is_not_success(self):
        self.cfg['executor']['default'] = 'codex'
        for mode in ['malformed', 'partial', 'error', 'duplicate-turn', 'missing-thread', 'missing-final', 'mismatch']:
            with self.subTest(mode=mode):
                self.assertNotEqual(self.launch(mode, mode=mode).returncode, 0)
                self.assertTrue(self.result(mode)['is_error'])

    def test_codex_resume_wrong_thread_is_rejected(self):
        self.cfg['executor']['default'] = 'codex'
        self.assertEqual(self.launch('first').returncode, 0)
        self.assertNotEqual(self.launch('second', resume='first', mode='wrong-session').returncode, 0)

    def test_timeout_is_terminal_and_does_not_restart(self):
        self.cfg['executor']['timeout_seconds'] = 1
        p = self.launch(mode='timeout')
        self.assertEqual(p.returncode, 124, p.stderr)
        self.assertTrue(self.result()['is_error'])
        self.assertEqual(self.launch().returncode, 73)
        pid = int((self.root/'descendant').read_text())
        state = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], text=True, capture_output=True).stdout.strip()
        self.assertTrue(not state or state.startswith('Z'), state)

    def test_preflight_selects_both_roles_without_launching(self):
        self.cfg['worker']['executor'] = 'codex'
        self.cfg['acceptance']['model'] = 'audit-model'
        self.config.write_text(json.dumps(self.cfg))
        p = self.run_tool('check', '--config', self.config)
        self.assertEqual(p.returncode, 0, p.stderr)
        resolved = json.loads(p.stdout)
        self.assertEqual(resolved['worker']['executor'], 'codex')
        self.assertEqual(resolved['acceptance']['executor'], 'claude')
        self.assertEqual(resolved['acceptance']['model'], 'audit-model')
        self.assertEqual(len(resolved['config_sha256']), 64)
        self.assertFalse((self.root/'calls').exists())

    def test_missing_required_executor_and_invalid_worker_block(self):
        del self.cfg['executor']
        self.assertNotEqual(self.launch('missing').returncode, 0)
        self.cfg['executor'] = {'default': 'claude'}
        self.cfg['worker'] = []
        p = self.launch('bad-worker', role='acceptance')
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn('Traceback', p.stderr)
        self.assertFalse((self.root/'calls').exists())

    def test_bootstrap_config_pin_prevents_new_launch_after_drift(self):
        self.config.write_text(json.dumps(self.cfg))
        pin = json.loads(self.run_tool('check', '--config', self.config).stdout)['config_sha256']
        self.cfg['worker']['model'] = 'different'
        self.config.write_text(json.dumps(self.cfg))
        p = self.run_tool('run', '--config', self.config, '--config-sha256', pin,
                          '--role', 'worker', '--worktree', self.repo,
                          '--attempt', self.root/'attempt', '--prompt-file', self.prompt)
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse((self.root/'attempt').exists())

    def test_resume_rejects_tampered_request(self):
        self.assertEqual(self.launch('first').returncode, 0)
        p = self.root/'first/request.json'
        request = json.loads(p.read_text())
        request['prompt'] = 'Changed after execution'
        p.write_text(json.dumps(request))
        self.assertNotEqual(self.launch('second', resume='first').returncode, 0)
        self.assertEqual(len(self.calls()), 1)

    def test_resume_rejects_different_worktree(self):
        self.assertEqual(self.launch('first').returncode, 0)
        self.repo = self.root/'another-repo'
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        self.assertNotEqual(self.launch('second', resume='first').returncode, 0)
        self.assertEqual(len(self.calls()), 1)

    def test_codex_timeout_cannot_consume_partial_output(self):
        self.cfg['executor'].update(default='codex', timeout_seconds=1)
        self.assertEqual(self.launch(mode='timeout').returncode, 124)
        self.assertTrue(self.result()['is_error'])

    def test_normalized_codex_verdict_keeps_gate_and_unknown_cost(self):
        self.cfg['executor']['default'] = 'codex'
        for i, verdict in enumerate([
            {'gaps':[], 'gaps_summary':'', 'verdicts':{'spec':'pass','quality':'approved'}},
            {'gaps':[], 'gaps_summary':'', 'verdicts':{'spec':'fail','quality':'approved'}}
        ]):
            name = 'review'+str(i)
            self.assertEqual(self.launch(name, role='acceptance', final=json.dumps(verdict)).returncode, 0)
            p = subprocess.run([str(BIN/'parse-verdict'),'acceptance',str(self.root/name/'result.json')], text=True, capture_output=True)
            self.assertEqual(p.returncode, 0 if i == 0 else 4, p.stderr)
            if i == 0:
                self.assertIsNone(json.loads(p.stdout)['_cost_usd'])
                self.assertEqual(json.loads(p.stdout)['_executor'], 'codex')


class Protocol(unittest.TestCase):
    def test_controller_uses_shared_executor_for_all_stages(self):
        flow = (ROOT/'kit/commands/flow-run.md').read_text()
        self.assertNotIn('-- claude', flow)
        for role in ['worker', 'critic', 'acceptance']:
            self.assertIn('run-agent run --role ' + role, flow)
        self.assertIn('--config-sha256 <recorded-config-sha>', flow)
        self.assertIn('Do not overwrite `worker_attempt` with the critic attempt', flow)
        self.assertIn('unknown_cost_runs', flow)

    def test_fresh_tdd_implementation_has_plan_and_requires_approval(self):
        prompt = (ROOT/'kit/prompts/worker-impl.md').read_text()
        self.assertIn('<PLAN-comment>', prompt.split('---', 1)[1])
        self.assertIn('Exhausted spec revisions never authorize implementation', prompt)


if __name__ == '__main__':
    unittest.main(verbosity=2)
