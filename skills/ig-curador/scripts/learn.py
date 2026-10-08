#!/usr/bin/env python3
"""
learn.py - cierra el ciclo: qué se publicó, cómo le fue, y qué pesos de la
rúbrica predicen de verdad el rendimiento EN TU CUENTA.

Los pesos de formatos.json y objetivos.json son priors razonables para
cualquiera. Tu audiencia no es cualquiera. Después de unas cuantas
publicaciones medidas, este script compara lo que la skill puntuó con lo que
pasó y propone ajustes (~/.claude/rrss/pesos.json) que rank.py aplica solo.

Comandos
  python3 learn.py registrar TRABAJO                 # al publicar
  python3 learn.py resultados ID --alcance 4200 --envios 61 --guardados 90 \\
        --comentarios 14 --me-gusta 380 [--visitas-perfil 55] [--retencion-3s 64]
  python3 learn.py historial                         # lo publicado y sus números
  python3 learn.py calibrar                          # propone pesos (no aplica)
  python3 learn.py calibrar --aplicar                # escribe pesos.json

Honestidad
  - Con menos de ~8 publicaciones medidas no propone nada: sería ruido.
  - Correlación no es causa. Si los posts con caras rinden más, puede ser por
    las caras o porque esos días publicaste otra cosa. Por eso los ajustes se
    encogen hacia 1.0 cuando hay pocos datos y nunca pasan de +-25 %.
  - La métrica es el rendimiento relativo a la mediana de tu propia cuenta en
    ese formato, no las cifras brutas, que dependen de cuántos te siguen.
"""

import argparse
import json
import math
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import USER_DIR, load_json, save_json, slug  # noqa: E402

HIST = USER_DIR / "historial.jsonl"
DIMS = ["impacto", "sujeto", "emocion", "composicion", "relevancia", "narrativa",
        "marca", "autenticidad", "espacio_texto", "gancho", "ritmo", "audio"]
# un envío cuesta más que un guardado, que cuesta más que un comentario, que cuesta más que un me gusta
WEIGHTS = {"me_gusta": 1, "comentarios": 2, "guardados": 3, "envios": 4}


def read_hist():
    if not HIST.exists():
        return []
    return [json.loads(l) for l in HIST.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_hist(rows):
    HIST.parent.mkdir(parents=True, exist_ok=True)
    HIST.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def cmd_registrar(a):
    work = Path(a.trabajo)
    sel = load_json(work / "seleccion.json")
    ev = load_json(work / "evaluacion.json", default={})
    ev = {k.upper(): v for k, v in ev.get("activos", ev).items() if isinstance(v, dict)}
    brief = sel.get("brief", {})
    pid = f"{a.fecha or date.today().isoformat()}-{slug(brief.get('mensaje') or brief.get('contexto') or sel['formato'], 30)}"
    rows = read_hist()
    if any(r["id"] == pid for r in rows):
        pid += f"-{len(rows) + 1}"
    rows.append({
        "id": pid, "fecha": a.fecha or date.today().isoformat(),
        "formato": sel["formato"], "objetivo": sel["objetivo"], "proporcion": sel["proporcion"],
        "potencial": sel["potencial"], "trabajo": str(work.resolve()),
        "mensaje": brief.get("mensaje") or brief.get("contexto"),
        "piezas": [{"id": it["id"], "rol": it.get("rol"), "puntaje": it.get("puntaje"),
                    "eval": {d: ev.get(it["id"], {}).get(d) for d in DIMS
                             if isinstance(ev.get(it["id"], {}).get(d), (int, float))}}
                   for it in sel["seleccion"]],
        "resultados": None, "nota": a.nota,
    })
    write_hist(rows)
    print(f"registrado: {pid}")
    print(f"cuando tengas números (a las 48-72 h): python3 learn.py resultados {pid} --alcance N ...")


def cmd_resultados(a):
    rows = read_hist()
    hit = [r for r in rows if r["id"] == a.id or r["id"].startswith(a.id)]
    if len(hit) != 1:
        sys.exit(f"error: {'no encuentro' if not hit else 'ambiguo'} '{a.id}'. Usa `historial`.")
    res = {k: v for k, v in {
        "alcance": a.alcance, "me_gusta": a.me_gusta, "comentarios": a.comentarios,
        "guardados": a.guardados, "envios": a.envios, "visitas_perfil": a.visitas_perfil,
        "seguidores": a.seguidores, "reproducciones": a.reproducciones,
        "retencion_3s": a.retencion_3s, "no_seguidores_pct": a.no_seguidores}.items() if v is not None}
    if not res.get("alcance"):
        sys.exit("error: --alcance es obligatorio (todo se mide por alcance)")
    hit[0]["resultados"] = res
    write_hist(rows)
    print(f"resultados guardados en {hit[0]['id']}: {res}")


def engagement(res):
    reach = max(1, res["alcance"])
    return sum(WEIGHTS[k] * res.get(k, 0) for k in WEIGHTS) / reach


def outliers(rows):
    """Rendimiento / mediana de la cuenta en el mismo formato."""
    by = {}
    for r in rows:
        by.setdefault(r["formato"], []).append(engagement(r["resultados"]))
    meds = {k: statistics.median(v) for k, v in by.items()}
    for r in rows:
        m = meds[r["formato"]] or 1e-9
        r["_mult"] = engagement(r["resultados"]) / m if m > 0 else 1.0
    return rows


def spearman(x, y):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                rk[order[k]] = (i + j) / 2
            i = j + 1
        return rk
    if len(x) < 3:
        return 0.0
    rx, ry = ranks(x), ranks(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


def cmd_historial(a):
    rows = read_hist()
    if not rows:
        print("historial vacío. Registra publicaciones con `learn.py registrar TRABAJO`.")
        return
    done = outliers([r for r in rows if r.get("resultados")])
    mult = {r["id"]: r["_mult"] for r in done}
    print(f"{'id':42} {'formato':9} {'objetivo':11} {'potencial':>9} {'rend.':>7}")
    for r in rows:
        m = mult.get(r["id"])
        print(f"{r['id'][:42]:42} {r['formato']:9} {r['objetivo']:11} {r['potencial']:9.0f} "
              f"{(f'{m:.2f}x' if m is not None else 'pend.'):>7}")
    if len(done) >= 5:
        rho = spearman([r["potencial"] for r in done], [math.log(r["_mult"] + 1e-9) for r in done])
        print(f"\n¿el 'potencial' predice tu rendimiento? Spearman = {rho:+.2f} con n={len(done)} "
              "(0 = nada, 1 = perfecto)")


def cmd_calibrar(a):
    done = [r for r in read_hist() if r.get("resultados")]
    if len(done) < a.min:
        print(f"Solo {len(done)} publicaciones medidas. Hacen falta al menos {a.min} para que un "
              "ajuste sea algo más que ruido. Los pesos por defecto siguen activos.")
        return
    done = outliers(done)
    sug, table = {}, []
    scopes = {"*": done}
    for fmt in {r["formato"] for r in done}:
        sub = [r for r in done if r["formato"] == fmt]
        if len(sub) >= a.min:
            scopes[fmt] = sub
    for scope, rows in scopes.items():
        sug[scope] = {}
        n = len(rows)
        y = [math.log(r["_mult"] + 1e-9) for r in rows]
        for d in DIMS:
            # lo que decide es la primera pieza (portada, gancho, apertura)
            pairs = [(r["piezas"][0]["eval"].get(d), yy) for r, yy in zip(rows, y)
                     if r["piezas"] and r["piezas"][0]["eval"].get(d) is not None]
            if len(pairs) < a.min:
                continue
            rho = spearman([p[0] for p in pairs], [p[1] for p in pairs])
            shrunk = rho * len(pairs) / (len(pairs) + 8)
            m = round(max(0.75, min(1.25, 1 + 0.6 * shrunk)), 2)
            table.append((scope, d, len(pairs), rho, m))
            if abs(m - 1) >= 0.03:
                sug[scope][d] = m
        if not sug[scope]:
            del sug[scope]
    print(f"CALIBRACIÓN  ·  {len(done)} publicaciones medidas")
    print(f"{'ámbito':9} {'dimensión':14} {'n':>3} {'rho':>6}  multiplicador")
    for scope, d, n, rho, m in sorted(table, key=lambda t: (t[0], -abs(t[3]))):
        print(f"{scope:9} {d:14} {n:3d} {rho:+6.2f}  x{m:.2f}{'' if abs(m - 1) >= 0.03 else '  (sin cambio)'}")
    out = USER_DIR / ("pesos.json" if a.aplicar else "pesos_sugeridos.json")
    sug["_nota"] = ("Generado por learn.py calibrar a partir de tu historial. "
                    "Multiplica los pesos de formatos.json. Bórralo para volver a los valores por defecto.")
    save_json(out, sug)
    print(f"\n{'aplicado' if a.aplicar else 'propuesta escrita'}: {out}")
    if not a.aplicar:
        print("Revísala con el usuario y vuelve a correr con --aplicar si está de acuerdo.")


def main():
    ap = argparse.ArgumentParser(description="Aprende de los resultados publicados.")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("registrar")
    p.add_argument("trabajo")
    p.add_argument("--fecha")
    p.add_argument("--nota")
    p = sp.add_parser("resultados")
    p.add_argument("id")
    for flag in ("alcance", "me-gusta", "comentarios", "guardados", "envios", "visitas-perfil",
                 "seguidores", "reproducciones"):
        p.add_argument(f"--{flag}", type=int)
    p.add_argument("--retencion-3s", type=float, help="porcentaje que sigue a los 3 s")
    p.add_argument("--no-seguidores", type=float, help="% del alcance que no te sigue")
    sp.add_parser("historial")
    p = sp.add_parser("calibrar")
    p.add_argument("--min", type=int, default=8)
    p.add_argument("--aplicar", action="store_true")
    a = ap.parse_args()
    {"registrar": cmd_registrar, "resultados": cmd_resultados,
     "historial": cmd_historial, "calibrar": cmd_calibrar}[a.cmd](a)


if __name__ == "__main__":
    main()
