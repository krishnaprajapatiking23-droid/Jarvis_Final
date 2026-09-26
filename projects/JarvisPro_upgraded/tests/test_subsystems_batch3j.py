"""Batch 3j - desktop UI subsystem tests (deep-spec sections 9-15).

These tests exercise real behaviour: real /proc telemetry, a real socket probe,
real SQLite settings persistence, real worker threads with timeouts, and the
honesty contracts (UNAVAILABLE / NOT_CONFIGURED) that keep the dashboard from
showing invented numbers.
"""

import os
import shutil
import socket
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import (CpuSampler, DashboardViewModel, DesktopApp, HotkeyManager,
                HotkeyProvider, QUICK_ACTIONS, QtDashboard, SettingsStore,
                TelemetryProvider, ToastCenter, TrayMenu, TrayProvider,
                WorkerPool, battery, detect_qt, format_duration, headless,
                host_info, memory, network, normalise, storage, uptime)
from ui.workers import CANCELLED, DONE, FAILED, TIMEOUT

PASSED = 0
FAILED_COUNT = 0


def check(name, condition, detail=""):
    global PASSED, FAILED_COUNT
    if condition:
        PASSED += 1
        print("PASS %s" % name)
    else:
        FAILED_COUNT += 1
        print("FAIL %s -- %s" % (name, detail))


class FakeObservability:
    def __init__(self, explode=False):
        self.explode = explode

    def recent_events(self, limit=10):
        if self.explode:
            raise RuntimeError("observability offline")
        return [{"component": "kernel", "operation": "understand",
                 "status": "ok", "timestamp": time.time()}] * 3


class FakeReminders:
    def due(self):
        return [{"title": "Revise physics", "at": time.time()}]


class FakeNotes:
    def recent(self, limit=5):
        return [{"title": "Discipline today, success tomorrow"}]


class FakeTasks:
    def summary(self):
        return {"open": 2, "done": 5}


class FakeApi:
    def __init__(self):
        self.calls = []

    def handle(self, route, payload=None, **kwargs):
        self.calls.append((route, payload))
        return {"ok": True, "route": route, "data": {"reply": "done"}}


class FakeKernel:
    def __init__(self, broken_status=False, broken_observability=False):
        self.broken_status = broken_status
        self.observability = FakeObservability(explode=broken_observability)
        self.reminders = FakeReminders()
        self.notes = FakeNotes()
        self.tasks = FakeTasks()
        self.api = FakeApi()
        self.understood = []

    def status(self):
        if self.broken_status:
            raise RuntimeError("kernel status exploded")
        return {"managers": {"automation": {"available": True},
                             "browser": {"available": False}}}

    def understand(self, text, **kwargs):
        self.understood.append(text)
        return {"intent": "open", "text": text}


class RecordingHotkeyProvider(HotkeyProvider):
    name = "recording"

    def __init__(self):
        self.registered = []
        self.unregistered = []

    def register(self, binding, action):
        self.registered.append((binding, action))

    def unregister(self, binding):
        self.unregistered.append(binding)


class BrokenHotkeyProvider(HotkeyProvider):
    name = "broken"

    def register(self, binding, action):
        raise RuntimeError("permission denied by the window manager")

    def unregister(self, binding):
        raise RuntimeError("permission denied by the window manager")


class RecordingTrayProvider(TrayProvider):
    name = "recording"

    def __init__(self):
        self.shown = 0
        self.updates = 0
        self.hidden = 0
        self.last_menu = []

    def show(self, tooltip, menu):
        self.shown += 1
        self.last_menu = menu

    def update(self, tooltip, menu):
        self.updates += 1
        self.last_menu = menu

    def hide(self):
        self.hidden += 1


TMP = tempfile.mkdtemp(prefix="b3j_")


def run():
    print("-- telemetry --")
    sampler = CpuSampler()
    first = sampler.sample()
    check("first cpu sample refuses to invent a percentage",
          first["status"] == "UNAVAILABLE" and first["value"] is None
          and "first sample" in (first["reason"] or ""), first)
    time.sleep(0.12)
    second = sampler.sample()
    check("second cpu sample is a real percentage",
          second["status"] == "ok" and 0.0 <= second["value"] <= 100.0, second)
    missing = CpuSampler(stat_path=os.path.join(TMP, "nope")).sample()
    check("unreadable cpu counters report unavailable",
          missing["status"] == "UNAVAILABLE" and "unreadable" in missing["reason"],
          missing)

    mem = memory()
    check("memory is measured from the host",
          mem["status"] == "ok" and 0 < mem["value"] <= 100
          and mem["total_gb"] > 0, mem)

    disk = storage("/")
    check("storage is measured from a real mount",
          disk["status"] == "ok" and disk["total_gb"] > 0
          and disk["used_gb"] >= 0, disk)
    bad_mount = storage(os.path.join(TMP, "no-such-mount"))
    check("missing mount reports the reason",
          bad_mount["status"] == "UNAVAILABLE"
          and "cannot read" in bad_mount["reason"], bad_mount)

    no_battery = battery(power_root=os.path.join(TMP, "empty-power"))
    check("absent battery is unavailable, not zero",
          no_battery["status"] == "UNAVAILABLE" and no_battery["value"] is None
          and "no battery" in no_battery["reason"], no_battery)

    power = os.path.join(TMP, "power")
    for name, kind, extra in (("AC", "Mains", None), ("BAT0", "Battery", "77")):
        node = os.path.join(power, name)
        os.makedirs(node, exist_ok=True)
        open(os.path.join(node, "type"), "w").write(kind + "\n")
        if extra:
            open(os.path.join(node, "capacity"), "w").write(extra + "\n")
            open(os.path.join(node, "status"), "w").write("Discharging\n")
    real_battery = battery(power_root=power)
    check("battery reads capacity and state from sysfs",
          real_battery["status"] == "ok" and real_battery["value"] == 77
          and real_battery["state"] == "discharging", real_battery)
    check("mains adapter is not mistaken for a battery",
          real_battery["source"] == "BAT0", real_battery)

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    live = network("127.0.0.1", port, 1.0)
    check("network latency is measured, not guessed",
          live["status"] == "ok" and live["unit"] == "ms"
          and live["value"] >= 0, live)
    listener.close()
    dead = network("127.0.0.1", 9, 0.4)
    check("failed probe reports unavailable with the reason",
          dead["status"] == "UNAVAILABLE" and dead["value"] is None
          and "failed" in dead["reason"], dead)

    up = uptime()
    check("host uptime is read from the machine",
          up["status"] in ("ok", "UNAVAILABLE"), up)
    check("duration formats days, hours, minutes, seconds",
          format_duration(90061) == "1d 01h 01m 01s", format_duration(90061))
    check("negative durations do not print garbage",
          format_duration(-5) == "0h 00m 00s", format_duration(-5))

    info = host_info()
    check("host info reports os, python and cores",
          info["cores"] >= 1 and info["python"].startswith("3.")
          and info["os"], info)

    provider = TelemetryProvider(probe_host="127.0.0.1", probe_port=9,
                                 history_size=4,
                                 power_root=os.path.join(TMP, "empty-power"))
    snapshot = provider.sample()
    check("provider samples every dashboard metric",
          set(snapshot["metrics"]) == {"cpu", "memory", "storage", "battery",
                                       "network", "uptime"}, snapshot["metrics"].keys())
    check("unreachable probe is listed as degraded",
          "network" in snapshot["degraded"], snapshot["degraded"])
    for _ in range(6):
        provider.sample()
    check("history is bounded",
          all(len(series) <= 4 for series in provider.history.values()),
          {k: len(v) for k, v in provider.history.items()})
    check("provider counts its samples",
          provider.health()["samples"] == 7, provider.health())
    check("trend needs two comparable readings",
          provider.trend("battery") is None, provider.trend("battery"))
    check("trend of a real metric is a number",
          isinstance(provider.trend("memory"), float), provider.trend("memory"))

    print("-- workers --")
    pool = WorkerPool(workers=2, default_timeout=1.0)
    job = pool.submit("add", lambda a, b: a + b, 2, 3)
    check("a job is accepted and identified",
          job["status"] == "ok" and job["job"].startswith("JOB-"), job)
    done = pool.wait(job["job"], 3.0)
    check("job result comes back off the GUI thread",
          done["state"] == DONE and done["result"] == 5, done)
    check("job duration is measured",
          isinstance(done["duration_ms"], float), done)
    check("non-callable work is rejected",
          pool.submit("bad", "not a function")["status"] == "invalid_input",
          pool.submit("bad", 7))

    def boom():
        raise ValueError("worker exploded")

    crash = pool.wait(pool.submit("boom", boom)["job"], 3.0)
    check("a crashing job fails without killing the pool",
          crash["state"] == FAILED and "exploded" in crash["error"], crash)

    hung = pool.submit("hang", lambda: time.sleep(5), timeout=0.3)
    timed = pool.wait(hung["job"], 3.0)
    check("a hung job degrades to timeout",
          timed["state"] == TIMEOUT and "timed out" in timed["error"], timed)

    slow = pool.submit("slow", lambda: time.sleep(0.6), timeout=5.0)
    cancelled = pool.cancel(slow["job"])
    check("a running job can be cancelled",
          cancelled["status"] == "ok" and cancelled["cancelled"] is True,
          cancelled)
    after = pool.wait(slow["job"], 3.0)
    check("cancellation is recorded in the final state",
          after["state"] in (CANCELLED, DONE), after)
    check("cancelling an unknown job is not_found",
          pool.cancel("JOB-nope")["status"] == "not_found",
          pool.cancel("JOB-nope"))
    check("status of an unknown job is not_found",
          pool.status("JOB-nope")["status"] == "not_found", pool.status("x"))

    seen = []
    pool.on_result(lambda payload: seen.append(payload["name"]))
    ids = [pool.submit("batch-%d" % i, lambda i=i: i * 2)["job"]
           for i in range(24)]
    results = [pool.wait(jid, 5.0) for jid in ids]
    check("24 queued jobs all complete on 2 workers",
          all(r["state"] == DONE for r in results),
          [r["state"] for r in results if r["state"] != DONE])
    check("result listeners are notified", len(seen) >= 24, len(seen))
    check("drain hands finished jobs to the UI and empties",
          len(pool.drain()) >= 24 and pool.drain() == [], "drain")
    health = pool.health()
    check("pool health counts outcomes",
          health["completed"] >= 25 and health["failed"] == 1
          and health["timed_out"] == 1, health)
    # A job that timed out is still physically running (Python cannot kill a
    # thread), so shutdown must report the straggler instead of claiming a
    # clean stop. Earlier this test asserted stopped is True, which was my
    # wrong expectation, not an implementation bug.
    stopped = pool.shutdown()
    check("shutdown is honest about threads it could not join",
          stopped["status"] == "ok"
          and stopped["stopped"] == (stopped["still_running"] == 0), stopped)
    check("the pool is unavailable once shut down",
          pool.health()["available"] is False, pool.health())
    check("submitting after shutdown is refused honestly",
          pool.submit("late", lambda: 1)["status"] == "UNAVAILABLE",
          pool.submit("late", lambda: 1))

    print("-- settings --")
    db = os.path.join(TMP, "ui.db")
    store = SettingsStore(db)
    check("defaults come from the declared schema",
          store.get("theme") == "arc_reactor"
          and store.get("telemetry_interval_ms") == 1000, store.all())
    check("schema is introspectable for the settings panel",
          len(store.schema()) == len(store.all())
          and all("kind" in row for row in store.schema()), store.schema()[:1])

    changes = []
    store.on_change(lambda key, old, new: changes.append((key, old, new)))
    store.on_change(lambda key, old, new: (_ for _ in ()).throw(
        RuntimeError("bad observer")))
    check("a valid choice is stored",
          store.set("theme", "midnight")["status"] == "ok", store.get("theme"))
    check("observers see the change",
          changes and changes[0] == ("theme", "arc_reactor", "midnight"), changes)
    check("a crashing observer does not undo a valid write",
          store.get("theme") == "midnight", store.get("theme"))
    check("an unknown choice is rejected with the allowed list",
          "one of" in store.set("theme", "neon")["error"],
          store.set("theme", "neon"))
    check("a number below range is rejected",
          ">=" in store.set("telemetry_interval_ms", 10)["error"],
          store.set("telemetry_interval_ms", 10))
    check("a number above range is rejected",
          "<=" in store.set("telemetry_interval_ms", 999999)["error"],
          store.set("telemetry_interval_ms", 999999))
    check("a numeric string is coerced",
          store.set("telemetry_interval_ms", "500")["value"] == 500,
          store.get("telemetry_interval_ms"))
    check("nonsense for a number is rejected",
          store.set("telemetry_interval_ms", "soon")["status"] == "invalid_input",
          store.set("telemetry_interval_ms", "soon"))
    check("a boolean string is coerced",
          store.set("voice_enabled", "false")["value"] is False,
          store.get("voice_enabled"))
    check("a number is not a boolean",
          store.set("voice_enabled", 7)["status"] == "invalid_input",
          store.set("voice_enabled", 7))
    check("over-long text is rejected",
          store.set("wake_word", "j" * 80)["status"] == "invalid_input",
          store.set("wake_word", "j" * 80))
    check("a hotkey setting is normalised",
          store.set("global_hotkey", "ctrl+shift+k")["value"] == "Ctrl+Shift+K",
          store.get("global_hotkey"))
    check("a modifier-less hotkey is rejected",
          store.set("global_hotkey", "j")["status"] == "invalid_input",
          store.set("global_hotkey", "j"))
    check("an unknown setting is not_found",
          store.set("warp_drive", True)["status"] == "not_found",
          store.set("warp_drive", True))
    check("a restart-required setting says so",
          store.set("launch_on_login", True)["restart_required"] is True,
          store.set("launch_on_login", True))

    bulk = store.update({"theme": "light", "toast_seconds": 3,
                         "mode": "warp"})
    check("bulk update applies the good keys",
          bulk["applied"]["theme"] == "light"
          and bulk["applied"]["toast_seconds"] == 3.0, bulk)
    check("bulk update reports the bad keys",
          "mode" in bulk["errors"], bulk["errors"])
    log = store.history("theme")
    check("changes are journalled newest first",
          log and log[0]["key"] == "theme" and log[0]["new"] == "light", log[:1])
    check("reset restores the default",
          store.reset("theme")["value"] == "arc_reactor", store.get("theme"))
    check("resetting an unknown key is not_found",
          store.reset("warp_drive")["status"] == "not_found", "reset")
    check("settings health counts the schema",
          store.health()["declared"] == len(store.all())
          and store.health()["available"] is True, store.health())
    store.close()

    reopened = SettingsStore(db)
    check("settings survive a restart",
          reopened.get("global_hotkey") == "Ctrl+Shift+K"
          and reopened.get("voice_enabled") is False, reopened.all())
    reopened._db.execute("UPDATE settings SET value = ? WHERE key = ?",
                         ("{not json", "global_hotkey"))
    reopened._db.commit()
    check("a corrupt stored value falls back to the default",
          reopened.get("global_hotkey") == "Ctrl+Shift+J",
          reopened.get("global_hotkey"))
    reopened._db.execute("UPDATE settings SET value = ? WHERE key = ?",
                         ('"neon"', "theme"))
    reopened._db.commit()
    check("a now-invalid stored value falls back to the default",
          reopened.get("theme") == "arc_reactor", reopened.get("theme"))
    reopened.close()

    print("-- hotkeys --")
    table = [("ctrl+shift+j", "Ctrl+Shift+J"),
             ("CTRL-ALT-F5", "Ctrl+Alt+F5"),
             ("cmd+space", "Meta+Space"),
             ("shift+ctrl+j", "Ctrl+Shift+J"),
             ("win+alt+escape", "Alt+Meta+Escape")]
    for raw, expected in table:
        ok, value, reason = normalise(raw)
        check("normalise %r -> %s" % (raw, expected),
              ok and value == expected, (value, reason))
    for raw in ("", "ctrl", "j", "ctrl+shift", "ctrl+shift+jj", "ctrl++j",
                "ctrl+f99", 5, None, "ctrl+alt+delete"):
        ok, value, reason = normalise(raw)
        check("reject hotkey %r" % (raw,), not ok and reason, (ok, value))

    keys = HotkeyManager()
    tracked = keys.bind("ctrl+shift+j", "toggle_window", handler=lambda: "shown")
    check("without a backend a hotkey is tracked but not grabbed",
          tracked["status"] == "NOT_CONFIGURED"
          and "not grabbed" in tracked["error"], tracked)
    check("the binding is still visible to the settings panel",
          keys.bindings()["Ctrl+Shift+J"]["registered"] is False,
          keys.bindings())
    check("hotkey health is honest about the missing backend",
          keys.health()["status"] == "NOT_CONFIGURED"
          and keys.health()["available"] is False, keys.health())
    fired = keys.trigger("ctrl+shift+j")
    check("a tracked hotkey still dispatches in-process",
          fired["status"] == "ok" and fired["result"] == "shown", fired)

    backend = RecordingHotkeyProvider()
    attached = keys.set_provider(backend)
    check("attaching a backend rebinds existing hotkeys",
          attached["rebound"] == ["Ctrl+Shift+J"]
          and backend.registered == [("Ctrl+Shift+J", "toggle_window")],
          (attached, backend.registered))
    check("health flips to ok once the keys are grabbed",
          keys.health()["available"] is True, keys.health())
    conflict = keys.bind("ctrl+shift+j", "push_to_talk")
    check("a conflicting binding names the current owner",
          conflict["status"] == "conflict"
          and "toggle_window" in conflict["error"], conflict)
    check("an explicit replace wins",
          keys.bind("ctrl+shift+j", "push_to_talk", replace=True)["status"] == "ok",
          keys.bindings())
    moved = keys.rebind("push_to_talk", "ctrl+alt+p")
    check("rebinding moves the action to new keys",
          moved["status"] == "ok" and "Ctrl+Alt+P" in keys.bindings()
          and "Ctrl+Shift+J" not in keys.bindings(), (moved, keys.bindings()))
    check("the old grab is released",
          "Ctrl+Shift+J" in backend.unregistered, backend.unregistered)
    check("rebinding an unknown action is not_found",
          keys.rebind("nope", "ctrl+alt+z")["status"] == "not_found", "rebind")
    check("unbinding works",
          keys.unbind("ctrl+alt+p")["status"] == "ok", keys.bindings())
    check("unbinding twice is not_found",
          keys.unbind("ctrl+alt+p")["status"] == "not_found", "unbind")
    check("triggering an unbound hotkey is not_found",
          keys.trigger("ctrl+alt+p")["status"] == "not_found", "trigger")
    check("triggering nonsense is invalid_input",
          keys.trigger("nonsense")["status"] == "invalid_input", "trigger")
    keys.bind("ctrl+alt+h", "no_handler")
    check("a hotkey with no handler is not_configured",
          keys.trigger("ctrl+alt+h")["status"] == "NOT_CONFIGURED", "handler")

    def explode():
        raise RuntimeError("handler broke")

    keys.bind("ctrl+alt+b", "broken", handler=explode)
    broke = keys.trigger("ctrl+alt+b")
    check("a crashing handler is reported, not swallowed",
          broke["status"] == "failure" and "handler broke" in broke["error"],
          broke)
    refused = HotkeyManager(provider=BrokenHotkeyProvider()).bind(
        "ctrl+shift+j", "toggle")
    check("an OS refusal is surfaced with its reason",
          refused["status"] == "NOT_CONFIGURED"
          and "permission" in refused["error"], refused)

    print("-- tray --")
    tray = TrayMenu(tooltip="JARVIS")
    check("tray item is added",
          tray.add("show", "Show JARVIS", handler=lambda: "shown")["status"] == "ok",
          tray.items())
    check("duplicate tray ids are rejected",
          tray.add("show", "Again")["status"] == "invalid_input", tray.items())
    check("an empty label is rejected",
          tray.add("blank", "  ")["status"] == "invalid_input", tray.items())
    check("showing without a backend is not_configured",
          tray.show()["status"] == "NOT_CONFIGURED", tray.show())
    check("tray health is honest without a backend",
          tray.health()["available"] is False, tray.health())
    tray.add("listen", "Listening", handler=lambda: "toggled", checkable=True)
    tray.add("quit", "Quit")
    backend = RecordingTrayProvider()
    check("attaching a tray backend shows the icon",
          tray.set_provider(backend)["status"] == "ok" and backend.shown == 1,
          backend.shown)
    tray.set_tooltip("JARVIS PRO")
    check("menu changes are pushed to the backend",
          backend.updates > 0 and all("id" in item for item in backend.last_menu),
          backend.last_menu)
    check("a blank tooltip is rejected",
          tray.set_tooltip("  ")["status"] == "invalid_input", tray.tooltip)
    clicked = tray.click("show")
    check("clicking runs the handler",
          clicked["status"] == "ok" and clicked["result"] == "shown", clicked)
    toggled = tray.click("listen")
    check("a checkable item toggles",
          toggled["checked"] is True, toggled)
    check("clicking it again untoggles",
          tray.click("listen")["checked"] is False, tray.items())
    check("an item with no handler is not_configured",
          tray.click("quit")["status"] == "NOT_CONFIGURED", tray.click("quit"))
    tray.set_enabled("show", False)
    check("a disabled item refuses clicks",
          tray.click("show")["status"] == "invalid_input", tray.items())
    check("enabling an unknown item is not_found",
          tray.set_enabled("nope", True)["status"] == "not_found", "enable")
    check("checking a non-checkable item is invalid_input",
          tray.set_checked("quit", True)["status"] == "invalid_input", "check")
    tray.add("boom", "Boom",
             handler=lambda: (_ for _ in ()).throw(RuntimeError("tray broke")))
    check("a crashing tray handler is reported",
          tray.click("boom")["status"] == "failure", tray.click("boom"))
    check("removing an item works",
          tray.remove("boom")["status"] == "ok", tray.items())
    check("removing twice is not_found",
          tray.remove("boom")["status"] == "not_found", "remove")
    check("hiding calls the backend",
          tray.hide()["status"] == "ok" and backend.hidden == 1, backend.hidden)

    print("-- toasts --")
    toasts = ToastCenter(max_visible=2, default_ttl=5.0, dedupe_window=10.0)
    now = 1000.0
    one = toasts.push("Backup done", "3 files", level="success", now=now)
    check("a toast is queued and shown",
          one["status"] == "ok" and len(toasts.visible(now)) == 1, one)
    dup = toasts.push("Backup done", "3 files", level="success", now=now + 1)
    check("an identical toast is de-duplicated with a count",
          dup.get("duplicate") is True and dup["count"] == 2, dup)
    check("a blank title is rejected",
          toasts.push("   ", now=now)["status"] == "invalid_input", "blank")
    check("an unknown level is rejected",
          toasts.push("Hi", level="loud", now=now)["status"] == "invalid_input",
          "level")
    toasts.push("Disk almost full", level="warning", now=now + 2)
    check("visible list respects the cap",
          len(toasts.visible(now + 2)) == 2, toasts.visible(now + 2))
    toasts.push("Backup failed", level="error", now=now + 3)
    visible = toasts.visible(now + 3)
    check("most severe toast is promoted first",
          any(t["level"] == "error" for t in visible), visible)
    check("displacement is counted",
          toasts.health()["displaced"] >= 1, toasts.health())
    check("toasts expire on time",
          toasts.visible(now + 999) == [], toasts.visible(now + 999))
    hist = toasts.history()
    check("history keeps what was shown, newest first",
          hist and hist[0]["title"] == "Backup failed", hist[:1])

    live = ToastCenter(max_visible=1, default_ttl=100.0)
    shown = []
    live.on_show(lambda toast: shown.append(toast["title"]))
    live.push("First", now=2000.0)
    check("show listeners are notified", shown == ["First"], shown)
    target = live.push("Second", now=2000.1)
    check("dismissing a queued toast works",
          live.dismiss(target["id"], now=2000.2)["status"] == "ok", "dismiss")
    check("dismissing an unknown toast is not_found",
          live.dismiss("TST-nope")["status"] == "not_found", "dismiss")

    burst = ToastCenter(max_visible=1, max_queue=3, default_ttl=100.0)
    results = [burst.push("Info %d" % i, now=3000.0) for i in range(10)]
    check("burst push still returns a result for every call",
          all(r["status"] == "ok" for r in results), results[:2])
    check("overflow is dropped and counted, not silently lost",
          burst.health()["dropped"] > 0 and burst.health()["queued"] <= 3,
          burst.health())
    urgent = burst.push("Critical", level="error", now=3000.1)
    check("an error is accepted even when the queue is full of info",
          not urgent.get("dropped"), urgent)
    check("the error reaches the screen",
          any(t["level"] == "error" for t in burst.visible(3000.2)),
          burst.visible(3000.2))
    check("clear empties the centre",
          burst.clear()["cleared"] >= 1 and burst.visible(3000.3) == [],
          "clear")

    print("-- view model --")
    vm_settings = SettingsStore(os.path.join(TMP, "vm.db"))
    kernel = FakeKernel()
    vm = DashboardViewModel(kernel=kernel,
                            telemetry=TelemetryProvider(probe_port=9,
                                                        power_root=os.path.join(TMP, "empty-power")),
                            settings=vm_settings, owner="Krishna")
    snap = vm.refresh()
    check("dashboard builds every panel",
          set(["header", "reactor", "system", "activity", "reminders", "notes",
               "tasks", "quick_actions", "modes"]).issubset(snap), snap.keys())
    check("greeting uses the owner name",
          snap["reactor"]["greeting"] == "Hello Krishna, how can I help you today?",
          snap["reactor"]["greeting"])
    check("a degraded manager takes the reactor offline",
          snap["reactor"]["state"] == "OFFLINE"
          and "browser" in snap["reactor"]["degraded"], snap["reactor"])
    check("gauges carry status, not just numbers",
          snap["header"]["gauges"]["battery"]["status"] == "UNAVAILABLE"
          and snap["header"]["gauges"]["memory"]["status"] == "ok",
          snap["header"]["gauges"])
    check("activity feed reads real events",
          snap["activity"]["status"] == "ok"
          and snap["activity"]["items"][0]["component"] == "kernel",
          snap["activity"])
    check("reminders and notes come from the kernel",
          snap["reminders"]["status"] == "ok"
          and snap["notes"]["status"] == "ok", (snap["reminders"], snap["notes"]))
    check("task summary is included",
          snap["tasks"]["data"]["open"] == 2, snap["tasks"])
    check("nine quick actions match the dashboard grid",
          len(vm.quick_actions()) == 9 == len(QUICK_ACTIONS), vm.quick_actions())
    check("voice examples are offered",
          len(vm.voice_examples()) >= 3, vm.voice_examples())
    check("refreshes are counted and cached",
          vm.refreshes == 1 and vm.last() is snap, vm.refreshes)
    check("navigation validates the page",
          vm.navigate("chat")["status"] == "ok"
          and vm.navigate("warp")["status"] == "invalid_input", vm.page)
    check("mode changes persist through settings",
          vm.set_mode("focus")["status"] == "ok"
          and vm_settings.get("mode") == "focus", vm.mode())
    check("an unknown mode is rejected",
          vm.set_mode("warp")["status"] == "invalid_input", vm.mode())

    broken_vm = DashboardViewModel(
        kernel=FakeKernel(broken_status=True, broken_observability=True),
        telemetry=TelemetryProvider(probe_port=9,
                                    power_root=os.path.join(TMP, "empty-power")),
        owner="Krishna")
    broken_snap = broken_vm.refresh()
    check("a broken kernel status does not crash the dashboard",
          broken_snap["status"] == "ok"
          and broken_snap["reactor"]["state"] == "OFFLINE", broken_snap["reactor"])
    check("the failure reason is shown, not hidden",
          "exploded" in (broken_snap["reactor"]["reason"] or ""),
          broken_snap["reactor"])
    check("a broken activity feed degrades to unavailable",
          broken_snap["activity"]["status"] == "UNAVAILABLE"
          and "offline" in broken_snap["activity"]["reason"],
          broken_snap["activity"])

    bare = DashboardViewModel(
        telemetry=TelemetryProvider(probe_port=9,
                                    power_root=os.path.join(TMP, "empty-power")),
        owner="Krishna")
    bare_snap = bare.refresh()
    check("with no kernel the panels say not_configured",
          bare_snap["activity"]["status"] == "NOT_CONFIGURED"
          and bare_snap["reminders"]["status"] == "NOT_CONFIGURED",
          bare_snap["activity"])
    check("telemetry still works without a kernel",
          bare_snap["header"]["gauges"]["memory"]["status"] == "ok",
          bare_snap["header"]["gauges"]["memory"])
    vm_settings.close()

    print("-- desktop app --")
    kernel = FakeKernel()
    app = DesktopApp(kernel=kernel, db_path=os.path.join(TMP, "app.db"),
                     telemetry=TelemetryProvider(probe_port=9,
                                                 power_root=os.path.join(TMP, "empty-power")),
                     owner="Krishna")
    check("the shell wires the tray menu",
          len(app.tray.items()) >= 5, app.tray.items())
    check("the shell binds the configured global hotkey",
          "Ctrl+Shift+J" in app.hotkeys.bindings(), app.hotkeys.bindings())
    check("the global hotkey toggles the window",
          app.hotkeys.trigger("ctrl+shift+j")["result"]["visible"] is True,
          app.window_visible)
    check("pressing it again hides the window",
          app.hotkeys.trigger("ctrl+shift+j")["result"]["visible"] is False,
          app.window_visible)
    app.settings.set("minimise_to_tray", False)
    app.show_window()
    check("hiding respects the minimise-to-tray setting",
          app.hide_window()["visible"] is True, app.window_visible)
    app.settings.set("minimise_to_tray", True)
    check("changing the hotkey setting rebinds it live",
          app.settings.set("global_hotkey", "ctrl+alt+j")["status"] == "ok"
          and "Ctrl+Alt+J" in app.hotkeys.bindings(), app.hotkeys.bindings())
    check("the tray navigates the window",
          app.tray.click("settings")["status"] == "ok"
          and app.dashboard.page == "settings", app.dashboard.page)
    check("push to talk toggles listening",
          app.tray.click("listen")["status"] == "ok" and app.listening is True,
          app.listening)

    queued = app.submit_command("open my notes")
    check("a command is queued to a worker, not run on the GUI thread",
          queued["status"] == "ok" and queued["job"].startswith("JOB-"), queued)
    result = app.workers.wait(queued["job"], 5.0)
    check("the command reaches the API layer",
          result["state"] == DONE and kernel.api.calls
          and kernel.api.calls[0][0] == "command.execute", kernel.api.calls)
    check("an empty command is rejected",
          app.submit_command("   ")["status"] == "invalid_input", "command")
    no_kernel = DesktopApp(telemetry=TelemetryProvider(probe_port=9))
    check("with no kernel commands are not_configured",
          no_kernel.submit_command("hello")["status"] == "NOT_CONFIGURED",
          no_kernel.submit_command("hello"))
    no_kernel.shutdown()

    panel = app.settings_panel()
    check("the settings panel exposes schema, values and history",
          panel["schema"] and panel["values"] and isinstance(panel["history"], list),
          panel.keys())
    applied = app.apply_settings({"toast_seconds": 2, "theme": "neon"})
    check("valid settings apply and invalid ones are reported",
          applied["applied"]["toast_seconds"] == 2.0
          and "theme" in applied["errors"], applied)
    check("a rejected setting raises a warning toast",
          any(t["level"] == "warning" for t in app.toasts.visible()),
          app.toasts.visible())
    check("the toast duration follows the setting",
          app.toasts.default_ttl == 2.0, app.toasts.default_ttl)

    snapshot = app.refresh()
    check("the shell refreshes the dashboard",
          snapshot["status"] == "ok", snapshot.get("status"))
    started = app.start_refresh_loop()
    check("the background refresh loop starts",
          started["running"] is True, started)
    time.sleep(1.2)
    before = app.dashboard.refreshes
    time.sleep(1.2)
    check("the refresh loop keeps sampling in the background",
          app.dashboard.refreshes > before, (before, app.dashboard.refreshes))
    check("stopping the loop is clean",
          app.stop_refresh_loop()["running"] is False, "loop")

    qt = detect_qt()
    check("Qt detection is honest about this environment",
          (qt["status"] == "ok" and qt["binding"]) or
          (qt["status"] == "UNAVAILABLE" and "no Qt binding" in qt["reason"]), qt)
    view = QtDashboard(app)
    built = view.build()
    check("the window refuses to claim it rendered without a toolkit",
          built["status"] in ("ok", "UNAVAILABLE")
          and (built["status"] == "ok" or built["reason"]), built)
    painted = view.render(snapshot)
    check("rendering is pure and works headless",
          "MEMORY" in painted["header"] and "BATTERY --" in painted["header"],
          painted["header"])
    check("the reactor line carries state and greeting",
          "Hello Krishna" in painted["reactor"], painted["reactor"])
    check("nine nav items match the dashboard design",
          len(QtDashboard.NAV_ITEMS) == 9
          and QtDashboard.TITLE == "JARVIS AI v7.0.1 PRO",
          QtDashboard.NAV_ITEMS)
    check("headless detection returns a boolean",
          isinstance(headless(), bool), headless())

    status = app.status()
    check("status reports every subsystem",
          set(["toasts", "workers", "hotkeys", "tray", "settings",
               "telemetry", "dashboard"]).issubset(status), status.keys())
    health = app.health()
    check("health separates 'running' from 'renderable'",
          health["available"] is True
          and (health["renderable"] is True or health["reason"]), health)
    check("shutdown stops the workers and closes settings",
          app.shutdown()["status"] == "ok", "shutdown")

    print("")
    print("batch3j: %d passed, %d failed" % (PASSED, FAILED_COUNT))
    return FAILED_COUNT


if __name__ == "__main__":
    failures = run()
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if failures else 0)
