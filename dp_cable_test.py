#!/usr/bin/env python3
"""
DisplayPort Kablo Test Programi (CLI)
======================================
Takili DisplayPort kablonun versiyonunu, kalitesini, hizini
ve destekledigi maksimum teknolojileri olcer.

Kullanim:
  sudo python3 dp_cable_test.py           # Gercek donanim
  python3 dp_cable_test.py --demo         # Demo modu (donanim gerekmez)
  python3 dp_cable_test.py --help
"""

import os
import sys
import argparse

from dp_core import (
    DPAnalysis,
    find_dp_connections,
    find_aux_for_connector,
    analyze_dp,
    make_demo_analysis,
)


# ============================================================
# Terminal Renk Kodlari
# ============================================================
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"


def _color_enabled() -> bool:
    return sys.stdout.isatty()


def c(code: str, text: str) -> str:
    return f"{code}{text}{C.RESET}" if _color_enabled() else text


# ============================================================
# Cikti Yardimcilari
# ============================================================
def print_header() -> None:
    w = 72
    print()
    print(c(C.CYAN + C.BOLD, "=" * w))
    print(c(C.CYAN + C.BOLD, "   DISPLAYPORT KABLO TEST PROGRAMI"))
    print(c(C.CYAN + C.BOLD, "=" * w))
    print()


def print_section(title: str) -> None:
    print()
    print(c(C.BLUE + C.BOLD, f"--- {title} " + "-" * max(1, 55 - len(title))))


def kv(key: str, value: str, indent: int = 2) -> None:
    pad = " " * indent
    print(f"{pad}{c(C.DIM, key + ':')} {c(C.WHITE + C.BOLD, value)}")


def yn(flag: bool) -> str:
    return c(C.GREEN + C.BOLD, "Evet") if flag else c(C.DIM, "Hayir")


# ============================================================
# Analiz Raporu
# ============================================================
def print_analysis(a: DPAnalysis) -> None:
    # Baglanti bilgisi
    print_section("BAGLANTI BILGISI")
    kv("Connector", a.connector_name)
    kv("AUX Device", a.aux_device)
    if a.edid:
        kv("Monitor", f"{a.edid.manufacturer} {a.edid.model_name}".strip())
        if a.edid.serial:
            kv("Seri No", a.edid.serial)
        kv("Uretim", f"Hafta {a.edid.week}, {a.edid.year}")
        kv("EDID Versiyon", a.edid.edid_version)
        if a.edid.max_hpixels:
            kv("Panel Cozunurlugu", f"{a.edid.max_hpixels}x{a.edid.max_vpixels}")
        if a.edid.max_refresh:
            kv("Maks Yenileme", f"{a.edid.max_refresh:.0f} Hz")

    # DP versiyon & hiz
    print_section("DISPLAYPORT VERSIYON & HIZ")
    kv("DPCD Revizyon", f"{a.dpcd_major}.{a.dpcd_minor}")
    kv("DP Versiyon", a.dp_version)
    kv("Max Link Rate", f"{a.max_link_rate_gbps:.2f} Gbps/lane ({a.link_rate_name})")
    if a.uhbr_support and a.uhbr_rates:
        kv("UHBR Modlari", ", ".join(a.uhbr_rates))
    kv("Max Lane Sayisi", str(a.max_lane_count))
    kv("Toplam Bant Genisligi", f"{a.total_bandwidth_gbps:.2f} Gbps (ham)")
    enc = "128b/132b" if a.uhbr_support else "8b/10b"
    kv("Efektif Bant Genisligi", f"{a.effective_bandwidth_gbps:.2f} Gbps ({enc} sonrasi)")

    # Ozellik bayraklari
    print_section("OZELLIKLER")
    kv("Enhanced Framing", yn(a.enhanced_framing))
    kv("TPS3", yn(a.tps3_support))
    kv("TPS4", yn(a.tps4_support))
    kv("MST (Daisy-Chain)", yn(a.mst_support))
    kv("FEC", yn(a.fec_support))
    kv("DSC", yn(a.dsc_support))
    kv("UHBR (128b/132b)", yn(a.uhbr_support))

    # Aktif link durumu
    print_section("AKTIF LINK DURUMU")
    if a.current_link_rate_gbps:
        kv("Aktif Link Rate", f"{a.current_link_rate_gbps:.2f} Gbps/lane")
    else:
        kv("Aktif Link Rate", "Okunamiyor")
    kv("Aktif Lane Sayisi", str(a.current_lane_count) if a.current_lane_count else "Okunamiyor")
    kv("Aktif Bant Genisligi", f"{a.current_bandwidth_gbps:.2f} Gbps" if a.current_bandwidth_gbps else "N/A")

    if a.lanes_synced:
        print()
        print(c(C.DIM, "  Lane   CR    EQ    SYM   Durum"))
        print(c(C.DIM, "  " + "-" * 37))
        for l in a.lanes_synced:
            cr  = c(C.GREEN, " OK ") if l["cr"]  else c(C.RED, "FAIL")
            eq  = c(C.GREEN, " OK ") if l["eq"]  else c(C.RED, "FAIL")
            sym = c(C.GREEN, " OK ") if l["sym"] else c(C.RED, "FAIL")
            ok  = c(C.GREEN + C.BOLD, "  SENKRON") if l["ok"] else c(C.RED + C.BOLD, "  SORUNLU")
            print(f"   {l['lane']}    {cr}  {eq}  {sym} {ok}")
        aligned_str = c(C.GREEN + C.BOLD, "EVET") if a.link_aligned else c(C.RED + C.BOLD, "HAYIR")
        kv("Lane Hizalama", aligned_str)

    # Kalite
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

    # Desteklenen teknolojiler
    print_section("DESTEKLENEN TEKNOLOJILER")
    for feat in a.supported_features:
        print(f"  {c(C.GREEN, '+')} {feat}")

    # Cozunurluk tablosu
    print_section("DESTEKLENEN COZUNURLUKLER")
    print(f"  {'Cozunurluk':<22} {'Hz':>5}  {'Gerekli':>10}  {'Durum':>12}")
    print(f"  {'-' * 56}")
    seen: set[str] = set()
    for r in a.max_resolutions:
        key = f"{r['resolution']}@{r['refresh']}"
        if key in seen:
            continue
        seen.add(key)
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
# Ana Program
# ============================================================
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dp_cable_test.py",
        description="DisplayPort kablo versiyon ve kalite testi (Linux)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ornekler:\n"
            "  sudo python3 dp_cable_test.py\n"
            "  python3 dp_cable_test.py --demo\n"
        ),
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Gercek donanim olmadan demo modu ile calistir",
    )
    args = parser.parse_args()

    print_header()

    if args.demo:
        print(c(C.YELLOW + C.BOLD, "  [DEMO MODU] Gercek donanim kullanilmiyor.\n"))
        print_analysis(make_demo_analysis())
        return

    if os.geteuid() != 0:
        print(c(C.RED + C.BOLD, "  HATA: Bu program root yetkisi gerektirir!"))
        print(f"  Kullanim: {c(C.CYAN, 'sudo python3 dp_cable_test.py')}")
        print(f"  Demo modu: {c(C.CYAN, 'python3 dp_cable_test.py --demo')}")
        print()
        sys.exit(1)

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
