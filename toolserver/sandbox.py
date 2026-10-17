"""One sandbox container per agent run: where agent-controlled code (its RTL, its Python tests) runs.

The container has no network, a read-only root filesystem, the workspace mounted read-only, a
small scratch /tmp, no capabilities, an unprivileged user, and memory / process limits. Only the
workspace and box_runner.py are mounted: no repository, so no answer key.

Each tool call is one `docker exec` under `timeout -s KILL`. Afterwards every process left in the
container is killed (except the idle PID 1), so a hung simulator or a background process an agent
test started can't outlive the call.
"""

import secrets
import subprocess
from pathlib import Path

BOX_RUNNER = Path(__file__).resolve().parent / "box_runner.py"
IMAGE = "rtl-debug-agent:dev"
LABEL = "prip.sandbox"
# Kills every process this user can signal except the caller (and PID 1, which Linux excludes).
KILL_ALL = ["python", "-c", "import os, signal\ntry: os.kill(-1, signal.SIGKILL)\nexcept ProcessLookupError: pass"]


class SandboxError(Exception):
    pass


class Sandbox:
    def __init__(self, workspace: Path, image: str = IMAGE, memory: str = "2g", pids: int = 256,
                 cpus: str = "2", tmp_size: str = "512m"):
        self.workspace = Path(workspace).resolve()
        self.image = image
        self.name = f"prip-sbx-{secrets.token_hex(6)}"
        self.opts = ["--memory", memory, "--memory-swap", memory, "--pids-limit", str(pids),
                     "--cpus", cpus, "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size={tmp_size}"]
        self.running = False

    def start(self):
        cmd = ["docker", "run", "-d", "--rm", "--name", self.name, "--label", f"{LABEL}=1",
               "--network", "none", "--read-only", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--user", "65534:65534",
               *self.opts,
               "-e", "HOME=/tmp", "-e", "PYTHONDONTWRITEBYTECODE=1",
               "-v", f"{self.workspace}:/ws:ro",
               "-v", f"{BOX_RUNNER}:/opt/box/box_runner.py:ro",
               "-w", "/tmp", "--entrypoint", "sleep", self.image, "infinity"]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode:
            raise SandboxError(f"could not start sandbox: {p.stderr.strip()}")
        self.running = True

    def exec(self, argv: list[str], timeout: int) -> tuple[int, str, bool]:
        """Runs argv in the sandbox. Returns (exit code, combined output, timed out)."""
        cmd = ["docker", "exec", self.name, "timeout", "-s", "KILL", str(timeout), *argv]
        try:
            # The host-side limit is a backstop for a stuck `docker exec` itself.
            p = subprocess.run(cmd, capture_output=True, timeout=timeout + 30)
            rc, out = p.returncode, (p.stdout + p.stderr).decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired as e:
            rc, out = 137, ((e.stdout or b"") + (e.stderr or b"")).decode("utf-8", errors="replace")
        finally:
            subprocess.run(["docker", "exec", self.name, *KILL_ALL], capture_output=True, timeout=30)
        return rc, out, rc == 137

    def stop(self):
        if self.running:
            subprocess.run(["docker", "kill", self.name], capture_output=True)
            self.running = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()


def repo_mount(root: Path) -> list[str]:
    """docker run options that mount the repo at /work for trusted containers (grading), with the
    repo's .env (the OpenRouter API key) hidden behind an empty file. Never use for agent code."""
    root = Path(root).resolve()
    mask = ["-v", f"{root / 'docker' / 'no_env'}:/work/.env:ro"] if (root / ".env").exists() else []
    return ["-v", f"{root}:/work", *mask, "-w", "/work"]


def remove_leftovers():
    """Kills sandboxes left behind by a crashed server."""
    ids = subprocess.run(["docker", "ps", "-q", "--filter", f"label={LABEL}"],
                         capture_output=True, text=True).stdout.split()
    if ids:
        subprocess.run(["docker", "kill", *ids], capture_output=True)
