#!/usr/bin/env python3
"""
DisplayPort Kablo Test Programi
================================
Takili DisplayPort kablonun versiyonunu, kalitesini, hizini
ve destekledigi maksimum teknolojileri olcer.

Kullanim: sudo python3 dp_cable_test.py
"""

import os
import sys
import struct
import glob
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# ============================================================
# DPCD Register Adresleri (DP Standard)
# ============================================================
DPCD_REV            = 0x0000
DPCD_MAX_LINK_RATE  = 0x0001
DPCD_MAX_LANE_COUNT = 0x0002
DPCD_MAX_DOWNSPREAD = 0x0003
DPCD_NORP           = 0x0004
DPCD_DOWNSTREAMPORT = 0x0005
DPCD_MAIN_LINK_CODING = 0x0006
DPCD_DOWN_STREAM_PORT_COUNT = 0x0007
DPCD_RECEIVE_PORT0_CAP0 = 0x0008
DPCD_RECEIVE_PORT0_CAP1 = 0x0009
DPCD_I2C_SPEED_CTRL = 0x000C
DPCD_EDP_CONFIG     = 0x000D
DPCD_TRAINING_AUX   = 0x000E

DPCD_LINK_BW_SET    = 0x0100
DPCD_LANE_COUNT_SET = 0x0101

DPCD_LINK_STATUS_0  = 0x0200  # SINK_COUNT
DPCD_LINK_STATUS_1  = 0x0201  # DEVICE_SERVICE_IRQ_VECTOR
DPCD_LANE01_STATUS  = 0x0202
DPCD_LANE23_STATUS  = 0x0203
DPCD_LANE_ALIGN     = 0x0204
DPCD_SINK_STATUS    = 0x0205

DPCD_ADJUST_REQ_01  = 0x0206
DPCD_ADJUST_REQ_23  = 0x0207

DPCD_TRAINING_SCORE_01 = 0x0208
DPCD_TRAINING_SCORE_23 = 0x0209

# Extended (DP 1.4+)
DPCD_EXTENDED_CAP   = 0x2200

# FEC (Forward Error Correction)
DPCD_FEC_CAPABILITY = 0x0090
DPCD_DSC_SUPPORT    = 0x0060

# ============================================================
# Link Rate Kodlari -> Gercek Hiz
# ============================================================
LINK_RATE_MAP = {
    0x06: ("1.62 Gbps/lane", 1.62,  "RBR",   "1.0"),
    0x0A: ("2.70 Gbps/lane", 2.70,  "HBR",   "1.1"),
    0x14: ("5.40 Gbps/lane", 5.40,  "HBR2",  "1.2"),
    0x1E: ("8.10 Gbps/lane", 8.10,  "HBR3",  "1.3+"),
}

# DPCD Revizyon -> DP Versiyonu
DPCD_REV_MAP = {
    (1, 0): "1.0",
    (1, 1): "1.1",
    (1, 2): "1.2",
    (1, 3): "1.3",
    (1, 4): "1.4",
    (2, 0): "2.0",
    (2, 1): "2.1",
}

# ============================================================
# Renk Kodlari (Terminal)
# ============================================================
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BLUE   = "\033[94m"
    MAGENTA= "\033[95m"
    DIM    = "\033[2m"
    WHITE  = "\033[97m"
    BG_DARK = "\033[48;5;234m"

def color_enabled():
    return sys.stdout.isatty()

def c(code, text):
    if color_enabled():
        return f"{code}{text}{C.RESET}"
    return text

# ============================================================
# DPCD Okuyucu
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
        except (PermissionError, OSError) as e:
            return b''

    def read_byte(self, offset: int) -> int | None:
        data = self.read(offset, 1)
        if data:
            return data[0]
        return None

    def read_bytes(self, offset: int, count: int) -> list[int]:
        data = self.read(offset, count)
        return list(data) if data else []


# ============================================================
# EDID Parser (Temel)
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
    detailed_timings: list = field(default_factory=list)
    cea_modes: list = field(default_factory=list)

def parse_edid(raw: bytes) -> EDIDInfo | None:
    if len(raw) < 128:
        return None
    # Check header
    if raw[0:8] != b'\x00\xff\xff\xff\xff\xff\xff\x00':
        return None

    info = EDIDInfo()

    # Manufacturer ID (bytes 8-9)
    mfg_id = (raw[8] << 8) | raw[9]
    c1 = chr(((mfg_id >> 10) & 0x1F) + ord('A') - 1)
    c2 = chr(((mfg_id >> 5) & 0x1F) + ord('A') - 1)
    c3 = chr((mfg_id & 0x1F) + ord('A') - 1)
    info.manufacturer = f"{c1}{c2}{c3}"

    # Year/week
    info.week = raw[16]
    info.year = raw[17] + 1990
    info.edid_version = f"{raw[18]}.{raw[19]}"

    # Detailed Timing Descriptors (bytes 54-125, 4 x 18-byte blocks)
    for i in range(4):
        offset = 54 + i * 18
        block = raw[offset:offset+18]

        # Check if it's a descriptor or timing
        if block[0] == 0 and block[1] == 0:
            # Descriptor
            tag = block[3]
            if tag == 0xFC:  # Monitor Name
                info.model_name = block[5:18].decode('ascii', errors='ignore').strip()
            elif tag == 0xFF:  # Serial
                info.serial = block[5:18].decode('ascii', errors='ignore').strip()
            elif tag == 0xFD:  # Monitor Range Limits
                info.max_refresh = block[8]  # Max vertical rate
                if block[4] & 0x02:  # DP 1.4a range limit offset
                    info.max_refresh += 255
        else:
            # Detailed Timing
            pixel_clock = (block[1] << 8 | block[0]) * 10000  # Hz
            if pixel_clock == 0:
                continue
            h_active = ((block[4] & 0xF0) << 4) | block[2]
            v_active = ((block[7] & 0xF0) << 4) | block[5]
            h_blank = ((block[4] & 0x0F) << 8) | block[3]
            v_blank = ((block[7] & 0x0F) << 8) | block[6]
            h_total = h_active + h_blank
            v_total = v_active + v_blank
            if h_total > 0 and v_total > 0:
                refresh = pixel_clock / (h_total * v_total)
                info.detailed_timings.append((h_active, v_active, refresh, pixel_clock))
                if h_active > info.max_hpixels:
                    info.max_hpixels = h_active
                    info.max_vpixels = v_active

    # CEA Extension block (if present)
    if len(raw) >= 256 and raw[128] == 0x02:
        cea = raw[128:256]
        dtd_offset = cea[2]
        if 4 < dtd_offset < 127:
            pos = 4
            while pos < dtd_offset:
                tag_code = (cea[pos] >> 5) & 0x07
                block_len = cea[pos] & 0x1F
                if tag_code == 0:
                    break
                pos += 1 + block_len

    return info


# ============================================================
# Kablo / Link Analizi
# ============================================================
@dataclass
class DPAnalysis:
    # DPCD bilgileri
    dpcd_major: int = 0
    dpcd_minor: int = 0
    dp_version: str = "Bilinmiyor"
    max_link_rate_code: int = 0
    max_link_rate_gbps: float = 0.0
    link_rate_name: str = ""
    min_dp_version: str = ""
    max_lane_count: int = 0
    enhanced_framing: bool = False
    tps3_support: bool = False
    tps4_support: bool = False
    fec_support: bool = False
    dsc_support: bool = False
    mst_support: bool = False  # Multi-Stream Transport
    total_bandwidth_gbps: float = 0.0
    effective_bandwidth_gbps: float = 0.0

    # Aktif link durumu
    current_link_rate_code: int = 0
    current_link_rate_gbps: float = 0.0
    current_lane_count: int = 0
    lanes_synced: list = field(default_factory=list)
    link_aligned: bool = False
    current_bandwidth_gbps: float = 0.0

    # Kalite metrikleri
    quality_score: int = 0  # 0-100
    quality_grade: str = ""
    issues: list = field(default_factory=list)

    # Desteklenen teknolojiler
    max_resolutions: list = field(default_factory=list)
    supported_features: list = field(default_factory=list)

    # EDID
    edid: EDIDInfo | None = None

    # Connector bilgisi
    connector_name: str = ""
    aux_device: str = ""


def analyze_dp(aux_path: str, connector: str, edid_path: str | None) -> DPAnalysis:
    """Tek bir DP baglantisini analiz et."""
    reader = DPCDReader(aux_path)
    a = DPAnalysis()
    a.connector_name = connector
    a.aux_device = aux_path

    # --- DPCD Revision ---
    rev = reader.read_byte(DPCD_REV)
    if rev is None:
        a.issues.append("DPCD okunamiyor")
        return a

    a.dpcd_major = (rev >> 4) & 0x0F
    a.dpcd_minor = rev & 0x0F
    a.dp_version = DPCD_REV_MAP.get((a.dpcd_major, a.dpcd_minor), f"{a.dpcd_major}.{a.dpcd_minor}")

    # --- Max Link Rate ---
    rate_code = reader.read_byte(DPCD_MAX_LINK_RATE)
    if rate_code and rate_code in LINK_RATE_MAP:
        name, gbps, short, min_ver = LINK_RATE_MAP[rate_code]
        a.max_link_rate_code = rate_code
        a.max_link_rate_gbps = gbps
        a.link_rate_name = short
        a.min_dp_version = min_ver

    # --- Max Lane Count ---
    lane_byte = reader.read_byte(DPCD_MAX_LANE_COUNT)
    if lane_byte:
        a.max_lane_count = lane_byte & 0x1F
        a.enhanced_framing = bool(lane_byte & 0x80)
        a.tps3_support = bool(lane_byte & 0x40)

    # --- TPS4 Support (DP 1.3+) ---
    training_byte = reader.read_byte(DPCD_TRAINING_AUX)
    if training_byte:
        a.tps4_support = bool(training_byte & 0x80)

    # --- Multi-Stream Transport ---
    mstm = reader.read_byte(0x0021)
    if mstm:
        a.mst_support = bool(mstm & 0x01)

    # --- FEC Support (DP 1.4+) ---
    fec_byte = reader.read_byte(DPCD_FEC_CAPABILITY)
    if fec_byte:
        a.fec_support = bool(fec_byte & 0x01)

    # --- DSC Support ---
    dsc_byte = reader.read_byte(DPCD_DSC_SUPPORT)
    if dsc_byte:
        a.dsc_support = bool(dsc_byte & 0x01)

    # --- Toplam Bant Genisligi ---
    if a.max_link_rate_gbps and a.max_lane_count:
        a.total_bandwidth_gbps = a.max_link_rate_gbps * a.max_lane_count
        # 8b/10b encoding overhead (%20 kayip)
        a.effective_bandwidth_gbps = a.total_bandwidth_gbps * 0.80

    # --- Aktif Link Durumu ---
    current_rate = reader.read_byte(DPCD_LINK_BW_SET)
    if current_rate and current_rate in LINK_RATE_MAP:
        a.current_link_rate_code = current_rate
        a.current_link_rate_gbps = LINK_RATE_MAP[current_rate][1]

    current_lanes = reader.read_byte(DPCD_LANE_COUNT_SET)
    if current_lanes:
        a.current_lane_count = current_lanes & 0x1F

    if a.current_link_rate_gbps and a.current_lane_count:
        a.current_bandwidth_gbps = a.current_link_rate_gbps * a.current_lane_count * 0.80

    # --- Lane Status ---
    lane01 = reader.read_byte(DPCD_LANE01_STATUS)
    lane23 = reader.read_byte(DPCD_LANE23_STATUS)
    align  = reader.read_byte(DPCD_LANE_ALIGN)

    if lane01 is not None:
        # Lane 0
        l0_cr = bool(lane01 & 0x01)
        l0_eq = bool(lane01 & 0x02)
        l0_sym = bool(lane01 & 0x04)
        a.lanes_synced.append({"lane": 0, "cr": l0_cr, "eq": l0_eq, "sym": l0_sym, "ok": l0_cr and l0_eq and l0_sym})
        # Lane 1
        l1_cr = bool(lane01 & 0x10)
        l1_eq = bool(lane01 & 0x20)
        l1_sym = bool(lane01 & 0x40)
        a.lanes_synced.append({"lane": 1, "cr": l1_cr, "eq": l1_eq, "sym": l1_sym, "ok": l1_cr and l1_eq and l1_sym})

    if lane23 is not None and a.current_lane_count > 2:
        l2_cr = bool(lane23 & 0x01)
        l2_eq = bool(lane23 & 0x02)
        l2_sym = bool(lane23 & 0x04)
        a.lanes_synced.append({"lane": 2, "cr": l2_cr, "eq": l2_eq, "sym": l2_sym, "ok": l2_cr and l2_eq and l2_sym})
        l3_cr = bool(lane23 & 0x10)
        l3_eq = bool(lane23 & 0x20)
        l3_sym = bool(lane23 & 0x40)
        a.lanes_synced.append({"lane": 3, "cr": l3_cr, "eq": l3_eq, "sym": l3_sym, "ok": l3_cr and l3_eq and l3_sym})

    if align is not None:
        a.link_aligned = bool(align & 0x01)

    # --- EDID ---
    if edid_path and os.path.exists(edid_path):
        try:
            with open(edid_path, 'rb') as f:
                edid_raw = f.read()
            a.edid = parse_edid(edid_raw)
        except Exception:
            pass

    # --- Kalite Hesapla ---
    a.quality_score, a.quality_grade, a.issues = calculate_quality(a)

    # --- Desteklenen Cozunurlukler ---
    a.max_resolutions = calculate_max_resolutions(a)

    # --- Desteklenen Ozellikler ---
    a.supported_features = calculate_features(a)

    return a


def calculate_quality(a: DPAnalysis) -> tuple[int, str, list]:
    """Kablo kalite puani hesapla."""
    score = 100
    issues = list(a.issues)

    # Link rate negotiation check
    if a.current_link_rate_gbps and a.max_link_rate_gbps:
        rate_ratio = a.current_link_rate_gbps / a.max_link_rate_gbps
        if rate_ratio < 1.0:
            penalty = int((1.0 - rate_ratio) * 40)
            score -= penalty
            issues.append(f"Link hizi dusurulmus: {a.current_link_rate_gbps:.2f} / {a.max_link_rate_gbps:.2f} Gbps/lane ({rate_ratio:.0%})")

    # Lane count check
    if a.current_lane_count and a.max_lane_count:
        if a.current_lane_count < a.max_lane_count:
            score -= 20
            issues.append(f"Lane sayisi dusurulmus: {a.current_lane_count}/{a.max_lane_count}")

    # Lane sync check
    bad_lanes = [l for l in a.lanes_synced if not l["ok"]]
    if bad_lanes:
        score -= len(bad_lanes) * 15
        for l in bad_lanes:
            parts = []
            if not l["cr"]: parts.append("CR")
            if not l["eq"]: parts.append("EQ")
            if not l["sym"]: parts.append("SYM")
            issues.append(f"Lane {l['lane']} sorunlu: {', '.join(parts)} basarisiz")

    # Alignment check
    if a.lanes_synced and not a.link_aligned:
        score -= 15
        issues.append("Lane hizalamasi basarisiz")

    # Enhanced framing
    if not a.enhanced_framing and a.max_link_rate_gbps > 2.7:
        score -= 5
        issues.append("Enhanced framing destegi yok (yuksek hizlarda onemli)")

    score = max(0, min(100, score))

    if score >= 90:
        grade = "MUKEMMEL"
    elif score >= 75:
        grade = "IYI"
    elif score >= 50:
        grade = "ORTA"
    elif score >= 25:
        grade = "ZAYIF"
    else:
        grade = "KOTU"

    return score, grade, issues


def calculate_max_resolutions(a: DPAnalysis) -> list[dict]:
    """Bu bant genisligi ile desteklenen maksimum cozunurlukler."""
    bw = a.effective_bandwidth_gbps
    if not bw:
        return []

    # Yaygin cozunurlukler: (isim, genislik, yukseklik, bpp, min_bw_gbps_at_60hz)
    common_res = [
        ("8K (7680x4320)",  7680, 4320, 24),
        ("5K (5120x2880)",  5120, 2880, 24),
        ("4K (3840x2160)",  3840, 2160, 24),
        ("WQHD (2560x1440)", 2560, 1440, 24),
        ("FHD (1920x1080)", 1920, 1080, 24),
    ]

    refresh_rates = [60, 120, 144, 165, 240, 360]
    results = []

    for name, w, h, bpp in common_res:
        for hz in refresh_rates:
            # Basit bant genisligi hesabi: width * height * bpp * refresh / 1e9
            # Blanking overhead ~%6 ekle
            required_gbps = (w * h * bpp * hz * 1.06) / 1e9
            supported = required_gbps <= bw
            dsc_possible = required_gbps <= bw * 3 and a.dsc_support  # DSC ~3x compression
            results.append({
                "resolution": name,
                "refresh": hz,
                "required_gbps": required_gbps,
                "supported": supported,
                "dsc_possible": dsc_possible and not supported,
            })

    return results


def calculate_features(a: DPAnalysis) -> list[str]:
    """Desteklenen teknoloji ve ozellikleri listele."""
    features = []

    if a.dp_version != "Bilinmiyor":
        features.append(f"DisplayPort {a.dp_version}")

    features.append(f"{a.link_rate_name} ({a.max_link_rate_gbps:.2f} Gbps/lane)" if a.link_rate_name else "")

    if a.max_lane_count:
        features.append(f"{a.max_lane_count}x Lane")

    if a.enhanced_framing:
        features.append("Enhanced Framing")

    if a.tps3_support:
        features.append("TPS3 (Link Training Pattern 3)")

    if a.tps4_support:
        features.append("TPS4 (Link Training Pattern 4)")

    if a.mst_support:
        features.append("MST (Multi-Stream Transport / Daisy-Chain)")

    if a.fec_support:
        features.append("FEC (Forward Error Correction)")

    if a.dsc_support:
        features.append("DSC (Display Stream Compression)")

    # HDR/HBR ozellikleri
    if a.max_link_rate_gbps >= 8.1:
        features.append("HDR10 / HDR10+ Destegi")
        features.append("10-bit / 12-bit Renk Derinligi")
    elif a.max_link_rate_gbps >= 5.4:
        features.append("HDR10 Destegi (sinirli)")
        features.append("10-bit Renk Derinligi")
    elif a.max_link_rate_gbps >= 2.7:
        features.append("8-bit Renk Derinligi")

    # Adaptive Sync
    if a.dpcd_major >= 1 and a.dpcd_minor >= 3:
        features.append("Adaptive Sync (FreeSync / G-Sync Uyumlu)")
    elif a.dpcd_major >= 1 and a.dpcd_minor >= 2:
        features.append("Adaptive Sync (sinirli)")

    # Audio
    features.append("DP Audio (7.1 Surround)")

    return [f for f in features if f]


# ============================================================
# Cikti / Raporlama
# ============================================================

def print_header():
    w = 72
    print()
    print(c(C.CYAN + C.BOLD, "=" * w))
    print(c(C.CYAN + C.BOLD, "   DISPLAYPORT KABLO TEST PROGRAMI"))
    print(c(C.CYAN + C.BOLD, "=" * w))
    print()


def print_section(title: str):
    print()
    print(c(C.BLUE + C.BOLD, f"--- {title} " + "-" * (55 - len(title))))


def kv(key: str, value: str, indent: int = 2):
    pad = " " * indent
    print(f"{pad}{c(C.DIM, key + ':')} {c(C.WHITE + C.BOLD, value)}")


def print_analysis(a: DPAnalysis):
    """Analiz sonuclarini goster."""

    # --- Baglanti Bilgisi ---
    print_section("BAGLANTI BILGISI")
    kv("Connector", a.connector_name)
    kv("AUX Device", a.aux_device)

    if a.edid:
        kv("Monitor", f"{a.edid.manufacturer} {a.edid.model_name}")
        if a.edid.serial:
            kv("Seri No", a.edid.serial)
        kv("Uretim", f"Hafta {a.edid.week}, {a.edid.year}")
        kv("EDID Versiyon", a.edid.edid_version)

    # --- DP Versiyon & Hiz ---
    print_section("DISPLAYPORT VERSIYON & HIZ")
    kv("DPCD Revizyon", f"{a.dpcd_major}.{a.dpcd_minor}")
    kv("DP Versiyon", a.dp_version)
    kv("Max Link Rate", f"{a.max_link_rate_gbps:.2f} Gbps/lane ({a.link_rate_name})")
    kv("Max Lane Sayisi", str(a.max_lane_count))
    kv("Toplam Bant Genisligi", f"{a.total_bandwidth_gbps:.2f} Gbps (ham)")
    kv("Efektif Bant Genisligi", f"{a.effective_bandwidth_gbps:.2f} Gbps (8b/10b sonrasi)")

    # --- Aktif Link Durumu ---
    print_section("AKTIF LINK DURUMU")
    if a.current_link_rate_gbps:
        kv("Aktif Link Rate", f"{a.current_link_rate_gbps:.2f} Gbps/lane")
    else:
        kv("Aktif Link Rate", "Okunamiyor")
    kv("Aktif Lane Sayisi", str(a.current_lane_count) if a.current_lane_count else "Okunamiyor")
    kv("Aktif Bant Genisligi", f"{a.current_bandwidth_gbps:.2f} Gbps" if a.current_bandwidth_gbps else "N/A")

    # Lane detay
    if a.lanes_synced:
        print()
        header = "  Lane   CR    EQ    SYM   Durum"
        print(c(C.DIM, header))
        print(c(C.DIM, "  " + "-" * 35))
        for l in a.lanes_synced:
            cr  = c(C.GREEN, " OK ") if l["cr"]  else c(C.RED, "FAIL")
            eq  = c(C.GREEN, " OK ") if l["eq"]  else c(C.RED, "FAIL")
            sym = c(C.GREEN, " OK ") if l["sym"] else c(C.RED, "FAIL")
            ok  = c(C.GREEN + C.BOLD, "  SENKRON") if l["ok"] else c(C.RED + C.BOLD, "  SORUNLU")
            print(f"   {l['lane']}    {cr}  {eq}  {sym}  {ok}")

    if a.lanes_synced:
        aligned_str = c(C.GREEN + C.BOLD, "EVET") if a.link_aligned else c(C.RED + C.BOLD, "HAYIR")
        kv("Lane Hizalama", aligned_str)

    # --- Kalite ---
    print_section("KABLO KALITE DEGERLENDIRMESI")

    score_color = C.GREEN if a.quality_score >= 75 else (C.YELLOW if a.quality_score >= 50 else C.RED)
    bar_len = 40
    filled = int(a.quality_score / 100 * bar_len)
    bar = c(score_color + C.BOLD, "#" * filled) + c(C.DIM, "-" * (bar_len - filled))

    print(f"  {bar}  {c(score_color + C.BOLD, f'{a.quality_score}/100')}  {c(score_color + C.BOLD, a.quality_grade)}")

    if a.issues:
        print()
        for issue in a.issues:
            print(f"  {c(C.YELLOW, '!')} {issue}")
    else:
        print(f"\n  {c(C.GREEN, 'Sorun bulunamadi.')}")

    # --- Desteklenen Ozellikler ---
    print_section("DESTEKLENEN TEKNOLOJILER")
    for feat in a.supported_features:
        print(f"  {c(C.GREEN, '+')} {feat}")

    # --- Cozunurluk Tablosu ---
    print_section("DESTEKLENEN COZUNURLUKLER")
    print(f"  {'Cozunurluk':<22} {'Hz':>5}  {'Gerekli':>10}  {'Durum':>12}")
    print(f"  {'-'*55}")

    printed_resolutions = set()
    for r in a.max_resolutions:
        key = f"{r['resolution']}@{r['refresh']}"
        if key in printed_resolutions:
            continue
        printed_resolutions.add(key)

        if r["supported"]:
            status = c(C.GREEN + C.BOLD, "  DESTEKLI")
        elif r["dsc_possible"]:
            status = c(C.YELLOW, "  DSC GEREK")
        else:
            status = c(C.RED, "  YETERSIZ")

        gbps_str = f"{r['required_gbps']:.1f} Gbps"
        print(f"  {r['resolution']:<22} {r['refresh']:>4}  {gbps_str:>10}  {status}")

    print()


# ============================================================
# DP Konnektor Bulma
# ============================================================

def find_dp_connections() -> list[dict]:
    """Sistemdeki tum DP konnektorleri bul."""
    connections = []
    drm_path = Path("/sys/class/drm")

    if not drm_path.exists():
        return connections

    for connector_dir in sorted(drm_path.iterdir()):
        name = connector_dir.name
        if "DP" not in name:
            continue

        status_file = connector_dir / "status"
        if not status_file.exists():
            continue

        try:
            status = status_file.read_text().strip()
        except Exception:
            continue

        edid_path = connector_dir / "edid"
        edid_str = str(edid_path) if edid_path.exists() else None

        connections.append({
            "name": name,
            "path": str(connector_dir),
            "status": status,
            "edid_path": edid_str,
        })

    return connections


def find_aux_for_connector(connector_name: str) -> str | None:
    """Bir DP konnektor icin dogru /dev/drm_dp_aux* cihazini bul."""
    aux_devices = sorted(glob.glob("/dev/drm_dp_aux*"))

    # Yontem 1: sysfs uzerinden aux<->connector eslemesini dene
    # /sys/class/drm_dp_aux_dev/drm_dp_auxN/name veya device linkinden
    for aux in aux_devices:
        aux_name = os.path.basename(aux)
        sysfs_name = f"/sys/class/drm_dp_aux_dev/{aux_name}/name"
        if os.path.exists(sysfs_name):
            try:
                name = open(sysfs_name).read().strip()
                if connector_name in name:
                    return aux
            except Exception:
                pass

    # Yontem 2: Tum aux cihazlari dene, DPCD rev okuyabileni sec (connected olani bulur)
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
# Ana Program
# ============================================================

def main():
    print_header()

    # Root kontrol
    if os.geteuid() != 0:
        print(c(C.RED + C.BOLD, "  HATA: Bu program root yetkisi gerektirir!"))
        print(f"  Kullanim: {c(C.CYAN, 'sudo python3 dp_cable_test.py')}")
        print()
        sys.exit(1)

    # DP konnektorleri bul
    connections = find_dp_connections()
    if not connections:
        print(c(C.RED, "  Hicbir DisplayPort konnektor bulunamadi!"))
        print()
        sys.exit(1)

    print(c(C.DIM, f"  {len(connections)} DisplayPort konnektor bulundu:"))
    for conn in connections:
        status_color = C.GREEN if conn["status"] == "connected" else C.DIM
        print(f"    {c(C.WHITE, conn['name'])} - {c(status_color, conn['status'])}")
    print()

    # Her bagli konnektor icin analiz
    found_connected = False
    for conn in connections:
        if conn["status"] != "connected":
            continue

        found_connected = True
        print(c(C.CYAN + C.BOLD, f"  >>> {conn['name']} analiz ediliyor..."))

        aux = find_aux_for_connector(conn["name"])
        if not aux:
            print(c(C.RED, f"  AUX cihazi bulunamiyor: {conn['name']}"))
            continue

        analysis = analyze_dp(aux, conn["name"], conn["edid_path"])
        print_analysis(analysis)

    if not found_connected:
        print(c(C.YELLOW + C.BOLD, "  Bagli DisplayPort kablo bulunamadi!"))
        print(c(C.DIM, "  Bir DisplayPort kablo takili oldugundan emin olun."))
        print()


if __name__ == "__main__":
    main()
