#!/usr/bin/env python3
"""
Prompt Initializer - Creates a new prompt from template

Usage:
    init_prompt.py <prompt-name> --path <path>

Examples:
    init_prompt.py generar-tests --path prompts/testing/
    init_prompt.py documentar-api --path prompts/docs/
"""

import sys
from pathlib import Path


PROMPT_TEMPLATE = """---
description: [TODO: Descripción breve del propósito del prompt]
mode: agent
---

# {prompt_title}

## Objetivo

[TODO: Describir qué debe lograr este prompt]

## Contexto

[TODO: Proporcionar información necesaria para la tarea]

## Instrucciones

[TODO: Pasos específicos a seguir]

1. Paso 1
2. Paso 2
3. Paso 3

## Restricciones

[TODO: Qué NO debe hacer]

- NO hacer X
- NO hacer Y

## Formato de Salida

[TODO: Definir estructura esperada del resultado]

```
[Ejemplo de formato]
```

## Ejemplo

### Input
[TODO: Ejemplo de entrada]

### Output esperado
[TODO: Ejemplo de salida]
"""


def title_case_prompt_name(prompt_name):
    """Convert hyphenated prompt name to Title Case for display."""
    return ' '.join(word.capitalize() for word in prompt_name.split('-'))


def init_prompt(prompt_name, path):
    """
    Initialize a new prompt file from template.

    Args:
        prompt_name: Name of the prompt (kebab-case)
        path: Path where the prompt file should be created

    Returns:
        Path to created prompt file, or None if error
    """
    # Determine prompt file path
    prompt_dir = Path(path).resolve()
    prompt_file = prompt_dir / f"{prompt_name}.prompt.md"

    # Check if file already exists
    if prompt_file.exists():
        print(f"❌ Error: El archivo del prompt ya existe: {prompt_file}")
        return None

    # Create directory if it doesn't exist
    try:
        prompt_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"❌ Error creando directorio: {e}")
        return None

    # Create prompt file from template
    prompt_title = title_case_prompt_name(prompt_name)
    prompt_content = PROMPT_TEMPLATE.format(
        prompt_name=prompt_name,
        prompt_title=prompt_title
    )

    try:
        prompt_file.write_text(prompt_content)
        print(f"✅ Archivo de prompt creado: {prompt_file}")
    except Exception as e:
        print(f"❌ Error creando archivo de prompt: {e}")
        return None

    # Print next steps
    print(f"\n✅ Prompt '{prompt_name}' inicializado correctamente")
    print("\nPróximos pasos:")
    print("1. Edita el archivo para completar los TODOs")
    print("2. Define el objetivo claramente")
    print("3. Especifica las instrucciones paso a paso")
    print("4. Añade restricciones y formato de salida")
    print("5. Incluye al menos un ejemplo")
    print("6. Prueba el prompt con casos reales")

    return prompt_file


def main():
    if len(sys.argv) < 4 or sys.argv[2] != '--path':
        print("Uso: init_prompt.py <nombre-prompt> --path <ruta>")
        print("\nRequisitos del nombre del prompt:")
        print("  - Identificador en kebab-case (ej: 'generar-tests')")
        print("  - Solo letras minúsculas, dígitos y guiones")
        print("  - Debe ser descriptivo de la tarea")
        print("\nEjemplos:")
        print("  init_prompt.py generar-tests --path prompts/testing/")
        print("  init_prompt.py documentar-api --path prompts/docs/")
        sys.exit(1)

    prompt_name = sys.argv[1]
    path = sys.argv[3]

    print(f"🚀 Inicializando prompt: {prompt_name}")
    print(f"   Ubicación: {path}")
    print()

    result = init_prompt(prompt_name, path)

    if result:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
