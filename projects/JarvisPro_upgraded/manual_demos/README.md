# Manual demos

These scripts used to sit at the project root named `test_*.py`, so
pytest collected them and some blocked collection on `input()`.
They are demonstrations, not automated tests, so they were renamed
`demo_*.py` and moved here. Nothing was deleted.

Run one from the project root, for example:

```bash
python3 manual_demos/demo_voice.py
```

Automated tests live in `tests/` and are discovered by pytest
(see `pytest.ini`) or the offline runner `python3 run_tests.py`.
