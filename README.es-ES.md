

# Plateau-obs

Un disyuntor semántico para agentes de IA autónomos. Detecta cuándo un agente ha dejado de aprender, incluso cuando sus acciones siguen cambiando.

## Diseño

Dos controles por turno:

| | **aprendió algo** (novedad ≥ umbral inferior) | **no aprendió nada** (novedad < umbral inferior) |
|---|---|---|
| **confiado** (action_sim ≥ umbral superior) | **GRIND** — trabajo por lotes saludable | **LOOP** — estancamiento clásico (dispara en 3) |
| **no confiado** | **EXPLORE** — investigación abierta | **THRASH** — acciones variadas, sin progreso (dispara en 6) |

La novedad es el eje de disparo. La similitud solo establece el umbral de evidencia. Esa revisión surgió de la medición: tres herramientas genuinamente diferentes (`read_file`, `grep`, `list_dir`) arrojaron un `action_sim` de 0.7397 contra la misma ventana, por lo que MiniLM no tiene una región de baja similitud para cadenas de llamadas a herramientas. Thrash se define únicamente en el eje de novedad.

## Resultados de los fixtures

Prólogo productivo de seis turnos, seguido del patrón bajo prueba. Los cuatro superan la validación:

| Fixture | Cuadrante | Turno de disparo | Sim. acción | Novedad obs. |
|---|---|---|---|---|
| 1 — bucle de paráfrasis | LOOP | — | 0.8927 | 0.0000 |
| 2 — lote de facturas (demo contraria) | GRIND | — | 0.9913 | 0.4392 |
| 3a — cadenas de error idénticas | LOOP (migra thrash→loop) | **6** | 0.7818 | 0.0000 |
| 3b — cadenas de error variadas | THRASH (NO dispara) | — | 0.7397 | 0.2114 |

El fixture 2 es la demo contraria: un `action_sim` de 0.9913 supera el umbral superior, por lo que la similitud por sí sola lo condenaría. Sobrevive porque la novedad 0.4392 está por encima del umbral inferior. Ahí es donde el diseño conjunto justifica su existencia.

## Lea esto antes de la tabla de resultados

**Los siguientes fixtures validan la _clasificación_, no la _detección_, y la comparación de detección que sigue aún no constituye un benchmark válido.** Los fixtures 1 y 2 tienen una duración de **dos turnos**. Cada umbral de disparo en el diseño es 3 o mayor, por lo que ningún fixture puede dispararse físicamente sin importar los parámetros. Cualquier fila que muestre `---` para ellos está midiendo la longitud de la traza, no el comportamiento del detector.

Esto se aclara de antemano porque el barrido (sweep) a continuación informa **0 configuraciones utilizables de 144**, y ese número es un artefacto de lo anterior, no un veredicto sobre el diseño. Se requieren trazas reales por clase (§9) antes de que cualquier afirmación de detección aquí signifique algo.

## Comparación con seis líneas base

Turno de disparo por variante y fixture (turnos de prólogo + fixture; `---` = sin disparo):

| Variante | 1 — paráfrasis (2t) | 2 — lote (2t) | 3a — idénticas (7t) | 3b — variadas (3t) |
|---|---|---|---|---|
| **Plateau (completo)** | --- | --- | 6 | --- |
| **action_only** | --- | --- | 5 | --- |
| **novelty_only** | --- | --- | 6 | --- |
| exact-args debounce | --- | --- | --- | --- |
| exact-match (OpenHands) | --- | --- | --- | --- |
| lexical (agent-loop-detector) | --- | --- | 2 | --- |
| step-cap (LangGraph 25) | --- | --- | --- | --- |

*action_only* fija la novedad en 0. El calibrador nunca se calienta (todos los turnos están bloqueados), por lo que el umbral superior se mantiene en el valor predeterminado conservador de 0.85. Dispara en el turno 5 para 3a frente al 6 del Plateau completo: ligeramente más rápido porque el turno 0 (novedad 0.6981 en realidad) también es estancado cuando la novedad se oculta.

*novelty_only* fija `action_sim` en 0, por lo que `confident` nunca es verdadero y solo se activa la ruta `stall_hits`. Coincide con Plateau completo en las detecciones; solo difiere en los turnos hasta la detección.

Nota: **step_cap (LangGraph 25)** requiere 27 turnos para dispararse, más que cualquier fixture. Con el valor predeterminado de la fuente de **10007**, nunca se dispara en ninguna traza de hasta 200 turnos: el recall es cero por construcción.

### Nuestras peores cifras, dichas claramente

**En el único fixture donde algo detecta un estancamiento, una línea base léxica de la era 2019 nos supera: `agent-loop-detector` dispara en el turno 2, Plateau en el turno 6.** Ese es el resultado honesto para 3a, cuyas observaciones son idénticas a nivel de byte: exactamente el caso para el que están diseñados la coincidencia exacta y léxica. La ventaja reivindicada de Plateau es sobre el estancamiento *parafraeado*, y el fixture que lo demostraría (fixture 1) es demasiado corto para dispararse en absoluto. Por lo tanto, la ventaja actualmente está **sin medir**, no demostrada.

**Barrido (Sweep): 0 de 144 configuraciones son utilizables.** Una configuración es utilizable solo si detecta cada estancamiento y no genera falsos positivos en nada.

| Resultado del barrido | Valor |
|---|---|
| Configuraciones evaluadas | 144 |
| Configuraciones utilizables | **0 (0.0%)** |
| Recuperación (recall) máxima observada | **0.5** |
| Anchura de ventana de umbral utilizable | **vacía — indefinida** |
| Tasa de falsos disparos (fixture 2, todas las configs) | **0.0** |
| `1_paraphrase_loop` omitido en | **144/144 configs** |
| `3a_thrash_identical_errors` omitido en | 28/144 configs |

El único número genuinamente bueno es la tasa de falsos disparos: **0.0 en todas las 144 configuraciones**: el trabajo por lotes saludable nunca fue disparado, en ninguna configuración de parámetros. La demo contraria es el resultado más robusto del proyecto.

Todo lo demás está pendiente de trazas reales. `metrics.json` → `sweep.summary`.

## Limitaciones documentadas

1. **El fixture 3b (cadenas de error variadas) es un fallo conocido.** Los mensajes de error léxicamente variados se interpretan como información nueva en embeddings de cadenas cortas, por lo que un agente que falla de maneras redactadas diferente evade la detección. No se ha ajustado para eliminarlo, se mantiene honesto mediante `test_fixture_3b_varied_errors_is_a_known_miss`.

2. **Las herramientas de polling deben declarar `idempotent: true`.** La distribución de novedad medida muestra que los pollers abarcan de 0.0067 a 0.2311, solapándose con la banda de bucles. Un poller está estancado informacionalmente ("aún en ejecución, 4m" → "aún en ejecución, 9m"), por lo que ningún umbral puede separarlo de un agente atascado. Cualquier herramienta que legítimamente devuelva observaciones casi idénticas debe declararse idempotente.

3. **Sin umbral inferior para thrash.** Tres herramientas diferentes obtienen 0.7397, por lo que `mu − k·σ` no puede encontrar una región de baja similitud que no existe. No se ha parcheado con una constante.

4. **Los fixtures 1 y 2 tienen dos turnos de duración y no pueden dispararse.** Cada umbral es ≥3. Prueban la clasificación de cuadrantes, que superan, y nada más. Por lo tanto, la comparación de detección y el barrido aún no son benchmarks válidos.

5. **Sin evaluación no sintética todavía.** Cada traza anterior está escrita a mano. El conjunto de datos TRAIL (con acceso restringido, `PatronusAI/TRAIL`) se descarga por separado por un humano y nunca se hace commit; `data/trail/` está ignorado por git. Hasta que se carguen esas trazas, ningún número aquí es evidencia sobre el comportamiento real de los agentes.

## Estado del arte previo, tal como se ha leído

Cuatro sistemas lanzados protegen contra bucles de agentes. Leímos el código fuente de cada uno en lugar de su README, y dos afirmaciones en nuestra propia presentación resultaron ser incorrectas: las correcciones están registradas en `THIRD_PARTY_NOTICES.md`.

| Sistema | Lee | Mecanismo |
|---|---|---|
| OpenHands `StuckDetector` | **ambas mitades** | igualdad exacta (`_event_eq`), 5 escenarios |
| `agent-loop-detector` | **solo observación** (`check(output)`) | Jaccard / TF-cosine / Levenshtein |
| Strands `LimitToolCounts` | recuento de acciones por herramienta | límite de llamadas por herramienta |
| LangGraph `recursion_limit` | **ninguna mitad** | contador de superpasos, sin comparación de contenido |

**Ninguno compara ambas mitades semánticamente.** Esa es la brecha que Plateau intenta cubrir: una afirmación más restrictiva que "todos comparan cadenas exactas", la cual es falsa: LangGraph no compara nada en absoluto, y `agent-loop-detector` compara superposición léxica.

Ambos issues abiertos de OpenHands que citamos como motivación son reales y están sin resolver: [#5355](https://github.com/All-Hands-AI/OpenHands/issues/5355) (la detección de bucles mata a los agentes que esperan procesos de larga ejecución) y [#5480](https://github.com/All-Hands-AI/OpenHands/issues/5480) (no se puede recuperar de un bucle atascado). El segundo es la razón por la que la recuperación aquí es una sonda evaluada en lugar de una parada forzada.

## Parámetros provisionales (pendientes de barrido)

| Parámetro | Actual | Propiedad de |
|---|---|---|
| `NOVELTY_FLOOR` | 0.30 | `eval/sweep.py` |
| `K_SIGMA` | 1.0 | `eval/sweep.py` |
| `TRIP_AFTER_LOOP` | 3 | `eval/sweep.py` |
| `TRIP_AFTER_STALL` | 6 | `eval/sweep.py` |
