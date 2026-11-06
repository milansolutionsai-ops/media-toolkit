// Claude Code UserPromptSubmit hook: tells Claude when Milan has sent review feedback.
// Reads only <root>/_review-index.json. Silent outside the workspace and on any error.
import { readFileSync } from "node:fs";
import { dirname, join, relative, resolve, isAbsolute } from "node:path";
import { fileURLToPath } from "node:url";

const STALE_HOURS = 4;

function main() {
  const root = resolve(process.env.REVIEW_ROOT || join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", ".."));
  let input = {};
  try { input = JSON.parse(readFileSync(0, "utf8") || "{}"); } catch { /* no stdin */ }
  const cwd = resolve(input.cwd || process.cwd());
  const rel = relative(root, cwd);
  if (rel.startsWith("..") || isAbsolute(rel)) return;

  const index = JSON.parse(readFileSync(join(root, "_review-index.json"), "utf8"));
  const now = Date.now();
  const lines = [];
  for (const v of index.videos || []) {
    if (v.status !== "sent") continue;
    if (v.claimed_at && now - Date.parse(v.claimed_at) < STALE_HOURS * 3600e3) continue;
    const n = v.notes_count;
    lines.push(`Feedback ready: ${v.project} / ${v.title}, ${v.round_label}, ${n} note${n === 1 ? "" : "s"}. ` +
      `Claim with: python media-toolkit/tools/review/review.py claim ${v.id}, then review.py show ${v.id}.`);
  }
  if (lines.length) process.stdout.write(lines.join("\n") + "\n");
}

try { main(); } catch { /* never block a prompt */ }
process.exitCode = 0;
