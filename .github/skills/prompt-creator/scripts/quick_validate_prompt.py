#!/usr/bin/env python3
"""
Quick validation script for prompts - minimal version
"""

import sys
import re
import yaml
from pathlib import Path


def validate_prompt(prompt_path):
    """Basic validation of a prompt file"""
    prompt_path = Path(prompt_path)

    # Check file exists
    if not prompt_path.exists():
        return False, "Archivo de prompt no encontrado"

    # Check file extension
    if not prompt_path.name.endswith('.prompt.md'):
        return False, "El archivo debe tener extensión .prompt.md"

    # Read content
    content = prompt_path.read_text()

    # Check if has frontmatter (optional but recommended)
    has_frontmatter = content.startswith('---')
    
    if has_frontmatter:
        # Extract frontmatter
        match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
        if match:
            frontmatter_text = match.group(1)
            
            # Parse YAML frontmatter
            try:
                frontmatter = yaml.safe_load(frontmatter_text)
                if frontmatter and isinstance(frontmatter, dict):
                    # Check description
                    description = frontmatter.get('description', '')
                    if description and '[TODO' in str(description):
                        return False, "La descripción contiene placeholders TODO sin completar"
                    
                    # Check mode if present
                    mode = frontmatter.get('mode', '')
                    if mode and mode not in ['agent', 'edit', '']:
                        return False, f"Modo inválido '{mode}'. Debe ser 'agent' o 'edit'"
                        
            except yaml.YAMLError as e:
                return False, f"YAML inválido en frontmatter: {e}"
            
            body = content[match.end():].strip()
        else:
            body = content
    else:
        body = content.strip()

    # Check body content
    if len(body) < 50:
        return False, "El cuerpo del prompt es muy corto. Añade más contenido."

    # Check for required sections (flexible)
    required_keywords = ['objetivo', 'instrucciones', 'Objetivo', 'Instrucciones', 'Instructions', 'Goal']
    has_structure = any(keyword in body for keyword in required_keywords)
    
    if not has_structure:
        return False, "El prompt debe tener al menos secciones de Objetivo e Instrucciones"

    # Check for TODO placeholders
    todo_count = body.count('[TODO')
    if todo_count > 5:
        return False, f"El cuerpo contiene {todo_count} placeholders TODO. Completa el contenido."

    return True, "¡Prompt válido!"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python quick_validate_prompt.py <archivo-prompt.prompt.md>")
        sys.exit(1)

    valid, message = validate_prompt(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)
