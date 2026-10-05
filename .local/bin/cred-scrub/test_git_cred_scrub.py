#!/usr/bin/env python3
"""Tests for git-cred-scrub, the embedded-credential finder and scrubber.

Run: python3 test_git_cred_scrub.py -v
Every fixture is a throwaway repo under a temp dir holding obviously fake tokens, and every
tool run gets a temp HOME, so the real ~/.gitconfig and ~/.git-credentials are never read.
Covers each finding kind, dry-run (exit codes, nothing modified), --fix (URLs otherwise
identical, only offending keys unset, ~/.git-credentials untouched), --scan with
submodule configs under .git/modules, and the rule that no secret reaches stdout or stderr.

LiveWorkspaceTest also dry-runs the tool against the real dotfiles checkout and its sibling
devbox-provision checkout (override with GIT_CRED_SCRUB_LIVE_REPOS, os.pathsep-separated).
It skips a workspace that is absent or whose origin URL is already clean. It reads the
config in-process and never prints a value: failure messages name a leak, not its content.
"""
import ast
import base64
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "git-cred-scrub"
SYMLINK = HERE.parent / "git-cred-scrub"
LIVE_REPOS_ENV = "GIT_CRED_SCRUB_LIVE_REPOS"

# Obviously fake credentials, one per finding kind, so a leak names the kind that failed.
# They are deliberately shorter than real provider formats so no secret scanner matches them.
U_REMOTE = "FAKEuser-remote"
T_REMOTE = "FAKEtok-remote-0001"
T_PUSHURL = "ghp_FAKEtokPushurl0002"
U_INSTEADOF = "FAKEuser-insteadof"
T_INSTEADOF = "FAKEtok-insteadof-0003"
T_PUSHINSTEADOF = "glpat-FAKEpushinst04"
T_HEADER_BASIC = "FAKEtok-header-basic-0005"
B64_HEADER_BASIC = base64.b64encode(f"x-access-token:{T_HEADER_BASIC}".encode()).decode()
T_HEADER_BEARER = "FAKEtok-header-bearer-0006"
U_STORE = "FAKEuser-store"
T_STORE = "FAKEtok-store-file-0007"
T_SUBMODULE = "FAKEtok-submodule-0008"
T_SCAN_A = "FAKEtok-scan-a-0009"
T_SCAN_B = "FAKEtok-scan-b-0010"

SECRETS = {
    "remote url username": U_REMOTE,
    "remote url token": T_REMOTE,
    "pushurl token": T_PUSHURL,
    "insteadOf username": U_INSTEADOF,
    "insteadOf token": T_INSTEADOF,
    "pushInsteadOf token": T_PUSHINSTEADOF,
    "extraheader basic token": T_HEADER_BASIC,
    "extraheader basic base64": B64_HEADER_BASIC,
    "extraheader bearer token": T_HEADER_BEARER,
    "git-credentials username": U_STORE,
    "git-credentials token": T_STORE,
    "submodule token": T_SUBMODULE,
    "scan repo A token": T_SCAN_A,
    "scan repo B token": T_SCAN_B,
}

REMOTE_URL = f"https://{U_REMOTE}:{T_REMOTE}@git.example.com/team/repo.git"
REMOTE_URL_SHOWN = "https://***@git.example.com/team/repo.git"
PUSHURL = f"https://{T_PUSHURL}@git.example.com/team/repo.git"  # token-only userinfo
PUSHURL_SHOWN = "https://***@git.example.com/team/repo.git"
INSTEADOF_BASE = f"https://{U_INSTEADOF}:{T_INSTEADOF}@git.example.org/"
INSTEADOF_BASE_SHOWN = "https://***@git.example.org/"
PUSHINSTEADOF_BASE = f"https://x-access-token:{T_PUSHINSTEADOF}@push.example.org/"
PUSHINSTEADOF_BASE_SHOWN = "https://***@push.example.org/"
EXTRAHEADER_BASIC = f"AUTHORIZATION: basic {B64_HEADER_BASIC}"  # actions/checkout style
EXTRAHEADER_BEARER = f"Authorization: Bearer {T_HEADER_BEARER}"
GIT_CREDENTIALS = f"https://{U_STORE}:{T_STORE}@git.example.com\n"

# --fix must keep scheme, host, port, and path exactly; only the userinfo goes.
FIX_URL = f"https://{U_REMOTE}:{T_REMOTE}@git.example.com:8443/team/sub%20dir/repo.git"
FIX_URL_CLEAN = "https://git.example.com:8443/team/sub%20dir/repo.git"
FIX_PUSHURLS = [
    f"http://{U_REMOTE}:{T_PUSHURL}@git.example.com:8080/team/push.git",
    f"https://{T_PUSHURL}@git.example.net/team/mirror.git",
]
FIX_PUSHURLS_CLEAN = [
    "http://git.example.com:8080/team/push.git",
    "https://git.example.net/team/mirror.git",
]
UPSTREAM_URL = "https://git.example.com/upstream/repo.git"
REVOKE_HOSTS = ["git.example.com", "git.example.net", "git.example.org", "push.example.org"]

SUB_URL = f"https://x-access-token:{T_SUBMODULE}@sub.example.net/team/sub.git"
SUB_URL_SHOWN = "https://***@sub.example.net/team/sub.git"
SUB_URL_CLEAN = "https://sub.example.net/team/sub.git"

# The tracked ~/.config/git/config shape (T02): helper resets, GCM wrapper, gh for GitHub.
CLEAN_XDG_CONFIG = (
    "[credential]\n"
    "\thelper =\n"
    '\thelper = !"$HOME/.local/bin/git-credential-gcm"\n'
    "\tguiPrompt = false\n"
    '[credential "https://github.com"]\n'
    "\thelper =\n"
    '\thelper = !"$HOME/.local/bin/git-credential-gh"\n'
    '[credential "https://gist.github.com"]\n'
    "\thelper =\n"
    '\thelper = !"$HOME/.local/bin/git-credential-gh"\n'
)

# An http(s) URL whose userinfo is anything other than the "***" redaction.
UNREDACTED_HTTP_USERINFO = re.compile(r"https?://(?!\*\*\*@)[^\s/@]+@", re.IGNORECASE)


def hermetic_env(home, ceiling):
    """The caller's env minus GIT_*, with a temp HOME and no system config."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        HOME=str(home),
        XDG_CONFIG_HOME=str(Path(home) / ".config"),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CEILING_DIRECTORIES=str(ceiling),
    )
    return env


def snapshot(paths):
    """mtime_ns and content hash per path (None when absent), to prove nothing changed."""
    state = {}
    for path in paths:
        path = Path(path)
        if path.exists():
            state[str(path)] = (path.stat().st_mtime_ns,
                                hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            state[str(path)] = None
    return state


def output(result):
    """A tool run's streams for a failure message; use only after assertNoSecrets passed."""
    return f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"


class ScrubTestCase(unittest.TestCase):
    """Temp dir, temp HOME, and secret-safe helpers shared by every test."""

    def setUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp(prefix="cred-scrub-test-")))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.work = self.tmp / "work"
        self.work.mkdir()
        self.xdg_config = self.home / ".config" / "git" / "config"
        self.gitconfig = self.home / ".gitconfig"
        self.git_credentials = self.home / ".git-credentials"

    # -- fixtures -------------------------------------------------------------

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.tmp,
                              env=hermetic_env(self.home, self.tmp),
                              capture_output=True, text=True, check=True)

    def make_repo(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.git("-c", "init.defaultBranch=main", "init", "-q", str(path))
        return path

    def config(self, cfg, *args):
        """`git config --file cfg ...` (fixture writes only; fake values)."""
        Path(cfg).parent.mkdir(parents=True, exist_ok=True)
        self.git("config", "--file", str(cfg), *args)

    def get_all(self, cfg, key):
        """Every value of `key` in `cfg`, in file order; [] when unset."""
        result = subprocess.run(["git", "config", "--file", str(cfg), "--get-all", key],
                                env=hermetic_env(self.home, self.tmp),
                                capture_output=True, text=True)
        if result.returncode == 1:
            return []
        self.assertEqual(result.returncode, 0, f"git config --get-all {key} failed")
        return result.stdout.split("\n")[:-1]

    def global_files(self):
        return [self.gitconfig, self.xdg_config, self.git_credentials]

    # -- running the tool ------------------------------------------------------

    def scrub(self, *args, home=None):
        if not SCRIPT.is_file():
            self.fail(f"git-cred-scrub is missing: {SCRIPT}")
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.tmp,
                              env=hermetic_env(home or self.home, self.tmp),
                              capture_output=True, text=True, timeout=120)

    # -- assertions that never echo a secret -----------------------------------

    def assertNoSecrets(self, result, secrets=None):
        """No secret value and no unredacted http(s) userinfo in stdout or stderr."""
        secrets = SECRETS if secrets is None else secrets
        for stream in ("stdout", "stderr"):
            text = getattr(result, stream)
            for label, value in secrets.items():
                if value and value in text:
                    self.fail(f"{label} leaked into {stream}")
            if UNREDACTED_HTTP_USERINFO.search(text):
                self.fail(f"an http(s) URL with unredacted userinfo reached {stream}")

    def assertFileHasNoSecrets(self, path):
        text = Path(path).read_text()
        for label, value in SECRETS.items():
            if value in text:
                self.fail(f"{label} is still in {path}")

    def assertUnchanged(self, before, after):
        for path, state in before.items():
            if after.get(path) != state:
                self.fail(f"{path} was created, modified, or removed")

    def assertDryRunFinds(self, args, watched, home=None):
        """Dry-run exits 1, prints no secret, and leaves every watched file as it was."""
        before = snapshot(watched)
        result = self.scrub(*args, home=home)
        self.assertNoSecrets(result)
        self.assertEqual(result.returncode, 1, "expected exit 1 (findings)" + output(result))
        self.assertUnchanged(before, snapshot(watched))
        return result

    def assertFixRan(self, result):
        self.assertNoSecrets(result)
        self.assertNotEqual(result.returncode, 2, "--fix reported an error" + output(result))

    def assertRevokeAndReauth(self, stdout, hosts):
        """The report ends with the hosts to revoke and says how to re-authenticate."""
        low = stdout.lower()
        at = low.find("revoke")
        self.assertNotEqual(at, -1, "no revoke guidance in stdout")
        for host in hosts:
            self.assertIn(host, low[at:], f"{host} is missing from the revoke host list")
        self.assertRegex(low, r"re-?authenticat", "no re-authentication guidance in stdout")


class FindingKindsTest(ScrubTestCase):
    """Each finding kind alone makes a dry-run exit 1 without printing or changing anything."""

    def setUp(self):
        super().setUp()
        self.repo = self.make_repo(self.work / "repo")
        self.cfg = self.repo / ".git" / "config"

    def dry_run(self):
        return self.assertDryRunFinds([str(self.repo)], [self.cfg, *self.global_files()])

    def test_remote_url_userinfo(self):
        self.config(self.cfg, "remote.origin.url", REMOTE_URL)
        out = self.dry_run().stdout
        self.assertIn("remote.origin.url", out.lower())
        self.assertIn(REMOTE_URL_SHOWN, out)

    def test_remote_pushurl_token_only_userinfo(self):
        self.config(self.cfg, "remote.origin.url", "https://git.example.com/team/repo.git")
        self.config(self.cfg, "remote.origin.pushurl", PUSHURL)
        out = self.dry_run().stdout
        self.assertIn("remote.origin.pushurl", out.lower())
        self.assertIn(PUSHURL_SHOWN, out)

    def test_insteadof_base_userinfo(self):
        self.config(self.cfg, f"url.{INSTEADOF_BASE}.insteadOf", "ssh://git@git.example.org/")
        out = self.dry_run().stdout
        self.assertIn("insteadof", out.lower())
        self.assertIn(INSTEADOF_BASE_SHOWN, out)

    def test_pushinsteadof_base_userinfo(self):
        self.config(self.cfg, f"url.{PUSHINSTEADOF_BASE}.pushInsteadOf", "git@push.example.org:")
        out = self.dry_run().stdout
        self.assertIn("pushinsteadof", out.lower())
        self.assertIn(PUSHINSTEADOF_BASE_SHOWN, out)

    def test_http_extraheader_authorization_scoped_to_url(self):
        self.config(self.cfg, "http.https://git.example.com/.extraheader", EXTRAHEADER_BASIC)
        self.assertIn("extraheader", self.dry_run().stdout.lower())

    def test_http_extraheader_authorization_unscoped(self):
        self.config(self.cfg, "http.extraHeader", EXTRAHEADER_BEARER)
        self.assertIn("extraheader", self.dry_run().stdout.lower())

    def test_repo_credential_helper_store(self):
        self.config(self.cfg, "credential.helper", "store")
        self.assertIn("credential.helper", self.dry_run().stdout.lower())

    def test_global_credential_helper_store_in_gitconfig(self):
        self.config(self.gitconfig, "credential.helper", "store")
        self.assertIn("credential.helper", self.dry_run().stdout.lower())

    def test_global_credential_helper_store_in_xdg_config(self):
        self.xdg_config.parent.mkdir(parents=True)
        self.xdg_config.write_text(CLEAN_XDG_CONFIG)
        self.config(self.xdg_config, "--add", "credential.helper",
                    f"store --file={self.home / '.my-credentials'}")
        self.assertIn("credential.helper", self.dry_run().stdout.lower())

    def test_git_credentials_file(self):
        self.git_credentials.write_text(GIT_CREDENTIALS)
        self.git_credentials.chmod(0o600)
        self.assertIn(".git-credentials", self.dry_run().stdout)


class CleanTest(ScrubTestCase):
    """No embedded credentials: exit 0, and --fix leaves every file byte-identical.

    SSH and scp-style URLs carry a user name, not a credential, so they are not findings;
    neither are non-Authorization extra headers or non-store helpers.
    """

    def setUp(self):
        super().setUp()
        self.repo = self.make_repo(self.work / "clean")
        self.cfg = self.repo / ".git" / "config"
        self.config(self.cfg, "remote.origin.url", "git@github.com:example/repo.git")
        self.config(self.cfg, "remote.mirror.url", "ssh://git@git.example.com/team/repo.git")
        self.config(self.cfg, "remote.upstream.url", UPSTREAM_URL)
        self.config(self.cfg, "url.https://git.example.org/.insteadOf", "git@git.example.org:")
        self.config(self.cfg, "http.https://git.example.com/.extraheader", "X-Trace: keepme")
        self.config(self.cfg, "credential.helper", "cache --timeout=600")
        self.xdg_config.parent.mkdir(parents=True)
        self.xdg_config.write_text(CLEAN_XDG_CONFIG)
        self.config(self.gitconfig, "--add", "credential.https://github.com.helper", "")
        self.config(self.gitconfig, "--add", "credential.https://github.com.helper",
                    "!gh auth git-credential")
        self.watched = [self.cfg, *self.global_files()]

    def test_dry_run_exits_zero(self):
        before = snapshot(self.watched)
        result = self.scrub(str(self.repo))
        self.assertNoSecrets(result)
        self.assertEqual(result.returncode, 0, output(result))
        self.assertNotIn("***@", result.stdout)
        self.assertUnchanged(before, snapshot(self.watched))

    def test_fix_changes_nothing(self):
        before = snapshot(self.watched)
        result = self.scrub("--fix", str(self.repo))
        self.assertNoSecrets(result)
        self.assertEqual(result.returncode, 0, output(result))
        self.assertUnchanged(before, snapshot(self.watched))


class DirtyRepoTest(ScrubTestCase):
    """One repo and HOME holding every finding kind at once."""

    def setUp(self):
        super().setUp()
        self.repo = self.make_repo(self.work / "dirty")
        self.cfg = self.repo / ".git" / "config"
        cfg = self.cfg
        self.config(cfg, "remote.origin.url", FIX_URL)
        for url in FIX_PUSHURLS:
            self.config(cfg, "--add", "remote.origin.pushurl", url)
        self.config(cfg, "remote.upstream.url", UPSTREAM_URL)
        self.config(cfg, f"url.{INSTEADOF_BASE}.insteadOf", "ssh://git@git.example.org/")
        self.config(cfg, f"url.{PUSHINSTEADOF_BASE}.pushInsteadOf", "git@push.example.org:")
        self.config(cfg, "--add", "http.https://git.example.com/.extraheader", "X-Trace: keepme")
        self.config(cfg, "--add", "http.https://git.example.com/.extraheader", EXTRAHEADER_BASIC)
        self.config(cfg, "http.extraheader", EXTRAHEADER_BEARER)
        self.config(cfg, "credential.helper", "store")
        self.config(self.gitconfig, "user.name", "Fake Name")
        self.config(self.gitconfig, "--add", "credential.https://github.com.helper", "")
        self.config(self.gitconfig, "--add", "credential.https://github.com.helper",
                    "!gh auth git-credential")
        self.config(self.gitconfig, "credential.helper", "store")
        self.git_credentials.write_text(GIT_CREDENTIALS)
        self.git_credentials.chmod(0o600)

    def test_dry_run_reports_every_kind_and_ends_with_revoke_hosts(self):
        out = self.assertDryRunFinds([str(self.repo)], [self.cfg, *self.global_files()]).stdout
        for key in ("remote.origin.url", "remote.origin.pushurl", "insteadof", "pushinsteadof",
                    "extraheader", "credential.helper", ".git-credentials"):
            self.assertIn(key, out.lower(), f"no {key} finding")
        self.assertRevokeAndReauth(out, REVOKE_HOSTS)

    def test_fix_strips_userinfo_and_keeps_urls_otherwise_identical(self):
        self.assertFixRan(self.scrub("--fix", str(self.repo)))
        self.assertEqual(self.get_all(self.cfg, "remote.origin.url"), [FIX_URL_CLEAN])
        self.assertEqual(self.get_all(self.cfg, "remote.origin.pushurl"), FIX_PUSHURLS_CLEAN)
        self.assertEqual(self.get_all(self.cfg, "remote.upstream.url"), [UPSTREAM_URL])
        self.assertEqual(self.get_all(self.cfg, "url.https://git.example.org/.insteadof"),
                         ["ssh://git@git.example.org/"])
        self.assertEqual(self.get_all(self.cfg, "url.https://push.example.org/.pushinsteadof"),
                         ["git@push.example.org:"])
        self.assertFileHasNoSecrets(self.cfg)

    def test_fix_unsets_only_offending_keys(self):
        self.assertFixRan(self.scrub("--fix", str(self.repo)))
        self.assertEqual(self.get_all(self.cfg, "http.https://git.example.com/.extraheader"),
                         ["X-Trace: keepme"])
        self.assertEqual(self.get_all(self.cfg, "http.extraheader"), [])
        self.assertEqual(self.get_all(self.cfg, "credential.helper"), [])
        self.assertEqual(self.get_all(self.gitconfig, "credential.helper"), [])
        self.assertEqual(self.get_all(self.gitconfig, "credential.https://github.com.helper"),
                         ["", "!gh auth git-credential"])
        self.assertEqual(self.get_all(self.gitconfig, "user.name"), ["Fake Name"])

    def test_fix_never_touches_git_credentials(self):
        before = snapshot([self.git_credentials])
        self.assertFixRan(self.scrub("--fix", str(self.repo)))
        self.assertUnchanged(before, snapshot([self.git_credentials]))

    def test_fix_output_ends_with_revoke_hosts(self):
        result = self.scrub("--fix", str(self.repo))
        self.assertFixRan(result)
        self.assertRevokeAndReauth(result.stdout, REVOKE_HOSTS)

    def test_fixed_repo_dry_runs_clean(self):
        self.assertFixRan(self.scrub("--fix", str(self.repo)))
        fresh_home = self.tmp / "fresh-home"
        fresh_home.mkdir()
        result = self.scrub(str(self.repo), home=fresh_home)
        self.assertNoSecrets(result)
        self.assertEqual(result.returncode, 0, output(result))

    def test_fix_does_not_create_global_config(self):
        self.gitconfig.unlink()
        self.git_credentials.unlink()
        self.assertFixRan(self.scrub("--fix", str(self.repo)))
        self.assertFalse(self.gitconfig.exists(), "--fix created ~/.gitconfig")
        self.assertFalse(self.xdg_config.exists(), "--fix created ~/.config/git/config")
        self.assertFalse(self.git_credentials.exists(), "--fix created ~/.git-credentials")


class ScanTest(ScrubTestCase):
    """--scan DIR finds repos at any depth and submodule configs under .git/modules."""

    def setUp(self):
        super().setUp()
        self.scan_root = self.tmp / "scan"
        src = self.make_repo(self.tmp / "src")
        (src / "README").write_text("submodule source\n")
        self.git("-C", str(src), "add", "README")
        self.git("-C", str(src), "-c", "user.name=Fake", "-c", "user.email=fake@example.invalid",
                 "commit", "-q", "-m", "init")
        self.super = self.make_repo(self.scan_root / "projects" / "super")
        self.git("-C", str(self.super), "-c", "protocol.file.allow=always",
                 "submodule", "--quiet", "add", str(src), "sub")
        self.super_cfg = self.super / ".git" / "config"
        self.sub_cfg = self.super / ".git" / "modules" / "sub" / "config"
        self.assertTrue(self.sub_cfg.is_file(), "fixture: submodule config was not created")
        self.config(self.super_cfg, "remote.origin.url", "https://git.example.com/team/super.git")
        self.config(self.sub_cfg, "remote.origin.url", SUB_URL)
        clean = self.make_repo(self.scan_root / "other" / "clean")
        self.clean_cfg = clean / ".git" / "config"
        self.config(self.clean_cfg, "remote.origin.url", "git@git.example.com:team/clean.git")
        (self.scan_root / "notes").mkdir()
        (self.scan_root / "notes" / "todo.txt").write_text("not a repo\n")
        self.watched = [self.super_cfg, self.sub_cfg, self.clean_cfg, *self.global_files()]

    def test_scan_reports_submodule_credentials(self):
        out = self.assertDryRunFinds(["--scan", str(self.scan_root)], self.watched).stdout
        self.assertIn(SUB_URL_SHOWN, out)
        self.assertRevokeAndReauth(out, ["sub.example.net"])

    def test_scan_fix_strips_submodule_credentials(self):
        self.assertFixRan(self.scrub("--fix", "--scan", str(self.scan_root)))
        self.assertEqual(self.get_all(self.sub_cfg, "remote.origin.url"), [SUB_URL_CLEAN])
        self.assertEqual(self.get_all(self.super_cfg, "remote.origin.url"),
                         ["https://git.example.com/team/super.git"])
        result = self.scrub("--scan", str(self.scan_root))
        self.assertNoSecrets(result)
        self.assertEqual(result.returncode, 0, output(result))

    def test_scan_finds_every_repo_below_dir(self):
        repo_a = self.make_repo(self.scan_root / "a")
        repo_b = self.make_repo(self.scan_root / "deep" / "er" / "b")
        cfg_a = repo_a / ".git" / "config"
        cfg_b = repo_b / ".git" / "config"
        self.config(cfg_a, "remote.origin.url", f"https://{T_SCAN_A}@a.example.com/team/a.git")
        self.config(cfg_b, "remote.origin.url", f"https://u:{T_SCAN_B}@b.example.com/team/b.git")
        out = self.assertDryRunFinds(["--scan", str(self.scan_root)],
                                     [cfg_a, cfg_b, *self.watched]).stdout
        self.assertIn("https://***@a.example.com/team/a.git", out)
        self.assertIn("https://***@b.example.com/team/b.git", out)
        self.assertIn(SUB_URL_SHOWN, out)


class ExitCodeTest(ScrubTestCase):
    """Anything the tool cannot scan is an error (exit 2), never a clean result."""

    def assertError(self, *args):
        result = self.scrub(*args)
        self.assertNoSecrets(result)
        self.assertEqual(result.returncode, 2, output(result))

    def test_missing_path(self):
        self.assertError(str(self.tmp / "does-not-exist"))

    def test_path_that_is_not_a_repo(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        self.assertError(str(plain))

    def test_missing_scan_dir(self):
        self.assertError("--scan", str(self.tmp / "does-not-exist"))


class LayoutTest(ScrubTestCase):
    """The dotfiles tool layout: stdlib-only script, README, .gitignore, and bin symlink."""

    def test_script_is_executable_stdlib_only_python(self):
        self.assertTrue(SCRIPT.is_file(), f"git-cred-scrub is missing: {SCRIPT}")
        self.assertTrue(os.access(SCRIPT, os.X_OK), "git-cred-scrub is not executable")
        source = SCRIPT.read_text()
        self.assertRegex(source.splitlines()[0], r"^#!.*python3")
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(sorted(imported - set(sys.stdlib_module_names)), [])

    def test_readme_and_gitignore_exist(self):
        for name in ("README.md", ".gitignore"):
            self.assertTrue((HERE / name).is_file(), f"{name} is missing")

    def test_bin_symlink_runs_the_tool(self):
        self.assertTrue(SYMLINK.is_symlink(), f"{SYMLINK} is not a symlink")
        self.assertEqual(os.readlink(SYMLINK), "cred-scrub/git-cred-scrub")
        result = subprocess.run([str(SYMLINK), "--help"], cwd=self.tmp,
                                env=hermetic_env(self.home, self.tmp),
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--scan", result.stdout)
        self.assertIn("--fix", result.stdout)


def live_repos():
    raw = os.environ.get(LIVE_REPOS_ENV)
    if raw is not None:
        return [Path(p) for p in raw.split(os.pathsep) if p]
    dotfiles = HERE.parents[2]
    return [dotfiles, dotfiles.parent / "devbox-provision"]


_SECTION = re.compile(r'^\s*\[\s*([A-Za-z0-9.-]+)(?:\s+"((?:[^"\\]|\\.)*)")?\s*\]')
_URL_LINE = re.compile(r"^\s*url\s*=\s*(.*?)\s*$", re.IGNORECASE)


def origin_urls(cfg_bytes):
    """remote.origin.url values parsed in-process from raw config, so nothing is printed."""
    urls, in_origin = [], False
    for line in cfg_bytes.decode("utf-8", "replace").splitlines():
        section = _SECTION.match(line)
        if section:
            in_origin = section.group(1).lower() == "remote" and section.group(2) == "origin"
            continue
        match = _URL_LINE.match(line) if in_origin else None
        if match:
            urls.append(match.group(1).strip('"'))
    return urls


def embedded_secrets(urls):
    """The secret half of each http(s) URL's userinfo.

    A username-only userinfo that also appears in the host or path yields "", which still
    marks the URL as embedded but is not leak-checked (it would match the redacted path).
    """
    secrets = []
    for url in urls:
        try:
            parts = urlsplit(url)
        except ValueError:
            continue
        if parts.scheme.lower() not in ("http", "https") or "@" not in parts.netloc:
            continue
        userinfo, _, hostport = parts.netloc.rpartition("@")
        secret = userinfo.partition(":")[2] or userinfo
        secrets.append("" if secret in hostport + parts.path else secret)
    return secrets


class LiveWorkspaceTest(ScrubTestCase):
    """Dry-run against the real workspaces reports origin, exits 1, and modifies nothing."""

    def test_dry_run_reports_origin_and_changes_nothing(self):
        checked = 0
        for repo in live_repos():
            with self.subTest(workspace=repo.name):
                cfg = repo / ".git" / "config"
                if not cfg.is_file():
                    continue
                secrets = embedded_secrets(origin_urls(cfg.read_bytes()))
                if not secrets:
                    continue
                checked += 1
                before = snapshot([cfg])
                result = self.scrub(str(repo))
                self.assertNoSecrets(result, {f"{repo.name} origin credential #{i}": s
                                              for i, s in enumerate(secrets)})
                self.assertEqual(result.returncode, 1, f"{repo.name}: expected exit 1")
                if "remote.origin.url" not in result.stdout.lower():
                    self.fail(f"{repo.name}: no remote.origin.url finding")
                self.assertUnchanged(before, snapshot([cfg]))
        if not checked:
            self.skipTest("no live workspace has an embedded origin credential")


# -- review round 1: submodule.<name>.url, included files, config.worktree, helper resets ----

T_SUBINIT = "FAKEtok-subinit-0011"
T_INCLUDE = "FAKEtok-include-0012"
T_INCLUDEIF = "FAKEtok-includeif-0013"
T_WORKTREE = "FAKEtok-worktree-0014"
ROUND1_SECRETS = {
    **SECRETS,
    "submodule init token": T_SUBINIT,
    "include.path token": T_INCLUDE,
    "includeIf token": T_INCLUDEIF,
    "config.worktree token": T_WORKTREE,
}
# CLEAN_XDG_CONFIG's unescaped quotes are config syntax, so git reads the helper without them.
GCM_HELPER = "!$HOME/.local/bin/git-credential-gcm"


class Round1TestCase(ScrubTestCase):
    """Leak checks extended to the round-1 fake tokens."""

    def assertNoSecrets(self, result, secrets=None):
        super().assertNoSecrets(result, ROUND1_SECRETS if secrets is None else secrets)

    def assertFileHasNoSecrets(self, path):
        text = Path(path).read_text()
        for label, value in ROUND1_SECRETS.items():
            if value in text:
                self.fail(f"{label} is still in {path}")

    def assertRerunClean(self, repo):
        result = self.scrub(str(repo))
        self.assertNoSecrets(result)
        self.assertEqual(result.returncode, 0, output(result))


class SubmoduleUrlTest(Round1TestCase):
    """`git submodule init` copies a token-bearing origin into submodule.<name>.url."""

    def setUp(self):
        super().setUp()
        self.repo = self.make_repo(self.work / "super")
        self.cfg = self.repo / ".git" / "config"
        self.config(self.cfg, "remote.origin.url",
                    f"https://x-access-token:{T_SUBINIT}@git.example.com/team/super.git")
        (self.repo / ".gitmodules").write_text(
            '[submodule "sub"]\n\tpath = sub\n\turl = ../sub.git\n')
        self.git("-C", str(self.repo), "update-index", "--add", "--cacheinfo",
                 "160000,1111111111111111111111111111111111111111,sub")
        self.git("-C", str(self.repo), "add", ".gitmodules")
        self.git("-C", str(self.repo), "submodule", "--quiet", "init")
        self.assertTrue(any(T_SUBINIT in v for v in self.get_all(self.cfg, "submodule.sub.url")),
                        "fixture: submodule init did not copy the origin credential")

    def test_dry_run_reports_submodule_url(self):
        out = self.assertDryRunFinds([str(self.repo)], [self.cfg, *self.global_files()]).stdout
        self.assertIn("submodule.sub.url", out.lower())
        self.assertIn("https://***@git.example.com/team/sub.git", out)

    def test_fix_strips_submodule_url_and_reruns_clean(self):
        self.assertFixRan(self.scrub("--fix", str(self.repo)))
        self.assertFileHasNoSecrets(self.cfg)
        self.assertEqual(self.get_all(self.cfg, "submodule.sub.url"),
                         ["https://git.example.com/team/sub.git"])
        self.assertRerunClean(self.repo)

    def test_submodule_url_alone_is_reported_with_its_host(self):
        self.config(self.cfg, "remote.origin.url", "https://git.example.com/team/super.git")
        out = self.assertDryRunFinds([str(self.repo)], [self.cfg, *self.global_files()]).stdout
        self.assertIn("submodule.sub.url", out.lower())
        self.assertRevokeAndReauth(out, ["git.example.com"])


class IncludedConfigTest(Round1TestCase):
    """include.path / includeIf targets and config.worktree are scanned and fixed."""

    def setUp(self):
        super().setUp()
        self.repo = self.make_repo(self.work / "repo")
        self.cfg = self.repo / ".git" / "config"

    def test_repo_include_path_relative_to_including_file(self):
        included = self.repo / ".git" / "extra.inc"
        self.config(included, "remote.origin.url",
                    f"https://{T_INCLUDE}@inc.example.com/team/repo.git")
        self.config(self.cfg, "include.path", "extra.inc")
        out = self.assertDryRunFinds([str(self.repo)],
                                     [self.cfg, included, *self.global_files()]).stdout
        self.assertIn(str(included), out)
        self.assertIn("https://***@inc.example.com/team/repo.git", out)
        self.assertFixRan(self.scrub("--fix", str(self.repo)))
        self.assertFileHasNoSecrets(included)
        self.assertEqual(self.get_all(included, "remote.origin.url"),
                         ["https://inc.example.com/team/repo.git"])
        self.assertRerunClean(self.repo)

    def test_global_include_if_with_tilde_path(self):
        work_cfg = self.home / ".config" / "git" / "work.inc"
        self.config(work_cfg, "credential.helper", "store")
        self.config(work_cfg, f"url.https://u:{T_INCLUDEIF}@work.example.com/.insteadOf", "work:")
        self.config(self.gitconfig, "includeIf.gitdir:~/work/.path", "~/.config/git/work.inc")
        out = self.assertDryRunFinds([str(self.repo)],
                                     [self.cfg, work_cfg, *self.global_files()]).stdout
        self.assertIn("https://***@work.example.com/", out)
        self.assertIn("credential.helper", out.lower())
        self.assertFixRan(self.scrub("--fix", str(self.repo)))
        self.assertFileHasNoSecrets(work_cfg)
        self.assertEqual(self.get_all(work_cfg, "credential.helper"), [])
        self.assertRerunClean(self.repo)

    def test_config_worktree(self):
        wt_cfg = self.repo / ".git" / "config.worktree"
        self.config(self.cfg, "extensions.worktreeConfig", "true")
        self.config(wt_cfg, "remote.wt.url", f"https://{T_WORKTREE}@wt.example.com/team/repo.git")
        out = self.assertDryRunFinds([str(self.repo)],
                                     [self.cfg, wt_cfg, *self.global_files()]).stdout
        self.assertIn("https://***@wt.example.com/team/repo.git", out)
        self.assertFixRan(self.scrub("--fix", str(self.repo)))
        self.assertFileHasNoSecrets(wt_cfg)
        self.assertEqual(self.get_all(wt_cfg, "remote.wt.url"),
                         ["https://wt.example.com/team/repo.git"])
        self.assertRerunClean(self.repo)


class HelperResetTest(Round1TestCase):
    """--fix must not leave a lone `helper =` reset that disables the tracked GCM helper."""

    def setUp(self):
        super().setUp()
        self.repo = self.make_repo(self.work / "repo")
        self.xdg_config.parent.mkdir(parents=True)
        self.xdg_config.write_text(CLEAN_XDG_CONFIG)
        self.config(self.gitconfig, "user.name", "Fake Name")
        self.config(self.gitconfig, "--add", "credential.helper", "")
        self.config(self.gitconfig, "--add", "credential.helper", "store")

    def effective_helpers(self):
        """The general helper list git builds across every scope, after the last reset."""
        values = self.git("-C", str(self.repo), "config", "--get-all",
                          "credential.helper").stdout.split("\n")[:-1]
        return values[len(values) - values[::-1].index(""):] if "" in values else values

    def test_lone_reset_goes_with_the_store_helper(self):
        out = self.assertDryRunFinds([str(self.repo)], self.global_files()).stdout
        self.assertIn("reset", out.lower())
        self.assertFixRan(self.scrub("--fix", str(self.repo)))
        self.assertEqual(self.get_all(self.gitconfig, "credential.helper"), [])
        self.assertEqual(self.get_all(self.gitconfig, "user.name"), ["Fake Name"])
        self.assertEqual(self.effective_helpers(), [GCM_HELPER])

    def test_reset_before_another_helper_stays(self):
        self.config(self.gitconfig, "--add", "credential.helper", "cache --timeout=600")
        self.assertFixRan(self.scrub("--fix", str(self.repo)))
        self.assertEqual(self.get_all(self.gitconfig, "credential.helper"),
                         ["", "cache --timeout=600"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
