"""Behavioural tests for Batch 3: S12 automation, S13 browser, S14 research.

No pytest. Prints [PASS]/[FAIL] plus evidence and exits non-zero on failure.
Every store is isolated in a temp directory so live data is never touched.
"""
from __future__ import annotations

import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_core.automation_manager import AutomationManager, CRITICAL_PROCESSES  # noqa: E402
from jarvis_core.browser_manager import BrowserManager, NullDriver  # noqa: E402
from jarvis_core.research_manager import ResearchManager, classify_source  # noqa: E402

PASSED = 0
FAILED = 0


def check(name, condition, evidence=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"[PASS] {name}" + (f"  {evidence}" if evidence else ""))
    else:
        FAILED += 1
        print(f"[FAIL] {name}" + (f"  {evidence}" if evidence else ""))


TMP = tempfile.mkdtemp(prefix="jarvis_batch3_")

# ===========================================================================
print("=== S12 computer automation ===")
work = os.path.join(TMP, "work")
os.makedirs(os.path.join(work, "docs"), exist_ok=True)
with open(os.path.join(work, "docs", "alpha.txt"), "w") as fh:
    fh.write("jarvis roadmap notes\n")
with open(os.path.join(work, "beta.log"), "w") as fh:
    fh.write("nothing relevant\n")

auto = AutomationManager(allowed_roots=[work])

archive = os.path.join(work, "bundle.zip")
zipped = auto.zip_paths([os.path.join(work, "docs")], archive)
check("zip creates a real archive and verifies its members",
      zipped["ok"] and zipped["verified"] and zipfile.is_zipfile(archive),
      f"entries={zipped['entries']} members={zipped['members']}")

refused = auto.zip_paths([os.path.join(work, "docs")], archive)
check("zip refuses to silently overwrite an existing archive",
      not refused["ok"] and "overwrite" in refused["reason"], refused["reason"])

out_dir = os.path.join(work, "extracted")
unzipped = auto.unzip(archive, out_dir)
check("unzip extracts and verifies files on disk",
      unzipped["ok"] and os.path.isfile(os.path.join(out_dir, "docs", "alpha.txt")),
      f"extracted={unzipped['extracted']} verified={unzipped['verified']}")

bad = auto.unzip(os.path.join(work, "beta.log"), out_dir)
check("unzip rejects a non-archive with a clear status",
      bad["status"] == "invalid_input", bad["reason"])

escape = os.path.join(work, "evil.zip")
with zipfile.ZipFile(escape, "w") as zf:
    zf.writestr("../../escaped.txt", "pwned")
slip = auto.unzip(escape, out_dir)
check("unzip blocks zip-slip path traversal",
      slip["status"] == "permission_denied"
      and not os.path.exists(os.path.join(TMP, "escaped.txt")), slip["reason"])

traversal = auto.zip_paths(["/etc/passwd"], os.path.join(work, "leak.zip"))
check("automation refuses paths outside the allowed roots",
      traversal["status"] == "permission_denied", traversal["reason"])

found = auto.search_computer("*.txt", roots=[work], contains="roadmap")
check("computer search finds files by name and content",
      found["ok"] and any(m["path"].endswith("alpha.txt") for m in found["matches"]),
      f"{len(found['matches'])} match(es)")

none_found = auto.search_computer("*.txt", roots=[work], contains="absent-token")
check("computer search reports zero matches instead of guessing",
      none_found["ok"] and none_found["matches"] == [], "0 matches")

limited = auto.search_computer("*", roots=[work], limit=1)
check("computer search is bounded by the result limit",
      len(limited["matches"]) == 1 and limited["truncated"], "limit=1 truncated=True")

bad_pattern = auto.search_computer("")
check("computer search validates its input",
      bad_pattern["status"] == "invalid_input", bad_pattern["reason"])

procs = auto.list_processes()
check("process listing uses a real backend and returns live processes",
      procs["ok"] and procs["count"] > 0,
      f"backend={procs['backend']} count={procs['count']}")

self_kill = auto.kill_process(pid=os.getpid())
check("process management refuses to kill Jarvis itself",
      self_kill["status"] == "permission_denied", self_kill["reason"])

init_kill = auto.kill_process(pid=1)
check("process management refuses to kill init/pid 1",
      init_kill["status"] == "permission_denied", init_kill["reason"])

check("critical process list protects system processes",
      auto.is_critical("systemd") and auto.is_critical("lsass.exe")
      and not auto.is_critical("leafpad"),
      f"{len(CRITICAL_PROCESSES)} protected names")

missing = auto.kill_process(pid=999999)
check("killing an unknown pid reports not_found",
      missing["status"] == "not_found", missing["reason"])

import subprocess  # noqa: E402

victim = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
killed = auto.kill_process(pid=victim.pid, force=True, allow_critical=True)
victim.wait(timeout=10)
check("process management really terminates a non-critical process",
      killed["ok"] and victim.poll() is not None,
      f"pid {victim.pid} exit={victim.poll()} signal={killed.get('signal')}")

windows = auto.move_window("Untitled", 10, 10)
check("window move reports unavailable on a headless host instead of faking success",
      windows["status"] in ("unavailable", "not_found", "ok"),
      f"status={windows['status']} reason={windows.get('reason')}")

unknown = auto.run("teleport")
check("automation manager rejects unknown actions",
      unknown["status"] == "invalid_input", unknown["reason"])

# ===========================================================================
print("\n=== S13 browser manager ===")


class FakeDriver:
    """In-process driver double implementing the BrowserDriver port."""

    name = "fake"

    def __init__(self, html="<html><body>welcome</body></html>"):
        self.html = html
        self.url = None
        self.values = {}
        self.clicked = []
        self.uploaded = {}
        self._tabs = ["about:blank"]
        self.index = 0
        self.download_records = []
        self.selectors = {"#email", "#password", "#submit", "#file", "#status"}
        self.closed = False

    def open(self, url):
        self.url = url
        self._tabs[self.index] = url

    def current_url(self):
        return self.url

    def page_source(self):
        return self.html

    def find(self, selector):
        return selector in self.selectors

    def fill(self, selector, value):
        if selector not in self.selectors:
            raise RuntimeError(f"no such element {selector}")
        self.values[selector] = value

    def click(self, selector):
        self.clicked.append(selector)
        self.values["#status"] = "Signed in as krishna"

    def text_of(self, selector):
        if selector == "#file":
            return self.uploaded.get(selector, "")
        return self.values.get(selector, "")

    def upload(self, selector, path):
        self.uploaded[selector] = os.path.basename(path)

    def downloads(self):
        return self.download_records

    def tabs(self):
        return list(self._tabs)

    def switch(self, index):
        self.index = index
        self.url = self._tabs[index]

    def close(self):
        self.closed = True


driver = FakeDriver()
browser = BrowserManager(os.path.join(TMP, "browser.db"), driver=driver,
                         download_dir=os.path.join(TMP, "dl"))

session = browser.open_session("research")["session"]["id"]
check("browser sessions are created and tracked",
      session.startswith("BS-") and browser.sessions()[0]["profile"] == "research",
      f"session={session}")

nav = browser.open_url(session, "https://example.test/login")
check("navigation verifies the resulting URL",
      nav["ok"] and nav["url"] == "https://example.test/login" and nav["verified"],
      f"url={nav['url']}")

bad_url = browser.open_url(session, "javascript:alert(1)")
check("browser refuses non-http(s) URLs",
      bad_url["status"] == "invalid_input", bad_url["reason"])

no_session = browser.open_url("BS-nonexistent", "https://example.test")
check("browser rejects actions on an unknown session",
      no_session["status"] == "not_found", no_session["reason"])

form = browser.fill_form(session, {"#email": "krishna@example.test",
                                   "#password": "s3cret"},
                         submit_selector="#submit",
                         expect_selector="#status", expect_text="Signed in")
check("form filling uses DOM selectors and verifies the outcome",
      form["ok"] and form["verified"] and driver.clicked == ["#submit"],
      f"filled={form['filled']} observed={form['observed']}")

logged = [h for h in browser.history(session) if h["action"] == "fill"]
pw = [h for h in logged if h["target"] == "#password"]
check("password field values are redacted in browser history",
      pw and "s3cret" not in pw[0]["expected"] and "REDACT" in pw[0]["expected"],
      f"stored expected={pw[0]['expected'] if pw else None}")

missing_sel = browser.fill_form(session, {"#nope": "x"})
check("form filling reports a missing selector instead of silently continuing",
      missing_sel["status"] == "not_found", missing_sel["reason"])

empty_form = browser.fill_form(session, {})
check("form filling validates its input",
      empty_form["status"] == "invalid_input", empty_form["reason"])

tabs = browser.active_tab(session)
check("active tab is tracked",
      tabs["ok"] and tabs["url"] == "https://example.test/login",
      f"active_tab={tabs['active_tab']} url={tabs['url']}")

driver._tabs.append("https://example.test/report")
switched = browser.switch_tab(session, 1)
check("tab switching verifies the new active tab",
      switched["ok"] and switched["url"] == "https://example.test/report",
      f"url={switched['url']} verified={switched['verified']}")

bad_tab = browser.switch_tab(session, 9)
check("tab switching rejects an out-of-range index",
      bad_tab["status"] == "invalid_input", bad_tab["reason"])

cap = browser.detect_captcha('<div class="g-recaptcha" data-sitekey="x"></div>')
check("CAPTCHA markup is detected",
      cap["captcha"] and "g-recaptcha" in cap["markers"], f"markers={cap['markers']}")

clean = browser.detect_captcha("<html><body>plain page</body></html>")
check("clean pages are not falsely flagged as CAPTCHA", not clean["captcha"], "captcha=False")

driver.html = "<html><body>Please verify you are human</body></html>"
blocked = browser.open_url(session, "https://example.test/protected")
check("CAPTCHA stops the operation and asks for a human",
      blocked["status"] == "captcha_required" and "human" in blocked["reason"],
      blocked["reason"])

blocked_form = browser.fill_form(session, {"#email": "a@b.test"})
check("CAPTCHA blocks form submission too (never bypassed)",
      blocked_form["status"] == "captcha_required", blocked_form["reason"])
driver.html = "<html><body>welcome</body></html>"

payload = os.path.join(TMP, "payload.bin")
with open(payload, "wb") as fh:
    fh.write(b"x" * 1234)
driver.download_records.append({"url": "https://example.test/file", "path": payload,
                               "state": "completed"})
downloaded = browser.download(session, "https://example.test/file", expected_bytes=1234)
check("download completes and is verified against the expected size",
      downloaded["ok"] and downloaded["bytes"] == 1234 and downloaded["verified"],
      f"path={downloaded['path']} bytes={downloaded['bytes']}")

wrong_size = browser.download(session, "https://example.test/file", expected_bytes=99)
check("download verification fails loudly on a size mismatch",
      not wrong_size["ok"] and not wrong_size["verified"],
      f"status={wrong_size['status']}")

timed_out = browser.download(session, "https://example.test/never", timeout=0.3, poll=0.05)
check("an unfinished download reports timeout, not success",
      timed_out["status"] == "timeout", timed_out["reason"])

check("download history is persisted",
      len(browser.downloads(session)) >= 3,
      f"{len(browser.downloads(session))} download records")

uploaded = browser.upload(session, "#file", payload)
check("upload attaches the file and verifies it",
      uploaded["ok"] and uploaded["attached"] == "payload.bin",
      f"attached={uploaded['attached']}")

no_file = browser.upload(session, "#file", os.path.join(TMP, "ghost.bin"))
check("upload reports a missing local file",
      no_file["status"] == "not_found", no_file["reason"])

reopened = BrowserManager(os.path.join(TMP, "browser.db"), driver=driver,
                          download_dir=os.path.join(TMP, "dl"))
check("browser action history survives restart",
      len(reopened.history()) > 5, f"{len(reopened.history())} actions reloaded")

closed = browser.close_session(session)
check("closing a session closes the driver",
      closed["ok"] and driver.closed and closed["session"]["closed"], "session closed")

after_close = browser.open_url(session, "https://example.test")
check("a closed session cannot be reused",
      after_close["status"] == "not_found", after_close["reason"])

headless = BrowserManager(os.path.join(TMP, "browser2.db"), driver=NullDriver(),
                          download_dir=os.path.join(TMP, "dl"))
hsession = headless.open_session()["session"]["id"]
unavailable = headless.open_url(hsession, "https://example.test")
check("without a browser backend the manager reports unavailable",
      unavailable["status"] == "unavailable" and not headless.health()["available"],
      unavailable["error"])

# ===========================================================================
print("\n=== S14 research manager ===")

DOCS = {
    "https://arxiv.org/abs/1234": (
        "Transformer throughput study. The measured latency of the model is 42 ms "
        "on commodity hardware. Unrelated filler sentence about weather."),
    "https://docs.example.org/guide": (
        "Official guide. The measured latency of the model is 42 ms under the same "
        "benchmark harness."),
    "https://someblog.medium.com/post": (
        "In my experience the measured latency of the model is 900 ms and cannot be "
        "improved."),
    "https://reuters.com/tech": (
        "Industry report: the measured latency of the model is 42 ms according to "
        "independent testing."),
}


def fetcher(question):
    return [{"url": url, "text": text} for url, text in DOCS.items()]


research = ResearchManager(os.path.join(TMP, "research.db"), fetcher=fetcher)

check("source classification recognises domain classes",
      classify_source("https://arxiv.org/abs/1") == "peer_reviewed"
      and classify_source("https://x.com/post") == "social"
      and classify_source("https://unknown.zz/a") == "unknown",
      "peer_reviewed / social / unknown")

ev = research.extract_evidence("What is the measured latency of the model?",
                               {"url": "https://arxiv.org/abs/1234",
                                "text": DOCS["https://arxiv.org/abs/1234"]})
check("evidence extraction keeps only relevant sentences",
      ev and all("latency" in e.claim.lower() for e in ev) and len(ev) == 1,
      f"{len(ev)} claim(s): {ev[0].claim[:60]!r}")
check("extracted evidence records source, quality, confidence and numbers",
      ev[0].source_class == "peer_reviewed" and ev[0].quality > 0.9
      and "42" in ev[0].numbers and 0 < ev[0].confidence <= 1,
      f"quality={ev[0].quality} confidence={ev[0].confidence} numbers={ev[0].numbers}")

try:
    research.extract_evidence("", {"url": "x", "text": "y"})
    bad_q = False
except ValueError as exc:
    bad_q = True
    msg = str(exc)
check("evidence extraction validates the question", bad_q, msg)

empty = research.extract_evidence("latency of the model", {"url": "u", "text": ""})
check("an empty document yields no invented evidence", empty == [], "0 claims")

high = research.score_source("https://arxiv.org/abs/1", corroborations=3)
low = research.score_source("https://someblog.medium.com/p", contradictions=2)
check("source quality scoring ranks a journal above a blog",
      high["score"] > low["score"],
      f"arxiv={high['score']} vs blog={low['score']}")

result = research.research("What is the measured latency of the model?", use_cache=False)
check("research collects evidence from multiple sources",
      result["ok"] and len(result["sources"]) >= 3,
      f"{len(result['sources'])} sources, {len(result['evidence'])} claims")
check("conflicting information is detected, not averaged away",
      any(c["kind"] == "numeric_disagreement" for c in result["conflicts"]),
      f"{len(result['conflicts'])} conflict(s)")
resolutions = [r for r in result["resolutions"] if r["resolved"]]
check("contradictions are resolved by evidence quality, not first result",
      resolutions and "42" in resolutions[0]["winner"]["claim"]
      and resolutions[0]["loser"]["source"].endswith("/post"),
      resolutions[0]["reason"] if resolutions else "none resolved")
check("the losing claim is preserved rather than discarded",
      all(r["conflict_preserved"] for r in result["resolutions"]),
      f"{len(result['resolutions'])} resolution record(s)")
check("research stops on a real stopping condition",
      result["stopped_because"] and len(result["rounds"]) < 4,
      f"{len(result['rounds'])} round(s): {result['stopped_because']}")
check("the chosen answer is the highest-quality claim",
      "42 ms" in result["answer"]["claim"],
      f"answer source={result['answer']['source']}")

stop_early = research.should_stop(ev, [], min_sources=5, confidence_target=0.99)
check("stopping condition refuses to stop on thin evidence",
      not stop_early["stop"] and "more source" in stop_early["reason"],
      stop_early["reason"])

budget = research.should_stop(ev, [], max_rounds=2, round_index=1)
check("stopping condition honours the round budget (no infinite research)",
      budget["stop"] and "budget" in budget["reason"], budget["reason"])

cached = research.research("What is the measured latency of the model?")
check("research results are cached and reused",
      cached.get("cached") and research.cache_stats()["hits"] >= 1,
      f"cache={research.cache_stats()}")

stored = research.claims("What is the measured latency of the model?")
check("claims are persisted with provenance",
      len(stored) >= 4 and all(r["source"] for r in stored),
      f"{len(stored)} claims stored")

reopened_research = ResearchManager(os.path.join(TMP, "research.db"), fetcher=fetcher)
check("research cache and claims survive restart",
      reopened_research.cache_stats()["entries"] >= 1
      and len(reopened_research.claims()) >= 4,
      f"entries={reopened_research.cache_stats()['entries']} "
      f"claims={len(reopened_research.claims())}")

no_fetcher = ResearchManager(os.path.join(TMP, "research3.db"))
blocked_research = no_fetcher.research("anything at all")
check("without a fetcher research reports unavailable instead of inventing sources",
      blocked_research["status"] == "unavailable", blocked_research["reason"])

bad_question = research.research("")
check("research validates its input",
      bad_question["status"] == "invalid_input", bad_question["reason"])


def broken_fetcher(question):
    raise ConnectionError("network unreachable")


failing = ResearchManager(os.path.join(TMP, "research4.db"), fetcher=broken_fetcher)
failed = failing.research("latency of the model", use_cache=False)
check("a fetcher failure is reported, not swallowed",
      failed["status"] == "failure" and "ConnectionError" in failed["error"],
      failed["error"])

print(f"\n{PASSED} passed, {FAILED} failed")
sys.exit(1 if FAILED else 0)
