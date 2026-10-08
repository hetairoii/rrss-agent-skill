---
name: ig-curador
description: >-
  Elige qué fotos y videos publicar en Instagram a partir del contexto de la
  publicación: lee el objetivo, mira todo el material, descarta lo roto y lo
  repetido, puntúa cada pieza con una rúbrica visual, decide el formato
  (post, carrusel, reel o historias) si no se indica, ordena la secuencia,
  elige portada y deja los archivos recortados a medida. Úsala cuando el
  usuario tenga una carpeta o un grupo de fotos/videos y pregunte "¿cuáles
  subo?", "elige las mejores", "arma un carrusel con esto", "haz un reel con
  estos videos", "qué pongo en stories", "selecciona para Instagram", o
  cuando diga qué quiere lograr con una publicación y tenga material.
---

# ig-curador

Del montón de fotos y videos a la selección que mejor sirve a ESTA publicación,
en ESTE formato, para ESTE objetivo. Y nada se publica: la skill elige, ordena
y exporta; el usuario sube.

La elección la hace tu mirada, guiada por una rúbrica. Los scripts hacen lo
que los ojos hacen mal o lento: medir nitidez y exposición, encontrar ráfagas
y recortes de la misma toma, calcular qué se pierde al llevar una foto a 4:5 o
9:16, mantener la diversidad de un carrusel y ser consistente entre lotes.

`SKILL` en los comandos es la carpeta donde está este archivo.

```bash
python3 SKILL/scripts/scan.py CARPETA --out TRABAJO       # 1. inventario técnico
python3 SKILL/scripts/contact.py TRABAJO                  # 2. hojas de contacto
python3 SKILL/scripts/contact.py TRABAJO --video V01      #    tira de fotogramas
python3 SKILL/scripts/rank.py TRABAJO                     # 4. selección
python3 SKILL/scripts/contact.py TRABAJO --seleccion      # 5. vista previa
python3 SKILL/scripts/export.py TRABAJO                   # 6. archivos listos
python3 SKILL/scripts/learn.py registrar TRABAJO          # 7. historial
```

Dependencias: Python 3.9+, `pillow` y `numpy`. Recomendadas:
`opencv-python-headless` (caras y detección de la misma toma) y `ffmpeg`
(cualquier video). `pillow-heif` si hay fotos HEIC de iPhone. Si falta algo,
instálalo con pip antes de empezar y dilo en una línea.

## Archivos del usuario

En `~/.claude/rrss/` (créalo si no existe):

- `marca.md`: la identidad de la cuenta: estética, paleta, quién puede salir y
  quién no, lo que nunca se muestra. Léelo siempre. Si no existe, sigue sin él,
  y al final ofrece en una línea crearlo desde `templates/marca.md` del repo o a
  partir de 6-9 publicaciones que el usuario considere "muy suyas".
- `pesos.json`: ajustes aprendidos de sus resultados. `rank.py` lo aplica solo.
- `historial.jsonl`: lo publicado y cómo le fue.

## El flujo

### 1. El brief

Saca de la conversación lo que la publicación tiene que lograr y escríbelo en
`TRABAJO/brief.json`. TRABAJO es `./rrss-trabajo/AAAA-MM-DD-tema/` salvo que el
usuario diga otra cosa. Esquema y ejemplos en `references/brief.md`.

Lo imprescindible es el **objetivo** (alcance, interaccion, guardados,
conversion, comunidad, anuncio) y el **mensaje** en una frase. Si el usuario
ya lo dijo o se deduce, no preguntes: escribe tu lectura en una línea y sigue.
Si de verdad no se puede deducir, haz UNA pregunta agrupada (qué quieres
lograr, qué tiene que entender quien lo vea, formato si ya lo tienes decidido)
y no más.

Formato: si el usuario lo nombra, ese. Si no, `"auto"`: la skill compara los
cuatro con el material real y recomienda.

### 2. El inventario

```bash
python3 SKILL/scripts/scan.py CARPETA --out TRABAJO
```

Te da una tabla: id (F01 fotos, V01 videos), calidad técnica, proporción,
caras, ráfagas (`[G1*]`, el asterisco es la mejor técnicamente) y "misma toma"
(`~F03`: recortes o reexposiciones de la misma foto). Los avisos (desenfocada,
quemada, baja resolución, sin audio, arranque borroso) son pistas, no
veredictos: una foto movida puede ser la mejor del día.

### 3. Mirar

Esta es la parte que no se puede saltar. Un ranking sin mirar las piezas es
un ranking técnico, y la técnica no sabe si la foto cuenta lo que el brief pide.

1. `contact.py TRABAJO` y **mira cada hoja** con Read. 12 miniaturas por hoja.
   Descarta en bloque lo que obviamente no sirve y apunta candidatas.
2. **Mira a tamaño completo** las candidatas reales (`TRABAJO/vistas/ID.jpg`):
   ojos cerrados, foco en la cara correcta, manos, detalles, texto legible,
   marcas de agua. Hasta ~12; más es desperdiciar contexto.
3. Por cada video candidato, `contact.py TRABAJO --video V01` y mira la tira:
   qué pasa en los primeros 2 segundos, dónde están los tramos buenos, dónde
   hay tiempo muerto, qué fotograma sirve de portada.

Con más de ~80 piezas, trabaja por rondas: hojas → shortlist de 20-25 → vista
completa de las finalistas.

### 4. Evaluar

Antes de puntuar, lee `references/FORMATO.md` (post, carrusel, reel o story),
porque cambia lo que importa, y ten a mano `config/rubrica.json`.

Escribe `TRABAJO/evaluacion.json`, esquema completo en
`references/evaluacion.md`. Por cada pieza que viste: las dimensiones de la
rúbrica de 0 a 10, `roles`, `motivo` (una frase que el usuario pueda leer), y
cuando haga falta `foco` (dónde centrar el recorte), `descartar` con motivo,
`mismo_momento` (piezas que cuentan lo mismo), y en videos `gancho`, `ritmo`,
`audio`, `tramos` y `portada_t`. Añade `alt` (texto alternativo) a las que
probablemente salgan.

Cómo puntuar bien:

- **Comparativo, no absoluto.** La pregunta es cuánto aporta esta pieza, frente
  al resto del lote, a este brief. Si todo sale entre 7 y 8, no estás separando.
- **Relevancia es el puente con el contexto.** Una foto preciosa que no cuenta
  el mensaje lleva relevancia baja, y `rank.py` la frena (por debajo de 4 la
  penaliza un 25 %).
- **Descartes duros** (`rubrica.json → descartes_duros`): ojos cerrados en la
  cara principal, sujeto desenfocado, marca de agua de otra app, menores o
  personas que `marca.md` excluye, datos sensibles visibles, contenido ajeno.
  Se marcan `descartar: true` con el motivo, sin discutir.
- **Las caras con expresión ganan** casi siempre a los objetos en impacto y
  emoción. Pero en conversión manda que el producto se entienda.

### 5. Elegir

```bash
python3 SKILL/scripts/rank.py TRABAJO
```

Combina tu evaluación (pesada según formato y objetivo), la técnica y las
penalizaciones de recorte, y elige según el formato:

| formato | cómo elige |
| --- | --- |
| post | la mejor, cada foto en su mejor proporción (4:5, 3:4 o 1:1), y 3 alternativas distintas entre sí |
| carrusel | portada aparte (la que frena), una 2.ª diapositiva que funcione como segunda portada, relleno con diversidad para no repetir tomas, orden narrativo / cronológico / por impacto y cierre al final. Corta antes que rellenar con piezas flojas |
| reel | el mejor arranque primero, tramos de 6 s máx., fotos solo si están a la altura y no repiten lo que ya sale en video, portada elegida y comprobada para la cuadrícula. Si solo hay fotos, lo dice: un carrusel suele rendir más |
| story | apertura con persona o emoción, contenido en orden del día, la pieza con espacio limpio en la posición 3-4 para el sticker, cierre. Fondo difuminado en vez de recorte cuando 9:16 destrozaría la foto |
| auto | prueba los cuatro con el material real y recomienda uno, explicando por qué |

**Léelo con ojo crítico.** Si el resultado contradice lo que viste (una pieza
floja arriba, la mejor fuera), la causa casi siempre es la evaluación: corrígela
y vuelve a correr. No retoques números para forzar una foto: si crees que debe
ir, `debe_incluir` en el brief existe para eso, y se dice.

El "potencial" (0-100) compara opciones dentro de esta cuenta y este lote. No
es una predicción de visualizaciones: `references/engagement.md` explica de
dónde sale y qué no puede saber.

### 6. Presentar y aprobar

```bash
python3 SKILL/scripts/contact.py TRABAJO --seleccion
```

Envía `TRABAJO/hojas/seleccion.jpg` al usuario: se ve la selección en orden, con
el recorte real y las zonas que tapa la interfaz. Luego un bloque así:

```
CARRUSEL  ·  6 piezas  ·  4:5  ·  objetivo: anuncio  ·  potencial 78 ALTO

1  F07  portada     la barista sirviendo, mirada a cámara: frena y presenta
2  F12  2.ª portada el espresso de cerca: el producto, por si entra desde aquí
3  F03  contexto    el local desde la puerta: dónde es
...
6  F21  cierre      fachada con espacio arriba para "Sábado 10:00"

Fuera:  F04 movida · F09 ojos cerrados · F15-F18 ráfaga de F07 · F11 fuera de tema
Reserva: F14 (si prefieres abrir con producto), F02
Avisos: F12 viene a 900 px, se ve bien en móvil pero no admite más recorte

¿La exporto así, o cambias algo? (orden, portada, quitar/añadir)
```

Cada pieza con su porqué en una línea. Las descartadas agrupadas. Si el
usuario cambia algo, actualiza brief o evaluación, vuelve a correr `rank.py` y
enseña la nueva hoja.

### 7. Exportar, entregar y registrar

Tras el "sí":

```bash
python3 SKILL/scripts/export.py TRABAJO
```

Escribe `TRABAJO/listo/`: archivos numerados en orden de subida, a 1080 px de
ancho, sRGB, sin metadatos (la ubicación GPS no viaja), `LEEME.txt` con orden,
textos alternativos, zona segura y sticker. En reels, además los tramos, un
`reel_borrador.mp4` de referencia y la portada con su vista en la cuadrícula.
Envía los archivos al usuario.

Después ofrece el texto: si existe `/ig-caption` (pack instagram-agent-skill),
pásale el brief y la descripción de la portada; si no, escribe un pie corto
con el gancho en los primeros 125 caracteres, una sola llamada a la acción y
hasta 5 hashtags.

Cuando el usuario confirme que lo publicó: `learn.py registrar TRABAJO`. Si
más adelante comparte números (alcance, envíos, guardados, comentarios...),
`learn.py resultados ID ...`. Con 8+ publicaciones medidas, `learn.py
calibrar` propone pesos ajustados a su audiencia: enséñaselos y aplica solo
si está de acuerdo (`--aplicar`).

## Reglas

- **Nunca publica nada.** No hay API, no hay navegador, no hay "programar". La
  skill entrega archivos y texto. Automatizar publicación fuera de la API
  oficial va contra los términos de Instagram y bloquea cuentas.
- **Nunca inventa.** Ni datos del local, ni testimonios, ni lo que pasa en una
  foto que no viste. Si el brief necesita algo que el material no muestra
  (el precio, la dirección, el horario), dilo: va en el texto o en un rótulo,
  no se inventa una foto.
- **Personas.** Si una foto muestra a alguien reconocible y nada indica que
  tiene permiso (y `marca.md` no lo aclara), señálalo antes de exportar. Con
  menores identificables, descártala salvo indicación explícita.
- **Mejor corto y fuerte que largo con relleno.** Un carrusel de 5 piezas
  buenas gana a uno de 10 con 5 flojas; un reel de 9 s con gancho gana a uno de
  30 s estirado. La skill lo dice en vez de rellenar.
- **Original.** Nada con marcas de agua de otras apps ni contenido ajeno: es lo
  primero que Instagram deja de distribuir.
- **Las cifras de plataforma caducan.** `config/formatos.json` tiene fecha de
  verificación. Si algo choca con lo que Instagram hace hoy, Instagram tiene
  razón y se corrige el archivo.

## Archivos de esta skill

```
scripts/scan.py        inventario técnico: nitidez del sujeto, exposición, ruido, color,
                       caras (YuNet), punto focal, ráfagas, misma toma (ORB), videos:
                       fotogramas, cortes de escena, arranque, audio, portada sugerida
scripts/contact.py     hojas de contacto, tiras de video y vista previa de la selección
scripts/rank.py        puntuación por formato y objetivo, diversidad, orden, potencial
scripts/export.py      recorte/relleno a medida, sRGB, sin metadatos, tramos y montaje
scripts/learn.py       historial, resultados y calibración de pesos
config/rubrica.json    las 12 dimensiones con anclas 2/5/8/10, roles y descartes duros
config/formatos.json   medidas, proporciones, pesos y reglas por formato (verificado 2026-10)
config/objetivos.json  6 objetivos: señal que persiguen y cómo mueven los pesos
references/            brief.md, evaluacion.md, post.md, carrusel.md, reel.md, story.md,
                       engagement.md: léelos cuando el paso lo pida, no todos de golpe
```
