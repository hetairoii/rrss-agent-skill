# Historias

No son un feed pequeño. Las ven casi solo quienes ya te siguen, así que su
trabajo no es el alcance sino la cercanía: que respondan, reaccionen y
escriban por mensaje directo. Y es la única superficie donde un toque se
convierte en conversación.

## Qué pesa

`autenticidad` arriba de todo: lo pulido parece anuncio y se pasa de largo.
Luego `relevancia`, `emocion` y `espacio_texto` (cada historia lleva texto o
sticker). La técnica casi no pesa (10 %).

## Secuencia

3 a 7 historias. Por encima de 7, cada toque pierde gente y lo último lo ve
casi nadie, que es justo donde se suele poner la pregunta.

```
1      APERTURA    una cara o unas manos haciendo algo. Texto sobre fondo de color se pasa.
2-3    CONTENIDO   lo que pasó, en el orden en que pasó.
3-4    PREGUNTA    la pieza con más espacio limpio, para el sticker. No en la última.
último CIERRE      el resultado, el "nos vemos el sábado", o el adelanto de mañana.
```

`rank.py` elige la apertura por emoción + autenticidad + caras, ordena el resto
por hora de captura, y coloca la pieza con más `espacio_texto` en la posición
de la pregunta. El sticker sugerido depende del objetivo (`objetivos.json`).

## Fotos horizontales

Recortar 3:2 a 9:16 tira dos tercios de la foto. Cuando la pérdida pasa del 35 %,
la skill usa **relleno**: la foto entera sobre un fondo difuminado de sí misma.
Se nota menos inmersivo pero no destroza la imagen, y deja arriba y abajo el
espacio para texto.

## Videos

Hasta 60 s por historia; si es más largo, se recorta y se avisa. En historias
el arranque importa menos que en un reel (quien está ahí ya te sigue), pero un
video que empieza en negro sigue perdiendo gente.

## Zona segura (1080x1920)

Nada por encima de y=250 (la fila del perfil) ni por debajo de y=1600 (la barra
de respuesta). Las líneas rojas de la vista previa lo marcan.
