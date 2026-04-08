#!/usr/bin/env python3
"""
DisplayPort Kablo Test Programi - Linux GUI
============================================
Takili DisplayPort kablonun versiyonunu, kalitesini, hizini
ve destekledigi maksimum teknolojileri olcer.

Kullanim:
  sudo python3 dp_cable_test_gui.py
  python3 dp_cable_test_gui.py --demo
"""

import os
import sys
import argparse
import subprocess
import tkinter as tk
from tkinter import ttk

from dp_core import (
    DPAnalysis,
    EDIDInfo,
    find_dp_connections,
    find_aux_for_connector,
    analyze_dp,
    make_demo_analysis,
)

# ============================================================
# Renk Paleti
# ============================================================
BG_DARK      = "#1a1a2e"
BG_CARD      = "#16213e"
BG_CARD2     = "#0f3460"
FG_TEXT      = "#e0e0e0"
FG_DIM       = "#888899"
FG_TITLE     = "#ffffff"
ACCENT_BLUE  = "#00adb5"
ACCENT_GREEN = "#00e676"
ACCENT_RED   = "#ff5252"
ACCENT_YELLOW= "#ffd740"
ACCENT_ORANGE= "#ff9100"
ACCENT_CYAN  = "#18ffff"
BAR_BG       = "#2a2a4a"


# ============================================================
# Widget: Dairesel Kalite Gostergesi
# ============================================================
class ScoreGauge(tk.Canvas):
    def __init__(self, parent: tk.Widget, size: int = 200, **kwargs) -> None:
        super().__init__(parent, width=size, height=size,
                         bg=BG_CARD, highlightthickness=0, **kwargs)
        self.size = size
        self.score = 0
        self.grade = ""
        self._anim_score = 0

    def set_score(self, score: int, grade: str) -> None:
        self.score = score
        self.grade = grade
        self._anim_score = 0
        self._animate()

    def _animate(self) -> None:
        if self._anim_score < self.score:
            self._anim_score = min(self._anim_score + 2, self.score)
            self._draw(self._anim_score)
            self.after(16, self._animate)
        else:
            self._draw(self.score)

    def _draw(self, current_score: int) -> None:
        self.delete("all")
        cx, cy = self.size / 2, self.size / 2
        r = self.size / 2 - 15
        lw = 12

        self.create_arc(cx - r, cy - r, cx + r, cy + r,
                        start=225, extent=-270, style="arc",
                        outline=BAR_BG, width=lw)

        if   current_score >= 75: color = ACCENT_GREEN
        elif current_score >= 50: color = ACCENT_YELLOW
        elif current_score >= 25: color = ACCENT_ORANGE
        else:                     color = ACCENT_RED

        extent = -270 * (current_score / 100)
        self.create_arc(cx - r, cy - r, cx + r, cy + r,
                        start=225, extent=extent, style="arc",
                        outline=color, width=lw)

        self.create_text(cx, cy - 10, text=str(current_score),
                         font=("Segoe UI", 36, "bold"), fill=color)
        self.create_text(cx, cy + 25, text="/100",
                         font=("Segoe UI", 12), fill=FG_DIM)
        self.create_text(cx, cy + 48, text=self.grade,
                         font=("Segoe UI", 14, "bold"), fill=color)


# ============================================================
# Widget: Lane Durum Gostergesi
# ============================================================
class LaneIndicator(tk.Canvas):
    def __init__(self, parent: tk.Widget, lane_num: int, **kwargs) -> None:
        super().__init__(parent, width=80, height=120,
                         bg=BG_CARD, highlightthickness=0, **kwargs)
        self.lane_num = lane_num

    def set_status(self, cr: bool, eq: bool, sym: bool, ok: bool) -> None:
        self.delete("all")
        border = ACCENT_GREEN if ok else ACCENT_RED
        self.create_rectangle(10, 10, 70, 110, outline=border, width=2, fill=BG_CARD2)
        self.create_text(40, 25, text=f"L{self.lane_num}",
                         font=("Segoe UI", 12, "bold"), fill=FG_TITLE)
        y = 45
        for label, val in [("CR", cr), ("EQ", eq), ("SYM", sym)]:
            dot_color = ACCENT_GREEN if val else ACCENT_RED
            self.create_oval(18, y, 28, y + 10, fill=dot_color, outline="")
            self.create_text(50, y + 5, text=label,
                             font=("Segoe UI", 9), fill=FG_TEXT)
            y += 20


# ============================================================
# Widget: Bant Genisligi Cubugu
# ============================================================
class BandwidthBar(tk.Canvas):
    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        super().__init__(parent, width=400, height=50,
                         bg=BG_CARD, highlightthickness=0, **kwargs)

    def set_values(self, current: float, maximum: float) -> None:
        self.delete("all")
        w, h = 400, 50
        bar_y, bar_h = 25, 16
        self.create_rectangle(10, bar_y, w - 10, bar_y + bar_h, fill=BAR_BG, outline="")
        if maximum > 0:
            ratio = min(current / maximum, 1.0)
            fill_w = (w - 20) * ratio
            color = ACCENT_GREEN if ratio >= 0.9 else (ACCENT_YELLOW if ratio >= 0.5 else ACCENT_RED)
            self.create_rectangle(10, bar_y, 10 + fill_w, bar_y + bar_h, fill=color, outline="")
        self.create_text(10, 10, anchor="w",
                         text=f"Aktif: {current:.1f} Gbps",
                         font=("Segoe UI", 10, "bold"), fill=ACCENT_CYAN)
        self.create_text(w - 10, 10, anchor="e",
                         text=f"Max: {maximum:.1f} Gbps",
                         font=("Segoe UI", 10), fill=FG_DIM)


# ============================================================
# Ana GUI Uygulamasi
# ============================================================
class DPTestApp:
    def __init__(self, root: tk.Tk, demo: bool = False) -> None:
        self.root = root
        self.demo = demo
        self.root.title("DisplayPort Kablo Test")
        self.root.configure(bg=BG_DARK)
        self.root.minsize(900, 700)

        # Scrollable ana cerceve
        self.canvas = tk.Canvas(root, bg=BG_DARK, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(root, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg=BG_DARK)
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Mouse wheel
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        self._build_ui()
        self.root.after(100, self.run_test)

    def _on_canvas_resize(self, event: tk.Event) -> None:
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _build_ui(self) -> None:
        f = self.scroll_frame

        hdr = tk.Frame(f, bg=BG_CARD2, pady=15)
        hdr.pack(fill="x", padx=10, pady=(10, 5))

        title_text = "DISPLAYPORT KABLO TEST"
        if self.demo:
            title_text += "  [DEMO]"
        tk.Label(hdr, text=title_text,
                 font=("Segoe UI", 22, "bold"), fg=ACCENT_CYAN, bg=BG_CARD2).pack()
        tk.Label(hdr, text="Kablo versiyonu, kalitesi, hizi ve destekledigi teknolojiler",
                 font=("Segoe UI", 10), fg=FG_DIM, bg=BG_CARD2).pack()

        self.content_frame = tk.Frame(f, bg=BG_DARK)
        self.content_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.status_var = tk.StringVar(value="Taranıyor...")
        tk.Label(f, textvariable=self.status_var,
                 font=("Segoe UI", 9), fg=FG_DIM, bg=BG_DARK, anchor="w").pack(
            fill="x", padx=15, pady=(0, 10))

    def run_test(self) -> None:
        for w in self.content_frame.winfo_children():
            w.destroy()

        if self.demo:
            self._show_analysis(make_demo_analysis())
            self.status_var.set("Demo modu - gercek donanim kullanilmiyor")
            self._add_refresh_button()
            return

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
        self._add_refresh_button()

    def _add_refresh_button(self) -> None:
        btn_frame = tk.Frame(self.content_frame, bg=BG_DARK)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Yeniden Tara", command=self.run_test,
                  font=("Segoe UI", 11, "bold"), fg=BG_DARK, bg=ACCENT_CYAN,
                  activebackground=ACCENT_BLUE, relief="flat", padx=20, pady=8,
                  cursor="hand2").pack()

    def _show_error(self, msg: str) -> None:
        frm = tk.Frame(self.content_frame, bg=BG_CARD, padx=30, pady=30)
        frm.pack(fill="x", pady=20)
        tk.Label(frm, text="HATA", font=("Segoe UI", 16, "bold"),
                 fg=ACCENT_RED, bg=BG_CARD).pack()
        tk.Label(frm, text=msg, font=("Segoe UI", 12),
                 fg=FG_TEXT, bg=BG_CARD).pack(pady=10)
        self.status_var.set("Hata olustu")

    def _card(self, parent: tk.Widget, title: str) -> tk.Frame:
        card = tk.Frame(parent, bg=BG_CARD, padx=15, pady=12)
        card.pack(fill="x", pady=4)
        tk.Label(card, text=title, font=("Segoe UI", 13, "bold"),
                 fg=ACCENT_CYAN, bg=BG_CARD, anchor="w").pack(fill="x")
        tk.Frame(card, bg=ACCENT_BLUE, height=1).pack(fill="x", pady=(4, 8))
        body = tk.Frame(card, bg=BG_CARD)
        body.pack(fill="x")
        return body

    def _kv_row(self, parent: tk.Widget, key: str, value: str, row: int,
                val_color: str = FG_TEXT) -> None:
        tk.Label(parent, text=key, font=("Segoe UI", 10),
                 fg=FG_DIM, bg=BG_CARD, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(0, 15), pady=1)
        tk.Label(parent, text=value, font=("Segoe UI", 10, "bold"),
                 fg=val_color, bg=BG_CARD, anchor="w").grid(
            row=row, column=1, sticky="w", pady=1)

    def _show_analysis(self, a: DPAnalysis) -> None:
        parent = self.content_frame

        # --- Ust satir: Kalite + Baglanti Bilgisi ---
        top = tk.Frame(parent, bg=BG_DARK)
        top.pack(fill="x", pady=4)
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=2)

        # Kalite gostergesi
        score_card = tk.Frame(top, bg=BG_CARD, padx=15, pady=12)
        score_card.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        tk.Label(score_card, text="KABLO KALITESI",
                 font=("Segoe UI", 13, "bold"), fg=ACCENT_CYAN, bg=BG_CARD).pack()
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
                     font=("Segoe UI", 10), fg=ACCENT_GREEN, bg=BG_CARD).pack()

        # Baglanti bilgisi
        conn_body = tk.Frame(top, bg=BG_CARD, padx=15, pady=12)
        conn_body.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        tk.Label(conn_body, text="BAGLANTI BILGISI",
                 font=("Segoe UI", 13, "bold"), fg=ACCENT_CYAN, bg=BG_CARD).pack(anchor="w")
        tk.Frame(conn_body, bg=ACCENT_BLUE, height=1).pack(fill="x", pady=(4, 8))
        info_grid = tk.Frame(conn_body, bg=BG_CARD)
        info_grid.pack(fill="x")

        row = 0
        self._kv_row(info_grid, "Connector", a.connector_name, row); row += 1
        self._kv_row(info_grid, "AUX Device", a.aux_device, row); row += 1
        if a.edid:
            self._kv_row(info_grid, "Monitor",
                         f"{a.edid.manufacturer} {a.edid.model_name}".strip(),
                         row, ACCENT_CYAN); row += 1
            if a.edid.serial:
                self._kv_row(info_grid, "Seri No", a.edid.serial, row); row += 1
            self._kv_row(info_grid, "Uretim",
                         f"Hafta {a.edid.week}, {a.edid.year}", row); row += 1
            self._kv_row(info_grid, "EDID", a.edid.edid_version, row); row += 1
            if a.edid.max_hpixels:
                self._kv_row(info_grid, "Panel",
                             f"{a.edid.max_hpixels}x{a.edid.max_vpixels}", row); row += 1
        self._kv_row(info_grid, "DP Versiyon", a.dp_version, row, ACCENT_GREEN); row += 1
        self._kv_row(info_grid, "DPCD Rev", f"{a.dpcd_major}.{a.dpcd_minor}", row); row += 1
        rate_label = f"{a.max_link_rate_gbps:.2f} Gbps/lane ({a.link_rate_name})"
        self._kv_row(info_grid, "Link Rate", rate_label, row, ACCENT_CYAN); row += 1
        if a.uhbr_support and a.uhbr_rates:
            self._kv_row(info_grid, "UHBR", ", ".join(a.uhbr_rates), row, ACCENT_CYAN); row += 1
        self._kv_row(info_grid, "Lane Sayisi", str(a.max_lane_count), row); row += 1

        # --- Bant Genisligi ---
        bw_body = self._card(parent, "BANT GENISLIGI")
        bw_bar = BandwidthBar(bw_body)
        bw_bar.pack(fill="x", pady=5)
        bw_bar.set_values(a.current_bandwidth_gbps, a.effective_bandwidth_gbps)
        bw_grid = tk.Frame(bw_body, bg=BG_CARD)
        bw_grid.pack(fill="x")
        enc = "128b/132b" if a.uhbr_support else "8b/10b"
        self._kv_row(bw_grid, "Toplam (ham)", f"{a.total_bandwidth_gbps:.2f} Gbps", 0)
        self._kv_row(bw_grid, f"Efektif ({enc})",
                     f"{a.effective_bandwidth_gbps:.2f} Gbps", 1, ACCENT_GREEN)
        self._kv_row(bw_grid, "Aktif Link Rate",
                     f"{a.current_link_rate_gbps:.2f} Gbps/lane"
                     if a.current_link_rate_gbps else "N/A", 2)
        self._kv_row(bw_grid, "Aktif Lane",
                     str(a.current_lane_count) if a.current_lane_count else "N/A", 3)

        # --- Lane Durumu ---
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
                     font=("Segoe UI", 11, "bold"), fg=align_color, bg=BG_CARD).pack(pady=(5, 0))

        # --- Ozellikler ---
        feat_body = self._card(parent, "DESTEKLENEN TEKNOLOJILER")
        cols = 2
        for i, feat in enumerate(a.supported_features):
            r_idx, col_idx = divmod(i, cols)
            tk.Label(feat_body, text=f"  +  {feat}",
                     font=("Segoe UI", 10), fg=ACCENT_GREEN, bg=BG_CARD, anchor="w").grid(
                row=r_idx, column=col_idx, sticky="w", padx=(0, 30), pady=1)

        # --- Cozunurluk Tablosu ---
        res_body = self._card(parent, "COZUNURLUK DESTEGI")
        hdr_frame = tk.Frame(res_body, bg=BG_CARD2)
        hdr_frame.pack(fill="x")
        for text, w in [("Cozunurluk", 120), ("Hz", 50), ("Gerekli", 90), ("Durum", 100)]:
            tk.Label(hdr_frame, text=text, font=("Segoe UI", 9, "bold"),
                     fg=FG_DIM, bg=BG_CARD2, width=w // 8, anchor="w").pack(side="left", padx=5)

        for r in a.max_resolutions:
            row_frame = tk.Frame(res_body, bg=BG_CARD)
            row_frame.pack(fill="x")
            tk.Label(row_frame, text=f"{r['resolution']}",
                     font=("Segoe UI", 9), fg=FG_TEXT, bg=BG_CARD,
                     width=15, anchor="w").pack(side="left", padx=5)
            tk.Label(row_frame, text=str(r['refresh']),
                     font=("Segoe UI", 9), fg=FG_TEXT, bg=BG_CARD,
                     width=6, anchor="w").pack(side="left", padx=5)
            tk.Label(row_frame, text=f"{r['required_gbps']:.1f} Gbps",
                     font=("Segoe UI", 9), fg=FG_DIM, bg=BG_CARD,
                     width=11, anchor="w").pack(side="left", padx=5)
            if r["supported"]:
                st_text, st_color = "DESTEKLI", ACCENT_GREEN
            elif r["dsc_possible"]:
                st_text, st_color = "DSC GEREK", ACCENT_YELLOW
            else:
                st_text, st_color = "YETERSIZ", ACCENT_RED
            tk.Label(row_frame, text=st_text,
                     font=("Segoe UI", 9, "bold"), fg=st_color, bg=BG_CARD,
                     width=12, anchor="w").pack(side="left", padx=5)


# ============================================================
# Main
# ============================================================
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dp_cable_test_gui.py",
        description="DisplayPort kablo test - Linux GUI",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Gercek donanim olmadan demo modu",
    )
    args = parser.parse_args()

    if not args.demo and os.geteuid() != 0:
        try:
            subprocess.Popen(["pkexec", sys.executable] + sys.argv)
            sys.exit(0)
        except Exception:
            pass

    root = tk.Tk()
    root.geometry("920x750")

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Vertical.TScrollbar",
                    background=BAR_BG, troughcolor=BG_DARK, arrowcolor=FG_DIM)

    DPTestApp(root, demo=args.demo)
    root.mainloop()


if __name__ == "__main__":
    main()
