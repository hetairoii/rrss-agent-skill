# brief.json

El brief es la traducción del contexto del usuario a algo que el ranking puede
usar. Todo lo que no esté aquí, el ranking no lo sabe.

```json
{
  "contexto": "Cafetería de especialidad que abre este sábado en el barrio.",
  "objetivo": "anuncio",
  "formato": "auto",
  "mensaje": "Abrimos el sábado: espresso de especialidad y una barista que te lo explica",
  "audiencia": "vecinos de 25 a 40 que trabajan en remoto",
  "tono": "cercano, sin postureo",
  "cta": "Guarda la fecha y ven el sábado",
  "orden": "narrativo",
  "cantidad": null,
  "duracion": null,
  "proporcion": null,
  "debe_incluir": [],
  "excluir": [],
  "fotos_en_reel": true,
  "restricciones": "No sale la fachada del vecino. El logo aún no es definitivo."
}
```

| campo | obligatorio | qué hace |
| --- | --- | --- |
| `objetivo` | sí | Cambia los pesos y la señal que se persigue. Ver tabla abajo. |
| `mensaje` | sí | Lo que quien lo vea tiene que entender. Es contra lo que puntúas `relevancia`. |
| `formato` | no | `post`, `carrusel`, `reel`, `story` o `auto` (por defecto). |
| `contexto`, `audiencia`, `tono`, `cta` | no | Te sirven a ti al evaluar y al escribir el texto. |
| `orden` | no | Carrusel: `narrativo` (por roles), `cronologico` (por hora de captura) o `impacto`. Si falta, lo decide el objetivo. |
| `cantidad` | no | Piezas en carrusel o historias. Si falta: 7 y 5. Es un máximo: si no hay tantas buenas, sale menos. |
| `duracion` | no | Segundos objetivo del reel. Si falta, 20, y si no hay material a la altura sale más corto. |
| `proporcion` | no | Fuerza `4:5`, `1:1` o `3:4` en feed. Si falta, se elige la que menos destroza el material. |
| `debe_incluir` | no | Ids que van sí o sí (la foto del cliente, el producto nuevo). |
| `excluir` | no | Ids que no van, por la razón que sea. |
| `fotos_en_reel` | no | `false` para un reel solo de video. |

## Del contexto al objetivo

| lo que dice el usuario | objetivo |
| --- | --- |
| "que nos conozca más gente", "crecer", "que se haga viral" | `alcance` |
| "que la gente comente", "abrir conversación", "engagement" | `interaccion` |
| "un tutorial", "tips", "algo útil", "que lo guarden" | `guardados` |
| "vender", "reservas", "que escriban", "que entren al link" | `conversion` |
| "mostrar el equipo", "detrás de cámaras", "conectar con los que ya nos siguen" | `comunidad` |
| "anunciar", "evento", "lanzamiento", "abrimos", "nueva colección" | `anuncio` |

Si caben dos, elige el que decide qué foto gana. "Anunciar la apertura para
que venga gente" es `anuncio` (la fecha y el lugar tienen que entenderse);
"que la gente se enamore del local" es `alcance` o `comunidad`.

## Cuándo preguntar

Solo si no puedes escribir `objetivo` y `mensaje` con lo que hay. Una pregunta
agrupada, por ejemplo:

> Antes de elegir: ¿qué quieres que pase con esta publicación (que venga gente
> el sábado, que os conozcan, vender algo concreto...) y qué tiene que entender
> alguien que la vea en 2 segundos? Si ya sabes el formato, dímelo; si no, lo
> decido con el material.

Todo lo demás se deduce o se queda en su valor por defecto, y lo dices en una
línea ("Lo leo como anuncio, formato a decidir con el material").
