# Repository instructions

This project is an experimental display diagnostic utility, written in Python 3.11+ using the standard library. Read README.en.md and ROADMAP.md before changing hardware interpretation.

- Linux shared analysis lives in dp_core.py; its CLI is dp_cable_test.py and GUI is dp_cable_test_gui.py. The Windows GUI is separate and uses Windows APIs.
- Keep hardware-free code importable on Linux and Windows. Avoid adding runtime dependencies unless the change needs them.
- Use `python -m unittest discover -s tests -v` and `python dp_cable_test.py --demo` for validation. Do not run privileged hardware commands automatically.
- Keep measured values, device-reported capabilities, estimates and unknown data distinct. Never infer physical cable certification from DPCD revision or device capabilities.
- Hardware register changes require a relevant public upstream/specification reference and meaningful fixture tests. Synthetic tests do not establish hardware compatibility.
- Test GUI changes locally on the relevant OS and describe untested platforms honestly.
- Keep Turkish and English documentation consistent. Avoid unrelated refactoring.
- Explain the problem, behavior change, validation and limitations in each PR. Never invent adoption metrics, contributors or hardware results.
