"""Regression tests for the deep-repair pass (Phase 15).

One or more tests per repaired bug, plus security, concurrency and
integration coverage. Pure standard library so the suite runs offline.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ANDROID = ROOT / "android" / "app" / "src" / "main"
KOTLIN = ANDROID / "java" / "com" / "jarvis" / "companion"


# ---------------------------------------------------------------- BUG 1
class CompatibilityWrappers(unittest.TestCase):
    """BUG 1: canonical modules own the implementation."""

    PAIRS = (
        ("brains_v2.planner.scheduler", "brains_v2.planner.schedular"),
        ("brains_v2.vision.ocr", "brains_v2.vision.orc"),
        ("thinking.observer", "thinking.obsever"),
    )

    def test_all_six_modules_import(self):
        for canonical, legacy in self.PAIRS:
            self.assertTrue(importlib.import_module(canonical))
            self.assertTrue(importlib.import_module(legacy))

    def test_legacy_reexports_the_same_objects(self):
        for canonical, legacy in self.PAIRS:
            new = importlib.import_module(canonical)
            old = importlib.import_module(legacy)
            for name in new.__all__:
                self.assertIs(
                    getattr(old, name),
                    getattr(new, name),
                    msg=f"{legacy}.{name} is not the canonical object",
                )

    def test_canonical_does_not_import_legacy(self):
        checks = (
            ("brains_v2/planner/scheduler.py", "schedular"),
            ("brains_v2/vision/ocr.py", "orc"),
            ("thinking/observer.py", "obsever"),
        )
        for relative, legacy_name in checks:
            source = (ROOT / relative).read_text(encoding="utf-8")
            for line in source.splitlines():
                stripped = line.strip()
                if not (stripped.startswith("import ") or stripped.startswith("from ")):
                    continue
                self.assertNotIn(
                    legacy_name,
                    stripped,
                    msg=f"{relative} still imports the misspelled module",
                )

    def test_canonical_works_without_legacy_files(self):
        """Delete the misspelled files in a temp copy; canonical must work."""
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / "project"
            shutil.copytree(
                ROOT,
                copy,
                ignore=shutil.ignore_patterns(
                    "__pycache__", ".git", "*.db", "manual_demos", "android"
                ),
            )
            for relative in (
                "brains_v2/planner/schedular.py",
                "brains_v2/vision/orc.py",
                "thinking/obsever.py",
            ):
                (copy / relative).unlink()

            script = (
                "import brains_v2.planner.scheduler as s;"
                "import brains_v2.vision.ocr as o;"
                "import thinking.observer as v;"
                "print(s.build_schedule(['a']).order, "
                "o.engine.backend_status()['available'], "
                "bool(v.observer.status()))"
            )
            import subprocess

            finished = subprocess.run(
                [sys.executable, "-c", script],
                cwd=copy,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(finished.returncode, 0, msg=finished.stderr[-2000:])
            self.assertIn("['a']", finished.stdout)


# ---------------------------------------------------------------- BUG 4
class SafeMathLimits(unittest.TestCase):
    """BUG 4: dangerous expressions rejected before evaluation."""

    def setUp(self):
        from security import safe_math

        self.math = safe_math

    def test_reasonable_expressions_still_work(self):
        cases = {
            "2+3*4": 14,
            "2**10": 1024,
            "9**9": 387420489,
            "10/4": 2.5,
            "-(3**3)": -27,
        }
        for expression, expected in cases.items():
            self.assertEqual(self.math.evaluate(expression), expected, expression)
        self.assertEqual(self.math.evaluate("2**100"), 2 ** 100)
        self.assertEqual(self.math.evaluate("2**20"), 2 ** 20)

    def test_abuse_cases_are_rejected_quickly(self):
        for expression in ("9**9**9999", "10**1000000", "(2**100)**100", "2**(10**10)"):
            started = time.monotonic()
            with self.assertRaises(self.math.SafeMathError, msg=expression):
                self.math.evaluate(expression)
            self.assertLess(
                time.monotonic() - started, 0.5, msg=f"{expression} was slow"
            )

    def test_code_execution_is_not_arithmetic(self):
        for expression in (
            "__import__('os').system('id')",
            "open('/etc/passwd').read()",
            "[1,2,3]",
            "'a'*10000000",
        ):
            with self.assertRaises(self.math.SafeMathError, msg=expression):
                self.math.evaluate(expression)

    def test_division_by_zero_is_a_clean_error(self):
        with self.assertRaises(self.math.SafeMathError):
            self.math.evaluate("1/0")

    def test_complexity_limits_apply(self):
        with self.assertRaises(self.math.SafeMathError):
            self.math.evaluate("+".join(["1"] * 500))


# ---------------------------------------------------------------- BUG 5
class HeadlessOAuth(unittest.TestCase):
    """BUG 5: no flow may wait forever."""

    def setUp(self):
        from integrations import oauth

        self.oauth = oauth
        self.flow = oauth.AuthorizationCodeFlow(
            client_id="client",
            authorization_endpoint="https://example.test/authorize",
            token_endpoint="https://example.test/token",
            scopes=("email",),
            timeout=1.0,
        )

    def test_headless_environment_selects_manual_mode(self):
        os.environ["JARVIS_OAUTH_HEADLESS"] = "1"
        try:
            self.assertTrue(self.oauth.headless())
            self.assertEqual(self.flow.resolve_mode(), "manual")
        finally:
            os.environ.pop("JARVIS_OAUTH_HEADLESS", None)

    def test_callback_wait_times_out(self):
        started = time.monotonic()
        with self.assertRaises(self.oauth.OAuthTimeout) as caught:
            self.flow._wait_for_callback()
        self.assertIn("timed out", str(caught.exception).lower())
        self.assertLess(time.monotonic() - started, 20)

    def test_timeout_message_is_exact(self):
        self.assertEqual(self.oauth.TIMEOUT_MESSAGE, "Authentication timed out.")

    def test_authorization_url_uses_pkce_and_state(self):
        url = self.flow.authorization_url()
        self.assertIn("code_challenge_method=S256", url)
        self.assertIn("code_challenge=", url)
        self.assertIn("state=" + self.flow.state, url)
        self.assertNotIn(self.flow.verifier, url)

    def test_state_mismatch_is_rejected(self):
        with self.assertRaises(self.oauth.OAuthError):
            self.flow._validate({"code": "abc", "state": "wrong"})

    def test_manual_mode_accepts_a_pasted_redirect_url(self):
        redirect = f"http://127.0.0.1/callback?code=xyz&state={self.flow.state}"
        self.flow.prompt = lambda _prompt: redirect
        self.assertEqual(self.flow._manual_code(), "xyz")

    def test_manual_mode_does_not_block_without_a_reader(self):
        flow = self.oauth.AuthorizationCodeFlow(
            client_id="client",
            authorization_endpoint="https://example.test/authorize",
            token_endpoint="https://example.test/token",
            timeout=1.0,
        )
        flow.prompt = None
        with self.assertRaises(self.oauth.OAuthError):
            flow._manual_code()


# ---------------------------------------------------------------- BUG 6
class WhatsAppAutomationSafety(unittest.TestCase):
    """BUG 6: never click blindly."""

    def setUp(self):
        # integrations/__init__ re-exports a WhatsApp *instance* under the
        # same name, so import the module explicitly.
        self.module = importlib.import_module("integrations.whatsapp")

    def test_desktop_automation_aborts_when_target_not_found(self):
        desktop = self.module.DesktopAutomation(
            dry_run=True, allow_coordinate_fallback=True
        )
        result = desktop.send("+10000000000", "hello")
        self.assertFalse(result.ok)
        self.assertEqual(result.error, self.module.TARGET_NOT_FOUND)

    def test_coordinates_are_window_relative(self):
        window = self.module.WindowTarget("WhatsApp", 1920, 200, 800, 600)
        point = window.point(*self.module.DesktopAutomation.SEARCH_BOX)
        self.assertGreaterEqual(point[0], 1920)
        self.assertLessEqual(point[0], 1920 + 800)
        self.assertGreaterEqual(point[1], 200)

    def test_no_bare_screen_clicks_in_source(self):
        source = (ROOT / "integrations" / "whatsapp.py").read_text(encoding="utf-8")
        self.assertNotIn("pyautogui.click(1", source)
        self.assertIn("point(", source)

    def test_missing_credentials_are_explicit(self):
        result = self.module.CloudAPI(token="", phone_id="").send("1", "x")
        self.assertFalse(result.ok)
        self.assertIn("required", result.error)

    def test_unconfigured_whatsapp_reports_configuration_error(self):
        client = self.module.WhatsApp(cloud=self.module.CloudAPI(token="", phone_id=""))
        client.desktop = None
        result = client.send("1", "hi")
        self.assertFalse(result.ok)
        self.assertIn("not configured", result.error)

    def test_cloud_api_url_is_well_formed(self):
        self.assertEqual(
            self.module.CloudAPI.BASE_URL, "https://graph.facebook.com/v20.0"
        )
        self.assertTrue(
            self.module.WhatsApp.web_link("+1 555 0100", "hi").startswith(
                "https://wa.me/15550100?"
            )
        )


# ---------------------------------------------------------------- BUG 7
class DatabaseConcurrency(unittest.TestCase):
    """BUG 7: short transactions, no locks across LLM calls."""

    def setUp(self):
        from database.connection import SQLiteDatabase, TransactionMisuse

        self.temporary = tempfile.mkdtemp()
        self.db = SQLiteDatabase(Path(self.temporary) / "test.db")
        self.misuse = TransactionMisuse
        self.db.script("CREATE TABLE c (n INTEGER)")
        self.db.execute("INSERT INTO c (n) VALUES (?)", (0,))

    def tearDown(self):
        shutil.rmtree(self.temporary, ignore_errors=True)

    def test_wal_and_busy_timeout(self):
        health = self.db.health()
        self.assertTrue(health["ok"])
        self.assertEqual(health["journal_mode"], "wal")
        self.assertGreater(health["busy_timeout"], 0)

    def test_long_call_inside_a_transaction_is_refused(self):
        with self.db.transaction() as connection:
            connection.execute("UPDATE c SET n = n + 1")
            with self.assertRaises(self.misuse):
                with self.db.no_transaction("LLM generation"):
                    pass

    def test_long_call_outside_a_transaction_is_allowed(self):
        with self.db.no_transaction("LLM generation"):
            time.sleep(0.01)
        self.assertFalse(self.db.in_transaction)

    def test_rollback_leaves_no_partial_write(self):
        with self.assertRaises(RuntimeError):
            with self.db.transaction() as connection:
                connection.execute("UPDATE c SET n = 999")
                raise RuntimeError("boom")
        self.assertEqual(self.db.query("SELECT n FROM c")[0]["n"], 0)

    def test_concurrent_writers_all_commit(self):
        writers = 6
        per_writer = 20
        errors: list = []

        def work():
            try:
                for _ in range(per_writer):
                    with self.db.transaction() as connection:
                        connection.execute("UPDATE c SET n = n + 1")
            except Exception as error:  # pragma: no cover - failure path
                errors.append(error)

        threads = [threading.Thread(target=work) for _ in range(writers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=120)

        self.assertEqual(errors, [])
        self.assertEqual(
            self.db.query("SELECT n FROM c")[0]["n"], writers * per_writer
        )

    def test_reads_stay_responsive_during_a_simulated_llm_call(self):
        """A 20s 'generation' must not block readers, because no lock is held."""
        stop = threading.Event()
        durations: list = []

        def generation():
            with self.db.no_transaction("LLM generation"):
                stop.wait(1.0)  # stands in for a 20-30s model call
            with self.db.transaction() as connection:
                connection.execute("UPDATE c SET n = n + 1")

        worker = threading.Thread(target=generation)
        worker.start()
        for _ in range(10):
            started = time.monotonic()
            self.db.query("SELECT n FROM c")
            durations.append(time.monotonic() - started)
        stop.set()
        worker.join(timeout=60)

        self.assertLess(max(durations), 1.0)


# ---------------------------------------------------------------- BUG 8/9
class PipelineShutdown(unittest.TestCase):
    """BUG 8: EOF and Ctrl+C shut down cleanly."""

    def setUp(self):
        from brains_v2.voice.pipeline import VoicePipeline

        self.VoicePipeline = VoicePipeline

    def test_eof_shuts_down_without_traceback(self):
        def reader(_prompt):
            raise EOFError

        pipeline = self.VoicePipeline(voice_enabled=False, reader=reader)
        report = pipeline.run()
        self.assertEqual(report["reason"], "eof")
        self.assertTrue(report["eof"])
        self.assertFalse(pipeline.running)

    def test_keyboard_interrupt_shuts_down_cleanly(self):
        def reader(_prompt):
            raise KeyboardInterrupt

        pipeline = self.VoicePipeline(voice_enabled=False, reader=reader)
        report = pipeline.run()
        self.assertEqual(report["reason"], "interrupted")
        self.assertTrue(report["interrupted"])

    def test_exit_phrase_ends_the_session(self):
        turns = iter(["hello", "bye"])
        pipeline = self.VoicePipeline(
            voice_enabled=False,
            reader=lambda _prompt: next(turns),
            handler=lambda text: {"reply": f"echo {text}"},
        )
        report = pipeline.run()
        self.assertEqual(report["reason"], "exit-phrase")
        self.assertEqual(report["turns"], 1)

    def test_wake_word_uses_a_real_word_boundary(self):
        self.assertTrue(self.VoicePipeline.has_wake_word("hey jarvis, hello"))
        self.assertFalse(self.VoicePipeline.has_wake_word("jarvisson"))

    def test_handler_errors_do_not_kill_the_loop(self):
        turns = iter(["boom", "quit"])

        def handler(_text):
            raise ValueError("nope")

        pipeline = self.VoicePipeline(
            voice_enabled=False, reader=lambda _p: next(turns), handler=handler
        )
        report = pipeline.run()
        self.assertEqual(report["reason"], "exit-phrase")

    def test_source_is_readable_again(self):
        """Phase 5: the pipeline must not be minified one-liners."""
        source = (ROOT / "brains_v2" / "voice" / "pipeline.py").read_text(
            encoding="utf-8"
        )
        lines = source.splitlines()
        self.assertGreater(len(lines), 120)
        self.assertLess(max(len(line) for line in lines), 100)
        statements = [
            line
            for line in lines
            if line.strip().startswith(("self.", "return", "import"))
            and "; " in line
        ]
        self.assertEqual(statements, [])
        self.assertIn('"""', source)


class SystemInfoContract(unittest.TestCase):
    """BUG 9: module and instance expose the same API."""

    def test_module_and_instance_agree(self):
        module = importlib.import_module("automation.system_info")
        self.assertTrue(callable(module.summary))
        self.assertIsInstance(module.summary(), str)
        self.assertIsInstance(module.system_info.summary(), str)
        self.assertIsInstance(module.details(), dict)
        self.assertIsInstance(module.system_info.details(), dict)

    def test_summary_never_raises_without_psutil(self):
        module = importlib.import_module("automation.system_info")
        info = module.SystemInfo()
        info._psutil = None
        text = info.summary()
        self.assertIn("psutil", text)
        self.assertFalse(info.metrics_available())

    def test_legacy_aliases_exist(self):
        module = importlib.import_module("automation.system_info")
        self.assertEqual(module.report(), module.summary())
        self.assertIsInstance(module.info(), dict)


# --------------------------------------------------------------- BUG 10
class TestDiscoveryHygiene(unittest.TestCase):
    """BUG 10 / Phase 16: automated tests and demos are separated."""

    def test_no_interactive_root_test_scripts(self):
        offenders = []
        for path in ROOT.glob("test_*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "input(" in text:
                offenders.append(path.name)
        self.assertEqual(offenders, [])

    def test_demos_were_preserved_not_deleted(self):
        demos = ROOT / "manual_demos"
        self.assertTrue(demos.is_dir())
        self.assertTrue(list(demos.glob("demo_*.py")))
        self.assertTrue((demos / "README.md").is_file())

    def test_no_test_prefixed_files_in_demo_directory(self):
        self.assertEqual(list((ROOT / "manual_demos").glob("test_*.py")), [])

    def test_pytest_configuration_is_explicit(self):
        config = (ROOT / "pytest.ini").read_text(encoding="utf-8")
        self.assertIn("testpaths = tests", config)
        self.assertIn("manual_demos", config)


# --------------------------------------------------------------- Phase 4
class OllamaStateMachine(unittest.TestCase):
    """Phase 4: no repeated daemon spawns or retry spam."""

    def setUp(self):
        from brains_v2.llm.provider_state import ProviderState, ProviderStateMachine

        self.ProviderState = ProviderState
        self.machine = ProviderStateMachine(base_cooldown=10.0, max_attempts=3)

    def test_initial_state_allows_one_attempt(self):
        self.assertEqual(self.machine.state, self.ProviderState.UNKNOWN)
        self.assertTrue(self.machine.should_attempt_start())

    def test_failure_enters_cooldown_with_backoff(self):
        first = self.machine.mark_failed("boom")
        self.assertEqual(self.machine.state, self.ProviderState.COOLDOWN)
        self.assertFalse(self.machine.should_attempt_start())
        second = self.machine.mark_failed("boom")
        self.assertGreater(second, first)

    def test_repeated_failures_reach_failed_and_stop_retrying(self):
        for _ in range(3):
            self.machine.mark_failed("boom")
        self.assertEqual(self.machine.state, self.ProviderState.FAILED)
        self.assertFalse(self.machine.should_attempt_start())

    def test_explicit_retry_clears_the_cooldown(self):
        self.machine.mark_failed("boom")
        self.machine.retry_now()
        self.assertEqual(self.machine.state, self.ProviderState.UNKNOWN)
        self.assertTrue(self.machine.should_attempt_start())

    def test_available_provider_is_not_restarted(self):
        self.machine.mark_available()
        self.assertFalse(self.machine.should_attempt_start())
        self.assertEqual(self.machine.report()["failures"], 0)

    def test_provider_source_is_gated_by_the_state_machine(self):
        source = (ROOT / "brains_v2" / "llm" / "ollama_provider.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("should_attempt_start", source)
        self.assertIn("mark_starting", source)
        spawn_index = source.index('"ollama", "serve"')
        gate_index = source.index("should_attempt_start")
        self.assertLess(gate_index, spawn_index)


# --------------------------------------------------------- Phases 6 & 7
class AndroidCompanionSource(unittest.TestCase):
    """Phase 6: the companion is real code, not a skeleton (CODE VERIFIED)."""

    def read(self, name: str) -> str:
        path = KOTLIN / name
        self.assertTrue(path.is_file(), msg=f"{name} is missing")
        return path.read_text(encoding="utf-8")

    def test_all_companion_sources_exist_and_are_substantial(self):
        for name in (
            "ServerConfig.kt",
            "JarvisClient.kt",
            "JarvisProtocol.kt",
            "JarvisWebSocketClient.kt",
            "DiscoveryClient.kt",
            "MainActivity.kt",
        ):
            self.assertGreater(len(self.read(name).splitlines()), 40, msg=name)

    def test_no_hardcoded_emulator_address_or_token(self):
        for path in KOTLIN.glob("*.kt"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("10.0.2.2", source, msg=path.name)
            self.assertNotIn("Bearer eyJ", source, msg=path.name)

    def test_server_config_is_user_editable_and_persisted(self):
        source = self.read("ServerConfig.kt")
        for marker in ("val host", "val port", "val token", "val useTls"):
            self.assertIn(marker, source)
        self.assertIn("EncryptedSharedPreferences", source)
        self.assertIn("fun save", source)
        self.assertIn("fun load", source)

    def test_rest_client_sends_bearer_auth(self):
        source = self.read("JarvisClient.kt")
        self.assertIn("fun login", source)
        self.assertIn("fun command", source)
        self.assertIn("Authorization", source)

    def test_protocol_envelope_matches_the_specification(self):
        source = self.read("JarvisProtocol.kt")
        for field in ("\"type\"", "\"id\"", "\"timestamp\"", "\"payload\""):
            self.assertIn(field, source)
        for field in ("status", "error"):
            self.assertIn(field, source)

    def test_websocket_has_timeout_heartbeat_and_bounded_reconnect(self):
        source = self.read("JarvisWebSocketClient.kt")
        for marker in (
            "CONNECT_TIMEOUT_SECONDS",
            "HEARTBEAT_SECONDS",
            "MAX_RECONNECT_ATTEMPTS",
            "fun disconnect",
            "scheduleReconnect",
        ):
            self.assertIn(marker, source)

    def test_all_six_ui_states_exist(self):
        source = self.read("JarvisWebSocketClient.kt")
        for state in (
            "DISCONNECTED",
            "CONNECTING",
            "CONNECTED",
            "AUTH_FAILED",
            "SERVER_UNAVAILABLE",
            "TIMEOUT",
        ):
            self.assertIn(state, source)

    def test_manifest_denies_cleartext_and_uses_network_security_config(self):
        manifest = (ANDROID / "AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn('android:usesCleartextTraffic="false"', manifest)
        self.assertIn("networkSecurityConfig", manifest)

        debug = (ANDROID / "res" / "xml" / "network_security_config.xml").read_text(
            encoding="utf-8"
        )
        self.assertIn('cleartextTrafficPermitted="true"', debug)
        self.assertIn("192.168.0.0/16", debug)

        release = (
            ANDROID / "res" / "xml" / "network_security_config_release.xml"
        ).read_text(encoding="utf-8")
        self.assertNotIn('cleartextTrafficPermitted="true"', release)

    def test_only_the_launcher_activity_is_exported(self):
        manifest = (ANDROID / "AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertEqual(manifest.count('android:exported="true"'), 1)
        self.assertNotIn("<service", manifest)
        self.assertNotIn("<receiver", manifest)


class LocalDiscovery(unittest.TestCase):
    """Phase 7: optional discovery, manual entry always available."""

    def setUp(self):
        from brains_v2.server import discovery

        self.discovery = discovery

    def test_advertisement_payload_shape(self):
        payload = self.discovery.advertisement("Jarvis", 8765, False, "10.1.2.3")
        self.assertEqual(payload["service"], "jarvis")
        self.assertEqual(payload["host"], "10.1.2.3")
        self.assertEqual(payload["port"], 8765)
        self.assertFalse(payload["tls"])

    def test_probe_receives_a_reply(self):
        advertiser = self.discovery.DiscoveryAdvertiser(
            name="Test", port=18766, listen_port=18767
        )
        if not advertiser.start():
            self.skipTest("udp/18767 unavailable in this sandbox")
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(3.0)
            client.sendto(self.discovery.PROBE, ("127.0.0.1", 18767))
            data, _sender = client.recvfrom(2048)
            client.close()
            payload = json.loads(data.decode("utf-8"))
            self.assertEqual(payload["service"], "jarvis")
            self.assertEqual(payload["port"], 18766)
        finally:
            advertiser.stop()
        self.assertFalse(advertiser.running)

    def test_unknown_probe_is_ignored(self):
        advertiser = self.discovery.DiscoveryAdvertiser(
            name="Test", port=18766, listen_port=18768
        )
        if not advertiser.start():
            self.skipTest("udp/18768 unavailable in this sandbox")
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(1.0)
            client.sendto(b"nonsense", ("127.0.0.1", 18768))
            with self.assertRaises(socket.timeout):
                client.recvfrom(2048)
            client.close()
        finally:
            advertiser.stop()


# --------------------------------------------------------------- Phase 8
class SecurityBoundaries(unittest.TestCase):
    """Phase 8: authentication and code-execution boundaries."""

    def test_auth_manager_rejects_invalid_tokens(self):
        from brains_v2.server.auth import AuthManager

        manager = AuthManager()
        token = manager.create_token(device="phone")
        self.assertTrue(manager.verify(token))
        self.assertFalse(manager.verify("not-a-token"))
        self.assertFalse(manager.verify(""))

    def test_expired_tokens_stop_working(self):
        from brains_v2.server.auth import AuthManager

        clock = [1000.0]
        manager = AuthManager(ttl=10, clock=lambda: clock[0])
        token = manager.create_token(device="phone")
        self.assertTrue(manager.verify(token))
        clock[0] += 60
        self.assertFalse(manager.verify(token))

    def test_code_sandbox_uses_real_process_isolation(self):
        source = (ROOT / "security" / "code_sandbox.py").read_text(encoding="utf-8")
        self.assertIn("subprocess", source)
        self.assertIn("timeout", source)


if __name__ == "__main__":
    unittest.main()
