// Views: inbox (#/), video page (#/v/<project>/<slug>) with review or fix-check mode, and the round history.
import { parseFps, fmtTime, reduceKey, initialKeyState } from "./frames.js";
import { Player } from "./player.js";
import { Timeline } from "./timeline.js";
import { attachKeys } from "./keys.js";
import { PLATFORMS, overlay } from "./safezones.js";

const app = document.getElementById("app");
const keysBar = document.getElementById("keys");
let detachKeys = () => {};
let cleanupView = () => {};

const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (v !== false && v != null) el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid);
  return el;
};
const api = (p, opts) => fetch(p, opts).then(async (r) => {
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
});
const TAG_LABEL = { picture: "Picture", sound: "Sound", cut: "Cut" };
const hhmm = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const uid = () => Math.random().toString(36).slice(2, 8);

// ---------- platform safe zones (shared toggle, remembered per browser) ----------
const zoneKey = "rv-safezone";
const getZone = () => { try { return localStorage.getItem(zoneKey) || "off"; } catch { return "off"; } };
const zoneBoxes = new Set();
function videoBox(video, vw, vh) {
  const box = h("div", { class: "vbox" }, video);
  const paint = () => {
    box.querySelector(".safezones")?.remove();
    const p = getZone();
    if (p !== "off") box.append(overlay(p, vw, vh));
  };
  box.paintZones = paint;
  zoneBoxes.add(box);
  paint();
  return box;
}
function zonePicker() {
  const sel = h("select", { class: "zonepick", title: "Show where the app's buttons cover the video",
    onchange: () => { try { localStorage.setItem(zoneKey, sel.value); } catch {}
      zoneBoxes.forEach((b) => (b.isConnected ? b.paintZones() : zoneBoxes.delete(b))); } },
    h("option", { value: "off" }, "Safe zones: off"),
    Object.entries(PLATFORMS).map(([k, p]) => h("option", { value: k }, `Safe zones: ${p.name}`)));
  sel.value = getZone();
  return sel;
}

// ---------- pointer line (feedback waiting for Claude) ----------
async function refreshPointer() {
  const list = await api("/api/videos");
  const sent = list.filter((v) => (v.status === "sent" || v.status === "plan_sent") && !v.claimed_at);
  const box = document.getElementById("pointer");
  box.hidden = !sent.length;
  if (!sent.length) return;
  const v = sent[0];
  const text = (v.kind === "style"
    ? `Style reactions ready: ${v.project} / ${v.title}, ${v.round_label}, ${v.notes_count} candidates`
    : v.status === "plan_sent" ? `Edit plan back: ${v.project} / ${v.title}, ${v.notes_count} lines to change`
    : `Feedback ready: ${v.project} / ${v.title}, ${v.round_label}, ${v.notes_count} notes`) +
    (sent.length > 1 ? ` (+${sent.length - 1} more)` : "");
  document.getElementById("pointer-text").textContent = text;
  document.getElementById("pointer-copy").onclick = () => navigator.clipboard.writeText(text);
}

// ---------- inbox ----------
async function inbox() {
  keysBar.hidden = true;
  const list = await api("/api/videos");
  let showApproved = false;
  const grid = h("div", { class: "cards" });
  const draw = () => {
    grid.replaceChildren();
    const shown = list.filter((v) => showApproved || v.status !== "approved")
      .sort((a, b) => (b.updated || "").localeCompare(a.updated || ""));
    if (!shown.length) grid.append(h("div", { class: "empty" }, "Nothing waiting for review."));
    for (const v of shown) {
      const href = v.kind === "style" ? `#/s/${v.id.replace("/style-", "/")}` : `#/v/${v.id}`;
      grid.append(h("a", { class: "card", href },
        h("span", { class: "title" }, v.title),
        h("span", { class: "meta" }, `${v.project} · ${v.round_label}${v.kind === "style" ? ` · ${v.notes_count} options` : ""}`),
        h("span", { class: `status ${v.status}` }, v.status_label,
          v.status === "sent" && v.claimed_at ? ` · picked up ${hhmm(v.claimed_at)}` : "")));
    }
  };
  const toggle = h("button", { class: "ghost", onclick: () => {
    showApproved = !showApproved; toggle.classList.toggle("on", showApproved); draw();
  } }, "Show approved");
  app.replaceChildren(h("div", { class: "inbox-head" }, h("h1", {}, "To review"), toggle), grid);
  draw();
}

// ---------- edit plan ----------
const secs = (t) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, "0")}`;

function planRows(d, open, verdicts, notes, onChange) {
  return d.plan.rows.map((r) => {
    const btn = (val, label) => h("button", { class: `ghost ${val}`, disabled: !open || null,
      onclick: () => { verdicts[r.id] = val; paint(); onChange(); } }, label);
    const ok = btn("ok", "OK"), change = btn("change", "Change");
    const note = h("input", { class: "cnote", placeholder: "What should change?", disabled: !open || null,
      oninput: () => { notes[r.id] = note.value; onChange(); } });
    note.value = notes[r.id] || "";
    const paint = () => {
      ok.classList.toggle("on", verdicts[r.id] === "ok");
      change.classList.toggle("on", verdicts[r.id] === "change");
      note.hidden = verdicts[r.id] !== "change";
    };
    paint();
    return h("div", { class: "planrow" },
      r.still_url ? h("img", { class: "pstill", src: r.still_url, alt: "" }) : h("div", { class: "pstill none" }),
      h("div", { class: "pbody" },
        h("div", { class: "ptime" }, `${secs(r.start)} → ${secs(r.end)}`),
        h("div", { class: "ptext" }, r.text),
        h("div", { class: "verdict" }, ok, change), note));
  });
}

function planPage(d, head) {
  keysBar.hidden = true;
  const open = d.status === "plan_waiting";
  const verdicts = { ...d.plan.verdicts }, notes = { ...d.plan.notes };
  const overall = h("textarea", { placeholder: "Anything about the plan as a whole? (optional)", disabled: !open || null });
  overall.value = d.plan.note || "";
  const sendBtn = h("button", { class: "primary" });
  const update = () => {
    const left = d.plan.rows.filter((r) => !verdicts[r.id]).length;
    const changes = d.plan.rows.filter((r) => verdicts[r.id] === "change");
    const unsaid = changes.filter((r) => !(notes[r.id] || "").trim()).length;
    sendBtn.disabled = !open || left > 0 || unsaid > 0;
    sendBtn.textContent = !open ? "Plan sent" : left ? `OK or change ${left} more line${left > 1 ? "s" : ""}`
      : unsaid ? "Say what to change" : changes.length
        ? `Send ${changes.length} change${changes.length > 1 ? "s" : ""} to Claude` : "Approve plan";
  };
  sendBtn.onclick = async () => {
    sendBtn.disabled = true;
    try {
      await api(`/api/videos/${d.id}/plan/send`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ verdicts, notes, note: overall.value }) });
      location.hash = "#/";
    } catch (err) { sendBtn.textContent = `Couldn't send: ${err.message}`; sendBtn.disabled = false; }
  };
  app.replaceChildren(head,
    h("p", { class: "meta" }, "What happens when, before anything gets built. OK each line, or say what to change."),
    h("div", { class: "plan" }, planRows(d, open, verdicts, notes, update)),
    h("div", { class: "editor", style: "margin-top:16px" }, overall),
    h("div", { class: "sendbar", style: "margin-top:12px" }, sendBtn));
  update();
}

// ---------- round history ----------
function history(d) {
  const box = h("div", { class: "history" }, h("h2", { class: "panel-title" }, "Rounds"));
  if (d.plan) {
    box.append(h("details", {}, h("summary", {}, "Edit plan"),
      d.plan.rows.map((r) => h("div", { class: "item" }, h("b", {}, `${secs(r.start)} `), r.text,
        d.plan.verdicts[r.id] === "change" ? ` (change: ${d.plan.notes[r.id] || ""})` : ""))));
  }
  for (const r of d.rounds) {
    const items = [];
    for (const a of r.answers) {
      items.push(h("div", { class: "item" }, h("b", {}, "Claude: "), a.explanation,
        a.note ? ` (on "${a.note.text}")` : ""));
    }
    for (const [id, verdict] of Object.entries(r.verdicts)) {
      const a = r.answers.find((x) => x.note_id === id);
      items.push(h("div", { class: "item" }, h("b", {}, verdict === "fixed" ? "Fixed: " : "Not fixed: "),
        a?.note?.text || id));
    }
    for (const n of r.notes) {
      items.push(h("div", { class: "item" }, h("b", {}, `${TAG_LABEL[n.tag]} ${fmtTime(n.start, parseFps(d.fps))}: `), n.text));
    }
    if (!items.length) items.push(h("div", { class: "item" }, r.sent ? "No notes." : "Not reviewed yet."));
    box.append(h("details", { open: r === d.rounds[d.rounds.length - 1] || null }, h("summary", {}, r.label), items));
  }
  return box;
}

// ---------- marking workspace (review + the new-notes part of fix-check) ----------
function workspace(d, round, notes) {
  const fps = parseFps(d.fps);
  const total = round.frames;
  const video = h("video", { src: round.video_url, preload: "auto", playsinline: true });
  const readout = h("div", { class: "readout" });
  const tl = h("div", { class: "timeline" });
  let ks = { ...initialKeyState(), total };
  let player, timeline;

  const range = () => (ks.markIn === null ? [ks.frame, ks.frame] : [ks.markIn, ks.markOut]);
  const list = h("div", { class: "notes" });
  const text = h("textarea", { placeholder: "What's wrong here? (Enter saves, Shift+Enter new line)" });
  const tagBtns = Object.keys(TAG_LABEL).map((t) => h("button", { class: "ghost", "data-tag": t,
    onclick: () => { ks.tag = t; paint(); } }, `${TAG_LABEL[t]} (${t[0].toUpperCase()})`));
  const rangeEl = h("div", { class: "range" });

  const paint = () => {
    const [a, b] = range();
    readout.replaceChildren(h("span", {}, "Frame ", h("b", {}, String(ks.frame))),
      h("span", {}, h("b", {}, fmtTime(ks.frame, fps))), h("span", {}, `of ${fmtTime(total, fps)}`));
    rangeEl.textContent = ks.markIn === null ? `At ${fmtTime(a, fps)} (frame ${a}) · I / O to mark a range`
      : `${fmtTime(a, fps)} → ${fmtTime(b + 1, fps)} · frames ${a}-${b} (${b - a + 1})`;
    tagBtns.forEach((b) => b.classList.toggle("on", b.dataset.tag === ks.tag));
    list.replaceChildren(...notes.map((n) => h("div", { class: "note", onclick: () => player.seek(n.start) },
      h("div", { class: "row" }, h("span", { class: "tag" }, TAG_LABEL[n.tag]),
        `${fmtTime(n.start, fps)}${n.end > n.start ? " → " + fmtTime(n.end + 1, fps) : ""}`,
        h("button", { class: "del", title: "Delete note", onclick: (e) => {
          e.stopPropagation(); notes.splice(notes.indexOf(n), 1); paint(); } }, "✕")),
      h("div", { class: "text" }, n.text))));
    timeline?.set({ ranges: notes.map((n) => [n.start, n.end]), mark: ks.markIn === null ? null : range(),
      frame: ks.frame });
    onChange();
  };
  let onChange = () => {};

  const save = () => {
    const t = text.value.trim();
    if (!t) { text.focus(); return; }
    const [a, b] = range();
    notes.push({ id: uid(), start: a, end: b, tag: ks.tag, text: t });
    notes.sort((x, y) => x.start - y.start);
    text.value = ""; text.blur();
    ks = { ...ks, markIn: null, markOut: null };
    paint();
  };

  const onKey = (e) => {
    const next = reduceKey(ks, e);
    if (next === ks) return false;
    ks = next;
    switch (ks.action) {
      case "seek": player.pause(); player.seek(ks.frame); break;
      case "toggle-play": player.toggle(); break;
      case "pause": player.pause(); break;
      case "shuttle": player.shuttle(ks.shuttle); break;
      case "save": save(); return true;
      case "cancel": text.blur(); break;
      case "tag": break;
    }
    paint();
    return true;
  };

  const el = h("div", {},
    h("div", { class: `work ${d.orientation}` },
      h("div", {}, h("div", { class: "stage" }, videoBox(video, d.width, d.height)),
        h("div", { class: "under" }, readout, zonePicker())),
      h("div", { class: "panel" }, h("h2", {}, "Notes"), list,
        h("div", { class: "editor" }, h("div", { class: "tags" }, tagBtns), rangeEl, text))),
    tl);

  requestAnimationFrame(() => {
    player = new Player(video, fps, total, (f) => { ks.frame = f; paint(); });
    cleanupView();
    timeline = new Timeline(tl, { spriteUrl: round.sprite.url, spriteMeta: round.sprite.meta,
      peaksUrl: round.peaks_url, total, onSeek: (f) => { player.pause(); player.seek(f); } });
    player.seek(0);
    cleanupView = () => { timeline.destroy(); player.pause(); };
  });
  return { el, onKey, onChangeSet: (fn) => { onChange = fn; paint(); } };
}

// ---------- fix-check rows ----------
function checkRow(a, verdicts, onVerdict) {
  const media = h("div", { class: "media" });
  const fc = a.fixcheck;
  let step = 0;
  const row = h("div", { class: "check", tabindex: "0" });
  if (fc?.kind === "pairs") {
    const img = h("img", { src: fc.urls[0], alt: "Before and after" });
    const pos = h("span");
    const show = () => { img.src = fc.urls[step]; pos.textContent = `Frame ${step + 1} of ${fc.urls.length}`; };
    const go = (dlt) => { step = Math.max(0, Math.min(fc.urls.length - 1, step + dlt)); show(); };
    row.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.stopPropagation(); e.preventDefault(); go(e.key === "ArrowRight" ? 1 : -1);
      }
    });
    media.append(h("div", { class: "labels" }, h("span", {}, "Before"), h("span", {}, "After")), img,
      h("div", { class: "stepper" }, h("button", { class: "ghost", onclick: () => go(-1) }, "‹"), pos,
        h("button", { class: "ghost", onclick: () => go(1) }, "›"), "Click here, then ← → to step"));
    show();
  } else if (fc) {
    media.append(h("div", { class: "labels" }, fc.kind === "audio"
      ? [h("span", {}, "Before, then after")] : [h("span", {}, "Before"), h("span", {}, "After")]),
      h("video", { src: fc.urls[0], controls: true, loop: true, preload: "metadata" }));
  } else {
    media.append(h("div", { class: "empty" }, "No preview for this note."));
  }
  const btn = (val, label) => h("button", { class: `ghost ${val}`, onclick: () => { onVerdict(a.note_id, val); paint(); } }, label);
  const fixed = btn("fixed", "Fixed"), notFixed = btn("not-fixed", "Not fixed");
  const paint = () => {
    fixed.classList.toggle("on", verdicts[a.note_id] === "fixed");
    notFixed.classList.toggle("on", verdicts[a.note_id] === "not-fixed");
  };
  paint();
  row.append(media, h("div", { class: "side" },
    a.note ? h("div", {}, h("span", { class: "tag" }, TAG_LABEL[a.note.tag]), " ", a.note.text) : null,
    h("div", { class: "explain" }, h("b", {}, "Claude: "), a.explanation),
    h("div", { class: "verdict" }, fixed, notFixed)));
  return row;
}

// ---------- video page ----------
async function videoPage(id) {
  const d = await api(`/api/videos/${id}`);
  const round = d.rounds[d.rounds.length - 1];
  const head = h("div", { class: "vhead" }, h("h1", {}, d.title),
    h("span", { class: `status ${d.status}` }, d.status_label,
      (d.status === "sent" || d.status === "plan_sent") && d.claimed_at ? ` · picked up ${hhmm(d.claimed_at)}` : ""),
    h("span", { class: "meta" }, `${d.project} · ${round ? round.label : d.round_label}`));
  detachKeys();
  if (!round) return planPage(d, head);

  if (d.status !== "waiting" && d.status !== "fixes_ready") {
    keysBar.hidden = true;
    const v = h("video", { src: round.video_url, controls: true, preload: "metadata" });
    app.replaceChildren(head, h("div", { class: `work ${d.orientation}` }, h("div", { class: "stage" }, v)), history(d));
    return;
  }

  keysBar.hidden = false;
  const notes = [];
  const verdicts = {};
  const ws = workspace(d, round, notes);
  const checking = d.status === "fixes_ready";
  const sendBtn = h("button", { class: "primary" });
  const update = () => {
    const pending = checking ? round.answers.filter((a) => !verdicts[a.note_id]).length : 0;
    sendBtn.disabled = pending > 0;
    sendBtn.textContent = pending ? `Check ${pending} more fix${pending > 1 ? "es" : ""} first`
      : notes.length || Object.values(verdicts).includes("not-fixed")
        ? `Send ${notes.length ? notes.length + " note" + (notes.length > 1 ? "s" : "") : "verdicts"} to Claude`
        : "Approve video";
  };
  sendBtn.onclick = async () => {
    sendBtn.disabled = true;
    try {
      await api(`/api/videos/${id}/send`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ round: round.n, notes, verdicts }) });
      location.hash = "#/";
    } catch (err) {
      sendBtn.textContent = `Couldn't send: ${err.message}`;
      sendBtn.disabled = false;
    }
  };
  ws.onChangeSet(update);
  detachKeys = attachKeys(ws.onKey);

  const parts = [head];
  if (checking) {
    parts.push(h("h2", { class: "panel-title" }, "Check the fixes"),
      h("div", { class: "checks" }, round.answers.map((a) => checkRow(a, verdicts, (nid, val) => {
        verdicts[nid] = val; update();
      }))),
      h("h2", { class: "panel-title", style: "margin-top:22px" }, "Anything new on this version?"));
  }
  parts.push(ws.el, h("div", { class: "sendbar", style: "margin-top:14px" }, sendBtn), history(d));
  app.replaceChildren(...parts);
  update();
}

// ---------- style round page ----------
async function stylePage(project, n) {
  keysBar.hidden = true;
  const d = await api(`/api/style/${project}/${n}`);
  const open = d.status === "waiting";
  const reactions = {};
  for (const [cid, r] of Object.entries(d.reactions || {})) reactions[cid] = { ...r };
  const sendBtn = h("button", { class: "primary" });
  const roundNote = h("textarea", { placeholder: "Anything about the round as a whole? (optional)", disabled: !open || null });
  roundNote.value = d.note || "";
  const update = () => {
    const left = d.candidates.filter((c) => !reactions[c.id]?.verdict).length;
    sendBtn.disabled = !open || left > 0;
    sendBtn.textContent = !open ? "Reactions sent" : left ? `React to ${left} more first` : "Send reactions to Claude";
  };
  const cards = d.candidates.map((c) => {
    const video = h("video", { src: c.video_url, controls: true, loop: true, preload: "metadata", playsinline: true });
    const btns = ["keep", "maybe", "drop"].map((v) => h("button", { class: `ghost react ${v}`, disabled: !open || null,
      onclick: () => { reactions[c.id] = { ...(reactions[c.id] || {}), verdict: v }; paint(); update(); } },
      v[0].toUpperCase() + v.slice(1)));
    const note = h("input", { class: "cnote", placeholder: "Close? Say what to change (optional)", disabled: !open || null,
      oninput: () => { reactions[c.id] = { ...(reactions[c.id] || {}), note: note.value }; } });
    note.value = reactions[c.id]?.note || "";
    const paint = () => btns.forEach((b) => b.classList.toggle("on", b.classList.contains(reactions[c.id]?.verdict)));
    paint();
    return h("div", { class: `cand ${c.width > c.height ? "wide" : ""}` },
      h("div", { class: "cmedia" }, videoBox(video, c.width, c.height)),
      h("div", { class: "cbody" },
        h("div", { class: "row" }, h("span", { class: "tag" }, c.dimension),
          c.origin === "claude" ? h("span", { class: "badge" }, "Claude's idea") : null),
        h("div", { class: "title" }, c.label),
        c.explain ? h("div", { class: "meta" }, c.explain) : null,
        h("div", { class: "verdict" }, btns), note));
  });
  sendBtn.onclick = async () => {
    sendBtn.disabled = true;
    try {
      await api(`/api/style/${project}/${n}/send`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reactions, note: roundNote.value }) });
      location.hash = "#/";
    } catch (err) { sendBtn.textContent = `Couldn't send: ${err.message}`; sendBtn.disabled = false; }
  };
  app.replaceChildren(
    h("div", { class: "vhead" }, h("h1", {}, d.title), h("span", { class: `status ${d.status}` },
      open ? "Waiting for you" : "Reactions sent"), h("span", { class: "meta" }, `${d.project} · Style round ${d.n}`),
      h("span", { class: "spacer" }), zonePicker()),
    h("p", { class: "meta" }, "Each option changes one thing. Keep it, maybe, or drop it. A few words help when it's close."),
    h("div", { class: "cands" }, cards),
    h("div", { class: "editor", style: "margin-top:16px" }, roundNote),
    h("div", { class: "sendbar", style: "margin-top:12px" }, sendBtn));
  update();
}

// ---------- router ----------
async function route() {
  detachKeys(); detachKeys = () => {};
  cleanupView(); cleanupView = () => {};
  const m = location.hash.match(/^#\/v\/([^/]+\/[^/]+)$/);
  const s = location.hash.match(/^#\/s\/([^/]+)\/(\d+)$/);
  try {
    await (m ? videoPage(m[1]) : s ? stylePage(s[1], s[2]) : inbox());
  } catch (err) {
    app.replaceChildren(h("div", { class: "empty" }, `Something went wrong: ${err.message}`));
  }
  refreshPointer().catch(() => {});
}
window.addEventListener("hashchange", route);
route();
setInterval(() => refreshPointer().catch(() => {}), 15000);
