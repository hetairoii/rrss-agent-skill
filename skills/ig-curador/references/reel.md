# Reel

El formato que más llega a gente que no te sigue. Y el que más castiga un mal
arranque: si en los primeros segundos no pasa nada, Instagram deja de
enseñarlo. La retención decide el alcance.

## Qué pesa

`gancho` (los primeros 2 s) es la dimensión que más pesa de toda la skill.
Después `ritmo`, `impacto`, `emocion` y `relevancia`. La técnica pesa poco
(15 %): un video de móvil con algo real pasando gana a uno perfecto y muerto.

## Cómo evaluar un video

Con la tira de fotogramas (`contact.py TRABAJO --video V01`) delante:

1. **El arranque.** Fotogramas marcados ARRANQUE. ¿Hay movimiento, una cara,
   algo ocurriendo desde el primer fotograma? Si el video empieza con alguien
   colocándose, un plano fijo o negro, el `gancho` es bajo, pero el tramo bueno
   puede estar en el segundo 6: márcalo en `tramos` con etiqueta `gancho`.
2. **Los tramos.** Marca solo lo que vale, en segundos. 2 a 6 s por tramo. Los
   cortes de escena detectados (`cortes` en el inventario) son buenos puntos de
   corte.
3. **El tiempo muerto.** Más de 3-4 s sin cambio de plano ni acción es donde la
   gente se va. `ritmo` bajo, y no incluyas ese trozo en `tramos`.
4. **El audio.** Voz clara o sonido con carácter sube `audio`. Viento y ruido lo
   bajan: no descarta el video, pero hay que poner música y decirlo.
5. **La portada.** `portada_t`: un fotograma nítido, con sujeto centrado
   (la cuadrícula del perfil lo recorta) y, si puede ser, con espacio para un
   titular.

## Cómo arma el reel `rank.py`

- Primero el tramo con mejor arranque (gancho + movimiento inicial + puntaje).
- Luego los mejores tramos hasta la duración objetivo, en orden de rodaje.
- Fotos fijas solo si hacen falta, si están a la altura y si no repiten una toma
  que ya sale en video. Cada foto entra 2 s con un acercamiento lento.
- Si no llega a la duración con material bueno, sale más corto y lo dice.
- El último tramo idealmente conecta con el primero (mismo plano, misma
  persona): las repeticiones cuentan como visualización.

## Lo que no hace

No edita: `reel_borrador.mp4` es un corte de referencia para que el usuario vea
la propuesta. La edición final (música, texto en pantalla, transiciones) se
hace en la app que use, exportando **sin marca de agua**: el contenido con
logos de otras plataformas se distribuye menos.

## Si solo hay fotos

Un reel de fotos fijas rara vez gana a un carrusel con las mismas fotos. La
skill lo arma si se lo piden, pero lo avisa y en `auto` no lo recomienda.

## Zona segura (1080x1920)

Nada importante por encima de y=230 ni por debajo de y=1440, y los 230 px de la
derecha libres: ahí van el pie, los botones y el audio. La vista previa marca
estas líneas en rojo.
