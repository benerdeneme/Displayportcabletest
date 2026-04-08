#!/usr/bin/env python3
"""
DisplayPort / HDMI Kablo Test Programi - Windows GUI
=====================================================
Bagli DisplayPort veya HDMI kablonun versiyonunu, kalitesini
ve destekledigi teknolojileri analiz eder.

* Windows 10/11 uzerinde calisir (yonetici yetkisi gerekmez)
* DisplayPort VE HDMI kablo destegi
* EDID Windows kayit defterinden okunur
* HDMI versiyonu CEA-861 eklenti blogundan algilanir
* DP bant genisligi EDID zamanlamalarindan tahmin edilir
  (Linux aksine Windows'ta DPCD dogrudan okunamaz)

Kullanim: python cable_test_windows_gui.py
"""

import os
import sys
import json
import subprocess
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field

if sys.platform == "win32":
    import winreg  # type: ignore[import]
else:
    winreg = None  # type: ignore[assignment]

import tkinter as tk
from tkinter import ttk

# ============================================================
# Renk Paleti
# ============================================================
BG_DARK       = "#1a1a2e"
BG_CARD       = "#16213e"
BG_CARD2      = "#0f3460"
FG_TEXT       = "#e0e0e0"
FG_DIM        = "#888899"
ACCENT_BLUE   = "#00adb5"
ACCENT_GREEN  = "#00e676"
ACCENT_RED    = "#ff5252"
ACCENT_YELLOW = "#ffd740"
ACCENT_ORANGE = "#ff9100"
ACCENT_CYAN   = "#18ffff"
ACCENT_PURPLE = "#b388ff"
BAR_BG        = "#2a2a4a"

# ============================================================
# Windows API Yapilari
# ============================================================
class DISPLAY_DEVICE(ctypes.Structure):
    _fields_ = [
        ("cb",           wintypes.DWORD),
        ("DeviceName",   ctypes.c_wchar * 32),
        ("DeviceString", ctypes.c_wchar * 128),
        ("StateFlags",   wintypes.DWORD),
        ("DeviceID",     ctypes.c_wchar * 128),
        ("DeviceKey",    ctypes.c_wchar * 128),
    ]

# WMI VideoOutputTechnology kodlari
VIDEO_OUTPUT_TECH: dict = {
    0:          "VGA",
    1:          "S-Video",
    2:          "Kompozit",
    3:          "Komponent",
    4:          "DVI",
    5:          "HDMI",
    6:          "LVDS",
    9:          "SDI",
    10:         "DisplayPort",
    11:         "UDI",
    12:         "DisplayPort (Gomulu)",
    13:         "MHL",
    0xFFFFFFFF: "Bilinmiyor",
}

# HDMI versiyonu -> maksimum bant genisligi (Gbps)
HDMI_BANDWIDTH: dict = {
    "1.0": 4.95,  "1.1": 4.95,  "1.2": 4.95,
    "1.3": 10.2,  "1.4": 10.2,
    "2.0": 18.0,  "2.0a": 18.0, "2.0b": 18.0,
    "2.1": 48.0,
}

# DP efektif bant genisligi (4 lane, 8b/10b overhead sonrasi)
DP_BANDWIDTH: dict = {
    "1.0": 6.48,   # 4 x RBR  x 0.80
    "1.1": 8.64,   # 4 x HBR  x 0.80
    "1.2": 17.28,  # 4 x HBR2 x 0.80
    "1.4": 25.92,  # 4 x HBR3 x 0.80
    "2.0": 77.37,  # UHBR20 x 4 x 0.964 (128b/132b)
}

# ============================================================
# Veri Yapilari
# ============================================================
@dataclass
class EDIDInfo:
    manufacturer: str = ""
    model_name: str = ""
    serial: str = ""
    max_hpixels: int = 0
    max_vpixels: int = 0
    max_refresh: float = 0.0
    year: int = 0
    week: int = 0
    edid_version: str = ""
    max_pixel_clock_mhz: float = 0.0
    detailed_timings: list = field(default_factory=list)


@dataclass
class HDMICapabilities:
    is_hdmi: bool = False
    version: str = "Bilinmiyor"
    max_bandwidth_gbps: float = 0.0
    max_tmds_clock_mhz: int = 0
    has_arc: bool = False
    has_earc: bool = False
    has_vrr: bool = False
    has_allm: bool = False
    has_hdr10: bool = False
    has_dolby_vision: bool = False
    has_ycbcr444: bool = False
    has_ycbcr422: bool = False
    has_ycbcr420: bool = False
    has_deep_color: bool = False
    has_3d: bool = False
    has_cec: bool = False
    scdc_present: bool = False


@dataclass
class DPCapabilities:
    estimated_version: str = "Bilinmiyor"
    max_bandwidth_gbps: float = 0.0
    note: str = "DPCD Windows'ta dogrudan okunamiyor; EDID zamanlamalarindan tahmin edildi"


@dataclass
class CableAnalysis:
    connector_name: str = ""
    connector_type: str = "Bilinmiyor"
    device_id: str = ""
    is_active: bool = False
    edid: object = None  # EDIDInfo | None
    hdmi: HDMICapabilities = field(default_factory=HDMICapabilities)
    dp: DPCapabilities = field(default_factory=DPCapabilities)
    current_width: int = 0
    current_height: int = 0
    current_refresh: int = 0
    max_bandwidth_gbps: float = 0.0
    effective_bandwidth_gbps: float = 0.0
    quality_score: int = 0
    quality_grade: str = ""
    issues: list = field(default_factory=list)
    supported_features: list = field(default_factory=list)
    max_resolutions: list = field(default_factory=list)


# ============================================================
# EDID Parser
# ============================================================
def parse_edid(raw: bytes):
    """Ham EDID baytlarini EDIDInfo yapisina donusturur."""
    if len(raw) < 128 or raw[0:8] != b'\x00\xff\xff\xff\xff\xff\xff\x00':
        return None

    info = EDIDInfo()

    mfg_id = (raw[8] << 8) | raw[9]
    c1 = chr(((mfg_id >> 10) & 0x1F) + ord('A') - 1)
    c2 = chr(((mfg_id >> 5)  & 0x1F) + ord('A') - 1)
    c3 = chr((mfg_id         & 0x1F) + ord('A') - 1)
    info.manufacturer = f"{c1}{c2}{c3}"

    info.week         = raw[16]
    info.year         = raw[17] + 1990
    info.edid_version = f"{raw[18]}.{raw[19]}"

    for i in range(4):
        offset = 54 + i * 18
        block  = raw[offset:offset + 18]

        if block[0] == 0 and block[1] == 0:
            tag = block[3]
            if tag == 0xFC:
                info.model_name = block[5:18].decode('ascii', errors='ignore').strip()
            elif tag == 0xFF:
                info.serial = block[5:18].decode('ascii', errors='ignore').strip()
            elif tag == 0xFD:
                info.max_refresh = block[8]
        else:
            pixel_clock_hz = (block[1] << 8 | block[0]) * 10000
            if pixel_clock_hz == 0:
                continue
            pixel_clock_mhz = pixel_clock_hz / 1e6
            h_active = ((block[4] & 0xF0) << 4) | block[2]
            v_active = ((block[7] & 0xF0) << 4) | block[5]
            h_blank  = ((block[4] & 0x0F) << 8) | block[3]
            v_blank  = ((block[7] & 0x0F) << 8) | block[6]
            h_total  = h_active + h_blank
            v_total  = v_active + v_blank

            if h_total > 0 and v_total > 0:
                refresh = pixel_clock_hz / (h_total * v_total)
                info.detailed_timings.append(
                    (h_active, v_active, refresh, pixel_clock_mhz)
                )
                if h_active > info.max_hpixels:
                    info.max_hpixels = h_active
                    info.max_vpixels = v_active
                if refresh > info.max_refresh:
                    info.max_refresh = refresh
                if pixel_clock_mhz > info.max_pixel_clock_mhz:
                    info.max_pixel_clock_mhz = pixel_clock_mhz

    return info


# ============================================================
# CEA-861 / HDMI Parser
# ============================================================
def parse_cea_hdmi(raw: bytes) -> HDMICapabilities:
    """CEA-861 eklenti blogunu parse ederek HDMI yeteneklerini belirler.

    HDMI VSDB (OUI 0x000C03) varsa monitor HDMI uzerinden baglidir.
    DisplayPort baglantilari bu blogu genellikle icermez.
    """
    caps = HDMICapabilities()

    if len(raw) < 256 or raw[128] != 0x02:
        return caps

    cea = raw[128:256]

    if len(cea) > 3:
        caps.has_ycbcr444 = bool(cea[3] & 0x20)
        caps.has_ycbcr422 = bool(cea[3] & 0x10)

    dtd_offset = cea[2] if len(cea) > 2 else 0
    if dtd_offset < 4:
        return caps

    pos = 4
    while pos < dtd_offset and pos < len(cea) - 1:
        tag_code  = (cea[pos] >> 5) & 0x07
        block_len = cea[pos] & 0x1F

        if pos + block_len >= len(cea):
            break

        if tag_code == 0x03 and block_len >= 3:
            oui = (cea[pos + 3] << 16) | (cea[pos + 2] << 8) | cea[pos + 1]

            if oui == 0x000C03:
                # HDMI VSDB — HDMI 1.x imzasi
                caps.is_hdmi = True
                caps.has_cec = True

                if block_len >= 6 and (pos + 6) < len(cea):
                    b6 = cea[pos + 6]
                    caps.has_deep_color = bool(b6 & 0x78)
                    caps.has_3d         = bool(b6 & 0x02)

                if block_len >= 7 and (pos + 7) < len(cea):
                    caps.max_tmds_clock_mhz = cea[pos + 7] * 5

                if block_len >= 8 and (pos + 8) < len(cea):
                    b8 = cea[pos + 8]
                    caps.has_3d  = caps.has_3d or bool(b8 & 0x80)
                    caps.has_arc = bool(b8 & 0x40)

                tmds = caps.max_tmds_clock_mhz or 165
                if tmds > 165:
                    caps.version           = "1.4"
                    caps.max_bandwidth_gbps = HDMI_BANDWIDTH["1.4"]
                elif tmds > 74:
                    caps.version           = "1.3"
                    caps.max_bandwidth_gbps = HDMI_BANDWIDTH["1.3"]
                else:
                    caps.version           = "1.2"
                    caps.max_bandwidth_gbps = HDMI_BANDWIDTH["1.2"]

            elif oui == 0xC45DD8:
                # HF-VSDB — HDMI Forum (HDMI 2.0/2.1)
                caps.is_hdmi      = True
                caps.scdc_present = True
                caps.has_cec      = True

                if block_len >= 5 and (pos + 5) < len(cea):
                    tmds = cea[pos + 5] * 5
                    caps.max_tmds_clock_mhz = max(caps.max_tmds_clock_mhz, tmds)

                if block_len >= 6 and (pos + 6) < len(cea):
                    b6 = cea[pos + 6]
                    caps.has_vrr  = bool(b6 & 0x04)
                    caps.has_allm = bool(b6 & 0x02)
                    caps.has_earc = bool(b6 & 0x01)
                    caps.has_arc  = caps.has_arc or caps.has_earc

                tmds2 = caps.max_tmds_clock_mhz
                if tmds2 > 340:
                    caps.version            = "2.1"
                    caps.max_bandwidth_gbps = HDMI_BANDWIDTH["2.1"]
                else:
                    caps.version            = "2.0"
                    caps.max_bandwidth_gbps = HDMI_BANDWIDTH["2.0"]

        elif tag_code == 0x07 and block_len >= 1:
            ext_tag = cea[pos + 1]
            if   ext_tag == 0x06: caps.has_hdr10       = True
            elif ext_tag == 0x0B: caps.has_ycbcr420    = True
            elif ext_tag == 0x13: caps.has_dolby_vision = True

        pos += 1 + block_len
        if block_len == 0:
            break

    return caps


# ============================================================
# DP Kapasite Tahmini (EDID'den)
# ============================================================
def estimate_dp_capabilities(edid) -> DPCapabilities:
    """EDID zamanlama verilerinden minimum DP versiyonu/bant genisligi tahmin eder."""
    dp = DPCapabilities()
    if not edid or not edid.max_hpixels:
        return dp

    w  = edid.max_hpixels or 1920
    h  = edid.max_vpixels or 1080
    hz = edid.max_refresh or 60.0

    required_gbps = (w * h * 24 * hz * 1.06) / 1e9

    if   required_gbps <= DP_BANDWIDTH["1.0"]:
        dp.estimated_version = "1.0"; dp.max_bandwidth_gbps = DP_BANDWIDTH["1.0"]
    elif required_gbps <= DP_BANDWIDTH["1.1"]:
        dp.estimated_version = "1.1"; dp.max_bandwidth_gbps = DP_BANDWIDTH["1.1"]
    elif required_gbps <= DP_BANDWIDTH["1.2"]:
        dp.estimated_version = "1.2"; dp.max_bandwidth_gbps = DP_BANDWIDTH["1.2"]
    elif required_gbps <= DP_BANDWIDTH["1.4"]:
        dp.estimated_version = "1.4"; dp.max_bandwidth_gbps = DP_BANDWIDTH["1.4"]
    else:
        dp.estimated_version = "2.0+"; dp.max_bandwidth_gbps = DP_BANDWIDTH["2.0"]

    return dp


# ============================================================
# Windows Ekran Bilgisi Toplama
# ============================================================
def _run_ps(script: str, timeout: int = 15) -> str:
    """Gizli bir PowerShell oturumu acarak scripti calistirir."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
            creationflags=flags,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def get_wmi_monitors() -> list:
    """WMI araciligiyla bagli monitor bilgilerini toplar."""
    script = r"""
$c = @{}
try {
    Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorConnectionParams -EA Stop |
        ForEach-Object { $c[$_.InstanceName] = $_.VideoOutputTechnology }
} catch {}

$res = @()
Get-CimInstance Win32_VideoController |
    Where-Object { $_.CurrentHorizontalResolution -gt 0 } |
    ForEach-Object {
        $t = 4294967295
        $pid2 = $_.PNPDeviceID -replace '\\','_'
        foreach ($k in $c.Keys) {
            if ($k -match [regex]::Escape($pid2)) { $t = $c[$k]; break }
        }
        $res += [PSCustomObject]@{
            Name    = $_.Name
            Width   = [int]$_.CurrentHorizontalResolution
            Height  = [int]$_.CurrentVerticalResolution
            Refresh = [int]$_.CurrentRefreshRate
            VideoOutputTechnology = [long]$t
            DeviceID = $_.PNPDeviceID
        }
    }
if ($res.Count -eq 0) { Write-Output '[]' } else { $res | ConvertTo-Json -Compress }
"""
    raw = _run_ps(script)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return data or []
    except Exception:
        return []


def get_display_device_names() -> list:
    """EnumDisplayDevicesW ile adaptore bagli monitor adlarini listeler."""
    if sys.platform != "win32":
        return []

    result = []
    user32 = ctypes.windll.user32
    i = 0
    while True:
        adapter = DISPLAY_DEVICE()
        adapter.cb = ctypes.sizeof(DISPLAY_DEVICE)
        if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(adapter), 0):
            break
        if adapter.StateFlags & 0x1:
            j = 0
            while True:
                mon = DISPLAY_DEVICE()
                mon.cb = ctypes.sizeof(DISPLAY_DEVICE)
                if not user32.EnumDisplayDevicesW(
                    adapter.DeviceName, j, ctypes.byref(mon), 0
                ):
                    break
                result.append({
                    "adapter":      adapter.DeviceName,
                    "adapter_desc": adapter.DeviceString,
                    "monitor_id":   mon.DeviceID,
                    "monitor_desc": mon.DeviceString,
                })
                j += 1
        i += 1
    return result


def read_all_edids_from_registry() -> list:
    """Windows kayit defterinden tum monitor EDID'lerini okur.

    Yol: HKLM\\SYSTEM\\CurrentControlSet\\Enum\\DISPLAY\\{id}\\{inst}\\Device Parameters\\EDID
    """
    if winreg is None:
        return []

    results = []
    base_path = r"SYSTEM\CurrentControlSet\Enum\DISPLAY"

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_path) as base_key:
            i = 0
            while True:
                try:
                    monitor_id   = winreg.EnumKey(base_key, i)
                    monitor_path = f"{base_path}\\{monitor_id}"
                    try:
                        with winreg.OpenKey(
                            winreg.HKEY_LOCAL_MACHINE, monitor_path
                        ) as mk:
                            j = 0
                            while True:
                                try:
                                    instance_id = winreg.EnumKey(mk, j)
                                    edid_key    = (
                                        f"{monitor_path}\\{instance_id}"
                                        r"\Device Parameters"
                                    )
                                    try:
                                        with winreg.OpenKey(
                                            winreg.HKEY_LOCAL_MACHINE, edid_key
                                        ) as pk:
                                            try:
                                                edid_val, _ = winreg.QueryValueEx(pk, "EDID")
                                                results.append({
                                                    "monitor_id":  monitor_id,
                                                    "instance_id": instance_id,
                                                    "edid_raw":    bytes(edid_val),
                                                    "device_path": (
                                                        f"DISPLAY\\"
                                                        f"{monitor_id}\\"
                                                        f"{instance_id}"
                                                    ),
                                                })
                                            except FileNotFoundError:
                                                pass
                                    except (PermissionError, FileNotFoundError, OSError):
                                        pass
                                    j += 1
                                except OSError:
                                    break
                    except (PermissionError, OSError):
                        pass
                    i += 1
                except OSError:
                    break
    except (PermissionError, FileNotFoundError, OSError):
        pass

    return results


# ============================================================
# Analiz
# ============================================================
def find_monitors() -> list:
    """Bagli tum monitorleri bulur ve analiz eder."""
    wmi_mons   = get_wmi_monitors()
    edid_recs  = read_all_edids_from_registry()

    # WMI sonuc gelmezse WinAPI fallback
    if not wmi_mons:
        for d in get_display_device_names():
            wmi_mons.append({
                "Name":    d.get("adapter_desc", "Ekran"),
                "Width":   0, "Height": 0, "Refresh": 0,
                "VideoOutputTechnology": 0xFFFFFFFF,
                "DeviceID": d.get("monitor_id", ""),
            })

    if not wmi_mons and edid_recs:
        for rec in edid_recs:
            wmi_mons.append({
                "Name":    rec["monitor_id"],
                "Width":   0, "Height": 0, "Refresh": 0,
                "VideoOutputTechnology": 0xFFFFFFFF,
                "DeviceID": rec["device_path"],
            })

    analyses = []
    for idx, mon in enumerate(wmi_mons):
        raw_edid    = None
        device_path = mon.get("DeviceID", "")

        # Hardware ID parcasiyla EDID eslestirmesi
        mon_hw = ""
        parts  = device_path.split("\\")
        if len(parts) >= 2:
            mon_hw = parts[1].upper()

        for rec in edid_recs:
            if mon_hw and rec["monitor_id"].upper() == mon_hw:
                raw_edid    = rec["edid_raw"]
                device_path = device_path or rec["device_path"]
                break

        if raw_edid is None and edid_recs:
            pick     = edid_recs[idx] if idx < len(edid_recs) else edid_recs[0]
            raw_edid = pick["edid_raw"]
            device_path = device_path or pick["device_path"]

        edid_info = parse_edid(raw_edid) if raw_edid else None
        tech_code = int(mon.get("VideoOutputTechnology", 0xFFFFFFFF))
        conn_type = VIDEO_OUTPUT_TECH.get(tech_code, "Bilinmiyor")

        analyses.append(analyze_monitor(
            connector_name  = mon.get("Name", f"Ekran {idx + 1}"),
            connector_type  = conn_type,
            device_id       = device_path,
            edid_raw        = raw_edid,
            edid_info       = edid_info,
            current_width   = int(mon.get("Width",   0) or 0),
            current_height  = int(mon.get("Height",  0) or 0),
            current_refresh = int(mon.get("Refresh", 0) or 0),
        ))

    return analyses


def analyze_monitor(
    connector_name: str, connector_type: str, device_id: str,
    edid_raw, edid_info,
    current_width: int, current_height: int, current_refresh: int,
) -> CableAnalysis:
    a = CableAnalysis()
    a.connector_name  = connector_name
    a.connector_type  = connector_type
    a.device_id       = device_id
    a.edid            = edid_info
    a.current_width   = current_width
    a.current_height  = current_height
    a.current_refresh = current_refresh
    a.is_active       = bool(current_width and current_height)

    if edid_raw:
        a.hdmi = parse_cea_hdmi(edid_raw)
        # CEA'daki HDMI VSDB baglanti tipini onaylar
        if a.hdmi.is_hdmi and connector_type == "Bilinmiyor":
            a.connector_type = "HDMI"
            connector_type   = "HDMI"

    is_hdmi = "hdmi" in connector_type.lower()

    if is_hdmi:
        bw = a.hdmi.max_bandwidth_gbps
        a.max_bandwidth_gbps = a.effective_bandwidth_gbps = bw
    elif edid_info:
        a.dp = estimate_dp_capabilities(edid_info)
        a.max_bandwidth_gbps = a.effective_bandwidth_gbps = a.dp.max_bandwidth_gbps

    a.quality_score, a.quality_grade, a.issues = _calculate_quality(a)
    a.supported_features = _calculate_features(a)
    a.max_resolutions    = _calculate_max_resolutions(a)
    return a


def _calculate_quality(a: CableAnalysis):
    score  = 100
    issues = []

    is_hdmi = "hdmi" in a.connector_type.lower()
    is_dp   = "displayport" in a.connector_type.lower()

    if not a.edid:
        score -= 30
        issues.append("EDID okunamiyor – monitor bilgisi eksik")

    if not a.is_active:
        score -= 15
        issues.append("Monitor aktif degil veya cozunurluk okunamiyor")
    elif a.edid and a.edid.max_hpixels and a.current_width:
        if a.current_width < a.edid.max_hpixels:
            ratio = a.current_width / a.edid.max_hpixels
            if ratio < 0.75:
                score -= 15
                issues.append(
                    f"Dusurulmus cozunurluk: "
                    f"{a.current_width}x{a.current_height} "
                    f"(max: {a.edid.max_hpixels}x{a.edid.max_vpixels})"
                )

    if a.connector_type == "Bilinmiyor":
        score -= 10
        issues.append("Baglanti tipi belirlenemiyor")

    if is_hdmi:
        ver = a.hdmi.version
        if ver == "Bilinmiyor":
            score -= 15
            issues.append("HDMI versiyonu belirlenemiyor")
        elif ver in ("1.0", "1.1", "1.2"):
            score -= 30
            issues.append(f"Eski HDMI versiyonu: {ver} – maks 4.95 Gbps")
        elif ver == "1.3":
            score -= 10
            issues.append("HDMI 1.3 – 4K destegi sinirli (max 10.2 Gbps)")
        # 1.4, 2.0, 2.1 -> puan kesintisi yok
    elif is_dp:
        if a.dp.estimated_version == "Bilinmiyor":
            score -= 20
            issues.append("DP versiyonu tahmini basarisiz")
        issues.append(
            "Not: DP DPCD verileri Windows'ta dogrudan okunamiyor; "
            "degerler EDID'den tahmin edilmistir"
        )

    score = max(0, min(100, score))
    if   score >= 90: grade = "MUKEMMEL"
    elif score >= 75: grade = "IYI"
    elif score >= 50: grade = "ORTA"
    elif score >= 25: grade = "ZAYIF"
    else:             grade = "KOTU"
    return score, grade, issues


def _calculate_features(a: CableAnalysis) -> list:
    feats   = []
    is_hdmi = "hdmi" in a.connector_type.lower()
    is_dp   = "displayport" in a.connector_type.lower()

    if is_hdmi and a.hdmi.is_hdmi:
        feats.append(f"HDMI {a.hdmi.version}")
        feats.append(f"Max Bant Genisligi: {a.hdmi.max_bandwidth_gbps:.0f} Gbps")
        if a.hdmi.max_tmds_clock_mhz:
            feats.append(f"Max TMDS Saati: {a.hdmi.max_tmds_clock_mhz} MHz")
        if a.hdmi.scdc_present:
            feats.append("SCDC (Durum ve Kontrol Veri Kanali – HDMI 2.0+)")
        if a.hdmi.has_earc:
            feats.append("eARC (Gelismis Ses Geri Kanali – HDMI 2.1)")
        elif a.hdmi.has_arc:
            feats.append("ARC (Ses Geri Kanali – HDMI 1.4+)")
        if a.hdmi.has_vrr:
            feats.append("VRR (Degisken Yenileme Hizi – HDMI 2.1)")
        if a.hdmi.has_allm:
            feats.append("ALLM (Otomatik Dusuk Gecikme – HDMI 2.1)")
        if a.hdmi.has_hdr10:
            feats.append("HDR10 Destegi")
        if a.hdmi.has_dolby_vision:
            feats.append("Dolby Vision Destegi")
        if a.hdmi.has_deep_color:
            feats.append("Deep Color (10/12-bit renk)")
        if a.hdmi.has_3d:
            feats.append("3D Destegi")
        if a.hdmi.has_ycbcr444: feats.append("YCbCr 4:4:4")
        if a.hdmi.has_ycbcr422: feats.append("YCbCr 4:2:2")
        if a.hdmi.has_ycbcr420: feats.append("YCbCr 4:2:0")
        if a.hdmi.has_cec:
            feats.append("CEC (Tuketici Elektronik Kontrolu)")
        feats.append("HDMI Audio (7.1 Surround)")

    elif is_dp:
        if a.dp.estimated_version != "Bilinmiyor":
            feats.append(f"DisplayPort {a.dp.estimated_version} (min. versiyon tahmini)")
        feats.append(f"Tahmini Maks BW: {a.dp.max_bandwidth_gbps:.1f} Gbps")
        feats.append("DP Audio (7.1 Surround)")
        feats.append("Not: DPCD verileri Windows'ta dogrudan okunamiyor")

    if a.edid:
        mon = f"{a.edid.manufacturer} {a.edid.model_name}".strip()
        if mon:
            feats.append(f"Monitor: {mon}")
        if a.edid.max_hpixels:
            feats.append(f"EDID Maks Coz.: {a.edid.max_hpixels}x{a.edid.max_vpixels}")
        if a.edid.edid_version:
            feats.append(f"EDID Versiyonu: {a.edid.edid_version}")

    if a.current_width and a.current_height:
        feats.append(
            f"Aktif Mod: {a.current_width}x{a.current_height}@{a.current_refresh}Hz"
        )

    return [f for f in feats if f]


def _calculate_max_resolutions(a: CableAnalysis) -> list:
    bw = a.effective_bandwidth_gbps
    if not bw:
        return []

    common = [
        ("8K",   7680, 4320, 24),
        ("5K",   5120, 2880, 24),
        ("4K",   3840, 2160, 24),
        ("WQHD", 2560, 1440, 24),
        ("FHD",  1920, 1080, 24),
    ]
    res = []
    for name, w, h, bpp in common:
        for hz in [60, 120, 144, 165, 240]:
            req = (w * h * bpp * hz * 1.06) / 1e9
            res.append({"res": name, "w": w, "h": h, "hz": hz,
                        "req": req, "ok": req <= bw})
    return res


# ============================================================
# GUI
# ============================================================
class ScoreGauge(tk.Canvas):
    """Dairesel kalite gostergesi."""

    def __init__(self, parent, size=180, **kwargs):
        super().__init__(parent, width=size, height=size,
                         bg=BG_CARD, highlightthickness=0, **kwargs)
        self.size  = size
        self.score = 0
        self.grade = ""
        self._anim = 0

    def set_score(self, score, grade):
        self.score = score
        self.grade = grade
        self._anim = 0
        self._animate()

    def _animate(self):
        if self._anim < self.score:
            self._anim = min(self._anim + 2, self.score)
            self._draw(self._anim)
            self.after(16, self._animate)
        else:
            self._draw(self.score)

    def _draw(self, s):
        self.delete("all")
        cx = cy = self.size / 2
        r  = self.size / 2 - 14
        lw = 11
        self.create_arc(cx-r, cy-r, cx+r, cy+r,
                        start=225, extent=-270, style="arc",
                        outline=BAR_BG, width=lw)
        color = (ACCENT_GREEN  if s >= 75 else
                 ACCENT_YELLOW if s >= 50 else
                 ACCENT_ORANGE if s >= 25 else ACCENT_RED)
        self.create_arc(cx-r, cy-r, cx+r, cy+r,
                        start=225, extent=-270*(s/100), style="arc",
                        outline=color, width=lw)
        self.create_text(cx, cy-10, text=str(s),
                         font=("Segoe UI", 32, "bold"), fill=color)
        self.create_text(cx, cy+22, text="/100",
                         font=("Segoe UI", 11), fill=FG_DIM)
        self.create_text(cx, cy+44, text=self.grade,
                         font=("Segoe UI", 13, "bold"), fill=color)


class BandwidthBar(tk.Canvas):
    """Bant genisligi yatay cubugu."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, width=420, height=50,
                         bg=BG_CARD, highlightthickness=0, **kwargs)

    def set_values(self, current, maximum):
        self.delete("all")
        w = 420
        by, bh = 25, 16
        self.create_rectangle(10, by, w-10, by+bh, fill=BAR_BG, outline="")
        if maximum > 0:
            ratio  = min(current / maximum, 1.0)
            fill_w = (w - 20) * ratio
            color  = (ACCENT_GREEN  if ratio >= 0.9 else
                      ACCENT_YELLOW if ratio >= 0.5 else ACCENT_RED)
            self.create_rectangle(10, by, 10+fill_w, by+bh, fill=color, outline="")
        self.create_text(10, 10, anchor="w",
                         text=f"Mevcut: {current:.1f} Gbps",
                         font=("Segoe UI", 10, "bold"), fill=ACCENT_CYAN)
        self.create_text(w-10, 10, anchor="e",
                         text=f"Max: {maximum:.1f} Gbps",
                         font=("Segoe UI", 10), fill=FG_DIM)


class CableTestApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DisplayPort / HDMI Kablo Test – Windows")
        self.root.configure(bg=BG_DARK)
        self.root.minsize(960, 700)

        self.canvas    = tk.Canvas(root, bg=BG_DARK, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(root, orient="vertical",
                                       command=self.canvas.yview)
        self.frame     = tk.Frame(self.canvas, bg=BG_DARK)

        self.frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            ),
        )
        self._win = self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind_all("<MouseWheel>", self._on_mwheel)

        self._build_header()
        self.content = tk.Frame(self.frame, bg=BG_DARK)
        self.content.pack(fill="both", expand=True, padx=10, pady=5)

        self.status_var = tk.StringVar(value="Taraniyor...")
        tk.Label(self.frame, textvariable=self.status_var,
                 font=("Segoe UI", 9), fg=FG_DIM,
                 bg=BG_DARK, anchor="w").pack(fill="x", padx=15, pady=(0, 8))

        self.root.after(120, self.run_test)

    def _on_resize(self, e):
        self.canvas.itemconfig(self._win, width=e.width)

    def _on_mwheel(self, e):
        self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def _build_header(self):
        hdr = tk.Frame(self.frame, bg=BG_CARD2, pady=15)
        hdr.pack(fill="x", padx=10, pady=(10, 5))
        tk.Label(hdr, text="DISPLAYPORT / HDMI KABLO TEST",
                 font=("Segoe UI", 22, "bold"), fg=ACCENT_CYAN,
                 bg=BG_CARD2).pack()
        tk.Label(hdr,
                 text="Kablo versiyonu  *  Kalite  *  Desteklenen teknolojiler"
                      "  |  Windows 10/11",
                 font=("Segoe UI", 10), fg=FG_DIM, bg=BG_CARD2).pack()

    # -------------------------------------------------------
    def run_test(self):
        for w in self.content.winfo_children():
            w.destroy()

        if sys.platform != "win32":
            self._show_error(
                "Bu program yalnizca Windows'ta calisir.\n"
                "Linux icin dp_cable_test_gui.py kullanin."
            )
            return

        self.status_var.set("Monitorler taraniyor...")
        self.root.update_idletasks()

        analyses = find_monitors()

        if not analyses:
            self._show_error(
                "Bagli monitor bulunamadi!\n"
                "Kablonun duzgun takildigini kontrol edin."
            )
            self.status_var.set("Monitor bulunamadi")
            return

        for a in analyses:
            self._show_analysis(a)

        btn_f = tk.Frame(self.content, bg=BG_DARK)
        btn_f.pack(pady=12)
        tk.Button(btn_f, text="Yeniden Tara", command=self.run_test,
                  font=("Segoe UI", 11, "bold"), fg=BG_DARK,
                  bg=ACCENT_CYAN, activebackground=ACCENT_BLUE,
                  relief="flat", padx=20, pady=8, cursor="hand2").pack()

        self.status_var.set(f"Tamamlandi - {len(analyses)} monitor bulundu")

    # -------------------------------------------------------
    def _show_error(self, msg):
        frm = tk.Frame(self.content, bg=BG_CARD, padx=30, pady=30)
        frm.pack(fill="x", pady=20)
        tk.Label(frm, text="HATA", font=("Segoe UI", 16, "bold"),
                 fg=ACCENT_RED, bg=BG_CARD).pack()
        tk.Label(frm, text=msg, font=("Segoe UI", 12),
                 fg=FG_TEXT, bg=BG_CARD).pack(pady=10)
        self.status_var.set("Hata olustu")

    def _card(self, title, parent=None):
        p    = parent or self.content
        card = tk.Frame(p, bg=BG_CARD, padx=15, pady=12)
        card.pack(fill="x", pady=4)
        tk.Label(card, text=title, font=("Segoe UI", 13, "bold"),
                 fg=ACCENT_CYAN, bg=BG_CARD, anchor="w").pack(fill="x")
        tk.Frame(card, bg=ACCENT_BLUE, height=1).pack(fill="x", pady=(4, 8))
        body = tk.Frame(card, bg=BG_CARD)
        body.pack(fill="x")
        return body

    def _kv(self, parent, key, value, row, val_color=FG_TEXT):
        tk.Label(parent, text=key, font=("Segoe UI", 10),
                 fg=FG_DIM, bg=BG_CARD, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(0, 15), pady=2)
        tk.Label(parent, text=str(value), font=("Segoe UI", 10, "bold"),
                 fg=val_color, bg=BG_CARD, anchor="w").grid(
            row=row, column=1, sticky="w", pady=2)

    # -------------------------------------------------------
    def _show_analysis(self, a: CableAnalysis):
        is_hdmi    = "hdmi" in a.connector_type.lower()
        type_color = ACCENT_PURPLE if is_hdmi else ACCENT_CYAN

        # Ayirici baslik
        sep = tk.Frame(self.content, bg=BG_CARD2, padx=15, pady=6)
        sep.pack(fill="x", pady=(8, 2))
        tk.Label(sep, text=f"▶  {a.connector_name}  [{a.connector_type}]",
                 font=("Segoe UI", 13, "bold"), fg=type_color,
                 bg=BG_CARD2).pack(anchor="w")

        # --- Ust satir: Kalite + Baglanti ---
        top = tk.Frame(self.content, bg=BG_DARK)
        top.pack(fill="x", pady=4)
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=2)

        # Kalite karti
        sc_card = tk.Frame(top, bg=BG_CARD, padx=15, pady=12)
        sc_card.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        tk.Label(sc_card, text="KABLO KALITESI",
                 font=("Segoe UI", 13, "bold"), fg=ACCENT_CYAN,
                 bg=BG_CARD).pack()
        tk.Frame(sc_card, bg=ACCENT_BLUE, height=1).pack(fill="x", pady=(4, 8))
        gauge = ScoreGauge(sc_card, size=180)
        gauge.pack(pady=5)
        gauge.set_score(a.quality_score, a.quality_grade)

        notes      = [i for i in a.issues if i.startswith("Not:")]
        warn_issues = [i for i in a.issues if not i.startswith("Not:")]
        if warn_issues:
            for issue in warn_issues:
                tk.Label(sc_card, text=f"!  {issue}",
                         font=("Segoe UI", 9), fg=ACCENT_YELLOW,
                         bg=BG_CARD, anchor="w",
                         wraplength=260).pack(anchor="w", pady=1)
        else:
            tk.Label(sc_card, text="Sorun bulunamadi",
                     font=("Segoe UI", 10), fg=ACCENT_GREEN,
                     bg=BG_CARD).pack()
        for note in notes:
            tk.Label(sc_card, text=note,
                     font=("Segoe UI", 8), fg=FG_DIM,
                     bg=BG_CARD, anchor="w",
                     wraplength=260).pack(anchor="w", pady=1)

        # Baglanti bilgi karti
        conn_card = tk.Frame(top, bg=BG_CARD, padx=15, pady=12)
        conn_card.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        tk.Label(conn_card, text="BAGLANTI BILGISI",
                 font=("Segoe UI", 13, "bold"), fg=ACCENT_CYAN,
                 bg=BG_CARD).pack(anchor="w")
        tk.Frame(conn_card, bg=ACCENT_BLUE, height=1).pack(fill="x", pady=(4, 8))

        g   = tk.Frame(conn_card, bg=BG_CARD)
        g.pack(fill="x")
        row = 0
        self._kv(g, "Baglanti Tipi", a.connector_type, row, type_color); row += 1
        self._kv(g, "Adaptor",       a.connector_name,  row); row += 1
        if a.device_id:
            self._kv(g, "Cihaz ID", a.device_id, row, FG_DIM); row += 1

        if a.edid:
            mon = f"{a.edid.manufacturer} {a.edid.model_name}".strip()
            self._kv(g, "Monitor",   mon or "—",       row, ACCENT_CYAN); row += 1
            if a.edid.serial:
                self._kv(g, "Seri No", a.edid.serial,  row); row += 1
            self._kv(g, "Uretim",
                     f"Hafta {a.edid.week}, {a.edid.year}", row); row += 1
            self._kv(g, "EDID", a.edid.edid_version, row); row += 1
            if a.edid.max_hpixels:
                self._kv(g, "EDID Max Coz.",
                         f"{a.edid.max_hpixels}x{a.edid.max_vpixels}",
                         row, ACCENT_GREEN); row += 1

        if a.current_width:
            self._kv(g, "Aktif Mod",
                     f"{a.current_width}x{a.current_height}@{a.current_refresh}Hz",
                     row, ACCENT_CYAN); row += 1

        if is_hdmi and a.hdmi.is_hdmi:
            self._kv(g, "HDMI Versiyonu",   a.hdmi.version, row, ACCENT_PURPLE); row += 1
            self._kv(g, "Max Bant Gen.",
                     f"{a.hdmi.max_bandwidth_gbps:.0f} Gbps",
                     row, ACCENT_GREEN); row += 1
            if a.hdmi.max_tmds_clock_mhz:
                self._kv(g, "Max TMDS",
                         f"{a.hdmi.max_tmds_clock_mhz} MHz", row); row += 1
        else:
            self._kv(g, "DP Versiyon (tahmini)", a.dp.estimated_version,
                     row, ACCENT_GREEN); row += 1
            self._kv(g, "Tahmini Max BW",
                     f"{a.dp.max_bandwidth_gbps:.1f} Gbps", row); row += 1

        # --- Bant Genisligi ---
        bw_body = self._card("BANT GENISLIGI")
        bar = BandwidthBar(bw_body)
        bar.pack(fill="x", pady=5)
        bar.set_values(0.0, a.effective_bandwidth_gbps)

        bw_g = tk.Frame(bw_body, bg=BG_CARD)
        bw_g.pack(fill="x")
        self._kv(bw_g, "Maks Efektif",
                 f"{a.effective_bandwidth_gbps:.1f} Gbps", 0, ACCENT_GREEN)
        lbl2 = f"HDMI {a.hdmi.version}" if is_hdmi else f"DP {a.dp.estimated_version} (tahmini)"
        self._kv(bw_g, "Versiyon", lbl2, 1)

        # --- Desteklenen Teknolojiler ---
        feat_body = self._card("DESTEKLENEN TEKNOLOJILER")
        cols = 2
        for i, feat in enumerate(a.supported_features):
            r_idx, col = divmod(i, cols)
            hdmi_feat  = any(x in feat for x in
                             ("HDMI", "ARC", "VRR", "ALLM", "SCDC",
                              "Dolby", "Deep Color", "CEC", "eARC"))
            color = ACCENT_PURPLE if hdmi_feat else ACCENT_GREEN
            tk.Label(feat_body, text=f"  +  {feat}",
                     font=("Segoe UI", 10), fg=color,
                     bg=BG_CARD, anchor="w").grid(
                row=r_idx, column=col, sticky="w", padx=(0, 30), pady=1)

        # --- Cozunurluk Tablosu ---
        res_body = self._card("COZUNURLUK DESTEGI")
        hdr_f = tk.Frame(res_body, bg=BG_CARD2)
        hdr_f.pack(fill="x")
        for text, ww in [("Cozunurluk", 120), ("Hz", 50),
                          ("Gerekli", 90), ("Durum", 100)]:
            tk.Label(hdr_f, text=text, font=("Segoe UI", 9, "bold"),
                     fg=FG_DIM, bg=BG_CARD2,
                     width=ww // 8, anchor="w").pack(side="left", padx=5)

        for r in a.max_resolutions:
            rf = tk.Frame(res_body, bg=BG_CARD)
            rf.pack(fill="x")
            tk.Label(rf, text=f"{r['res']} ({r['w']}x{r['h']})",
                     font=("Segoe UI", 9), fg=FG_TEXT,
                     bg=BG_CARD, width=15, anchor="w").pack(side="left", padx=5)
            tk.Label(rf, text=str(r["hz"]),
                     font=("Segoe UI", 9), fg=FG_TEXT,
                     bg=BG_CARD, width=6, anchor="w").pack(side="left", padx=5)
            tk.Label(rf, text=f"{r['req']:.1f} Gbps",
                     font=("Segoe UI", 9), fg=FG_DIM,
                     bg=BG_CARD, width=11, anchor="w").pack(side="left", padx=5)
            st_text  = "DESTEKLI" if r["ok"] else "YETERSIZ"
            st_color = ACCENT_GREEN if r["ok"] else ACCENT_RED
            tk.Label(rf, text=st_text,
                     font=("Segoe UI", 9, "bold"), fg=st_color,
                     bg=BG_CARD, width=12, anchor="w").pack(side="left", padx=5)


# ============================================================
# Ana Program
# ============================================================
def main():
    if sys.platform != "win32":
        print(
            "UYARI: Bu program Windows icin tasarlanmistir.\n"
            "Linux icin dp_cable_test_gui.py kullanin.\n"
            "GUI hata mesajini gostermek icin devam ediliyor..."
        )

    root = tk.Tk()
    root.geometry("960x750")

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Vertical.TScrollbar",
                    background=BAR_BG, troughcolor=BG_DARK,
                    arrowcolor=FG_DIM)

    CableTestApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
