// Build references from links the author actually supplied; never infer claim support.
export function addSources(prose, items, copyText) {
  const sources = new Map();
  const groups = { cited: [], consulted: [], listed: [] };
  const urlOf = (value) => {
    try {
      const url = new URL(value);
      if (
        !["http:", "https:"].includes(url.protocol) ||
        url.username ||
        url.password
      )
        return null;
      return url.href;
    } catch {
      return null;
    }
  };
  const register = (anchor, kind) => {
    const url = urlOf(anchor.getAttribute("href"));
    if (!url) return null;
    if (sources.has(url)) return sources.get(url);
    const item = items.find((entry) => urlOf(entry.url) === url);
    const label = anchor.textContent.trim();
    const title =
      anchor.getAttribute("title") ||
      item?.title ||
      (/^\[?\d+\]?$/.test(label) ? new URL(url).hostname : label) ||
      new URL(url).hostname;
    const source = { number: sources.size + 1, url, title, kind };
    sources.set(url, source);
    groups[kind].push(source);
    return source;
  };
  const bibliographies = [];
  for (const heading of prose.querySelectorAll(":scope > h2")) {
    const label = heading.textContent.trim().toLowerCase();
    const kind =
      label === "other sources consulted"
        ? "consulted"
        : ["sources", "references"].includes(label)
          ? "listed"
          : null;
    if (!kind) continue;
    const nodes = [heading];
    let next = heading.nextElementSibling;
    while (
      next &&
      next.tagName !== "H2" &&
      !next.classList.contains("edition-end")
    ) {
      nodes.push(next);
      next = next.nextElementSibling;
    }
    // Only fold link lists; preserve free-form coverage notes in older reports.
    if (nodes.slice(1).some((node) => !["UL", "OL"].includes(node.tagName)))
      continue;
    for (const node of nodes) {
      bibliographies.push(
        ...Array.from(node.querySelectorAll("a[href]"), (anchor) => ({
          anchor,
          kind,
        })),
      );
      node.remove();
    }
  }
  const citations = [];
  for (const anchor of prose.querySelectorAll("a[href]")) {
    if (anchor.closest("pre, code, .edition-end")) continue;
    let section = anchor;
    while (section.parentElement !== prose) section = section.parentElement;
    while (section && section.tagName !== "H2")
      section = section.previousElementSibling;
    const supporting =
      !/coverage gaps|further read|deeper read|limitations/i.test(
        section?.textContent || "",
      );
    const source = register(anchor, supporting ? "cited" : "listed");
    if (!source) continue;
    if (!supporting) continue;
    const citation = document.createElement("a");
    citation.className = "source-citation";
    citation.href = `#source-${source.number}`;
    citation.textContent = `[${source.number}]`;
    citation.setAttribute(
      "aria-label",
      `Source ${source.number}: ${source.title}`,
    );
    if (/^\[?\d+\]?$/.test(anchor.textContent.trim()))
      anchor.replaceWith(citation);
    else anchor.after(document.createTextNode(" "), citation);
    citations.push(citation);
  }
  for (const { anchor, kind } of bibliographies) register(anchor, kind);
  for (const item of items) {
    const anchor = document.createElement("a");
    anchor.setAttribute("href", item.url || "");
    anchor.textContent = item.title || "";
    register(anchor, "listed");
  }
  if (!sources.size) return;
  const details = document.createElement("details");
  details.className = "edition-sources";
  const summary = document.createElement("summary");
  summary.textContent = `Sources · ${sources.size}`;
  details.append(summary);
  const bibliography = (source) =>
    `[${source.number}] ${source.title}\n${source.url}`;
  const copyButton = (label, text) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "quiet-button";
    button.textContent = label;
    button.onclick = () => copyText(text);
    return button;
  };
  const labels = {
    cited: "Cited in this edition",
    consulted: "Other sources consulted",
    listed: "Other sources listed in this edition",
  };
  const allText = Object.entries(groups)
    .filter(([, entries]) => entries.length)
    .map(
      ([kind, entries]) =>
        `${labels[kind]}\n\n${entries.map(bibliography).join("\n\n")}`,
    )
    .join("\n\n");
  const copyAll = copyButton("Copy sources", allText);
  copyAll.onclick = (event) => {
    event.preventDefault();
    event.stopPropagation();
    copyText(allText);
  };
  summary.append(copyAll);
  for (const [kind, entries] of Object.entries(groups)) {
    if (!entries.length) continue;
    const heading = document.createElement("h3");
    heading.textContent = labels[kind];
    const list = document.createElement("ol");
    for (const source of entries) {
      const entry = document.createElement("li");
      entry.id = `source-${source.number}`;
      entry.tabIndex = -1;
      const number = document.createElement("span");
      number.className = "source-number";
      number.textContent = `[${source.number}]`;
      const body = document.createElement("div");
      const link = document.createElement("a");
      link.href = source.url;
      link.textContent = source.title;
      const domain = document.createElement("small");
      domain.textContent = new URL(source.url).hostname;
      body.append(link, domain);
      const copy = copyButton(
        `Copy source ${source.number}`,
        bibliography(source),
      );
      copy.setAttribute("aria-label", `Copy source ${source.number}`);
      copy.title = `Copy source ${source.number}`;
      copy.textContent = "";
      copy.innerHTML =
        '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true"><rect x="7" y="7" width="9" height="10" rx="1.5"/><path d="M12 7V3H3v10h4"/></svg>';
      entry.append(number, body, copy);
      list.append(entry);
    }
    if (kind !== "cited") details.append(heading);
    details.append(list);
  }
  prose.querySelector(".edition-end").before(details);
  const reveal = (hash) => {
    const entry = Array.from(details.querySelectorAll("li")).find(
      (node) => `#${node.id}` === hash,
    );
    if (!entry) return;
    details.open = true;
    entry.focus({ preventScroll: true });
    entry.scrollIntoView({ block: "center" });
  };
  for (const citation of citations)
    citation.onclick = (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
        return;
      event.preventDefault();
      history.replaceState(null, "", citation.hash);
      reveal(citation.hash);
    };
  if (/^#source-\d+$/.test(location.hash)) reveal(location.hash);
}

export async function copySources(text, toast, options = {}) {
  const success = options.success || "Sources copied";
  try {
    await navigator.clipboard.writeText(text);
    toast(success);
    return true;
  } catch {
    /* Private LAN HTTP may not expose the Clipboard API. */
  }
  const field = document.createElement("textarea");
  field.value = text;
  field.readOnly = true;
  field.className = options.className || "source-copy-fallback";
  field.setAttribute("aria-label", options.label || "Sources to copy");
  const details =
    options.container || document.querySelector(".edition-sources");
  details.querySelector("." + field.className)?.remove();
  details.append(field);
  field.focus();
  field.select();
  try {
    if (document.execCommand("copy")) {
      field.remove();
      toast(success);
      return true;
    }
  } catch {
    /* Leave the selected bibliography available for manual copying. */
  }
  toast(options.manual || "Select and copy the sources below.");
  return false;
}
