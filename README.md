<p align="center">
  <img src="https://raw.githubusercontent.com/ignaciomigliaro/slurmboard/main/media/icon.png" width="96" alt="Slurm Board icon">
</p>

<h1 align="center">Slurm Board</h1>

<p align="center">
  <b>A to-do list for your Slurm calculations, in the VSCode sidebar.</b><br>
  See what's running, what's queued, what finished and what died. Fix the input, resubmit, and look at the geometry without leaving the editor.
</p>

<p align="center">
  <a href="https://github.com/ignaciomigliaro/slurmboard/releases/latest/download/slurmboard.vsix"><img src="https://raw.githubusercontent.com/ignaciomigliaro/slurmboard/main/images/download.png" width="300" alt="Download Slurm Board (latest .vsix)"></a>
  <br><sub><a href="https://github.com/ignaciomigliaro/slurmboard/releases">All releases</a> · <a href="#install">How to install</a></sub>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/ignaciomigliaro/slurmboard/main/images/hero.png" alt="Slurm Board sidebar showing calculations grouped into Needs attention, Running, Pending and Completed, with an ORCA error notification" width="100%">
</p>

---

## Why

You submit twenty jobs, two of them die in the first minute, and you find out the next morning. Slurm Board watches `sacct` for you. It groups your jobs into one list per calculation and flags the ones that need you, including jobs Slurm calls "completed" whose program never finished cleanly.

## Features

### One entry per calculation, sorted by what needs you

Each entry is one calculation (work directory + job name). The **newest attempt sets the status**: when you resubmit a failed job, it moves out of *Needs attention* by itself, and the earlier attempts stay in its history.

| Group | What lands there |
|---|---|
| **Needs attention** | failed, timed out, out of memory, cancelled, node failure, or *completed but the program reported an error* |
| **Running** | running, with elapsed time against the time limit and the node it's on |
| **Pending** | queued, with Slurm's reason (Priority, Resources, …) |
| **Completed** | finished cleanly. A ⚠ marks warnings such as an optimization that didn't converge |

You get a **pop-up** when a job dies or finishes. The **status bar** shows running / pending / failed counts, and a **badge** on the sidebar icon counts calculations that need attention.

### Everything about a calculation, one click away

Expand a calculation to see its directory, input file, submit script, output and error files, geometry files, the error lines from the log, your notes, and earlier attempts. **Click** a calculation to copy its directory. Hover it for a summary.

<p align="center"><img src="https://raw.githubusercontent.com/ignaciomigliaro/slurmboard/main/images/detail.png" alt="An expanded calculation showing its files, error lines, note and attempt history, with a hover tooltip" width="90%"></p>

### Fix the input and resubmit

Click ✏️ **Edit Input** and fix the problem. When you save, Slurm Board asks whether to resubmit. **Resubmit with Options…** adds flags such as `--time=2-00:00:00` or `--mem-per-cpu=8G`.

<p align="center"><img src="https://raw.githubusercontent.com/ignaciomigliaro/slurmboard/main/images/resubmit.png" alt="Editing an ORCA input; after saving, a notification offers Resubmit, Resubmit with options, or Not yet" width="90%"></p>

The exact command is shown before anything is submitted:

<p align="center"><img src="https://raw.githubusercontent.com/ignaciomigliaro/slurmboard/main/images/confirm.png" alt="Confirmation dialog showing the cd and sbatch command that will be run" width="60%"></p>

### Look at the geometry

The structure button opens the calculation's final geometry, optimization trajectory, NEB path or input geometry in **[Protein Viewer](https://marketplace.visualstudio.com/items?itemName=ArianJamasb.protein-viewer)** (Mol*), or in **MatterViz** if you prefer.

- For **running ORCA jobs** it finds the live trajectory in the job's scratch directory, so you can watch an optimization or NEB as it goes.
- For jobs that **crashed before writing anything**, it shows the geometry from the input file, which helps when checking atom numbering for constraints.

<p align="center"><img src="https://raw.githubusercontent.com/ignaciomigliaro/slurmboard/main/images/geometry.png" alt="Picking a geometry file for a calculation and viewing it in Protein Viewer" width="90%"></p>

### Clear old entries in bulk

Ctrl/Cmd- or Shift-click several calculations and press ✓ Dismiss. Or use **Dismiss Several…** on a group header to tick them off from a searchable list. Dismissing only hides an entry: no files or jobs are touched, the 👁 button shows dismissed entries again, and a dismissed calculation reappears by itself if you resubmit it.

<p align="center"><img src="https://raw.githubusercontent.com/ignaciomigliaro/slurmboard/main/images/dismiss.png" alt="A checklist of completed calculations filtered by 'opt_' with three selected for dismissal" width="80%"></p>

<sub>Screenshots are illustrations made with example data.</sub>

---

## Supported programs

Any Slurm job is tracked: running, pending, failed, timed out and out of memory come from Slurm itself. For these programs, Slurm Board also reads the log to catch jobs that "completed" without finishing properly:

| Program | Finished OK when the log contains | Treated as failed if it contains | Edit Input opens |
|---|---|---|---|
| **ORCA** | `ORCA TERMINATED NORMALLY` | `error termination` | `<job>.inp` |
| **Gaussian** | `Normal termination of Gaussian` | `Error termination` | `<job>.com` / `.gjf` |
| **Q-Chem** | `Thank you very much for using Q-Chem` | | `<job>.in` |
| **Psi4** | `Psi4 exiting successfully` | | `<job>.dat` / `.in` |
| **CP2K** | `PROGRAM ENDED AT` | | `<job>.inp` |
| **xtb** | `normal termination of xtb` | | |
| **GROMACS** | `Finished mdrun on rank 0` | `Fatal error:` | `<job>.mdp` / newest `*.mdp` |
| **LAMMPS** | `Total wall time:` | `ERROR:` | `in.<job>` / `*.in` |
| **TeraChem** | `Job finished` | | `<job>.in` |

The ORCA markers have been checked against real output. The others follow each program's usual end-of-run messages: test with one finished job and adjust them if needed (see [Adding or changing a program](#adding-or-changing-a-program)).

---

## Install

**Requirements**
- VSCode connected to your cluster with **Remote-SSH**. The extension runs on the cluster side, where `sacct` and `sbatch` live.
- `python3` 3.6 or newer on the cluster. Nothing else to install.
- Optional, for viewing geometries: [Protein Viewer](https://marketplace.visualstudio.com/items?itemName=ArianJamasb.protein-viewer). You'll be offered a one-click install the first time you need it.

**Steps**
1. Download **[slurmboard.vsix](https://github.com/ignaciomigliaro/slurmboard/releases/latest/download/slurmboard.vsix)** (always the latest version), or pick a version from the [releases page](https://github.com/ignaciomigliaro/slurmboard/releases).
2. In VSCode, connected to the cluster: open the Extensions view → `⋯` menu → **Install from VSIX…** → pick the file. Install it on the cluster side (`SSH: <host>`) if asked.
   Or, from a terminal on the cluster: `code --install-extension slurmboard.vsix`
3. Run **Developer: Reload Window**. A checklist icon appears in the activity bar.

The first sync loads the last 14 days of jobs. If that brings back old failures, use **Dismiss All in This Group** to start clean.

---

## Settings

| Setting | Default | What it does |
|---|---|---|
| `slurmboard.refreshInterval` | `120` | Seconds between `sacct` polls (minimum 30). Keep it modest on shared clusters. |
| `slurmboard.notifications` | `true` | Pop-ups when a calculation dies or completes. |
| `slurmboard.completedLimit` | `50` | Maximum number of completed calculations listed. |
| `slurmboard.geometryViewer` | `protein-viewer` | `protein-viewer` (xyz, pdb, cif, mol/mol2, sdf, gro) or `matterviz` (also VASP, LAMMPS dumps, MD trajectories, cube files). |
| `slurmboard.pythonPath` | `python3` | Python used to run the bundled backend. |
| `slurmboard.programs` | `[]` | Add or override program profiles (below). |

### Adding or changing a program

```jsonc
"slurmboard.programs": [
  {
    "name": "MyCode",
    "detect":  ["MyCode version"],          // text near the top of the log that identifies the program
    "success": ["Calculation finished"],    // must appear near the end of the log
    "failure": ["FATAL"],                   // any of these near the end means failed
    "outputs": ["{stem}.log", "*.log"],     // where the log is; {stem} = job name, wildcards pick the newest
    "inputs":  [".in", "in.*"],             // ".ext" means <job>.ext; anything else is a file pattern
    "resubmit": "sbatch run_mycode.sh {input}"  // used only when the original sbatch script is gone
  }
]
```

A profile with the same `name` as a built-in one replaces just the fields you give. For example, to use your own ORCA submit wrapper:

```jsonc
"slurmboard.programs": [{ "name": "ORCA", "resubmit": "my_orca_submit {input}" }]
```

---

## How resubmit works

1. If the original `sbatch <script>` from the job's submit line still exists, Slurm Board reruns that exact command in the job's directory. Options from **Resubmit with Options…** go right after `sbatch`.
2. If the script is gone (some submit wrappers delete it), it uses the program's `resubmit` template with the input file it found. The ORCA default is `qorca {input}`. Change it to your own wrapper as shown above.
3. If neither is possible, the Resubmit button is disabled. Right-click → **Open Terminal Here** to resubmit by hand.

After a resubmit, the new job appears under **Pending** immediately, and the board checks again after about 10, 30 and 60 seconds, so a job that dies within seconds is reported right away.

---

## Command line

The same backend works without VSCode:

```bash
python3 ~/.vscode-server/extensions/migliaro.slurmboard-*/slurmboard.py status        # board in the terminal
python3 ~/.vscode-server/extensions/migliaro.slurmboard-*/slurmboard.py status --all  # include dismissed and all completed
```

---

## Good to know

- **Load on the cluster:** one `sacct` call per refresh (default every 2 minutes), covering only recent jobs. Each finished job's log is read once and the result is cached.
- **Your data stays yours:** history, notes and dismissals are kept in `~/.slurmboard/` for each user. Nothing leaves the cluster.
- **Geometries outside your workspace:** Protein Viewer can only read files inside your workspace folders. Other files (including scratch) are copied into a small staging folder that clears itself after a day.
- **Troubleshooting:** if the board says *Sync failed*, run `sacct -u $USER -S now-1day` in a terminal to check that accounting is available. If `python3` isn't found, set `slurmboard.pythonPath`.

## Building from source

```bash
git clone https://github.com/ignaciomigliaro/slurmboard
cd slurmboard
python3 build_vsix.py      # → slurmboard-<version>.vsix (no Node or npm needed)
```

The README images are regenerated with `python3 dev/make_images.py` (needs `cairosvg`, `fonttools` and the Inter font).

## License

MIT © 2026 Ignacio Migliaro
