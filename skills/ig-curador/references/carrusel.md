# Carrusel

El formato de feed con más tiempo de permanencia: cada deslizamiento es una
interacción. Además Instagram puede volver a enseñarlo a quien no interactuó,
empezando por la segunda diapositiva. Por eso hay dos portadas, no una.

## Qué pesa

`relevancia` y `narrativa` arriba: cada pieza tiene que añadir algo que no
estaba. La portada se elige con su propia mezcla (`pesos_portada`): mucho
`impacto`, `sujeto` claro, algo de `espacio_texto` para un titular.

## Estructura

```
1        PORTADA       la que frena. Cara con expresión o el resultado más vistoso.
2        2.ª PORTADA   tiene que funcionar sola: es por donde entra la segunda oportunidad.
3..N-1   DESARROLLO    una idea por pieza, en el orden que pide el brief:
                       narrativo  contexto -> persona -> proceso -> detalle -> producto -> resultado
                       cronológico  por hora de captura (un evento, un viaje, un día)
                       impacto    de más a menos fuerte (alcance: retener al que llegó)
N        CIERRE        lo que invita a actuar o cierra la historia; mejor si deja espacio
                       para la llamada a la acción.
```

## Lo que hace bueno un carrusel

- **Ninguna pieza repite a otra.** Ráfagas, recortes de la misma toma y
  "mismo momento" se eliminan solos (`rank.py` usa diversidad). Si dos fotos
  cuentan lo mismo desde ángulos distintos, márcalas `mismo_momento` y deja
  que gane la mejor.
- **Variedad de planos.** General, medio, detalle. Tres planos medios seguidos
  cansan aunque cada uno sea bueno.
- **Ritmo de color y luz coherente.** Todas las piezas comparten proporción
  (Instagram obliga) y deberían parecer de la misma publicación.
- **Mejor 5 fuertes que 10 con relleno.** La skill corta cuando las piezas
  bajan del 70 % de la portada, y lo avisa.
- **Video dentro de carrusel** está permitido (hasta 60 s por pieza) y rompe el
  ritmo bien en la posición 3-5. No como portada salvo que su primer fotograma
  sea lo mejor del lote.

## Proporción

Todas iguales. `rank.py` elige la que menos recorta el conjunto, con
preferencia por 4:5. Si la mitad del material es horizontal, puede salir 1:1;
mira la vista previa: si una cara queda cortada, ajusta `foco` o cambia la pieza.

## Cantidad

Hasta 20 piezas. Lo que funciona: 5 a 10. Menos de 3 no arranca el
deslizamiento; más de 10 casi nadie lo termina.
