---
name: prompt-creator
description: Guía para crear prompts efectivos para GitHub Copilot. Usar cuando el usuario quiera crear un nuevo prompt (o actualizar uno existente) para tareas específicas como generación de código, documentación o flujos de trabajo especializados. IMPORTANTE - Los prompts generados estarán en español.
license: Complete terms in LICENSE.txt
---

# Prompt Creator

Este skill proporciona guía para crear prompts efectivos para GitHub Copilot. **Los archivos `.prompt.md` generados estarán en español.**

## Sobre los Prompts

Los prompts son archivos que definen instrucciones específicas para tareas concretas. A diferencia de los agentes (que definen comportamientos generales), los prompts son instrucciones enfocadas en resolver una tarea particular.

### Diferencias entre Prompts y Agentes

| Aspecto | Prompts | Agentes |
|---------|---------|---------|
| Alcance | Tarea específica | Rol/comportamiento general |
| Duración | Una conversación | Múltiples conversaciones |
| Complejidad | Simple a moderada | Moderada a compleja |
| Ejemplo | "Genera tests unitarios" | "Actúa como QA Engineer" |

### Qué Proporcionan los Prompts

1. **Instrucciones específicas** - Pasos claros para una tarea
2. **Contexto necesario** - Información relevante para la tarea
3. **Formato de salida** - Estructura esperada del resultado
4. **Ejemplos** - Muestras del resultado deseado

## Anatomía de un Prompt

### Estructura Básica

```
nombre-del-prompt.prompt.md
├── YAML Frontmatter (opcional pero recomendado)
│   ├── description: (recomendado)
│   └── mode: (opcional: 'agent' o 'edit')
└── Cuerpo Markdown (requerido)
    ├── Contexto/Objetivo
    ├── Instrucciones
    ├── Restricciones
    └── Formato de salida
```

### Frontmatter

```yaml
---
description: Descripción breve del propósito del prompt
mode: agent  # 'agent' (chat) o 'edit' (edición inline)
---
```

## Principios de Diseño de Prompts

### 1. Claridad

**Malo:**
```
Genera código bueno
```

**Bueno:**
```
Genera una función TypeScript que:
- Reciba un array de números
- Devuelva el promedio
- Maneje arrays vacíos devolviendo 0
- Incluya JSDoc con descripción y tipos
```

### 2. Especificidad

**Malo:**
```
Haz tests para esta función
```

**Bueno:**
```
Genera tests unitarios con Jest para la función `calculateTotal`:
- Test de caso normal con valores positivos
- Test de caso edge con array vacío
- Test de caso edge con valores negativos
- Cada test debe tener nombre descriptivo en español
```

### 3. Contexto Relevante

**Malo:**
```
Documenta este código
```

**Bueno:**
```
Genera documentación JSDoc para esta función considerando:
- Es parte de una API REST de pagos
- La usan desarrolladores externos
- Debe incluir ejemplos de uso
- Debe documentar posibles errores
```

### 4. Formato de Salida Explícito

**Malo:**
```
Dame información sobre el archivo
```

**Bueno:**
```
Analiza el archivo y devuelve un JSON con:
{
  "nombre": "nombre del archivo",
  "lineas": número de líneas,
  "complejidad": "baja|media|alta",
  "sugerencias": ["sugerencia1", "sugerencia2"]
}
```

## Proceso de Creación de Prompts

### Paso 1: Identificar la Tarea

Responder:
- ¿Qué tarea específica debe resolver?
- ¿Qué información necesita Copilot?
- ¿Qué formato debe tener la salida?
- ¿Hay restricciones o requisitos especiales?

### Paso 2: Estructurar el Prompt

Usar esta plantilla:

```markdown
---
description: [Descripción breve]
mode: agent
---

## Objetivo
[Qué debe lograr el prompt]

## Contexto
[Información necesaria para la tarea]

## Instrucciones
[Pasos a seguir]

## Restricciones
[Qué NO hacer]

## Formato de Salida
[Estructura esperada del resultado]

## Ejemplo
[Muestra del resultado esperado]
```

### Paso 3: Inicializar el Prompt

Ejecutar el script de inicialización:

```bash
scripts/init_prompt.py <nombre-prompt> --path prompts/categoria/
```

### Paso 4: Refinar y Probar

1. Probar el prompt con casos reales
2. Verificar que el output cumple expectativas
3. Ajustar instrucciones según resultados
4. Documentar casos de uso

## Patrones Comunes de Prompts

### Patrón 1: Generación de Código

```markdown
---
description: Genera componente React con TypeScript
mode: agent
---

## Objetivo
Generar un componente React funcional con TypeScript.

## Instrucciones
1. Usar functional component con hooks
2. Definir Props interface
3. Incluir PropTypes o TypeScript types
4. Añadir comentarios JSDoc

## Restricciones
- NO usar class components
- NO usar any como tipo
- Mantener componente < 100 líneas

## Formato
```tsx
interface Props {
  // props tipadas
}

/**
 * Descripción del componente
 */
export const ComponentName: React.FC<Props> = ({ prop1, prop2 }) => {
  return (
    // JSX
  );
};
```
```

### Patrón 2: Generación de Tests

```markdown
---
description: Genera tests unitarios con Jest
mode: agent
---

## Objetivo
Generar tests unitarios completos para la función/clase seleccionada.

## Instrucciones
1. Analizar la función y sus casos de uso
2. Identificar casos edge
3. Crear tests descriptivos
4. Incluir setup y teardown si necesario

## Estructura de Tests
```typescript
describe('NombreFuncion', () => {
  describe('cuando [condición]', () => {
    it('debería [comportamiento esperado]', () => {
      // Arrange
      // Act
      // Assert
    });
  });
});
```

## Cobertura Requerida
- Caso feliz/normal
- Casos edge (vacío, null, undefined)
- Casos de error
- Casos límite
```

### Patrón 3: Documentación

```markdown
---
description: Genera documentación README
mode: agent
---

## Objetivo
Generar README.md completo para el proyecto.

## Secciones Requeridas
1. Título y descripción
2. Badges (opcional)
3. Instalación
4. Uso básico
5. Configuración
6. API/Referencia
7. Contribución
8. Licencia

## Formato
```markdown
# Nombre del Proyecto

Descripción breve y clara.

## Instalación
[Comandos de instalación]

## Uso
[Ejemplos de uso]

## Contribuir
[Guía de contribución]
```
```

### Patrón 4: Refactoring

```markdown
---
description: Refactoriza código aplicando Clean Code
mode: edit
---

## Objetivo
Mejorar la calidad del código seleccionado.

## Principios a Aplicar
- Single Responsibility
- DRY (Don't Repeat Yourself)
- Nombres descriptivos
- Funciones pequeñas y enfocadas

## Instrucciones
1. Identificar code smells
2. Extraer funciones si > 20 líneas
3. Renombrar variables poco claras
4. Eliminar código duplicado
5. Añadir tipado si falta

## Mantener
- Funcionalidad original
- Tests existentes pasando
- Compatibilidad de API pública
```

## Referencias Adicionales

- **Patrones avanzados**: Ver [references/prompt-patterns.md](references/prompt-patterns.md)
- **Ejemplos por categoría**: Ver [references/prompt-examples.md](references/prompt-examples.md)

## Checklist de Validación

Antes de finalizar un prompt:

- [ ] Tiene descripción clara del objetivo
- [ ] Las instrucciones son específicas y accionables
- [ ] El formato de salida está definido
- [ ] Incluye al menos un ejemplo
- [ ] Se ha probado con casos reales
- [ ] El nombre sigue la convención `kebab-case.prompt.md`
