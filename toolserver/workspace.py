"""The agent's workspace for one run, and the only file access the tool server does on its behalf.

Layout (the agent sees it at /ws inside the sandbox):
  <top>.v            working copy of the buggy RTL; the agent edits this and it is what gets submitted
  spec.md            plain-language spec
  original/<top>.v   the buggy file as handed out (read-only), so claimed lines can use its numbering
  tests/<name>.py    the agent's own cocotb tests

No golden RTL, reference test, manifest, meta.json or bug ID is ever copied in.

The sandbox mounts the workspace read-only, so only this module writes to it. It still never
follows a symlink or opens anything but a regular file: the host must not be talked into reading
or overwriting a file outside the workspace (e.g. designs/<name>/golden.v) through a planted link.
"""

import os
import re
import shutil
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_FILE_BYTES = 200_000
TEST_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\.py")


class WorkspaceError(Exception):
    """A refused file operation; the message is safe to show the agent."""


def create(bug: dict, workspace: Path) -> "Workspace":
    top = bug["top"]
    workspace.mkdir(parents=True)
    (workspace / "original").mkdir()
    (workspace / "tests").mkdir()
    buggy = (ROOT / bug["file"]).read_text()
    (workspace / f"{top}.v").write_text(buggy)
    (workspace / "original" / f"{top}.v").write_text(buggy)
    (workspace / "original" / f"{top}.v").chmod(0o444)
    shutil.copyfile(ROOT / "designs" / bug["design"] / "spec.md", workspace / "spec.md")
    return Workspace(workspace, top)


class Workspace:
    def __init__(self, root: Path, top: str):
        self.root = Path(root)
        self.top = top
        self.rtl = f"{top}.v"
        self.original = f"original/{top}.v"

    def readable(self) -> list[str]:
        return [self.rtl, "spec.md", self.original] + [f"tests/{n}" for n in self.test_files()]

    def _parse(self, path: str, writing: bool) -> tuple[list[str], str]:
        """Checks `path` against the fixed layout. Returns (directory parts, file name)."""
        if not isinstance(path, str) or "\\" in path or "\0" in path:
            raise WorkspaceError(f"invalid path {path!r}")
        parts = path.split("/")
        if path == self.rtl or (not writing and path in ("spec.md", self.original)):
            return parts[:-1], parts[-1]
        if len(parts) == 2 and parts[0] == "tests" and TEST_NAME.fullmatch(parts[1]):
            return ["tests"], parts[1]
        allowed = f"{self.rtl} or tests/<name>.py" if writing else \
            f"{self.rtl}, spec.md, {self.original} or tests/<name>.py"
        verb = "write" if writing else "read"
        raise WorkspaceError(f"can't {verb} {path!r}: paths are relative to the workspace; "
                             f"you can {verb} {allowed}")

    def _dir_fd(self, parts: list[str]) -> int:
        """Opens the workspace directory, then each part below it, refusing symlinks."""
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for p in parts:
                nfd = os.open(p, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nfd
        except OSError:
            os.close(fd)
            raise WorkspaceError(f"{'/'.join(parts)}/ is not a plain directory")
        return fd

    def read(self, path: str) -> str:
        parts, name = self._parse(path, writing=False)
        d = self._dir_fd(parts)
        try:
            # O_NONBLOCK: a planted FIFO must not hang the server on open.
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=d)
        except FileNotFoundError:
            raise WorkspaceError(f"{path} does not exist")
        except OSError:
            raise WorkspaceError(f"{path} is not a regular file")
        finally:
            os.close(d)
        with os.fdopen(fd, "rb") as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                raise WorkspaceError(f"{path} is not a regular file")
            data = f.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise WorkspaceError(f"{path} is larger than {MAX_FILE_BYTES} bytes")
        return data.decode("utf-8", errors="replace")

    def write(self, path: str, content: str):
        parts, name = self._parse(path, writing=True)
        data = content.encode("utf-8")
        if len(data) > MAX_FILE_BYTES:
            raise WorkspaceError(f"content is larger than {MAX_FILE_BYTES} bytes")
        d = self._dir_fd(parts)
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o644, dir_fd=d)
        except OSError:
            raise WorkspaceError(f"{path} is not a regular file")
        finally:
            os.close(d)
        with os.fdopen(fd, "wb") as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                raise WorkspaceError(f"{path} is not a regular file")
            f.truncate(0)
            f.write(data)

    def test_files(self) -> list[str]:
        d = self._dir_fd(["tests"])
        try:
            names = os.listdir(d)
            return sorted(n for n in names if TEST_NAME.fullmatch(n)
                          and stat.S_ISREG(os.stat(n, dir_fd=d, follow_symlinks=False).st_mode))
        finally:
            os.close(d)

    def snapshot_tests(self, dest: Path) -> list[str]:
        """Copies every test file to dest/ (through the same checks). Returns the names."""
        dest.mkdir(parents=True, exist_ok=True)
        names = self.test_files()
        for n in names:
            (dest / n).write_text(self.read(f"tests/{n}"))
        return names
