# rrss-agent · gestor de redes sociales para Claude

Empieza por la parte que nadie automatiza bien: **qué foto subo**.

Le das a Claude una carpeta con las fotos y videos de un evento, un producto o
un día de trabajo, y le dices qué quieres lograr ("anunciar que abrimos el
sábado", "que nos conozca más gente", "vender la colección nueva"). La skill
mira todo, descarta lo roto y lo repetido, puntúa cada pieza contra ese
objetivo, decide el formato si no lo diste, elige portada, ordena la secuencia
y te deja los archivos recortados a la medida exacta de Instagram.

**Nada se publica hasta que tú lo subes.** La skill elige y exporta. Tú posteas.

```
/ig-curador  estas son las fotos de la inauguración (./fotos). Quiero que la
             gente del barrio venga el sábado.
```

```
CARRUSEL  ·  6 piezas  ·  4:5  ·  objetivo: anuncio  ·  potencial 78 ALTO

1  F07  portada     la barista sirviendo, mirada a cámara: frena y presenta
2  F12  2.ª portada el espresso de cerca: el producto, por si entra desde aquí
3  F03  contexto    el local desde la puerta: dónde es
4  V02  proceso     0:06-0:11 la leche cayendo, el único video con movimiento real
5  F19  persona     el equipo detrás de la barra
6  F21  cierre      fachada con espacio arriba para "Sábado 10:00"

Fuera:   F04 movida · F09 ojos cerrados · F15-F18 ráfaga de F07 · F11 fuera de tema
Reserva: F14 (si prefieres abrir con producto), F02
```

Inspirado en [instagram-agent-skill](https://github.com/Jakeschincariol/instagram-agent-skill)
de Jake Schincariol (MIT): mismo espíritu (una skill, sin app, sin API, sin
cuenta que conectar, scripts locales que miden de verdad, honestidad sobre lo
que no se puede saber) aplicado al problema que ese pack no toca: **el
material visual**.

## En qué se diferencia del repo de referencia

| | instagram-agent-skill | rrss-agent |
| --- | --- | --- |
| Trabaja sobre | texto: guiones, ganchos, pies, DMs | fotos y videos: qué subir, en qué orden, con qué recorte |
| Contexto | la idea del post | un brief con objetivo, mensaje, audiencia, formato y restricciones |
| Formatos | una skill por formato, independientes | un solo flujo que cambia criterio por formato y puede **elegir el formato** comparando los cuatro con el material real |
| Medición local | ganchos, duración, pies, "humanizer" | nitidez del sujeto, exposición, ruido, caras, punto focal, ráfagas, misma toma aunque esté recortada, cortes de escena, arranque del video, audio |
| Juicio | heurísticas sobre texto | rúbrica visual de 12 dimensiones con anclas, que Claude aplica mirando las piezas, pesada por formato y objetivo |
| Secuencias | — | diversidad (no repite tomas), portada y 2.ª portada, orden narrativo/cronológico/impacto, posición del sticker, línea de tiempo de reel |
| Salida | bloques de texto para copiar | archivos numerados a 1080 px, sRGB, sin GPS, con relleno difuminado cuando recortar destrozaría la foto, tramos y borrador de reel |
| Aprende | registra lo publicado | registra, guarda resultados y **recalibra los pesos con tus números** (`learn.py calibrar`) |

Se complementan: este pack elige el material; `/ig-caption` y `/ig-reel` del
otro escriben el texto. Si están los dos instalados, `/ig-curador` le pasa el
brief a `/ig-caption` al final.

## Instalar

Pega esto en Claude:

```
<url de este repo>

Instala esta skill y confirma que /ig-curador funciona.
```

O a mano, en Claude Code:

```bash
git clone <url de este repo> rrss-agent-skill
cp -r rrss-agent-skill/skills/ig-curador ~/.claude/skills/
pip install pillow numpy opencv-python-headless   # + pillow-heif si usas iPhone
# y ffmpeg: brew install ffmpeg  /  sudo apt install ffmpeg  /  winget install ffmpeg
```

O como plugin:

```
/plugin marketplace add <usuario>/rrss-agent-skill
/plugin install rrss-agent
```

En claude.ai (app de escritorio o web) también funciona: sube la carpeta
`skills/ig-curador` como skill, o simplemente adjunta las fotos y pega el
`SKILL.md` al principio del chat. Los scripts corren en el entorno de Claude.

Luego dedica diez minutos a `templates/marca.md`. Cópialo a
`~/.claude/rrss/marca.md` y rellénalo, o pásale a Claude 6-9 publicaciones tuyas
y dile "escribe mi marca.md a partir de estas".

## Cómo trabaja

```
contexto ──> brief.json
carpeta  ──> scan.py ──> inventario.json  (técnica, caras, ráfagas, misma toma, videos)
                    └──> contact.py ──> hojas de contacto ──> Claude MIRA
                                                              └──> evaluacion.json (rúbrica)
brief + inventario + evaluación ──> rank.py ──> seleccion.json  (+ formato si era "auto")
                                         └──> contact.py --seleccion ──> vista previa ──> TÚ APRUEBAS
                                                                         └──> export.py ──> listo/
publicado ──> learn.py registrar ──> resultados ──> calibrar ──> pesos.json
```

### Los cuatro formatos

| formato | qué busca | cómo elige |
| --- | --- | --- |
| **post** | una imagen que se entiende sola en miniatura | la mejor, cada foto en su mejor proporción (4:5 / 3:4 / 1:1), 3 alternativas distintas entre sí |
| **carrusel** | permanencia: que se deslice hasta el final | portada propia, 2.ª portada, diversidad, orden narrativo / cronológico / impacto, cierre; corta antes que rellenar |
| **reel** | retención desde el primer segundo | el mejor arranque primero, tramos ≤ 6 s, fotos solo si están a la altura, portada comprobada para la cuadrícula |
| **story** | respuestas de quien ya te sigue | apertura con persona, orden del día, pieza con espacio para el sticker en la posición 3-4, relleno difuminado en vez de recorte destructivo |

### Los seis objetivos

`alcance` (envíos y retención) · `interaccion` (comentarios) · `guardados` ·
`conversion` (visitas al perfil, enlace, mensajes) · `comunidad` (respuestas a
historias) · `anuncio` (que se entienda qué, cuándo y dónde). Cada uno mueve
los pesos de la rúbrica y la afinidad con cada formato
([`objetivos.json`](skills/ig-curador/config/objetivos.json)).

### Las herramientas que corren

Todo local. Nada se sube a ningún sitio.

```bash
python3 scan.py ./fotos --out ./trabajo           # inventario técnico
python3 contact.py ./trabajo                      # hojas de 12 miniaturas
python3 contact.py ./trabajo --video V01          # tira de fotogramas
python3 rank.py ./trabajo [--formato auto]        # selección
python3 contact.py ./trabajo --seleccion          # vista previa con recortes reales
python3 export.py ./trabajo                       # archivos listos
python3 learn.py calibrar                         # pesos ajustados a tu cuenta
```

Ejemplo real de `scan.py` sobre el lote de prueba:

```
INVENTARIO  ·  11 fotos  ·  2 videos  ·  2 grupos de ráfaga/duplicado  ·  9.5s
id   técnica                       prop.  orient.    extra          archivo
F01     93.5  ###################. 4:5    vertical   1.7MP 1cara    IMG_1001_retrato.jpg [G1*] ~F02,F11,V01
F03     97.3  ###################. 3:2    horizontal 3.8MP          IMG_1003_cafe.jpg [G2*] ~F04,F05,F10
F04     52.6  ###########......... 3:2    horizontal 3.8MP          IMG_1004_cafe_movida.jpg [G2]
              - desenfocada o movida
F10     80.5  ################.... 9:16   vertical   1.4MP          IMG_1010_cafe_vertical.jpg ~F03,F04,F05
              - resolución baja (900px de lado corto)
V01     96.9  ###################. 9:16   vertical   9.0s 1cara     VID_2001_vertical.mp4
```

`~F03` en F10 es la detección de "misma toma": F10 es un recorte vertical de
F03. El hash perceptual no lo ve (distancia 33 de 64, como dos fotos sin
relación); el emparejamiento de puntos ORB con homografía sí. Sin esto, un
carrusel puede salir con la misma taza dos veces.

## La parte honesta

**La skill no predice visualizaciones.** El "potencial" compara opciones del
mismo lote para la misma cuenta. No sabe tu número de seguidores, la hora, la
música, el pie ni a quién se lo enseña Instagram esa semana, que deciden más
que la foto. [`engagement.md`](skills/ig-curador/references/engagement.md)
explica cómo se calcula, con los priors a la vista.

**El juicio es de Claude, guiado por una rúbrica.** Los scripts no saben si una
foto es bonita ni si cuenta el mensaje. Saben si está movida, si una cara queda
cortada al pasar a 4:5 y si dos archivos son la misma toma. La skill obliga a
mirar las piezas antes de rankear; sin `evaluacion.json`, el ranking sale como
"solo técnico" y lo dice.

**Las métricas técnicas son heurísticas.** La nitidez se mide en la zona más
nítida (percentil 85 de una rejilla 4x4) para no castigar un fondo desenfocado
a propósito, pero una foto movida con intención seguirá saliendo como
"desenfocada". Es un aviso, no una sentencia.

**Aprende solo con datos.** `learn.py calibrar` no propone nada con menos de 8
publicaciones medidas, encoge los ajustes hacia 1.0 cuando hay pocos datos y
nunca mueve un peso más de un 25 %. Correlación no es causa, y el informe lo
recuerda.

**No publica, no programa, no hace scraping.** La API oficial de publicación
existe para cuentas profesionales y necesita una app de Meta revisada; todo lo
demás que automatiza publicaciones va contra los términos de Instagram. Así que
el final es siempre el mismo: una carpeta con archivos en orden y un `LEEME.txt`.

**Las cifras de plataforma caducan.** Medidas, límites y zonas seguras están en
[`formatos.json`](skills/ig-curador/config/formatos.json) con fecha de
verificación (2026-10). Si Instagram cambia, se corrige ese archivo, no el código.

## Siguientes plataformas

La lógica no es de Instagram: es brief → inventario → mirada → rúbrica →
selección por formato → exportación. Añadir TikTok, LinkedIn o Facebook es
sobre todo un `formatos.json` nuevo (medidas, pesos, señales) y un
`references/` por formato. La estructura está pensada para eso.

## Archivos

```
skills/ig-curador/SKILL.md                 el flujo que sigue Claude
skills/ig-curador/scripts/scan.py          inventario técnico de fotos y videos
skills/ig-curador/scripts/contact.py       hojas de contacto, tiras de video, vista previa
skills/ig-curador/scripts/rank.py          puntuación, selección por formato, potencial
skills/ig-curador/scripts/export.py        recorte/relleno a medida, tramos, montaje
skills/ig-curador/scripts/learn.py         historial, resultados, calibración
skills/ig-curador/scripts/common.py        geometría de recorte y similitud
skills/ig-curador/config/rubrica.json      12 dimensiones, anclas 2/5/8/10, roles, descartes
skills/ig-curador/config/formatos.json     medidas y criterio de cada formato
skills/ig-curador/config/objetivos.json    6 objetivos y cómo mueven los pesos
skills/ig-curador/config/face_detection_yunet_2023mar.onnx
                                           detector de caras YuNet (OpenCV Zoo, MIT)
skills/ig-curador/references/              brief, evaluación, un archivo por formato, engagement
templates/marca.md                         tu identidad visual. Rellénalo primero.
```

## Licencia

MIT. Inspirado en instagram-agent-skill de Jake Schincariol (MIT). El modelo
YuNet es de OpenCV Zoo (MIT).
