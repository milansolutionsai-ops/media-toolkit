// Global keyboard routing. While typing a note only Enter (save) and Escape (cancel) reach the reducer;
// Shift+Enter makes a new line.
export function attachKeys(onKey) {
  const handler = (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const typing = /^(TEXTAREA|INPUT)$/.test(document.activeElement?.tagName || "");
    if (typing && !(e.key === "Enter" && !e.shiftKey) && e.key !== "Escape") return;
    if (onKey(e) !== false) e.preventDefault();
  };
  window.addEventListener("keydown", handler);
  return () => window.removeEventListener("keydown", handler);
}
