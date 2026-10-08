# Engagement: qué persigue la skill y qué no puede saber

## Las señales

Instagram no publica su fórmula, pero su responsable, Adam Mosseri, ha
repetido públicamente (2024-2025) cuáles pesan más: el **tiempo de
visualización**, los **me gusta por alcance** (sobre todo con quien ya te
sigue) y los **envíos por alcance** (sobre todo con quien no te sigue). Guardados,
comentarios y respuestas a historias cuentan también, con distinto peso según la
superficie. Y en 2025 reforzó que el contenido original se distribuye más y
que lo reciclado (reposts, marcas de agua de otras apps) se distribuye menos.

| superficie | lo que más pesa | qué significa al elegir |
| --- | --- | --- |
| Reels | retención, envíos, repeticiones | el arranque manda; algo que alguien le mandaría a un amigo |
| Feed (post, carrusel) | me gusta y guardados por alcance, tiempo en la publicación | portada que frena; carrusel que se desliza hasta el final |
| Historias | respuestas, reacciones, toques en stickers | autenticidad y una pregunta fácil de contestar |
| Explorar | interacción prevista de desconocidos | impacto y originalidad |

Cada objetivo (`config/objetivos.json`) dice qué señal persigue, y mueve los
pesos de la rúbrica hacia lo que la produce: envíos piden emoción e impacto;
guardados piden claridad y secuencia; conversión pide que el producto se entienda.

## Cómo se calcula el "potencial"

1. Cada pieza recibe un puntaje: la rúbrica visual pesada por formato y
   objetivo, mezclada con la técnica, menos lo que cuesta el recorte.
2. El potencial de la selección es la mitad la primera pieza (portada, gancho o
   apertura, que decide si se ve el resto) y la mitad la media del resto.
3. Ajustes estructurales, que son priors y no mediciones:
   - carrusel: hasta +6 si tiene varias piezas casi tan fuertes como la portada
     (profundidad = más deslizamientos);
   - post: -3 (una sola oportunidad de interacción);
   - reel: +4 si hay video real con gancho de 7 o más; -10 si es solo de fotos.
4. Se multiplica por la afinidad del formato con el objetivo (las historias
   apenas sirven para alcance, el carrusel es fuerte en guardados...).

ALTO a partir de 72, MEDIO de 55 a 72, BAJO por debajo.

## Lo que el potencial NO es

- **No es una predicción de visualizaciones.** No sabe cuántos seguidores tiene
  la cuenta, a qué hora se publica, qué música lleva el reel, qué dice el pie, ni
  a quién se lo enseña Instagram esa semana. Eso decide más que la foto.
- **No compara cuentas.** Sirve para elegir entre opciones del mismo lote y para
  ver si un formato encaja mejor que otro con el material que hay.
- **Depende de tu evaluación.** Si la rúbrica se puntúa con desgana, el número
  es ruido con decimales.

La única forma de que el número signifique algo para una cuenta concreta es
cerrar el ciclo: `learn.py registrar`, `learn.py resultados` y, con 8+
publicaciones medidas, `learn.py calibrar`. Después de eso, `learn.py
historial` dice cuánto se parece el potencial a lo que realmente pasó, con un
número (correlación de Spearman), sin adornos.
