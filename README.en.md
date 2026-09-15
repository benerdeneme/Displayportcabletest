# DisplayPort Cable Test

Experimental Python tools for inspecting display connection information, with a Linux CLI, a Linux GUI and a separate Windows GUI.

[Türkçe](README.md) · [Contributing](CONTRIBUTING.md) · [Roadmap](ROADMAP.md)

## Try it in one minute

Requires Python 3.11 or later. The CLI and tests use only the standard library.

```sh
git clone https://github.com/benerdeneme/Displayportcabletest.git
cd Displayportcabletest
python dp_cable_test.py --demo
python -m unittest discover -s tests -v
```

The demo uses synthetic data. No monitor, administrator privileges or display server is required. See [sample output](docs/demo-output.txt).

## What it does

| Entry point | Purpose |
| --- | --- |
| `dp_cable_test.py` | Linux CLI; reads exposed DRM AUX data and EDID |
| `dp_cable_test_gui.py` | Linux tkinter interface with a demo mode |
| `cable_test_windows_gui.py` | Separate Windows tkinter interface using Windows display information |
| `dp_core.py` | Linux analysis, EDID parsing and shared calculations |

The Linux analysis reports device capability fields, available link status, lane synchronization, and estimated bandwidth and resolution budgets.

## Real hardware

Linux needs a driver exposing `/dev/drm_dp_aux*` and `/sys/class/drm`. The current hardware CLI requires root:

```sh
sudo python3 dp_cable_test.py
sudo python3 dp_cable_test_gui.py
```

For a GUI demo: `python3 dp_cable_test_gui.py --demo`. Install your distribution's tkinter package if it is missing. On Windows, run `python cable_test_windows_gui.py` with a Python installation that includes tkinter. Windows and Linux use different data sources; their reports are not equivalent.

## Interpreting results

This is an experimental diagnostic aid. It does not certify a cable or measure physical signal integrity. Device capabilities and DPCD revision do not establish a cable's version. The quality score is heuristic, and resolution estimates do not prove that a monitor supports a mode. Some feature labels, including HDR and adaptive sync, are inferred rather than verified.

AUX-to-connector fallback can select the wrong device on multi-monitor systems. UHBR interpretation, incomplete reads and inferred feature labels need further validation; see the [roadmap](ROADMAP.md). Do not treat synthetic tests as hardware certification.

## Develop with Codespaces and Copilot

Open **Code → Codespaces → Create codespace**. The repository configuration sets up Python and runs the hardware-free tests. Codespaces cannot access the display cable connected to your own computer; use it for the CLI demo, fixtures and documentation. Desktop GUI testing needs a local desktop environment.

Repository-specific Copilot instructions describe the architecture, test command and evidence required for hardware claims. Copilot access depends on your account's active entitlement.

Contributions in Turkish or English are welcome. Start with the [contribution guide](CONTRIBUTING.md).

## License

MIT, as declared in the original project README.
