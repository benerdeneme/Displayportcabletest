# Development roadmap

These are planned investigations, not completed features. The first priority is trustworthy output and reproducible hardware reports.

| Priority | Work item | Completion evidence |
| --- | --- | --- |
| P0 | Distinguish measured, reported, inferred and unavailable values in CLI/GUI output | Reports label each class; missing data cannot produce a reassuring score |
| P0 | Verify AUX-to-connector mapping with multiple displays | Fixtures and a manual two-monitor test; ambiguous mapping stays unknown |
| P0 | Validate legacy and UHBR capability/active-rate interpretation | Public upstream references and fixtures covering capable devices running at lower negotiated rates |
| P1 | Harden EDID parsing for malformed, truncated and invalid-checksum data | Anonymized or synthetic fixtures with documented expected behavior |
| P1 | Validate lane status for one-, two- and four-lane links | Unused lanes are excluded from synchronization results |
| P1 | Replace inferred HDR/adaptive-sync labels with evidence-based capability reporting | Capability-specific evidence or an explicit unknown value |
| P1 | Document real Windows/Linux hardware results | OS, driver, topology and repeatable commands; no invented compatibility claims |
| P2 | Add machine-readable output and anonymized diagnostic export | Stable schema and tests for unknown values and removed identifiers |

## First release gate

- Hardware-free CI passes on supported Python versions.
- Known limitations are visible in the README and release notes.
- At least one real Linux and one real Windows report have been reviewed before claiming hardware validation on both.
- Binary packaging is tested before distributing executables.

See [CONTRIBUTING.md](CONTRIBUTING.md) to help with one item.
