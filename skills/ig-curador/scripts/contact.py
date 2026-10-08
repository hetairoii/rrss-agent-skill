#!/usr/bin/env python3
"""
contact.py - hojas de contacto para que Claude (y tú) vean todo de un vistazo.

Mirar 60 fotos una a una gasta tiempo y contexto. Una hoja de 12 miniaturas
etiquetadas deja comparar, detectar duplicados y descartar en una sola mirada.
Las finalistas se miran después a tamaño completo (vistas/<id>.jpg).

Modos
  python3 contact.py TRABAJO                      # todas, 12 por hoja
  python3 contact.py TRABAJO --ids F01,F04,V02     # solo esas
  python3 contact.py TRABAJO --video V01           # tira de fotogramas con tiempos
  python3 contact.py TRABAJO --seleccion           # la selección final, en orden,
                                                   # con el recorte real marcado

Todo se escribe en TRABAJO/hojas/.
"""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import crop_box, fmt_time, load_json, parse_ratio  # noqa: E402

BG = (24, 24, 27)
FG = (235, 235, 235)
DIM = (150, 150, 155)
WARN = (240, 90, 80)
OK = (90, 200, 120)
ACCENT = (255, 196, 0)


def font(size):
    for name in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "Arial.ttf",
                 "/System/Library/Fonts/Supplemental/Arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def fit(img, box_w, box_h):
    im = img.copy()
    im.thumbnail((box_w, box_h), Image.LANCZOS)
    canvas = Image.new("RGB", (box_w, box_h), BG)
    canvas.paste(im, ((box_w - im.width) // 2, (box_h - im.height) // 2))
    return canvas, ((box_w - im.width) // 2, (box_h - im.height) // 2, im.width, im.height)


def open_view(a):
    try:
        im = Image.open(a["vista"])
        im.load()
        return im.convert("RGB")
    except Exception:
        return Image.new("RGB", (400, 400), (60, 20, 20))


def video_cell(a, cw, ch):
    """2x2 de fotogramas repartidos por el video."""
    frames = a.get("fotogramas") or []
    pick = [frames[int(i * (len(frames) - 1) / 3)] for i in range(4)] if len(frames) >= 4 else frames
    canvas = Image.new("RGB", (cw, ch), BG)
    hw, hh = cw // 2, ch // 2
    f = font(14)
    for k, fr in enumerate(pick):
        try:
            im = Image.open(fr["archivo"]).convert("RGB")
        except Exception:
            continue
        cell, _ = fit(im, hw - 2, hh - 2)
        x, y = (k % 2) * hw, (k // 2) * hh
        canvas.paste(cell, (x + 1, y + 1))
        d = ImageDraw.Draw(canvas)
        d.rectangle([x + 4, y + 4, x + 58, y + 22], fill=(0, 0, 0))
        d.text((x + 8, y + 5), fmt_time(fr["t"]), fill=ACCENT, font=f)
    return canvas


def sheet(assets, out, title, cols=4, cell=360):
    label_h = 54
    rows = (len(assets) + cols - 1) // cols
    W, H = cols * cell, rows * (cell + label_h) + 40
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((12, 10), title, fill=FG, font=font(18))
    f1, f2 = font(17), font(13)
    for i, a in enumerate(assets):
        x, y = (i % cols) * cell, 40 + (i // cols) * (cell + label_h)
        if "error" in a:
            d.rectangle([x + 4, y + 4, x + cell - 4, y + cell - 4], outline=WARN, width=2)
            d.text((x + 12, y + 12), f"{a['id']} ERROR", fill=WARN, font=f1)
            continue
        thumb = video_cell(a, cell - 8, cell - 8) if a["tipo"] == "video" else fit(open_view(a), cell - 8, cell - 8)[0]
        img.paste(thumb, (x + 4, y + 4))
        bad = a["tecnica"] < 45 or any("desenfoc" in w or "quemad" in w for w in a.get("avisos", []))
        if bad:
            d.rectangle([x + 4, y + 4, x + cell - 5, y + cell - 5], outline=WARN, width=3)
        # etiqueta grande del id, legible incluso reducida
        d.rectangle([x + 4, y + 4, x + 74, y + 34], fill=(0, 0, 0))
        d.text((x + 10, y + 8), a["id"], fill=ACCENT, font=font(20))
        line1 = f"{a['proporcion']}  téc {a['tecnica']:.0f}"
        if a["tipo"] == "video":
            line1 += f"  {a['duracion']:.1f}s"
        if a.get("caras"):
            line1 += f"  {len(a['caras'])} cara(s)"
        if a.get("grupo"):
            line1 += f"  {a['grupo']}{'*' if a.get('mejor_del_grupo') else ''}"
        d.text((x + 8, y + cell), line1, fill=WARN if bad else FG, font=f1)
        line2 = ", ".join(a.get("avisos", [])) or a.get("nombre", "")
        d.text((x + 8, y + cell + 24), line2[:44], fill=WARN if a.get("avisos") else DIM, font=f2)
    img.save(out, "JPEG", quality=88)
    return out


def filmstrip(a, out, cols=4, cell=300):
    frames = a.get("fotogramas") or []
    if not frames:
        sys.exit(f"error: {a['id']} no tiene fotogramas")
    ratio = a["ancho"] / a["alto"]
    cw = cell
    ch = int(cell / ratio) if ratio >= 1 else int(cell / ratio)
    ch = min(ch, int(cell * 1.8))
    rows = (len(frames) + cols - 1) // cols
    W, H = cols * cw, rows * (ch + 30) + 64
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    cuts = a.get("cortes") or []
    d.text((12, 8), f"{a['id']}  ·  {a['nombre']}  ·  {a['duracion']:.1f}s  ·  {a['fps']} fps  ·  "
                    f"audio: {'sí' if a.get('audio') else 'no'}", fill=FG, font=font(18))
    d.text((12, 34), f"cortes de escena: {', '.join(fmt_time(c) for c in cuts) or 'ninguno'}   ·   "
                     f"portada sugerida: {fmt_time(a.get('portada_sugerida_t', 0))}",
           fill=DIM, font=font(14))
    for i, fr in enumerate(frames):
        x, y = (i % cols) * cw, 64 + (i // cols) * (ch + 30)
        try:
            im = Image.open(fr["archivo"]).convert("RGB")
        except Exception:
            continue
        thumb, _ = fit(im, cw - 6, ch - 6)
        img.paste(thumb, (x + 3, y + 3))
        hook = fr["t"] <= 2.05
        if abs(fr["t"] - a.get("portada_sugerida_t", -1)) < 1e-6:
            d.rectangle([x + 3, y + 3, x + cw - 4, y + ch - 4], outline=OK, width=3)
        d.text((x + 6, y + ch + 4),
               f"{fmt_time(fr['t'])}{'  ARRANQUE' if hook else ''}  nit {fr['nitidez']:.0f}",
               fill=ACCENT if hook else FG, font=font(14))
    img.save(out, "JPEG", quality=88)
    return out


def selection_sheet(work, out, cell=340):
    sel = load_json(Path(work) / "seleccion.json")
    inv = {a["id"]: a for a in load_json(Path(work) / "inventario.json")["activos"]}
    items = sel.get("seleccion", [])
    if not items:
        sys.exit("error: seleccion.json no tiene elementos")
    ratio = parse_ratio(sel.get("proporcion", "4:5"))
    cw = cell
    ch = int(cell / ratio)
    cols = min(len(items), 5)
    rows = (len(items) + cols - 1) // cols
    label_h = 70
    W, H = cols * cw, rows * (ch + label_h) + 48
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((12, 12), f"{sel['formato'].upper()}  ·  {sel.get('proporcion')}  ·  objetivo: "
                     f"{sel.get('objetivo')}  ·  potencial {sel.get('potencial', 0):.0f}/100",
           fill=FG, font=font(18))
    for i, it in enumerate(items):
        a = inv.get(it["id"])
        if not a:
            continue
        x, y = (i % cols) * cw, 48 + (i // cols) * (ch + label_h)
        if a["tipo"] == "foto":
            src = open_view(a)
        else:
            # el fotograma que de verdad abre ese tramo, no la portada del video
            t = (it.get("tramo") or [a.get("portada_sugerida_t", 0)])[0] + 0.3
            fr = min(a.get("fotogramas") or [{"t": 0, "archivo": a["vista"]}],
                     key=lambda x: abs(x["t"] - t))
            src = Image.open(fr["archivo"]).convert("RGB")
        w, h = src.size
        if it.get("modo") == "relleno":
            bgim = src.resize((cw - 4, ch - 4)).filter(ImageFilter.GaussianBlur(18))
            mask_src = src.copy()
            mask_src.thumbnail((cw - 4, ch - 4))
            bgim.paste(mask_src, ((cw - 4 - mask_src.width) // 2, (ch - 4 - mask_src.height) // 2))
            tile = bgim
        else:
            box = crop_box(w, h, ratio, tuple(it.get("foco") or a.get("foco") or (0.5, 0.5)))
            tile = src.crop(tuple(int(v) for v in box)).resize((cw - 4, ch - 4), Image.LANCZOS)
        img.paste(tile, (x + 2, y + 2))
        if sel["formato"] in ("story", "reel"):
            # zonas que tapa la interfaz (aprox. proporcional a 1080x1920)
            top, bot = int(ch * 250 / 1920), int(ch * 1600 / 1920)
            d.line([x + 2, y + top, x + cw - 2, y + top], fill=WARN, width=1)
            d.line([x + 2, y + bot, x + cw - 2, y + bot], fill=WARN, width=1)
        d.rectangle([x + 2, y + 2, x + 44, y + 30], fill=(0, 0, 0))
        d.text((x + 8, y + 5), str(i + 1), fill=ACCENT, font=font(20))
        d.text((x + 6, y + ch + 4), f"{it['id']}  {it.get('rol', '')}", fill=FG, font=font(16))
        extra = f"puntaje {it.get('puntaje', 0):.0f}"
        if it.get("tramo"):
            t0, t1 = it["tramo"]
            extra += f"  {fmt_time(t0)}-{fmt_time(t1)}"
        if it.get("modo") == "relleno":
            extra += "  relleno"
        d.text((x + 6, y + ch + 26), extra, fill=DIM, font=font(14))
        if it.get("caras_cortadas"):
            d.text((x + 6, y + ch + 46), f"corta {it['caras_cortadas']} cara(s)", fill=WARN, font=font(14))
    img.save(out, "JPEG", quality=90)
    return out


def main():
    ap = argparse.ArgumentParser(description="Hojas de contacto.")
    ap.add_argument("trabajo")
    ap.add_argument("--ids", help="lista separada por comas")
    ap.add_argument("--video", help="id de un video: tira de fotogramas")
    ap.add_argument("--seleccion", action="store_true", help="vista previa de la selección")
    ap.add_argument("--por-hoja", type=int, default=12)
    ap.add_argument("--cols", type=int, default=4)
    a = ap.parse_args()

    work = Path(a.trabajo)
    hojas = work / "hojas"
    hojas.mkdir(parents=True, exist_ok=True)

    if a.seleccion:
        print(selection_sheet(work, hojas / "seleccion.jpg"))
        return

    inv = load_json(work / "inventario.json")
    assets = inv["activos"]
    if a.video:
        v = next((x for x in assets if x["id"] == a.video), None)
        if not v or v["tipo"] != "video":
            sys.exit(f"error: {a.video} no es un video del inventario")
        print(filmstrip(v, hojas / f"tira_{a.video}.jpg"))
        return
    if a.ids:
        want = [s.strip().upper() for s in a.ids.split(",") if s.strip()]
        by = {x["id"]: x for x in assets}
        assets = [by[i] for i in want if i in by]
        prefix = "detalle"
    else:
        prefix = "hoja"

    n = a.por_hoja
    total = (len(assets) + n - 1) // n
    for k in range(total):
        chunk = assets[k * n:(k + 1) * n]
        title = (f"{prefix} {k + 1}/{total}  ·  {chunk[0]['id']}-{chunk[-1]['id']}  ·  "
                 "rojo = problema técnico  ·  G = ráfaga (* mejor técnica)")
        print(sheet(chunk, hojas / f"{prefix}_{k + 1:02d}.jpg", title, cols=a.cols))


if __name__ == "__main__":
    main()
