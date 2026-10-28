"""Stop hook gate. Run the goal's tests: exit 0 = goal met, the agent may finish; exit 2 = block the finish."""
import json, os, re, subprocess, sys

def main() -> int:
    hook = json.load(sys.stdin)  # the hook input: session_id, cwd, hook_event_name, stop_hook_active, ...
    goal = sys.argv[1:]              # the goal: test files or test ids that must all pass
    if not goal:
        print("Stop blocked: the gate has no goal tests.", file=sys.stderr)
        return 2
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider", *goal],
                         cwd=hook.get("cwd", os.getcwd()), capture_output=True, text=True)
    if run.returncode == 0:
        return 0                     # every goal test passed
    count = re.search(r"(\d+) failed", run.stdout)
    failed = [line for line in run.stdout.splitlines() if line.startswith("FAILED")]
    # stop_hook_active is not read on purpose: a second stop attempt must still be red, never a free pass
    reason = failed[:6] or run.stdout.splitlines()[-3:]  # no FAILED line (usage error, missing file): the last lines
    print(f"Stop blocked: {count.group(1) if count else 'some'} goal test(s) fail. Fix them, then finish again:\n"
          + "\n".join(reason), file=sys.stderr)
    return 2

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:       # fail closed: an unexpected error blocks the finish too
        print(f"Stop blocked: the gate failed: {error}", file=sys.stderr)
        sys.exit(2)
