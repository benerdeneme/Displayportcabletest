# Contributing / Katkıda bulunma

Bug reports, documentation improvements and reproducible hardware observations are welcome in Turkish or English.

## Local development

1. Fork the repository and create a branch for one specific change.
2. Use Python 3.11 or later. No pip packages are needed for the CLI or tests.
3. Run:

```sh
python -m unittest discover -s tests -v
python dp_cable_test.py --demo
```

The same commands work in Codespaces without display hardware. Real hardware testing belongs on a local machine; tkinter windows require a desktop session.

## Good first contributions

- Improve English or Turkish setup instructions after trying them yourself.
- Report a reproducible device mismatch with the GPU, OS and connection topology.
- Add an anonymized EDID fixture and a test for a parsing issue.
- Investigate one item in [ROADMAP.md](ROADMAP.md), with evidence and an explicit expected result.

Check existing issues before starting substantial work. A focused patch is easier to review.

## Hardware reports

Include OS and Python versions, GPU/driver, monitor model, adapters/docks, command, expected result and actual result. Say whether you used `--demo`. Remove serial numbers, personal paths and unrelated device information from reports or screenshots. Synthetic examples should be clearly labeled.

For new hardware claims, link the relevant public specification or upstream driver source and explain how the observed data supports the claim. Device capabilities, negotiated link state and physical cable properties are different kinds of evidence.

## Pull requests

Describe the problem and the changed behavior. Include test commands and results. For a fix, include a regression test when it can reproduce the problem without hardware; otherwise document a repeatable manual procedure. Report platforms you actually tested, and mark other platforms as untested.

AI-assisted changes follow the same review process: understand the patch, verify factual claims, run checks and disclose relevant limitations.
