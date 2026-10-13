---
description: Investiga y recomienda la alternativa más sencilla para propagar el actor real de Zeus a action-ci-token
mode: agent
---

## Objetivo

Investigar, evaluar y recomendar **la solución más sencilla posible** para que el action `action-ci-token` pueda conocer el **usuario real que lanza un workflow desde Zeus** (en lugar de detectar al usuario técnico `app-devopsplatform` que Zeus/Controlplane usa para ejecutar los workflows).

La solución elegida debe ser:

- **Mínimamente intrusiva** en los repos que consumen el action (cap, binding, etc.).
- **Rápida de implementar**.
- **Autocontenida**: debe depender únicamente de componentes que gestionamos nosotros (`action-ci-token`, `arch-plat-lambda-controlplane`, `cloud-gestconf-runtime` o el secret manager propio).

## Contexto

### Arquitectura actual

1. **Zeus** invoca workflows a través del **controlplane** (repo `mapfre-tech/arch-plat-lambda-controlplane`) con una llamada tipo:

   ```bash
   curl --request POST \
       --url https://controlplane.aws.devops.mapfre.com/repositories/<repo>/workflows/<workflow> \
       --header 'authorization: {{apiKey}}' \
       --header 'content-type: application/json' \
       --header 'x-atlas-api-key: {{x-atlas-api-key}}' \
       --data '{
           "ref": "<ref>",
           "inputs": {},
           "entity": "<entity>",
           "product": "<product>"
       }'
   ```

2. **Controlplane** valida los permisos del usuario que llama y, si es correcto, dispara el workflow en GitHub usando un **token global** de un usuario admin (`app-devopsplatform`).

3. **action-ci-token** (este repo) toma `github.actor`, comprueba permisos y devuelve un token de una GitHub App con permisos sobre el repo actual y sobre otros repos indicados en el propio action.

### Problema

Cuando el workflow lo lanza Zeus, `github.actor` = `app-devopsplatform` (superadmin), por lo que **se pierde la identidad del usuario original** y no podemos aplicar sus permisos reales.

### Alternativas ya consideradas

**Opción 1 — Endpoint en Zeus (por `github.run_id`)**
- Zeus expone endpoint que, dado `run_id`, devuelve el actor original.
- Requiere: modificar `action-ci-token`, secreto de API de Zeus a nivel org, propagar el secreto por todos los workflows reusables (cap, binding, deploy…), posible restricción a runner privado.

**Opción 2 — JWT como input del workflow**
- Zeus envía el JWT del usuario como input del workflow.
- Requiere: verificar firma JWT con clave pública de Zeus en `action-ci-token`, secreto de clave pública a nivel org, propagar clave e input `zeus_identity` por todos los workflows reusables.
- No requiere runner privado.

**Opción 3 — Guardar el actor en `cloud-gestconf-runtime`**
- Controlplane escribe `(run_id → actor)` en el gestor de configuración.
- `action-ci-token` lo consulta.

**Opción 4 — BBDD en controlplane**
- Controlplane registra `(run_id, actor)` en una BBDD propia y expone endpoint para consulta desde el action.

**Opción 5 (abierta) — Extender el secret manager actual**
- El action ya consume un secret manager propio (para el `decrypt-token`).
- Podría usarse como almacén temporal de la relación `run_id → actor` escrita por controlplane.

## Instrucciones

Realiza el análisis siguiendo estos pasos:

1. **Explora los repos implicados** para entender restricciones reales antes de opinar:
   - `mapfre-tech/action-ci-token` (este repo): cómo obtiene hoy `github.actor`, cómo consulta el secret manager, en qué runner corre.
   - `mapfre-tech/arch-plat-lambda-controlplane`: cómo dispara el workflow, dónde se conoce el actor original, qué persistencia tiene disponible.
   - `mapfre-tech/cloud-gestconf-runtime`: qué API expone y si es apto para escrituras cortas / lecturas frecuentes.
   - Workflows reusables afectados (cap, binding, deploy) para valorar el coste de propagar inputs/secretos.

2. **Para cada alternativa (1–5 y cualquier nueva que propongas)** produce una ficha con:
   - **Resumen** en 1–2 líneas.
   - **Cambios en `action-ci-token`**.
   - **Cambios en controlplane**.
   - **Cambios en repos consumidores** (workflows cap, binding, deploy…): ¿hay que tocar cada repo o solo workflows centrales?
   - **Nuevos secretos / configuraciones** requeridos y a qué nivel (org, repo, entorno).
   - **Requisitos de red / runner** (¿obliga a runner privado?).
   - **Riesgos de seguridad** (spoofing del actor, replay, permisos ampliados…).
   - **Coste estimado** (S / M / L) en implementación y en mantenimiento.
   - **Grado de intrusión** en los repos cliente (Bajo / Medio / Alto).

3. **Propón al menos una alternativa adicional** si detectas alguna vía mejor (por ejemplo: usar `workflow_dispatch` con inputs firmados, OIDC de GitHub contra un endpoint propio, un job previo en el propio reusable que resuelva el actor, etc.).

4. **Comparativa** en tabla resumen con columnas: `Opción | Intrusión repos | Cambios reusables | Secretos nuevos | Runner privado | Seguridad | Coste | Rapidez`.

5. **Recomendación final**:
   - Elige **una única opción ganadora** aplicando el criterio "lo más sencillo posible y menos intrusivo".
   - Justifica por qué descartas el resto.
   - Describe un **plan de implementación por fases** (qué se toca primero, cómo se despliega sin romper los repos que aún no propagan el nuevo input/secreto, estrategia de rollback).
   - Enumera **preguntas abiertas** que haya que confirmar con el equipo de Zeus / Controlplane antes de arrancar.

## Restricciones

- **NO** proponer soluciones que dependan de servicios de terceros fuera de Mapfre.
- **NO** proponer soluciones que impliquen que cada repo cliente tenga que mantener lógica de identidad; la complejidad debe quedar en `action-ci-token` + controlplane + un almacén nuestro.
- **NO** dar por buena una opción sin analizar el impacto en los workflows reusables intermedios (cap, binding, deploy).
- **NO** inventar endpoints o campos de Zeus/Controlplane sin verificarlos en el código real; si no se pueden verificar, marcarlos explícitamente como *"a confirmar"*.
- La solución **no debe ampliar** los permisos que hoy tiene la GitHub App.

## Formato de Salida

Entrega el análisis en Markdown con esta estructura exacta:

```markdown
# Análisis: propagación del actor real de Zeus a action-ci-token

## 1. Hallazgos en el código
- action-ci-token: ...
- controlplane: ...
- cloud-gestconf-runtime: ...
- Workflows reusables afectados: ...

## 2. Fichas por alternativa
### Opción 1 — Endpoint Zeus por run_id
- Resumen:
- Cambios en action-ci-token:
- Cambios en controlplane:
- Cambios en repos consumidores:
- Secretos / config:
- Runner:
- Seguridad:
- Coste (S/M/L):
- Intrusión (B/M/A):

### Opción 2 — JWT como input
...

### Opción 3 — cloud-gestconf-runtime
...

### Opción 4 — BBDD en controlplane
...

### Opción 5 — Secret manager propio
...

### Opción N — [nuevas propuestas]
...

## 3. Comparativa
| Opción | Intrusión repos | Cambios reusables | Secretos nuevos | Runner privado | Seguridad | Coste | Rapidez |
|--------|-----------------|-------------------|-----------------|----------------|-----------|-------|---------|
| 1 | ... | ... | ... | ... | ... | ... | ... |
| ... |

## 4. Recomendación
- **Opción elegida:** ...
- **Justificación:** ...
- **Opciones descartadas y por qué:** ...

## 5. Plan de implementación
1. Fase 1 — ...
2. Fase 2 — ...
3. Rollback — ...

## 6. Preguntas abiertas
- ...
```

## Ejemplo de nivel de detalle esperado (fragmento)

> **Opción 3 — cloud-gestconf-runtime**
> - **Resumen:** Controlplane escribe `run_id → actor` en gestconf al lanzar el workflow; el action lo lee usando el mismo cliente que ya emplea para otras configs.
> - **Cambios en action-ci-token:** Añadir helper `getActorFromGestconf(runId)` reutilizando el cliente existente de gestconf. Si `github.actor == 'app-devopsplatform'`, usar el valor devuelto; si no, mantener `github.actor`.
> - **Cambios en controlplane:** Tras invocar el workflow (`workflow_dispatch`), obtener el `run_id` resultante y hacer `PUT /config/zeus-actors/{run_id}` con TTL corto (ej. 2h).
> - **Cambios en repos consumidores:** **Ninguno**. No se añaden inputs ni secretos nuevos.
> - **Secretos / config:** Ninguno nuevo (credencial de gestconf ya existe en el action).
> - **Runner:** No cambia (`ubuntu-latest` sigue siendo válido si gestconf es accesible desde internet o vía el mismo canal actual).
> - **Seguridad:** El actor no viaja por el workflow ni por logs; solo lo escribe controlplane (única fuente de verdad). Riesgo de escritura maliciosa mitigado por auth de gestconf.
> - **Coste:** S.
> - **Intrusión:** Baja.
