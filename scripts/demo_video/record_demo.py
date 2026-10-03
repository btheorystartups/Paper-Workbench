"""Capture real UI actions against the explicitly synthetic loopback demo."""

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

OUT = None
BROWSER = None
BASE = PID = MID = TID = MS = None
RECORDING_FALLBACKS = []
RECORDING_AVAILABLE = True
SESSION = "wb-demo-video"
CALLOUTS = []
CAPTURE_CALLOUTS = False
ORIGINAL = (
    "The pilot measured a 12% improvement across ten runs. "
    "This small experiment does not establish general applicability."
)
PROPOSED = (
    "Across ten pilot runs, we observed a 12% improvement. "
    "These preliminary findings need replication before broader conclusions can be drawn."
)
REVISED = (
    "Across ten pilot runs, we observed a 12% improvement. "
    "The small sample limits generalizability; independent replication is needed."
)


def browser(*args, script=None):
    # Browser daemons can inherit pipe handles on Windows. File-backed capture avoids
    # waiting for descendant processes to close stdout after the CLI has exited.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stdout:
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr:
            p = subprocess.run(
                [BROWSER, "--session", SESSION, *args],
                env={**os.environ, "AGENT_BROWSER_HOME": str(Path(BROWSER).resolve().parent.parent)},
                input=script or "",
                encoding="utf-8",
                errors="replace",
                stdout=stdout,
                stderr=stderr,
                timeout=60,
            )
            stdout.seek(0)
            stderr.seek(0)
            output = stdout.read()
            if p.returncode:
                raise RuntimeError(output + stderr.read())
            return output


def js(code):
    return browser("eval", "--stdin", script=code)


def api(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as response:
        return json.load(response)


def scroll(selector, block="center"):
    js(
        f"document.querySelector({json.dumps(selector)}).scrollIntoView({{block:{json.dumps(block)},behavior:'smooth'}})"
    )
    time.sleep(0.7)


def click(selector):
    scroll(selector)
    browser("click", selector)
    time.sleep(0.8)


def details(label):
    js(
        "[...document.querySelectorAll('summary')].find(e=>e.textContent.trim()==="
        + json.dumps(label)
        + ").click()"
    )
    time.sleep(0.4)


def shot(name):
    browser("screenshot", str(OUT / f"{name}.png"))


def cue(chapter, phrase, selector, label):
    """Capture the actual element and its bounds together, before its state changes."""
    if not CAPTURE_CALLOUTS:
        return
    scroll(selector)
    result = json.loads(
        js(
            """(() => {
      const e = document.querySelector(SELECTOR);
      const r = e.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0 || r.top < 48 || r.bottom > innerHeight)
        throw new Error('Callout target must be fully visible');
      return {box: [r.x, r.y, r.width, r.height], text: e.textContent.trim(),
              disabled: Boolean(e.disabled), viewport: [innerWidth, innerHeight]};
    })()""".replace("SELECTOR", json.dumps(selector))
        )
    )
    name = f"cue-{len(CALLOUTS):02}"
    shot(name)
    CALLOUTS.append(
        {
            "chapter": chapter,
            "phrase": phrase,
            "label": label,
            "image": name + ".png",
            "selector": selector,
            **result,
        }
    )
    (OUT / "callouts.json").write_text(json.dumps(CALLOUTS, indent=2), encoding="utf-8")


def start(name, url):
    browser("open", url)
    time.sleep(0.5)
    if RECORDING_AVAILABLE:
        browser("record", "start", str(OUT / f"{name}.webm"))
    else:
        RECORDING_FALLBACKS.append(name)
    time.sleep(0.6)
    print("Recording", name, flush=True)


def stop(name):
    global RECORDING_AVAILABLE
    time.sleep(1.2)
    shot(name)
    try:
        if RECORDING_AVAILABLE:
            browser("record", "stop")
    except RuntimeError as error:
        if "ffmpeg failed" not in str(error):
            raise
        # Preserve the verified real UI frame when the recorder's own encoder fails.
        # The renderer reads this explicit record instead of using a partial WebM.
        RECORDING_FALLBACKS.append(name)
        RECORDING_AVAILABLE = False
        print(f"Recorder encoding failed for {name}; using captured screenshot.", flush=True)
    print("Captured", name, flush=True)


def section_text():
    return next(o for o in api(f"/projects/{PID}/objects") if o["kind"] == "section")["body"]["text"]


def parse_demo_url(url):
    parts = urlsplit(url)
    match = re.fullmatch(r"/project/([a-f0-9]{32})/manuscripts/([a-f0-9]{32})/([a-f0-9]{32})", parts.fragment)
    if (
        parts.scheme != "http"
        or parts.hostname != "127.0.0.1"
        or parts.username
        or parts.password
        or parts.query
        or parts.path != "/ui/"
        or not match
    ):
        raise ValueError("Use the exact loopback URL printed by preview_manuscript_chat.py")
    return f"http://{parts.netloc}", *match.groups()


def main():
    global OUT, BROWSER, BASE, PID, MID, TID, MS, RECORDING_AVAILABLE, SESSION, CAPTURE_CALLOUTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-url", required=True)
    parser.add_argument("--agent-browser", required=True, help="Path to agent-browser 0.27.0 executable")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--session", default="wb-demo-video")
    parser.add_argument("--callouts", action="store_true", help="Capture phrase-linked UI highlights.")
    parser.add_argument(
        "--screenshots-only",
        action="store_true",
        help="Exercise the UI and capture verified frames without the browser video encoder.",
    )
    args = parser.parse_args()
    BASE, PID, MID, TID = parse_demo_url(args.demo_url)
    MS = args.demo_url
    OUT = args.output_dir.resolve()
    BROWSER = args.agent_browser
    SESSION = args.session
    RECORDING_AVAILABLE = not args.screenshots_only
    CAPTURE_CALLOUTS = args.callouts
    health = api("/health")
    if health["provider_mode"] != "fake" or health["auth_required"] or health["deployment_mode"] != "local":
        raise SystemExit("Capture requires the isolated, unauthenticated, fake-provider local demo.")
    sources = api(f"/projects/{PID}/sources")
    if (
        len(sources) != 1
        or sources[0]["title"] != "Synthetic pilot observations"
        or section_text() != ORIGINAL
    ):
        raise SystemExit("Capture requires a fresh synthetic preview fixture.")
    OUT.mkdir(parents=True, exist_ok=True)
    if list(OUT.glob("*.webm")):
        raise SystemExit("Choose an output directory without existing recordings.")
    try:
        browser("open", MS)
        capture()
    finally:
        browser("close")


def capture():
    browser("set", "viewport", "1600", "760")
    start("01-sources", f"{BASE}/ui/#/project/{PID}/sources")
    cue("01-sources", "In Sources", "#src-h", "Sources")
    cue("01-sources", "register the material", "#src-title", "Register source")
    cue("01-sources", "ingest a supported local file", "#ing-path", "Ingest a local file")
    cue("01-sources", "Record its access level", "#src-access", "Access level")
    cue("01-sources", "acquisition details", "#src-acq", "Acquisition note")
    cue("01-sources", "Open the source", '[data-action="open-source"]', "Open source")
    click('[data-action="open-source"]')
    cue("01-sources", "inspect captured excerpts", "#excerpt-list", "Excerpt and locator")
    js("window.scrollTo({top:200,behavior:'smooth'})")
    stop("01-sources")

    start("02-claims", f"{BASE}/ui/#/project/{PID}/claims")
    cue("02-claims", "In Claims", '[data-action="open-claim"]', "Claim")
    cue("02-claims", "The support state", "tbody tr td:nth-child(2)", "Support state")
    click('[data-action="open-claim"]')
    cue("02-claims", "Opening this claim", "#evidence-list", "Linked evidence")
    js("window.scrollTo({top:0,behavior:'smooth'})")
    stop("02-claims")

    start("03-manuscript", MS)
    cue("03-manuscript", "a heading", "#sec-heading", "Section heading")
    cue("03-manuscript", "purpose", "#sec-purpose", "Purpose")
    cue("03-manuscript", "word budget", "#sec-budget", "Word budget")
    cue("03-manuscript", "linked claims", "#sec-claims", "Linked claims")
    cue("03-manuscript", "Our Discussion section", ".section-item", "Discussion and limitations")
    cue("03-manuscript", "Choose Discuss section", '[data-action="chat-section"]', "Discuss section")
    click('[data-action="chat-section"]')
    cue("03-manuscript", "The current section appears", "#chat-section-text", "Current section")
    scroll(".manuscript-chat", "start")
    stop("03-manuscript")

    start("04-brief", MS)
    details("Research brief")
    browser(
        "fill",
        "#thread-brief",
        "Question: What does the pilot support? Audience: methods researchers. "
        "Preserve the ten-run limitation. "
        "Do not invent citations or generalize the result. Next: plan independent replication.",
    )
    cue("04-brief", "Use Research brief", "#thread-brief", "Research brief")
    cue("04-brief", "Save it", '[data-form="thread-brief"] button', "Save brief")
    cue("04-brief", "Here we explicitly preserve", "#thread-brief", "Keep the limitations in the brief")
    click('[data-form="thread-brief"] button')
    details("Context for the next reply")
    scroll(".context-panel", "start")
    js("document.querySelector('#chat-context details').open=true")
    cue(
        "04-brief",
        "Open Context for the next reply",
        ".context-panel > summary",
        "Context for the next reply",
    )
    cue("04-brief", "manuscript outline", "#chat-context details:nth-child(1)", "Manuscript outline")
    cue("04-brief", "selected section", "#chat-context details:nth-child(2) > summary", "Selected section")
    cue("04-brief", "linked claims", "#chat-context details:nth-child(3) > summary", "Linked claim")
    cue("04-brief", "available evidence", "#chat-context details:nth-child(5) > summary", "Available excerpt")
    stop("04-brief")
    assert "independent replication" in api(f"/threads/{TID}/context")["system_prompt"]

    start("05-dialogue", MS)
    browser("select", "#th-mode", "challenge")
    cue("05-dialogue", "Use conversation modes", "#th-mode", "Conversation mode: challenge")
    browser(
        "fill",
        "#turn-input",
        "What would a skeptical reviewer challenge about this paragraph? "
        "Separate supported observations from assumptions.",
    )
    cue("05-dialogue", "A useful prompt", "#turn-input", "Ask a focused question")
    click('[data-form="send-turn"] button')
    cue("05-dialogue", "use Branch", '.msg.assistant [data-action="branch-turn"]', "Branch from this turn")
    cue("05-dialogue", "This response is visibly simulated", ".msg.assistant .msg-meta", "Simulated response")
    scroll("#chat-log", "start")
    stop("05-dialogue")

    start("06-proposal", MS)
    browser("select", "#th-mode", "act")
    browser("fill", "#turn-input", "revise: " + PROPOSED)
    cue("06-proposal", "With a live provider configured", "#turn-input", "Request an edit")
    cue("06-proposal", "the special revise command", "#turn-input", "Offline demo: revise command")
    click('[data-form="send-turn"] button')
    cue(
        "06-proposal",
        "The Before and Proposed text panels",
        ".edit-comparison",
        "Compare before and proposed text",
    )
    cue("06-proposal", "Reject any edit", '[data-action="action-reject"]', "Reject unsupported edits")
    scroll("#action-list", "start")
    stop("06-proposal")
    assert section_text() == ORIGINAL, "A pending proposal must not change prose"

    start("07-revise", MS)
    details("Revise this proposal")
    cue(
        "07-revise",
        "Open Revise this proposal",
        '[data-form="revise-edit"] textarea',
        "Write your replacement text",
    )
    scroll('[data-form="revise-edit"]', "center")
    browser("fill", '[data-form="revise-edit"] textarea', REVISED)
    cue(
        "07-revise",
        "approval is disabled",
        '[data-action="action-approve"]',
        "Disabled until revision is saved",
    )
    cue(
        "07-revise",
        "Save revised proposal creates",
        '[data-form="revise-edit"] button',
        "Save revised proposal",
    )
    time.sleep(1)
    click('[data-form="revise-edit"] button')
    cue("07-revise", "Here, our revision explicitly says", ".edit-comparison", "Review your revised wording")
    scroll('[data-action="action-approve"]', "center")
    stop("07-revise")
    assert section_text() == ORIGINAL

    start("08-apply", MS)
    cue("08-apply", "Choose Apply shown edit", '[data-action="action-approve"]', "Apply the reviewed edit")
    scroll('[data-action="action-approve"]', "center")
    time.sleep(1)
    click('[data-action="action-approve"]')
    cue("08-apply", "The section now contains", "#chat-section-text", "Exact approved wording")
    scroll("#chat-section-text", "center")
    stop("08-apply")
    assert section_text() == REVISED

    start("09-undo", MS)
    cue("09-undo", "Propose undo creates", '[data-action="edit-undo"]', "Propose undo")
    click('[data-action="edit-undo"]')
    cue("09-undo", "It does not immediately restore", ".edit-comparison", "Undo is a pending proposal")
    cue(
        "09-undo",
        "Review that proposal and apply it",
        '[data-action="action-approve"]',
        "Review, then apply the undo",
    )
    scroll('[data-action="action-approve"]', "center")
    time.sleep(1.5)
    assert section_text() == REVISED, "Propose undo must await review"
    click('[data-action="action-approve"]')
    scroll("#chat-section-text", "center")
    cue("09-undo", "restore the original paragraph", "#chat-section-text", "Original paragraph restored")
    stop("09-undo")
    assert section_text() == ORIGINAL

    start("10-audit", MS)
    cue("10-audit", "Run audit", '[data-action="ms-audit"]', "Run audit")
    click('[data-action="ms-audit"]')
    cue("10-audit", "Treat the findings", "#ms-results", "Audit findings")
    cue("10-audit", "Skeptical review is", '[data-action="ms-review"]', "Separate skeptical review")
    scroll("#ms-results", "center")
    stop("10-audit")

    start("11-export", MS)
    scroll('[data-form="ms-export"]', "center")
    js(
        "document.querySelectorAll('[name=fmt]').forEach(e=>{e.checked=['md','html','docx','bib'].includes(e.value)})"
    )
    cue("11-export", "Choose your export formats", '[data-form="ms-export"]', "Choose formats and export")
    cue("11-export", "The interface also offers", '[data-form="ms-export"] fieldset', "Additional formats")
    click('[data-form="ms-export"] button')
    cue(
        "11-export",
        "Exports include a provenance manifest",
        "#ms-results",
        "Exported files and provenance manifest",
    )
    scroll("#ms-results", "start")
    assert "Export complete" in js("document.querySelector('#ms-results').textContent")
    stop("11-export")

    browser("open", f"{BASE}/ui/#/project/{PID}/literature")
    time.sleep(1)
    shot("12-literature")
    cue("12-toolbox", "Literature supports", 'a[href$="/literature"]', "Literature")
    browser("open", f"{BASE}/ui/#/project/{PID}/compute")
    time.sleep(1)
    shot("12-compute")
    cue("12-toolbox", "Compute provides", 'a[href$="/compute"]', "Compute")
    browser("open", f"{BASE}/ui/#/project/{PID}/figures")
    time.sleep(1)
    shot("12-figures")
    cue("12-toolbox", "Figures tracks", 'a[href$="/figures"]', "Figures")
    if CAPTURE_CALLOUTS:
        browser("open", MS)
        time.sleep(1)
        cue("12-toolbox", "Manuscripts also offers reporting checklists", "#cl-pack", "Reporting checklists")
        cue(
            "12-toolbox",
            "authorship contribution records",
            '[data-form="create-credit-contributor"]',
            "Authorship contributions",
        )
    browser("open", f"{BASE}/ui/#/project/{PID}/submissions")
    time.sleep(1)
    shot("12-toolbox")
    cue("12-toolbox", "Submissions tracks", 'a[href$="/submissions"]', "Submissions")
    checks = {
        "pending_edit_kept_original": True,
        "human_revision_kept_original": True,
        "approved_edit_matches_reviewer_text": True,
        "undo_awaited_approval": True,
        "approved_undo_restored_original": True,
        "brief_in_context": True,
        "export_completed": True,
        "browser_errors": browser("errors"),
        "data": "synthetic only",
        "provider": "fake",
        "recording_fallbacks": RECORDING_FALLBACKS,
    }
    (OUT / "capture-verification.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print("All capture checks passed", flush=True)


if __name__ == "__main__":
    main()
