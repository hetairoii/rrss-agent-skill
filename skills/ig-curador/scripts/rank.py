#!/usr/bin/env python3
"""
rank.py - combina el brief, la evaluación visual y las métricas técnicas y
elige el contenido para el formato pedido.

Entradas (en la carpeta de trabajo):
  brief.json        qué se quiere con la publicación (objetivo, formato, mensaje...)
  inventario.json   lo que midió scan.py
  evaluacion.json   lo que Claude vio en cada pieza (rubrica.json, 0-10)

Salida:
  seleccion.json    la elección, en orden, con rol, recorte y motivo
  seleccion.md      el mismo informe en texto legible

Cómo puntúa, sin magia:
  visual   = media ponderada de la rúbrica. Los pesos son los del formato
             (formatos.json) x los multiplicadores del objetivo (objetivos.json)
             x tus ajustes aprendidos (~/.claude/rrss/pesos.json, si existe).
  puntaje  = (1 - a) * visual + a * técnica - penalizaciones
             a = peso_tecnica del formato (un story vive de lo auténtico, un
             post de la calidad, así que no pesa igual).
  penalizaciones: lo que se pierde al recortar a la proporción destino, caras
             cortadas por ese recorte, resolución insuficiente tras recortar.

Luego cada formato elige a su manera: un post se queda con la mejor y da
alternativas distintas entre sí; un carrusel elige portada aparte y rellena
con diversidad (MMR) para no repetir la misma foto tres veces; un reel arma
una línea de tiempo empezando por el mejor arranque; un story arma la
secuencia apertura -> contenido -> pregunta -> cierre.

El "potencial" final es un índice comparativo para decidir entre opciones,
no una predicción de visualizaciones. Ver references/engagement.md.

Uso
  python3 rank.py TRABAJO
  python3 rank.py TRABAJO --formato carrusel --n 8
  python3 rank.py TRABAJO --formato auto          # recomienda formato
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (USER_DIR, clamp, crop_box, crop_loss, faces_cut,  # noqa: E402
                    fmt_time, load_config, load_json, parse_ratio, save_json,
                    similarity, bar)

FORMATS = ("post", "carrusel", "reel", "story")


# ================================================================ setup

def norm_objective(obj, cfg):
    o = (obj or "interaccion").strip().lower()
    o = cfg["alias"].get(o, o)
    if o not in cfg["objetivos"]:
        print(f"aviso: objetivo '{obj}' desconocido, uso 'interaccion'", file=sys.stderr)
        o = "interaccion"
    return o


def load_overrides():
    p = USER_DIR / "pesos.json"
    return load_json(p, default={}) if p.exists() else {}


def weights(base, mult, overrides, fmt):
    w = dict(base)
    for k, m in (mult or {}).items():
        if k in w:
            w[k] *= m
    for scope in ("*", fmt):
        for k, m in (overrides.get(scope) or {}).items():
            if k in w and isinstance(m, (int, float)):
                w[k] *= m
    return w


def visual(r, w, kind):
    """Media ponderada 0-100 de las dimensiones evaluadas. Devuelve (valor, cobertura)."""
    if not r:
        return None, 0.0
    rub = RUBRIC["dimensiones"]
    num = den = total = 0.0
    for k, wt in w.items():
        only = rub.get(k, {}).get("solo")
        if only and kind not in only:
            continue
        total += wt
        v = r.get(k)
        if isinstance(v, (int, float)):
            num += wt * clamp(v, 0, 10)
            den += wt
    if den == 0:
        return None, 0.0
    return num / den * 10, den / total if total else 0.0


def roles_of(r):
    roles = r.get("roles") or ([r["rol"]] if r.get("rol") else [])
    return [x.lower() for x in roles]


# ============================================================ puntuación

def fit(a, ratio, f, focus):
    """Penalización por llevar el activo a la proporción destino.
    Devuelve (total, modo, pérdida, caras cortadas, desglose)."""
    w, h = a["ancho"], a["alto"]
    loss = crop_loss(w, h, ratio)
    box = crop_box(w, h, ratio, focus)
    cut = faces_cut(a.get("caras") or [], box, w, h)
    mode = "recorte"
    why = {}
    # no lineal: recortar un 3:2 a 4:5 es normal y casi nunca un problema;
    # lo que duele es perder la mitad de la escena o cortar una cara.
    if loss > 0.01:
        why["recorte"] = (loss ** 1.5) * f.get("penalizacion_recorte", 25)
    if cut:
        why["caras cortadas"] = min(25, cut * 12)
    bw, bh = box[2] - box[0], box[3] - box[1]
    rx, ry = (focus[0] * w - box[0]) / bw, (focus[1] * h - box[1]) / bh
    if loss > 0.05 and not (0.08 <= rx <= 0.92 and 0.08 <= ry <= 0.92):
        why["foco al borde"] = 5.0
    if f.get("permite_relleno") and loss > f.get("relleno_si_perdida", 1.0):
        mode, cut = "relleno", 0
        why = {"relleno (fondo difuminado)": f.get("penalizacion_relleno", 8)}
    target_w = f["medidas"][next(iter(f["medidas"]))][0]
    crop_w = bw if mode == "recorte" else min(w, h * ratio)
    if crop_w < target_w:
        why["resolución"] = (1 - crop_w / target_w) * 20
    why = {k: round(v, 1) for k, v in why.items() if v >= 0.5}
    return sum(why.values()), mode, loss, cut, why


def score_assets(inv, ev, brief, fmt, f, obj, overrides, ratio):
    w = weights(f["pesos"], obj["multiplicadores"], overrides, fmt)
    wc = weights(f.get("pesos_portada", {}), obj["multiplicadores"], overrides, fmt) \
        if f.get("pesos_portada") else None
    alpha = f.get("peso_tecnica", 0.2)
    excl = {x.upper() for x in brief.get("excluir", [])}
    must = {x.upper() for x in brief.get("debe_incluir", [])}
    rows, dropped = [], []

    for a in inv["activos"]:
        aid = a["id"]
        r = ev.get(aid, {})
        if "error" in a:
            dropped.append({"id": aid, "motivo": a["error"]})
            continue
        if aid in excl:
            dropped.append({"id": aid, "motivo": "excluido en el brief"})
            continue
        if r.get("descartar") and aid not in must:
            dropped.append({"id": aid, "motivo": r.get("motivo") or "descartada en la evaluación visual"})
            continue
        if a["tipo"] not in f["acepta"]:
            dropped.append({"id": aid, "motivo": f"un {fmt} no admite {a['tipo']}"})
            continue
        if a["tipo"] == "video" and f.get("video_max_seg") and a["duracion"] > f["video_max_seg"] \
                and not r.get("tramos"):
            note = f"dura {a['duracion']:.0f}s (máx {f['video_max_seg']}s): hay que recortarlo"
        else:
            note = None
        if a["tecnica"] < 20 and aid not in must and not r:
            dropped.append({"id": aid, "motivo": f"técnicamente inutilizable ({a['tecnica']:.0f})"})
            continue

        focus = tuple(r.get("foco") or a.get("foco") or (0.5, 0.5))
        v, cov = visual(r, w, a["tipo"])
        pen, mode, loss, cut, why = fit(a, ratio, f, focus)
        tec = a["tecnica"]
        if v is None:
            base = tec * 0.6          # sin ojos humanos (o de Claude) no hay certeza
        else:
            base = (1 - alpha) * v + alpha * tec
        sc = clamp(base - pen)
        rel = r.get("relevancia")
        if isinstance(rel, (int, float)) and rel < 4 and aid not in must:
            # lo bonito pero fuera de tema no debe colarse en la selección
            sc *= 0.75
            note = (note + "; " if note else "") + "poco relacionada con el mensaje del brief"
        cover = None
        if wc:
            cv, _ = visual(r, wc, a["tipo"])
            if cv is not None:
                cover = clamp(0.75 * cv + 0.25 * tec - pen)
                if isinstance(rel, (int, float)) and rel < 4:
                    cover *= 0.75
        rows.append({
            "id": aid, "tipo": a["tipo"], "a": a, "r": r, "roles": roles_of(r),
            "visual": None if v is None else round(v, 1), "cobertura": round(cov, 2),
            "tecnica": tec, "penalizacion": round(pen, 1), "modo": mode,
            "perdida_recorte": round(loss, 2), "caras_cortadas": cut, "foco": list(focus),
            "desglose": why,
            "puntaje": round(sc, 1), "portada": None if cover is None else round(cover, 1),
            "obligatorio": aid in must, "nota": note,
            "motivo": r.get("motivo") or r.get("nota") or "",
        })
    rows.sort(key=lambda x: -x["puntaje"])
    return rows, dropped


def sim_rows(x, y):
    """Similitud medida + la que declaró la evaluación ('mismo_momento')."""
    linked = {i.upper() for i in (x["r"].get("mismo_momento") or [])} | \
             {i.upper() for i in (y["r"].get("mismo_momento") or [])}
    if x["id"] in linked or y["id"] in linked:
        return 0.95
    return similarity(x["a"], y["a"])


def mmr(cands, chosen, lam, n, floor):
    """Maximal Marginal Relevance: el mejor puntaje que no repita lo ya elegido."""
    chosen = list(chosen)
    pool = [c for c in cands if c not in chosen]
    while pool and len(chosen) < n:
        def gain(c):
            sim = max((sim_rows(c, s) for s in chosen), default=0.0)
            return c["puntaje"] - lam * 100 * sim, sim
        scored = [(gain(c), c) for c in pool]
        (g, sim), best = max(scored, key=lambda t: t[0][0])
        if sim >= 0.92 and not best["obligatorio"]:     # casi la misma foto
            pool.remove(best)
            continue
        if best["puntaje"] < floor and not best["obligatorio"]:
            break
        best["redundancia"] = round(sim, 2)
        chosen.append(best)
        pool.remove(best)
    return chosen


def pick_ratio(inv, f, brief, ev):
    if brief.get("proporcion") and brief["proporcion"] in f["medidas"]:
        return brief["proporcion"]
    opts = f["proporciones"]
    if len(opts) == 1:
        return opts[0]
    pool = [a for a in inv["activos"] if "error" not in a and a["tipo"] in f["acepta"]
            and not ev.get(a["id"], {}).get("descartar")]
    best, best_cost = opts[0], None
    for i, r in enumerate(opts):
        rr = parse_ratio(r)
        cost = sum(crop_loss(a["ancho"], a["alto"], rr) for a in pool) / max(1, len(pool))
        cost += i * 0.04                        # preferencia por el orden declarado
        if best_cost is None or cost < best_cost:
            best, best_cost = r, cost
    return best


# ======================================================== por formato

def select_post(rows, f, brief):
    if not rows:
        return [], []
    must = [r for r in rows if r["obligatorio"]]
    pick = must[0] if must else rows[0]
    pick["rol"] = "única"
    alts = mmr(rows, [pick], 0.5, 1 + f.get("alternativas", 3), 0)[1:]
    for a in alts:
        a["rol"] = "alternativa"
    return [pick], alts


def order_sequence(items, mode, f):
    def when(x):
        return str(x["a"].get("fecha") or "")
    if mode == "cronologico":
        return sorted(items, key=when)
    if mode == "impacto":
        return sorted(items, key=lambda x: -x["puntaje"])
    order = {r: i for i, r in enumerate(f.get("orden_roles", []))}

    def key(x):
        ranks = [order[r] for r in x["roles"] if r in order and r != "portada"]
        return (min(ranks) if ranks else len(order) - 1.5, when(x))
    return sorted(items, key=key)


def select_carousel(rows, f, brief, obj):
    if not rows:
        return [], []
    q = f["cantidad"]
    n = int(brief.get("cantidad") or q["defecto"])
    n = max(q["min"], min(q["max"], n))
    must = [r for r in rows if r["obligatorio"]]

    def cover_key(r):
        c = r["portada"] if r["portada"] is not None else r["puntaje"]
        bonus = 6 if "portada" in r["roles"] else 0
        return 0.6 * c + 0.4 * r["puntaje"] + bonus
    cover = max(rows, key=cover_key)
    cover["rol"] = "portada"
    floor = cover["puntaje"] * f.get("piso_relativo", 0.6)
    chosen = mmr(rows, [cover] + [m for m in must if m is not cover], f.get("diversidad", 0.4), n, floor)
    rest = chosen[1:]
    if not rest:
        return chosen, []
    # segunda diapositiva = segunda portada (Instagram puede reenseñar el carrusel desde ahí)
    second = max(rest, key=lambda r: (r["r"].get("impacto", 5) + r["r"].get("narrativa", 5)) * 5
                 + 0.5 * r["puntaje"])
    body = [r for r in rest if r is not second]
    closer = next((r for r in body if "cierre" in r["roles"]), None)
    if closer:
        body.remove(closer)
    mode = brief.get("orden") or obj.get("orden_carrusel", "narrativo")
    body = order_sequence(body, mode, f)
    seq = [cover, second] + body + ([closer] if closer else [])
    second["rol"] = "2.ª portada"
    for r in body:
        r["rol"] = next((x for x in r["roles"] if x != "portada"), "desarrollo")
    if closer:
        closer["rol"] = "cierre"
    alts = [r for r in rows if r not in seq][:4]
    for a in alts:
        a["rol"] = "reserva"
    return seq, alts


def clips_for(row, f):
    """Tramos candidatos de un video: los que marcó la evaluación, o los que
    salen de los cortes de escena, sin pasar de tramo_max_seg."""
    a, r = row["a"], row["r"]
    dur = a["duracion"]
    cap = f.get("tramo_max_seg", 6.0)
    out = []
    if r.get("tramos"):
        for t in r["tramos"]:
            t0, t1 = float(t[0]), float(t[1])
            label = t[2] if len(t) > 2 else ""
            if t1 > t0:
                out.append((t0, min(t1, dur), label))
    else:
        cuts = [0.0] + [c for c in a.get("cortes", []) if 0.3 < c < dur - 0.3] + [dur]
        for s, e in zip(cuts, cuts[1:]):
            if e - s >= 0.8:
                out.append((s, min(e, s + cap), "inicio" if s == 0 else ""))
    return out or [(0.0, min(dur, cap), "inicio")]


def select_reel(rows, f, brief, obj):
    d = f["duracion"]
    target = float(brief.get("duracion") or d["defecto"])
    target = max(d["min"], min(d["max"], target))
    vids = [r for r in rows if r["tipo"] == "video"]
    photos = [r for r in rows if r["tipo"] == "foto"]
    warn = []
    if not vids:
        warn.append("No hay video utilizable: un reel hecho solo de fotos fijas casi siempre "
                    "rinde menos que un carrusel con esas mismas fotos.")

    clips = []
    for v in vids:
        for (t0, t1, label) in clips_for(v, f):
            hook = v["r"].get("gancho")
            hook_score = (hook * 10 if isinstance(hook, (int, float)) else 50) * 0.55 \
                + v["a"].get("movimiento_inicio", 0) * 0.15 + v["puntaje"] * 0.30
            clips.append({"row": v, "t0": t0, "t1": t1, "label": label,
                          "hook": hook_score if t0 < 0.5 or label == "gancho" else hook_score - 25,
                          "score": v["puntaje"] + (5 if label in ("gancho", "clave") else 0)})

    seq, total = [], 0.0
    if clips:
        h = max(clips, key=lambda c: c["hook"])
        seq.append(h)
        total += h["t1"] - h["t0"]
        rest = sorted((c for c in clips if c is not h), key=lambda c: -c["score"])
        for c in rest:
            if total >= target:
                break
            if c["score"] < h["row"]["puntaje"] * 0.5:
                continue
            seq.append(c)
            total += c["t1"] - c["t0"]
    spf = f.get("segundos_por_foto", 2.0)
    use_photos = brief.get("fotos_en_reel", True)
    if total < target and photos and use_photos:
        # fotos solo si están a la altura y no repiten una toma que ya sale en video
        ref = seq[0]["row"]["puntaje"] if seq else photos[0]["puntaje"]
        context = list({id(c["row"]): c["row"] for c in seq}.values())
        need = int((target - total) / spf + 0.999)
        extra = mmr(photos, context, 0.4, len(context) + need, ref * 0.65)[len(context):]
        for p in extra:
            if total >= target:
                break
            seq.append({"row": p, "t0": 0.0, "t1": spf, "label": "foto", "score": p["puntaje"]})
            total += spf
    if total < target - 0.5 and not brief.get("duracion"):
        warn.append(f"Con el material fuerte disponible sale un reel de {total:.0f}s. "
                    "Mejor corto y bueno que estirado con relleno.")
    elif total < target - 0.5:
        warn.append(f"Pediste {target:.0f}s y solo hay {total:.0f}s de material a la altura.")
    if total < d["min"]:
        warn.append(f"Solo hay {total:.1f}s de material útil; el mínimo razonable es {d['min']}s.")

    # cuerpo en orden de rodaje (video, tiempo); el gancho se queda primero
    head, body = seq[:1], seq[1:]
    body.sort(key=lambda c: (str(c["row"]["a"].get("fecha")), c["row"]["id"], c["t0"]))
    seq = head + body

    items, used = [], set()
    for i, c in enumerate(seq):
        row = dict(c["row"])
        row["rol"] = "gancho" if i == 0 else ("cierre" if i == len(seq) - 1 and len(seq) > 2 else
                                               ("foto" if c["label"] == "foto" else "desarrollo"))
        row["tramo"] = [round(c["t0"], 2), round(c["t1"], 2)]
        row["duracion"] = round(c["t1"] - c["t0"], 2)
        items.append(row)
        used.add(row["id"])

    # portada: mejor fotograma marcado o sugerido, o la mejor foto para portada
    cover = None
    cands = []
    for v in vids:
        t = v["r"].get("portada_t", v["a"].get("portada_sugerida_t", 0))
        fr = min(v["a"].get("fotogramas", []), key=lambda x: abs(x["t"] - t), default=None)
        cands.append({"id": v["id"], "t": t, "archivo": fr["archivo"] if fr else v["a"]["vista"],
                      "valor": v["portada"] if v["portada"] is not None else v["puntaje"]})
    for p in photos[:5]:
        cands.append({"id": p["id"], "t": None, "archivo": p["a"]["vista"],
                      "valor": (p["portada"] if p["portada"] is not None else p["puntaje"]) - 3})
    if cands:
        cover = max(cands, key=lambda c: c["valor"])
    alts = [r for r in rows if r["id"] not in used][:4]
    for a in alts:
        a["rol"] = "reserva"
    return items, alts, cover, round(total, 1), warn


def select_story(rows, f, brief, obj):
    if not rows:
        return [], []
    q = f["cantidad"]
    n = int(brief.get("cantidad") or q["defecto"])
    n = max(q["min"], min(q["max"], n))
    must = [r for r in rows if r["obligatorio"]]
    chosen = mmr(rows, must, f.get("diversidad", 0.3), n,
                 rows[0]["puntaje"] * f.get("piso_relativo", 0.5))

    def opener(r):
        rr = r["r"]
        return (rr.get("emocion", 5) + rr.get("autenticidad", 5)) * 5 + (15 if r["a"].get("caras") else 0) \
            + 0.3 * r["puntaje"]
    first = max(chosen, key=opener)
    rest = sorted((r for r in chosen if r is not first), key=lambda r: str(r["a"].get("fecha") or ""))
    seq = [first] + rest
    if len(seq) >= 3:
        ask = max(seq[1:], key=lambda r: r["r"].get("espacio_texto", 0) * 10 + 0.2 * r["puntaje"])
        seq.remove(ask)
        pos = min(f.get("posicion_pregunta", 4), len(seq)) - 1
        seq.insert(max(1, pos), ask)
        ask["rol"] = "pregunta / sticker"
    first["rol"] = "apertura"
    for r in seq:
        r.setdefault("rol", "contenido")
        if r.get("rol") in (None, "", "reserva", "alternativa"):
            r["rol"] = "contenido"
    if len(seq) >= 2 and seq[-1]["rol"] == "contenido":
        seq[-1]["rol"] = "cierre"
    for r in seq[1:]:
        if r["rol"] not in ("pregunta / sticker", "cierre"):
            r["rol"] = "contenido"
    alts = [r for r in rows if r not in seq][:4]
    for a in alts:
        a["rol"] = "reserva"
    return seq, alts


# ================================================================ potencial

def potential(items, fmt, obj):
    """Índice comparativo 0-100. La primera pieza (portada, gancho, apertura)
    pesa la mitad porque decide si se ve el resto. Los ajustes estructurales
    son priors explicados en references/engagement.md, no mediciones."""
    if not items:
        return 0.0
    first = items[0]["puntaje"]
    rest = [it["puntaje"] for it in items[1:]]
    base = first if not rest else 0.5 * first + 0.5 * sum(rest) / len(rest)
    if fmt == "carrusel":
        strong = sum(1 for x in rest if x >= 0.85 * first)
        base += min(6.0, 1.5 * strong)          # profundidad: cada deslizamiento cuenta
    elif fmt == "post":
        base -= 3.0                              # una sola oportunidad de interacción
    elif fmt == "reel":
        vids = [it for it in items if it["tipo"] == "video"]
        hook = items[0]["r"].get("gancho") if items[0]["tipo"] == "video" else None
        if vids and isinstance(hook, (int, float)) and hook >= 7:
            base += 4.0                          # arranque fuerte = retención
        if not vids:
            base -= 10.0
    return round(clamp(base * obj["afinidad"].get(fmt, 1.0)), 1)


def level(p):
    return "ALTO" if p >= 72 else ("MEDIO" if p >= 55 else "BAJO")


# 4:5 y 3:4 ocupan más pantalla en el feed que 1:1: pequeña ventaja a igualdad de recorte
RATIO_BONUS = {"4:5": 2.0, "3:4": 2.0, "1:1": 0.0}


def score_post(inv, ev, brief, f, obj, overrides):
    """En un post cada foto puede ir en su mejor proporción."""
    if brief.get("proporcion") in f["medidas"]:
        opts = [brief["proporcion"]]
    else:
        opts = f["proporciones"]
    best, dropped = {}, []
    for r in opts:
        rows, dropped = score_assets(inv, ev, brief, "post", f, obj, overrides, parse_ratio(r))
        for row in rows:
            row["puntaje_prop"] = row["puntaje"] + RATIO_BONUS.get(r, 0)
            row["proporcion"] = r
            if row["id"] not in best or row["puntaje_prop"] > best[row["id"]]["puntaje_prop"]:
                best[row["id"]] = row
    rows = sorted(best.values(), key=lambda x: -x["puntaje"])
    return rows, dropped


def run_format(fmt, inv, ev, brief, fcfg, obj, overrides):
    f = fcfg["formatos"][fmt]
    if fmt == "post":
        rows, dropped = score_post(inv, ev, brief, f, obj, overrides)
        ratio_name = rows[0]["proporcion"] if rows else f["proporciones"][0]
    else:
        ratio_name = pick_ratio(inv, f, brief, ev)
        rows, dropped = score_assets(inv, ev, brief, fmt, f, obj, overrides, parse_ratio(ratio_name))
    extra = {}
    warn = []
    if fmt == "post":
        items, alts = select_post(rows, f, brief)
        if items:
            ratio_name = items[0]["proporcion"]
    elif fmt == "carrusel":
        items, alts = select_carousel(rows, f, brief, obj)
        rec = f["cantidad"].get("recomendado", [1, 99])
        if len(items) < 2:
            warn.append("No hay material suficiente y distinto para un carrusel (mínimo 2 piezas "
                        "que no repitan toma). Mejor un post o un reel.")
        elif len(items) < rec[0]:
            warn.append(f"Solo {len(items)} piezas superan el nivel mínimo; mejor un carrusel corto "
                        "y fuerte que uno largo con relleno.")
    elif fmt == "reel":
        items, alts, cover, total, warn = select_reel(rows, f, brief, obj)
        extra = {"portada": cover, "duracion_total": total}
    else:
        items, alts = select_story(rows, f, brief, obj)
    return {"f": f, "ratio": ratio_name, "rows": rows, "dropped": dropped,
            "items": items, "alts": alts, "extra": extra, "warn": warn,
            "potencial": potential(items, fmt, obj)}


def recommend(inv, ev, brief, fcfg, obj, overrides):
    """Para 'formato: auto': prueba los cuatro y compara."""
    res = {}
    for fmt in FORMATS:
        r = run_format(fmt, inv, ev, brief, fcfg, obj, overrides)
        p = r["potencial"]
        vids = [x for x in r["items"] if x["tipo"] == "video"]
        why = []
        if fmt == "reel" and not vids:
            p *= 0.75
            why.append("sin video real")
        if fmt == "carrusel" and len(r["items"]) < 3:
            p *= 0.8
            why.append("pocas piezas fuertes y distintas")
        if fmt == "post" and len(r["rows"]) > 1:
            gap = r["rows"][0]["puntaje"] - r["rows"][1]["puntaje"]
            if gap > 8:
                p *= 1.06
                why.append(f"una pieza destaca por {gap:.0f} puntos")
        if fmt == "story" and obj["afinidad"].get("story", 1) < 0.8:
            why.append("las historias no llegan a quien no te sigue")
        res[fmt] = {"potencial": round(clamp(p), 1), "razones": why, "_r": r}
    best = max(res, key=lambda k: res[k]["potencial"])
    return best, res


# ================================================================== salida

def pack(it):
    keep = ("id", "tipo", "rol", "puntaje", "visual", "tecnica", "penalizacion", "modo", "foco",
            "perdida_recorte", "caras_cortadas", "portada", "tramo", "duracion", "motivo", "nota",
            "redundancia", "cobertura", "desglose", "proporcion")
    d = {k: it.get(k) for k in keep if it.get(k) is not None}
    d["archivo"] = it["a"]["archivo"]
    d["vista"] = it["a"]["vista"]
    return d


def report(sel, inv):
    L = []
    L.append(f"SELECCIÓN  ·  {sel['formato'].upper()}  ·  {sel['proporcion']} "
             f"({sel['medidas'][0]}x{sel['medidas'][1]})  ·  objetivo: {sel['objetivo']}")
    L.append("=" * 88)
    L.append(f"señal que persigue: {sel['senal_principal']}")
    L.append(f"potencial: {sel['potencial']:.0f}/100 {sel['nivel']}   (índice comparativo, no una predicción)")
    if sel.get("recomendacion_formato"):
        L.append("")
        L.append("FORMATO (auto)")
        for k, v in sorted(sel["recomendacion_formato"].items(), key=lambda kv: -kv[1]["potencial"]):
            mark = "->" if k == sel["formato"] else "  "
            L.append(f"  {mark} {k:9} {v['potencial']:5.1f}  {bar(v['potencial'])}  {'; '.join(v['razones'])}")
    L.append("")
    for i, it in enumerate(sel["seleccion"], 1):
        line = f"{i:>3}. {it['id']:4} {it.get('rol', ''):18} {it['puntaje']:5.1f}  "
        line += f"vis {it['visual']:.0f}" if it.get("visual") is not None else "vis --"
        line += f"  téc {it['tecnica']:.0f}"
        if it.get("tramo"):
            line += f"  {fmt_time(it['tramo'][0])}-{fmt_time(it['tramo'][1])}"
        if it.get("penalizacion"):
            parts = []
            for k, v in (it.get("desglose") or {}).items():
                if k == "recorte":
                    k = f"recorte {it['perdida_recorte'] * 100:.0f}%"
                parts.append(f"{k} -{v:.0f}")
            line += "  [" + ", ".join(parts) + "]"
        L.append(line)
        if it.get("motivo"):
            L.append(f"{'':10}{it['motivo']}")
        if it.get("nota"):
            L.append(f"{'':10}! {it['nota']}")
    if sel.get("portada"):
        c = sel["portada"]
        t = f" en {fmt_time(c['t'])}" if c.get("t") is not None else ""
        L.append(f"\nportada: {c['id']}{t}")
    if sel.get("duracion_total"):
        L.append(f"duración total: {sel['duracion_total']:.1f}s")
    if sel.get("sticker"):
        L.append(f"sticker sugerido (pieza 'pregunta'): {sel['sticker']}")
    if sel["alternativas"]:
        L.append("\nALTERNATIVAS / RESERVA")
        for it in sel["alternativas"]:
            L.append(f"     {it['id']:4} {it['puntaje']:5.1f}  {it.get('motivo', '')[:70]}")
    if sel["descartadas"]:
        L.append("\nDESCARTADAS")
        for d in sel["descartadas"]:
            L.append(f"     {d['id']:4} {d['motivo']}")
    if sel["avisos"]:
        L.append("\nAVISOS")
        for w in sel["avisos"]:
            L.append(f"  - {w}")
    L.append("-" * 88)
    L.append("Nada se ha publicado. Revisa, cambia lo que quieras y aprueba antes de exportar.")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Elige el contenido para la publicación.")
    ap.add_argument("trabajo")
    ap.add_argument("--formato", choices=FORMATS + ("auto",))
    ap.add_argument("--objetivo")
    ap.add_argument("--n", type=int, help="cantidad de piezas (carrusel/story)")
    ap.add_argument("--duracion", type=float, help="segundos objetivo (reel)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    work = Path(a.trabajo)
    inv = load_json(work / "inventario.json")
    brief = load_json(work / "brief.json", default={})
    ev_raw = load_json(work / "evaluacion.json", default={})
    ev = {k.upper(): v for k, v in (ev_raw.get("activos", ev_raw)).items() if isinstance(v, dict)}
    fcfg = load_config("formatos.json")
    ocfg = load_config("objetivos.json")
    overrides = load_overrides()

    if a.formato:
        brief["formato"] = a.formato
    if a.objetivo:
        brief["objetivo"] = a.objetivo
    if a.n:
        brief["cantidad"] = a.n
    if a.duracion:
        brief["duracion"] = a.duracion
    obj_key = norm_objective(brief.get("objetivo"), ocfg)
    obj = ocfg["objetivos"][obj_key]
    fmt = (brief.get("formato") or "auto").lower()
    fmt = {"carousel": "carrusel", "historia": "story", "historias": "story", "stories": "story",
           "publicacion": "post", "foto": "post"}.get(fmt, fmt)

    warn = []
    unrated = [x["id"] for x in inv["activos"] if "error" not in x and x["id"] not in ev]
    if unrated and ev:
        warn.append(f"Sin evaluación visual: {', '.join(unrated[:12])}{'...' if len(unrated) > 12 else ''}. "
                    "Se ordenan solo por técnica y quedan por detrás.")
    if not ev:
        warn.append("No hay evaluacion.json: ranking SOLO técnico. La skill debe mirar las piezas "
                    "y puntuarlas con rubrica.json antes de dar una selección por buena.")

    if any(k != "_nota" for k in overrides):
        warn.append(f"Pesos personalizados activos ({USER_DIR / 'pesos.json'}), aprendidos de tu historial.")

    rec = None
    if fmt == "auto":
        fmt, rec = recommend(inv, ev, brief, fcfg, obj, overrides)
        res = rec[fmt]["_r"]
    elif fmt in FORMATS:
        res = run_format(fmt, inv, ev, brief, fcfg, obj, overrides)
    else:
        sys.exit(f"error: formato '{fmt}' desconocido ({', '.join(FORMATS)}, auto)")

    f = res["f"]
    if fmt == "carrusel":
        vids = [x for x in res["items"] if x["tipo"] == "video"]
        if vids and len(vids) < len(res["items"]):
            warn.append("Carrusel mixto foto+video: todas las piezas se exportan a la misma proporción.")
    low = [x for x in res["items"] if x.get("cobertura", 1) < 0.6 and x.get("visual") is not None]
    if low:
        warn.append(f"Evaluación incompleta (faltan dimensiones clave del formato) en: "
                    f"{', '.join(x['id'] for x in low)}.")
    cut = [x["id"] for x in res["items"] if x.get("caras_cortadas")]
    if cut:
        warn.append(f"El recorte a {res['ratio']} corta caras en {', '.join(cut)}: ajusta 'foco' "
                    "en evaluacion.json o usa otra pieza.")

    sel = {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "formato": fmt, "objetivo": obj_key, "senal_principal": obj["senal_principal"],
        "proporcion": res["ratio"], "medidas": f["medidas"][res["ratio"]],
        "potencial": res["potencial"], "nivel": level(res["potencial"]),
        "brief": brief,
        "seleccion": [pack(x) for x in res["items"]],
        "alternativas": [pack(x) for x in res["alts"]],
        "descartadas": res["dropped"],
        "avisos": warn + res["warn"],
        "zona_segura": f.get("zona_segura"),
    }
    if fmt == "story":
        sel["sticker"] = obj.get("sticker")
    if res["extra"].get("portada"):
        sel["portada"] = res["extra"]["portada"]
        sel["duracion_total"] = res["extra"]["duracion_total"]
    if rec:
        sel["recomendacion_formato"] = {k: {"potencial": v["potencial"], "razones": v["razones"]}
                                        for k, v in rec.items()}

    save_json(work / "seleccion.json", sel)
    txt = report(sel, inv)
    (work / "seleccion.md").write_text("```\n" + txt + "\n```\n", encoding="utf-8")
    if a.json:
        print(json.dumps(sel, ensure_ascii=False, indent=2))
    else:
        print(txt)


RUBRIC = load_config("rubrica.json")

if __name__ == "__main__":
    main()
