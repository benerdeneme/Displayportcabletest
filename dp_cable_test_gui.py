#!/usr/bin/env python3
"""
DisplayPort Kablo Test Programi - GUI
======================================
Takili DisplayPort kablonun versiyonunu, kalitesini, hizini
ve destekledigi maksimum teknolojileri olcer.

Kullanim: sudo python3 dp_cable_test_gui.py
"""

import os
import sys
import glob
import math
import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import dataclass, field
from pathlib import Path

# ============================================================
# Renkler
# ============================================================
BG_DARK     = "#1a1a2e"
BG_CARD     = "#16213e"
BG_CARD2    = "#0f3460"
FG_TEXT      = "#e0e0e0"
FG_DIM       = "#888899"
FG_TITLE     = "#ffffff"
ACCENT_BLUE  = "#00adb5"
ACCENT_GREEN = "#00e676"
ACCENT_RED   = "#ff5252"
ACCENT_YELLOW= "#ffd740"
ACCENT_ORANGE= "#ff9100"
ACCENT_CYAN  = "#18ffff"
ACCENT_PURPLE= "#b388ff"
BAR_BG       = "#2a2a4a"

# ============================================================
# DPCD Register Adresleri
# ============================================================
DPCD_REV            = 0x0000
DPCD_MAX_LINK_RATE  = 0x0001
DPCD_MAX_LANE_COUNT = 0x0002
DPCD_TRAINING_AUX   = 0x000E
DPCD_LINK_BW_SET    = 0x0100
DPCD_LANE_COUNT_SET = 0x0101
DPCD_LANE01_STATUS  = 0x0202
DPCD_LANE23_STATUS  = 0x0203
DPCD_LANE_ALIGN     = 0x0204
DPCD_FEC_CAPABILITY = 0x0090
DPCD_DSC_SUPPORT    = 0x0060

LINK_RATE_MAP = {
    0x06: ("1.62 Gbps/lane", 1.62,  "RBR",   "1.0"),
    0x0A: ("2.70 Gbps/lane", 2.70,  "HBR",   "1.1"),
    0x14: ("5.40 Gbps/lane", 5.40,  "HBR2",  "1.2"),
    0x1E: ("8.10 Gbps/lane", 8.10,  "HBR3",  "1.3+"),
}

DPCD_REV_MAP = {
    (1, 0): "1.0", (1, 1): "1.1", (1, 2): "1.2",
    (1, 3): "1.3", (1, 4): "1.4", (2, 0): "2.0", (2, 1): "2.1",
}

# ============================================================
# DPCD / EDID / Analysis (ayni mantik)
# ============================================================
class DPCDReader:
    def __init__(self, aux_path: str):
        self.aux_path = aux_path
        self._cache = {}

    def read(self, offset: int, length: int) -> bytes:
        key = (offset, length)
        if key in self._cache:
            return self._cache[key]
        try:
            with open(self.aux_path, 'rb') as f:
                f.seek(offset)
                data = f.read(length)
                self._cache[key] = data
                return data
        except (PermissionError, OSError):
            return b''

    def read_byte(self, offset: int) -> int | None:
        data = self.read(offset, 1)
        return data[0] if data else None


@dataclass
class EDIDInfo:
    manufacturer: str = ""
    model_name: str = ""
    serial: str = ""
    max_hpixels: int = 0
    max_vpixels: int = 0
    year: int = 0
    week: int = 0
    edid_version: str = ""


def parse_edid(raw: bytes) -> EDIDInfo | None:
    if len(raw) < 128 or raw[0:8] != b'\x00\xff\xff\xff\xff\xff\xff\x00':
        return None
    info = EDIDInfo()
    mfg_id = (raw[8] << 8) | raw[9]
    info.manufacturer = chr(((mfg_id >> 10) & 0x1F) + 64) + chr(((mfg_id >> 5) & 0x1F) + 64) + chr((mfg_id & 0x1F) + 64)
    info.week = raw[16]
    info.year = raw[17] + 1990
    info.edid_version = f"{raw[18]}.{raw[19]}"

    for i in range(4):
        offset = 54 + i * 18
        block = raw[offset:offset + 18]
        if block[0] == 0 and block[1] == 0:
            tag = block[3]
            if tag == 0xFC:
                info.model_name = block[5:18].decode('ascii', errors='ignore').strip()
            elif tag == 0xFF:
                info.serial = block[5:18].decode('ascii', errors='ignore').strip()
        else:
            pixel_clock = (block[1] << 8 | block[0]) * 10000
            if pixel_clock == 0:
                continue
            h_active = ((block[4] & 0xF0) << 4) | block[2]
            v_active = ((block[7] & 0xF0) << 4) | block[5]
            if h_active > info.max_hpixels:
                info.max_hpixels = h_active
                info.max_vpixels = v_active
    return info


@dataclass
class DPAnalysis:
    dpcd_major: int = 0
    dpcd_minor: int = 0
    dp_version: str = "Bilinmiyor"
    max_link_rate_code: int = 0
    max_link_rate_gbps: float = 0.0
    link_rate_name: str = ""
    max_lane_count: int = 0
    enhanced_framing: bool = False
    tps3_support: bool = False
    tps4_support: bool = False
    fec_support: bool = False
    dsc_support: bool = False
    mst_support: bool = False
    total_bandwidth_gbps: float = 0.0
    effective_bandwidth_gbps: float = 0.0
    current_link_rate_code: int = 0
    current_link_rate_gbps: float = 0.0
    current_lane_count: int = 0
    lanes_synced: list = field(default_factory=list)
    link_aligned: bool = False
    current_bandwidth_gbps: float = 0.0
    quality_score: int = 0
    quality_grade: str = ""
    issues: list = field(default_factory=list)
    max_resolutions: list = field(default_factory=list)
    supported_features: list = field(default_factory=list)
    edid: EDIDInfo | None = None
    connector_name: str = ""
    aux_device: str = ""


def analyze_dp(aux_path: str, connector: str, edid_path: str | None) -> DPAnalysis:
    reader = DPCDReader(aux_path)
    a = DPAnalysis()
    a.connector_name = connector
    a.aux_device = aux_path

    rev = reader.read_byte(DPCD_REV)
    if rev is None:
        a.issues.append("DPCD okunamiyor")
        return a

    a.dpcd_major = (rev >> 4) & 0x0F
    a.dpcd_minor = rev & 0x0F
    a.dp_version = DPCD_REV_MAP.get((a.dpcd_major, a.dpcd_minor), f"{a.dpcd_major}.{a.dpcd_minor}")

    rate_code = reader.read_byte(DPCD_MAX_LINK_RATE)
    if rate_code and rate_code in LINK_RATE_MAP:
        name, gbps, short, min_ver = LINK_RATE_MAP[rate_code]
        a.max_link_rate_code = rate_code
        a.max_link_rate_gbps = gbps
        a.link_rate_name = short

    lane_byte = reader.read_byte(DPCD_MAX_LANE_COUNT)
    if lane_byte:
        a.max_lane_count = lane_byte & 0x1F
        a.enhanced_framing = bool(lane_byte & 0x80)
        a.tps3_support = bool(lane_byte & 0x40)

    training_byte = reader.read_byte(DPCD_TRAINING_AUX)
    if training_byte:
        a.tps4_support = bool(training_byte & 0x80)

    mstm = reader.read_byte(0x0021)
    if mstm:
        a.mst_support = bool(mstm & 0x01)

    fec_byte = reader.read_byte(DPCD_FEC_CAPABILITY)
    if fec_byte:
        a.fec_support = bool(fec_byte & 0x01)

    dsc_byte = reader.read_byte(DPCD_DSC_SUPPORT)
    if dsc_byte:
        a.dsc_support = bool(dsc_byte & 0x01)

    if a.max_link_rate_gbps and a.max_lane_count:
        a.total_bandwidth_gbps = a.max_link_rate_gbps * a.max_lane_count
        a.effective_bandwidth_gbps = a.total_bandwidth_gbps * 0.80

    current_rate = reader.read_byte(DPCD_LINK_BW_SET)
    if current_rate and current_rate in LINK_RATE_MAP:
        a.current_link_rate_code = current_rate
        a.current_link_rate_gbps = LINK_RATE_MAP[current_rate][1]

    current_lanes = reader.read_byte(DPCD_LANE_COUNT_SET)
    if current_lanes:
        a.current_lane_count = current_lanes & 0x1F

    if a.current_link_rate_gbps and a.current_lane_count:
        a.current_bandwidth_gbps = a.current_link_rate_gbps * a.current_lane_count * 0.80

    lane01 = reader.read_byte(DPCD_LANE01_STATUS)
    lane23 = reader.read_byte(DPCD_LANE23_STATUS)
    align = reader.read_byte(DPCD_LANE_ALIGN)

    if lane01 is not None:
        a.lanes_synced.append({"lane": 0, "cr": bool(lane01 & 0x01), "eq": bool(lane01 & 0x02), "sym": bool(lane01 & 0x04), "ok": bool(lane01 & 0x07 == 0x07)})
        a.lanes_synced.append({"lane": 1, "cr": bool(lane01 & 0x10), "eq": bool(lane01 & 0x20), "sym": bool(lane01 & 0x40), "ok": bool(lane01 & 0x70 == 0x70)})

    if lane23 is not None and a.current_lane_count > 2:
        a.lanes_synced.append({"lane": 2, "cr": bool(lane23 & 0x01), "eq": bool(lane23 & 0x02), "sym": bool(lane23 & 0x04), "ok": bool(lane23 & 0x07 == 0x07)})
        a.lanes_synced.append({"lane": 3, "cr": bool(lane23 & 0x10), "eq": bool(lane23 & 0x20), "sym": bool(lane23 & 0x40), "ok": bool(lane23 & 0x70 == 0x70)})

    if align is not None:
        a.link_aligned = bool(align & 0x01)

    if edid_path and os.path.exists(edid_path):
        try:
            with open(edid_path, 'rb') as f:
                a.edid = parse_edid(f.read())
        except Exception:
            pass

    a.quality_score, a.quality_grade, a.issues = calculate_quality(a)
    a.max_resolutions = calculate_max_resolutions(a)
    a.supported_features = calculate_features(a)
    return a


def calculate_quality(a):
    score = 100
    issues = list(a.issues)
    if a.current_link_rate_gbps and a.max_link_rate_gbps:
        ratio = a.current_link_rate_gbps / a.max_link_rate_gbps
        if ratio < 1.0:
            score -= int((1.0 - ratio) * 40)
            issues.append(f"Link hizi dusurulmus: {a.current_link_rate_gbps:.2f}/{a.max_link_rate_gbps:.2f} Gbps/lane")
    if a.current_lane_count and a.max_lane_count and a.current_lane_count < a.max_lane_count:
        score -= 20
        issues.append(f"Lane sayisi dusurulmus: {a.current_lane_count}/{a.max_lane_count}")
    bad_lanes = [l for l in a.lanes_synced if not l["ok"]]
    if bad_lanes:
        score -= len(bad_lanes) * 15
        for l in bad_lanes:
            parts = []
            if not l["cr"]: parts.append("CR")
            if not l["eq"]: parts.append("EQ")
            if not l["sym"]: parts.append("SYM")
            issues.append(f"Lane {l['lane']} sorunlu: {', '.join(parts)}")
    if a.lanes_synced and not a.link_aligned:
        score -= 15
        issues.append("Lane hizalamasi basarisiz")
    if not a.enhanced_framing and a.max_link_rate_gbps > 2.7:
        score -= 5
        issues.append("Enhanced framing destegi yok")
    score = max(0, min(100, score))
    if score >= 90: grade = "MUKEMMEL"
    elif score >= 75: grade = "IYI"
    elif score >= 50: grade = "ORTA"
    elif score >= 25: grade = "ZAYIF"
    else: grade = "KOTU"
    return score, grade, issues


def calculate_max_resolutions(a):
    bw = a.effective_bandwidth_gbps
    if not bw:
        return []
    common_res = [
        ("8K",   7680, 4320, 24),
        ("5K",   5120, 2880, 24),
        ("4K",   3840, 2160, 24),
        ("WQHD", 2560, 1440, 24),
        ("FHD",  1920, 1080, 24),
    ]
    refresh_rates = [60, 120, 144, 165, 240, 360]
    results = []
    for name, w, h, bpp in common_res:
        for hz in refresh_rates:
            req = (w * h * bpp * hz * 1.06) / 1e9
            supported = req <= bw
            dsc = req <= bw * 3 and a.dsc_support and not supported
            results.append({"res": name, "w": w, "h": h, "hz": hz, "req": req, "ok": supported, "dsc": dsc})
    return results


def calculate_features(a):
    features = []
    if a.dp_version != "Bilinmiyor": features.append(f"DisplayPort {a.dp_version}")
    if a.link_rate_name: features.append(f"{a.link_rate_name} ({a.max_link_rate_gbps:.2f} Gbps/lane)")
    if a.max_lane_count: features.append(f"{a.max_lane_count}x Lane")
    if a.enhanced_framing: features.append("Enhanced Framing")
    if a.tps3_support: features.append("TPS3 (Training Pattern 3)")
    if a.tps4_support: features.append("TPS4 (Training Pattern 4)")
    if a.mst_support: features.append("MST (Multi-Stream / Daisy-Chain)")
    if a.fec_support: features.append("FEC (Forward Error Correction)")
    if a.dsc_support: features.append("DSC (Display Stream Compression)")
    if a.max_link_rate_gbps >= 8.1:
        features.append("HDR10 / HDR10+")
        features.append("10-bit / 12-bit Renk")
    elif a.max_link_rate_gbps >= 5.4:
        features.append("HDR10 (sinirli)")
        features.append("10-bit Renk")
    elif a.max_link_rate_gbps >= 2.7:
        features.append("8-bit Renk")
    if a.dpcd_major >= 1 and a.dpcd_minor >= 3:
        features.append("Adaptive Sync (FreeSync/G-Sync)")
    elif a.dpcd_major >= 1 and a.dpcd_minor >= 2:
        features.append("Adaptive Sync (sinirli)")
    features.append("DP Audio (7.1 Surround)")
    return features


def find_dp_connections():
    connections = []
    drm_path = Path("/sys/class/drm")
    if not drm_path.exists():
        return connections
    for d in sorted(drm_path.iterdir()):
        if "DP" not in d.name:
            continue
        sf = d / "status"
        if not sf.exists():
            continue
        try:
            status = sf.read_text().strip()
        except Exception:
            continue
        edid_path = d / "edid"
        connections.append({
            "name": d.name, "path": str(d), "status": status,
            "edid_path": str(edid_path) if edid_path.exists() else None,
        })
    return connections


def find_aux_for_connector(connector_name):
    aux_devices = sorted(glob.glob("/dev/drm_dp_aux*"))
    for aux in aux_devices:
        sysfs_name = f"/sys/class/drm_dp_aux_dev/{os.path.basename(aux)}/name"
        if os.path.exists(sysfs_name):
            try:
                name = open(sysfs_name).read().strip()
                if connector_name in name:
                    return aux
            except Exception:
                pass
    for aux in aux_devices:
        try:
            with open(aux, 'rb') as f:
                data = f.read(2)
                if data and len(data) >= 2 and data[0] > 0:
                    return aux
        except Exception:
            continue
    return None


# ============================================================
# GUI
# ============================================================

class ScoreGauge(tk.Canvas):
    """Dairesel kalite gostergesi."""

    def __init__(self, parent, size=200, **kwargs):
        super().__init__(parent, width=size, height=size,
                         bg=BG_CARD, highlightthickness=0, **kwargs)
        self.size = size
        self.score = 0
        self.grade = ""
        self._anim_score = 0

    def set_score(self, score, grade):
        self.score = score
        self.grade = grade
        self._anim_score = 0
        self._animate()

    def _animate(self):
        if self._anim_score < self.score:
            self._anim_score = min(self._anim_score + 2, self.score)
            self._draw(self._anim_score)
            self.after(16, self._animate)
        else:
            self._draw(self.score)

    def _draw(self, current_score):
        self.delete("all")
        cx, cy = self.size / 2, self.size / 2
        r = self.size / 2 - 15
        lw = 12

        # Background arc
        self.create_arc(cx - r, cy - r, cx + r, cy + r,
                        start=225, extent=-270, style="arc",
                        outline=BAR_BG, width=lw)

        # Score arc
        if current_score >= 75:
            color = ACCENT_GREEN
        elif current_score >= 50:
            color = ACCENT_YELLOW
        elif current_score >= 25:
            color = ACCENT_ORANGE
        else:
            color = ACCENT_RED

        extent = -270 * (current_score / 100)
        self.create_arc(cx - r, cy - r, cx + r, cy + r,
                        start=225, extent=extent, style="arc",
                        outline=color, width=lw)

        # Score text
        self.create_text(cx, cy - 10, text=str(current_score),
                         font=("Segoe UI", 36, "bold"), fill=color)
        self.create_text(cx, cy + 25, text="/100",
                         font=("Segoe UI", 12), fill=FG_DIM)
        self.create_text(cx, cy + 48, text=self.grade,
                         font=("Segoe UI", 14, "bold"), fill=color)


class LaneIndicator(tk.Canvas):
    """Tek bir lane icin gorsel gosterge."""

    def __init__(self, parent, lane_num, **kwargs):
        super().__init__(parent, width=80, height=120,
                         bg=BG_CARD, highlightthickness=0, **kwargs)
        self.lane_num = lane_num

    def set_status(self, cr, eq, sym, ok):
        self.delete("all")
        color = ACCENT_GREEN if ok else ACCENT_RED

        # Lane kutusu
        self.create_rectangle(10, 10, 70, 110, outline=color, width=2, fill=BG_CARD2)

        # Lane numarasi
        self.create_text(40, 25, text=f"L{self.lane_num}",
                         font=("Segoe UI", 12, "bold"), fill=FG_TITLE)

        # CR / EQ / SYM indicators
        y = 45
        for label, val in [("CR", cr), ("EQ", eq), ("SYM", sym)]:
            c = ACCENT_GREEN if val else ACCENT_RED
            self.create_oval(18, y, 28, y + 10, fill=c, outline="")
            self.create_text(50, y + 5, text=label,
                             font=("Segoe UI", 9), fill=FG_TEXT)
            y += 20


class BandwidthBar(tk.Canvas):
    """Bant genisligi gorseli."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, width=400, height=50,
                         bg=BG_CARD, highlightthickness=0, **kwargs)

    def set_values(self, current, maximum):
        self.delete("all")
        w, h = 400, 50
        bar_y = 25
        bar_h = 16

        # Background
        self.create_rectangle(10, bar_y, w - 10, bar_y + bar_h,
                              fill=BAR_BG, outline="")

        # Fill
        if maximum > 0:
            ratio = min(current / maximum, 1.0)
            fill_w = (w - 20) * ratio
            color = ACCENT_GREEN if ratio >= 0.9 else (ACCENT_YELLOW if ratio >= 0.5 else ACCENT_RED)
            self.create_rectangle(10, bar_y, 10 + fill_w, bar_y + bar_h,
                                  fill=color, outline="")

        # Labels
        self.create_text(10, 10, anchor="w",
                         text=f"Aktif: {current:.1f} Gbps",
                         font=("Segoe UI", 10, "bold"), fill=ACCENT_CYAN)
        self.create_text(w - 10, 10, anchor="e",
                         text=f"Max: {maximum:.1f} Gbps",
                         font=("Segoe UI", 10), fill=FG_DIM)


class DPTestApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DisplayPort Kablo Test")
        self.root.configure(bg=BG_DARK)
        self.root.minsize(900, 700)

        # Scrollable main frame
        self.canvas = tk.Canvas(root, bg=BG_DARK, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(root, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg=BG_DARK)

        self.scroll_frame.bind("<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Mouse wheel
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))

        # Canvas resize
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        self._build_ui()
        self.root.after(100, self.run_test)

    def _on_canvas_resize(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _build_ui(self):
        f = self.scroll_frame

        # Header
        hdr = tk.Frame(f, bg=BG_CARD2, pady=15)
        hdr.pack(fill="x", padx=10, pady=(10, 5))
        tk.Label(hdr, text="DISPLAYPORT KABLO TEST",
                 font=("Segoe UI", 22, "bold"), fg=ACCENT_CYAN,
                 bg=BG_CARD2).pack()
        tk.Label(hdr, text="Kablo versiyonu, kalitesi, hizi ve destekledigi teknolojiler",
                 font=("Segoe UI", 10), fg=FG_DIM, bg=BG_CARD2).pack()

        # Content area (bos, test sonrasi doldurulacak)
        self.content_frame = tk.Frame(f, bg=BG_DARK)
        self.content_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Status bar
        self.status_var = tk.StringVar(value="Taranıyor...")
        self.status_bar = tk.Label(f, textvariable=self.status_var,
                                   font=("Segoe UI", 9), fg=FG_DIM,
                                   bg=BG_DARK, anchor="w")
        self.status_bar.pack(fill="x", padx=15, pady=(0, 10))

    def run_test(self):
        # Clear
        for w in self.content_frame.winfo_children():
            w.destroy()

        if os.geteuid() != 0:
            self._show_error("Root yetkisi gerekli!\nsudo python3 dp_cable_test_gui.py")
            return

        connections = find_dp_connections()
        if not connections:
            self._show_error("DisplayPort konnektor bulunamadi!")
            return

        found = False
        for conn in connections:
            if conn["status"] != "connected":
                continue
            found = True
            aux = find_aux_for_connector(conn["name"])
            if not aux:
                self._show_error(f"AUX cihazi bulunamadi: {conn['name']}")
                continue
            analysis = analyze_dp(aux, conn["name"], conn["edid_path"])
            self._show_analysis(analysis)

        if not found:
            self._show_error("Bagli DisplayPort kablo bulunamadi!\nBir DP kablo takili oldugundan emin olun.")
            return

        self.status_var.set(f"Test tamamlandi - {len(connections)} konnektor bulundu")

        # Refresh butonu
        btn_frame = tk.Frame(self.content_frame, bg=BG_DARK)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Yeniden Tara", command=self.run_test,
                  font=("Segoe UI", 11, "bold"), fg=BG_DARK, bg=ACCENT_CYAN,
                  activebackground=ACCENT_BLUE, relief="flat", padx=20, pady=8,
                  cursor="hand2").pack()

    def _show_error(self, msg):
        frm = tk.Frame(self.content_frame, bg=BG_CARD, padx=30, pady=30)
        frm.pack(fill="x", pady=20)
        tk.Label(frm, text="HATA", font=("Segoe UI", 16, "bold"),
                 fg=ACCENT_RED, bg=BG_CARD).pack()
        tk.Label(frm, text=msg, font=("Segoe UI", 12),
                 fg=FG_TEXT, bg=BG_CARD).pack(pady=10)
        self.status_var.set("Hata olustu")

    def _card(self, parent, title):
        """Karti olustur."""
        card = tk.Frame(parent, bg=BG_CARD, padx=15, pady=12)
        card.pack(fill="x", pady=4)
        tk.Label(card, text=title, font=("Segoe UI", 13, "bold"),
                 fg=ACCENT_CYAN, bg=BG_CARD, anchor="w").pack(fill="x")
        tk.Frame(card, bg=ACCENT_BLUE, height=1).pack(fill="x", pady=(4, 8))
        body = tk.Frame(card, bg=BG_CARD)
        body.pack(fill="x")
        return body

    def _kv_row(self, parent, key, value, row, val_color=FG_TEXT):
        tk.Label(parent, text=key, font=("Segoe UI", 10),
                 fg=FG_DIM, bg=BG_CARD, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(0, 15), pady=1)
        tk.Label(parent, text=value, font=("Segoe UI", 10, "bold"),
                 fg=val_color, bg=BG_CARD, anchor="w").grid(
            row=row, column=1, sticky="w", pady=1)

    def _show_analysis(self, a: DPAnalysis):
        parent = self.content_frame

        # ====== Top row: Score + Connection Info ======
        top = tk.Frame(parent, bg=BG_DARK)
        top.pack(fill="x", pady=4)
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=2)

        # Score gauge
        score_card = tk.Frame(top, bg=BG_CARD, padx=15, pady=12)
        score_card.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        tk.Label(score_card, text="KABLO KALITESI",
                 font=("Segoe UI", 13, "bold"), fg=ACCENT_CYAN,
                 bg=BG_CARD).pack()
        tk.Frame(score_card, bg=ACCENT_BLUE, height=1).pack(fill="x", pady=(4, 8))

        gauge = ScoreGauge(score_card, size=200)
        gauge.pack(pady=5)
        gauge.set_score(a.quality_score, a.quality_grade)

        if a.issues:
            for issue in a.issues:
                tk.Label(score_card, text=f"! {issue}",
                         font=("Segoe UI", 9), fg=ACCENT_YELLOW,
                         bg=BG_CARD, anchor="w", wraplength=250).pack(anchor="w")
        else:
            tk.Label(score_card, text="Sorun bulunamadi",
                     font=("Segoe UI", 10), fg=ACCENT_GREEN,
                     bg=BG_CARD).pack()

        # Connection info
        conn_body = tk.Frame(top, bg=BG_CARD, padx=15, pady=12)
        conn_body.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        tk.Label(conn_body, text="BAGLANTI BILGISI",
                 font=("Segoe UI", 13, "bold"), fg=ACCENT_CYAN,
                 bg=BG_CARD).pack(anchor="w")
        tk.Frame(conn_body, bg=ACCENT_BLUE, height=1).pack(fill="x", pady=(4, 8))

        info_grid = tk.Frame(conn_body, bg=BG_CARD)
        info_grid.pack(fill="x")

        row = 0
        self._kv_row(info_grid, "Connector", a.connector_name, row); row += 1
        self._kv_row(info_grid, "AUX Device", a.aux_device, row); row += 1
        if a.edid:
            self._kv_row(info_grid, "Monitor", f"{a.edid.manufacturer} {a.edid.model_name}", row, ACCENT_CYAN); row += 1
            if a.edid.serial:
                self._kv_row(info_grid, "Seri No", a.edid.serial, row); row += 1
            self._kv_row(info_grid, "Uretim", f"Hafta {a.edid.week}, {a.edid.year}", row); row += 1
            self._kv_row(info_grid, "EDID", a.edid.edid_version, row); row += 1
            if a.edid.max_hpixels:
                self._kv_row(info_grid, "Panel", f"{a.edid.max_hpixels}x{a.edid.max_vpixels}", row); row += 1

        self._kv_row(info_grid, "DP Versiyon", a.dp_version, row, ACCENT_GREEN); row += 1
        self._kv_row(info_grid, "DPCD Rev", f"{a.dpcd_major}.{a.dpcd_minor}", row); row += 1
        self._kv_row(info_grid, "Link Rate", f"{a.max_link_rate_gbps:.2f} Gbps/lane ({a.link_rate_name})", row, ACCENT_CYAN); row += 1
        self._kv_row(info_grid, "Lane Sayisi", str(a.max_lane_count), row); row += 1

        # ====== Bandwidth ======
        bw_body = self._card(parent, "BANT GENISLIGI")
        bw_bar = BandwidthBar(bw_body)
        bw_bar.pack(fill="x", pady=5)
        bw_bar.set_values(a.current_bandwidth_gbps, a.effective_bandwidth_gbps)

        bw_grid = tk.Frame(bw_body, bg=BG_CARD)
        bw_grid.pack(fill="x")
        self._kv_row(bw_grid, "Toplam (ham)", f"{a.total_bandwidth_gbps:.2f} Gbps", 0)
        self._kv_row(bw_grid, "Efektif (8b/10b)", f"{a.effective_bandwidth_gbps:.2f} Gbps", 1, ACCENT_GREEN)
        self._kv_row(bw_grid, "Aktif Link Rate", f"{a.current_link_rate_gbps:.2f} Gbps/lane" if a.current_link_rate_gbps else "N/A", 2)
        self._kv_row(bw_grid, "Aktif Lane", str(a.current_lane_count) if a.current_lane_count else "N/A", 3)

        # ====== Lane Status ======
        if a.lanes_synced:
            lane_body = self._card(parent, "LANE DURUMU")
            lane_row = tk.Frame(lane_body, bg=BG_CARD)
            lane_row.pack()

            for l in a.lanes_synced:
                li = LaneIndicator(lane_row, l["lane"])
                li.pack(side="left", padx=8, pady=5)
                li.set_status(l["cr"], l["eq"], l["sym"], l["ok"])

            align_color = ACCENT_GREEN if a.link_aligned else ACCENT_RED
            align_text = "HIZALAMA: BASARILI" if a.link_aligned else "HIZALAMA: BASARISIZ"
            tk.Label(lane_body, text=align_text,
                     font=("Segoe UI", 11, "bold"), fg=align_color,
                     bg=BG_CARD).pack(pady=(5, 0))

        # ====== Features ======
        feat_body = self._card(parent, "DESTEKLENEN TEKNOLOJILER")
        cols = 2
        for i, feat in enumerate(a.supported_features):
            r, col = divmod(i, cols)
            tk.Label(feat_body, text=f"  +  {feat}",
                     font=("Segoe UI", 10), fg=ACCENT_GREEN,
                     bg=BG_CARD, anchor="w").grid(
                row=r, column=col, sticky="w", padx=(0, 30), pady=1)

        # ====== Resolution Table ======
        res_body = self._card(parent, "COZUNURLUK DESTEGI")

        # Table header
        hdr_frame = tk.Frame(res_body, bg=BG_CARD2)
        hdr_frame.pack(fill="x")
        headers = [("Cozunurluk", 120), ("Hz", 50), ("Gerekli", 90), ("Durum", 100)]
        for text, w in headers:
            tk.Label(hdr_frame, text=text, font=("Segoe UI", 9, "bold"),
                     fg=FG_DIM, bg=BG_CARD2, width=w // 8,
                     anchor="w").pack(side="left", padx=5)

        # Table rows
        for r in a.max_resolutions:
            row_frame = tk.Frame(res_body, bg=BG_CARD)
            row_frame.pack(fill="x")

            tk.Label(row_frame, text=f"{r['res']} ({r['w']}x{r['h']})",
                     font=("Segoe UI", 9), fg=FG_TEXT, bg=BG_CARD,
                     width=15, anchor="w").pack(side="left", padx=5)
            tk.Label(row_frame, text=f"{r['hz']}",
                     font=("Segoe UI", 9), fg=FG_TEXT, bg=BG_CARD,
                     width=6, anchor="w").pack(side="left", padx=5)
            tk.Label(row_frame, text=f"{r['req']:.1f} Gbps",
                     font=("Segoe UI", 9), fg=FG_DIM, bg=BG_CARD,
                     width=11, anchor="w").pack(side="left", padx=5)

            if r["ok"]:
                st_text, st_color = "DESTEKLI", ACCENT_GREEN
            elif r["dsc"]:
                st_text, st_color = "DSC GEREK", ACCENT_YELLOW
            else:
                st_text, st_color = "YETERSIZ", ACCENT_RED

            tk.Label(row_frame, text=st_text,
                     font=("Segoe UI", 9, "bold"), fg=st_color, bg=BG_CARD,
                     width=12, anchor="w").pack(side="left", padx=5)


# ============================================================
# Main
# ============================================================

def main():
    if os.geteuid() != 0:
        # Try launching with pkexec
        try:
            import subprocess
            subprocess.Popen(["pkexec", sys.executable] + sys.argv)
            sys.exit(0)
        except Exception:
            pass

    root = tk.Tk()
    root.geometry("920x750")

    # Dark theme for ttk
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Vertical.TScrollbar",
                    background=BAR_BG, troughcolor=BG_DARK,
                    arrowcolor=FG_DIM)

    app = DPTestApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
