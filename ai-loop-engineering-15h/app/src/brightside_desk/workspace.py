"""The desk's git repo: one worktree and one branch per scheduled run, and the reviewer's diff (lessons 21 and 24).

`main` is the desk's book of record: one file per case, under cases/. A scheduled run works in its own worktree,
on its own branch made from `main`. It commits its case file only when its checks are green. A run that waits for
a reviewer keeps its branch; an approval merges that branch into `main`. A worktree isolates files, not the machine,
so the run's permissions still come from permissions.py.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
IDENTITY = ["-c", "user.name=brightside-desk", "-c", "user.email=desk@example.com"]  # a stand-in author, no person


class GitError(RuntimeError):
    """A git command failed. The message is git's own, and it contains no secrets."""


class DeskRepo:
    def __init__(self, root: Path) -> None:
        self.root = root  # the main checkout: only merges and the first commit are made here

    def _git(self, *args: str, cwd: Path | None = None) -> str:
        r = subprocess.run(["git", *IDENTITY, *args], cwd=cwd or self.root, capture_output=True, text=True)
        if r.returncode:
            raise GitError(r.stderr.strip() or f"git {args[0]} failed")
        return r.stdout.strip()

    def ensure(self) -> None:
        """Make the repo on first use: one commit on main, with an empty cases/ folder."""
        if (self.root / ".git").exists():
            return
        self.root.mkdir(parents=True, exist_ok=True)
        self._git("init", "-q", "-b", "main")
        (self.root / "cases").mkdir()
        (self.root / "cases" / ".gitkeep").write_text("", encoding="utf-8")
        (self.root / "README.md").write_text("Brightside desk record: one file per case, on its run's branch.\n",
                                             encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "desk record as shipped")

    def add_run(self, branch: str, folder: Path) -> Path:
        """One worktree and one new branch, both from main. The run edits only this folder."""
        self.ensure()
        folder.parent.mkdir(parents=True, exist_ok=True)
        self._git("worktree", "add", "-q", "-b", branch, str(folder), "main")
        return folder

    def commit_case(self, folder: Path, ticket: str, record: dict[str, Any]) -> str:
        """Write the run's case file and commit it on the run's branch. Returns the short commit id."""
        path = folder / "cases" / f"{ticket}.json"
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self._git("add", "-A", cwd=folder)
        self._git("commit", "-q", "-m", f"case {ticket}", cwd=folder)
        return self._git("log", "-1", "--format=%h", cwd=folder)

    def remove_run(self, folder: Path, branch: str, keep_branch: bool) -> None:
        """Remove the run's folder. The branch stays as the record unless the run left nothing to keep."""
        self._git("worktree", "remove", str(folder))  # refuses if the folder holds uncommitted work
        if not keep_branch:
            self._git("branch", "-D", branch)

    def review_text(self, branch: str, ticket: str) -> str:
        """What the reviewer reads: the files the branch changes, and the case file itself."""
        stat = self._git("show", "--stat", "--format=", branch)
        body = self._git("show", f"{branch}:cases/{ticket}.json")
        return f"{stat}\n{body}"

    def merge(self, branch: str) -> None:
        """Merge a reviewed run into main. Called only inside an approval, while the lease is checked."""
        self._git("merge", "-q", "--no-edit", branch)

    def has_file_on_main(self, ticket: str) -> bool:
        return (self.root / "cases" / f"{ticket}.json").exists()
