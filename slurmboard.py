#!/usr/bin/env python3
"""slurmboard: a to-do style tracker for your Slurm calculations.

One row per calculation (work directory + job name); the newest attempt
decides its status. Failed / timed-out / OOM jobs, and jobs whose program
did not finish normally, land in "Needs attention" until you resubmit or
dismiss them.

Usage:
    slurmboard.py status [--all]          print the board in the terminal
    slurmboard.py sync                    refresh state once and exit
    slurmboard.py json [--no-sync]        board as JSON (used by the VSCode extension)
    slurmboard.py resubmit KEY [--extra "--time=2-00:00:00"]
    slurmboard.py dismiss KEY... [--undo]
    slurmboard.py note KEY TEXT

Program-specific checks (ORCA, Gaussian, Q-Chem, ...) are listed in PROGRAMS
below. Add or override them in ~/.slurmboard/config.json:
    {"programs": [{"name": "MyCode", "detect": ["MyCode v"],
                   "success": ["finished OK"], "inputs": [".in"],
                   "resubmit": "submit_mycode {input}"}]}

Stdlib only, Python >= 3.6. State lives in ~/.slurmboard/.
"""
import argparse
import fcntl
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

STATE_DIR = os.path.expanduser("~/.slurmboard")
STATE_FILE = os.path.join(STATE_DIR, "state.json")
LOCK_FILE = os.path.join(STATE_DIR, "lock")
CONFIG_FILE = os.path.join(STATE_DIR, "config.json")
USER = os.environ.get("USER") or os.getlogin()

SACCT_FIELDS = ["JobID", "JobName", "State", "WorkDir", "ExitCode", "Submit", "Start",
                "End", "Elapsed", "Timelimit", "SubmitLine", "StdOut", "StdErr",
                "NodeList", "Reason"]
SEP = "\x1f"
RUNNING = {"RUNNING", "COMPLETING", "CONFIGURING", "STAGE_OUT", "SIGNALING"}
PENDING = {"PENDING", "REQUEUED", "REQUEUE_HOLD", "REQUEUE_FED", "SUSPENDED",
           "RESIZING", "SPECIAL_EXIT"}
INSPECT_VERSION = 3  # bump to re-inspect cached finished jobs after changing the checks

# How to recognise each program's output and judge whether it finished cleanly.
#   detect   - any of these strings near the top of the output identifies the program
#   success  - one of these must appear near the end, or the job "needs attention"
#   failure  - any of these near the end means it failed even if success also appears
#   warnings - {text in tail: message} shown on otherwise-successful jobs
#   outputs  - the program's own log files; preferred over the Slurm stdout when present.
#              {stem} is the job name; wildcards pick the newest match (e.g. "*.log")
#   inputs   - input files for "Edit input" and {input} in resubmit: ".ext" means
#              <stem>.ext, anything else is a file pattern like the outputs
#   resubmit - command template run in the work directory when the sbatch script is
#              gone; {input}, {stem}, {workdir} are substituted
PROGRAMS = [
    {"name": "ORCA", "detect": ["O   R   C   A"], "success": ["ORCA TERMINATED NORMALLY"],
     "failure": ["ORCA finished by error termination"],
     "warnings": {"did not converge": "Geometry optimization did not converge"},
     "outputs": ["{stem}.out"], "inputs": [".inp"], "resubmit": "qorca {input}"},
    {"name": "Gaussian", "detect": ["Gaussian, Inc."], "success": ["Normal termination of Gaussian"],
     "failure": ["Error termination"], "outputs": ["{stem}.log", "{stem}.out"],
     "inputs": [".com", ".gjf"]},
    {"name": "Q-Chem", "detect": ["Q-Chem, Inc."],
     "success": ["Thank you very much for using Q-Chem"], "outputs": ["{stem}.out"],
     "inputs": [".in", ".inp"]},
    {"name": "Psi4", "detect": ["Psi4: An Open-Source Ab Initio"],
     "success": ["Psi4 exiting successfully"], "outputs": ["{stem}.out"], "inputs": [".dat", ".in"]},
    {"name": "CP2K", "detect": ["CP2K|"], "success": ["PROGRAM ENDED AT"],
     "outputs": ["{stem}.out"], "inputs": [".inp"]},
    {"name": "xtb", "detect": ["x T B"], "success": ["normal termination of xtb"],
     "outputs": ["{stem}.out"], "inputs": []},
    {"name": "GROMACS", "detect": [":-) GROMACS", "GROMACS:      gmx"],
     "success": ["Finished mdrun on rank 0", "GROMACS reminds you"],
     "failure": ["Fatal error:"], "outputs": ["{stem}.log", "md.log", "*.log"],
     "inputs": [".mdp", "*.mdp"]},
    {"name": "LAMMPS", "detect": ["LAMMPS ("], "success": ["Total wall time:"],
     "failure": ["ERROR:", "ERROR on proc"],
     "outputs": ["log.lammps", "log.{stem}", "{stem}.log"],
     "inputs": ["in.{stem}", ".in", ".lmp", "in.*", "*.in"]},
    {"name": "TeraChem", "detect": ["TeraChem"], "success": ["Job finished"],
     "outputs": ["{stem}.out"], "inputs": [".in"]},
]


# --------------------------------------------------------------- config ----

def load_programs():
    """Built-in profiles, overridden/extended by config file and $SLURMBOARD_PROGRAMS."""
    progs = {p["name"]: dict(p) for p in PROGRAMS}
    extra = []
    try:
        with open(CONFIG_FILE) as f:
            extra += json.load(f).get("programs", [])
    except (OSError, ValueError):
        pass
    try:
        extra += json.loads(os.environ.get("SLURMBOARD_PROGRAMS") or "[]")
    except ValueError:
        pass
    for p in extra:
        if isinstance(p, dict) and p.get("name"):
            merged = dict(progs.get(p["name"], {}))
            merged.update(p)
            progs[p["name"]] = merged
    # user-defined profiles are tried first
    names = [p["name"] for p in extra if isinstance(p, dict) and p.get("name")]
    order = list(dict.fromkeys(names + [p["name"] for p in PROGRAMS]))
    return [progs[n] for n in order if n in progs]


# ---------------------------------------------------------------- state ----

def run(argv, cwd=None):
    return subprocess.run(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=60)


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"jobs": {}, "meta": {}, "last_sync": None, "sync_error": None}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)


class FileLock:
    def __enter__(self):
        self.fh = open(LOCK_FILE, "w")
        fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


def ensure_dirs():
    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)


# ----------------------------------------------------------------- sync ----

def job_sort_key(jobid):
    head = jobid.split("_")[0].split(".")[0]
    return int(head) if head.isdigit() else 0


CORE_FIELDS = {"JobID", "JobName", "State", "ExitCode", "Submit", "Start", "End", "Elapsed"}


def sacct_fields(state):
    """SACCT_FIELDS this Slurm version knows. Older versions lack e.g. StdOut, StdErr and
    SubmitLine, and sacct rejects the whole query on one unknown field. Cached for a day."""
    cache = state.get("sacct_fields") or {}
    if cache.get("fields") and time.time() - cache.get("t", 0) < 86400:
        return cache["fields"]
    out = run(["sacct", "--helpformat"])
    known = {w.lower() for w in out.stdout.split()} if out.returncode == 0 else set()
    fields = [f for f in SACCT_FIELDS if f in CORE_FIELDS or f.lower() in known]
    state["sacct_fields"] = {"t": time.time(), "fields": fields}
    return fields


def run_sacct(since, fields):
    cmd = ["sacct", "-u", USER, "-X", "-n", "-P", "--delimiter", SEP,
           "-S", since, "-o", ",".join(fields)]
    out = run(cmd)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "sacct failed")
    rows = []
    for line in out.stdout.splitlines():
        parts = line.split(SEP)
        if len(parts) != len(fields):
            continue
        row = dict.fromkeys(SACCT_FIELDS, "")
        row.update(zip(fields, parts))
        rows.append(row)
    return rows


def run_squeue():
    """{jobid: (workdir, command)} for queued/running jobs; fills gaps on older Slurm."""
    out = run(["squeue", "-u", USER, "-h", "-o", "%i" + SEP + "%Z" + SEP + "%o"])
    jobs = {}
    if out.returncode == 0:
        for line in out.stdout.splitlines():
            parts = line.split(SEP)
            if len(parts) == 3:
                jobs[parts[0].strip()] = (parts[1].strip(), parts[2].strip())
    return jobs


def expand_path(p, job):
    if not p:
        return ""
    jid = job["JobID"]
    return (p.replace("%j", jid.split("_")[0]).replace("%A", jid.split("_")[0])
             .replace("%x", job["JobName"]).replace("%u", USER))


def read_tail(path, nbytes):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - nbytes))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return None


def read_head(path, nbytes=16384):
    try:
        with open(path, "rb") as f:
            return f.read(nbytes).decode("utf-8", "replace")
    except OSError:
        return None


def stems(job):
    """Candidate base names for this job's files: job name and stdout file stem."""
    out = [job["name"]]
    if job.get("stdout"):
        s = os.path.splitext(os.path.basename(job["stdout"]))[0]
        if s not in out:
            out.append(s)
    return out


def resolve(job, pattern):
    """Existing-or-not paths for a file pattern; wildcard matches come newest first."""
    out = []
    for stem in stems(job):
        p = os.path.join(job["workdir"], pattern.format(stem=stem))
        if any(ch in p for ch in "*?["):
            def mtime(f):
                try:
                    return os.path.getmtime(f)
                except OSError:
                    return 0
            out.extend(sorted(glob.glob(p), key=mtime, reverse=True)[:20])
        else:
            out.append(p)
    return list(dict.fromkeys(out))


def detects(prog, head):
    return any(d in head for d in prog.get("detect", []))


def detect_program(job, programs):
    """Return (profile, output_path) for the first output file a profile recognises."""
    candidates = [job["stdout"]] if job.get("stdout") else []
    for prog in programs:
        for pat in prog.get("outputs", []):
            candidates += resolve(job, pat)
    for path in dict.fromkeys(candidates):
        head = read_head(path)
        if not head:
            continue
        for prog in programs:
            if not detects(prog, head):
                continue
            # prefer the program's own log (md.log, log.lammps, ...) over the Slurm stdout
            for pat in prog.get("outputs", []):
                for own in resolve(job, pat):
                    h = read_head(own) if own != path else head
                    if h and detects(prog, h):
                        return prog, own
            return prog, path
    return None, None


def find_input(job, prog, programs):
    pats = prog.get("inputs", []) if prog else []
    if not pats:  # unknown program: only try <stem>.<ext>, never broad wildcards
        pats = list(dict.fromkeys(e for p in programs for e in p.get("inputs", [])
                                  if e.startswith(".")))
    for pat in pats:
        for path in resolve(job, "{stem}" + pat if pat.startswith(".") else pat):
            if os.path.isfile(path):
                return path
    return None


def inspect_output(job, programs):
    """Look at a finished job's output once; the verdict is cached in the state file."""
    prog, out_path = detect_program(job, programs)
    out_path = out_path or job.get("stdout")
    out_tail = read_tail(out_path, 65536) if out_path else None
    err_tail = read_tail(job["stderr"], 4096) if job.get("stderr") else None
    info = {"v": INSPECT_VERSION, "program": prog["name"] if prog else None, "ok": None,
            "warning": None, "snippet": None, "output": out_path,
            "input": find_input(job, prog, programs)}
    if prog and out_tail is not None:
        failed = any(f in out_tail for f in prog.get("failure", []))
        succeeded = any(s in out_tail for s in prog.get("success", []))
        info["ok"] = succeeded and not failed
        for needle, msg in (prog.get("warnings") or {}).items():
            if needle in out_tail:
                info["warning"] = msg
    src = err_tail if err_tail and err_tail.strip() else out_tail
    if src and (job["category"] != "completed" or info["ok"] is False):
        lines = [l.rstrip() for l in src.splitlines() if l.strip()]
        idx = [i for i, l in enumerate(lines) if any(k in l.lower() for k in
               ("error", "abort", "killed", "oom", "cancelled", "time limit", "segmentation"))]
        # headings like GROMACS's "Fatal error:" put the actual message on the next line
        idx = sorted(set(idx + [i + 1 for i in idx
                                if lines[i].endswith(":") and i + 1 < len(lines)]))
        pick = [lines[i] for i in idx][-6:] if idx else lines[-6:]
        info["snippet"] = "\n".join(l[:200] for l in pick)
    return info


def categorize(state_str):
    if state_str in RUNNING:
        return "running"
    if state_str in PENDING:
        return "pending"
    if state_str == "COMPLETED":
        return "completed"
    return "attention"


def sync(state, initial_days=14):
    if state.get("last_sync"):
        since = time.strftime("%Y-%m-%dT%H:%M:%S",
                              time.localtime(state["last_sync"] - 6 * 3600))
    else:
        since = time.strftime("%Y-%m-%dT00:00:00", time.localtime(time.time() - initial_days * 86400))
    fields = sacct_fields(state)
    rows = run_sacct(since, fields)
    missing = {"WorkDir", "SubmitLine", "StdOut"} - set(fields)
    queued = run_squeue() if missing else {}
    programs = load_programs()
    jobs = state["jobs"]
    # jobs outside the sacct window whose cached check predates the current rules
    for job in jobs.values():
        job["category"] = categorize(job["state"])
        if job["category"] in ("completed", "attention"):
            if (job.get("inspect") or {}).get("v") != INSPECT_VERSION:
                job["inspect"] = inspect_output(job, programs)
            if job["category"] == "completed" and job["inspect"]["ok"] is False:
                job["category"] = "attention"
    for r in rows:
        st = r["State"].split()[0] if r["State"] else "UNKNOWN"
        jid = r["JobID"]
        prev = jobs.get(jid)
        job = {
            "id": jid, "name": r["JobName"], "state": st, "state_full": r["State"],
            "workdir": r["WorkDir"], "exit": r["ExitCode"], "submit": r["Submit"],
            "start": r["Start"], "end": r["End"], "elapsed": r["Elapsed"],
            "timelimit": r["Timelimit"], "submitline": r["SubmitLine"],
            "stdout": expand_path(r["StdOut"], r), "stderr": expand_path(r["StdErr"], r),
            "nodes": r["NodeList"], "reason": r["Reason"],
        }
        fill_missing(job, prev, queued.get(jid))
        job["category"] = categorize(st)
        if job["category"] in ("completed", "attention"):
            cached = prev and prev.get("state") == st and prev.get("inspect")
            if cached and cached.get("v") == INSPECT_VERSION:
                job["inspect"] = cached
            else:
                job["inspect"] = inspect_output(job, programs)
            if job["category"] == "completed" and job["inspect"]["ok"] is False:
                job["category"] = "attention"
        jobs[jid] = job
    state["last_sync"] = time.time()
    state["sync_error"] = None
    return state


def fill_missing(job, prev, queued):
    """Fill fields an older sacct can't report from squeue, earlier polls, or Slurm defaults."""
    prev = prev or {}
    if queued:
        workdir, command = queued
        if not job["workdir"] and workdir:
            job["workdir"] = workdir
        if command and command != "(null)" and not job["submitline"]:
            job["command"] = command
    for k in ("workdir", "submitline", "stdout", "stderr", "command"):
        if not job.get(k) and prev.get(k):
            job[k] = prev[k]
    if not job["submitline"] and job.get("command"):
        job["submitline"] = "sbatch " + shlex.quote(job["command"])
    if not job["stdout"] and job["workdir"]:
        default = os.path.join(job["workdir"], "slurm-%s.out" % job["id"])
        if os.path.isfile(default):
            job["stdout"] = default


def do_sync():
    with FileLock():
        state = load_state()
        try:
            sync(state)
        except Exception as e:  # keep showing stale data, surface the error
            state["sync_error"] = str(e)
        save_state(state)
        return state


# ---------------------------------------------------------------- board ----

def calc_key(job):
    return job["workdir"] + "::" + job["name"]


def sbatch_script(job):
    """Path of the sbatch script from the submit line, if it still exists."""
    try:
        argv = shlex.split(job.get("submitline") or "")
    except ValueError:
        return None
    if not argv or os.path.basename(argv[0]) != "sbatch":
        return None
    # first non-option argument; options taking a separate value use "--opt=value" in practice
    script = next((a for a in argv[1:] if not a.startswith("-")), None)
    if not script:
        return None
    if not os.path.isabs(script):
        script = os.path.join(job["workdir"], script)
    return script if os.path.isfile(script) else None


def guess_script(job):
    """A submit script named after the job, for Slurm versions without SubmitLine."""
    for ext in (".slurm", ".sbatch", ".sh", ".job"):
        for stem in stems(job):
            p = os.path.join(job["workdir"], stem + ext)
            if os.path.isfile(p):
                return p
    return None


def resubmit_command(job, programs=None):
    """argv that reruns this job from its work directory, or None if it can't be rebuilt."""
    if sbatch_script(job):
        return shlex.split(job["submitline"])
    if not job.get("submitline") and job.get("workdir"):
        guessed = guess_script(job)
        if guessed:
            return ["sbatch", os.path.basename(guessed)]
    programs = programs or load_programs()
    ins = job.get("inspect") or {}
    prog = next((p for p in programs if p["name"] == ins.get("program")), None)
    inp = ins.get("input") or find_input(job, prog, programs)
    candidates = [prog] if prog else [p for p in programs
                                      if inp and os.path.splitext(inp)[1] in p.get("inputs", [])]
    for p in candidates:
        tmpl = p.get("resubmit")
        if not tmpl or not inp:
            continue
        argv = [a.format(input=os.path.basename(inp), stem=os.path.splitext(os.path.basename(inp))[0],
                         workdir=job["workdir"]) for a in shlex.split(tmpl)]
        exe = shutil.which(argv[0])
        if exe:
            return [exe] + argv[1:]
    return None


def build_board(state):
    programs = load_programs()
    groups = {}
    for job in state["jobs"].values():
        groups.setdefault(calc_key(job), []).append(job)
    calcs = []
    for key, attempts in groups.items():
        attempts.sort(key=lambda j: job_sort_key(j["id"]), reverse=True)
        latest = attempts[0]
        meta = state["meta"].get(key, {})
        finished = latest["category"] in ("attention", "completed")
        ins = latest.get("inspect") or {}
        calcs.append({
            "key": key, "name": latest["name"], "workdir": latest["workdir"],
            "category": latest["category"], "latest": latest,
            "attempts": [{"id": a["id"], "state": a["state"], "end": a["end"]}
                         for a in attempts],
            "dismissed": meta.get("dismissed_jobid") == latest["id"],
            "note": meta.get("note", ""),
            # only finished jobs need these, and skipping the rest avoids filesystem stats
            "script": resubmit_command(latest, programs) if finished else None,
            "script_file": (sbatch_script(latest) or (guess_script(latest)
                            if not latest.get("submitline") and latest.get("workdir") else None))
                           if finished else None,
            "input": (ins.get("input") or find_input(latest, None, programs)) if finished else None,
        })
    calcs.sort(key=lambda c: job_sort_key(c["latest"]["id"]), reverse=True)
    return {"user": USER, "calcs": calcs, "last_sync": state.get("last_sync"),
            "sync_error": state.get("sync_error")}


def resubmit(state, key, extra=""):
    jobs = [j for j in state["jobs"].values() if calc_key(j) == key]
    if not jobs:
        raise ValueError("unknown calculation")
    latest = max(jobs, key=lambda j: job_sort_key(j["id"]))
    argv = resubmit_command(latest)
    if not argv:
        raise ValueError("Cannot resubmit automatically: submit script not found and no "
                         "resubmit command configured (submit line was: %r)"
                         % latest.get("submitline"))
    if extra:  # options go right after the command, e.g. sbatch --time=... script
        argv = argv[:1] + shlex.split(extra) + argv[1:]
    out = run(argv, cwd=latest["workdir"])
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or out.stdout.strip() or "submission failed")
    # sacct can lag behind sbatch; show the new job as pending right away
    m = re.search(r"Submitted (?:batch )?job (\d+)", out.stdout)
    if m and m.group(1) not in state["jobs"]:
        job = dict(latest, id=m.group(1), state="PENDING", state_full="PENDING",
                   category="pending", exit="", start="Unknown", end="Unknown",
                   elapsed="00:00:00", nodes="", reason="just submitted",
                   submit=time.strftime("%Y-%m-%dT%H:%M:%S"))
        job.pop("inspect", None)
        state["jobs"][job["id"]] = job
        save_state(state)
    return out.stdout.strip()


# ------------------------------------------------------------------ cli ----

COLORS = {"attention": "\033[31m", "running": "\033[32m", "pending": "\033[33m",
          "completed": "\033[2m"}


def print_status(show_all):
    board = build_board(do_sync())
    order = ["attention", "running", "pending", "completed"]
    titles = {"attention": "NEEDS ATTENTION", "running": "RUNNING",
              "pending": "PENDING", "completed": "COMPLETED"}
    tty = sys.stdout.isatty()
    for cat in order:
        rows = [c for c in board["calcs"] if c["category"] == cat
                and (show_all or not c["dismissed"])]
        if cat == "completed" and not show_all:
            rows = rows[:10]
        if not rows:
            continue
        col = COLORS[cat] if tty else ""
        print("%s== %s (%d) ==%s" % (col, titles[cat], len(rows), "\033[0m" if tty else ""))
        for c in rows:
            j = c["latest"]
            ins = j.get("inspect") or {}
            extra = j["state"]
            if ins.get("ok") is False:
                extra = "%s ERROR" % ins.get("program")
            elif ins.get("warning"):
                extra += " (" + ins["warning"] + ")"
            if cat == "pending" and j["reason"] not in ("", "None"):
                extra += " (" + j["reason"] + ")"
            print("  %-10s %-28s %-22s %s" % (j["id"], c["name"][:28], extra[:40], j["elapsed"]))
            print("             %s" % (ins.get("output") or j["stdout"] or c["workdir"]))
        print()
    if board["sync_error"]:
        print("sync error:", board["sync_error"])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    st = sub.add_parser("status")
    st.add_argument("--all", action="store_true", help="include dismissed and all completed")
    sub.add_parser("sync")
    js = sub.add_parser("json", help="sync (unless --no-sync) and print the board as JSON")
    js.add_argument("--no-sync", action="store_true")
    r = sub.add_parser("resubmit", help="resubmit the latest attempt of a calculation")
    r.add_argument("key")
    r.add_argument("--extra", default="",
                   help='extra options for the submit command, e.g. --extra="--time=2-00:00:00"')
    d = sub.add_parser("dismiss")
    d.add_argument("keys", nargs="+")
    d.add_argument("--undo", action="store_true")
    n = sub.add_parser("note")
    n.add_argument("key")
    n.add_argument("text")
    args = ap.parse_args()
    ensure_dirs()
    if args.cmd == "json":
        state = load_state() if args.no_sync else do_sync()
        print(json.dumps(build_board(state)))
    elif args.cmd == "resubmit":
        with FileLock():
            msg = resubmit(load_state(), args.key, args.extra)
        do_sync()
        print(msg)
    elif args.cmd in ("dismiss", "note"):
        with FileLock():
            state = load_state()
            if args.cmd == "note":
                state["meta"].setdefault(args.key, {})["note"] = args.text[:2000]
            else:
                for key in args.keys:
                    meta = state["meta"].setdefault(key, {})
                    if args.undo:
                        meta.pop("dismissed_jobid", None)
                        continue
                    jobs = [j for j in state["jobs"].values() if calc_key(j) == key]
                    if jobs:
                        meta["dismissed_jobid"] = max(jobs, key=lambda j: job_sort_key(j["id"]))["id"]
            save_state(state)
    elif args.cmd == "sync":
        state = do_sync()
        print("synced %d jobs%s" % (len(state["jobs"]),
              ("; error: " + state["sync_error"]) if state["sync_error"] else ""))
    else:
        print_status(False)


if __name__ == "__main__":
    main()
