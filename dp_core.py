#!/usr/bin/env python3
"""
DisplayPort Kablo Test - Ortak Cekirdek Kutuphanesi
====================================================
dp_cable_test.py ve dp_cable_test_gui.py tarafindan paylasilan
DPCD okuma, EDID ayristirma ve analiz mantigi.

Dogrudan calistirilamaz; import ederek kullanin.
"""

import os
import glob
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ============================================================
# DPCD Register Adresleri (DP Standard)
# ============================================================
DPCD_REV                    = 0x0000
DPCD_MAX_LINK_RATE          = 0x0001
DPCD_MAX_LANE_COUNT         = 0x0002
DPCD_MAX_DOWNSPREAD         = 0x0003
DPCD_DOWNSTREAMPORT         = 0x0005
DPCD_MAIN_LINK_CODING       = 0x0006
DPCD_TRAINING_AUX           = 0x000E
DPCD_LINK_BW_SET            = 0x0100
DPCD_LANE_COUNT_SET         = 0x0101
DPCD_LANE01_STATUS          = 0x0202
DPCD_LANE23_STATUS          = 0x0203
DPCD_LANE_ALIGN             = 0x0204
DPCD_SINK_STATUS            = 0x0205
DPCD_FEC_CAPABILITY         = 0x0090
DPCD_DSC_SUPPORT            = 0x0060
DPCD_MSTM_CAP               = 0x0021
DPCD_SUPPORTED_LINK_RATES   = 0x0010   # DP 1.4+ (8 x 2-byte entries)
DPCD_EXTENDED_CAP           = 0x2200   # DP 2.0+ extended register base
DPCD_UHBR_RATE_CAP          = 0x2201   # DP 2.0 UHBR rate capability

# ============================================================
# Link Rate Tablolari
# ============================================================

# Legacy DP (8b/10b): DPCD 0x0001
LINK_RATE_MAP: dict[int, tuple[str, float, str, str]] = {
    0x06: ("1.62 Gbps/lane", 1.62,  "RBR",    "1.0"),
    0x0A: ("2.70 Gbps/lane", 2.70,  "HBR",    "1.1"),
    0x14: ("5.40 Gbps/lane", 5.40,  "HBR2",   "1.2"),
    0x1E: ("8.10 Gbps/lane", 8.10,  "HBR3",   "1.3+"),
}

# DP 2.0 UHBR (128b/132b): DPCD 0x2201
# Bit 0 = UHBR10, Bit 1 = UHBR20, Bit 2 = UHBR13.5
UHBR_RATE_BITS: list[tuple[int, str, float, str]] = [
    (0x01, "UHBR10",   10.0,  "2.0"),
    (0x04, "UHBR13.5", 13.5,  "2.0"),
    (0x02, "UHBR20",   20.0,  "2.0"),
]

# DPCD Revision -> DP Version
DPCD_REV_MAP: dict[tuple[int, int], str] = {
    (1, 0): "1.0",
    (1, 1): "1.1",
    (1, 2): "1.2",
    (1, 3): "1.3",
    (1, 4): "1.4",
    (2, 0): "2.0",
    (2, 1): "2.1",
}

# ============================================================
# DPCD Okuyucu
# ============================================================
class DPCDReader:
    def __init__(self, aux_path: str) -> None:
        self.aux_path = aux_path
        self._cache: dict[tuple[int, int], bytes] = {}

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

    def read_byte(self, offset: int) -> Optional[int]:
        data = self.read(offset, 1)
        return data[0] if data else None

    def read_bytes(self, offset: int, count: int) -> list[int]:
        data = self.read(offset, count)
        return list(data) if data else []


# ============================================================
# EDID Parser
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


def _decode_mfg_id(raw: bytes) -> str:
    """EDID 2-byte manufacturer ID (PNP) kodunu coz."""
    mfg_id = (raw[8] << 8) | raw[9]
    return (
        chr(((mfg_id >> 10) & 0x1F) + ord('A') - 1)
        + chr(((mfg_id >> 5) & 0x1F) + ord('A') - 1)
        + chr((mfg_id & 0x1F) + ord('A') - 1)
    )


def parse_edid(raw: bytes) -> Optional[EDIDInfo]:
    if len(raw) < 128:
        return None
    if raw[0:8] != b'\x00\xff\xff\xff\xff\xff\xff\x00':
        return None

    info = EDIDInfo()
    info.manufacturer = _decode_mfg_id(raw)
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
            elif tag == 0xFD:
                info.max_refresh = float(block[8])
        else:
            pixel_clock = (block[1] << 8 | block[0]) * 10_000
            if pixel_clock == 0:
                continue
            h_active = ((block[4] & 0xF0) << 4) | block[2]
            v_active = ((block[7] & 0xF0) << 4) | block[5]
            h_blank  = ((block[4] & 0x0F) << 8) | block[3]
            v_blank  = ((block[7] & 0x0F) << 8) | block[6]
            h_total  = h_active + h_blank
            v_total  = v_active + v_blank
            if h_total > 0 and v_total > 0:
                refresh = pixel_clock / (h_total * v_total)
                info.detailed_timings.append((h_active, v_active, refresh, pixel_clock))
                if h_active > info.max_hpixels:
                    info.max_hpixels = h_active
                    info.max_vpixels = v_active

    return info


# ============================================================
# Analiz Veri Yapisi
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
    mst_support: bool = False
    uhbr_support: bool = False
    uhbr_rates: list[str] = field(default_factory=list)  # desteklenen UHBR modlari
    total_bandwidth_gbps: float = 0.0
    effective_bandwidth_gbps: float = 0.0
    # Aktif link durumu
    current_link_rate_gbps: float = 0.0
    current_lane_count: int = 0
    lanes_synced: list = field(default_factory=list)
    link_aligned: bool = False
    current_bandwidth_gbps: float = 0.0
    # Kalite
    quality_score: int = 0
    quality_grade: str = ""
    issues: list[str] = field(default_factory=list)
    # Yetenekler
    max_resolutions: list = field(default_factory=list)
    supported_features: list[str] = field(default_factory=list)
    # EDID
    edid: Optional[EDIDInfo] = None
    # Konnektor
    connector_name: str = ""
    aux_device: str = ""


# ============================================================
# Analiz
# ============================================================
def analyze_dp(
    aux_path: str,
    connector: str,
    edid_path: Optional[str],
) -> DPAnalysis:
    """Tek bir DP baglantisini analiz et ve DPAnalysis dondur."""
    reader = DPCDReader(aux_path)
    a = DPAnalysis(connector_name=connector, aux_device=aux_path)

    rev = reader.read_byte(DPCD_REV)
    if rev is None:
        a.issues.append("DPCD okunamiyor")
        return a

    a.dpcd_major = (rev >> 4) & 0x0F
    a.dpcd_minor = rev & 0x0F
    a.dp_version = DPCD_REV_MAP.get((a.dpcd_major, a.dpcd_minor), f"{a.dpcd_major}.{a.dpcd_minor}")

    # DP 2.0: 128b/132b encoding kontrolu
    coding_byte = reader.read_byte(DPCD_MAIN_LINK_CODING)
    uses_128b132b = bool(coding_byte and (coding_byte & 0x02))

    # UHBR hizlarini bul (DP 2.0+)
    if uses_128b132b or (a.dpcd_major >= 2):
        uhbr_cap = reader.read_byte(DPCD_UHBR_RATE_CAP)
        if uhbr_cap:
            best_gbps = 0.0
            best_name = ""
            best_min_ver = ""
            for bit, short, gbps, min_ver in UHBR_RATE_BITS:
                if uhbr_cap & bit:
                    a.uhbr_rates.append(short)
                    if gbps > best_gbps:
                        best_gbps = gbps
                        best_name = short
                        best_min_ver = min_ver
            if best_gbps > 0:
                a.uhbr_support = True
                a.max_link_rate_gbps = best_gbps
                a.link_rate_name = best_name
                a.min_dp_version = best_min_ver

    # Legacy link rate (henuz UHBR bulunamadiysa)
    if not a.uhbr_support:
        rate_code = reader.read_byte(DPCD_MAX_LINK_RATE)
        if rate_code and rate_code in LINK_RATE_MAP:
            label, gbps, short, min_ver = LINK_RATE_MAP[rate_code]
            a.max_link_rate_code = rate_code
            a.max_link_rate_gbps = gbps
            a.link_rate_name = short
            a.min_dp_version = min_ver

    # Max Lane Count
    lane_byte = reader.read_byte(DPCD_MAX_LANE_COUNT)
    if lane_byte:
        a.max_lane_count = lane_byte & 0x1F
        a.enhanced_framing = bool(lane_byte & 0x80)
        a.tps3_support = bool(lane_byte & 0x40)

    # TPS4 (DP 1.3+)
    training_byte = reader.read_byte(DPCD_TRAINING_AUX)
    if training_byte:
        a.tps4_support = bool(training_byte & 0x80)

    # MST
    mstm = reader.read_byte(DPCD_MSTM_CAP)
    if mstm:
        a.mst_support = bool(mstm & 0x01)

    # FEC (DP 1.4+)
    fec_byte = reader.read_byte(DPCD_FEC_CAPABILITY)
    if fec_byte:
        a.fec_support = bool(fec_byte & 0x01)

    # DSC
    dsc_byte = reader.read_byte(DPCD_DSC_SUPPORT)
    if dsc_byte:
        a.dsc_support = bool(dsc_byte & 0x01)

    # Bant genisligi
    if a.max_link_rate_gbps and a.max_lane_count:
        a.total_bandwidth_gbps = a.max_link_rate_gbps * a.max_lane_count
        # 128b/132b: ~%3 overhead; 8b/10b: %20 overhead
        eff = (128 / 132) if a.uhbr_support else 0.80
        a.effective_bandwidth_gbps = a.total_bandwidth_gbps * eff

    # Aktif link rate
    current_rate = reader.read_byte(DPCD_LINK_BW_SET)
    if current_rate:
        if a.uhbr_support:
            # UHBR modunda LINK_BW_SET 0x01/0x02/0x04 olur
            for bit, short, gbps, _ in UHBR_RATE_BITS:
                if current_rate == bit:
                    a.current_link_rate_gbps = gbps
                    break
        elif current_rate in LINK_RATE_MAP:
            a.current_link_rate_gbps = LINK_RATE_MAP[current_rate][1]

    current_lanes_byte = reader.read_byte(DPCD_LANE_COUNT_SET)
    if current_lanes_byte:
        a.current_lane_count = current_lanes_byte & 0x1F

    if a.current_link_rate_gbps and a.current_lane_count:
        eff = (128 / 132) if a.uhbr_support else 0.80
        a.current_bandwidth_gbps = a.current_link_rate_gbps * a.current_lane_count * eff

    # Lane durumu
    lane01 = reader.read_byte(DPCD_LANE01_STATUS)
    lane23 = reader.read_byte(DPCD_LANE23_STATUS)
    align  = reader.read_byte(DPCD_LANE_ALIGN)

    if lane01 is not None:
        a.lanes_synced.append({
            "lane": 0, "cr": bool(lane01 & 0x01), "eq": bool(lane01 & 0x02),
            "sym": bool(lane01 & 0x04), "ok": (lane01 & 0x07) == 0x07,
        })
        a.lanes_synced.append({
            "lane": 1, "cr": bool(lane01 & 0x10), "eq": bool(lane01 & 0x20),
            "sym": bool(lane01 & 0x40), "ok": (lane01 & 0x70) == 0x70,
        })

    if lane23 is not None and a.current_lane_count > 2:
        a.lanes_synced.append({
            "lane": 2, "cr": bool(lane23 & 0x01), "eq": bool(lane23 & 0x02),
            "sym": bool(lane23 & 0x04), "ok": (lane23 & 0x07) == 0x07,
        })
        a.lanes_synced.append({
            "lane": 3, "cr": bool(lane23 & 0x10), "eq": bool(lane23 & 0x20),
            "sym": bool(lane23 & 0x40), "ok": (lane23 & 0x70) == 0x70,
        })

    if align is not None:
        a.link_aligned = bool(align & 0x01)

    # EDID
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


def calculate_quality(a: DPAnalysis) -> tuple[int, str, list[str]]:
    score = 100
    issues: list[str] = list(a.issues)

    if a.current_link_rate_gbps and a.max_link_rate_gbps:
        ratio = a.current_link_rate_gbps / a.max_link_rate_gbps
        if ratio < 1.0:
            score -= int((1.0 - ratio) * 40)
            issues.append(
                f"Link hizi dusurulmus: {a.current_link_rate_gbps:.2f} / "
                f"{a.max_link_rate_gbps:.2f} Gbps/lane ({ratio:.0%})"
            )

    if a.current_lane_count and a.max_lane_count and a.current_lane_count < a.max_lane_count:
        score -= 20
        issues.append(f"Lane sayisi dusurulmus: {a.current_lane_count}/{a.max_lane_count}")

    bad_lanes = [l for l in a.lanes_synced if not l["ok"]]
    if bad_lanes:
        score -= len(bad_lanes) * 15
        for l in bad_lanes:
            parts = [
                lbl for lbl, ok in [("CR", l["cr"]), ("EQ", l["eq"]), ("SYM", l["sym"])]
                if not ok
            ]
            issues.append(f"Lane {l['lane']} sorunlu: {', '.join(parts)} basarisiz")

    if a.lanes_synced and not a.link_aligned:
        score -= 15
        issues.append("Lane hizalamasi basarisiz")

    if not a.enhanced_framing and not a.uhbr_support and a.max_link_rate_gbps > 2.7:
        score -= 5
        issues.append("Enhanced framing destegi yok (yuksek hizlarda onemli)")

    score = max(0, min(100, score))

    if   score >= 90: grade = "MUKEMMEL"
    elif score >= 75: grade = "IYI"
    elif score >= 50: grade = "ORTA"
    elif score >= 25: grade = "ZAYIF"
    else:             grade = "KOTU"

    return score, grade, issues


def calculate_max_resolutions(a: DPAnalysis) -> list[dict]:
    bw = a.effective_bandwidth_gbps
    if not bw:
        return []

    common_res = [
        ("8K (7680x4320)",    7680, 4320, 24),
        ("5K (5120x2880)",    5120, 2880, 24),
        ("4K (3840x2160)",    3840, 2160, 24),
        ("WQHD (2560x1440)",  2560, 1440, 24),
        ("FHD (1920x1080)",   1920, 1080, 24),
    ]
    refresh_rates = [60, 120, 144, 165, 240, 360]
    results = []
    for name, w, h, bpp in common_res:
        for hz in refresh_rates:
            required_gbps = (w * h * bpp * hz * 1.06) / 1e9
            supported = required_gbps <= bw
            dsc_possible = (required_gbps <= bw * 3) and a.dsc_support and not supported
            results.append({
                "resolution": name,
                "refresh": hz,
                "required_gbps": required_gbps,
                "supported": supported,
                "dsc_possible": dsc_possible,
            })
    return results


def calculate_features(a: DPAnalysis) -> list[str]:
    features: list[str] = []
    if a.dp_version != "Bilinmiyor":
        features.append(f"DisplayPort {a.dp_version}")
    if a.link_rate_name:
        features.append(f"{a.link_rate_name} ({a.max_link_rate_gbps:.2f} Gbps/lane)")
    if a.max_lane_count:
        features.append(f"{a.max_lane_count}x Lane")
    if a.uhbr_support:
        features.append(f"128b/132b Encoding ({', '.join(a.uhbr_rates)})")
    elif a.enhanced_framing:
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
    if a.max_link_rate_gbps >= 20.0:
        features.append("HDR10 / HDR10+ / Dolby Vision")
        features.append("10-bit / 12-bit / 16-bit Renk Derinligi")
    elif a.max_link_rate_gbps >= 8.1:
        features.append("HDR10 / HDR10+")
        features.append("10-bit / 12-bit Renk Derinligi")
    elif a.max_link_rate_gbps >= 5.4:
        features.append("HDR10 Destegi (sinirli)")
        features.append("10-bit Renk Derinligi")
    elif a.max_link_rate_gbps >= 2.7:
        features.append("8-bit Renk Derinligi")
    if a.dpcd_major >= 1 and a.dpcd_minor >= 3:
        features.append("Adaptive Sync (FreeSync / G-Sync Uyumlu)")
    elif a.dpcd_major >= 1 and a.dpcd_minor >= 2:
        features.append("Adaptive Sync (sinirli)")
    features.append("DP Audio (7.1 Surround)")
    return features


# ============================================================
# Konnektor Kesfetme (Linux)
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
        connections.append({
            "name": name,
            "path": str(connector_dir),
            "status": status,
            "edid_path": str(edid_path) if edid_path.exists() else None,
        })
    return connections


def find_aux_for_connector(connector_name: str) -> Optional[str]:
    """Bir DP konnektor icin /dev/drm_dp_aux* cihazini bul."""
    aux_devices = sorted(glob.glob("/dev/drm_dp_aux*"))

    # Yontem 1: sysfs isim eslesmesi
    for aux in aux_devices:
        sysfs_name = f"/sys/class/drm_dp_aux_dev/{os.path.basename(aux)}/name"
        if os.path.exists(sysfs_name):
            try:
                with open(sysfs_name) as f:
                    name = f.read().strip()
                if connector_name in name:
                    return aux
            except Exception:
                pass

    # Yontem 2: Gecerli DPCD Rev okuyabilen ilk aux'u sec
    for aux in aux_devices:
        try:
            with open(aux, 'rb') as f:
                data = f.read(1)
            if data and data[0] > 0:
                return aux
        except Exception:
            continue

    return None


# ============================================================
# Demo Modu - Donanim olmadan test icin
# ============================================================
def make_demo_analysis() -> DPAnalysis:
    """Gercek donanim olmadan test icin ornek DPAnalysis olustur."""
    a = DPAnalysis()
    a.connector_name = "card0-DP-1 (DEMO)"
    a.aux_device = "/dev/drm_dp_aux0 (simule)"
    a.dpcd_major = 1
    a.dpcd_minor = 4
    a.dp_version = "1.4"
    a.max_link_rate_code = 0x1E
    a.max_link_rate_gbps = 8.10
    a.link_rate_name = "HBR3"
    a.min_dp_version = "1.3+"
    a.max_lane_count = 4
    a.enhanced_framing = True
    a.tps3_support = True
    a.tps4_support = True
    a.fec_support = True
    a.dsc_support = True
    a.mst_support = False
    a.uhbr_support = False
    a.total_bandwidth_gbps = 8.10 * 4
    a.effective_bandwidth_gbps = a.total_bandwidth_gbps * 0.80
    a.current_link_rate_gbps = 8.10
    a.current_lane_count = 4
    a.current_bandwidth_gbps = a.current_link_rate_gbps * 4 * 0.80
    a.lanes_synced = [
        {"lane": i, "cr": True, "eq": True, "sym": True, "ok": True}
        for i in range(4)
    ]
    a.link_aligned = True
    a.edid = EDIDInfo(
        manufacturer="SAM",
        model_name="Odyssey G9",
        serial="H1AK500000",
        max_hpixels=5120,
        max_vpixels=1440,
        max_refresh=240.0,
        year=2022,
        week=14,
        edid_version="1.4",
    )
    a.quality_score, a.quality_grade, a.issues = calculate_quality(a)
    a.max_resolutions = calculate_max_resolutions(a)
    a.supported_features = calculate_features(a)
    return a
