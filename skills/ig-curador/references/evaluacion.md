# evaluacion.json

Lo que viste, en un formato que `rank.py` puede pesar. Una entrada por pieza
que hayas mirado. Las que no evalúes se ordenan solo por técnica y quedan por
detrás (el informe lo avisa).

```json
{
  "F07": {
    "impacto": 8, "sujeto": 8, "emocion": 9, "composicion": 7, "relevancia": 9,
    "narrativa": 7, "marca": 8, "autenticidad": 9, "espacio_texto": 4,
    "roles": ["persona", "portada"],
    "foco": [0.42, 0.31],
    "motivo": "La barista sirviendo y mirando a cámara: presenta el local con una cara.",
    "alt": "Una barista sonriente sirve un espresso en la barra de madera del local."
  },
  "F09": { "descartar": true, "motivo": "Ojos cerrados." },
  "F15": { "impacto": 7, "sujeto": 7, "emocion": 8, "composicion": 6, "relevancia": 9,
           "narrativa": 4, "marca": 7, "autenticidad": 8, "espacio_texto": 3,
           "roles": ["persona"], "mismo_momento": ["F07"],
           "motivo": "Mismo momento que F07, encuadre peor." },
  "V02": {
    "impacto": 8, "sujeto": 7, "emocion": 6, "composicion": 7, "relevancia": 9,
    "narrativa": 8, "marca": 8, "autenticidad": 8, "espacio_texto": 5,
    "gancho": 8, "ritmo": 6, "audio": 7,
    "roles": ["proceso"],
    "tramos": [[0.0, 2.8, "gancho"], [6.5, 11.0, "clave"], [14.2, 17.0, "cierre"]],
    "portada_t": 7.1,
    "motivo": "La leche cayendo en cámara lenta desde el primer fotograma; 3-6 s es tiempo muerto."
  }
}
```

| campo | tipo | para qué |
| --- | --- | --- |
| dimensiones | 0-10 | Las de `config/rubrica.json`. `gancho`, `ritmo`, `audio` solo en video. Puedes omitir alguna si no aplica; el informe avisa si faltan las que más pesan en el formato. |
| `roles` | lista | `portada`, `contexto`, `proceso`, `detalle`, `persona`, `producto`, `resultado`, `cierre`, `pregunta`. Ordenan el carrusel y la historia. |
| `motivo` | texto | Una frase que el usuario leerá. Concreta: qué se ve y por qué sirve o no. |
| `foco` | [x, y] 0-1 | Dónde centrar el recorte. Por defecto: la cara más grande o lo más llamativo según el análisis. Ponlo cuando el sujeto no esté donde el detector cree (un plato, un cartel, la persona de espaldas). |
| `descartar` | bool | Fuera de cualquier selección (salvo `debe_incluir`). Siempre con `motivo`. |
| `mismo_momento` | lista de ids | Piezas que cuentan lo mismo aunque no sean la misma toma. Evita que el carrusel repita escena. |
| `tramos` | [[t0, t1, etiqueta]] | Video: los trozos que valen, en segundos. Etiquetas útiles: `gancho`, `clave`, `cierre`. Sin tramos, se cortan por escenas. |
| `portada_t` | segundos | Video: el fotograma que serviría de portada. |
| `alt` | texto | Texto alternativo para lectores de pantalla; va al `LEEME.txt`. Describe lo que se ve, no lo que vende. |

## Calibrar la escala

Antes de escribir, ordena mentalmente las candidatas de mejor a peor en cada
dimensión que importa al formato y reparte los números de acuerdo con ese
orden. Señales de que la evaluación no está separando:

- La mitad de las piezas tienen el mismo número en `impacto`.
- Ninguna baja de 6 en `relevancia` aunque haya fotos de otro tema.
- Una ráfaga entera con las mismas notas: elige la mejor y baja el resto o
  márcalas `mismo_momento`.
