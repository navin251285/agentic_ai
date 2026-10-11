#!/usr/bin/env python3
"""Check whether this machine can run the cluster lessons (Docker Compose and Kubernetes via kind).

Usage:
    python3 scripts/check_env.py            # check tools, limits and resources
    python3 scripts/check_env.py --smoke    # also create and delete a real 4-node kind cluster
    python3 scripts/check_env.py --json     # machine-readable result (used by /tutorial-plan)

Install instructions: docs/INFRA_SETUP.md (in a generated course: SETUP_CLUSTERS.md next to this script)
Exit code 0 = Docker lessons can run; the report says which lesson kinds (docker, k8s) are ready.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KIND_CONFIG = """kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
- role: worker
- role: worker
- role: worker
"""


def run(cmd: list[str], timeout: int = 30) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode == 0, (p.stdout or p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def first_line(text: str) -> str:
    return text.splitlines()[0][:80] if text else ""


def mem_gb() -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) / 1024 / 1024
    except OSError:
        pass
    try:  # macOS
        ok, out = run(["sysctl", "-n", "hw.memsize"])
        return int(out) / 1024 ** 3 if ok else None
    except ValueError:
        return None


def sysctl(name: str) -> int | None:
    try:
        return int(Path("/proc/sys/" + name.replace(".", "/")).read_text().strip())
    except (OSError, ValueError):
        return None


def check() -> dict:
    r: dict = {"checks": []}

    def add(name, ok, detail, fix="", needed_for="docker"):
        r["checks"].append({"name": name, "ok": ok, "detail": detail, "fix": fix, "needed_for": needed_for})

    if shutil.which("docker"):
        ok, out = run(["docker", "version", "--format", "{{.Server.Version}}"])
        add("docker", ok, f"server {out}" if ok else (first_line(out) or "installed, but the Docker daemon is not reachable"),
            "" if ok else "Docker is installed but not reachable: start it, or add yourself to the docker group "
                          "(sudo usermod -aG docker $USER, then log in again)")
        ok_c, out_c = run(["docker", "compose", "version", "--short"])
        add("docker compose", ok_c, out_c if ok_c else first_line(out_c), "" if ok_c else "Install the Docker Compose plugin")
    else:
        add("docker", False, "not installed", "See the setup guide, step 1")
        add("docker compose", False, "not installed", "Comes with Docker")

    for tool, args, step in [("kind", ["kind", "version"], 2),
                             ("kubectl", ["kubectl", "version", "--client"], 3),
                             ("helm", ["helm", "version", "--short"], 4)]:
        if shutil.which(tool):
            ok, out = run(args)
            add(tool, ok, first_line(out), "", "k8s")
        else:
            add(tool, False, "not installed", f"See the setup guide, step {step}", "k8s")

    if sys.platform.startswith("linux"):
        for name, need in [("fs.inotify.max_user_watches", 524288), ("fs.inotify.max_user_instances", 512)]:
            v = sysctl(name)
            add(name, v is not None and v >= need, f"{v}", f"Set to {need}: setup guide, step 5", "k8s")

    cpus = os.cpu_count() or 0
    add("CPUs", cpus >= 4, f"{cpus}", "4+ recommended for cluster lessons", "k8s")
    gb = mem_gb()
    add("RAM", gb is not None and gb >= 8, f"{gb:.1f} GB" if gb else "unknown",
        "16 GB comfortable, 8 GB minimum for cluster lessons", "k8s")
    free = shutil.disk_usage(Path.cwd()).free / 1024 ** 3
    add("free disk", free >= 20, f"{free:.0f} GB", "50 GB comfortable, 20 GB minimum", "k8s")

    docker_ok = all(c["ok"] for c in r["checks"] if c["name"] in ("docker", "docker compose"))
    k8s_ok = docker_ok and all(c["ok"] for c in r["checks"] if c["needed_for"] == "k8s"
                               and c["name"] not in ("CPUs", "RAM", "free disk"))
    r["ready"] = {"docker": docker_ok, "k8s": k8s_ok}
    r["enable"] = ",".join(k for k, v in r["ready"].items() if v)
    return r


def smoke() -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(KIND_CONFIG)
        cfg = f.name
    name = "tut-env-check"
    try:
        ok, out = run(["kind", "create", "cluster", "--name", name, "--config", cfg, "--wait", "180s"], timeout=420)
        if not ok:
            return False, "kind could not create the cluster:\n" + out[-800:]
        ok, out = run(["kubectl", "get", "nodes", "--context", f"kind-{name}", "--no-headers"])
        ready = [l for l in out.splitlines() if " Ready " in f" {l} "]
        return ok and len(ready) == 4, f"{len(ready)}/4 nodes Ready\n{out}"
    finally:
        run(["kind", "delete", "cluster", "--name", name], timeout=180)
        os.unlink(cfg)


def main(argv: list[str]) -> int:
    r = check()
    if "--smoke" in argv:
        if r["ready"]["k8s"]:
            ok, detail = smoke()
            r["smoke"] = {"ok": ok, "detail": detail}
            r["ready"]["k8s"] = ok
            r["enable"] = ",".join(k for k, v in r["ready"].items() if v)
        else:
            r["smoke"] = {"ok": False, "detail": "skipped: Kubernetes tools not ready"}
    if "--json" in argv:
        print(json.dumps(r, indent=2))
        return 0 if r["ready"]["docker"] else 1

    for c in r["checks"]:
        mark = "✓" if c["ok"] else "✗"
        print(f"{mark} {c['name']:<30} {c['detail']}" + (f"\n    → {c['fix']}" if not c["ok"] and c["fix"] else ""))
    if "smoke" in r:
        print(f"{'✓' if r['smoke']['ok'] else '✗'} 4-node kind cluster smoke test: {r['smoke']['detail'].splitlines()[0]}")
    print()
    print(f"Docker Compose cluster lessons: {'ready' if r['ready']['docker'] else 'NOT ready'}")
    print(f"Kubernetes (kind) lessons:      {'ready' if r['ready']['k8s'] else 'NOT ready'}")
    if r["enable"]:
        print(f"Run those cells for real with: TUT_ENABLE={r['enable']}")
    else:
        print("Cluster cells will show recorded output. Install guide: docs/INFRA_SETUP.md")
    return 0 if r["ready"]["docker"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
