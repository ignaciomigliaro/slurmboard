// Slurm Board: sidebar tracker for Slurm calculations.
// All Slurm/state logic lives in the bundled slurmboard.py; this file is just the UI.
const vscode = require('vscode');
const path = require('path');
const fs = require('fs');
const { execFile } = require('child_process');

const GROUPS = [
  { id: 'attention', label: 'Needs attention' },
  { id: 'running', label: 'Running' },
  { id: 'pending', label: 'Pending' },
  { id: 'completed', label: 'Completed' },
];

let board = null;          // last JSON from the backend
let showDismissed = false;
let busy = false;
let prev = null;           // key -> "category:jobid" from the previous poll

function cfg(name) { return vscode.workspace.getConfiguration('slurmboard').get(name); }

function backend(context, args) {
  const script = path.join(context.extensionPath, 'slurmboard.py');
  return new Promise((resolve, reject) => {
    const env = Object.assign({}, process.env, { SLURMBOARD_PROGRAMS: JSON.stringify(cfg('programs') || []) });
    execFile(cfg('pythonPath') || 'python3', [script, ...args],
      { timeout: 120000, maxBuffer: 64 * 1024 * 1024, env },
      (err, stdout, stderr) => {
        if (err) reject(new Error((stderr || err.message).trim().split('\n').pop()));
        else resolve(stdout);
      });
  });
}

function statusLabel(c) {
  const j = c.latest, ins = j.inspect || {};
  if (ins.ok === false && j.state === 'COMPLETED') return `${ins.program} error`;
  if (j.state === 'OUT_OF_MEMORY') return 'out of memory';
  if (j.state === 'TIMEOUT') return 'timed out';
  return j.state.toLowerCase().replace(/_/g, ' ');
}

function timing(c) {
  const j = c.latest;
  if (c.category === 'running') return `running ${j.elapsed} / ${j.timelimit} on ${j.nodes}`;
  if (c.category === 'pending') return `queued since ${j.submit.replace('T', ' ')}` +
    (j.reason && j.reason !== 'None' ? ` (${j.reason})` : '');
  return `ended ${j.end.replace('T', ' ')} · ran ${j.elapsed} · exit ${j.exit}`;
}

function iconFor(c) {
  const warn = c.latest.inspect && c.latest.inspect.warning;
  switch (c.category) {
    case 'attention': return new vscode.ThemeIcon('error', new vscode.ThemeColor('testing.iconFailed'));
    case 'running': return new vscode.ThemeIcon('sync~spin', new vscode.ThemeColor('charts.green'));
    case 'pending': return new vscode.ThemeIcon('clock', new vscode.ThemeColor('charts.yellow'));
    default: return warn
      ? new vscode.ThemeIcon('warning', new vscode.ThemeColor('charts.yellow'))
      : new vscode.ThemeIcon('pass', new vscode.ThemeColor('testing.iconPassed'));
  }
}

function visibleCalcs(groupId) {
  if (!board) return [];
  let rows = board.calcs.filter(c => c.category === groupId && (showDismissed || !c.dismissed));
  if (groupId === 'completed') rows = rows.slice(0, cfg('completedLimit') || 50);
  return rows;
}

class Provider {
  constructor() {
    this._em = new vscode.EventEmitter();
    this.onDidChangeTreeData = this._em.event;
  }
  refresh() { this._em.fire(); }

  getChildren(el) {
    if (!board) return [];
    if (!el) {
      const out = [];
      if (board.sync_error) out.push({ kind: 'error', text: board.sync_error });
      for (const g of GROUPS) out.push({ kind: 'group', group: g });
      return out;
    }
    if (el.kind === 'group') return visibleCalcs(el.group.id).map(c => ({ kind: 'calc', calc: c }));
    if (el.kind === 'calc') {
      const c = el.calc, j = c.latest, ins = j.inspect || {}, kids = [];
      kids.push({ kind: 'dir', calc: c });
      if (c.input) kids.push({ kind: 'file', calc: c, file: c.input, label: 'input' });
      if (c.script_file) kids.push({ kind: 'file', calc: c, file: c.script_file, label: 'submit script' });
      if (ins.output && ins.output !== j.stdout) kids.push({ kind: 'file', calc: c, file: ins.output, label: ins.program + ' output' });
      for (const g of geometriesFor(c).slice(0, 6)) kids.push({ kind: 'geo', calc: c, file: g.file, label: g.label });
      if (c.input && /\.inp$/.test(c.input)) kids.push({ kind: 'geo-input', calc: c });
      if (j.stdout) kids.push({ kind: 'file', calc: c, file: j.stdout });
      if (j.stderr && j.stderr !== j.stdout) kids.push({ kind: 'file', calc: c, file: j.stderr });
      if (c.note) kids.push({ kind: 'text', icon: 'note', text: c.note });
      if (ins.warning) kids.push({ kind: 'text', icon: 'warning', text: ins.warning });
      if (ins.snippet && c.category === 'attention')
        for (const line of ins.snippet.split('\n')) kids.push({ kind: 'text', icon: 'debug-stackframe-dot', text: line });
      if (c.attempts.length > 1)
        kids.push({ kind: 'text', icon: 'history',
          text: 'attempts: ' + c.attempts.map(a => `${a.id} ${a.state.toLowerCase()}`).join(', ') });
      return kids;
    }
    return [];
  }

  getTreeItem(el) {
    const N = vscode.TreeItemCollapsibleState;
    if (el.kind === 'error') {
      const it = new vscode.TreeItem('Sync failed: ' + el.text, N.None);
      it.iconPath = new vscode.ThemeIcon('warning');
      return it;
    }
    if (el.kind === 'group') {
      const all = board.calcs.filter(c => c.category === el.group.id && (showDismissed || !c.dismissed));
      const it = new vscode.TreeItem(`${el.group.label}`,
        el.group.id === 'completed' ? N.Collapsed : (all.length ? N.Expanded : N.Collapsed));
      it.id = 'group:' + el.group.id;
      it.description = String(all.length);
      it.contextValue = 'group-' + el.group.id;
      return it;
    }
    if (el.kind === 'calc') {
      const c = el.calc, j = c.latest;
      const it = new vscode.TreeItem(c.name, N.Collapsed);
      it.id = 'calc:' + c.key;
      it.description = `${statusLabel(c)} · #${j.id}${c.attempts.length > 1 ? ` · try ${c.attempts.length}` : ''}`;
      it.iconPath = iconFor(c);
      const md = new vscode.MarkdownString();
      md.appendMarkdown(`**${c.name}** — ${statusLabel(c)} (#${j.id})` +
        (j.inspect && j.inspect.program ? ` · ${j.inspect.program}` : '') + '\n\n');
      md.appendCodeblock(c.workdir, 'text');
      md.appendMarkdown(timing(c) + '\n\n');
      if (c.note) md.appendMarkdown(`📝 ${c.note}\n\n`);
      if (j.inspect && j.inspect.snippet && c.category === 'attention') md.appendCodeblock(j.inspect.snippet, 'text');
      md.appendMarkdown('\n_Click to copy the directory._');
      it.tooltip = md;
      const flags = ['calc'];
      if ((c.category === 'attention' || c.category === 'completed') && c.script) flags.push('resubmittable');
      if (c.input) flags.push('hasinput');
      if (c.category === 'attention' || c.category === 'completed') flags.push(c.dismissed ? 'dismissed' : 'dismissable');
      it.contextValue = flags.join('-');
      it.command = { command: 'slurmboard.clickCalc', title: 'Copy directory', arguments: [el] };
      return it;
    }
    if (el.kind === 'dir') {
      const it = new vscode.TreeItem(el.calc.workdir, N.None);
      it.iconPath = new vscode.ThemeIcon('folder');
      it.tooltip = 'Click to copy: ' + el.calc.workdir;
      it.command = { command: 'slurmboard.copyDir', title: 'Copy', arguments: [el] };
      return it;
    }
    if (el.kind === 'geo') {
      const it = new vscode.TreeItem(path.basename(el.file), N.None);
      it.description = el.label;
      it.iconPath = new vscode.ThemeIcon('symbol-structure');
      it.tooltip = el.file + '\nClick to view the structure';
      it.command = { command: 'slurmboard.openGeometryFile', title: 'View', arguments: [el.file] };
      return it;
    }
    if (el.kind === 'geo-input') {
      const it = new vscode.TreeItem('input geometry', N.None);
      it.iconPath = new vscode.ThemeIcon('symbol-structure');
      it.tooltip = 'Geometry from ' + el.calc.input + '\nClick to view the structure';
      it.command = { command: 'slurmboard.viewInputGeometry', title: 'View', arguments: [el] };
      return it;
    }
    if (el.kind === 'file') {
      const it = new vscode.TreeItem(path.basename(el.file), N.None);
      it.resourceUri = vscode.Uri.file(el.file);
      if (el.label) it.description = el.label;
      it.iconPath = vscode.ThemeIcon.File;
      it.tooltip = el.file;
      it.command = { command: 'slurmboard.openFile', title: 'Open', arguments: [el.file] };
      return it;
    }
    const it = new vscode.TreeItem(el.text, N.None);
    it.iconPath = new vscode.ThemeIcon(el.icon);
    it.tooltip = el.text;
    return it;
  }
}

// ------------------------------------------------------------ geometry ----
// Structures open in Protein Viewer (Mol*) by default, or MatterViz (setting slurmboard.geometryViewer).
const VIEWERS = {
  'protein-viewer': { id: 'ArianJamasb.protein-viewer', name: 'Protein Viewer',
    ext: /\.(xyz|pdb|ent|pdbqt|cif|mcif|mmcif|mol|mol2|sdf|gro)$/i, names: null },
  'matterviz': { id: 'janosh.matterviz', name: 'MatterViz',
    ext: /\.(xyz|extxyz|pdb|cif|mcif|mmcif|mol|mol2|sdf|poscar|vasp|lammpstrj|dump|data|lmp|xtc|trr|traj|dcd|cube|h5|hdf5)(\.gz)?$/i,
    names: /^(CONTCAR|POSCAR|OUTCAR|XDATCAR)/i },
};
function viewer() { return VIEWERS[cfg('geometryViewer')] || VIEWERS['protein-viewer']; }
let storageDir = null;   // set in activate(); holds geometries extracted from inputs

function geoKind(base, stem) {
  if (base === stem + '.xyz') return 'final geometry';
  if (/_MEP_trj\.xyz$/.test(base)) return 'NEB path';
  if (/NEB-(CI|TS).*\.xyz$/.test(base) || /_TS.*converged.*\.xyz$/.test(base)) return 'NEB transition state';
  if (/_MEP_ALL_trj\.xyz$/.test(base)) return 'NEB all images';
  if (/_initial_path_trj\.xyz$/.test(base)) return 'NEB initial path';
  const im = /_im(\d+)\.xyz$/.exec(base);
  if (im) return 'NEB image ' + im[1];
  if (/_trj\.xyz$/.test(base)) return 'optimization trajectory';
  if (/\.cube(\.gz)?$/.test(base)) return 'volumetric data';
  if (/\.(xtc|trr|dcd|lammpstrj|dump|traj)$/.test(base)) return 'MD trajectory';
  return path.extname(base).slice(1) + ' file';
}

// allowAll: list every structure when none is named after the calculation (job-private
// scratch dirs, MD runs with names like md.xtc). Shared ORCA folders must not do this.
function listGeometries(dir, stem, allowAll) {
  let names;
  try { names = fs.readdirSync(dir); } catch (e) { return []; }
  // other calculations in the same folder, so "P_TMAOH" doesn't claim "P_TMAOH_cation.xyz"
  const stems = new Set([stem]);
  for (const n of names) {
    const m = /^(.+)\.(inp|com|gjf|in|mdp)$/.exec(n);
    if (m) stems.add(m[1]);
  }
  const owner = base => {
    let best = null;
    for (const st of stems)
      if ((base.startsWith(st + '.') || base.startsWith(st + '_')) && (!best || st.length > best.length)) best = st;
    return best;
  };
  const v = viewer();
  const files = names.filter(n => v.ext.test(n) || (v.names && v.names.test(n))).map(n => {
    const f = path.join(dir, n);
    let mtime = 0;
    try { mtime = fs.statSync(f).mtimeMs; } catch (e) { /* vanished */ }
    return { file: f, base: n, mtime };
  });
  const own = files.filter(g => owner(g.base) === stem);
  return (own.length || !allowAll ? own : files).sort((a, b) => b.mtime - a.mtime).slice(0, 15);
}

// running ORCA jobs (qorca) work in a scratch dir named in the .out header
function scratchDir(job) {
  if (!job.stdout) return null;
  try {
    const fd = fs.openSync(job.stdout, 'r'), buf = Buffer.alloc(16384);
    const n = fs.readSync(fd, buf, 0, buf.length, 0); fs.closeSync(fd);
    const m = /Working dir\.:\s*(\S+)/.exec(buf.toString('utf8', 0, n));
    return m && m[1] !== job.workdir && fs.existsSync(m[1]) ? m[1] : null;
  } catch (e) { return null; }
}

// ORCA "* xyz charge mult ... *" block or "* xyzfile charge mult file.xyz"
function inputGeometry(c) {
  if (!c.input || !/\.inp$/.test(c.input)) return null;
  let text;
  try { text = fs.readFileSync(c.input, 'utf8'); } catch (e) { return null; }
  const ref = /^\s*\*\s*xyzfile\s+\S+\s+\S+\s+(\S+)/im.exec(text);
  if (ref) {
    const f = path.resolve(path.dirname(c.input), ref[1]);
    return fs.existsSync(f) ? { file: f, label: 'input geometry' } : null;
  }
  const m = /^\s*\*\s*xyz\s+\S+\s+\S+\s*\n([\s\S]*?)^\s*\*/im.exec(text);
  if (!m) return null;
  const atoms = m[1].split('\n').map(l => l.trim()).filter(l => /^[A-Za-z]{1,3}\S*\s+[-\d.]+\s+[-\d.]+\s+[-\d.]+/.test(l))
    .map(l => l.split(/\s+/).slice(0, 4).join('  ').replace(/^([A-Za-z]+)\S*/, '$1'));
  if (!atoms.length || !storageDir) return null;
  fs.mkdirSync(storageDir, { recursive: true });
  const f = path.join(storageDir, path.basename(c.input, '.inp') + '_input.xyz');
  fs.writeFileSync(f, `${atoms.length}\n${c.name} input geometry\n${atoms.join('\n')}\n`);
  return { file: f, label: 'input geometry' };
}

function geometriesFor(c) {
  const stem = c.input ? path.basename(c.input).replace(/\.[^.]+$/, '') : c.name;
  const out = [];
  const scratch = c.category === 'running' ? scratchDir(c.latest) : null;
  if (scratch) for (const g of listGeometries(scratch, stem, true))
    out.push({ file: g.file, label: geoKind(g.base, stem) + ' (live, scratch)', mtime: g.mtime });
  const md = ['GROMACS', 'LAMMPS'].includes((c.latest.inspect || {}).program);
  for (const g of listGeometries(c.workdir, stem, md))
    out.push({ file: g.file, label: geoKind(g.base, stem), mtime: g.mtime });
  // final geometry first, then trajectories; the rest newest first
  const rank = l => /final/.test(l) ? 0 : /transition/.test(l) ? 1 : /NEB path/.test(l) ? 2
    : /trajectory|path|all images/.test(l) ? 3 : 4;
  out.sort((a, b) => rank(a.label) - rank(b.label) || b.mtime - a.mtime);
  return out;
}

// Protein Viewer's webview can only read files inside a workspace folder (or its own
// install dir), so anything else (job folders outside the workspace, scratch, extracted
// input geometries) is copied into a staging folder inside its install dir first.
function stageForProteinViewer(file, ext) {
  if (vscode.workspace.getWorkspaceFolder(vscode.Uri.file(file))) return file;
  const root = path.join(ext.extensionPath, '.slurmboard-view');
  const dir = path.join(root, require('crypto').createHash('md5').update(file).digest('hex').slice(0, 10));
  fs.mkdirSync(dir, { recursive: true });
  const dest = path.join(dir, path.basename(file));
  fs.copyFileSync(file, dest);   // re-copied on every open, so live scratch files are current
  try {   // keep the staging folder small: drop copies older than a day
    for (const d of fs.readdirSync(root)) {
      const p = path.join(root, d);
      if (Date.now() - fs.statSync(p).mtimeMs > 86400e3) fs.rmSync(p, { recursive: true, force: true });
    }
  } catch (e) { /* best effort */ }
  return dest;
}

async function openGeometry(file) {
  const v = viewer();
  const ext = vscode.extensions.getExtension(v.id);
  if (!ext) {
    const a = await vscode.window.showWarningMessage(
      `Viewing geometries needs the ${v.name} extension (setting: slurmboard.geometryViewer).`,
      `Install ${v.name}`, 'Open as text');
    if (a && a.startsWith('Install')) vscode.commands.executeCommand('workbench.extensions.installExtension', v.id);
    if (a === 'Open as text') openFile(file);
    return;
  }
  if (v === VIEWERS['matterviz'])
    return vscode.commands.executeCommand('vscode.openWith', vscode.Uri.file(file), 'matterviz.viewer');
  try {
    const uri = vscode.Uri.file(stageForProteinViewer(file, ext));
    await vscode.commands.executeCommand('protein-viewer.activateFromFiles', uri, [uri]);
  } catch (e) {
    vscode.window.showErrorMessage(`Could not open ${path.basename(file)} in Protein Viewer: ${e.message}`);
  }
}

async function viewGeometry(c) {
  const geos = geometriesFor(c);
  const inp = inputGeometry(c);
  if (inp) geos.push(inp);
  if (!geos.length) {
    vscode.window.showInformationMessage(`No geometry files found for ${c.name} in ${c.workdir}.`);
    return;
  }
  if (geos.length === 1) return openGeometry(geos[0].file);
  const pick = await vscode.window.showQuickPick(geos.map(g => ({
    label: path.basename(g.file), description: g.label,
    detail: g.mtime ? 'modified ' + new Date(g.mtime).toLocaleString() : undefined, file: g.file })),
    { placeHolder: `Geometry for ${c.name} (opens in ${viewer().name})`, matchOnDescription: true });
  if (pick) openGeometry(pick.file);
}

async function openFile(file) {
  if (!file || !fs.existsSync(file)) {
    vscode.window.showWarningMessage('File not found: ' + file);
    return;
  }
  const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(file));
  const ed = await vscode.window.showTextDocument(doc, { preview: true });
  const end = new vscode.Position(doc.lineCount - 1, 0);   // jump to the end, where errors are
  ed.selection = new vscode.Selection(end, end);
  ed.revealRange(new vscode.Range(end, end), vscode.TextEditorRevealType.InCenter);
}

function calcOf(arg) { return arg && arg.calc; }

function activate(context) {
  storageDir = context.globalStorageUri.fsPath;
  const provider = new Provider();
  const view = vscode.window.createTreeView('slurmboard.jobs', { treeDataProvider: provider, showCollapseAll: true, canSelectMany: true });
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  status.command = 'slurmboard.jobs.focus';
  status.text = '$(server-process) Slurm';
  status.show();
  context.subscriptions.push(view, status);
  vscode.commands.executeCommand('setContext', 'slurmboard.showDismissed', false);

  function updateChrome() {
    const n = k => board.calcs.filter(c => c.category === k && !c.dismissed).length;
    const bad = n('attention'), run = n('running'), pend = n('pending');
    status.text = `$(sync${run ? '~spin' : ''}) ${run}  $(clock) ${pend}  $(error) ${bad}`;
    status.tooltip = `Slurm: ${run} running, ${pend} pending, ${bad} need attention`;
    status.backgroundColor = bad ? new vscode.ThemeColor('statusBarItem.warningBackground') : undefined;
    view.badge = bad ? { value: bad, tooltip: `${bad} calculation(s) need attention` } : undefined;
    const t = board.last_sync ? new Date(board.last_sync * 1000).toLocaleTimeString() : 'never';
    view.message = board.sync_error ? `Sync failed: ${board.sync_error}` : undefined;
    view.description = `synced ${t}`;
  }

  function notifyTransitions() {
    const now = {};
    for (const c of board.calcs) now[c.key] = c.category + ':' + c.latest.id;
    if (prev && Object.keys(prev).length && cfg('notifications')) {
      const changed = board.calcs.filter(c => prev[c.key] !== now[c.key] &&
        (c.category === 'attention' || c.category === 'completed'));
      if (changed.length > 4) {
        const bad = changed.filter(c => c.category === 'attention').length;
        vscode.window.showWarningMessage(`Slurm: ${changed.length - bad} completed, ${bad} need attention`, 'Show')
          .then(a => a && vscode.commands.executeCommand('slurmboard.jobs.focus'));
        prev = now;
        return;
      }
      for (const c of changed) {
        if (c.category === 'attention') {
          const acts = ['Open .out'];
          if (c.input) acts.push('Edit input');
          if (c.script) acts.push('Resubmit');
          vscode.window.showErrorMessage(`Slurm: ${c.name} ${statusLabel(c)} (#${c.latest.id})`, ...acts)
            .then(a => handleAction(a, c));
        } else if (c.category === 'completed') {
          vscode.window.showInformationMessage(`Slurm: ${c.name} completed (#${c.latest.id})`, 'Open .out', 'Copy directory')
            .then(a => handleAction(a, c));
        }
      }
    }
    prev = now;
  }

  async function handleAction(a, c) {
    if (a === 'Open .out') openFile((c.latest.inspect && c.latest.inspect.output) || c.latest.stdout);
    else if (a === 'Edit input') editInput(c);
    else if (a === 'Copy directory') copyDir(c);
    else if (a === 'Resubmit') resubmit(c);
    else if (a === 'Open terminal here') openTerminal(c);
  }

  let queued = null;   // a reload requested while another was running: run it afterwards
  async function reload(sync = true) {
    if (busy) { queued = queued || sync; return; }
    busy = true;
    try {
      board = JSON.parse(await backend(context, sync ? ['json'] : ['json', '--no-sync']));
      notifyTransitions();
      updateChrome();
      provider.refresh();
    } catch (e) {
      view.message = 'Slurm Board error: ' + e.message;
    } finally {
      busy = false;
      if (queued !== null) { const s = queued; queued = null; reload(s); }
    }
  }

  async function copyDir(c) {
    await vscode.env.clipboard.writeText(c.workdir);
    vscode.window.setStatusBarMessage('$(copy) Copied ' + c.workdir, 4000);
  }

  function openTerminal(c) {
    vscode.window.createTerminal({ name: c.name, cwd: c.workdir }).show();
  }

  async function resubmit(c, extra = '') {
    if (!c.script) {
      vscode.window.showWarningMessage(`Can't resubmit ${c.name}: submit script not found (was: ${c.latest.submitline}).`);
      return;
    }
    const ok = await vscode.window.showWarningMessage(
      `Resubmit ${c.name}?`, { modal: true, detail: `cd ${c.workdir}\n` +
        [c.script[0], extra, ...c.script.slice(1)].filter(Boolean).join(' ') }, 'Resubmit');
    if (ok !== 'Resubmit') return;
    try {
      const msg = await backend(context, ['resubmit', c.key, `--extra=${extra}`]);
      vscode.window.showInformationMessage(`${c.name}: ${msg.trim()}`);
      await reload(false);
      // jobs that die within seconds would otherwise go unseen until the next poll
      for (const sec of [10, 30, 60]) setTimeout(() => reload(true), sec * 1000);
    } catch (e) {
      vscode.window.showErrorMessage('Resubmit failed: ' + e.message);
    }
  }

  const editing = new Map();   // input path -> calc key, for the save-then-resubmit prompt
  async function editInput(c) {
    if (!c.input) { vscode.window.showWarningMessage(`No input file found for ${c.name}.`); return; }
    editing.set(c.input, c.key);
    await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(vscode.Uri.file(c.input)));
  }
  context.subscriptions.push(vscode.workspace.onDidSaveTextDocument(async doc => {
    const key = editing.get(doc.uri.fsPath);
    const c = key && board && board.calcs.find(x => x.key === key);
    if (!c || !c.script || !['attention', 'completed'].includes(c.category)) return;
    const a = await vscode.window.showInformationMessage(`Saved input for ${c.name}. Resubmit now?`,
      'Resubmit', 'Resubmit with options…', 'Not yet');
    if (a === 'Resubmit') { editing.delete(doc.uri.fsPath); resubmit(c); }
    else if (a === 'Resubmit with options…') { editing.delete(doc.uri.fsPath); vscode.commands.executeCommand('slurmboard.resubmitWith', { calc: c }); }
  }));

  async function runAndReload(args) {
    try { await backend(context, args); await reload(false); }
    catch (e) { vscode.window.showErrorMessage(e.message); }
  }

  const reg = (id, fn) => context.subscriptions.push(vscode.commands.registerCommand(id, fn));
  reg('slurmboard.refresh', () => reload(true));
  reg('slurmboard.showDismissed', () => { showDismissed = true; vscode.commands.executeCommand('setContext', 'slurmboard.showDismissed', true); provider.refresh(); });
  reg('slurmboard.hideDismissed', () => { showDismissed = false; vscode.commands.executeCommand('setContext', 'slurmboard.showDismissed', false); provider.refresh(); });
  reg('slurmboard.clickCalc', async el => {
    const c = calcOf(el);
    await copyDir(c);
    const acts = ['Open .out', 'Open terminal here'];
    if (c.input) acts.push('Edit input');
    if (c.script && (c.category === 'attention' || c.category === 'completed')) acts.push('Resubmit');
    vscode.window.showInformationMessage(`Copied: ${c.workdir}`, ...acts).then(a => handleAction(a, c));
  });
  reg('slurmboard.copyDir', el => copyDir(calcOf(el)));
  reg('slurmboard.openFile', f => openFile(f));
  reg('slurmboard.openOut', el => { const j = calcOf(el).latest; openFile((j.inspect && j.inspect.output) || j.stdout); });
  reg('slurmboard.editInput', el => editInput(calcOf(el)));
  reg('slurmboard.viewGeometry', el => viewGeometry(calcOf(el)));
  reg('slurmboard.openGeometryFile', f => openGeometry(f));
  reg('slurmboard.viewInputGeometry', el => {
    const g = inputGeometry(calcOf(el));
    if (g) openGeometry(g.file);
    else vscode.window.showInformationMessage('No geometry found in ' + calcOf(el).input);
  });
  reg('slurmboard.resubmitWith', async el => {
    const c = calcOf(el);
    const extra = await vscode.window.showInputBox({
      prompt: `Extra options for "${path.basename(c.script[0])}" (placed before the script/input)`,
      placeHolder: c.script[0].endsWith('sbatch') ? '--time=2-00:00:00 --mem-per-cpu=4G' : 'options understood by ' + path.basename(c.script[0]),
      value: context.globalState.get('lastExtra', '') });
    if (extra === undefined) return;
    context.globalState.update('lastExtra', extra);
    resubmit(c, extra);
  });
  reg('slurmboard.openErr', el => openFile(calcOf(el).latest.stderr));
  reg('slurmboard.openTerminal', el => openTerminal(calcOf(el)));
  reg('slurmboard.openFolder', el => vscode.commands.executeCommand('vscode.openFolder',
    vscode.Uri.file(calcOf(el).workdir), { forceNewWindow: true }));
  reg('slurmboard.resubmit', el => resubmit(calcOf(el)));
  // with multi-select, VSCode passes (clicked item, all selected items)
  const selectedKeys = (el, sel) => {
    const items = sel && sel.length && sel.includes(el) ? sel : [el];
    return items.filter(x => x && x.kind === 'calc').map(x => x.calc.key);
  };
  reg('slurmboard.dismiss', (el, sel) => runAndReload(['dismiss', ...selectedKeys(el, sel)]));
  reg('slurmboard.restore', (el, sel) => runAndReload(['dismiss', '--undo', ...selectedKeys(el, sel)]));
  reg('slurmboard.dismissSome', async el => {
    const calcs = visibleCalcs(el.group.id).filter(c => !c.dismissed);
    if (!calcs.length) return;
    const picks = await vscode.window.showQuickPick(calcs.map(c => ({
      label: c.name, description: `${statusLabel(c)} · #${c.latest.id} · ${c.latest.end.replace('T', ' ')}`,
      detail: c.workdir, key: c.key })),
      { canPickMany: true, matchOnDescription: true, matchOnDetail: true,
        placeHolder: `Tick the ${el.group.label.toLowerCase()} calculations to dismiss (type to filter by name or folder)` });
    if (picks && picks.length) runAndReload(['dismiss', ...picks.map(p => p.key)]);
  });
  reg('slurmboard.dismissGroup', async el => {
    const keys = visibleCalcs(el.group.id).filter(c => !c.dismissed).map(c => c.key);
    if (!keys.length) return;
    const ok = await vscode.window.showWarningMessage(
      `Dismiss all ${keys.length} calculations in "${el.group.label}"?`, { modal: true,
        detail: 'They come back automatically if you resubmit them. Use "Show Dismissed" to see them again.' }, 'Dismiss all');
    if (ok === 'Dismiss all') runAndReload(['dismiss', ...keys]);
  });
  reg('slurmboard.note', async el => {
    const c = calcOf(el);
    const text = await vscode.window.showInputBox({ prompt: `Note for ${c.name}`, value: c.note,
      placeHolder: 'e.g. increase MaxIter, tighten constraint on N–O…' });
    if (text !== undefined) runAndReload(['note', c.key, text]);
  });

  let timer = null;
  function schedule() {
    if (timer) clearInterval(timer);
    timer = setInterval(() => reload(true), Math.max(30, cfg('refreshInterval') || 120) * 1000);
  }
  context.subscriptions.push({ dispose: () => timer && clearInterval(timer) });
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(e => {
    if (e.affectsConfiguration('slurmboard')) { schedule(); provider.refresh(); }
  }));
  reload(false).then(() => reload(true));
  schedule();
}

function deactivate() {}

module.exports = { activate, deactivate };
