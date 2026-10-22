import { marked } from "marked";
import DOMPurify from "dompurify";
import { addSources, copySources } from "./sources.js";

const app = document.querySelector("#app");
const arrow =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';
const gear =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="currentColor"/><circle cx="15" cy="17" r="3" fill="currentColor"/></svg>';
const escape = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const formatDate = (
  s,
  options = { day: "numeric", month: "long", year: "numeric" },
) => new Date(s + "T12:00:00").toLocaleDateString("en-GB", options);
let editions = [],
  currentStatus = {},
  generationPoll,
  headingObserver,
  pageSequence = 0;

async function api(path, body) {
  const r = await fetch(
    "/api/" + path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const data = await r.json();
  if (!r.ok) {
    const e = new Error(data.error || "Something went wrong. Please retry.");
    e.status = r.status;
    throw e;
  }
  return data;
}
function toast(message) {
  const el = document.querySelector("#toast");
  el.textContent = message;
  el.classList.add("visible");
  clearTimeout(el.timeout);
  el.timeout = setTimeout(() => el.classList.remove("visible"), 4500);
}
function header(active = "journal") {
  return `<header class="site-header"><div class="header-inner"><a class="wordmark" href="/" aria-label="QuietLight home">QuietLight</a><nav aria-label="Main navigation"><a href="/" ${active === "journal" ? 'aria-current="page"' : ""}>Topics</a><a href="/settings" ${active === "settings" ? 'aria-current="page"' : ""}>${gear}<span>Settings</span></a><button type="button" class="theme-toggle" aria-label="Change color theme">◐</button></nav></div></header>`;
}
function footer() {
  return '<footer class="site-footer"><span>QuietLight</span><span>A quieter way to stay curious.</span><a href="#top">Back to top ↑</a></footer>';
}
function installMediaZoom() {
  const media = [...document.querySelectorAll(".prose img, .prose .diagram")];
  if (!media.length) return;
  const lightbox = document.createElement("dialog");
  lightbox.className = "media-lightbox";
  lightbox.setAttribute("aria-label", "Expanded media viewer");
  lightbox.innerHTML =
    '<div class="media-lightbox-toolbar"><span>Expanded view</span><div><button type="button" aria-label="Zoom out">−</button><button type="button" aria-label="Reset zoom">100%</button><button type="button" aria-label="Zoom in">+</button><button type="button" aria-label="Close expanded view" autofocus>×</button></div></div><div class="media-lightbox-content" tabindex="0" aria-label="Image or diagram; scroll to explore"></div>';
  app.append(lightbox);
  const content = lightbox.querySelector(".media-lightbox-content");
  let item,
    placeholder,
    opener,
    originalStyle,
    baseWidth,
    zoom = 1;
  const resize = () => {
    item.style.width = `${baseWidth * zoom}px`;
    lightbox.querySelector('[aria-label="Reset zoom"]').textContent =
      `${Math.round(zoom * 100)}%`;
    lightbox.querySelector('[aria-label="Zoom out"]').disabled = zoom <= 0.5;
    lightbox.querySelector('[aria-label="Zoom in"]').disabled = zoom >= 4;
  };
  lightbox.querySelector('[aria-label="Close expanded view"]').onclick = () =>
    lightbox.close();
  lightbox.querySelector('[aria-label="Zoom in"]').onclick = () => {
    zoom = Math.min(4, zoom + 0.25);
    resize();
  };
  lightbox.querySelector('[aria-label="Zoom out"]').onclick = () => {
    zoom = Math.max(0.5, zoom - 0.25);
    resize();
  };
  lightbox.querySelector('[aria-label="Reset zoom"]').onclick = () => {
    zoom = 1;
    resize();
  };
  lightbox.addEventListener("close", () => {
    if (!item) return;
    if (originalStyle === null) item.removeAttribute("style");
    else item.setAttribute("style", originalStyle);
    placeholder.replaceWith(item);
    item = null;
    opener.focus({ preventScroll: true });
  });
  lightbox.onclick = (event) => {
    const bounds = lightbox.getBoundingClientRect();
    if (
      event.target === lightbox &&
      (event.clientX < bounds.left ||
        event.clientX > bounds.right ||
        event.clientY < bounds.top ||
        event.clientY > bounds.bottom)
    )
      lightbox.close();
  };
  media.forEach((element, index) => {
    let target = element;
    if (element.matches("img")) {
      target = document.createElement("span");
      target.className = "media-image";
      element.replaceWith(target);
      target.append(element);
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = "media-zoom-button";
    button.setAttribute(
      "aria-label",
      `Maximize ${element.matches("img") ? "image" : "diagram"} ${index + 1}`,
    );
    button.title = "Maximize";
    button.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M9 4H4v5m11-5h5v5M4 15v5h5m11-5v5h-5"/></svg>';
    button.onclick = (event) => {
      event.preventDefault();
      event.stopPropagation();
      item = element.matches("img") ? element : element.querySelector("svg");
      if (!item) return;
      opener = button;
      originalStyle = item.getAttribute("style");
      placeholder = document.createComment("Expanded media position");
      item.replaceWith(placeholder);
      content.replaceChildren(item);
      lightbox.showModal();
      const available = Math.max(240, content.clientWidth - 48);
      baseWidth = item.matches("svg")
        ? Math.max(available, item.viewBox.baseVal.width)
        : Math.min(available, item.naturalWidth || available);
      zoom = 1;
      resize();
      content.scrollTo(0, 0);
    };
    target.classList.add("media-zoom-target");
    target.append(button);
  });
}
function setPage(content, active) {
  app.innerHTML = header(active) + content + footer();
  document.dispatchEvent(new Event("quietlight:page"));
  window.scrollTo(0, 0);
}
const weekdays = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];
function scheduleLabel(s = currentStatus.schedule, following = true) {
  if (!following || !s?.enabled) return "This topic is paused";
  const cadence =
    s.cadence === "weekly"
      ? `Every ${weekdays[s.weekday ?? 1]}`
      : s.cadence === "weekdays"
        ? "Weekdays"
        : "Daily";
  return `${cadence} at ${escape(s.time)} · London`;
}
function countLabel(n) {
  return `${n} ${n === 1 ? "story" : "stories"}`;
}
function metadata(report) {
  return `${report.minutes} min read <span aria-hidden="true">·</span> ${countLabel(report.items.length)}`;
}
function summary(text, length = 270) {
  return escape(
    text.length > length
      ? text.slice(0, length).replace(/\s+\S*$/, "") + "…"
      : text,
  );
}

const topicQuery = (id) => "?topic=" + encodeURIComponent(id);
const topicPath = (id) => "/topics/" + encodeURIComponent(id);
let readingTopic = "default";
const editionPath = (date) => `${topicPath(readingTopic)}/edition/${date}`;

const readEditionKey = "quietlight.read-editions.v1";
const legacyReadEditionKey = "fieldnotes.read-editions.v1";
let readEditions = new Map();
try {
  const current = localStorage.getItem(readEditionKey);
  const saved = JSON.parse(
    current ?? localStorage.getItem(legacyReadEditionKey) ?? "{}",
  );
  if (saved && typeof saved === "object" && !Array.isArray(saved)) {
    readEditions = new Map(
      Object.entries(saved).filter(([, id]) => typeof id === "string"),
    );
    if (current === null) {
      try {
        localStorage.setItem(
          readEditionKey,
          JSON.stringify(Object.fromEntries(readEditions)),
        );
      } catch {
        /* Reading still works if storage is read-only. */
      }
    }
  }
} catch {
  // Reading still works when browser storage is unavailable.
}
function markEditionRead(topicId, report) {
  if (!report.id) return;
  readEditions.set(topicId, report.id);
  try {
    localStorage.setItem(
      readEditionKey,
      JSON.stringify(Object.fromEntries(readEditions)),
    );
  } catch {}
}
function cadenceName(topic) {
  if (!topic.enabled || !topic.schedule?.enabled) return "Paused";
  return topic.schedule.cadence === "weekly"
    ? "Weekly"
    : topic.schedule.cadence === "weekdays"
      ? "Weekdays"
      : "Daily";
}
const todayLine = () =>
  new Date().toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
function editionCount(count) {
  return count
    ? count + (count === 1 ? " edition" : " editions")
    : "No editions yet";
}
// Each topic is a broadsheet section: its latest edition leads, earlier ones follow as one-liners.
function topicSection(entry) {
  const { topic, latest, reports, count, unavailable, unread } = entry;
  const [title, ...subtitle] = topic.name.split(" · ");
  const kicker = subtitle.join(" · ") || "Research topic";
  const href = topicPath(topic.id);
  const lead = unavailable
    ? `<p class="topic-card-description">The archive is temporarily unavailable.</p><p class="topic-card-meta">Retry archive</p>`
    : latest
      ? `<p class="topic-card-kicker">${unread ? "New edition" : "Latest"} · <time datetime="${latest.date}">${formatDate(latest.date, { day: "numeric", month: "short" })}</time></p><h3>${escape(latest.title)}</h3><p class="topic-card-description">${summary(latest.summary, 220)}</p><p class="topic-card-meta">${metadata(latest)}</p>`
      : `<p class="topic-card-description">Your first briefing will appear here.</p>`;
  return `<section class="topic-section">
    <div class="topic-section-head"><h2><a href="${href}">${unread ? '<span class="new-dot" title="Not yet read on this browser"></span>' : ""}${escape(title)}</a></h2><small>${escape(kicker)}</small><span class="topic-section-cadence" title="${scheduleLabel(topic.schedule, topic.enabled)}">${cadenceName(topic)} · ${unavailable ? "Archive unavailable" : editionCount(count)}</span></div>
    <a class="topic-card" href="${latest && !unavailable ? `${href}/edition/${latest.date}` : href}" aria-label="${latest && !unavailable ? `Read ${escape(latest.title)}` : `Open ${escape(topic.name)} topic`}">${lead}</a>
    ${reports
      .slice(1, 5)
      .map(
        (r) =>
          `<a class="topic-prev" href="${href}/edition/${r.date}"><time datetime="${r.date}">${formatDate(r.date, { day: "numeric", month: "short" })}</time><span>${escape(r.title)}</span><span class="topic-prev-minutes">${r.minutes} min</span></a>`,
      )
      .join("")}
    ${count ? `<a class="topic-see-all" href="${href}">All ${editionCount(count)} ${arrow}</a>` : ""}
  </section>`;
}
async function topicsHome(seq) {
  const catalog = await api("topics");
  const collections = await Promise.allSettled(
    catalog.map((t) => api("editions" + topicQuery(t.id))),
  );
  if (seq !== pageSequence) return;
  const entries = catalog.map((topic, i) => {
    const unavailable = collections[i].status === "rejected";
    const reports = unavailable ? [] : collections[i].value;
    const latest = reports[0];
    return {
      topic,
      latest,
      reports,
      count: reports.length,
      unavailable,
      unread: !!latest && readEditions.get(topic.id) !== latest.id,
    };
  });
  const filters = [
    { id: "all", label: "All", matches: () => true },
    { id: "new", label: "New editions", matches: (e) => e.unread },
    {
      id: "weekly",
      label: "Weekly",
      matches: (e) => e.topic.schedule?.cadence === "weekly",
    },
  ];
  const params = new URLSearchParams(location.search);
  let selectedFilter =
    filters.find((f) => f.id === params.get("filter")) || filters[0];
  const fresh = entries.filter((e) => e.unread).length;
  document.title = "QuietLight — Your research topics";
  setPage(`<main id="main" class="home topic-library" tabindex="-1">
    <div class="masthead"><h1><b>${todayLine()}</b><span aria-hidden="true">·</span><span id="topic-result-count"></span><span aria-hidden="true">·</span><span>${fresh} new ${fresh === 1 ? "edition" : "editions"}</span></h1>
    <div class="masthead-tools"><label class="topic-search"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5"/><path d="m13 13 4 4"/></svg><span class="sr-only">Search topics</span><input id="topic-search" type="search" placeholder="Find a topic…" value="${escape(params.get("q") || "")}" autocomplete="off"></label>
    <div class="topic-filters" role="group" aria-label="Filter topics">${filters.map((f) => `<button type="button" data-topic-filter="${f.id}" aria-pressed="${f === selectedFilter}"${f.id === "new" ? ' title="Editions not yet read on this browser"' : ""}>${f.label}<span>${entries.filter(f.matches).length}</span></button>`).join("")}</div>
    <a href="/settings?add=1" class="topic-add">+ Add topic</a></div></div>
    <p class="sr-only" id="topic-search-status" role="status" aria-live="polite"></p>
    <div class="topic-grid"></div>
    <div class="topic-no-results" hidden><h2>No topics found.</h2><p>Try a different search or filter.</p><button class="text-link" id="clear-topic-search" type="button">Show all topics ${arrow}</button></div>
  </main>`);
  const input = document.querySelector("#topic-search");
  function render() {
    const query = input.value.trim().toLocaleLowerCase();
    const results = entries.filter(
      (e) =>
        selectedFilter.matches(e) &&
        e.topic.name.toLocaleLowerCase().includes(query),
    );
    document.querySelector(".topic-grid").innerHTML = results
      .map(topicSection)
      .join("");
    document.querySelector("#topic-result-count").textContent =
      `${results.length} ${results.length === 1 ? "topic" : "topics"}`;
    document.querySelector("#topic-search-status").textContent =
      `${results.length} of ${entries.length} topics`;
    document.querySelector(".topic-no-results").hidden = results.length > 0;
    document
      .querySelectorAll("[data-topic-filter]")
      .forEach((button) =>
        button.setAttribute(
          "aria-pressed",
          String(button.dataset.topicFilter === selectedFilter.id),
        ),
      );
    const queryParams = new URLSearchParams();
    if (input.value) queryParams.set("q", input.value);
    if (selectedFilter.id !== "all")
      queryParams.set("filter", selectedFilter.id);
    history.replaceState(
      {},
      "",
      "/" + (queryParams.size ? "?" + queryParams : ""),
    );
  }
  input.addEventListener("input", render);
  document.querySelectorAll("[data-topic-filter]").forEach((button) => {
    button.onclick = () => {
      selectedFilter = filters.find((f) => f.id === button.dataset.topicFilter);
      render();
    };
  });
  document.querySelector("#clear-topic-search").onclick = () => {
    input.value = "";
    selectedFilter = filters[0];
    render();
    input.focus();
  };
  render();
}
async function home(seq, topicId = "default") {
  readingTopic = topicId;
  const values = await Promise.all([
    api("editions" + topicQuery(topicId)),
    api("status" + topicQuery(topicId)),
    api("topics"),
  ]);
  if (seq !== pageSequence) return;
  [editions, currentStatus] = values;
  const topic = values[2].find((t) => t.id === topicId);
  const [title, ...subtitle] = topic.name.split(" · ");
  const latest = editions[0];
  document.title = topic.name + " — QuietLight";
  // Broadsheet topic page: a sticky dateline column beside the run of editions.
  setPage(`<main id="main" class="home topic-page" tabindex="-1">
    <div class="topic-masthead"><a class="back-link" href="/">← All topics</a><span>${todayLine()}</span></div>
    <div class="topic-layout">
      <aside class="topic-aside"><p class="eyebrow">${escape(subtitle.join(" · ") || "Research topic")}</p><h1>${escape(title)}</h1>
        <dl><div><dt>Cadence</dt><dd>${cadenceName(topic)}</dd></div><div><dt>Next</dt><dd class="schedule-label"><span class="status-dot ${currentStatus.online ? "online" : ""}"></span>${scheduleLabel(topic.schedule, topic.enabled)}</dd></div><div><dt>Editions</dt><dd>${editions.length}</dd></div></dl>
        ${editions.length > 1 ? `<label class="search-label"><span class="sr-only">Search editions</span><input id="search" type="search" placeholder="Find an edition…"></label>` : ""}
        <a href="/settings${topicQuery(topicId)}" class="text-link">Edit this topic ${arrow}</a></aside>
      <div class="editions">
        <section id="research-progress" class="research-progress" hidden aria-label="Research activity"></section>
        ${latest ? `<a href="${editionPath(latest.date)}" class="featured-edition"><p class="edition-dateline">${readEditions.get(topicId) !== latest.id ? "<b>New</b>" : ""}<time datetime="${latest.date}">${formatDate(latest.date, { weekday: "long", day: "numeric", month: "long" })}</time></p><h2>${escape(latest.title)}</h2><p>${summary(latest.summary)}</p><span class="reading-meta">${metadata(latest)}</span></a>` : `<section class="empty-state"><span class="empty-symbol">↗</span><h2>Your next idea starts here.</h2><p>Tell the journal what you’re curious about.<br>Your first briefing will find its home on this page.</p><a class="button primary" href="/settings${topicQuery(topicId)}">Shape your briefing ${arrow}</a></section>`}
        <div id="archive-list" aria-label="Previous editions">${editions.length > 1 ? archiveRows(editions.slice(1)) : ""}</div>
      </div>
    </div>
  </main>`);
  let wasRunning = false;
  let lastProgress = "";
  function showProgress(st) {
    const research = st.research || {};
    const running = research.active || research.queued;
    const panel = document.querySelector("#research-progress");
    panel.hidden = !running && !wasRunning;
    const empty = document.querySelector(".empty-state");
    if (empty) empty.hidden = running;
    const events = research.events || [];
    const labels = {
      starting: "Preparing",
      searching: "Searching",
      reading: "Reading",
      reviewed: "Read",
      unavailable: "Couldn’t read",
      writing: "Writing",
    };
    const html = `<p class="eyebrow">RESEARCH IN PROGRESS</p><h2>${research.queued ? "Your briefing is queued." : running ? "Following the sources." : st.last_error ? "Research needs attention." : !st.online ? "Research updates are offline." : "Research has finished."}</h2><p role="status">${running ? "You can leave this page. Your edition will appear here when it’s ready." : escape(st.last_error || "Checking for your latest edition…")}</p>${
      events.length
        ? `<ol class="research-events">${events
            .slice(-8)
            .map((event) => {
              let url;
              try {
                const parsed = new URL(event.url);
                if (
                  ["http:", "https:"].includes(parsed.protocol) &&
                  !parsed.username &&
                  !parsed.password
                )
                  url = parsed.href;
              } catch {}
              return `<li><span>${escape(labels[event.stage] || "Researching")}</span><div>${url ? `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">${escape(event.message)} ↗</a><small>${escape(new URL(url).hostname)}</small>` : escape(event.message)}</div></li>`;
            })
            .join("")}</ol>`
        : running
          ? "<p>Waiting for the first research update…</p>"
          : ""
    }`;
    if (html !== lastProgress) panel.innerHTML = html;
    lastProgress = html;
    wasRunning ||= running;
  }
  showProgress(currentStatus);
  let polling = false;
  generationPoll = setInterval(async () => {
    if (polling) return;
    polling = true;
    try {
      const st = await api("status" + topicQuery(topicId));
      if (seq !== pageSequence) return;
      showProgress(st);
      const reports = await api("editions" + topicQuery(topicId));
      if (seq !== pageSequence) return;
      if (reports[0]?.id !== latest?.id) {
        clearInterval(generationPoll);
        await home(seq, topicId);
      }
    } catch {
      if (seq === pageSequence) {
        const panel = document.querySelector("#research-progress");
        panel.hidden = false;
        panel.textContent =
          "Live updates are temporarily unavailable. Retrying…";
        lastProgress = "";
      }
    } finally {
      polling = false;
    }
  }, 5000);
  document.querySelector("#search")?.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    document.querySelector("#archive-list").innerHTML = archiveRows(
      editions
        .slice(1)
        .filter((r) => (r.title + r.summary).toLowerCase().includes(q)),
    );
  });
}
function archiveRows(rows) {
  return rows.length
    ? rows
        .map(
          (r) =>
            `<a class="archive-row" href="${editionPath(r.date)}"><p class="edition-dateline"><time datetime="${r.date}">${formatDate(r.date, { weekday: "long", day: "numeric", month: "long" })}</time></p><h3>${escape(r.title)}</h3><p>${summary(r.summary, 150)}</p><span class="reading-meta">${r.minutes} min read</span></a>`,
        )
        .join("")
    : '<p class="empty-search">No editions match that search.</p>';
}

async function article(date, seq, topicId = "default") {
  const report = await api("editions/" + date + topicQuery(topicId));
  if (seq !== pageSequence) return;
  document.title = report.title + " — QuietLight";
  const md = report.markdown.replace(/^# [^\n]+\n+/, "");
  const fragment = DOMPurify.sanitize(marked.parse(md), {
    RETURN_DOM_FRAGMENT: true,
    FORBID_TAGS: ["iframe", "style", "form", "input", "script"],
    FORBID_ATTR: ["style", "onload"],
  });
  // Keep images local or embedded, preserving the journal's no-external-load policy.
  fragment.querySelectorAll("img").forEach((image) => {
    const source = image.getAttribute("src") || "";
    let url;
    try {
      url = new URL(source, location.href);
    } catch {
      image.replaceWith(document.createTextNode(image.alt));
      return;
    }
    const embedded = /^data:image\/(png|jpeg|gif|webp);base64,/i.test(source);
    if (
      !embedded &&
      (url.origin !== location.origin || url.pathname.startsWith("/api/"))
    ) {
      image.replaceWith(document.createTextNode(image.alt));
      return;
    }
    image.removeAttribute("srcset");
    image.removeAttribute("sizes");
    image.loading = "lazy";
    image.decoding = "async";
    image.referrerPolicy = "no-referrer";
  });
  const container = document.createElement("div");
  container.append(fragment);
  const html = container.innerHTML;
  setPage(
    `<div class="reading-progress" aria-hidden="true"><span></span></div><main id="main" class="article-page" tabindex="-1"><a class="back-link" href="/">← All editions</a><header class="article-header"><p class="eyebrow"><time datetime="${date}">${formatDate(date).toUpperCase()}</time><span class="eyebrow-divider">/</span> RESEARCH BRIEFING</p><h1>${escape(report.title)}</h1><div class="article-meta"><span>${metadata(report)}</span><button id="copy-link" class="quiet-button">Copy link ↗</button></div></header><div class="article-layout"><aside class="contents"><p class="eyebrow">IN THIS EDITION</p><nav id="contents-nav" aria-label="Table of contents"></nav><div class="margin-note"><span>Read. Reflect. Repeat.</span><p>Follow the sources.<br>Question the claims.<br>Keep the useful parts.</p></div></aside><article class="prose">${html}<div class="edition-end"><span class="end-mark">✳</span><h2>A good place to pause.</h2><p>You’re up to date with this edition.<br>Take the ideas that move your work forward.</p><a href="/">Back to the journal ${arrow}</a></div></article></div></main>`,
  );
  document.querySelector(".back-link").href = topicPath(topicId);
  document.querySelector(".edition-end a").href = topicPath(topicId);
  markEditionRead(topicId, report);
  addSources(document.querySelector(".prose"), report.items || [], (text) =>
    copySources(text, toast),
  );
  const headings = [
    ...document.querySelectorAll(".prose > h2:not(.edition-end h2)"),
  ];
  headings.forEach((h, i) => {
    h.id = "section-" + i;
    h.textContent = h.textContent.replace(/^\d+\.\s*/, "");
  });
  document.querySelector("#contents-nav").innerHTML = headings
    .map(
      (h, i) =>
        `<a href="#section-${i}"><span>${(i + 1).toString().padStart(2, "0")}</span>${escape(h.textContent)}</a>`,
    )
    .join("");
  document.querySelectorAll(".prose a").forEach((a) => {
    if (/^https?:\/\//.test(a.getAttribute("href") || "")) {
      a.target = "_blank";
      a.rel = "noopener noreferrer";
    }
  });
  document.querySelector("#copy-link").onclick = async () => {
    const button = document.querySelector("#copy-link");
    const copied = await copySources(location.href, toast, {
      container: document.querySelector(".article-meta"),
      className: "link-copy-fallback",
      label: "Edition link to copy",
      success: "Link copied",
      manual: "Select and copy the link below.",
    });
    button.textContent = copied ? "Link copied ✓" : "Select link below";
  };
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries)
        if (entry.isIntersecting) {
          document
            .querySelectorAll("#contents-nav a")
            .forEach((a) =>
              a.classList.toggle("selected", a.hash === "#" + entry.target.id),
            );
        }
    },
    { rootMargin: "-15% 0px -65% 0px" },
  );
  headingObserver = observer;
  headings.forEach((h) => observer.observe(h));
  const diagrams = [...document.querySelectorAll("code.language-mermaid")];
  if (diagrams.length) {
    const { default: mermaid } = await import("mermaid");
    if (seq !== pageSequence) return;
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      htmlLabels: false,
      theme: "base",
      themeVariables: {
        fontFamily: "system-ui, sans-serif",
        fontSize: "15px",
        primaryColor: "#eaf0e5",
        primaryTextColor: "#273423",
        primaryBorderColor: "#93a48b",
        lineColor: "#8c9786",
        secondaryColor: "#e8edf3",
        tertiaryColor: "#f2ede2",
      },
      flowchart: { htmlLabels: false, useMaxWidth: true },
    });
    for (let i = 0; i < diagrams.length; i++) {
      const block = diagrams[i],
        figure = document.createElement("figure");
      figure.className = "diagram";
      const label = document.createElement("figcaption");
      label.textContent = "A closer look · Conceptual diagram";
      try {
        const { svg } = await mermaid.render(
          "diagram-" + seq + "-" + i,
          block.textContent,
        );
        if (seq !== pageSequence) return;
        figure.innerHTML = DOMPurify.sanitize(svg, {
          USE_PROFILES: { svg: true, svgFilters: true },
        });
        figure.append(label);
        block.parentElement.replaceWith(figure);
      } catch {
        block.parentElement.classList.add("diagram-fallback");
      }
    }
  }
  installMediaZoom();
}

function field(label, id, value, help = "", rows = 3) {
  return `<label class="field" for="${id}"><span>${label}</span>${help ? `<small>${help}</small>` : ""}<textarea id="${id}" rows="${rows}">${escape(value)}</textarea></label>`;
}
async function settingsPage(seq) {
  clearInterval(generationPoll);
  document.title = "Settings — QuietLight";
  const session = await api("session");
  if (seq !== pageSequence) return;
  if (!session.authenticated) {
    const keyHelp = await api("access-key-help");
    if (seq !== pageSequence) return;
    setPage(
      `<main id="main" class="settings-page unlock-page" tabindex="-1"><a class="back-link" href="/">← Back to the journal</a><p class="eyebrow">YOUR JOURNAL, YOUR DIRECTION</p><h1>A space for<br>your curiosity.</h1><p class="settings-lead">Adjust what you follow, how deep you go,<br>and when your next edition arrives.</p><form id="unlock-form" class="unlock-card"><label class="field" for="access-key"><span>Settings access key</span><input id="access-key" type="password" autocomplete="current-password" required placeholder="Enter your private access key"></label><p class="form-error" id="login-error" role="alert"></p><button class="button primary" type="submit">Unlock settings ${arrow}</button><details class="key-help"><summary>Where do I find my key?</summary><p>${keyHelp.from_any_directory ? "On the machine running Docker, open a terminal in any folder and run:" : "On the machine running Docker, open the deployment folder containing the compose.yml used to start this journal, then run:"}</p><div class="key-command"><code id="key-command">${escape(keyHelp.command)}</code><button type="button" id="copy-key-command" class="quiet-button" aria-label="Copy access key command">Copy</button></div><p>Copy the output and paste it into Settings access key above. The key is created when the journal first starts and stays in the deployment’s data folder, which may be separate from your source-code checkout. This command reads it directly from the running container.</p><p>The key protects edits and research requests. Reading the journal needs no sign-in on your private network.</p></details></form></main>`,
      "settings",
    );
    document.querySelector("#copy-key-command").onclick = async () => {
      const command = document.querySelector("#key-command");
      try {
        await navigator.clipboard.writeText(command.textContent);
        toast("Command copied");
      } catch {
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(command);
        selection.removeAllRanges();
        selection.addRange(range);
        try {
          if (document.execCommand("copy")) {
            selection.removeAllRanges();
            toast("Command copied");
            return;
          }
        } catch {
          // Keep the command selected for manual copying.
        }
        toast("Command selected. Use your device’s Copy action.");
      }
    };
    document.querySelector("#unlock-form").onsubmit = async (e) => {
      e.preventDefault();
      const b = e.target.querySelector("button");
      b.disabled = true;
      try {
        await api("login", {
          token: document.querySelector("#access-key").value.trim(),
        });
        await settingsPage(seq);
      } catch (err) {
        document.querySelector("#login-error").textContent = err.message;
      } finally {
        b.disabled = false;
      }
    };
    return;
  }
  const selected =
    new URLSearchParams(location.search).get("topic") || "default";
  const [s, state, catalog] = await Promise.all([
    api("settings" + topicQuery(selected)),
    api("status"),
    api("topics"),
  ]);
  if (seq !== pageSequence) return;
  currentStatus = state;
  setPage(
    `<main id="main" class="settings-page" tabindex="-1"><div class="settings-heading"><div><p class="eyebrow">A JOURNAL THAT FOLLOWS YOUR CURIOSITY</p><h1>Make it yours.</h1><p class="settings-lead">A few thoughtful directions.<br>A more useful morning.</p></div><button id="lock-settings" class="quiet-button">Lock settings ↗</button></div><form id="settings-form"><section class="settings-section"><div class="section-intro"><span class="note-number">01 / THE BRIEF</span><h2>What’s on<br>your mind?</h2><p>Describe the work you’re doing and the ideas you want to follow. Be as specific as you like.</p></div><div class="section-fields">${field("Your research brief", "prompt", s.prompt, "The direction for every new edition. Past editions stay as they were.", 8)}${field("Areas to explore", "topics", s.topics.join("\n"), "One area per line within this topic. Leave blank to use your brief alone.", 4)}<div class="example-note"><span>Try a direction like</span><p>“Follow new research in the topics I care about. Explain the evidence, compare approaches, and highlight ideas worth trying.”</p></div></div></section><section class="settings-section"><div class="section-intro"><span class="note-number">02 / THE FILTER</span><h2>More signal.<br>Less noise.</h2><p>Point toward sources you trust and away from topics that don’t serve your work.</p></div><div class="section-fields">${field("Preferred sources", "sources", s.sources.join("\n"), "A URL or source name on each line.", 4)}${field("Leave out", "exclude", s.exclude.join("\n"), "One exclusion per line.", 3)}<div class="field-pair"><label class="field" for="maximum-items"><span>Maximum stories</span><small>Keep each edition considered.</small><input id="maximum-items" type="number" min="1" max="12" value="${s.maximum_items}" required></label><label class="field" for="lookback-days"><span>Look back</span><small>Days of research to consider.</small><input id="lookback-days" type="number" min="1" max="30" value="${s.lookback_days}" required></label></div></div></section><section class="settings-section"><div class="section-intro"><span class="note-number">03 / THE RHYTHM</span><h2>Your own<br>reading rhythm.</h2><p>Your briefing appears here automatically when research is complete.</p></div><div class="section-fields"><label class="toggle-row"><span><strong>Publish daily</strong><small>Pause whenever you need a quieter inbox.</small></span><input id="schedule-enabled" type="checkbox" ${s.schedule.enabled ? "checked" : ""}><span class="switch" aria-hidden="true"></span></label><label class="field time-field" for="schedule-time"><span>Begin research at</span><input id="schedule-time" type="time" required value="${escape(s.schedule.time)}"><small>Europe/London · adjusts for daylight saving.<br>Research takes several minutes before an edition is ready.</small></label><div class="service-status" id="service-status"></div><div class="generate-row"><div><strong>Curious now?</strong><p>Generate an edition using your saved settings.<br>A new version replaces today’s entry; earlier versions stay archived.</p></div><button type="button" id="generate" class="button secondary">Generate now ${arrow}</button></div></div></section><div class="save-bar"><p id="save-message" role="status">Your next edition starts with a good brief.</p><button class="button primary" type="submit" id="save-settings">Save changes ${arrow}</button></div></form></main>`,
    "settings",
  );
  const form = document.querySelector("#settings-form");
  const topic = catalog.find((t) => t.id === selected);
  document.querySelector("#schedule-enabled").checked =
    topic.enabled && s.schedule.enabled;
  form.insertAdjacentHTML(
    "beforebegin",
    `<section class="topic-picker"><label class="field" for="topic-select"><span>Research topic</span><select id="topic-select">${catalog.map((t) => `<option value="${t.id}" ${t.id === selected ? "selected" : ""}>${escape(t.name)}</option>`).join("")}</select></label><form id="add-topic-form"><label class="field" for="new-topic-name"><span>A new direction</span><input id="new-topic-name" maxlength="80" required placeholder="e.g. Sports science"></label><button class="button secondary" type="submit">Add topic ${arrow}</button><p id="topic-error" role="alert"></p></form></section>`,
  );
  form
    .querySelector(".section-fields")
    .insertAdjacentHTML(
      "afterbegin",
      `<label class="field" for="topic-name"><span>Topic name</span><input id="topic-name" maxlength="80" required value="${escape(topic.name)}"></label>`,
    );
  document
    .querySelector(".time-field")
    .insertAdjacentHTML(
      "beforebegin",
      `<label class="field" for="schedule-cadence"><span>Research cadence</span><select id="schedule-cadence"><option value="daily">Daily</option><option value="weekdays">Weekdays</option><option value="weekly">Weekly</option></select><small>Applies only to this topic. Set its lookback window above to cover the time between editions.</small></label><label class="field" id="weekday-field" for="schedule-weekday"><span>Research day</span><select id="schedule-weekday">${weekdays.map((name, day) => `<option value="${day}">${name}</option>`).join("")}</select></label>`,
    );
  const cadence = document.querySelector("#schedule-cadence");
  cadence.value = s.schedule.cadence || "daily";
  document.querySelector("#schedule-weekday").value = s.schedule.weekday ?? 1;
  const updateCadence = () => {
    document.querySelector("#weekday-field").hidden =
      cadence.value !== "weekly";
  };
  cadence.addEventListener("change", updateCadence);
  updateCadence();
  document
    .querySelector("#schedule-enabled")
    .closest("label")
    .querySelector("strong").textContent = "Research automatically";
  let dirty = false;
  if (new URLSearchParams(location.search).has("add")) {
    document.querySelector("#new-topic-name").focus();
  }
  document.querySelector("#topic-select").onchange = (e) => {
    if (
      dirty &&
      !window.confirm("Discard unsaved changes and switch topics?")
    ) {
      e.target.value = selected;
      return;
    }
    history.pushState({}, "", "/settings" + topicQuery(e.target.value));
    route();
  };
  document.querySelector("#add-topic-form").onsubmit = async (e) => {
    e.preventDefault();
    if (dirty && !window.confirm("Discard unsaved changes and add a topic?"))
      return;
    const button = e.target.querySelector("button");
    button.disabled = true;
    try {
      const created = await api("topics", {
        name: document.querySelector("#new-topic-name").value,
      });
      history.pushState({}, "", "/settings" + topicQuery(created.id));
      await route();
      toast(
        "Topic added. Shape its brief and enable automatic research when ready.",
      );
    } catch (err) {
      document.querySelector("#topic-error").textContent = err.message;
    } finally {
      button.disabled = false;
    }
  };
  form.addEventListener("input", () => {
    dirty = true;
    document.querySelector("#save-message").textContent =
      "You have unsaved changes.";
    document.querySelector("#generate").disabled = true;
  });
  form.onsubmit = async (e) => {
    e.preventDefault();
    const button = document.querySelector("#save-settings");
    button.disabled = true;
    const lines = (id) =>
      document
        .querySelector("#" + id)
        .value.split("\n")
        .map((x) => x.trim())
        .filter(Boolean);
    try {
      await api("settings" + topicQuery(selected), {
        name: document.querySelector("#topic-name").value,
        enabled: document.querySelector("#schedule-enabled").checked,
        prompt: document.querySelector("#prompt").value,
        topics: lines("topics"),
        sources: lines("sources"),
        exclude: lines("exclude"),
        maximum_items: Number(document.querySelector("#maximum-items").value),
        lookback_days: Number(document.querySelector("#lookback-days").value),
        schedule: {
          enabled: document.querySelector("#schedule-enabled").checked,
          time: document.querySelector("#schedule-time").value,
          cadence: document.querySelector("#schedule-cadence").value,
          weekday: Number(document.querySelector("#schedule-weekday").value),
        },
      });
      dirty = false;
      document.querySelector(
        `#topic-select option[value="${selected}"]`,
      ).textContent = document.querySelector("#topic-name").value.trim();
      document.querySelector("#save-message").textContent =
        "Saved. Your next edition will follow this brief.";
      toast("Your research direction is saved");
      updateStatus(await api("status"));
    } catch (err) {
      document.querySelector("#save-message").textContent = err.message;
    } finally {
      button.disabled = false;
    }
  };
  document.querySelector("#lock-settings").onclick = async () => {
    await api("logout", {});
    settingsPage(seq);
  };
  document.querySelector("#generate").onclick = async () => {
    try {
      await api("generate" + topicQuery(selected), {});
      toast("Research started. Your edition will appear when it’s ready.");
      updateStatus(await api("status"));
    } catch (err) {
      toast(err.message);
    }
  };
  function updateStatus(st) {
    if (seq !== pageSequence) return;
    const el = document.querySelector("#service-status");
    if (!el) return;
    el.innerHTML = `<span class="status-dot ${st.online ? "online" : ""}"></span><span>${st.busy ? "Research in progress. You can leave this page." : !st.online ? "Research service is offline." : st.last_error ? "The last operation needs attention." : "Ready for your next edition."}</span>${st.last_error ? `<p>${escape(st.last_error)}</p>` : ""}`;
    const b = document.querySelector("#generate");
    b.disabled = dirty || st.busy || !st.online;
    b.innerHTML = st.busy ? "Researching…" : `Generate now ${arrow}`;
  }
  updateStatus(state);
  generationPoll = setInterval(async () => {
    try {
      updateStatus(await api("status"));
    } catch {}
  }, 5000);
}

async function route() {
  headingObserver?.disconnect();
  clearInterval(generationPoll);
  const seq = ++pageSequence;
  try {
    const match = location.pathname.match(/^\/edition\/(\d{4}-\d{2}-\d{2})$/);
    const topicMatch = location.pathname.match(
      /^\/topics\/([a-z0-9-]+)(?:\/edition\/(\d{4}-\d{2}-\d{2}))?$/,
    );
    if (topicMatch?.[2]) await article(topicMatch[2], seq, topicMatch[1]);
    else if (topicMatch) await home(seq, topicMatch[1]);
    else if (match) await article(match[1], seq);
    else if (location.pathname === "/settings") await settingsPage(seq);
    else await topicsHome(seq);
  } catch (err) {
    if (seq !== pageSequence) return;
    setPage(
      `<main id="main" class="empty-state error-page"><p class="eyebrow">A MOMENTARY PAUSE</p><h1>${err.status === 404 ? "This edition isn’t here." : "We couldn’t open the journal."}</h1><p>${escape(err.message)}</p><a class="button primary" href="/">Back to the journal ${arrow}</a></main>`,
    );
  }
}
document.addEventListener("click", (e) => {
  const a = e.target.closest("a");
  if (
    !a ||
    a.origin !== location.origin ||
    a.target ||
    a.hash ||
    e.metaKey ||
    e.ctrlKey ||
    e.shiftKey
  )
    return;
  e.preventDefault();
  history.pushState({}, "", a.pathname + a.search);
  route();
});
window.addEventListener("popstate", route);
window.addEventListener(
  "scroll",
  () => {
    const bar = document.querySelector(".reading-progress span");
    if (bar)
      bar.style.width =
        Math.min(
          100,
          (100 * scrollY) /
            Math.max(1, document.documentElement.scrollHeight - innerHeight),
        ) + "%";
  },
  { passive: true },
);
route();
