"""
==========================================
JARVIS PRO
Install verifier
==========================================

Run this straight after copying a new build over your project folder:

    python tools\\verify_build.py

It checks that the files which must exist really exist, and that the
files which must be the NEW version really are the new version.  A half
finished copy (some new files, some old ones left behind) is the usual
reason for errors like "generate() takes 2 positional arguments but 3
were given" and for tests failing in a folder where they used to pass.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# file -> text that must appear inside it
MARKERS = {
    "tests/test_conversation_features.py": "def test_ai_cliches_are_stripped",
    "conversation/topic_tracker.py": "RETURN_MARKERS",
    "conversation/interruption.py": "CONTINUE_PREFIXES",
    "conversation/entity_tracker.py": "AMBIGUOUS_TERMS",
    "conversation/temporal_parser.py": "_all_relative_days",
    "conversation/style_controller.py": "_ROTATION",
    "conversation/response_quality.py": "internal_content",
    "conversation/correction_handler.py": "MARKER_PREFIX",
    "conversation/incomplete_sentence.py": "MODAL_WORDS",
    "conversation/dialogue_memory.py": "{subject}_uses",
    "conversation/repetition_detector.py": "as a language model",
    "brains_v2/llm/ollama_provider.py": "_server_listening",
    "tools/check_ollama.py": "def probe(",
    "tests/test_ollama_service.py": "def test_second_server_is_not_started_when_the_port_is_busy",
    "conversation/request_splitter.py": "def split(",
    "conversation/reference_resolver.py": "ACTIONABLE_TYPES",
    "conversation/ambiguity_detector.py": "def missing_slots(",
    "conversation/clarification_manager.py": "missing_parameters",
    "brains_v2/goals.py": "def execute(self, command",
    "brains_v2/intents/memory_intent.py": "request_splitter",
    "memory/memory_engine.py": "def process_memory(",
    "automation/apps.py": "def match_app(",
    "brains_v2/router_v2.py": "target = match_app(command)",
    "brains_v2/manager.py": "action_word and match_app(command)",
    "brains_v2/controllers/memory_controller.py": 'memory_intent.get("question")',
    "tests/test_conversation_repair.py": "def test_planner_exposes_execute_and_declines_questions",
    "brains_v2/llm/manager.py": "response_generator.generate",
    "brains_v2/llm/prompt_builder.py": "def build(",
    "brains_v2/trace.py": "pipeline_debug",
    "brains_v2/adaptive.py": '"talks"',
    "brains_v2/style.py": "def apply",
    "brains_v2/controllers/reply_controller.py": "def process",
    "conversation/conversation_engine.py": "greeting_reply",
    "conversation/dialogue_manager.py": "_STEP_FILE",
    "install_to_project.py": "def merge_settings",
    "conversation/response_generator.py": "def generate",
    "conversation/response_planner.py": "class ResponsePlan",
    "conversation/response_memory.py": "def times_asked",
    "conversation/response_quality.py": "class QualityReport",
    "conversation/question_similarity.py": "def same_request",
    "conversation/repetition_detector.py": "def similarity",
    "conversation/style_controller.py": "def parameters",
    "tools/run_tests.py": "def run_file",
    "tools/try_variation.py": "def report",
    "tools/repro_same_answer.py": "def new_path",
    "tests/test_conversation_system.py": "def test_greeting_is_answered_not_executed",
    "tests/test_response_variation.py": "def test_spec_1_same_question_many_times",
    "tests/test_greeting_variation.py": "def test_hundred_hellos_are_not_the_same_line",
    "tests/test_voice_interruption.py": "def test_tts_stop_interrupts_and_clears_the_queue",
    "conversation/output_sanitizer.py": "def final_user_response",
    "conversation/request_type.py": "def is_action_request",
    "conversation/request_splitter.py": "def split",
    "conversation/reference_resolver.py": "ACTIONABLE_TYPES",
    "conversation/ambiguity_detector.py": "def missing_slots",
    "conversation/clarification_manager.py": "class ClarificationManager",
    "brains_v2/goals.py": "def execute",
    "brains_v2/router_v2.py": "is_action_request",
    "brains_v2/manager.py": "is_action_request",
    "brains_v2/context.py": "Application state is not conversation topic",
    "brains_v2/response.py": "What would you like me to open?",
    "memory/memory_engine.py": "def last_fact",
    "brains_v2/intents/memory_intent.py": "def detect",
    "automation/apps.py": "def match_app",
    "tests/test_conversation_repair.py": "def test_router_guards_the_automation_route",
    "tests/test_conversation_repair_v2.py": "def test_tagged_thinking_block_is_removed",
    "brains_v2/reply_text.py": "def reply_text(",
    "brains_v2/voice/pipeline.py": "reply_text(reply)",
    "automation/apps.py": "def is_close_request",
    "conversation/output_sanitizer.py": "PROMPT_ECHO",
    "memory/memory_engine.py": "CHANGE_KEY_TO",
    "tests/test_live_pipeline_repair.py": "def test_prompt_echo_is_recognised_as_internal",
    "config/settings.json": "response_diversity",
}


def main() -> int:
    missing = []
    stale = []

    for relative, marker in MARKERS.items():
        path = os.path.join(ROOT, relative.replace("/", os.sep))

        if not os.path.exists(path):
            missing.append(relative)
            continue

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError as error:
            stale.append(f"{relative} (unreadable: {error})")
            continue

        if marker not in text:
            stale.append(relative)

    print("=" * 68)
    print("JARVIS PRO - install check")
    print("=" * 68)
    print(f"project folder : {ROOT}")
    print(f"files checked  : {len(MARKERS)}")

    if not missing and not stale:
        print("result         : OK - this folder has the complete new build")
        print("=" * 68)
        return 0

    if missing:
        print("\nMISSING FILES (the copy did not finish):")
        for item in missing:
            print(f"  - {item}")

    if stale:
        print("\nOLD VERSIONS STILL IN PLACE (overwrite these):")
        for item in stale:
            print(f"  - {item}")

    print("\nFix it by copying the whole new folder again, for example:")
    print('  robocopy "<extracted folder>" "%s" /E /IS /IT' % ROOT)
    print("=" * 68)
    return 1


if __name__ == "__main__":
    sys.exit(main())
