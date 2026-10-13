# Patrones Avanzados de Prompts

## Patrón de Cadena de Pensamiento

Para tareas complejas, guiar el razonamiento paso a paso:

```markdown
## Instrucciones

Antes de generar código, sigue estos pasos:

1. **Analizar requisitos**
   - ¿Qué inputs recibe?
   - ¿Qué outputs produce?
   - ¿Qué casos edge existen?

2. **Diseñar solución**
   - ¿Qué estructura de datos usar?
   - ¿Qué algoritmo es más eficiente?
   - ¿Qué patrones aplicar?

3. **Implementar**
   - Escribir código siguiendo el diseño
   - Añadir manejo de errores
   - Incluir documentación

4. **Validar**
   - Verificar casos de uso
   - Comprobar casos edge
   - Confirmar rendimiento
```

## Patrón de Ejemplos (Few-Shot)

Proporcionar ejemplos del resultado esperado:

```markdown
## Ejemplos

### Input
```typescript
function sum(a, b) { return a + b; }
```

### Output esperado
```typescript
/**
 * Suma dos números.
 * @param a - Primer sumando
 * @param b - Segundo sumando
 * @returns La suma de a y b
 * @example
 * sum(2, 3) // returns 5
 */
function sum(a: number, b: number): number {
  return a + b;
}
```

---

### Input
```typescript
const getUser = async (id) => { ... }
```

### Output esperado
```typescript
/**
 * Obtiene un usuario por su ID.
 * @param id - Identificador único del usuario
 * @returns Promise con los datos del usuario
 * @throws {NotFoundError} Si el usuario no existe
 */
const getUser = async (id: string): Promise<User> => { ... }
```
```

## Patrón de Restricciones

Definir límites claros para evitar outputs no deseados:

```markdown
## Restricciones

### DEBE incluir:
- Tipos TypeScript explícitos
- Manejo de errores con try/catch
- Comentarios en español
- Tests unitarios

### NO debe incluir:
- Uso de `any`
- Console.log en producción
- Dependencias externas nuevas
- Código comentado

### Límites:
- Máximo 50 líneas por función
- Máximo 3 niveles de anidación
- Máximo 4 parámetros por función
```

## Patrón de Contexto Dinámico

Usar variables del contexto de VS Code:

```markdown
## Contexto

Este prompt trabaja con:
- Archivo actual: ${file}
- Selección: ${selection}
- Lenguaje: ${languageId}
- Workspace: ${workspaceFolder}

## Instrucciones

1. Analizar ${selection}
2. Considerar convenciones de ${languageId}
3. Mantener consistencia con ${file}
```

## Patrón de Validación Incluida

Incluir criterios de auto-validación:

```markdown
## Validación

Antes de devolver el resultado, verificar:

1. ✓ Compila sin errores
2. ✓ Pasa análisis estático (ESLint)
3. ✓ No introduce breaking changes
4. ✓ Mantiene compatibilidad hacia atrás
5. ✓ Sigue convenciones del proyecto

Si alguna validación falla, corregir antes de devolver.
```

## Patrón de Salida Estructurada

Para outputs complejos, usar estructura definida:

```markdown
## Formato de Salida

Devolver respuesta en este formato exacto:

```json
{
  "analisis": {
    "complejidad": "baja|media|alta",
    "lineas_codigo": number,
    "funciones": number,
    "problemas": ["problema1", "problema2"]
  },
  "sugerencias": [
    {
      "tipo": "mejora|bug|refactor",
      "descripcion": "string",
      "prioridad": "alta|media|baja",
      "lineas_afectadas": [number]
    }
  ],
  "codigo_mejorado": "string (código completo)"
}
```
```

## Patrón de Modo Interactivo

Para tareas que requieren clarificación:

```markdown
## Modo Interactivo

Si la información es insuficiente, preguntar:

1. **Antes de generar código**:
   - "¿Cuál es el framework/librería objetivo?"
   - "¿Hay requisitos de rendimiento específicos?"

2. **Antes de refactorizar**:
   - "¿Debo mantener la API pública?"
   - "¿Hay tests que deba considerar?"

3. **Antes de documentar**:
   - "¿Quién es la audiencia objetivo?"
   - "¿Qué nivel de detalle se requiere?"

NO asumir. Preguntar si hay ambigüedad.
```
