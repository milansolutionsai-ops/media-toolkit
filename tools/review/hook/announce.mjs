// Claude Code UserPromptSubmit hook: tells Claude when the reviewer has sent review feedback.
// Reads only <root>/_review-index.json. Silent outside the workspace and on any error.
import { readFileSync } from "node:fs";
import { dirname, join, relative, resolve, isAbsolute } from "node:path";
import { fileURLToPath } from "node:url";

const STALE_HOURS = 4;
const CLI = resolve(dirname(fileURLToPath(import.meta.url)), "..", "review.py").replace(/\\/g, "/");
const STYLE_CLI = resolve(dirname(fileURLToPath(import.meta.url)), "..", "style.py").replace(/\\/g, "/");

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
    if (v.status !== "sent" && v.status !== "plan_sent") continue;
    if (v.claimed_at && now - Date.parse(v.claimed_at) < STALE_HOURS * 3600e3) continue;
    const n = v.notes_count;
    if (v.status === "plan_sent") {
      lines.push(`Edit plan back: ${v.project} / ${v.title}, ` +
        (n ? `${n} line${n === 1 ? "" : "s"} to change.` : "approved as is.") +
        ` Claim with: python "${CLI}" claim ${v.id}, then the same script with show ${v.id}.`);
      continue;
    }
    if (v.kind === "style") {
      lines.push(`Style reactions ready: ${v.project} / ${v.title}, ${v.round_label}, ${n} candidates. ` +
        `Claim with: python "${STYLE_CLI}" claim ${v.project} ${v.round}, then the same script with show and summary.`);
      continue;
    }
    lines.push(`Feedback ready: ${v.project} / ${v.title}, ${v.round_label}, ${n} note${n === 1 ? "" : "s"}. ` +
      `Claim with: python "${CLI}" claim ${v.id}, then the same script with show ${v.id}.`);
  }
  if (lines.length) process.stdout.write(lines.join("\n") + "\n");
}

try { main(); } catch { /* never block a prompt */ }
process.exitCode = 0;
