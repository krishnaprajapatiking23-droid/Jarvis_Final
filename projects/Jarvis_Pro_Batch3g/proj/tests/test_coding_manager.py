from brains_v2.manager_modules import coding_manager


def fake_ask(prompt):
    return "Problem: x is undefined. Fix: x = 0\nprint(x)"


def test_generate_python_code(monkeypatch):
    monkeypatch.setattr(coding_manager, "ask", fake_ask)

    result = coding_manager.process("write python hello world")

    assert isinstance(result, dict)
    assert result["type"] == "coding"
    assert result["reply"]


def test_debug_python_code(monkeypatch):
    monkeypatch.setattr(coding_manager, "ask", fake_ask)

    result = coding_manager.process(
        "debug this python code: print(x)"
    )

    assert isinstance(result, dict)
    assert result["type"] == "coding"
    assert result["reply"]

    reply = result["reply"].lower()

    assert "x" in reply
    assert "undefined" in reply or "fix" in reply


def test_project_search():
    result = coding_manager.process(
        "search project for BEHAVIOR_RULES"
    )

    assert isinstance(result, dict)
    assert result["type"] == "coding"
    assert "BEHAVIOR_RULES" in result["reply"]
