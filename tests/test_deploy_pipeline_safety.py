"""Guard the production deploy entry point against known destructive regressions."""
import re
import unittest
from pathlib import Path


SCRIPT = (Path(__file__).resolve().parents[1] / 'deploy_vps.ps1').read_text(
    encoding='utf-8-sig'
)


class DeployPipelineSafetyContracts(unittest.TestCase):
    def test_never_auto_stage_or_discard_human_changes(self):
        executable = '\n'.join(
            line.strip() for line in SCRIPT.splitlines()
            if line.strip() and not line.lstrip().startswith('#')
        )
        self.assertNotRegex(executable, r'(?i)git\s+add\s+-A\b')
        self.assertNotRegex(executable, r'(?i)git\s+(checkout\s+--\s+\.|reset\s+--hard|clean\s+-f)')
        self.assertIn('git status --porcelain --untracked-files=no', executable)
        self.assertIn('git merge --ff-only origin/main', executable)

    def test_deploy_does_not_change_database_or_finance_automatically(self):
        remote = SCRIPT.split("$remoteCommands = @'", 1)[1].split("'@", 1)[0]
        self.assertNotIn('flask db upgrade', remote)
        self.assertNotIn('flask finance sync', remote)
        self.assertNotIn('.venv/bin/pip install', remote)
        self.assertIn('.venv/bin/pip check', remote)

    def test_exact_reviewed_commit_and_health_are_checked(self):
        self.assertIn('$approvedSha -ne $originSha', SCRIPT)
        self.assertIn("test \"$(git rev-parse origin/main)\" = __APPROVED_SHA__", SCRIPT)
        self.assertIn('test "$(git rev-parse HEAD)" = __APPROVED_SHA__', SCRIPT)
        self.assertIn('systemctl is-active --quiet pro-ar', SCRIPT)
        self.assertIn('curl -fsS -o /dev/null', SCRIPT)
        self.assertIn('if ($LASTEXITCODE -ne 0)', SCRIPT)

    def test_no_new_credential_in_remote_git_url(self):
        self.assertNotRegex(SCRIPT, r'git remote set-url')
        self.assertNotIn('GITHUB_TOKEN', SCRIPT)


if __name__ == '__main__':
    unittest.main()
