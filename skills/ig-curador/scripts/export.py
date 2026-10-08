#!/usr/bin/env python3
"""
export.py - deja la selección aprobada lista para subir, en orden y a medida.

Fotos:   recorte a la proporción del formato centrado en el foco (o en la cara),
         redimensionado a 1080 de ancho, convertido a sRGB, JPEG de alta
         calidad, sin metadatos (la ubicación GPS de tu cámara no viaja).
         Modo "relleno": la foto entera sobre un fondo difuminado de sí misma,
         para cuando recortar a 9:16 destrozaría la imagen.
Videos:  el tramo elegido, recortado o con relleno a la medida, H.264/AAC,
         30 fps, listo para el móvil.
Reel:    además de los tramos sueltos, un montaje borrador (reel_borrador.mp4)
         en el orden propuesto, y la portada a 1080x1920.

Nada se sube a ningún sitio. Esto escribe archivos en tu disco y ahí termina.

Uso
  python3 export.py TRABAJO                     # escribe TRABAJO/listo/
  python3 export.py TRABAJO --out ~/Desktop/sabado
  python3 export.py TRABAJO --sin-montaje       # reel: solo tramos sueltos
"""

import argparse
import io
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageCms, ImageFilter, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import crop_box, load_json, parse_ratio, slug  # noqa: E402

try:
    from pillow_heif import register_heif_opener  # type: ignore
    register_heif_opener()
except Exception:
    pass

ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
       "-r", "30", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-movflags", "+faststart"]


def to_srgb(img):
    icc = img.info.get("icc_profile")
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            dst = ImageCms.createProfile("sRGB")
            img = ImageCms.profileToProfile(img, src, dst, outputMode="RGB")
        except Exception:
            pass
    return img.convert("RGB")


def render_image(path, ratio, size, mode, focus):
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im = to_srgb(im)
    W, H = size
    if mode == "relleno":
        bg = ImageOps.fit(im, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(40))
        bg = Image.blend(bg, Image.new("RGB", (W, H), (0, 0, 0)), 0.25)
        fg = im.copy()
        fg.thumbnail((W, H), Image.LANCZOS)
        bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
        return bg
    box = crop_box(im.width, im.height, ratio, focus)
    return im.crop(tuple(int(round(v)) for v in box)).resize((W, H), Image.LANCZOS)


def ffmpeg(args):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + args,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-600:])


def video_filter(a, ratio, size, mode, focus):
    W, H = size
    if mode == "relleno":
        return (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"boxblur=30:4,eq=brightness=-0.08[bg];[b]scale={W}:{H}:force_original_aspect_ratio="
                f"decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    x0, y0, x1, y1 = crop_box(a["ancho"], a["alto"], ratio, focus)
    cw, ch = int(x1 - x0) // 2 * 2, int(y1 - y0) // 2 * 2
    return f"crop={cw}:{ch}:{int(x0)}:{int(y0)},scale={W}:{H},setsar=1"


def render_video(a, t0, t1, ratio, size, mode, focus, dst):
    vf = video_filter(a, ratio, size, mode, focus)
    args = ["-ss", f"{t0:.3f}", "-to", f"{t1:.3f}", "-i", a["archivo"]]
    if not a.get("audio"):
        # pista muda para que el montaje se pueda concatenar sin sorpresas
        args += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                 "-shortest", "-map", "0:v:0", "-map", "1:a:0"]
    args += ["-vf", vf] + ENC + [str(dst)]
    ffmpeg(args)


def still_clip(img_path, seconds, dst):
    """Foto fija como tramo de reel, con un acercamiento lento para que no parezca congelada."""
    frames = int(seconds * 30)
    # una sola imagen de entrada: zoompan genera los `frames` fotogramas a partir de ella
    ffmpeg(["-i", str(img_path),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-filter_complex",
            f"[0]scale=1188:2112,zoompan=z='min(1+0.0015*on,1.08)':x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30,setsar=1[v]",
            "-map", "[v]", "-map", "1:a", "-t", f"{seconds:.2f}"] + ENC + [str(dst)])


def main():
    ap = argparse.ArgumentParser(description="Exporta la selección a medida de Instagram.")
    ap.add_argument("trabajo")
    ap.add_argument("--out")
    ap.add_argument("--sin-montaje", action="store_true")
    ap.add_argument("--calidad", type=int, default=92)
    a = ap.parse_args()

    work = Path(a.trabajo)
    sel = load_json(work / "seleccion.json")
    inv = {x["id"]: x for x in load_json(work / "inventario.json")["activos"]}
    ev = load_json(work / "evaluacion.json", default={})
    ev = {k.upper(): v for k, v in ev.get("activos", ev).items() if isinstance(v, dict)}
    out = Path(a.out) if a.out else work / "listo"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    fmt = sel["formato"]
    ratio = parse_ratio(sel["proporcion"])
    size = tuple(sel["medidas"])
    has_ff = bool(shutil.which("ffmpeg"))
    written, notes, segs = [], [], []

    for i, it in enumerate(sel["seleccion"], 1):
        asset = inv[it["id"]]
        role = slug(it.get("rol") or "pieza", 20)
        focus = tuple(it.get("foco") or asset.get("foco") or (0.5, 0.5))
        mode = it.get("modo", "recorte")
        base = f"{i:02d}_{role}_{it['id']}"
        try:
            if asset["tipo"] == "foto":
                img = render_image(asset["archivo"], ratio, size, mode, focus)
                dst = out / f"{base}.jpg"
                img.save(dst, "JPEG", quality=a.calidad, optimize=True, progressive=True)
                written.append(dst)
                if fmt == "reel" and has_ff:
                    seg = out / "tramos" / f"{base}.mp4"
                    seg.parent.mkdir(exist_ok=True)
                    still_clip(dst, it.get("duracion", 2.0), seg)
                    segs.append(seg)
            else:
                if not has_ff:
                    notes.append(f"{it['id']}: sin ffmpeg no se puede exportar video")
                    continue
                t0, t1 = it.get("tramo") or [0.0, asset["duracion"]]
                if fmt in ("carrusel", "story") and t1 - t0 > 60:
                    t1 = t0 + 60
                    notes.append(f"{it['id']}: recortado a 60 s (máximo por pieza)")
                dst = (out / "tramos" / f"{base}.mp4") if fmt == "reel" else out / f"{base}.mp4"
                dst.parent.mkdir(exist_ok=True)
                render_video(asset, float(t0), float(t1), ratio, size, mode, focus, dst)
                (segs if fmt == "reel" else written).append(dst)
        except Exception as e:
            notes.append(f"{it['id']}: error al exportar ({e})")

    if fmt == "reel" and has_ff:
        if segs and not a.sin_montaje:
            lst = out / "tramos" / "lista.txt"
            lst.write_text("".join(f"file '{s.resolve()}'\n" for s in segs), encoding="utf-8")
            reel = out / "reel_borrador.mp4"
            try:
                ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst)] + ENC + [str(reel)])
                written.append(reel)
            except Exception as e:
                notes.append(f"montaje: {e}")
        c = sel.get("portada")
        if c:
            dst = out / "00_portada.jpg"
            try:
                src = inv[c["id"]]
                if src["tipo"] == "video":
                    raw = out / "tramos" / "_portada_raw.png"
                    ffmpeg(["-ss", f"{float(c.get('t') or 0):.3f}", "-i", src["archivo"],
                            "-frames:v", "1", str(raw)])
                    img = render_image(raw, ratio, size, "recorte",
                                       tuple(src.get("foco") or (0.5, 0.5)))
                    raw.unlink(missing_ok=True)
                else:
                    img = render_image(src["archivo"], ratio, size, "recorte",
                                       tuple(src.get("foco") or (0.5, 0.5)))
                img.save(dst, "JPEG", quality=a.calidad)
                written.insert(0, dst)
                # cómo se verá en la cuadrícula del perfil (miniatura vertical, recorte central)
                gw, gh = 1080, 1440
                g = img.crop((0, (1920 - gh) // 2, gw, (1920 - gh) // 2 + gh))
                g.save(out / "00_portada_en_cuadricula.jpg", "JPEG", quality=85)
            except Exception as e:
                notes.append(f"portada: {e}")

    # textos de apoyo: orden, alt text y zona segura
    lines = [f"{fmt.upper()} · {sel['proporcion']} · {size[0]}x{size[1]} · objetivo: {sel['objetivo']}",
             "", "ORDEN DE SUBIDA"]
    for i, it in enumerate(sel["seleccion"], 1):
        alt = ev.get(it["id"], {}).get("alt")
        extra = f"  tramo {it['tramo'][0]:.1f}-{it['tramo'][1]:.1f}s" if it.get("tramo") else ""
        lines.append(f"{i:2}. {it['id']}  {it.get('rol', '')}{extra}")
        if alt:
            lines.append(f"    texto alternativo: {alt}")
    if sel.get("zona_segura"):
        lines += ["", "ZONA SEGURA", sel["zona_segura"]]
    if sel.get("sticker"):
        lines += ["", "STICKER", sel["sticker"]]
    if fmt == "reel":
        lines += ["", "MONTAJE",
                  "reel_borrador.mp4 es un corte de referencia. Si lo editas en otra app,",
                  "exporta SIN su marca de agua: Instagram reduce el alcance del contenido",
                  "con logos de otras plataformas. Añade la música desde Instagram."]
    if notes:
        lines += ["", "AVISOS"] + [f"- {n}" for n in notes]
    lines += ["", "Nada se ha publicado. Estos archivos los subes tú."]
    (out / "LEEME.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"EXPORTADO  ·  {fmt}  ·  {len(written)} archivo(s)  ·  {out}")
    for p in written:
        print(f"  {p.name}")
    for n in notes:
        print(f"  ! {n}")


if __name__ == "__main__":
    main()
