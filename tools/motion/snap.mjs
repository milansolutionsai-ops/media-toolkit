#!/usr/bin/env node
// Safe, non-destructive wrapper around `hyperframes snapshot` (Milan, 2026-10-20).
//
// Why it exists:
//  1. `hyperframes snapshot` sends every still to Gemini (metered API) whenever GEMINI_API_KEY is set.
//     This wrapper always passes `--describe false` AND strips GEMINI_API_KEY / GOOGLE_API_KEY from the
//     child env, so a snapshot can never bill the key. The key itself is left untouched in Windows.
//  2. `snapshot -o <dir>` wipes <dir> and renumbers from 00. This wrapper snapshots into a fresh
//     timestamped run folder, then copies each still into the target folder, replacing only the
//     still with the same frame number. Redoing one beat never deletes the others.
//
// Usage (from anywhere):
//   node snap.mjs <projectDir> --at 3,12,21 [--out boards/stills] [--first 0]
//   node snap.mjs <projectDir> --at 21 --first 2            # redo frame 02 only
//   node snap.mjs <projectDir> --at 3,12 --describe "Is any text cut off or too small?"
//
//   --out       target folder, relative to the project (default boards/stills)
//   --first     frame number the first --at time gets (default 0). Stills are named frame-NN-at-<s>s.png.
//   --describe  optional question about the stills, answered by the FREE Gemini CLI (agy, Milan's
//               subscription), never the API key. Writes the answer to <run>/describe.md.
import { spawnSync } from "node:child_process";
import { mkdirSync, readdirSync, copyFileSync, unlinkSync, writeFileSync, existsSync, mkdtempSync } from "node:fs";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";

const args = process.argv.slice(2);
const opt = (name, dflt) => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : dflt; };
const project = resolve(args.find((a, i) => !a.startsWith("--") && !(i > 0 && args[i - 1].startsWith("--"))) || ".");
const at = opt("at");
if (!at) { console.error("snap: --at <t1,t2,...> is required"); process.exit(2); }
const out = resolve(project, opt("out", "boards/stills"));
const first = parseInt(opt("first", "0"), 10);
const question = opt("describe");

const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const run = join(project, ".hyperframes", "snap-runs", stamp);
mkdirSync(run, { recursive: true });
mkdirSync(out, { recursive: true });

const env = { ...process.env };
delete env.GEMINI_API_KEY; delete env.GOOGLE_API_KEY;
// shell is needed for npx on Windows, so quote every argument (paths here contain spaces)
const q = (a) => `"${String(a).replace(/"/g, '\\"')}"`;
const cmd = "npx " + ["hyperframes", "snapshot", "--at", at, "--no-end", "--describe", "false", "-o", run, project].map(q).join(" ");
const r = spawnSync(cmd, { env, stdio: "inherit", shell: true });
if (r.status !== 0) { console.error(`snap: snapshot failed (exit ${r.status})`); process.exit(r.status || 1); }

const shots = readdirSync(run).filter((f) => /^frame-\d+-at-.*\.png$/.test(f)).sort();
for (const f of shots) {
  const n = parseInt(f.match(/^frame-(\d+)/)[1], 10) + first;
  const nn = String(n).padStart(2, "0");
  for (const old of readdirSync(out)) if (old.startsWith(`frame-${nn}-at-`)) unlinkSync(join(out, old));
  const name = f.replace(/^frame-\d+/, `frame-${nn}`);
  copyFileSync(join(run, f), join(out, name));
  console.log(`snap: ${name}`);
}
console.log(`snap: run folder (contact sheets) ${run}`);

if (question) {
  const agy = join(process.env.LOCALAPPDATA || "", "agy", "bin", "agy.exe");
  if (!existsSync(agy)) { console.error(`snap: agy not found at ${agy}; skipping --describe`); process.exit(0); }
  const files = shots.map((f) => `'${join(run, f)}'`).join(", ");
  const prompt = `Do NOT run shell commands or create files. Use view_file on each of these images: ${files}. ` +
    `They are stills from a motion-graphics video, in order. Answer per still, numbered: ${question}`;
  const cwd = mkdtempSync(join(tmpdir(), "snap-agy-"));
  const a = spawnSync(agy, ["-p", prompt, "--add-dir", run, "--output-format", "text"],
    { env, cwd, encoding: "utf8", timeout: 600000 });
  const answer = (a.stdout || "").trim() || `(no answer; exit ${a.status}) ${(a.stderr || "").slice(-400)}`;
  writeFileSync(join(run, "describe.md"), answer + "\n");
  console.log(`snap: describe (free Gemini CLI) -> ${join(run, "describe.md")}\n${answer}`);
}
