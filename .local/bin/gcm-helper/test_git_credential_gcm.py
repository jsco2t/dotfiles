#!/usr/bin/env python3
"""Tests for the tracked git credential config and its two helper wrappers.

Run: python3 test_git_credential_gcm.py -v

The tracked ~/.config/git/config must send github.com and gist.github.com to
git-credential-gh (which runs `gh auth git-credential`) and every other host to
git-credential-gcm (which runs Git Credential Manager, GCM). Each host must
reach exactly one helper for get, store and erase. Both wrappers are POSIX sh,
live in this directory, are linked from .local/bin, and exit 0 without output
when their binary is missing.

Isolation: every subprocess runs in a temp HOME with an environment built from
scratch, the equivalent of `env -i HOME=<tmp> PATH=/usr/bin:/bin`. The only
additions are test-isolation variables. GIT_CONFIG_SYSTEM points at a temp
system config holding a rogue helper that the tracked reset must drop.
GIT_ASKPASS is a stub that completes `git credential fill` without a terminal.
GIT_TERMINAL_PROMPT=0 and GIT_CEILING_DIRECTORIES stop any prompt or repo
lookup. No test reads the real ~/.gitconfig or reaches a real gh or GCM binary,
and every token is an obvious fake.

Contracts the tests rely on beyond the task text:
- git-credential-gh names its brew prefixes literally as /home/linuxbrew/.linuxbrew,
  /opt/homebrew and /usr/local (each with /bin/gh beneath it). The tests rewrite
  those roots in a copy of the wrapper, so the real gh on this host is never run.
- git-credential-gcm detects the OS with `uname` looked up on PATH. Only the
  tests that exercise the other platform's branch rely on this; they put a stub
  uname first on PATH.
"""
import os
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL_BIN = HERE.parent
REPO = LOCAL_BIN.parent.parent

GCM_WRAPPER = HERE / "git-credential-gcm"
GH_WRAPPER = HERE / "git-credential-gh"
GCM_LINK = LOCAL_BIN / "git-credential-gcm"
GH_LINK = LOCAL_BIN / "git-credential-gh"
TRACKED_CONFIG = REPO / ".config" / "git" / "config"

MIN_PATH = "/usr/bin:/bin"
GIT = shutil.which("git", path=MIN_PATH)
GH_ON_MIN_PATH = shutil.which("gh", path=MIN_PATH)
SHELLCHECK = shutil.which("shellcheck")
BREW_ROOTS = ("/home/linuxbrew/.linuxbrew", "/opt/homebrew", "/usr/local")

GCM_HELPER = '!"$HOME/.local/bin/git-credential-gcm"'
GH_HELPER = '!"$HOME/.local/bin/git-credential-gh"'
GITHUB_HOSTS = ("https://github.com", "https://gist.github.com")

FAKE_GH_SECRET = "ghp_FAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE0000"
FAKE_GCM_SECRET = "glpat-FAKEFAKEFAKEFAKE0000"
FAKE_ASKPASS_SECRET = "askpass-FAKEFAKEFAKE"
FAKE_STORED_SECRET = "stored-FAKEFAKEFAKE"
CRED_INPUT = "protocol=https\nhost=example.invalid\n\n"
UNSET = "<unset>"
TIMEOUT = 30

# (url fed to git, host the helper sees, wrapper that must serve it)
HOST_CASES = (
    ("https://github.com/example/repo.git", "github.com", "gh"),
    ("https://gist.github.com/0123abcd.git", "gist.github.com", "gh"),
    ("https://gitlab.example.com/group/repo.git", "gitlab.example.com", "gcm"),
    ("https://example.invalid/repo.git", "example.invalid", "gcm"),
)
# (git credential subcommand, helper operation it triggers)
ACTIONS = (("fill", "get"), ("approve", "store"), ("reject", "erase"))


class SandboxTestCase(unittest.TestCase):
    """A throwaway HOME, a stub directory, and environments built from scratch."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="gcm-helper-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.home = self.root / "home"
        self.home_bin = self.home / ".local" / "bin"
        self.home_bin.mkdir(parents=True)
        self.stubs = self.root / "stubs"
        self.stubs.mkdir()
        self.log = self.root / "calls.log"
        self.record = self.root / "record"
        self.record_stdin = self.root / "record.stdin"
        self.askpass = self.write_script(
            self.root / "askpass",
            'case $1 in\n'
            '  Username*) echo askpass-user ;;\n'
            f'  *) echo {FAKE_ASKPASS_SECRET} ;;\n'
            'esac\n',
        )
        # A helper configured below the tracked file; the tracked reset must drop it.
        self.write_log_stub(self.home_bin / "git-credential-system", "system")
        self.system_config = self.root / "system-gitconfig"
        self.system_config.write_text(
            "[credential]\n\thelper = !$HOME/.local/bin/git-credential-system\n"
        )

    # -- fixtures ---------------------------------------------------------

    def require(self, *paths):
        for path in paths:
            if not os.path.lexists(path):
                self.fail(f"missing {path.relative_to(REPO)}")

    def require_git(self):
        if GIT is None:
            self.skipTest(f"git is not in {MIN_PATH}")

    def require_no_gh_on_min_path(self):
        if GH_ON_MIN_PATH:
            self.skipTest(f"a real gh at {GH_ON_MIN_PATH} cannot be hidden from PATH")

    @staticmethod
    def write_script(path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
        return path

    def write_log_stub(self, path, label, secret=None):
        """A helper or binary stub that appends `label|args|host` to the call log.

        It reads stdin to EOF. With `secret`, it answers a get with fake
        credentials; without, it stays silent so git walks the whole helper list.
        """
        answer = ""
        if secret:
            answer = (
                'case "$*" in\n'
                f"  *get) printf 'username=stub-user\\npassword={secret}\\n' ;;\n"
                "esac\n"
            )
        return self.write_script(
            path,
            "host=\n"
            "while IFS= read -r line; do\n"
            '  case $line in host=*) host=${line#host=} ;; esac\n'
            "done\n"
            f"printf '%s|%s|%s\\n' {shlex.quote(label)} \"$*\" \"$host\""
            f" >> {shlex.quote(str(self.log))}\n" + answer,
        )

    def write_record_stub(self, path, label, output="", code=0):
        """A binary stub that records its label, args, GCM store and stdin."""
        return self.write_script(
            path,
            "{\n"
            f"  printf 'label=%s\\n' {shlex.quote(label)}\n"
            "  printf 'args=%s\\n' \"$*\"\n"
            '  if [ "${GCM_CREDENTIAL_STORE+set}" = set ]; then\n'
            "    printf 'store=%s\\n' \"$GCM_CREDENTIAL_STORE\"\n"
            "  else\n"
            f"    printf 'store=%s\\n' {shlex.quote(UNSET)}\n"
            "  fi\n"
            f"}} > {shlex.quote(str(self.record))}\n"
            f"cat > {shlex.quote(str(self.record_stdin))}\n"
            f"printf '%s' {shlex.quote(output)}\n"
            f"exit {code}\n",
        )

    def recorded(self):
        self.assertTrue(self.record.exists(), "the stub binary was never executed")
        fields = dict(
            line.split("=", 1) for line in self.record.read_text().splitlines()
        )
        fields["stdin"] = self.record_stdin.read_text()
        return fields

    def calls(self):
        if not self.log.exists():
            return []
        return [tuple(line.split("|")) for line in self.log.read_text().splitlines()]

    def install_config(self, xdg=None):
        dest = (xdg or self.home / ".config") / "git" / "config"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TRACKED_CONFIG, dest)

    def install_gcm_wrapper(self):
        """Link $HOME/.local/bin/git-credential-gcm to the tracked symlink."""
        (self.home_bin / "git-credential-gcm").symlink_to(GCM_LINK)

    def install_gh_wrapper(self):
        """Copy the gh wrapper with its brew roots moved into the sandbox.

        Returns {real root: fake root}; a stub at <fake root>/bin/gh stands in
        for a brew-installed gh.
        """
        text = GH_WRAPPER.read_text()
        missing = [root for root in BREW_ROOTS if root not in text]
        self.assertEqual(missing, [], "git-credential-gh must search every brew prefix")
        fake = {
            root: self.root / "brew" / name
            for root, name in zip(BREW_ROOTS, ("linuxbrew", "opt-homebrew", "usr-local"))
        }
        for prefix in fake.values():
            (prefix / "bin").mkdir(parents=True)
        pattern = re.compile("|".join(re.escape(root) for root in BREW_ROOTS))
        dest = self.home_bin / "gcm-helper" / "git-credential-gh"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(pattern.sub(lambda m: str(fake[m.group(0)]), text))
        dest.chmod(0o755)
        (self.home_bin / "git-credential-gh").symlink_to("gcm-helper/git-credential-gh")
        return fake

    # -- running ----------------------------------------------------------

    def wrapper_env(self, path=MIN_PATH, **extra):
        env = {"HOME": str(self.home), "PATH": path}
        env.update(extra)
        return env

    def git_env(self, path=MIN_PATH, **extra):
        env = self.wrapper_env(path)
        env.update(
            GIT_CONFIG_SYSTEM=str(self.system_config),
            GIT_ASKPASS=str(self.askpass),
            GIT_TERMINAL_PROMPT="0",
            GIT_CEILING_DIRECTORIES=str(self.root),
        )
        env.update(extra)
        return env

    def run_cmd(self, argv, env, stdin=""):
        return subprocess.run(
            [str(arg) for arg in argv],
            input=stdin,
            env=env,
            cwd=self.home,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            start_new_session=True,
        )

    def credential(self, action, url, env):
        lines = [f"url={url}"]
        if action != "fill":
            lines += ["username=stub-user", f"password={FAKE_STORED_SECRET}"]
        return self.run_cmd([GIT, "credential", action], env, "\n".join(lines) + "\n\n")


class TrackedFilesTest(SandboxTestCase):
    """The tracked config's keys, the wrappers' form, and the .local/bin links."""

    def git_config(self, *args):
        self.require_git()
        self.require(TRACKED_CONFIG)
        return self.run_cmd(
            [GIT, "config", "--file", TRACKED_CONFIG, *args],
            self.wrapper_env(GIT_CONFIG_NOSYSTEM="1"),
        )

    def get_all(self, key):
        result = self.git_config("--null", "--get-all", key)
        self.assertEqual(result.returncode, 0, f"{key} is not set in the tracked config")
        return result.stdout.split("\0")[:-1]

    def test_general_helper_resets_then_runs_gcm_wrapper(self):
        self.assertEqual(self.get_all("credential.helper"), ["", GCM_HELPER])

    def test_github_hosts_reset_then_run_gh_wrapper(self):
        for url in GITHUB_HOSTS:
            with self.subTest(url=url):
                self.assertEqual(self.get_all(f"credential.{url}.helper"), ["", GH_HELPER])

    def test_gui_prompt_off_and_cache_timeout_eight_hours(self):
        self.assertEqual(self.get_all("credential.guiPrompt"), ["false"])
        self.assertEqual(self.get_all("credential.cacheOptions"), ["--timeout 28800"])

    def test_interactive_and_credential_store_are_not_set(self):
        result = self.git_config("--name-only", "--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        names = [name.lower() for name in result.stdout.splitlines()]
        self.assertIn("credential.helper", names)
        credential = [name for name in names if name.startswith("credential.")]
        # Agents opt out of prompts via GCM_INTERACTIVE=0; humans keep their prompt.
        self.assertEqual([n for n in credential if n.endswith(".interactive")], [])
        # The store comes from the GCM wrapper's env default, so macOS keeps Keychain.
        self.assertEqual([n for n in credential if n.endswith(".credentialstore")], [])

    def test_wrappers_are_executable_posix_sh(self):
        for wrapper in (GCM_WRAPPER, GH_WRAPPER):
            with self.subTest(wrapper=wrapper.name):
                self.require(wrapper)
                self.assertTrue(os.access(wrapper, os.X_OK), f"{wrapper.name} is not executable")
                first_line = wrapper.read_text().splitlines()[0]
                self.assertEqual(first_line, "#!/bin/sh")

    def test_wrappers_pass_shellcheck(self):
        self.require(GCM_WRAPPER, GH_WRAPPER)
        if SHELLCHECK is None:
            self.skipTest("shellcheck is not installed")
        result = subprocess.run(
            [SHELLCHECK, str(GCM_WRAPPER), str(GH_WRAPPER)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_local_bin_links_point_into_gcm_helper(self):
        for link in (GCM_LINK, GH_LINK):
            with self.subTest(link=link.name):
                self.require(link)
                self.assertTrue(link.is_symlink(), f"{link.name} must be a symlink")
                self.assertEqual(os.readlink(link), f"gcm-helper/{link.name}")


class HelperRoutingTest(SandboxTestCase):
    """Which wrapper the tracked config sends each host to, for get, store and erase.

    Silent logging stubs stand in for both wrappers, so git walks the complete
    helper list for every operation and the log shows every helper it ran.
    """

    def setUp(self):
        super().setUp()
        self.require(TRACKED_CONFIG)
        self.require_git()
        self.write_log_stub(self.home_bin / "git-credential-gcm", "gcm")
        self.write_log_stub(self.home_bin / "git-credential-gh", "gh")

    def assert_routing(self, env):
        for url, host, expected in HOST_CASES:
            for action, op in ACTIONS:
                with self.subTest(url=url, action=action):
                    self.log.write_text("")
                    result = self.credential(action, url, env)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self.calls(), [(expected, op, host)])

    def test_routing_under_env_i_with_minimal_path(self):
        self.install_config()
        self.assert_routing(self.git_env())

    def test_routing_from_xdg_config_home(self):
        xdg = self.root / "xdg"
        self.install_config(xdg)
        self.assert_routing(self.git_env(XDG_CONFIG_HOME=str(xdg)))


class EndToEndTest(SandboxTestCase):
    """The real wrappers, reached through the tracked config, hand off to stub binaries."""

    def setUp(self):
        super().setUp()
        self.require(TRACKED_CONFIG, GCM_WRAPPER, GCM_LINK, GH_WRAPPER)
        self.require_git()
        self.require_no_gh_on_min_path()
        self.install_config()
        self.install_gcm_wrapper()
        fake = self.install_gh_wrapper()
        self.write_log_stub(
            self.home_bin / "git-credential-manager", "gcm-bin", FAKE_GCM_SECRET
        )
        self.write_log_stub(
            fake["/home/linuxbrew/.linuxbrew"] / "bin" / "gh", "gh-bin", FAKE_GH_SECRET
        )

    def assert_served(self, url, host, label, args_prefix, secret):
        self.log.write_text("")
        fill = self.credential("fill", url, self.git_env())
        self.assertEqual(fill.returncode, 0, fill.stderr)
        self.assertEqual(fill.stderr, "")
        self.assertIn(f"password={secret}\n", fill.stdout)
        self.assertEqual(self.calls(), [(label, f"{args_prefix}get", host)])

        self.log.write_text("")
        store = self.credential("approve", url, self.git_env())
        self.assertEqual(store.returncode, 0, store.stderr)
        self.assertEqual(store.stderr, "")
        self.assertEqual(self.calls(), [(label, f"{args_prefix}store", host)])

    def test_github_hosts_reach_only_gh(self):
        for url, host, wrapper in HOST_CASES:
            if wrapper == "gh":
                with self.subTest(url=url):
                    self.assert_served(
                        url, host, "gh-bin", "auth git-credential ", FAKE_GH_SECRET
                    )

    def test_other_hosts_reach_only_gcm(self):
        for url, host, wrapper in HOST_CASES:
            if wrapper == "gcm":
                with self.subTest(url=url):
                    self.assert_served(url, host, "gcm-bin", "", FAKE_GCM_SECRET)


class MissingBinaryTest(SandboxTestCase):
    """With GCM or gh absent, git falls through to its prompt with no wrapper error."""

    def setUp(self):
        super().setUp()
        self.require(TRACKED_CONFIG, GCM_WRAPPER, GCM_LINK, GH_WRAPPER)
        self.require_git()
        self.install_config()
        self.install_gcm_wrapper()
        self.install_gh_wrapper()

    def assert_silent(self, url):
        for action, _ in ACTIONS:
            with self.subTest(url=url, action=action):
                result = self.credential(action, url, self.git_env())
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                if action == "fill":
                    self.assertIn(f"password={FAKE_ASKPASS_SECRET}\n", result.stdout)

    def test_fill_without_gcm_is_silent(self):
        self.assert_silent("https://example.invalid/repo.git")

    def test_fill_with_dangling_gcm_link_is_silent(self):
        (self.home_bin / "git-credential-manager").symlink_to(
            self.root / "pruned" / "git-credential-manager"
        )
        self.assert_silent("https://example.invalid/repo.git")

    def test_fill_without_gh_is_silent(self):
        self.require_no_gh_on_min_path()
        for url in GITHUB_HOSTS:
            self.assert_silent(f"{url}/example/repo.git")


class GcmWrapperTest(SandboxTestCase):
    """git-credential-gcm: silent when GCM is absent, otherwise execs it.

    On Linux it exports GCM_CREDENTIAL_STORE=cache when the variable is unset; on
    macOS it leaves the variable alone so GCM keeps its Keychain default. The
    tests named *_stubbed_* put a stub `uname` first on PATH to choose the branch.
    """

    def setUp(self):
        super().setUp()
        self.require(GCM_WRAPPER)
        self.gcm = self.home_bin / "git-credential-manager"

    def run_wrapper(self, op="get", path=MIN_PATH, **extra):
        return self.run_cmd([GCM_WRAPPER, op], self.wrapper_env(path, **extra), CRED_INPUT)

    def stub_uname(self, system):
        self.write_script(self.stubs / "uname", f"echo {system}\n")
        return f"{self.stubs}:{MIN_PATH}"

    def store_seen_by_gcm(self, path=MIN_PATH, **extra):
        self.write_record_stub(self.gcm, "gcm")
        result = self.run_wrapper(path=path, **extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.recorded()["store"]

    def assert_silent_success(self, result):
        self.assertEqual(
            (result.returncode, result.stdout, result.stderr), (0, "", "")
        )

    def test_absent_gcm_exits_zero_silently(self):
        for op in ("get", "store", "erase"):
            with self.subTest(op=op):
                self.assert_silent_success(self.run_wrapper(op))

    def test_dangling_gcm_link_exits_zero_silently(self):
        self.gcm.symlink_to(self.root / "pruned" / "git-credential-manager")
        for op in ("get", "store", "erase"):
            with self.subTest(op=op):
                self.assert_silent_success(self.run_wrapper(op))

    def test_execs_gcm_with_args_stdin_and_output(self):
        output = f"username=gcm-user\npassword={FAKE_GCM_SECRET}\n"
        self.write_record_stub(self.gcm, "gcm", output=output)
        for op in ("get", "store", "erase"):
            with self.subTest(op=op):
                result = self.run_wrapper(op)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, output)
                self.assertEqual(result.stderr, "")
                seen = self.recorded()
                self.assertEqual(seen["args"], op)
                self.assertEqual(seen["stdin"], CRED_INPUT)

    def test_propagates_gcm_exit_status(self):
        self.write_record_stub(self.gcm, "gcm", code=3)
        self.assertEqual(self.run_wrapper().returncode, 3)

    @unittest.skipUnless(platform.system() == "Linux", "Linux default store")
    def test_linux_host_defaults_store_to_cache(self):
        self.assertEqual(self.store_seen_by_gcm(), "cache")

    def test_host_keeps_explicit_store(self):
        self.assertEqual(self.store_seen_by_gcm(GCM_CREDENTIAL_STORE="gpg"), "gpg")

    def test_stubbed_linux_defaults_store_to_cache(self):
        self.assertEqual(self.store_seen_by_gcm(self.stub_uname("Linux")), "cache")

    def test_stubbed_linux_keeps_explicit_store(self):
        path = self.stub_uname("Linux")
        self.assertEqual(self.store_seen_by_gcm(path, GCM_CREDENTIAL_STORE="gpg"), "gpg")

    def test_stubbed_macos_leaves_store_unset(self):
        self.assertEqual(self.store_seen_by_gcm(self.stub_uname("Darwin")), UNSET)

    def test_stubbed_macos_keeps_explicit_store(self):
        path = self.stub_uname("Darwin")
        self.assertEqual(self.store_seen_by_gcm(path, GCM_CREDENTIAL_STORE="cache"), "cache")


class GhWrapperTest(SandboxTestCase):
    """git-credential-gh: finds gh on PATH, then in brew prefixes, else exits 0."""

    def setUp(self):
        super().setUp()
        self.require(GH_WRAPPER)
        self.fake = self.install_gh_wrapper()
        self.wrapper = self.home_bin / "git-credential-gh"

    def run_wrapper(self, op="get", path=MIN_PATH):
        return self.run_cmd([self.wrapper, op], self.wrapper_env(path), CRED_INPUT)

    def test_execs_gh_from_path_with_args_stdin_and_output(self):
        output = f"username=gh-user\npassword={FAKE_GH_SECRET}\n"
        self.write_record_stub(self.stubs / "gh", "path-gh", output=output)
        for op in ("get", "store", "erase"):
            with self.subTest(op=op):
                result = self.run_wrapper(op, f"{self.stubs}:{MIN_PATH}")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, output)
                self.assertEqual(result.stderr, "")
                seen = self.recorded()
                self.assertEqual(seen["args"], f"auth git-credential {op}")
                self.assertEqual(seen["stdin"], CRED_INPUT)

    def test_gh_on_path_wins_over_brew_prefix(self):
        self.write_record_stub(self.stubs / "gh", "path-gh")
        self.write_record_stub(self.fake[BREW_ROOTS[0]] / "bin" / "gh", "brew-gh")
        result = self.run_wrapper(path=f"{self.stubs}:{MIN_PATH}")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded()["label"], "path-gh")

    def test_finds_gh_in_each_brew_prefix(self):
        self.require_no_gh_on_min_path()
        for root, prefix in self.fake.items():
            with self.subTest(prefix=root):
                for other in self.fake.values():
                    (other / "bin" / "gh").unlink(missing_ok=True)
                self.record.unlink(missing_ok=True)
                self.write_record_stub(prefix / "bin" / "gh", root)
                result = self.run_wrapper()
                self.assertEqual(result.returncode, 0, result.stderr)
                seen = self.recorded()
                self.assertEqual(seen["label"], root)
                self.assertEqual(seen["args"], "auth git-credential get")

    def test_propagates_gh_exit_status(self):
        self.write_record_stub(self.stubs / "gh", "path-gh", code=4)
        self.assertEqual(self.run_wrapper(path=f"{self.stubs}:{MIN_PATH}").returncode, 4)

    def test_absent_gh_exits_zero_silently(self):
        self.require_no_gh_on_min_path()
        for op in ("get", "store", "erase"):
            with self.subTest(op=op):
                result = self.run_wrapper(op)
                self.assertEqual(
                    (result.returncode, result.stdout, result.stderr), (0, "", "")
                )


if __name__ == "__main__":
    unittest.main()
