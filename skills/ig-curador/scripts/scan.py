#!/usr/bin/env python3
"""
scan.py - inventario técnico de una carpeta de fotos y videos.

Qué hace:   recorre la carpeta, mide cada archivo en tu máquina y escribe
            `inventario.json` en la carpeta de trabajo, más una vista previa
            ligera de cada foto (vistas/) y fotogramas de cada video (fotogramas/)
            para que Claude los pueda mirar sin abrir originales de 20 MB.

Qué mide:   nitidez (del sujeto, no del fondo), exposición, contraste, ruido,
            color, resolución, proporción, caras aproximadas, punto focal,
            fecha de captura, ráfagas y casi-duplicados. En videos además:
            duración, fps, audio, movimiento, cortes de escena, el arranque
            (los primeros 2 s, donde se gana o se pierde el reel) y el mejor
            fotograma para portada.

Qué NO es:  un juicio estético. Una foto técnicamente perfecta puede ser
            aburrida y una movida puede ser la mejor del día. Estas métricas
            sirven para descartar lo roto y para desempatar. La elección la
            hace la evaluación visual de la skill (rubrica.json).

Uso
  python3 scan.py ./fotos --out ./rrss-trabajo/lanzamiento
  python3 scan.py ./fotos --out ./trabajo -r            # incluye subcarpetas
  python3 scan.py ./fotos --out ./trabajo --max-frames 16
"""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (IMAGE_EXT, VIDEO_EXT, clamp, orientation, ratio_label,  # noqa: E402
                    save_json, hamming_hex, hist_intersection, bar)

try:
    from pillow_heif import register_heif_opener  # type: ignore
    register_heif_opener()
    HEIF = True
except Exception:
    HEIF = False

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
try:
    import cv2  # type: ignore
    _CASCADE = None
    CV2 = True
except Exception:
    CV2 = False

ANALYSIS_SIDE = 768
PREVIEW_SIDE = 1280


# ============================================================ métricas

def _laplacian(g):
    return (g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
            - 4 * g[1:-1, 1:-1])


def sharpness(g):
    """Varianza del laplaciano en escala 0-255.
    Devuelve (sujeto, global). 'sujeto' es el percentil 85 de una rejilla 4x4:
    así un retrato con fondo desenfocado a propósito no se castiga."""
    lap = _laplacian(g * 255.0)
    glob = float(lap.var())
    h, w = lap.shape
    tiles = []
    for i in range(4):
        for j in range(4):
            t = lap[i * h // 4:(i + 1) * h // 4, j * w // 4:(j + 1) * w // 4]
            if t.size:
                tiles.append(float(t.var()))
    subj = float(np.percentile(tiles, 85)) if tiles else glob
    return subj, glob


def sharp_score(v):
    # v~10 borrosa sin remedio, v~100 aceptable, v>=1000 muy nítida
    return clamp((math.log10(max(v, 1.0)) - 1.0) / 2.0 * 100)


def exposure(g):
    mean = float(g.mean())
    hi = float((g > 0.98).mean())
    lo = float((g < 0.02).mean())
    score = 100 - abs(mean - 0.48) * 130 - hi * 220 - lo * 140
    return mean, hi, lo, clamp(score)


def noise_sigma(g):
    """Estimador de Immerkær (1996). Sigma en escala 0-255."""
    I = g * 255.0
    if I.shape[0] < 3 or I.shape[1] < 3:
        return 0.0
    conv = (I[:-2, :-2] - 2 * I[:-2, 1:-1] + I[:-2, 2:]
            - 2 * I[1:-1, :-2] + 4 * I[1:-1, 1:-1] - 2 * I[1:-1, 2:]
            + I[2:, :-2] - 2 * I[2:, 1:-1] + I[2:, 2:])
    H, W = I.shape
    return float(math.sqrt(math.pi / 2) * np.abs(conv).sum() / (6 * (W - 2) * (H - 2)))


def colorfulness(rgb):
    """Hasler & Süsstrunk (2003)."""
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    rg = R - G
    yb = 0.5 * (R + G) - B
    return float(math.sqrt(rg.std() ** 2 + yb.std() ** 2)
                 + 0.3 * math.sqrt(rg.mean() ** 2 + yb.mean() ** 2))


def _box3(a):
    p = np.pad(a, 1, mode="edge")
    return sum(p[i:i + a.shape[0], j:j + a.shape[1]] for i in range(3) for j in range(3)) / 9.0


def saliency_focal(pil_gray):
    """Residuo espectral (Hou & Zhang 2007). Devuelve el punto focal (x, y)
    normalizado: el centro de masa de lo que más llama la atención."""
    small = np.asarray(pil_gray.resize((64, 64), Image.BILINEAR), dtype=np.float64)
    F = np.fft.fft2(small)
    A = np.log(np.abs(F) + 1e-8)
    P = np.angle(F)
    R = A - _box3(A)
    S = np.abs(np.fft.ifft2(np.exp(R + 1j * P))) ** 2
    S = Image.fromarray((S / (S.max() + 1e-12) * 255).astype(np.uint8))
    S = np.asarray(S.filter(ImageFilter.GaussianBlur(3)), dtype=np.float64)
    thr = np.percentile(S, 95)
    ys, xs = np.nonzero(S >= thr)
    wts = S[ys, xs]
    if wts.sum() == 0:
        return [0.5, 0.5]
    return [round(float((xs * wts).sum() / wts.sum() / 63), 3),
            round(float((ys * wts).sum() / wts.sum() / 63), 3)]


YUNET = Path(__file__).resolve().parent.parent / "config" / "face_detection_yunet_2023mar.onnx"


def _haar_path():
    name = "haarcascade_frontalface_default.xml"
    candidates = []
    try:
        candidates.append(Path(cv2.data.haarcascades) / name)
    except Exception:
        pass
    candidates += [Path(p) / name for p in ("/usr/share/opencv4/haarcascades",
                                            "/usr/local/share/opencv4/haarcascades",
                                            "/opt/homebrew/share/opencv4/haarcascades")]
    return next((str(p) for p in candidates if p.exists()), None)


def face_backend():
    """YuNet (incluido en config/, mucho mejor) o Haar como respaldo."""
    if not CV2:
        return None
    if hasattr(cv2, "FaceDetectorYN") and YUNET.exists():
        return "yunet"
    if hasattr(cv2, "CascadeClassifier") and _haar_path():
        return "haar"
    return None


def detect_faces(rgb_u8):
    """Caras aproximadas, normalizadas [x, y, w, h], de mayor a menor.
    Devuelve None si no hay detector (no es lo mismo que 0 caras)."""
    global _CASCADE
    backend = face_backend()
    if backend is None:
        return None
    h, w = rgb_u8.shape[:2]
    try:
        if backend == "yunet":
            bgr = np.ascontiguousarray(rgb_u8[:, :, ::-1])
            det = cv2.FaceDetectorYN.create(str(YUNET), "", (w, h), 0.75)
            found = det.detect(bgr)[1]
            boxes = [] if found is None else [(f[0], f[1], f[2], f[3]) for f in found]
        else:
            if _CASCADE is None:
                _CASCADE = cv2.CascadeClassifier(_haar_path())
            gray = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2GRAY)
            m = max(24, int(min(h, w) * 0.05))
            boxes = _CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(m, m))
        out = []
        for (x, y, fw, fh) in boxes:
            x, y = max(0.0, float(x)), max(0.0, float(y))
            out.append([round(x / w, 3), round(y / h, 3),
                        round(min(float(fw), w - x) / w, 3), round(min(float(fh), h - y) / h, 3)])
        return sorted(out, key=lambda f: -f[2] * f[3])
    except Exception:
        return None


def dhash(pil_gray):
    a = np.asarray(pil_gray.resize((9, 8), Image.BILINEAR), dtype=np.int16)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    return "%016x" % int("".join("1" if b else "0" for b in bits), 2)


def color_hist(pil_rgb):
    a = np.asarray(pil_rgb.resize((64, 64), Image.BILINEAR)) // 64
    idx = a[..., 0] * 16 + a[..., 1] * 4 + a[..., 2]
    h = np.bincount(idx.flatten(), minlength=64).astype(np.float64)
    h /= h.sum()
    return [round(float(x), 4) for x in h]


def analyze_pil(img):
    """Todas las métricas sobre una imagen PIL ya orientada."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    s = ANALYSIS_SIDE / max(w, h)
    small = rgb.resize((max(1, int(w * s)), max(1, int(h * s))), Image.BILINEAR) if s < 1 else rgb
    gray = small.convert("L")
    g = np.asarray(gray, dtype=np.float32) / 255.0
    arr = np.asarray(small, dtype=np.float32)

    subj, glob = sharpness(g)
    mean, hi, lo, expo = exposure(g)
    sig = noise_sigma(g)
    faces = detect_faces(np.asarray(small, dtype=np.uint8))
    focal = saliency_focal(gray)
    if faces:
        # la cara más grande manda sobre la saliencia
        fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
        focal = [round(fx + fw / 2, 3), round(fy + fh / 2, 3)]

    return {
        "nitidez": round(sharp_score(subj), 1),
        "nitidez_global": round(sharp_score(glob), 1),
        "exposicion": round(expo, 1),
        "luminancia": round(mean, 3),
        "altas_quemadas": round(hi, 4),
        "sombras_empastadas": round(lo, 4),
        "contraste": round(clamp(float(g.std()) / 0.25 * 100), 1),
        "ruido": round(clamp(100 - (sig - 2.0) * 9), 1),
        "color": round(clamp(colorfulness(arr)), 1),
        "caras": faces,
        "foco": focal,
        "dhash": dhash(gray),
        "hist": color_hist(small),
    }


def technical(m, min_side):
    resol = clamp(min_side / 1080 * 100)
    score = 0.45 * m["nitidez"] + 0.25 * m["exposicion"] + 0.15 * m["ruido"] + 0.15 * resol
    warn = []
    if m["nitidez"] < 35:
        warn.append("desenfocada o movida")
    if m["altas_quemadas"] > 0.08:
        warn.append("altas luces quemadas")
    if m["luminancia"] < 0.2 and m["sombras_empastadas"] > 0.15:
        warn.append("subexpuesta")
    if m["ruido"] < 40:
        warn.append("ruido alto")
    if min_side < 1080:
        warn.append(f"resolución baja ({min_side}px de lado corto)")
    return round(score, 1), warn


# ============================================================== fotos

def exif_date(img):
    try:
        ex = img.getexif()
        v = ex.get_ifd(0x8769).get(36867) or ex.get(306)
        if v:
            return datetime.strptime(str(v).strip()[:19], "%Y:%m:%d %H:%M:%S").isoformat()
    except Exception:
        pass
    return None


def scan_image(job):
    path, aid, out = job
    t0 = time.time()
    try:
        with Image.open(path) as im:
            date = exif_date(im)
            img = ImageOps.exif_transpose(im)
            img.load()
    except Exception as e:
        return {"id": aid, "archivo": str(path), "tipo": "foto", "error": f"no se pudo abrir: {e}"}

    w, h = img.size
    m = analyze_pil(img)
    tec, warn = technical(m, min(w, h))

    prev = img.convert("RGB")
    prev.thumbnail((PREVIEW_SIDE, PREVIEW_SIDE), Image.LANCZOS)
    vista = Path(out) / "vistas" / f"{aid}.jpg"
    prev.save(vista, "JPEG", quality=85)

    if not date:
        date = datetime.fromtimestamp(Path(path).stat().st_mtime).isoformat(timespec="seconds")
        date_src = "archivo"
    else:
        date_src = "exif"

    return {
        "id": aid, "tipo": "foto", "archivo": str(path), "nombre": Path(path).name,
        "vista": str(vista), "ancho": w, "alto": h, "proporcion": ratio_label(w, h),
        "orientacion": orientation(w, h), "megapixeles": round(w * h / 1e6, 1),
        "fecha": date, "fecha_origen": date_src,
        **m, "tecnica": tec, "avisos": warn, "seg": round(time.time() - t0, 2),
    }


# ============================================================== videos

def run(cmd, timeout=180):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def probe(path):
    r = run(["ffprobe", "-v", "error", "-print_format", "json",
             "-show_streams", "-show_format", str(path)])
    if r.returncode != 0:
        return None
    return json.loads(r.stdout or "{}")


def video_meta(info):
    vs = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    has_audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
    if not vs:
        return None
    w, h = int(vs.get("width", 0)), int(vs.get("height", 0))
    rot = 0
    try:
        rot = int(vs.get("tags", {}).get("rotate", 0))
    except Exception:
        pass
    for sd in vs.get("side_data_list", []) or []:
        if "rotation" in sd:
            try:
                rot = int(sd["rotation"])
            except Exception:
                pass
    if abs(rot) % 180 == 90:
        w, h = h, w
    fr = vs.get("avg_frame_rate") or vs.get("r_frame_rate") or "0/1"
    try:
        n, d = fr.split("/")
        fps = float(n) / float(d) if float(d) else 0.0
    except Exception:
        fps = 0.0
    dur = float(info.get("format", {}).get("duration") or vs.get("duration") or 0)
    date = info.get("format", {}).get("tags", {}).get("creation_time")
    return {"ancho": w, "alto": h, "fps": round(fps, 2), "duracion": round(dur, 2),
            "audio": has_audio, "codec": vs.get("codec_name"), "fecha_meta": date}


def scene_cuts(path, dur):
    """Tiempos de corte de escena (ffmpeg scene > 0.3), a baja resolución."""
    r = run(["ffmpeg", "-hide_banner", "-t", str(min(dur, 300)), "-i", str(path),
             "-vf", "scale=320:-2,select='gt(scene,0.30)',showinfo",
             "-an", "-f", "null", "-"], timeout=300)
    return sorted({round(float(x), 2) for x in re.findall(r"pts_time:([\d.]+)", r.stderr)})


def loudness(path):
    r = run(["ffmpeg", "-hide_banner", "-i", str(path), "-vn", "-af", "volumedetect",
             "-f", "null", "-"], timeout=300)
    mean = re.search(r"mean_volume:\s*(-?[\d.]+) dB", r.stderr)
    peak = re.search(r"max_volume:\s*(-?[\d.]+) dB", r.stderr)
    return (float(mean.group(1)) if mean else None, float(peak.group(1)) if peak else None)


def sample_times(dur, maxn):
    if dur <= 0:
        return [0.0]
    base = {0.05}
    if dur > 1.2:
        base.add(1.0)
    if dur > 2.4:
        base.add(2.0)
    n = max(4, min(maxn, int(dur / 1.5) + 1))
    for i in range(n):
        base.add(round(0.05 + (dur - 0.25) * i / max(1, n - 1), 2))
    return sorted(t for t in base if t < dur)


def extract_frame(path, t, dst):
    r = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}",
             "-i", str(path), "-frames:v", "1", "-vf", f"scale='min({PREVIEW_SIDE},iw)':-2",
             "-q:v", "3", str(dst)], timeout=60)
    return r.returncode == 0 and Path(dst).exists()


def scan_video(job):
    path, aid, out, maxn = job
    t0 = time.time()
    if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
        return {"id": aid, "tipo": "video", "archivo": str(path), "nombre": Path(path).name,
                "error": "ffmpeg/ffprobe no instalados: el video no se puede analizar"}
    info = probe(path)
    meta = video_meta(info) if info else None
    if not meta:
        return {"id": aid, "tipo": "video", "archivo": str(path), "nombre": Path(path).name,
                "error": "no se pudo leer el video"}

    fdir = Path(out) / "fotogramas"
    frames, grays = [], []
    for t in sample_times(meta["duracion"], maxn):
        dst = fdir / f"{aid}_{t:06.2f}.jpg"
        if not extract_frame(path, t, dst):
            continue
        with Image.open(dst) as im:
            im.load()
            m = analyze_pil(im)
            grays.append(np.asarray(im.convert("L").resize((64, 64)), dtype=np.float32) / 255)
        tec, _ = technical(m, min(meta["ancho"], meta["alto"]))
        frames.append({"t": t, "archivo": str(dst), "nitidez": m["nitidez"],
                       "exposicion": m["exposicion"], "color": m["color"],
                       "caras": len(m["caras"] or []), "foco": m["foco"],
                       "tecnica": tec, "_m": m})

    if not frames:
        return {"id": aid, "tipo": "video", "archivo": str(path), "nombre": Path(path).name,
                "error": "no se pudieron extraer fotogramas", **meta}

    diffs = [float(np.abs(grays[i + 1] - grays[i]).mean()) for i in range(len(grays) - 1)]
    mov = clamp(float(np.mean(diffs)) / 0.12 * 100) if diffs else 0.0
    hook = [f for f in frames if f["t"] <= 2.05]
    hook_diff = 0.0
    if len(hook) >= 2:
        i0 = frames.index(hook[0])
        i1 = frames.index(hook[-1])
        hook_diff = clamp(float(np.abs(grays[i1] - grays[i0]).mean()) / 0.12 * 100)

    for f in frames:
        f["portada"] = round(0.4 * f["nitidez"] + 0.3 * f["exposicion"]
                             + 0.1 * f["color"] + (20 if f["caras"] else 0), 1)
    cover = max(frames, key=lambda f: f["portada"])
    cm = cover["_m"]

    cuts = scene_cuts(path, meta["duracion"])
    mean_db, peak_db = loudness(path) if meta["audio"] else (None, None)

    med = {k: float(np.median([f[k] for f in frames])) for k in ("nitidez", "exposicion")}
    med_noise = float(np.median([f["_m"]["ruido"] for f in frames]))
    resol = clamp(min(meta["ancho"], meta["alto"]) / 1080 * 100)
    tec = 0.45 * med["nitidez"] + 0.25 * med["exposicion"] + 0.15 * med_noise + 0.15 * resol
    warn = []
    if meta["fps"] and meta["fps"] < 24:
        tec -= 10
        warn.append(f"{meta['fps']} fps: se verá entrecortado")
    if med["nitidez"] < 35:
        warn.append("mayormente desenfocado o movido")
    if min(meta["ancho"], meta["alto"]) < 1080:
        warn.append(f"resolución baja ({min(meta['ancho'], meta['alto'])}px)")
    if not meta["audio"]:
        warn.append("sin pista de audio")
    elif mean_db is not None and mean_db < -45:
        warn.append("audio casi en silencio")
    if hook and np.mean([f["nitidez"] for f in hook]) < 30:
        warn.append("arranque (0-2 s) borroso")

    for f in frames:
        f.pop("_m", None)

    w, h = meta["ancho"], meta["alto"]
    return {
        "id": aid, "tipo": "video", "archivo": str(path), "nombre": Path(path).name,
        "vista": cover["archivo"], **meta,
        "proporcion": ratio_label(w, h), "orientacion": orientation(w, h),
        "fecha": meta.get("fecha_meta") or datetime.fromtimestamp(
            Path(path).stat().st_mtime).isoformat(timespec="seconds"),
        "nitidez": round(med["nitidez"], 1), "exposicion": round(med["exposicion"], 1),
        "ruido": round(med_noise, 1), "color": cm["color"], "contraste": cm["contraste"],
        "caras": cm["caras"], "foco": cm["foco"], "dhash": cm["dhash"], "hist": cm["hist"],
        "movimiento": round(mov, 1), "movimiento_inicio": round(hook_diff, 1),
        "nitidez_inicio": round(float(np.mean([f["nitidez"] for f in hook])), 1) if hook else None,
        "cortes": cuts, "volumen_medio_db": mean_db, "volumen_pico_db": peak_db,
        "portada_sugerida_t": cover["t"], "fotogramas": frames,
        "tecnica": round(clamp(tec), 1), "avisos": warn, "seg": round(time.time() - t0, 2),
    }


# ======================================================= agrupación

def group_duplicates(assets):
    """Ráfagas y casi-duplicados -> grupos G1, G2...
    Dos fotos van al mismo grupo si son estructuralmente casi iguales, o si se
    tomaron con segundos de diferencia y se parecen bastante."""
    ok = [a for a in assets if "error" not in a]
    parent = {a["id"]: a["id"] for a in ok}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def ts(a):
        try:
            return datetime.fromisoformat(str(a.get("fecha"))[:19]).timestamp()
        except Exception:
            return None

    for i in range(len(ok)):
        for j in range(i + 1, len(ok)):
            a, b = ok[i], ok[j]
            if a["tipo"] != b["tipo"]:
                continue
            hd = hamming_hex(a["dhash"], b["dhash"])
            hi = hist_intersection(a["hist"], b["hist"])
            ta, tb = ts(a), ts(b)
            burst = (ta is not None and tb is not None and abs(ta - tb) <= 3
                     and a.get("fecha_origen") == "exif" and b.get("fecha_origen") == "exif")
            if (hd <= 8 and hi >= 0.75) or (burst and hd <= 16 and hi >= 0.6):
                parent[find(a["id"])] = find(b["id"])

    clusters = {}
    for a in ok:
        clusters.setdefault(find(a["id"]), []).append(a)
    groups = []
    n = 0
    for members in clusters.values():
        if len(members) < 2:
            continue
        n += 1
        gid = f"G{n}"
        best = max(members, key=lambda a: a["tecnica"])
        for a in members:
            a["grupo"] = gid
            a["mejor_del_grupo"] = a["id"] == best["id"]
        groups.append({"id": gid, "miembros": [a["id"] for a in members], "mejor_tecnica": best["id"]})
    return groups


# ================================================ misma toma (recortes)

def same_shot(assets):
    """Detecta la misma toma aunque esté recortada, girada o reexpuesta
    (ORB + homografía). El dHash no ve un recorte; esto sí. Rellena
    activo['escena'] = {otro_id: similitud 0-1} solo para pares relevantes."""
    if not CV2 or not hasattr(cv2, "ORB_create"):
        return False
    ok = [a for a in assets if "error" not in a and a.get("vista")]
    orb = cv2.ORB_create(800)
    feats = {}
    for a in ok:
        try:
            g = np.asarray(Image.open(a["vista"]).convert("L"))
            sc = 640 / max(g.shape)
            g = cv2.resize(g, (max(1, int(g.shape[1] * sc)), max(1, int(g.shape[0] * sc))))
            kp, d = orb.detectAndCompute(g, None)
            if d is not None and len(d) >= 20:
                feats[a["id"]] = (kp, d)
        except Exception:
            continue
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    ids = list(feats)
    by = {a["id"]: a for a in ok}
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            if hist_intersection(by[a]["hist"], by[b]["hist"]) < 0.35:
                continue          # colores distintos: no es la misma toma
            (ka, da), (kb, db) = feats[a], feats[b]
            try:
                m = bf.knnMatch(da, db, k=2)
            except Exception:
                continue
            good = [x for x in m if len(x) == 2 and x[0].distance < 0.75 * x[1].distance]
            if len(good) < 15:
                continue
            src = np.float32([ka[x[0].queryIdx].pt for x in good])
            dst = np.float32([kb[x[0].trainIdx].pt for x in good])
            _, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
            inl = int(mask.sum()) if mask is not None else 0
            ratio = inl / min(len(da), len(db))
            if inl >= 20 and ratio >= 0.08:
                sim = round(min(0.98, 0.6 + 1.2 * ratio), 2)
                by[a].setdefault("escena", {})[b] = sim
                by[b].setdefault("escena", {})[a] = sim
    return True


# ================================================================ main

def collect(folder, recursive):
    it = Path(folder).rglob("*") if recursive else Path(folder).glob("*")
    files = [p for p in it if p.is_file() and not p.name.startswith(".")
             and "rrss-trabajo" not in p.parts]
    imgs = sorted(p for p in files if p.suffix.lower() in IMAGE_EXT)
    vids = sorted(p for p in files if p.suffix.lower() in VIDEO_EXT)
    if not HEIF:
        heic = [p for p in imgs if p.suffix.lower() in {".heic", ".heif"}]
        if heic:
            print(f"aviso: {len(heic)} archivos HEIC omitidos. "
                  "Instala `pip install pillow-heif` para leerlos.", file=sys.stderr)
            imgs = [p for p in imgs if p not in heic]
    return imgs, vids


def main():
    ap = argparse.ArgumentParser(description="Inventario técnico de fotos y videos.")
    ap.add_argument("carpeta")
    ap.add_argument("--out", required=True, help="carpeta de trabajo")
    ap.add_argument("-r", "--recursive", action="store_true")
    ap.add_argument("--max-frames", type=int, default=12, help="fotogramas por video")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--json", action="store_true", help="imprime el inventario en JSON")
    a = ap.parse_args()

    out = Path(a.out)
    (out / "vistas").mkdir(parents=True, exist_ok=True)
    (out / "fotogramas").mkdir(parents=True, exist_ok=True)

    imgs, vids = collect(a.carpeta, a.recursive)
    if not imgs and not vids:
        sys.exit(f"error: no hay fotos ni videos en {a.carpeta}")

    t0 = time.time()
    ijobs = [(p, f"F{i + 1:02d}", str(out)) for i, p in enumerate(imgs)]
    vjobs = [(p, f"V{i + 1:02d}", str(out), a.max_frames) for i, p in enumerate(vids)]
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        assets = list(ex.map(scan_image, ijobs)) + list(ex.map(scan_video, vjobs))

    groups = group_duplicates(assets)
    shots = same_shot(assets)
    inv = {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "carpeta": str(Path(a.carpeta).resolve()),
        "trabajo": str(out.resolve()),
        "herramientas": {"caras": face_backend(), "misma_toma": shots, "heic": HEIF,
                         "ffmpeg": bool(shutil.which("ffmpeg"))},
        "resumen": {"fotos": len(imgs), "videos": len(vids),
                    "errores": sum(1 for x in assets if "error" in x),
                    "grupos_duplicados": len(groups)},
        "grupos": groups,
        "activos": assets,
    }
    save_json(out / "inventario.json", inv)

    if a.json:
        print(json.dumps(inv, ensure_ascii=False, indent=2))
        return

    print(f"INVENTARIO  ·  {len(imgs)} fotos  ·  {len(vids)} videos  ·  "
          f"{len(groups)} grupos de ráfaga/duplicado  ·  {time.time() - t0:.1f}s")
    print("=" * 92)
    print(f"{'id':4} {'técnica':>7}  {'':20} {'prop.':6} {'orient.':10} {'extra':14} archivo")
    for x in assets:
        if "error" in x:
            print(f"{x['id']:4} {'ERROR':>7}  {x['error']}  ({x.get('nombre', '')})")
            continue
        extra = f"{x['duracion']:.1f}s" if x["tipo"] == "video" else f"{x['megapixeles']}MP"
        if x.get("caras"):
            extra += f" {len(x['caras'])}cara"
        g = f" [{x['grupo']}{'*' if x.get('mejor_del_grupo') else ''}]" if x.get("grupo") else ""
        if x.get("escena"):
            g += " ~" + ",".join(sorted(x["escena"]))
        print(f"{x['id']:4} {x['tecnica']:7.1f}  {bar(x['tecnica'])} {x['proporcion']:6} "
              f"{x['orientacion']:10} {extra:14} {x['nombre']}{g}")
        for w in x["avisos"]:
            print(f"{'':14}- {w}")
    print("-" * 92)
    print(f"escrito: {out / 'inventario.json'}")
    if not face_backend():
        print("aviso: sin OpenCV no hay detección de caras (pip install opencv-python-headless)")


if __name__ == "__main__":
    main()
