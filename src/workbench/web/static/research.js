/* Delegated research UI. All returned text is escaped; reports are never executed. */
"use strict";

function researchTitle(question) {
  const text = question.replace(/\s+/g, ' ');
  return esc(text.length > 150 ? text.slice(0, 150) + '…' : text);
}

function researchSynthesis(synthesis) {
  const items = (values) => values?.length ? '<ul>' + values.map(value => '<li>' + esc(value) + '</li>').join('') + '</ul>' : '<p class="dim">None recorded.</p>';
  return '<h3>Parent synthesis</h3><p>' + esc(synthesis.summary || 'Awaiting saved work.') + '</p>' +
    '<h4>Agreements reported by the parent</h4>' + items(synthesis.agreements) +
    '<h4>Conflicts reported by the parent</h4>' + items(synthesis.conflicts) +
    (synthesis.comparisons || []).map(group => '<details' + (group.state === 'conflict_or_scope_difference' ? ' open' : '') +
      '><summary>' + esc(group.claim_key) + ' · ' + esc(group.state.replaceAll('_', ' ')) + '</summary><ul>' +
      group.findings.map(f => '<li>' + esc(f.statement) + ' <span class="dim">(' + esc(f.category.replaceAll('_', ' ')) +
        '; scope: ' + esc(f.scope) + '; agent ' + esc(f.agent_id.slice(0, 8)) + ')</span></li>').join('') + '</ul></details>').join('') +
    '<h4>Open questions</h4>' + items(synthesis.unresolved_questions) +
    '<details><summary>Full synthesis and report references</summary><pre>' + esc(JSON.stringify(synthesis, null, 2)) + '</pre></details>';
}

async function tabResearch(el, pid, sub) {
  const base = "/projects/" + encodeURIComponent(pid) + "/research-tasks";
  const terminal = new Set(["completed", "limit_reached_partial", "failed_partial",
    "cancelled_partial", "interrupted_partial"]);
  if (sub[0] === 'manuscript-path') {
    const root = '/projects/' + encodeURIComponent(pid);
    const path = await api(root + '/manuscript-path');
    el.innerHTML = '<h2>Path to manuscript</h2><p>Stages reflect recorded evidence. Model findings require human review; exports do not advance approval gates.</p>' +
      '<div class="actions"><button data-path-download="/manuscript-path/download">Export path</button> ' +
      '<button data-path-download="/research-artifacts/download">Download private artifact package</button></div>' +
      '<p class="notice">The complete package preserves original provenance and may contain private metadata. Only the sanitized results PDF is intended for sharing after your review.</p>' +
      path.stages.map(stage => '<section><h3>' + esc(stage.label) + ' · ' + esc(stage.state) + '</h3>' +
        '<ul>' + stage.evidence.map(item => '<li><a data-path-evidence href="' + esc(item.url) + '">' + esc(item.label) + '</a></li>').join('') + '</ul>' +
        '<p>Blockers: ' + esc(stage.blockers.join('; ') || 'None recorded for this stage.') + '</p>' +
        '<p>Next action: ' + esc(stage.next_action) + '</p></section>').join('') +
      '<p id="path-message" role="status"></p><details id="path-evidence"><summary>Selected evidence</summary><pre></pre></details>';
    el.querySelectorAll('[data-path-evidence]').forEach(link => link.addEventListener('click', async event => {
      event.preventDefault();
      try {
        if (link.getAttribute('href').endsWith('/download')) {
          await researchDownload(link.getAttribute('href'), 'evidence.zip');
          return;
        }
        const evidence = await api(link.getAttribute('href'));
        const detail = el.querySelector('#path-evidence');
        detail.querySelector('pre').textContent = JSON.stringify(evidence, null, 2);
        detail.open = true; detail.scrollIntoView({block: 'nearest'});
      } catch (error) { el.querySelector('#path-message').textContent = error.message; }
    }));
    el.querySelectorAll('[data-path-download]').forEach(button => button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        const suffix = button.dataset.pathDownload;
        await researchDownload(root + suffix, suffix.includes('research-artifacts') ? 'research-artifacts.zip' : 'path-to-manuscript.md');
      } catch (error) { el.querySelector('#path-message').textContent = error.message; }
      finally { button.disabled = false; }
    }));
    return;
  }
  if (!sub.length) {
    const [tasks, executors, sources] = await Promise.all([
      api(base), api("/projects/" + pid + "/research-executors"), api("/projects/" + pid + "/sources"),
    ]);
    el.innerHTML = '<h2>Delegated research</h2><p><a href="#/project/' + esc(pid) + '/research/manuscript-path">Path to manuscript and artifact package</a></p><p>Create a bounded question, attach documents, and review the returned evidence before using it in a manuscript.</p>' +
      '<p class="notice">Offline mode exercises separate parent and child worker processes. It performs no model research. Live delegation requires a separately configured agent executor; text-only chat cannot delegate.</p>' +
      '<ul>' + tasks.map(t => '<li><a href="#/project/' + esc(pid) + '/research/' + esc(t.id) + '">' +
        researchTitle(t.question) + '</a> — ' + esc((t.task_type || 'research').replaceAll('_', ' ')) + ' · ' + esc(t.state.replaceAll('_', ' ')) + ' · ' + esc(t.executor) + '</li>').join("") + '</ul>' +
      '<form id="research-create" class="stack"><div class="field"><label>Research question<textarea name="question" required maxlength="24000"></textarea></label></div>' +
      '<div class="field"><label>Task type<select name="task_type"><option value="research">General research</option><option value="literature_search">Literature search</option><option value="proof_audit">Independent proof audit</option></select></label></div>' +
      '<div class="field"><label>Success criteria<textarea name="success_criteria" placeholder="Optional — use the default evidence and open-questions checklist"></textarea></label></div>' +
      '<div class="field"><label>Instructions<textarea name="instructions" placeholder="Optional — use bounded research and evidence safeguards"></textarea></label></div>' +
      '<fieldset><legend>Deliverables (default: research report and evidence package)</legend>' +
      ['research_report', 'paper', 'reviewer_report'].map(name => '<label><input type="checkbox" name="deliverables" value="' + name + '"> ' + esc(name.replaceAll('_', ' ')) + '</label>').join(' ') + '</fieldset>' +
      '<details><summary>Select existing ingested documents (optional)</summary><fieldset><legend>Project sources</legend>' + (sources.length ? sources.map(s =>
        '<label><input type="checkbox" name="source_ids" value="' + esc(s.id) + '"> ' + esc(s.title) + ' · ' + esc(s.id.slice(0, 8)) + '</label><br>').join('') : '<p>No sources yet. You can upload after creating the task.</p>') + '</fieldset></details>' +
      '<div class="field"><label>Task-wide token limit<input name="token_limit" type="number" value="24000" min="2000" max="1000000" required></label></div>' +
      '<div class="field"><label>Time limit (seconds)<input name="time_limit_seconds" type="number" value="600" min="10" max="7200" required></label></div>' +
      '<div class="field"><label>Maximum child agents<input name="max_children" type="number" value="3" min="1" max="6" required></label></div>' +
      '<p class="small-text dim">20% of tokens and 10% of time are reserved for the final handoff. Missing usage is conservatively charged as the full allowance and labelled an estimate.</p>' +
      '<div class="field"><label>Executor<select name="executor"><option value="offline">Offline controlled workers — no model research</option><option value="process"' +
      (executors.process.available ? '' : ' disabled') + '>Configured live agent executor</option></select></label></div>' +
      '<label><input type="checkbox" name="allow_best_effort_tokens"> Permit a live worker with best-effort token stopping. In-flight model work may exceed the displayed token limit; the time limit still stops the local worker.</label>' +
      '<button type="submit" class="primary">Create research task</button></form><p id="research-message" role="status"></p>';
    const createForm = el.querySelector('#research-create');
    createForm.elements.question.closest('.field').insertAdjacentHTML('afterend',
      '<label><input type="checkbox" name="reuse_prior_research" checked> Retrieve saved project evidence and prior research</label>' +
      '<label>Matching method<select name="retrieval_mode"><option value="hybrid">Semantic + lexical (local model)</option><option value="lexical">Lexical only</option></select></label>' +
      '<label>Discovery breadth<select name="retrieval_recall"><option value="broad">Broad — include weaker semantic leads</option><option value="focused">Focused — stronger semantic matches</option></select></label>' +
      '<p class="small-text dim">For blind audits, disable prior research reuse. Semantic matching requires a local index; it never sends source text to an embedding API.</p>' +
      '<button type="button" id="research-index">Build / refresh local semantic index</button>' +
      '<div class="field"><label>Coverage topics (one per line, up to 12)<textarea name="coverage_topics" placeholder="Separate questions or methods to cover"></textarea></label></div>' +
      '<button type="button" id="research-retrieve">Preview relevant evidence and gaps</button><div id="research-retrieval" role="status"></div>');
    el.querySelector('#research-index').addEventListener('click', async event => {
      const button = event.currentTarget; button.disabled = true;
      const target = el.querySelector('#research-retrieval');
      target.textContent = 'Building a bounded batch of local embeddings…';
      try {
        const result = await api('/projects/' + encodeURIComponent(pid) + '/research-retrieval/index', 'POST', {});
        target.textContent = result.embedded_now + ' items indexed; ' + result.reused + ' reused; ' +
          result.remaining + ' remain. ' + (result.remaining ? 'Refresh again to process the next batch. ' : '') +
          'Local model: ' + result.model;
      } catch (error) { target.textContent = error.message; }
      finally { button.disabled = false; }
    });
    el.querySelector('#research-retrieve').addEventListener('click', async event => {
      const button = event.currentTarget, form = createForm;
      button.disabled = true;
      const target = el.querySelector('#research-retrieval');
      try {
        const result = await api('/projects/' + encodeURIComponent(pid) + '/research-retrieval', 'POST', {
          query: form.elements.question.value,
          mode: form.elements.retrieval_mode.value,
          recall: form.elements.retrieval_recall.value,
          topics: form.elements.coverage_topics.value.split('\n').map(s => s.trim()).filter(Boolean),
        });
        target.innerHTML = '<p>' + result.cards.length + ' distinct items selected; ' + result.scan.exact_duplicates_removed +
          ' exact duplicates removed. ' + esc(result.limitations) + '</p>' +
          '<p>Semantic matching: ' + esc(result.semantic.status.replaceAll('_', ' ')) +
          (result.semantic.reason ? ' · ' + esc(result.semantic.reason) : '') +
          '. Possible overlaps among selected items: ' + result.potential_overlap.length + ' (not proof of equivalence).</p>' +
          (result.scan.scan_limited || result.selection_limited ? '<p>Scan or selection limits apply; omitted evidence may remain relevant.</p>' : '') +
          result.coverage.map(c => '<p>' + esc(c.topic) + ': ' + c.matching_card_ids.length + ' retrieved matches (not verified coverage)</p>').join('') +
          result.cards.map(c => '<details><summary>' + esc(c.kind.replaceAll('_', ' ')) +
            (c.origins[0]?.title ? ': ' + esc(c.origins[0].title) : '') + ' · ' + esc(c.evidence_status) +
            (c.match?.weak_semantic_lead ? ' · weak semantic lead' : c.match?.semantic ? ' · semantic match' : '') +
            '</summary>' + c.origins.filter(o => o.original_url).map(o =>
              '<p>PDF page ' + esc((o.pdf_pages || []).join(', ') || 'unknown') +
              ' <button type="button" data-pdf-source="' + esc(o.source_id) + '" data-pdf-page="' +
              esc(o.pdf_pages?.[0] || 1) + '">Open original PDF</button>' +
              (o.quality_issues?.length ? ' · Possible text damage: ' + esc(o.quality_issues.join(', ')) : '') +
              '. Check formulas on the original page before citing.</p>').join('') +
            '<pre>' + esc(c.text) + '</pre><pre>' + esc(JSON.stringify(c.origins, null, 2)) + '</pre></details>').join('');
        target.querySelectorAll('[data-pdf-source]').forEach(link => link.addEventListener('click', async () => {
          try {
            await researchOpenPdf('/projects/' + encodeURIComponent(pid) + '/sources/' +
              encodeURIComponent(link.dataset.pdfSource) + '/original', Number(link.dataset.pdfPage));
          } catch (error) { el.querySelector('#research-message').textContent = error.message; }
        }));
      } catch (error) { target.textContent = error.message; }
      finally { button.disabled = false; }
    });
    el.querySelector('#research-create').addEventListener('submit', async event => {
      event.preventDefault();
      const form = event.currentTarget, data = new FormData(form);
      const button = form.querySelector('button[type="submit"]'); button.disabled = true;
      try {
        const body = Object.fromEntries(data);
        body.deliverables = data.getAll('deliverables'); body.source_ids = data.getAll('source_ids');
        body.allow_best_effort_tokens = data.has('allow_best_effort_tokens');
        body.reuse_prior_research = data.has('reuse_prior_research');
        body.coverage_topics = data.get('coverage_topics').split('\n').map(s => s.trim()).filter(Boolean);
        for (const key of ['token_limit', 'time_limit_seconds', 'max_children']) body[key] = Number(body[key]);
        const task = await api(base, 'POST', body);
        location.hash = '#/project/' + pid + '/research/' + task.id;
      } catch (error) { el.querySelector('#research-message').textContent = error.message; }
      finally { button.disabled = false; }
    });
    return;
  }
  const url = base + '/' + encodeURIComponent(sub[0]);
  const task = await api(url);
  if (!el.isConnected) return;
  const finished = terminal.has(task.state), draft = task.state === 'draft';
  const usage = task.ledger;
  const needsManuscriptTarget = Object.values(task.reviews).some(r => r.purpose === 'manuscript' && r.decision === 'approved' && !r.promotion);
  const manuscripts = needsManuscriptTarget ? (await api('/projects/' + pid + '/objects')).filter(o => o.kind === 'manuscript') : [];
  el.innerHTML = '<a href="#/project/' + esc(pid) + '/research">All research tasks</a><h2>' + researchTitle(task.contract.question) + '</h2>' +
    '<p role="status"><strong>' + esc(task.state) + '</strong> · ' + esc(task.contract.executor === 'offline' ? 'OFFLINE SIMULATION' : 'Configured agent executor') + '</p>' +
    '<p>Actual reported tokens: ' + esc(usage.actual_tokens ?? 0) + ' · Estimated reservation: ' + esc(usage.estimated_tokens ?? 0) +
    ' · Task limit: ' + esc(task.contract.token_limit) + ' · Time limit: ' + esc(task.contract.time_limit_seconds) + ' seconds</p>' +
    '<p>Token stopping: ' + esc(usage.token_limit_mode || 'pending worker capability') +
    (usage.token_limit_mode === 'best_effort' ? ' · An in-flight Codex turn can exceed the limit before usage arrives.' : '') + '</p>' +
    '<progress aria-label="Task token allowance charged" value="' + esc(usage.charged_tokens || 0) + '" max="' + esc(task.contract.token_limit) + '"></progress>' +
    '<p>Handoff reserve: ' + esc(task.contract.handoff_token_reserve) + ' tokens / ' + esc(task.contract.handoff_time_reserve_seconds) + ' seconds. ' +
    (usage.deadline ? 'Deadline: ' + esc(new Date(usage.deadline).toLocaleString()) + '.' +
      (!finished ? ' Remaining: ' + Math.max(0, Math.ceil((new Date(usage.deadline) - Date.now()) / 1000)) + ' seconds.' : '') : '') + '</p>' +
    (finished ? '<p class="notice">Research has stopped. ' + esc(usage.stop_reason || '') + ' The package contains work saved before the cutoff. A stopped task cannot resume.</p>' : '') +
    '<div class="actions"><button data-r-action="download">Download ' + (finished ? 'result' : 'checkpoint') + ' ZIP</button> ' +
    '<button data-r-action="pdf">Download results PDF</button> <a href="#/project/' + esc(pid) + '/research/manuscript-path">Path to manuscript</a> ' +
    (!finished ? '<button data-r-action="cancel">Cancel research</button>' : '') +
    ' <a href="#/project/' + esc(pid) + '/dialogue/' + esc(task.thread_id) + '">Task dialogue</a></div>' +
    '<details><summary>Task contract</summary><pre>' + esc(JSON.stringify(task.contract, null, 2)) + '</pre></details>' +
    (task.contract.retrieval ? '<details><summary>Retrieved evidence and coverage assignments (' +
      task.contract.retrieval.cards.length + ' items)</summary><p>Each item has one follow-up owner. Shared sources and overlapping methods may still require review. Prior findings do not count as independent verification.</p><pre>' +
      esc(task.contract.retrieval.coverage.map(c => c.topic + ': ' + c.matching_card_ids.length +
        ' retrieved matches (coverage not verified)').join('\n') || 'No separate coverage topics supplied.') + '</pre><ul>' +
      Object.entries(task.ledger.retrieval_allocation || {}).map(([key, cards]) => '<li>' + esc(key) + ': ' +
        cards.length + ' assigned evidence items</li>').join('') + '</ul>' +
      (!task.ledger.retrieval_allocation ? '<p>Follow-up owners will be assigned when the plan is saved.</p>' : '') + '</details>' : '') +
    '<details><summary>Source versions and hashes (' + task.sources.length + ')</summary><ul>' + task.sources.map(s => '<li>' + esc(s.title || s.name) + ' · ' + esc(s.version) +
      ' · SHA-256 ' + esc(s.sha256) + (s.context_truncated ? ' · Extracted context is truncated' : '') + '</li>').join('') + '</ul></details>' +
    (draft ? '<form id="research-attach" class="stack"><label>Documents or ZIPs<input type="file" name="files" multiple required accept=".zip,.pdf,.tex,.md,.txt,.bib,.csv,.json,.py,.html,.yaml,.yml"></label>' +
      '<label>Version label<input name="version" value="unspecified" maxlength="200" required></label><button type="submit">Attach sources</button></form>' +
      '<p class="small-text dim">ZIPs are inspected with path, member-count and expansion limits. Attached scripts are retained as text and never executed. Versions are user-declared; “latest” is never inferred.</p>' +
      (task.contract.executor !== 'offline' ? '<label><input id="research-live-ack" type="checkbox"> I authorize the configured live executor within this task’s limits.</label>' : '') +
      '<button class="primary" data-r-action="start">Start bounded research</button>' : '') +
    '<h3>Agent lineage and original reports</h3>' + task.agents.map(a => '<details><summary>' + esc(a.role) + ' ' + esc(a.id) +
      ' · ' + esc(a.state) + ' · parent ' + esc(a.parent_id || 'none') + '</summary><pre>' + esc(JSON.stringify(a, null, 2)) + '</pre></details>').join('') +
    researchSynthesis(task.synthesis) +
    (finished ? '<h3>Human review</h3><p>“Verified result” is the child’s assessment within its stated scope. Review the original evidence and any conflicts. Approval is bound to this exact snapshot and intended use.</p>' +
      task.agents.filter(a => a.role === 'child').flatMap(a => (a.report.findings || []).map(f =>
        '<form class="stack research-review" data-agent="' + esc(a.id) + '" data-finding="' + esc(f.id) + '"><h4>' + esc(f.category) + '</h4><p>' + esc(f.statement) + '</p><p>Scope: ' + esc(f.scope) + '</p>' +
        '<label>Intended use<select name="purpose"><option value="finding">Research finding</option><option value="proof">Claim of proof</option><option value="novelty">Scoped novelty assessment</option><option value="manuscript">Manuscript text</option></select></label>' +
        '<label>Review note, evidence checked and scope<textarea name="note" required maxlength="24000"></textarea></label>' +
        '<label>Decision<select name="decision"><option value="rejected">Needs further work / reject</option><option value="approved"' + (task.contract.executor === 'offline' ? ' disabled' : '') + '>Approve this use (live evidence only)</option></select></label><button type="submit">Record review</button></form>')).join('') +
      '<h4>Recorded reviews</h4>' + Object.entries(task.reviews).map(([key, r]) => '<div><pre>' + esc(JSON.stringify(r, null, 2)) + '</pre>' +
        (r.decision === 'approved' && !r.promotion ? (r.purpose === 'manuscript' ? '<label>Target manuscript<select name="manuscript_id"><option value="">Select a manuscript</option>' + manuscripts.map(m => '<option value="' + esc(m.id) + '">' + esc(m.title) + '</option>').join('') + '</select></label>' : '') + '<button data-r-action="promote" data-review="' + esc(key) + '">Promote approved finding</button>' : '') + '</div>').join('') : '') +
    '<p id="research-message" role="status"></p>';
  const message = el.querySelector('#research-message');
  const attach = el.querySelector('#research-attach');
  if (attach) attach.addEventListener('submit', async event => {
    event.preventDefault(); const button = attach.querySelector('button'); button.disabled = true;
    try {
      for (const file of attach.elements.files.files) {
        const body = new FormData(); body.append('file', file); body.append('version', attach.elements.version.value);
        const response = await fetch(url + '/attachments', {method: 'POST', headers: authHeaders('POST'), body});
        if (!response.ok) { const error = await response.json(); throw new Error(error.detail || 'Upload failed'); }
      }
      await tabResearch(el, pid, sub);
    } catch (error) { message.textContent = error.message; button.disabled = false; }
  });
  el.querySelectorAll('.research-review').forEach(form => form.addEventListener('submit', async event => {
    event.preventDefault(); const button = form.querySelector('button'); button.disabled = true;
    try {
      await api(url + '/reviews', 'POST', {...Object.fromEntries(new FormData(form)), agent_id: form.dataset.agent,
        finding_id: form.dataset.finding, expected_hash: task.review_hash});
      await tabResearch(el, pid, sub);
    } catch (error) { message.textContent = error.message; button.disabled = false; }
  }));
  el.querySelectorAll('[data-r-action]').forEach(button => button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      const action = button.dataset.rAction;
      if (action === 'download' || action === 'pdf') {
        await researchDownload(url + (action === 'pdf' ? '/results.pdf' : '/download'),
          'research-task-' + task.id + (action === 'pdf' ? '.pdf' : '.zip'));
      } else if (action === 'start') {
        await api(url + '/start', 'POST', {acknowledge_live_execution: !!el.querySelector('#research-live-ack')?.checked});
      } else if (action === 'promote') {
        const [agent_id, finding_id, purpose] = button.dataset.review.split(':');
        let manuscript_id = null;
        if (purpose === 'manuscript') {
          manuscript_id = button.parentElement.querySelector('select[name="manuscript_id"]').value;
          if (!manuscript_id) throw new Error('Select a target manuscript first.');
        }
        await api(url + '/promote', 'POST', {agent_id, finding_id, purpose, manuscript_id, expected_hash: task.review_hash});
      } else await api(url + '/cancel', 'POST');
      if (action !== 'download' && action !== 'pdf') await tabResearch(el, pid, sub);
    } catch (error) { message.textContent = error.message; }
    finally { button.disabled = false; }
  }));
  if (!draft && !finished) {
    const hash = location.hash;
    setTimeout(() => { if (el.isConnected && location.hash === hash) tabResearch(el, pid, sub).catch(error => {
      if (message.isConnected) message.textContent = error.message;
    }); }, 1500);
  }
}

async function researchDownload(url, filename) {
  const response = await fetch(url, {headers: authHeaders('GET')});
  if (!response.ok) throw new Error('Could not download the research artifact.');
  const blob = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href = blob; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(blob), 1000);
}

async function researchOpenPdf(url, page) {
  const viewer = window.open('', '_blank');
  if (!viewer) throw new Error('Allow a new tab to view the original PDF.');
  viewer.opener = null;
  try {
    const response = await fetch(url, {headers: authHeaders('GET')});
    if (!response.ok) throw new Error('Original PDF is unavailable or failed its integrity check.');
    const blob = URL.createObjectURL(await response.blob());
    viewer.location.href = blob + '#page=' + (Number.isSafeInteger(page) && page > 0 ? page : 1);
    setTimeout(() => URL.revokeObjectURL(blob), 60000);
  } catch (error) { viewer.close(); throw error; }
}
