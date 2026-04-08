# DisplayPort Kablo Test

DisplayPort kablosunun versiyonunu, kalitesini, lane durumunu ve desteklediği maksimum çözünürlükleri ölçen araç.

Linux (CLI + GUI) ve Windows (GUI) desteklenir.

---

## Özellikler

- **DP 1.0 – 2.1** tam versiyon tespiti (DPCD Rev okuması)
- **HBR / HBR2 / HBR3** ve **UHBR10 / UHBR13.5 / UHBR20** (DP 2.0) desteği
- **4 lane** bireysel CR / EQ / SYM senkron durumu
- **Kalite puanı** (0-100) — düşürülmüş link hızı, lane sorunları, hizalama hataları
- **Bant genişliği hesabı** — 8b/10b ve 128b/132b encoding overhead'i dahil
- **Maksimum çözünürlük tablosu** — 8K/5K/4K/WQHD/FHD × 60-360 Hz
- **DSC (Display Stream Compression)** desteği tespiti
- **MST / FEC / TPS3 / TPS4** özellik bayrakları
- **EDID** monitor bilgisi (üretici, model, seri, panel boyutu)
- **Demo modu** — donanım olmadan test için

---

## Dosya Yapısı

```
dp_core.py                # Ortak analiz motoru (DPCD, EDID, hesaplamalar)
dp_cable_test.py          # Linux CLI
dp_cable_test_gui.py      # Linux GUI (tkinter)
cable_test_windows_gui.py # Windows GUI (tkinter + winreg)
```

---

## Kullanım

### Linux CLI

```bash
sudo python3 dp_cable_test.py

# Donanım olmadan demo
python3 dp_cable_test.py --demo

# Yardım
python3 dp_cable_test.py --help
```

### Linux GUI

```bash
sudo python3 dp_cable_test_gui.py

# Demo modu
python3 dp_cable_test_gui.py --demo
```

### Windows GUI

```bat
python cable_test_windows_gui.py
```

> Windows'ta yönetici yetkisi gerekmez — EDID Windows Registry'den okunur.  
> Linux'ta `sudo` gereklidir çünkü `/dev/drm_dp_aux*` root korumalıdır.

---

## Gereksinimler

- **Python 3.11+**
- Yalnızca standart kütüphane (tkinter dahil) — ek paket gerekmez
- Linux: DRM AUX aygıtları (`/dev/drm_dp_aux*`) ve DRM sysfs (`/sys/class/drm/`)
- Windows: `winreg` (dahili), DisplayPort veya HDMI bağlı monitör

---

## Linux: Nasıl Çalışır

1. `/sys/class/drm/` altındaki DP konnektörleri taranır
2. Her bağlı konnektör için `/dev/drm_dp_aux*` eşlemesi yapılır
3. DPCD registerları doğrudan okunur:
   - `0x0000` DPCD Rev → DP versiyonu
   - `0x0001` Max Link Rate → HBR/HBR2/HBR3
   - `0x0002` Max Lane Count + bayraklar
   - `0x0202–0x0204` Lane senkron durumu ve hizalama
   - `0x2201` UHBR capability (DP 2.0+)
4. EDID `/sys/class/drm/<connector>/edid` dosyasından ayrıştırılır

---

## Kalite Puanı Hesabı

| Durum | Ceza |
|-------|------|
| Link hızı düşürülmüş | % fark × 40 puan |
| Lane sayısı düşürülmüş | −20 puan |
| Her sorunlu lane (CR/EQ/SYM) | −15 puan |
| Lane hizalama başarısız | −15 puan |
| Enhanced framing yok (>HBR) | −5 puan |

| Puan | Derece |
|------|--------|
| 90-100 | MÜKEMMEL |
| 75-89  | İYİ |
| 50-74  | ORTA |
| 25-49  | ZAYIF |
| 0-24   | KÖTÜ |

---

## Lisans

MIT
