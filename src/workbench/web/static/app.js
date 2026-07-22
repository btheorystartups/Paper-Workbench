/* Paper-Workbench UI — single classic script, no dependencies.
   Layout: vocab/constants, helpers, router, views, event delegation. */
"use strict";

/* ===================== vocab / constants ===================== */

const KINDS = [
  "question", "hypothesis", "conjecture", "result", "method", "definition",
  "assumption", "limitation", "decision", "task", "note", "dataset", "analysis",
  "figure", "table", "manuscript", "section", "paper_candidate",
];

const STRENGTHS = [
  "formally_established", "empirically_established",
  "computationally_verified_within_scope", "heuristically_supported",
  "conjectured", "ai_suggested",
];

const ACCESS_LEVELS = [
  "metadata_only", "abstract_only", "excerpt_available",
  "full_text_authorized", "full_text_user_supplied",
];

const SUPPORTS = [
  "research_result", "external_source", "both", "common_knowledge",
  "interpretation", "hypothesis", "unsupported", "verification_required",
];

const NOVELTY = [
  "apparently_novel_limited_search", "related_work_with_distinction",
  "known_result_new_derivation_possible", "insufficient_evidence",
  "probably_not_novel", "expert_confirmation_required",
];

const SCREEN_STATES = ["unread", "maybe", "include", "exclude"];
const RELATIONSHIPS = ["supports", "contradicts", "background"];

const FIGURE_KINDS = ["bar", "line", "scatter", "scree", "heatmap"];

const PAPER_TYPES = [
  "original_empirical", "mathematical_theoretical", "methodological",
  "computational", "applied", "proof_of_concept", "short_communication",
  "technical_note", "expository", "review_survey", "comparative",
  "replication_validation", "software", "data_resource",
  "working_paper_preprint", "custom",
];

const STRUCTURES = [
  "imrad", "definition_theorem_proof_example",
  "problem_framework_analysis_implications", "historical_synthesis",
  "algorithm_correctness_complexity_experiments",
  "application_method_case_study_validation", "custom",
];

const EXPORT_FORMATS = ["md", "tex", "html", "docx", "bib", "pdf", "jats"];

const OUTPUT_TYPES = [
  "conference_abstract", "poster_outline", "plain_language_summary",
  "teaching_explanation", "graphical_abstract_brief",
];

// Research-object kinds eligible for AI paper-candidate generation (source material,
// not manuscript scaffolding or bookkeeping objects).
const GENERATE_ELIGIBLE_KINDS = new Set([
  "result", "question", "hypothesis", "conjecture", "method",
  "analysis", "dataset", "figure", "table",
]);

const ACCESS_COLOR = {
  metadata_only: "b-gray",
  abstract_only: "b-blue",
  excerpt_available: "b-teal",
  full_text_authorized: "b-green",
  full_text_user_supplied: "b-green",
};

const SUPPORT_COLOR = {
  research_result: "b-green",
  external_source: "b-blue",
  both: "b-teal",
  common_knowledge: "b-gray",
  interpretation: "b-purple",
  hypothesis: "b-amber",
  unsupported: "b-red",
  verification_required: "b-orange",
};

const SEVERITY_COLOR = {
  blocker: "b-red", error: "b-red", high: "b-red",
  warning: "b-amber", medium: "b-amber",
  info: "b-blue", low: "b-blue",
};

const RISK_COLOR = {
  read_only: "b-gray", reversible: "b-blue", external: "b-orange",
};

const STATE_COLOR = {
  unread: "b-gray", maybe: "b-amber", include: "b-green", exclude: "b-red",
  proposed: "b-amber", approved: "b-blue", executed: "b-green",
  rejected: "b-red", invalidated: "b-gray",
};

const SUBMISSION_STATUS_COLOR = {
  drafting: "b-gray",
  submitted: "b-blue", under_review: "b-blue", resubmitted: "b-blue",
  revision_requested: "b-amber",
  accepted: "b-green",
  rejected: "b-red", withdrawn: "b-red",
};

const SUBMISSION_TRANSITIONS = {
  drafting: ["submitted", "withdrawn"],
  submitted: ["under_review", "withdrawn", "rejected"],
  under_review: ["revision_requested", "accepted", "rejected", "withdrawn"],
  revision_requested: ["resubmitted", "withdrawn"],
  resubmitted: ["under_review", "withdrawn", "rejected"],
  accepted: [],
  rejected: [],
  withdrawn: [],
};

/* ===================== state ===================== */

const state = {
  workspaceId: null,
  projectNames: {},        // pid -> name
  pickedExcerpts: new Map(), // excerpt id -> label (claim form, survives re-render)
  pickedProject: null,       // pid the picked excerpts belong to
};

/* ===================== helpers ===================== */

function esc(v) {
  return String(v === null || v === undefined ? "" : v).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function api(path, method = "GET", body) {
  let res;
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let token = null;
  try { token = localStorage.getItem("wb_token"); } catch (_e) { token = null; }
  if (token) headers["Authorization"] = "Bearer " + token;
  try {
    res = await fetch(path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (_e) {
    throw new Error("Network error: could not reach the API.");
  }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_e) { data = null; }
  if (!res.ok) {
    let detail = res.status + " " + res.statusText;
    if (data && data.detail !== undefined) {
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return data;
}

function toast(msg, kind) {
  const region = document.getElementById("toast-region");
  const div = document.createElement("div");
  div.className = "toast " + (kind === "err" ? "err" : "ok");
  div.textContent = msg;
  region.appendChild(div);
  const sr = document.getElementById("sr-status");
  if (sr) sr.textContent = msg;
  setTimeout(() => div.remove(), kind === "err" ? 8000 : 4500);
}

function loadingHTML(msg) { return '<p class="loading">' + esc(msg || "Loading…") + "</p>"; }
function emptyHTML(msg) { return '<p class="empty">' + esc(msg) + "</p>"; }
function errorHTML(msg) { return '<div class="error-box" role="alert">' + esc(msg) + "</div>"; }

function badge(text, color) {
  return '<span class="badge ' + esc(color || "b-gray") + '">' + esc(pretty(text)) + "</span>";
}

function pretty(v) { return String(v === null || v === undefined ? "" : v).replace(/_/g, " "); }

function trunc(s, n) {
  s = String(s === null || s === undefined ? "" : s);
  n = n || 120;
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function options(list, selected, withBlank) {
  let html = withBlank ? '<option value="">' + esc(withBlank) + "</option>" : "";
  for (const v of list) {
    html += '<option value="' + esc(v) + '"' + (v === selected ? " selected" : "") + ">" +
      esc(pretty(v)) + "</option>";
  }
  return html;
}

function multiOptions(items, labelFn) {
  return items.map((it) =>
    '<option value="' + esc(it.id) + '">' + esc(trunc(labelFn(it), 80)) + "</option>").join("");
}

function selectedValues(sel) {
  return sel ? Array.from(sel.selectedOptions).map((o) => o.value).filter(Boolean) : [];
}

function fd(form) {
  const out = {};
  new FormData(form).forEach((v, k) => {
    if (typeof v === "string") out[k] = v.trim();
  });
  return out;
}

async function withBusy(btn, fn) {
  if (btn) btn.disabled = true;
  try { return await fn(); } finally { if (btn) btn.disabled = false; }
}

function fmtAuthors(a) {
  if (Array.isArray(a)) return a.join(", ");
  return a || "";
}

function jsonPre(obj) {
  let s;
  try { s = JSON.stringify(obj, null, 2); } catch (_e) { s = String(obj); }
  return '<pre class="payload">' + esc(s) + "</pre>";
}

/* ===================== health badge ===================== */

async function loadHealth() {
  const el = document.getElementById("mode-badge");
  try {
    const h = await api("/health");
    const mode = h && h.provider_mode ? String(h.provider_mode) : "unknown";
    if (mode === "live") {
      el.className = "mode-badge live";
      el.textContent = "live providers";
    } else {
      el.className = "mode-badge fake";
      el.textContent = "OFFLINE/FAKE MODE (" + mode + ")";
    }
  } catch (_e) {
    el.className = "mode-badge unknown";
    el.textContent = "API unreachable";
  }
}

/* ===================== auth ===================== */

async function loadAuth() {
  const area = document.getElementById("auth-area");
  if (!area) return;
  try {
    const me = await api("/auth/me");
    const name = (me && (me.name || me.email)) ? (me.name || me.email) : "user";
    area.innerHTML =
      '<span class="dim small-text">Signed in as ' + esc(name) + "</span> " +
      '<button type="button" class="small" data-action="sign-out">Sign out</button>';
  } catch (_e) {
    // 401 in local mode (auth off) or any error: the app keeps working without a token.
    area.innerHTML =
      '<button type="button" class="small" data-action="sign-in">Sign in</button>';
  }
}

function openAuthModal(mode) {
  const modal = document.getElementById("auth-modal");
  if (!modal) return;
  const isReg = mode === "register";
  modal.innerHTML =
    '<div class="modal">' +
    '<h2 id="auth-modal-title">' + (isReg ? "Register" : "Sign in") + "</h2>" +
    '<form class="stack" data-form="' + (isReg ? "auth-register" : "auth-login") + '">' +
    (isReg
      ? '<div class="field"><label for="auth-name">Name</label>' +
        '<input id="auth-name" name="name" type="text" autocomplete="name" required></div>'
      : "") +
    '<div class="field"><label for="auth-email">Email</label>' +
    '<input id="auth-email" name="email" type="email" autocomplete="email" required></div>' +
    '<div class="field"><label for="auth-password">Password</label>' +
    '<input id="auth-password" name="password" type="password" autocomplete="' +
    (isReg ? "new-password" : "current-password") + '" required></div>' +
    '<div class="modal-actions">' +
    '<button type="submit" class="primary">' + (isReg ? "Register" : "Sign in") + "</button>" +
    '<button type="button" class="small" data-action="auth-cancel">Cancel</button>' +
    "</div>" +
    '<p class="small-text dim">' +
    (isReg
      ? 'Already have an account? <a href="#" data-action="auth-show-login">Sign in</a>'
      : 'No account? <a href="#" data-action="auth-show-register">Register</a>') +
    "</p>" +
    "</form></div>";
  modal.hidden = false;
  const first = modal.querySelector("input");
  if (first) first.focus();
}

function closeAuthModal() {
  const modal = document.getElementById("auth-modal");
  if (!modal) return;
  modal.hidden = true;
  modal.innerHTML = "";
}

/* ===================== router ===================== */

const TABS = ["objects", "sources", "claims", "literature", "dialogue", "manuscripts", "submissions", "figures"];

function route() {
  const view = document.getElementById("view");
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "project" && parts[1]) {
    const tab = TABS.includes(parts[2]) ? parts[2] : "objects";
    renderProject(view, parts[1], tab, parts.slice(3));
  } else {
    renderHome(view);
  }
}

async function guarded(container, fn) {
  container.innerHTML = loadingHTML();
  try {
    await fn(container);
  } catch (e) {
    container.innerHTML = errorHTML(e.message);
  }
}

/* ===================== home ===================== */

async function renderHome(view) {
  view.innerHTML =
    '<div class="panel-row">' +
    '<section class="panel" aria-labelledby="ws-h">' +
    '<h2 id="ws-h">Workspaces</h2><div id="ws-area">' + loadingHTML() + "</div>" +
    "</section>" +
    '<section class="panel" aria-labelledby="pr-h">' +
    '<h2 id="pr-h">Projects</h2><div id="pr-area">' +
    emptyHTML("Select a workspace to see its projects.") + "</div>" +
    "</section></div>";
  const wsArea = document.getElementById("ws-area");
  try {
    const workspaces = await api("/workspaces");
    let html = "";
    if (!workspaces.length) {
      html += emptyHTML("No workspaces yet. Create one below.");
    } else {
      html +=
        '<div class="field"><label for="ws-select">Workspace</label>' +
        '<select id="ws-select" data-change="ws-select">' +
        '<option value="">— choose —</option>' +
        workspaces.map((w) =>
          '<option value="' + esc(w.id) + '"' +
          (w.id === state.workspaceId ? " selected" : "") + ">" + esc(w.name) + "</option>"
        ).join("") +
        "</select></div>";
    }
    html +=
      '<hr class="soft">' +
      '<form class="stack" data-form="create-workspace">' +
      '<div class="field"><label for="ws-name">New workspace name</label>' +
      '<input id="ws-name" name="name" type="text" required></div>' +
      '<div><button type="submit" class="primary">Create workspace</button></div>' +
      "</form>";
    wsArea.innerHTML = html;
    if (state.workspaceId && workspaces.some((w) => w.id === state.workspaceId)) {
      renderProjects(state.workspaceId);
    }
  } catch (e) {
    wsArea.innerHTML = errorHTML(e.message);
  }
}

async function renderProjects(wsId) {
  const area = document.getElementById("pr-area");
  if (!area) return;
  area.innerHTML = loadingHTML();
  try {
    const projects = await api("/workspaces/" + encodeURIComponent(wsId) + "/projects");
    for (const p of projects) state.projectNames[p.id] = p.name;
    let html = "";
    if (!projects.length) {
      html += emptyHTML("No projects in this workspace yet.");
    } else {
      html += '<div class="card-list">' + projects.map((p) =>
        '<button type="button" class="card" data-action="open-project" data-pid="' + esc(p.id) + '">' +
        '<span class="card-title">' + esc(p.name) + "</span>" +
        (p.description ? '<br><span class="dim small-text">' + esc(trunc(p.description, 140)) + "</span>" : "") +
        "</button>"
      ).join("") + "</div>";
    }
    html +=
      '<hr class="soft">' +
      '<form class="stack" data-form="create-project" data-wsid="' + esc(wsId) + '">' +
      '<div class="field"><label for="pr-name">New project name</label>' +
      '<input id="pr-name" name="name" type="text" required></div>' +
      '<div class="field"><label for="pr-desc">Description</label>' +
      '<textarea id="pr-desc" name="description"></textarea></div>' +
      '<div><button type="submit" class="primary">Create project</button></div>' +
      "</form>";
    area.innerHTML = html;
  } catch (e) {
    area.innerHTML = errorHTML(e.message);
  }
}

/* ===================== project shell ===================== */

function renderProject(view, pid, tab, sub) {
  const name = state.projectNames[pid] || "Project";
  view.innerHTML =
    '<nav class="crumbs" aria-label="Breadcrumb"><a href="#/">Home</a> / ' +
    esc(name) +
    ' <span id="usage-line" class="dim small-text"></span>' +
    ' <button type="button" class="small" data-action="set-budget" data-pid="' + esc(pid) + '">Budget</button>' +
    ' <button type="button" class="small" data-action="export-project" data-pid="' + esc(pid) + '">Export bundle</button>' +
    "</nav>" +
    '<nav class="tabs" aria-label="Project sections">' +
    TABS.map((t) =>
      '<a href="#/project/' + esc(pid) + "/" + t + '"' +
      (t === tab ? ' aria-current="page"' : "") + ">" +
      esc(t.charAt(0).toUpperCase() + t.slice(1)) + "</a>"
    ).join("") +
    "</nav>" +
    '<div id="tab-content"></div>';
  const el = document.getElementById("tab-content");
  const fns = {
    objects: tabObjects, sources: tabSources, claims: tabClaims,
    literature: tabLiterature, dialogue: tabDialogue, manuscripts: tabManuscripts,
    submissions: tabSubmissions, figures: tabFigures,
  };
  guarded(el, (c) => fns[tab](c, pid, sub || []));
  loadUsageLine(pid);
}

async function loadUsageLine(pid) {
  const el = document.getElementById("usage-line");
  if (!el) return;
  try {
    const u = await api("/projects/" + encodeURIComponent(pid) + "/usage");
    let text = "LLM this month: " + u.live_total_tokens.toLocaleString() + " live tokens";
    if (u.monthly_token_ceiling) {
      text += " / " + u.monthly_token_ceiling.toLocaleString() + " ceiling";
    }
    el.textContent = text;
    if (u.ceiling_reached) {
      el.innerHTML = esc(text) + " " + badge("CEILING REACHED", "b-amber");
    }
  } catch (_e) { el.textContent = ""; }
}

/* ===================== objects tab ===================== */

async function tabObjects(el, pid) {
  const objects = await api("/projects/" + encodeURIComponent(pid) + "/objects");
  let rows;
  if (!objects.length) {
    rows = emptyHTML("No research objects yet. Create the first one below.");
  } else {
    rows = '<div class="table-wrap"><table><thead><tr>' +
      "<th scope=\"col\">Kind</th><th scope=\"col\">Title</th><th scope=\"col\">Strength</th>" +
      "<th scope=\"col\">Status</th><th scope=\"col\">Actions</th>" +
      "</tr></thead><tbody>" +
      objects.map((o) => {
        let status = "";
        if (o.ai_suggested && !o.accepted_by_user) status += badge("AI-suggested", "b-amber") + " ";
        if (o.accepted_by_user) status += badge("accepted", "b-green");
        if (!o.ai_suggested && !o.accepted_by_user) status += '<span class="dim">—</span>';
        const accept = (!o.accepted_by_user)
          ? '<button type="button" class="small approve" data-action="accept-object" data-id="' +
            esc(o.id) + '">Accept</button>'
          : "";
        return "<tr><td>" + badge(o.kind, "b-gray") + "</td><td>" + esc(o.title) +
          "</td><td>" + (o.strength ? badge(o.strength, "b-teal") : '<span class="dim">—</span>') +
          "</td><td>" + status + "</td><td>" + accept + "</td></tr>";
      }).join("") +
      "</tbody></table></div>";
  }
  el.innerHTML =
    '<section class="panel" aria-labelledby="obj-h"><h2 id="obj-h">Research objects</h2>' +
    rows + "</section>" +
    '<section class="panel" aria-labelledby="obj-new-h"><h2 id="obj-new-h">New object</h2>' +
    '<form class="stack" data-form="create-object" data-pid="' + esc(pid) + '">' +
    '<div class="field-row">' +
    '<div class="field"><label for="obj-kind">Kind</label>' +
    '<select id="obj-kind" name="kind">' + options(KINDS, "note") + "</select></div>" +
    '<div class="field"><label for="obj-strength">Strength (optional)</label>' +
    '<select id="obj-strength" name="strength">' + options(STRENGTHS, "", "— none —") + "</select></div>" +
    "</div>" +
    '<div class="field"><label for="obj-title">Title</label>' +
    '<input id="obj-title" name="title" type="text" required></div>' +
    '<div class="field"><label for="obj-body">Body (optional free text)</label>' +
    '<textarea id="obj-body" name="body"></textarea></div>' +
    '<div><button type="submit" class="primary">Create object</button></div>' +
    "</form></section>";
}

/* ===================== sources tab ===================== */

function accessBadge(access) {
  return badge(access, ACCESS_COLOR[access] || "b-gray");
}

async function tabSources(el, pid, sub) {
  const selectedSid = sub[0] || null;
  const sources = await api("/projects/" + encodeURIComponent(pid) + "/sources");
  let rows;
  if (!sources.length) {
    rows = emptyHTML("No sources registered yet.");
  } else {
    rows = '<div class="table-wrap"><table><thead><tr>' +
      '<th scope="col">Title</th><th scope="col">Authors</th><th scope="col">Year</th>' +
      '<th scope="col">Venue</th><th scope="col">Access</th><th scope="col">Verified</th>' +
      '<th scope="col">DOI</th>' +
      "</tr></thead><tbody>" +
      sources.map((s) =>
        '<tr class="' + (s.id === selectedSid ? "row-selected" : "") + '"><td>' +
        '<button type="button" class="row-title-btn" data-action="open-source" data-pid="' +
        esc(pid) + '" data-sid="' + esc(s.id) + '">' + esc(trunc(s.title, 90)) + "</button></td><td>" +
        esc(trunc(fmtAuthors(s.authors), 60)) + "</td><td>" + esc(s.year || "") + "</td><td>" +
        esc(trunc(s.venue, 40)) + "</td><td>" + accessBadge(s.access) + "</td><td>" +
        (s.human_verified
          ? '<span class="verified" title="Human verified">✓ verified</span>'
          : '<span class="unverified">unverified</span>') +
        '</td><td class="mono">' + esc(s.doi || "") + "</td></tr>"
      ).join("") +
      "</tbody></table></div>";
  }

  let excerptPanel = "";
  if (selectedSid) {
    const src = sources.find((s) => s.id === selectedSid);
    excerptPanel =
      '<section class="panel" aria-labelledby="exc-h"><h2 id="exc-h">Excerpts — ' +
      esc(src ? trunc(src.title, 80) : selectedSid) + "</h2>" +
      '<div id="excerpt-list">' + loadingHTML() + "</div>" +
      '<hr class="soft">' +
      '<form class="stack" data-form="add-excerpt" data-sid="' + esc(selectedSid) + '">' +
      '<div class="field"><label for="exc-text">Excerpt text (verbatim)</label>' +
      '<textarea id="exc-text" name="text" required></textarea></div>' +
      '<div class="field"><label for="exc-loc">Locator (page, section, etc.)</label>' +
      '<input id="exc-loc" name="locator" type="text" required></div>' +
      '<div><button type="submit" class="primary">Capture excerpt</button></div>' +
      "</form></section>";
  }

  el.innerHTML =
    '<section class="panel" aria-labelledby="src-h"><h2 id="src-h">Sources</h2>' +
    '<p class="dim small-text">Click a source title to view and capture excerpts.</p>' +
    rows + "</section>" +
    excerptPanel +
    '<div class="panel-row">' +
    '<section class="panel" aria-labelledby="src-new-h"><h3 id="src-new-h">Register source</h3>' +
    '<form class="stack" data-form="create-source" data-pid="' + esc(pid) + '">' +
    '<div class="field"><label for="src-title">Title</label>' +
    '<input id="src-title" name="title" type="text" required></div>' +
    '<div class="field-row">' +
    '<div class="field"><label for="src-access">Access level</label>' +
    '<select id="src-access" name="access">' + options(ACCESS_LEVELS, "metadata_only") + "</select></div>" +
    '<div class="field"><label for="src-year">Year</label>' +
    '<input id="src-year" name="year" type="number" min="0" max="3000"></div>' +
    "</div>" +
    '<div class="field"><label for="src-acq">Acquisition note ' +
    '<span class="dim">(required for full-text access levels)</span></label>' +
    '<textarea id="src-acq" name="acquisition"></textarea></div>' +
    '<div class="field-row">' +
    '<div class="field"><label for="src-authors">Authors</label>' +
    '<input id="src-authors" name="authors" type="text"></div>' +
    '<div class="field"><label for="src-venue">Venue</label>' +
    '<input id="src-venue" name="venue" type="text"></div>' +
    "</div>" +
    '<div class="field-row">' +
    '<div class="field"><label for="src-doi">DOI</label>' +
    '<input id="src-doi" name="doi" type="text"></div>' +
    '<div class="field"><label for="src-url">URL</label>' +
    '<input id="src-url" name="url" type="text"></div>' +
    '<div class="field"><label for="src-license">License</label>' +
    '<input id="src-license" name="license" type="text"></div>' +
    "</div>" +
    '<div><button type="submit" class="primary">Register source</button></div>' +
    "</form></section>" +
    '<section class="panel" aria-labelledby="ing-h"><h3 id="ing-h">Ingest local file</h3>' +
    '<p class="dim small-text">Registers a file you already have on disk as a full-text (user-supplied) source.</p>' +
    '<form class="stack" data-form="ingest-file" data-pid="' + esc(pid) + '">' +
    '<div class="field"><label for="ing-path">Absolute file path</label>' +
    '<input id="ing-path" name="path" type="text" required ' +
    'placeholder="C:\\papers\\smith2024.pdf"></div>' +
    '<div class="field"><label for="ing-title">Title (optional)</label>' +
    '<input id="ing-title" name="title" type="text"></div>' +
    '<div class="field"><label for="ing-license">License (optional)</label>' +
    '<input id="ing-license" name="license" type="text"></div>' +
    '<div><button type="submit" class="primary">Ingest file</button></div>' +
    "</form></section></div>";

  if (selectedSid) loadExcerpts(selectedSid);
}

async function loadExcerpts(sid) {
  const box = document.getElementById("excerpt-list");
  if (!box) return;
  try {
    const excerpts = await api("/sources/" + encodeURIComponent(sid) + "/excerpts");
    if (!excerpts.length) {
      box.innerHTML = emptyHTML("No excerpts captured for this source yet.");
      return;
    }
    box.innerHTML = '<ul class="plain">' + excerpts.map((x) =>
      '<li class="excerpt-item"><blockquote style="margin:0">' + esc(x.text) + "</blockquote>" +
      '<div class="small-text dim">locator: ' + esc(x.locator) +
      ' &middot; checksum: <span class="mono">' + esc(trunc(x.checksum, 16)) + "</span></div></li>"
    ).join("") + "</ul>";
  } catch (e) {
    box.innerHTML = errorHTML(e.message);
  }
}

/* ===================== claims tab ===================== */

async function tabClaims(el, pid, sub) {
  const selectedCid = sub[0] || null;
  if (state.pickedProject !== pid) {
    state.pickedProject = pid;
    state.pickedExcerpts = new Map();
  }
  const [claims, sources, objects] = await Promise.all([
    api("/projects/" + encodeURIComponent(pid) + "/claims"),
    api("/projects/" + encodeURIComponent(pid) + "/sources"),
    api("/projects/" + encodeURIComponent(pid) + "/objects"),
  ]);

  let rows;
  if (!claims.length) {
    rows = emptyHTML("No claims yet. Every claim carries an explicit support state.");
  } else {
    rows = '<div class="table-wrap"><table><thead><tr>' +
      '<th scope="col">Claim</th><th scope="col">Support</th>' +
      '<th scope="col">Evidence</th><th scope="col">Notes</th>' +
      "</tr></thead><tbody>" +
      claims.map((c) =>
        '<tr class="' + (c.id === selectedCid ? "row-selected" : "") + '"><td>' +
        '<button type="button" class="row-title-btn" data-action="open-claim" data-pid="' +
        esc(pid) + '" data-cid="' + esc(c.id) + '">' + esc(trunc(c.text, 130)) + "</button></td><td>" +
        badge(c.support, SUPPORT_COLOR[c.support] || "b-gray") + "</td><td>" +
        esc(c.evidence_count) + "</td><td>" + esc(trunc(c.notes, 70)) + "</td></tr>"
      ).join("") +
      "</tbody></table></div>";
  }

  let evidencePanel = "";
  if (selectedCid) {
    const claim = claims.find((c) => c.id === selectedCid);
    evidencePanel =
      '<section class="panel" aria-labelledby="ev-h"><h2 id="ev-h">Evidence — ' +
      esc(claim ? trunc(claim.text, 90) : selectedCid) + "</h2>" +
      (claim ? "<p>" + badge(claim.support, SUPPORT_COLOR[claim.support] || "b-gray") + "</p>" : "") +
      '<div id="evidence-list">' + loadingHTML() + "</div></section>";
  }

  const sourceOpts = sources.map((s) =>
    '<option value="' + esc(s.id) + '">' + esc(trunc(s.title, 70)) + "</option>").join("");

  el.innerHTML =
    '<section class="panel" aria-labelledby="cl-h"><h2 id="cl-h">Claims</h2>' +
    '<p class="dim small-text">Support states are always shown; they are never collapsed.</p>' +
    rows + "</section>" +
    evidencePanel +
    '<section class="panel" aria-labelledby="cl-new-h"><h2 id="cl-new-h">New claim</h2>' +
    '<form class="stack" data-form="create-claim" data-pid="' + esc(pid) + '">' +
    '<div class="field"><label for="cl-text">Claim text</label>' +
    '<textarea id="cl-text" name="text" required></textarea></div>' +
    '<div class="field"><label for="cl-support">Support state</label>' +
    '<select id="cl-support" name="support">' + options(SUPPORTS, "unsupported") + "</select></div>" +
    '<div class="field"><label for="cl-notes">Notes</label>' +
    '<textarea id="cl-notes" name="notes"></textarea></div>' +
    '<fieldset><legend>Evidence: excerpts</legend>' +
    '<div class="field"><label for="cl-source">Pick a source to list its excerpts</label>' +
    '<select id="cl-source" data-change="claim-source" data-sid-holder>' +
    '<option value="">— choose source —</option>' + sourceOpts + "</select></div>" +
    '<div id="claim-excerpts" class="checklist" aria-live="polite"></div>' +
    '<div class="field"><span class="dim small-text">Selected excerpts:</span>' +
    '<div id="claim-picked" class="chips"></div></div>' +
    "</fieldset>" +
    '<div class="field"><label for="cl-objects">Evidence: research objects (multi-select)</label>' +
    '<select id="cl-objects" multiple>' +
    multiOptions(objects, (o) => "[" + o.kind + "] " + o.title) + "</select></div>" +
    '<div><button type="submit" class="primary">Create claim</button></div>' +
    "</form></section>";

  renderPickedChips();
  if (selectedCid) loadEvidence(selectedCid);
}

function renderPickedChips() {
  const box = document.getElementById("claim-picked");
  if (!box) return;
  if (!state.pickedExcerpts.size) {
    box.innerHTML = '<span class="dim small-text">none</span>';
    return;
  }
  let html = "";
  state.pickedExcerpts.forEach((label, id) => {
    html += '<span class="chip">' + esc(trunc(label, 46)) +
      '<button type="button" data-action="unpick-excerpt" data-id="' + esc(id) +
      '" aria-label="Remove excerpt ' + esc(trunc(label, 30)) + '">×</button></span>';
  });
  box.innerHTML = html;
}

async function loadClaimExcerpts(sid) {
  const box = document.getElementById("claim-excerpts");
  if (!box) return;
  if (!sid) { box.innerHTML = ""; return; }
  box.innerHTML = loadingHTML();
  try {
    const excerpts = await api("/sources/" + encodeURIComponent(sid) + "/excerpts");
    if (!excerpts.length) {
      box.innerHTML = emptyHTML("This source has no excerpts yet (capture them on the Sources tab).");
      return;
    }
    box.innerHTML = excerpts.map((x) =>
      "<label><input type=\"checkbox\" data-change=\"pick-excerpt\" value=\"" + esc(x.id) +
      "\" data-label=\"" + esc(trunc(x.text, 60)) + "\"" +
      (state.pickedExcerpts.has(x.id) ? " checked" : "") + "> " +
      esc(trunc(x.text, 110)) + ' <span class="dim">(' + esc(x.locator) + ")</span></label>"
    ).join("");
  } catch (e) {
    box.innerHTML = errorHTML(e.message);
  }
}

async function loadEvidence(cid) {
  const box = document.getElementById("evidence-list");
  if (!box) return;
  try {
    const links = await api("/claims/" + encodeURIComponent(cid) + "/evidence");
    if (!links.length) {
      box.innerHTML = emptyHTML("No evidence linked to this claim.");
      return;
    }
    box.innerHTML = '<ul class="plain">' + links.map((ln) =>
      '<li class="evidence-item">' +
      (ln.entailment ? badge(ln.entailment, "b-blue") + " " : "") +
      (ln.excerpt_id
        ? 'excerpt <span class="mono">' + esc(ln.excerpt_id) + "</span>"
        : "") +
      (ln.research_object_id
        ? ' research object <span class="mono">' + esc(ln.research_object_id) + "</span>"
        : "") +
      "</li>"
    ).join("") + "</ul>";
  } catch (e) {
    box.innerHTML = errorHTML(e.message);
  }
}

/* ===================== literature tab ===================== */

async function tabLiterature(el, pid) {
  el.innerHTML =
    '<section class="panel" aria-labelledby="lit-h"><h2 id="lit-h">Literature search</h2>' +
    '<form class="stack" data-form="lit-search" data-pid="' + esc(pid) + '">' +
    '<div class="field-row">' +
    '<div class="field"><label for="lit-provider">Provider</label>' +
    '<select id="lit-provider" name="provider">' + options(["openalex", "crossref"], "openalex") + "</select></div>" +
    '<div class="field"><label for="lit-count">Results</label>' +
    '<input id="lit-count" name="count" type="number" value="10" min="1" max="50"></div>' +
    "</div>" +
    '<div class="field"><label for="lit-query">Query</label>' +
    '<input id="lit-query" name="query" type="text" required></div>' +
    '<div><button type="submit" class="primary">Search</button></div>' +
    "</form>" +
    '<div id="lit-results">' + emptyHTML("Run a search to see results.") + "</div>" +
    "</section>" +
    '<section class="panel" aria-labelledby="mat-h"><h2 id="mat-h">Screening matrix</h2>' +
    '<div id="lit-matrix">' + loadingHTML() + "</div></section>" +
    '<section class="panel" aria-labelledby="con-h"><h2 id="con-h">Contribution statement</h2>' +
    '<form class="stack" data-form="contribution" data-pid="' + esc(pid) + '">' +
    '<div class="field"><label for="con-title">Title</label>' +
    '<input id="con-title" name="title" type="text" required></div>' +
    '<div class="field"><label for="con-statement">Statement</label>' +
    '<textarea id="con-statement" name="statement" required></textarea></div>' +
    '<div class="field"><label for="con-novelty">Novelty assessment</label>' +
    '<select id="con-novelty" name="novelty">' +
    options(NOVELTY, "insufficient_evidence") + "</select></div>" +
    '<div class="field"><label for="con-coverage">Coverage note (what was searched; mandatory)</label>' +
    '<textarea id="con-coverage" name="coverage_note" required></textarea></div>' +
    '<div class="field"><label for="con-prior">Closest prior sources (multi-select)</label>' +
    '<select id="con-prior" multiple></select></div>' +
    '<div><button type="submit" class="primary">Record contribution</button></div>' +
    "</form></section>";
  await loadMatrix(pid);
}

async function loadMatrix(pid) {
  const box = document.getElementById("lit-matrix");
  if (!box) return;
  box.innerHTML = loadingHTML();
  try {
    const rows = await api("/projects/" + encodeURIComponent(pid) + "/literature/matrix");
    const prior = document.getElementById("con-prior");
    if (prior) {
      prior.innerHTML = rows.map((r) =>
        '<option value="' + esc(r.source_id) + '">' + esc(trunc(r.title, 80)) + "</option>").join("");
    }
    if (!rows.length) {
      box.innerHTML = emptyHTML("No sources in the matrix yet. Import search results or register sources.");
      return;
    }
    box.innerHTML = '<div class="table-wrap"><table><thead><tr>' +
      '<th scope="col">Title</th><th scope="col">Year</th><th scope="col">Access</th>' +
      '<th scope="col">Verified</th><th scope="col">State</th><th scope="col">Relationship</th>' +
      '<th scope="col">Reason</th><th scope="col"><span class="visually-hidden">Save</span></th>' +
      "</tr></thead><tbody>" +
      rows.map((r, i) =>
        '<tr data-sid="' + esc(r.source_id) + '"><td>' + esc(trunc(r.title, 70)) +
        (r.doi ? '<br><span class="mono dim">' + esc(r.doi) + "</span>" : "") + "</td><td>" +
        esc(r.year || "") + "</td><td>" + accessBadge(r.access) + "</td><td>" +
        (r.human_verified ? '<span class="verified">✓</span>' : '<span class="unverified">–</span>') +
        "</td><td>" +
        '<label class="visually-hidden" for="mx-state-' + i + '">Screening state</label>' +
        '<select id="mx-state-' + i + '" data-field="state">' +
        options(SCREEN_STATES, r.state || "unread") + "</select> " +
        badge(r.state || "unread", STATE_COLOR[r.state || "unread"]) +
        "</td><td>" +
        '<label class="visually-hidden" for="mx-rel-' + i + '">Relationship</label>' +
        '<select id="mx-rel-' + i + '" data-field="relationship">' +
        options(RELATIONSHIPS, r.relationship || "", "—") + "</select></td><td>" +
        '<label class="visually-hidden" for="mx-reason-' + i + '">Reason</label>' +
        '<input id="mx-reason-' + i + '" type="text" data-field="reason" value="' +
        esc(r.reason || "") + '"></td><td>' +
        '<button type="button" class="small" data-action="lit-screen" data-pid="' + esc(pid) +
        '" data-sid="' + esc(r.source_id) + '">Save</button></td></tr>'
      ).join("") +
      "</tbody></table></div>";
  } catch (e) {
    box.innerHTML = errorHTML(e.message);
  }
}

function renderLitResults(pid, data) {
  const box = document.getElementById("lit-results");
  if (!box) return;
  const works = data.works || [];
  if (!works.length) {
    box.innerHTML = emptyHTML("No results for this query.");
    return;
  }
  box.innerHTML = '<div class="table-wrap"><table><thead><tr>' +
    '<th scope="col">Title</th><th scope="col">Authors</th><th scope="col">Year</th>' +
    '<th scope="col">Venue</th><th scope="col">Cited by</th><th scope="col">Abstract</th>' +
    '<th scope="col"><span class="visually-hidden">Import</span></th>' +
    "</tr></thead><tbody>" +
    works.map((w) =>
      "<tr><td>" + esc(trunc(w.title, 90)) +
      (w.doi ? '<br><span class="mono dim">' + esc(w.doi) + "</span>" : "") + "</td><td>" +
      esc(trunc(fmtAuthors(w.authors), 50)) + "</td><td>" + esc(w.year || "") + "</td><td>" +
      esc(trunc(w.venue, 35)) + "</td><td>" + esc(w.cited_by_count == null ? "" : w.cited_by_count) +
      "</td><td>" + (w.has_abstract ? badge("yes", "b-teal") : '<span class="dim">no</span>') +
      "</td><td>" +
      '<button type="button" class="small primary" data-action="lit-import" data-pid="' + esc(pid) +
      '" data-provider="' + esc(w.provider) + '" data-provider-id="' + esc(w.provider_id) +
      '" data-query="' + esc(data._query || "") + '">Import</button></td></tr>'
    ).join("") +
    "</tbody></table></div>";
}

/* ===================== dialogue tab ===================== */

async function tabDialogue(el, pid, sub) {
  const selectedTid = sub[0] || null;
  const [threads, objects, sources] = await Promise.all([
    api("/projects/" + encodeURIComponent(pid) + "/threads"),
    api("/projects/" + encodeURIComponent(pid) + "/objects"),
    api("/projects/" + encodeURIComponent(pid) + "/sources"),
  ]);

  let list;
  if (!threads.length) {
    list = emptyHTML("No dialogue threads yet.");
  } else {
    list = '<div class="card-list">' + threads.map((t) =>
      '<button type="button" class="card' + (t.id === selectedTid ? " row-selected" : "") +
      '" data-action="open-thread" data-pid="' + esc(pid) + '" data-tid="' + esc(t.id) + '">' +
      '<span class="card-title">' + esc(t.title) + "</span>" +
      (t.goal ? '<br><span class="dim small-text">' + esc(trunc(t.goal, 100)) + "</span>" : "") +
      '<br><span class="dim small-text">' +
      esc((t.pinned_object_ids || []).length) + " pinned objects · " +
      esc((t.pinned_source_ids || []).length) + " pinned sources</span>" +
      "</button>"
    ).join("") + "</div>";
  }

  let threadView = "";
  if (selectedTid) {
    const th = threads.find((t) => t.id === selectedTid);
    threadView =
      '<section class="panel" aria-labelledby="th-h"><h2 id="th-h">' +
      esc(th ? th.title : "Thread") + "</h2>" +
      '<div id="chat-log" class="chat-log">' + loadingHTML() + "</div>" +
      '<form class="stack" data-form="send-turn" data-pid="' + esc(pid) +
      '" data-tid="' + esc(selectedTid) + '">' +
      '<div class="field"><label for="turn-input">Your message</label>' +
      '<textarea id="turn-input" name="content" required></textarea></div>' +
      '<div><button type="submit" class="primary">Send</button></div>' +
      "</form>" +
      '<hr class="soft"><h3>Proposed actions</h3>' +
      '<p class="dim small-text">AI-proposed actions run only after your explicit approval.</p>' +
      '<div id="action-list">' + loadingHTML() + "</div>" +
      "</section>";
  }

  el.innerHTML =
    '<div class="panel-row">' +
    "<div>" +
    '<section class="panel" aria-labelledby="thl-h"><h2 id="thl-h">Threads</h2>' + list + "</section>" +
    '<section class="panel" aria-labelledby="thn-h"><h3 id="thn-h">New thread</h3>' +
    '<form class="stack" data-form="create-thread" data-pid="' + esc(pid) + '">' +
    '<div class="field"><label for="th-title">Title</label>' +
    '<input id="th-title" name="title" type="text" required></div>' +
    '<div class="field"><label for="th-goal">Goal</label>' +
    '<textarea id="th-goal" name="goal"></textarea></div>' +
    '<div class="field"><label for="th-pin-obj">Pin research objects</label>' +
    '<select id="th-pin-obj" multiple>' +
    multiOptions(objects, (o) => "[" + o.kind + "] " + o.title) + "</select></div>" +
    '<div class="field"><label for="th-pin-src">Pin sources</label>' +
    '<select id="th-pin-src" multiple>' +
    multiOptions(sources, (s) => s.title) + "</select></div>" +
    '<div><button type="submit" class="primary">Create thread</button></div>' +
    "</form></section>" +
    "</div>" +
    "<div>" + (threadView || '<section class="panel">' +
      emptyHTML("Select a thread to view the conversation.") + "</section>") + "</div>" +
    "</div>";

  if (selectedTid) {
    loadTurns(selectedTid);
    loadActions(selectedTid);
  }
}

async function loadTurns(tid) {
  const box = document.getElementById("chat-log");
  if (!box) return;
  try {
    const turns = await api("/threads/" + encodeURIComponent(tid) + "/turns");
    if (!turns.length) {
      box.innerHTML = emptyHTML("No messages yet. Say something below.");
      return;
    }
    box.innerHTML = turns.map((t) => {
      const p = t.provenance || {};
      const isUser = t.role === "user";
      let meta = '<span class="msg-meta">' +
        "<strong>" + esc(isUser ? "you" : t.role) + "</strong>";
      if (!isUser && p.model) meta += '<span class="mono">' + esc(p.model) + "</span>";
      if (!isUser && p.simulated) meta += badge("SIMULATED", "b-amber");
      meta += "</span>";
      return '<div class="msg ' + (isUser ? "user" : "assistant") + '">' + meta +
        esc(t.content) + "</div>";
    }).join("");
    box.scrollTop = box.scrollHeight;
  } catch (e) {
    box.innerHTML = errorHTML(e.message);
  }
}

async function loadActions(tid) {
  const box = document.getElementById("action-list");
  if (!box) return;
  try {
    const actions = await api("/threads/" + encodeURIComponent(tid) + "/actions");
    if (!actions.length) {
      box.innerHTML = emptyHTML("No proposed actions in this thread.");
      return;
    }
    box.innerHTML = '<ul class="plain">' + actions.map((a) => {
      const pending = a.status === "proposed";
      let html = '<li class="action-item">' +
        "<strong>" + esc(pretty(a.kind)) + "</strong> " +
        badge(a.risk, RISK_COLOR[a.risk] || "b-gray") + " " +
        badge(a.status, STATE_COLOR[a.status] || "b-gray");
      html += jsonPre(a.payload);
      if (a.result && Object.keys(a.result).length) {
        html += '<div class="small-text dim" style="margin-top:0.3rem">result:</div>' + jsonPre(a.result);
      }
      if (pending) {
        html += '<div style="margin-top:0.5rem;display:flex;gap:0.4rem">' +
          '<button type="button" class="small approve" data-action="action-approve" data-tid="' +
          esc(tid) + '" data-aid="' + esc(a.id) + '" data-hash="' + esc(a.plan_hash) +
          '">Approve</button>' +
          '<button type="button" class="small danger" data-action="action-reject" data-tid="' +
          esc(tid) + '" data-aid="' + esc(a.id) + '">Reject</button></div>';
      }
      return html + "</li>";
    }).join("") + "</ul>";
  } catch (e) {
    box.innerHTML = errorHTML(e.message);
  }
}

/* ===================== manuscripts tab ===================== */

async function tabManuscripts(el, pid, sub) {
  const selectedMid = sub[0] || null;
  const [objects, claims] = await Promise.all([
    api("/projects/" + encodeURIComponent(pid) + "/objects"),
    api("/projects/" + encodeURIComponent(pid) + "/claims"),
  ]);
  const manuscripts = objects.filter((o) => o.kind === "manuscript");
  const candidates = objects.filter((o) => o.kind === "paper_candidate");
  const byId = {};
  for (const o of objects) byId[o.id] = o;

  let list;
  if (!manuscripts.length) {
    list = emptyHTML("No manuscripts yet. Create a paper candidate, then a manuscript.");
  } else {
    list = '<div class="card-list">' + manuscripts.map((m) =>
      '<button type="button" class="card' + (m.id === selectedMid ? " row-selected" : "") +
      '" data-action="open-manuscript" data-pid="' + esc(pid) + '" data-mid="' + esc(m.id) + '">' +
      '<span class="card-title">' + esc(m.title) + "</span>" +
      '<br><span class="dim small-text">' +
      esc(((m.body || {}).section_order || []).length) + " sections</span>" +
      "</button>"
    ).join("") + "</div>";
  }

  let msView = "";
  if (selectedMid) {
    const m = manuscripts.find((x) => x.id === selectedMid);
    const order = m ? ((m.body || {}).section_order || []) : [];
    const sections = order.map((id) => byId[id]).filter(Boolean);
    let secHtml;
    if (!sections.length) {
      secHtml = emptyHTML("No sections yet.");
    } else {
      secHtml = '<ul class="plain">' + sections.map((s, i) => {
        const b = s.body || {};
        return '<li class="finding section-item"><h4>' + (i + 1) + ". " + esc(s.title) + "</h4>" +
          (b.purpose ? '<div class="dim small-text">purpose: ' + esc(b.purpose) + "</div>" : "") +
          (b.text ? "<div>" + esc(trunc(b.text, 400)) + "</div>" : "") +
          '<div class="dim small-text">' +
          esc((b.claim_ids || []).length) + " linked claims" +
          (b.word_budget ? " · budget " + esc(b.word_budget) + " words" : "") +
          "</div></li>";
      }).join("") + "</ul>";
    }
    msView =
      '<section class="panel" aria-labelledby="ms-h"><h2 id="ms-h">Manuscript: ' +
      esc(m ? m.title : selectedMid) + "</h2>" +
      "<h3>Sections</h3>" + secHtml +
      '<hr class="soft"><h3>Add section</h3>' +
      '<form class="stack" data-form="add-section" data-mid="' + esc(selectedMid) + '">' +
      '<div class="field-row">' +
      '<div class="field"><label for="sec-heading">Heading</label>' +
      '<input id="sec-heading" name="heading" type="text" required></div>' +
      '<div class="field"><label for="sec-budget">Word budget</label>' +
      '<input id="sec-budget" name="word_budget" type="number" min="1"></div>' +
      '<div class="field"><label for="sec-pos">Position (0-based)</label>' +
      '<input id="sec-pos" name="position" type="number" min="0"></div>' +
      "</div>" +
      '<div class="field"><label for="sec-purpose">Purpose</label>' +
      '<input id="sec-purpose" name="purpose" type="text"></div>' +
      '<div class="field"><label for="sec-text">Text</label>' +
      '<textarea id="sec-text" name="text"></textarea></div>' +
      '<div class="field"><label for="sec-claims">Linked claims (multi-select)</label>' +
      '<select id="sec-claims" multiple>' +
      multiOptions(claims, (c) => c.text) + "</select></div>" +
      '<div><button type="submit" class="primary">Add section</button></div>' +
      "</form>" +
      '<hr class="soft"><h3>Checks &amp; export</h3>' +
      '<div style="display:flex;gap:0.5rem;flex-wrap:wrap;align-items:center">' +
      '<button type="button" data-action="ms-audit" data-mid="' + esc(selectedMid) + '">Run audit</button>' +
      '<button type="button" data-action="ms-review" data-mid="' + esc(selectedMid) + '">Skeptical review</button>' +
      "</div>" +
      '<form class="stack" data-form="ms-export" data-mid="' + esc(selectedMid) +
      '" style="margin-top:0.6rem">' +
      "<fieldset><legend>Export formats</legend><div class=\"chips\">" +
      EXPORT_FORMATS.map((f) =>
        '<label class="chip"><input type="checkbox" name="fmt" value="' + esc(f) +
        '" checked> ' + esc(f) + "</label>").join("") +
      "</div></fieldset>" +
      '<div><button type="submit" class="primary">Export</button></div>' +
      "</form>" +
      '<div id="ms-results" style="margin-top:0.8rem"></div>' +
      '<hr class="soft"><h3>Alternative outputs</h3>' +
      '<p class="empty">Grounded in this manuscript only; each is AI-suggested and awaits ' +
      "your review.</p>" +
      '<div style="display:flex;gap:0.5rem;flex-wrap:wrap;align-items:center">' +
      '<label class="visually-hidden" for="out-type">Output type</label>' +
      '<select id="out-type">' + options(OUTPUT_TYPES) + "</select>" +
      '<button type="button" data-action="ms-output" data-mid="' + esc(selectedMid) +
      '">Generate</button></div>' +
      '<div id="ms-outputs" style="margin-top:0.6rem"></div>' +
      "</section>";
  }

  const eligibleObjs = objects.filter((o) => GENERATE_ELIGIBLE_KINDS.has(o.kind));
  const eligibleOpts = eligibleObjs.length
    ? multiOptions(eligibleObjs, (o) => o.kind + ": " + o.title)
    : "";

  const generatePanel =
    '<section class="panel" aria-labelledby="gen-h"><h3 id="gen-h">Generate paper candidates (AI)</h3>' +
    '<p class="dim small-text">Pick research objects and the model proposes several distinct ' +
    "paper angles. Each is AI-suggested and awaits your review.</p>" +
    '<form class="stack" data-form="generate-candidates" data-pid="' + esc(pid) + '">' +
    '<div class="field"><label for="gen-objs">Research objects (multi-select)</label>' +
    '<select id="gen-objs" multiple>' + eligibleOpts + "</select>" +
    (eligibleObjs.length ? "" :
      '<span class="dim small-text">No eligible research objects yet.</span>') +
    "</div>" +
    '<div class="field-row">' +
    '<div class="field"><label for="gen-audience">Audience (optional)</label>' +
    '<input id="gen-audience" name="audience" type="text"></div>' +
    '<div class="field"><label for="gen-venue">Venue class (optional)</label>' +
    '<input id="gen-venue" name="venue_class" type="text"></div>' +
    '<div class="field"><label for="gen-n">How many (1–5)</label>' +
    '<input id="gen-n" name="n" type="number" min="1" max="5" value="3"></div>' +
    "</div>" +
    '<div class="field"><label for="gen-constraints">Constraints (optional)</label>' +
    '<input id="gen-constraints" name="constraints" type="text"></div>' +
    '<div><button type="submit" class="primary">Generate candidates</button></div>' +
    "</form></section>";

  const candCards = candidates.length
    ? candidates.map((c) => renderCandidateCard(c)).join("")
    : emptyHTML("No paper candidates yet. Generate some above, or create one manually below.");

  const candSection =
    '<section class="panel" aria-labelledby="cand-h"><h2 id="cand-h">Paper candidates</h2>' +
    (candidates.length
      ? '<div style="margin-bottom:0.7rem"><button type="button" ' +
        'data-action="compare-candidates" data-pid="' + esc(pid) + '" data-cids="' +
        esc(candidates.map((c) => c.id).join(",")) + '">Compare all</button></div>'
      : "") +
    '<div id="candidate-compare-results"></div>' +
    candCards +
    "</section>";

  el.innerHTML =
    '<section class="panel" aria-labelledby="msl-h"><h2 id="msl-h">Manuscripts</h2>' +
    list + "</section>" +
    msView +
    generatePanel +
    candSection +
    '<div class="panel-row">' +
    '<section class="panel" aria-labelledby="pc-h"><h3 id="pc-h">New paper candidate</h3>' +
    '<form class="stack" data-form="create-candidate" data-pid="' + esc(pid) + '">' +
    '<div class="field"><label for="pc-title">Title</label>' +
    '<input id="pc-title" name="title" type="text" required></div>' +
    '<div class="field-row">' +
    '<div class="field"><label for="pc-type">Paper type</label>' +
    '<select id="pc-type" name="paper_type">' + options(PAPER_TYPES, "original_empirical") + "</select></div>" +
    '<div class="field"><label for="pc-structure">Structure</label>' +
    '<select id="pc-structure" name="structure">' + options(STRUCTURES, "imrad") + "</select></div>" +
    "</div>" +
    '<div class="field"><label for="pc-q">Central question</label>' +
    '<textarea id="pc-q" name="central_question" required></textarea></div>' +
    '<div class="field"><label for="pc-thesis">Thesis</label>' +
    '<textarea id="pc-thesis" name="thesis" required></textarea></div>' +
    '<div class="field"><label for="pc-audience">Audience</label>' +
    '<input id="pc-audience" name="audience" type="text"></div>' +
    '<div class="field"><label for="pc-caveat">Novelty caveat</label>' +
    '<input id="pc-caveat" name="novelty_caveat" type="text"></div>' +
    '<div class="field"><label for="pc-risks">Risks</label>' +
    '<textarea id="pc-risks" name="risks"></textarea></div>' +
    '<div class="field"><label for="pc-missing">Missing work</label>' +
    '<textarea id="pc-missing" name="missing_work"></textarea></div>' +
    '<div class="field"><label for="pc-objs">Included research objects</label>' +
    '<select id="pc-objs" multiple>' +
    multiOptions(objects.filter((o) => o.kind !== "manuscript" && o.kind !== "section"),
      (o) => "[" + o.kind + "] " + o.title) + "</select></div>" +
    '<div><button type="submit" class="primary">Create candidate</button></div>' +
    "</form></section>" +
    '<section class="panel" aria-labelledby="msn-h"><h3 id="msn-h">New manuscript</h3>' +
    '<form class="stack" data-form="create-manuscript" data-pid="' + esc(pid) + '">' +
    '<div class="field"><label for="ms-title">Title</label>' +
    '<input id="ms-title" name="title" type="text" required></div>' +
    '<div class="field"><label for="ms-cand">From candidate (optional)</label>' +
    '<select id="ms-cand" name="from_candidate_id">' +
    '<option value="">— none —</option>' +
    multiOptions(candidates, (c) => c.title) + "</select></div>" +
    '<div><button type="submit" class="primary">Create manuscript</button></div>' +
    "</form></section></div>";
}

function renderCandidateCard(c) {
  const b = c.body || {};
  const frozen = !!b.frozen;

  let badges = "";
  if (b.angle) badges += badge(b.angle, "b-purple") + " ";
  if (b.paper_type) badges += badge(b.paper_type, "b-blue") + " ";
  if (b.recommendation) badges += badge(b.recommendation, "b-teal") + " ";
  badges += frozen ? badge("frozen", "b-green") : badge("proposal", "b-amber");

  const included = (b.included_object_ids || []).length;
  const excluded = b.excluded || [];
  const missing = b.missing_work || [];
  const plan = b.section_plan || [];

  let details = "";
  if (b.central_question) {
    details += '<div class="small-text"><strong>Central question:</strong> ' +
      esc(b.central_question) + "</div>";
  }
  if (b.scope) {
    details += '<div class="small-text"><strong>Scope:</strong> ' + esc(b.scope) + "</div>";
  }
  details += '<div class="small-text"><strong>Included objects:</strong> ' +
    esc(included) + "</div>";
  if (excluded.length) {
    details += '<div class="small-text"><strong>Excluded:</strong></div><ul class="plain">' +
      excluded.map((x) =>
        '<li class="finding">' + esc((x && x.ref) || "") +
        (x && x.reason ? " — " + esc(x.reason) : "") + "</li>").join("") + "</ul>";
  }
  if (missing.length) {
    details += '<div class="small-text"><strong>Missing work:</strong></div><ul class="plain">' +
      missing.map((m) =>
        '<li class="finding">' +
        esc(typeof m === "string" ? m : (m && (m.text || m.title)) || JSON.stringify(m)) +
        "</li>").join("") + "</ul>";
  }
  if (plan.length) {
    details += '<div class="small-text"><strong>Section plan:</strong></div><ol class="section-plan">' +
      plan.map((s) => {
        if (typeof s === "string") return "<li>" + esc(s) + "</li>";
        const heading = (s && (s.heading || s.title || s.name)) || "";
        const purpose = (s && s.purpose) ? " — " + esc(s.purpose) : "";
        return "<li>" + esc(heading) + purpose + "</li>";
      }).join("") + "</ol>";
  }

  const footer = frozen
    ? '<p class="small-text dim">Frozen — available in the manuscript ' +
      "'From candidate' picker.</p>"
    : '<div><button type="button" class="small approve" data-action="freeze-candidate" ' +
      'data-cid="' + esc(c.id) + '">Freeze this plan</button></div>';

  return '<div class="candidate-card">' +
    '<div class="cand-head"><strong>' + esc(c.title) + "</strong></div>" +
    '<p class="chips">' + badges + "</p>" +
    (b.thesis ? "<div>" + esc(b.thesis) + "</div>" : "") +
    (b.novelty_caveat
      ? '<div class="small-text dim">Novelty caveat: ' + esc(b.novelty_caveat) + "</div>"
      : "") +
    '<details><summary>Plan details</summary>' + details + "</details>" +
    footer +
    "</div>";
}

function renderCompare(data) {
  const box = document.getElementById("candidate-compare-results");
  if (!box) return;
  const cands = data.candidates || [];
  const fields = data.fields || [];
  const matrix = data.matrix || {};
  if (!cands.length || !fields.length) {
    box.innerHTML = emptyHTML("Nothing to compare.");
    return;
  }
  const cell = (v) => {
    if (v === null || v === undefined) return "—";
    if (Array.isArray(v)) return v.length ? v.join("; ") : "—";
    return String(v);
  };
  box.innerHTML = '<div class="table-wrap"><table class="compare-table"><thead><tr>' +
    '<th scope="col">Field</th>' +
    cands.map((c) =>
      '<th scope="col">' + esc(trunc(c.title, 40)) +
      (c.frozen ? " " + badge("frozen", "b-green") : "") +
      '<br><span class="dim small-text">' + esc(c.included_count == null ? 0 : c.included_count) +
      " objects</span></th>").join("") +
    "</tr></thead><tbody>" +
    fields.map((f) => {
      const row = matrix[f] || {};
      return '<tr><th scope="row">' + esc(pretty(f)) + "</th>" +
        cands.map((c) => "<td>" + esc(cell(row[c.id])) + "</td>").join("") + "</tr>";
    }).join("") +
    "</tbody></table></div>";
}

function renderAudit(data) {
  const box = document.getElementById("ms-results");
  if (!box) return;
  const findings = data.findings || [];
  const counts = data.counts || {};
  let html = "<h3>Audit findings</h3>";
  html += '<p class="chips">' + (Object.keys(counts).length
    ? Object.keys(counts).map((k) =>
        badge(k + ": " + counts[k], SEVERITY_COLOR[k] || "b-gray")).join(" ")
    : badge("no findings", "b-green")) + "</p>";
  if (!findings.length) {
    box.innerHTML = html + emptyHTML("Audit passed with no findings.");
    return;
  }
  const groups = {};
  for (const f of findings) (groups[f.severity] = groups[f.severity] || []).push(f);
  const order = ["blocker", "error", "high", "warning", "medium", "info", "low"];
  const keys = Object.keys(groups).sort((a, b) => {
    const ia = order.indexOf(a), ib = order.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
  for (const sev of keys) {
    html += "<h4>" + badge(sev, SEVERITY_COLOR[sev] || "b-gray") + "</h4><ul class=\"plain\">" +
      groups[sev].map((f) =>
        '<li class="finding"><span class="mono">' + esc(f.code) + "</span> " + esc(f.message) +
        (f.object_id ? ' <span class="dim mono small-text">(' + esc(f.object_id) + ")</span>" : "") +
        "</li>").join("") + "</ul>";
  }
  box.innerHTML = html;
}

function renderReview(data) {
  const box = document.getElementById("ms-results");
  if (!box) return;
  const objections = data.objections || [];
  let html = "<h3>Skeptical review</h3>";
  if (!objections.length) {
    box.innerHTML = html + emptyHTML("No objections raised.");
    return;
  }
  html += '<ul class="plain">' + objections.map((o) => {
    const b = o.body || {};
    const text = typeof b === "string" ? b : (b.text || b.note || "");
    return '<li class="objection">' + badge("AI-suggested", "b-amber") + " " +
      "<strong>" + esc(o.title) + "</strong>" +
      (text ? "<div>" + esc(text) + "</div>" : (b && Object.keys(b).length ? jsonPre(b) : "")) +
      "</li>";
  }).join("") + "</ul>";
  box.innerHTML = html;
}

function renderExport(data) {
  const box = document.getElementById("ms-results");
  if (!box) return;
  const files = data.files || {};
  let html = "<h3>Export complete</h3>" +
    '<p>Output directory: <span class="mono">' + esc(data.out_dir) + "</span></p>";
  const keys = Object.keys(files);
  html += keys.length
    ? '<ul class="plain">' + keys.map((k) =>
        '<li class="finding"><strong>' + esc(k) + '</strong> <span class="mono">' +
        esc(files[k]) + "</span></li>").join("") + "</ul>"
    : emptyHTML("No files were written.");
  if (data.audit_findings && data.audit_findings.length) {
    html += '<p class="dim small-text">' + esc(data.audit_findings.length) +
      " audit finding(s) recorded in the export manifest.</p>";
  }
  box.innerHTML = html;
}

/* ===================== submissions tab ===================== */

async function tabSubmissions(el, pid) {
  const [submissions, objects] = await Promise.all([
    api("/projects/" + encodeURIComponent(pid) + "/submissions"),
    api("/projects/" + encodeURIComponent(pid) + "/objects"),
  ]);
  const manuscripts = objects.filter((o) => o.kind === "manuscript");
  const titleById = {};
  for (const o of objects) titleById[o.id] = o.title;

  let list;
  if (!submissions.length) {
    list = emptyHTML("No submissions yet. Create one below.");
  } else {
    list = '<ul class="plain">' +
      submissions.map((s) => renderSubmission(s, titleById)).join("") + "</ul>";
  }

  let newForm;
  if (!manuscripts.length) {
    newForm = emptyHTML(
      "Create a manuscript first (on the Manuscripts tab) before submitting to a venue.");
  } else {
    newForm =
      '<form class="stack" data-form="create-submission" data-pid="' + esc(pid) + '">' +
      '<div class="field"><label for="sub-ms">Manuscript</label>' +
      '<select id="sub-ms" name="manuscript_id" required>' +
      multiOptions(manuscripts, (m) => m.title) + "</select></div>" +
      '<div class="field-row">' +
      '<div class="field"><label for="sub-venue">Venue name (optional)</label>' +
      '<input id="sub-venue" name="venue_name" type="text"></div>' +
      '<div class="field"><label for="sub-deadline">Deadline (optional)</label>' +
      '<input id="sub-deadline" name="deadline" type="date"></div>' +
      "</div>" +
      '<div><button type="submit" class="primary">Create submission</button></div>' +
      "</form>";
  }

  el.innerHTML =
    '<section class="panel" aria-labelledby="sub-h"><h2 id="sub-h">Submissions</h2>' +
    '<p class="dim small-text">Only legal next states are offered for each submission.</p>' +
    list + "</section>" +
    '<section class="panel" aria-labelledby="sub-new-h"><h2 id="sub-new-h">New submission</h2>' +
    newForm + "</section>";
}

function statusBadge(status) {
  return badge(status, SUBMISSION_STATUS_COLOR[status] || "b-gray");
}

function renderSubmission(s, titleById) {
  const title = titleById[s.manuscript_id] || s.manuscript_id;
  const nexts = SUBMISSION_TRANSITIONS[s.status] || [];
  const history = s.history || [];
  const revisions = s.revisions || [];

  const head =
    '<div class="sub-head"><div><strong>' + esc(title) + "</strong>" +
    (s.venue_name ? ' <span class="dim">— ' + esc(s.venue_name) + "</span>" : "") +
    "</div><div>" + statusBadge(s.status) + "</div></div>" +
    '<div class="small-text dim">' +
    (s.deadline ? "deadline: " + esc(s.deadline) : "no deadline") + "</div>";

  let transitions;
  if (nexts.length) {
    transitions =
      '<div class="sub-actions">' +
      '<label class="visually-hidden" for="sub-note-' + esc(s.id) + '">Transition note</label>' +
      '<input id="sub-note-' + esc(s.id) + '" type="text" class="sub-note" ' +
      'placeholder="optional note">' +
      nexts.map((to) =>
        '<button type="button" class="small" data-action="submission-transition" data-sid="' +
        esc(s.id) + '" data-to="' + esc(to) + '">' + esc(pretty(to)) + "</button>").join("") +
      "</div>";
  } else {
    transitions = '<div class="small-text dim">Terminal state — no further transitions.</div>';
  }

  let historyHtml;
  if (!history.length) {
    historyHtml = emptyHTML("No status changes recorded yet.");
  } else {
    historyHtml = '<ul class="plain timeline">' + history.map((h) =>
      '<li class="timeline-item">' +
      statusBadge(h.from) + ' <span class="dim">→</span> ' + statusBadge(h.to) +
      (h.note ? " <span>" + esc(h.note) + "</span>" : "") +
      '<div class="small-text dim mono">' + esc(h.at || "") + "</div></li>").join("") + "</ul>";
  }

  let revHtml;
  if (!revisions.length) {
    revHtml = emptyHTML("No revisions or responses to reviewers yet.");
  } else {
    revHtml = '<ul class="plain">' + revisions.map((r) =>
      '<li class="finding"><strong>Round ' + esc(r.round) + "</strong>" +
      (r.status_when_added ? " " + statusBadge(r.status_when_added) : "") +
      "<div>" + esc(r.summary) + "</div>" +
      '<div class="small-text dim mono">' + esc(r.at || "") + "</div></li>").join("") + "</ul>";
  }

  const revForm =
    '<form class="stack" data-form="add-revision" data-sid="' + esc(s.id) + '">' +
    '<div class="field"><label for="rev-sum-' + esc(s.id) + '">Revision summary</label>' +
    '<textarea id="rev-sum-' + esc(s.id) + '" name="summary" required></textarea></div>' +
    '<div class="field"><label for="rev-resp-' + esc(s.id) + '">Response to reviewers</label>' +
    '<textarea id="rev-resp-' + esc(s.id) + '" name="response_to_reviewers" required></textarea></div>' +
    '<div class="field"><label for="rev-chg-' + esc(s.id) + '">Changes (one per line, optional)</label>' +
    '<textarea id="rev-chg-' + esc(s.id) + '" name="changes"></textarea></div>' +
    '<div><button type="submit" class="primary small">Add revision</button></div>' +
    "</form>";

  return '<li class="submission-item">' + head + transitions +
    '<details class="sub-details"><summary>History (' + history.length + ")</summary>" +
    historyHtml + "</details>" +
    '<details class="sub-details"><summary>Revisions / responses to reviewers (' +
    revisions.length + ")</summary>" + revHtml + '<hr class="soft">' + revForm + "</details></li>";
}

/* ===================== figures tab ===================== */

async function tabFigures(el, pid) {
  const objects = await api("/projects/" + encodeURIComponent(pid) + "/objects");
  const datasets = objects.filter((o) => o.kind === "dataset");
  const figures = objects.filter((o) => o.kind === "figure");
  const tables = objects.filter((o) => o.kind === "table");

  let dsList;
  if (!datasets.length) {
    dsList = emptyHTML("No datasets yet. Create one below.");
  } else {
    dsList = '<ul class="plain">' + datasets.map((d) => {
      const b = d.body || {};
      const cols = b.columns || [];
      return '<li class="finding"><strong>' + esc(d.title) + "</strong>" +
        '<div class="small-text dim">' + esc(cols.length) + " columns · " +
        esc(b.n_rows == null ? 0 : b.n_rows) + " rows</div>" +
        (cols.length ? '<div class="small-text mono">' + esc(cols.join(", ")) + "</div>" : "") +
        "</li>";
    }).join("") + "</ul>";
  }

  const dsOpts = '<option value="">— choose dataset —</option>' +
    datasets.map((d) =>
      '<option value="' + esc(d.id) + '">' + esc(trunc(d.title, 70)) + "</option>").join("");

  const figList = figures.length
    ? figures.map((f) => renderFigureCard(f)).join("")
    : emptyHTML("No figures rendered yet.");

  const tblList = tables.length
    ? tables.map((t) => renderTableCard(t)).join("")
    : emptyHTML("No tables built yet.");

  el.innerHTML =
    '<section class="panel" aria-labelledby="fig-audit-h"><h2 id="fig-audit-h">Artifact audit</h2>' +
    '<p class="dim small-text">Surface stale, orphan, or uncaptioned figures and tables.</p>' +
    '<div><button type="button" data-action="run-artifact-audit" data-pid="' + esc(pid) +
    '">Run artifact audit</button></div>' +
    '<div id="fig-audit-results" style="margin-top:0.6rem"></div>' +
    "</section>" +

    '<section class="panel" aria-labelledby="ds-h"><h2 id="ds-h">Datasets</h2>' +
    dsList +
    '<hr class="soft"><h3>New dataset</h3>' +
    '<form class="stack" data-form="create-dataset" data-pid="' + esc(pid) + '">' +
    '<div class="field"><label for="ds-name">Name</label>' +
    '<input id="ds-name" name="name" type="text" required></div>' +
    '<div class="field"><label for="ds-cols">Columns (comma-separated)</label>' +
    '<input id="ds-cols" name="columns" type="text" required placeholder="year, value, group"></div>' +
    '<div class="field"><label for="ds-rows">Rows (one per line, comma-separated cells)</label>' +
    '<textarea id="ds-rows" name="rows" required ' +
    'placeholder="2020, 3.1, a&#10;2021, 4.7, b"></textarea></div>' +
    '<div><button type="submit" class="primary">Create dataset</button></div>' +
    "</form></section>" +

    '<section class="panel" aria-labelledby="figs-h"><h2 id="figs-h">Figures</h2>' +
    "<h3>Render figure</h3>" +
    '<form class="stack" data-form="render-figure" data-pid="' + esc(pid) + '">' +
    '<div class="field"><label for="fig-title">Title</label>' +
    '<input id="fig-title" name="title" type="text" required></div>' +
    '<div class="field-row">' +
    '<div class="field"><label for="fig-dataset">Dataset</label>' +
    '<select id="fig-dataset" name="dataset_id" required>' + dsOpts + "</select></div>" +
    '<div class="field"><label for="fig-kind">Kind</label>' +
    '<select id="fig-kind" name="kind">' + options(FIGURE_KINDS, "bar") + "</select></div>" +
    "</div>" +
    '<div class="field-row">' +
    '<div class="field"><label for="fig-x">X column</label>' +
    '<input id="fig-x" name="x" type="text"></div>' +
    '<div class="field"><label for="fig-series">Series (comma-separated columns)</label>' +
    '<input id="fig-series" name="series" type="text"></div>' +
    "</div>" +
    '<div class="field-row">' +
    '<div class="field"><label for="fig-xlabel">X label (optional)</label>' +
    '<input id="fig-xlabel" name="xlabel" type="text"></div>' +
    '<div class="field"><label for="fig-ylabel">Y label (optional)</label>' +
    '<input id="fig-ylabel" name="ylabel" type="text"></div>' +
    "</div>" +
    '<div class="field"><label class="checkbox-label">' +
    '<input type="checkbox" name="grayscale"> Grayscale (print-safe)</label></div>' +
    '<div><button type="submit" class="primary">Render figure</button></div>' +
    "</form>" +
    '<hr class="soft">' + figList +
    "</section>" +

    '<section class="panel" aria-labelledby="tbl-h"><h2 id="tbl-h">Tables</h2>' +
    "<h3>Build table</h3>" +
    '<form class="stack" data-form="build-table" data-pid="' + esc(pid) + '">' +
    '<div class="field"><label for="tbl-title">Title</label>' +
    '<input id="tbl-title" name="title" type="text" required></div>' +
    '<div class="field"><label for="tbl-dataset">Dataset</label>' +
    '<select id="tbl-dataset" name="dataset_id" required>' + dsOpts + "</select></div>" +
    '<div class="field"><label for="tbl-cols">Columns subset (comma-separated, optional)</label>' +
    '<input id="tbl-cols" name="columns" type="text"></div>' +
    '<div><button type="submit" class="primary">Build table</button></div>' +
    "</form>" +
    '<hr class="soft">' + tblList +
    "</section>";
}

function renderFigureCard(f) {
  const b = f.body || {};
  const num = b.number == null ? "" : b.number;
  let badges = "";
  if (b.palette) badges += " " + badge(b.palette, "b-gray");
  if (b.colorblind_safe) badges += " " + badge("colour-blind-safe", "b-green");
  if (b.renderer) badges += " " + badge(b.renderer, "b-blue");

  const caption = b.caption
    ? '<div class="fig-caption">' + esc(b.caption) + "</div>"
    : '<div><button type="button" class="small" data-action="generate-caption" data-id="' +
      esc(f.id) + '">Generate caption</button></div>';

  let accept = "";
  if (f.ai_suggested && !f.accepted_by_user) {
    accept = '<div class="fig-accept">' + badge("AI-suggested", "b-amber") +
      '<button type="button" class="small approve" data-action="accept-object" data-id="' +
      esc(f.id) + '">Accept</button></div>';
  }

  return '<figure class="fig-item">' +
    '<figcaption class="fig-head"><strong>Figure ' + esc(num) + "</strong> — " +
    esc(f.title) + badges + "</figcaption>" +
    '<img class="fig-image" src="/figures/' + esc(f.id) + '/image" alt="' +
    esc(b.alt_text || f.title) + '">' +
    caption + accept +
    "</figure>";
}

function renderTableCard(t) {
  const b = t.body || {};
  const num = b.number == null ? "" : b.number;
  return '<div class="tbl-item">' +
    '<div class="fig-head"><strong>Table ' + esc(num) + "</strong> — " + esc(t.title) + "</div>" +
    '<div class="table-wrap">' + markdownTableToHTML(b.markdown) + "</div></div>";
}

function markdownTableToHTML(md) {
  const lines = String(md == null ? "" : md).split("\n").map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return emptyHTML("No table content.");
  const splitRow = (line) => {
    const cells = line.split("|");
    if (cells.length && cells[0].trim() === "") cells.shift();
    if (cells.length && cells[cells.length - 1].trim() === "") cells.pop();
    return cells.map((c) => c.trim());
  };
  const isSep = (line) => line.indexOf("-") >= 0 && /^[\s|:-]+$/.test(line);
  const header = splitRow(lines[0]);
  let rest = lines.slice(1);
  if (rest.length && isSep(rest[0])) rest = rest.slice(1);
  return "<table><thead><tr>" +
    header.map((h) => '<th scope="col">' + esc(h) + "</th>").join("") +
    "</tr></thead><tbody>" +
    rest.map((line) =>
      "<tr>" + splitRow(line).map((c) => "<td>" + esc(c) + "</td>").join("") + "</tr>").join("") +
    "</tbody></table>";
}

function renderArtifactAudit(data) {
  const box = document.getElementById("fig-audit-results");
  if (!box) return;
  const findings = data.findings || [];
  const counts = data.counts || {};
  let html = '<p class="chips">' + (Object.keys(counts).length
    ? Object.keys(counts).map((k) =>
        badge(k + ": " + counts[k], SEVERITY_COLOR[k] || "b-gray")).join(" ")
    : badge("no findings", "b-green")) + "</p>";
  if (!findings.length) {
    box.innerHTML = html + emptyHTML("No artifact issues found.");
    return;
  }
  const groups = {};
  for (const f of findings) (groups[f.severity] = groups[f.severity] || []).push(f);
  const order = ["blocker", "error", "high", "warning", "medium", "info", "low"];
  const keys = Object.keys(groups).sort((a, b) => {
    const ia = order.indexOf(a), ib = order.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
  for (const sev of keys) {
    html += "<h4>" + badge(sev, SEVERITY_COLOR[sev] || "b-gray") + "</h4><ul class=\"plain\">" +
      groups[sev].map((f) =>
        '<li class="finding"><span class="mono">' + esc(f.code) + "</span> " + esc(f.message) +
        (f.object_id ? ' <span class="dim mono small-text">(' + esc(f.object_id) + ")</span>" : "") +
        "</li>").join("") + "</ul>";
  }
  box.innerHTML = html;
}

/* ===================== event delegation: clicks ===================== */

const clickActions = {
  "open-project": (t) => { location.hash = "#/project/" + t.dataset.pid + "/objects"; },

  "set-budget": (t) => withBusy(t, async () => {
    const current = window.prompt(
      "Monthly live-token ceiling for this project (0 = unlimited):", "0");
    if (current === null) return;
    const ceiling = parseInt(current, 10);
    if (isNaN(ceiling) || ceiling < 0) { toast("Enter a number >= 0.", "err"); return; }
    try {
      await api("/projects/" + encodeURIComponent(t.dataset.pid) + "/budget", "POST",
        { monthly_token_ceiling: ceiling });
      toast(ceiling ? "Ceiling set to " + ceiling.toLocaleString() + " tokens/month."
                    : "Budget set to unlimited.");
      loadUsageLine(t.dataset.pid);
    } catch (e) { toast(e.message, "err"); }
  }),

  "export-project": (t) => withBusy(t, async () => {
    try {
      const r = await api("/projects/" + encodeURIComponent(t.dataset.pid) + "/export", "POST", {});
      toast("Bundle written: " + r.path);
    } catch (e) { toast(e.message, "err"); }
  }),
  "open-source": (t) => { location.hash = "#/project/" + t.dataset.pid + "/sources/" + t.dataset.sid; },
  "open-claim": (t) => { location.hash = "#/project/" + t.dataset.pid + "/claims/" + t.dataset.cid; },
  "open-thread": (t) => { location.hash = "#/project/" + t.dataset.pid + "/dialogue/" + t.dataset.tid; },
  "open-manuscript": (t) => { location.hash = "#/project/" + t.dataset.pid + "/manuscripts/" + t.dataset.mid; },

  "submission-transition": (t) => withBusy(t, async () => {
    const noteInput = document.getElementById("sub-note-" + t.dataset.sid);
    const note = noteInput ? noteInput.value.trim() : "";
    const payload = { to_status: t.dataset.to };
    if (note) payload.note = note;
    try {
      await api("/submissions/" + encodeURIComponent(t.dataset.sid) + "/transition", "POST", payload);
      toast("Status changed to " + pretty(t.dataset.to) + ".");
    } catch (e) {
      toast(e.message, "err");
    }
    route();
  }),

  "sign-in": () => openAuthModal("login"),
  "sign-out": () => {
    try { localStorage.removeItem("wb_token"); } catch (_e) { /* ignore */ }
    location.reload();
  },
  "auth-cancel": () => closeAuthModal(),
  "auth-show-login": () => openAuthModal("login"),
  "auth-show-register": () => openAuthModal("register"),

  "accept-object": (t) => withBusy(t, async () => {
    try {
      await api("/objects/" + encodeURIComponent(t.dataset.id) + "/accept", "POST", {});
      toast("Object accepted.");
      route();
    } catch (e) { toast(e.message, "err"); }
  }),

  "unpick-excerpt": (t) => {
    state.pickedExcerpts.delete(t.dataset.id);
    renderPickedChips();
    const cb = document.querySelector(
      '#claim-excerpts input[value="' + CSS.escape(t.dataset.id) + '"]');
    if (cb) cb.checked = false;
  },

  "lit-import": (t) => withBusy(t, async () => {
    try {
      const r = await api("/projects/" + encodeURIComponent(t.dataset.pid) + "/literature/import",
        "POST", {
          provider: t.dataset.provider,
          query: t.dataset.query || "",
          provider_id: t.dataset.providerId,
        });
      toast(r.created
        ? "Imported (" + pretty(r.access) + ")."
        : "Already in project (" + pretty(r.access) + ").");
      t.textContent = "Imported";
      await loadMatrix(t.dataset.pid);
    } catch (e) { toast(e.message, "err"); }
  }),

  "lit-screen": (t) => withBusy(t, async () => {
    const tr = t.closest("tr");
    const get = (f) => {
      const inp = tr.querySelector('[data-field="' + f + '"]');
      return inp ? inp.value.trim() : "";
    };
    const body = { source_id: t.dataset.sid, state: get("state") };
    const rel = get("relationship");
    const reason = get("reason");
    if (rel) body.relationship = rel;
    if (reason) body.reason = reason;
    try {
      await api("/projects/" + encodeURIComponent(t.dataset.pid) + "/literature/screen", "POST", body);
      toast("Screening saved.");
      await loadMatrix(t.dataset.pid);
    } catch (e) { toast(e.message, "err"); }
  }),

  "action-approve": (t) => withBusy(t, async () => {
    try {
      const r = await api("/actions/" + encodeURIComponent(t.dataset.aid) + "/approve",
        "POST", { plan_hash: t.dataset.hash });
      toast("Action approved (" + pretty(r.status) + ").");
    } catch (e) {
      toast(e.message, "err");
    }
    loadActions(t.dataset.tid);
    loadTurns(t.dataset.tid);
  }),

  "action-reject": (t) => withBusy(t, async () => {
    try {
      await api("/actions/" + encodeURIComponent(t.dataset.aid) + "/reject", "POST", {});
      toast("Action rejected.");
    } catch (e) {
      toast(e.message, "err");
    }
    loadActions(t.dataset.tid);
  }),

  "run-artifact-audit": (t) => withBusy(t, async () => {
    const box = document.getElementById("fig-audit-results");
    if (box) box.innerHTML = loadingHTML("Running artifact audit…");
    try {
      renderArtifactAudit(await api("/projects/" + encodeURIComponent(t.dataset.pid) +
        "/artifacts/audit"));
      toast("Artifact audit complete.");
    } catch (e) {
      if (box) box.innerHTML = errorHTML(e.message);
      toast(e.message, "err");
    }
  }),

  "generate-caption": (t) => withBusy(t, async () => {
    try {
      await api("/artifacts/" + encodeURIComponent(t.dataset.id) + "/caption", "POST", {});
      toast("Caption generated (AI-suggested; review it).");
      route();
    } catch (e) { toast(e.message, "err"); }
  }),

  "freeze-candidate": (t) => withBusy(t, async () => {
    try {
      await api("/paper-candidates/" + encodeURIComponent(t.dataset.cid) + "/freeze", "POST", {});
      toast("Candidate frozen; available in the manuscript picker.");
      route();
    } catch (e) { toast(e.message, "err"); }
  }),

  "compare-candidates": (t) => withBusy(t, async () => {
    const ids = (t.dataset.cids || "").split(",").filter(Boolean);
    if (ids.length < 2) {
      toast("Need at least two candidates to compare.", "err");
      return;
    }
    const box = document.getElementById("candidate-compare-results");
    if (box) box.innerHTML = loadingHTML("Comparing candidates…");
    try {
      const data = await api("/projects/" + encodeURIComponent(t.dataset.pid) +
        "/paper-candidates/compare", "POST", { candidate_ids: ids });
      renderCompare(data);
      toast("Comparison ready.");
    } catch (e) {
      if (box) box.innerHTML = errorHTML(e.message);
      toast(e.message, "err");
    }
  }),

  "ms-audit": (t) => withBusy(t, async () => {
    const box = document.getElementById("ms-results");
    if (box) box.innerHTML = loadingHTML("Running audit…");
    try {
      renderAudit(await api("/manuscripts/" + encodeURIComponent(t.dataset.mid) + "/audit"));
      toast("Audit complete.");
    } catch (e) {
      if (box) box.innerHTML = errorHTML(e.message);
      toast(e.message, "err");
    }
  }),

  "ms-review": (t) => withBusy(t, async () => {
    const box = document.getElementById("ms-results");
    if (box) box.innerHTML = loadingHTML("Running skeptical review…");
    try {
      renderReview(await api("/manuscripts/" + encodeURIComponent(t.dataset.mid) +
        "/skeptical-review", "POST", {}));
      toast("Skeptical review complete.");
    } catch (e) {
      if (box) box.innerHTML = errorHTML(e.message);
      toast(e.message, "err");
    }
  }),

  "ms-output": (t) => withBusy(t, async () => {
    const box = document.getElementById("ms-outputs");
    const sel = document.getElementById("out-type");
    const otype = sel ? sel.value : "";
    if (box) box.innerHTML = loadingHTML("Generating (may call the model)…");
    try {
      await api("/manuscripts/" + encodeURIComponent(t.dataset.mid) + "/outputs",
        "POST", { output_type: otype });
      toast("Output generated (AI-suggested; review it).");
      await loadOutputs(t.dataset.mid);
    } catch (e) {
      if (box) box.innerHTML = errorHTML(e.message);
      toast(e.message, "err");
    }
  }),
};

async function loadOutputs(mid) {
  const box = document.getElementById("ms-outputs");
  if (!box) return;
  box.innerHTML = loadingHTML("Loading outputs…");
  try {
    const items = await api("/manuscripts/" + encodeURIComponent(mid) + "/outputs");
    if (!items.length) { box.innerHTML = emptyHTML("No alternative outputs yet."); return; }
    box.innerHTML = items.map((o) =>
      '<div class="panel" style="margin-top:0.5rem">' +
      badge(o.output_kind, "b-purple") + " " +
      (o.simulated ? badge("simulated", "b-amber") : "") +
      badge("AI-suggested", "b-amber") +
      ' <span class="muted">' + esc(o.word_count || 0) + " words</span>" +
      '<pre class="payload" style="white-space:pre-wrap">' + esc(o.content || "") + "</pre>" +
      "</div>").join("");
  } catch (e) {
    box.innerHTML = errorHTML(e.message);
  }
}

/* ===================== event delegation: forms ===================== */

const formActions = {
  "create-workspace": async (form) => {
    const body = fd(form);
    const w = await api("/workspaces", "POST", { name: body.name });
    state.workspaceId = w.id;
    toast('Workspace "' + w.name + '" created.');
    route();
  },

  "create-project": async (form) => {
    const body = fd(form);
    const p = await api("/projects", "POST", {
      workspace_id: form.dataset.wsid, name: body.name, description: body.description || "",
    });
    state.projectNames[p.id] = p.name;
    toast('Project "' + p.name + '" created.');
    renderProjects(form.dataset.wsid);
  },

  "create-object": async (form) => {
    const body = fd(form);
    const payload = { kind: body.kind, title: body.title };
    if (body.body) payload.body = { text: body.body };
    if (body.strength) payload.strength = body.strength;
    await api("/projects/" + encodeURIComponent(form.dataset.pid) + "/objects", "POST", payload);
    toast("Object created.");
    route();
  },

  "create-source": async (form) => {
    const body = fd(form);
    if (body.access.startsWith("full_text") && !body.acquisition) {
      throw new Error("Full-text access levels require an acquisition note.");
    }
    const payload = { title: body.title, access: body.access };
    if (body.acquisition) payload.acquisition = body.acquisition;
    if (body.authors) payload.authors = body.authors;
    if (body.year) payload.year = parseInt(body.year, 10);
    if (body.venue) payload.venue = body.venue;
    if (body.doi) payload.doi = body.doi;
    if (body.url) payload.url = body.url;
    if (body.license) payload.license = body.license;
    await api("/projects/" + encodeURIComponent(form.dataset.pid) + "/sources", "POST", payload);
    toast("Source registered.");
    route();
  },

  "ingest-file": async (form) => {
    const body = fd(form);
    const payload = { path: body.path };
    if (body.title) payload.title = body.title;
    if (body.license) payload.license = body.license;
    const r = await api("/projects/" + encodeURIComponent(form.dataset.pid) + "/ingest",
      "POST", payload);
    toast('Ingested "' + trunc(r.title, 50) + '" (' + pretty(r.access) + ").");
    route();
  },

  "add-excerpt": async (form) => {
    const body = fd(form);
    await api("/sources/" + encodeURIComponent(form.dataset.sid) + "/excerpts", "POST", {
      text: body.text, locator: body.locator,
    });
    toast("Excerpt captured.");
    form.reset();
    loadExcerpts(form.dataset.sid);
  },

  "create-claim": async (form) => {
    const body = fd(form);
    const payload = { text: body.text, support: body.support };
    if (body.notes) payload.notes = body.notes;
    const excerptIds = Array.from(state.pickedExcerpts.keys());
    if (excerptIds.length) payload.excerpt_ids = excerptIds;
    const objIds = selectedValues(form.querySelector("#cl-objects"));
    if (objIds.length) payload.research_object_ids = objIds;
    await api("/projects/" + encodeURIComponent(form.dataset.pid) + "/claims", "POST", payload);
    state.pickedExcerpts = new Map();
    toast("Claim created.");
    route();
  },

  "lit-search": async (form) => {
    const body = fd(form);
    const box = document.getElementById("lit-results");
    if (box) box.innerHTML = loadingHTML("Searching " + body.provider + "…");
    try {
      const data = await api("/projects/" + encodeURIComponent(form.dataset.pid) +
        "/literature/search", "POST", {
          provider: body.provider, query: body.query,
          count: parseInt(body.count, 10) || 10,
        });
      data._query = body.query;
      renderLitResults(form.dataset.pid, data);
      toast((data.works || []).length + " result(s).");
    } catch (e) {
      if (box) box.innerHTML = errorHTML(e.message);
      throw e;
    }
  },

  "contribution": async (form) => {
    const body = fd(form);
    const payload = {
      title: body.title, statement: body.statement,
      novelty: body.novelty, coverage_note: body.coverage_note,
    };
    const prior = selectedValues(form.querySelector("#con-prior"));
    if (prior.length) payload.closest_prior_source_ids = prior;
    await api("/projects/" + encodeURIComponent(form.dataset.pid) + "/contributions",
      "POST", payload);
    toast("Contribution recorded.");
    form.reset();
  },

  "create-thread": async (form) => {
    const body = fd(form);
    const payload = { title: body.title };
    if (body.goal) payload.goal = body.goal;
    const objs = selectedValues(form.querySelector("#th-pin-obj"));
    const srcs = selectedValues(form.querySelector("#th-pin-src"));
    if (objs.length) payload.pinned_object_ids = objs;
    if (srcs.length) payload.pinned_source_ids = srcs;
    const t = await api("/projects/" + encodeURIComponent(form.dataset.pid) + "/threads",
      "POST", payload);
    toast("Thread created.");
    location.hash = "#/project/" + form.dataset.pid + "/dialogue/" + t.id;
  },

  "send-turn": async (form) => {
    const body = fd(form);
    const tid = form.dataset.tid;
    const r = await api("/threads/" + encodeURIComponent(tid) + "/turns", "POST",
      { content: body.content });
    form.reset();
    const n = (r.proposed_actions || []).length;
    toast(n ? "Reply received; " + n + " action(s) proposed." : "Reply received.");
    loadTurns(tid);
    loadActions(tid);
  },

  "create-candidate": async (form) => {
    const body = fd(form);
    const payload = {
      title: body.title, paper_type: body.paper_type,
      central_question: body.central_question, thesis: body.thesis,
    };
    if (body.structure) payload.structure = body.structure;
    if (body.audience) payload.audience = body.audience;
    if (body.novelty_caveat) payload.novelty_caveat = body.novelty_caveat;
    if (body.risks) payload.risks = body.risks;
    if (body.missing_work) payload.missing_work = body.missing_work;
    const objs = selectedValues(form.querySelector("#pc-objs"));
    if (objs.length) payload.included_object_ids = objs;
    await api("/projects/" + encodeURIComponent(form.dataset.pid) + "/paper-candidates",
      "POST", payload);
    toast("Paper candidate created.");
    route();
  },

  "generate-candidates": async (form) => {
    const objIds = selectedValues(form.querySelector("#gen-objs"));
    if (!objIds.length) {
      toast("Select at least one research object to generate from.", "err");
      return;
    }
    const body = fd(form);
    const payload = { object_ids: objIds };
    if (body.audience) payload.audience = body.audience;
    if (body.venue_class) payload.venue_class = body.venue_class;
    if (body.constraints) payload.constraints = body.constraints;
    let n = parseInt(body.n, 10);
    if (Number.isNaN(n)) n = 3;
    n = Math.max(1, Math.min(5, n));
    payload.n = n;
    const r = await api("/projects/" + encodeURIComponent(form.dataset.pid) +
      "/paper-candidates/generate", "POST", payload);
    const count = (r && r.candidates) ? r.candidates.length : 0;
    toast("Generated " + count + " candidate(s) (AI-suggested; review them).");
    route();
  },

  "create-manuscript": async (form) => {
    const body = fd(form);
    const payload = { title: body.title };
    if (body.from_candidate_id) payload.from_candidate_id = body.from_candidate_id;
    const m = await api("/projects/" + encodeURIComponent(form.dataset.pid) + "/manuscripts",
      "POST", payload);
    toast("Manuscript created.");
    location.hash = "#/project/" + form.dataset.pid + "/manuscripts/" + m.id;
  },

  "add-section": async (form) => {
    const body = fd(form);
    const payload = { heading: body.heading };
    if (body.purpose) payload.purpose = body.purpose;
    if (body.text) payload.text = body.text;
    if (body.word_budget) payload.word_budget = parseInt(body.word_budget, 10);
    if (body.position !== "" && body.position !== undefined) {
      const pos = parseInt(body.position, 10);
      if (!Number.isNaN(pos)) payload.position = pos;
    }
    const claimIds = selectedValues(form.querySelector("#sec-claims"));
    if (claimIds.length) payload.claim_ids = claimIds;
    await api("/manuscripts/" + encodeURIComponent(form.dataset.mid) + "/sections",
      "POST", payload);
    toast("Section added.");
    route();
  },

  "create-submission": async (form) => {
    const body = fd(form);
    const payload = { manuscript_id: body.manuscript_id };
    if (body.venue_name) payload.venue_name = body.venue_name;
    if (body.deadline) payload.deadline = body.deadline;
    await api("/projects/" + encodeURIComponent(form.dataset.pid) + "/submissions", "POST", payload);
    toast("Submission created.");
    route();
  },

  "create-dataset": async (form) => {
    const body = fd(form);
    const columns = body.columns.split(",").map((c) => c.trim()).filter(Boolean);
    if (!columns.length) throw new Error("Provide at least one column name.");
    const lines = body.rows.split("\n").map((l) => l.trim()).filter(Boolean);
    if (!lines.length) throw new Error("Provide at least one data row.");
    const rows = [];
    for (let i = 0; i < lines.length; i++) {
      const cells = lines[i].split(",").map((c) => {
        const v = c.trim();
        const n = Number(v);
        return (v !== "" && !Number.isNaN(n)) ? n : v;
      });
      if (cells.length !== columns.length) {
        throw new Error("Row " + (i + 1) + " has " + cells.length + " cells but there are " +
          columns.length + " columns.");
      }
      rows.push(cells);
    }
    await api("/projects/" + encodeURIComponent(form.dataset.pid) + "/datasets", "POST",
      { name: body.name, columns, rows });
    toast("Dataset created.");
    route();
  },

  "render-figure": async (form) => {
    const body = fd(form);
    const spec = { kind: body.kind };
    if (body.x) spec.x = body.x;
    const series = (body.series || "").split(",").map((s) => s.trim()).filter(Boolean);
    if (series.length) spec.series = series;
    if (body.xlabel) spec.xlabel = body.xlabel;
    if (body.ylabel) spec.ylabel = body.ylabel;
    const payload = { title: body.title, dataset_id: body.dataset_id, spec };
    const gs = form.querySelector('[name="grayscale"]');
    if (gs && gs.checked) payload.grayscale = true;
    await api("/projects/" + encodeURIComponent(form.dataset.pid) + "/figures", "POST", payload);
    toast("Figure rendered.");
    route();
  },

  "build-table": async (form) => {
    const body = fd(form);
    const payload = { title: body.title, dataset_id: body.dataset_id };
    const cols = (body.columns || "").split(",").map((c) => c.trim()).filter(Boolean);
    if (cols.length) payload.columns = cols;
    await api("/projects/" + encodeURIComponent(form.dataset.pid) + "/tables", "POST", payload);
    toast("Table built.");
    route();
  },

  "add-revision": async (form) => {
    const body = fd(form);
    const payload = {
      summary: body.summary,
      response_to_reviewers: body.response_to_reviewers,
    };
    if (body.changes) {
      const changes = body.changes.split("\n").map((c) => c.trim()).filter(Boolean);
      if (changes.length) payload.changes = changes;
    }
    await api("/submissions/" + encodeURIComponent(form.dataset.sid) + "/revisions", "POST", payload);
    toast("Revision added.");
    route();
  },

  "auth-login": async (form) => {
    const body = fd(form);
    const pwEl = form.querySelector('[name="password"]');
    const password = pwEl ? pwEl.value : "";
    const r = await api("/auth/login", "POST", { email: body.email, password });
    if (!r || !r.access_token) throw new Error("Login failed: no access token returned.");
    try { localStorage.setItem("wb_token", r.access_token); } catch (_e) { /* ignore */ }
    toast("Signed in.");
    location.reload();
  },

  "auth-register": async (form) => {
    const body = fd(form);
    const pwEl = form.querySelector('[name="password"]');
    const password = pwEl ? pwEl.value : "";
    await api("/auth/register", "POST", { name: body.name, email: body.email, password });
    const r = await api("/auth/login", "POST", { email: body.email, password });
    if (!r || !r.access_token) throw new Error("Registered, but auto-login failed.");
    try { localStorage.setItem("wb_token", r.access_token); } catch (_e) { /* ignore */ }
    toast("Registered and signed in.");
    location.reload();
  },

  "ms-export": async (form) => {
    const formats = Array.from(form.querySelectorAll('input[name="fmt"]:checked'))
      .map((c) => c.value);
    if (!formats.length) throw new Error("Pick at least one export format.");
    const box = document.getElementById("ms-results");
    if (box) box.innerHTML = loadingHTML("Exporting…");
    try {
      const data = await api("/manuscripts/" + encodeURIComponent(form.dataset.mid) + "/export",
        "POST", { formats });
      renderExport(data);
      toast("Export written to " + data.out_dir);
    } catch (e) {
      if (box) box.innerHTML = errorHTML(e.message);
      throw e;
    }
  },
};

/* ===================== event delegation: changes ===================== */

const changeActions = {
  "ws-select": (t) => {
    state.workspaceId = t.value || null;
    if (t.value) renderProjects(t.value);
    else {
      const area = document.getElementById("pr-area");
      if (area) area.innerHTML = emptyHTML("Select a workspace to see its projects.");
    }
  },

  "claim-source": (t) => loadClaimExcerpts(t.value),

  "pick-excerpt": (t) => {
    if (t.checked) state.pickedExcerpts.set(t.value, t.dataset.label || t.value);
    else state.pickedExcerpts.delete(t.value);
    renderPickedChips();
  },
};

/* ===================== wiring ===================== */

document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-action]");
  if (!t) return;
  const fn = clickActions[t.dataset.action];
  if (fn) { e.preventDefault(); fn(t); }
});

document.addEventListener("submit", (e) => {
  const form = e.target.closest("form[data-form]");
  if (!form) return;
  e.preventDefault();
  const fn = formActions[form.dataset.form];
  if (!fn) return;
  const btn = form.querySelector('button[type="submit"]');
  withBusy(btn, async () => {
    try { await fn(form); } catch (err) { toast(err.message, "err"); }
  });
});

document.addEventListener("change", (e) => {
  const t = e.target.closest("[data-change]");
  if (!t) return;
  const fn = changeActions[t.dataset.change];
  if (fn) fn(t);
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const modal = document.getElementById("auth-modal");
  if (modal && !modal.hidden) closeAuthModal();
});

window.addEventListener("hashchange", route);
loadHealth().then(loadAuth);
route();
