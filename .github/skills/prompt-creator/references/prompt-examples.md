# Ejemplos de Prompts por Categoría

## Desarrollo Frontend

### Componente React

```markdown
---
description: Genera componente React con TypeScript y estilos
mode: agent
---

Genera un componente React funcional para: {descripcion}

## Requisitos
- TypeScript con interfaces para props
- Styled-components o CSS Modules
- Manejo de estados con hooks
- Accesibilidad básica (ARIA)

## Estructura
```tsx
// types.ts
export interface ComponentNameProps { }

// ComponentName.tsx
import React from 'react';
import { ComponentNameProps } from './types';
import styles from './ComponentName.module.css';

export const ComponentName: React.FC<ComponentNameProps> = (props) => {
  return ( );
};

// ComponentName.test.tsx
// tests básicos
```
```

### Formulario Angular

```markdown
---
description: Genera formulario reactivo Angular
mode: agent
---

Genera un formulario Angular reactivo para: {descripcion}

## Requisitos
- Reactive Forms
- Validaciones síncronas y asíncronas
- Mensajes de error localizados
- Submit con loading state

## Incluir
- FormGroup con FormControls
- Validadores custom si necesario
- Template con error handling
- Estilos accesibles
```

## Desarrollo Backend

### Endpoint REST Spring Boot

```markdown
---
description: Genera endpoint REST con Spring Boot
mode: agent
---

Genera un endpoint REST para: {descripcion}

## Estructura
```
├── controller/
│   └── ResourceController.java
├── service/
│   ├── ResourceService.java
│   └── impl/ResourceServiceImpl.java
├── repository/
│   └── ResourceRepository.java
├── dto/
│   ├── ResourceRequest.java
│   └── ResourceResponse.java
└── mapper/
    └── ResourceMapper.java
```

## Requisitos
- Anotaciones OpenAPI/Swagger
- Validación con Bean Validation
- Manejo de excepciones centralizado
- Tests unitarios e integración
```

### API Node.js/Express

```markdown
---
description: Genera API REST con Express y TypeScript
mode: agent
---

Genera endpoint Express para: {descripcion}

## Estructura
```
├── routes/
│   └── resource.routes.ts
├── controllers/
│   └── resource.controller.ts
├── services/
│   └── resource.service.ts
├── middleware/
│   └── validation.middleware.ts
└── types/
    └── resource.types.ts
```

## Requisitos
- TypeScript estricto
- Validación con Zod/Joi
- Error handling middleware
- Tests con Jest
```

## Testing

### Tests Unitarios Jest

```markdown
---
description: Genera tests unitarios completos con Jest
mode: agent
---

Genera tests para el código seleccionado.

## Estructura de Tests
```typescript
describe('Nombre', () => {
  // Setup
  beforeEach(() => { });
  
  describe('método/función', () => {
    it('caso normal - debería ...', () => { });
    it('caso edge - debería ...', () => { });
    it('caso error - debería ...', () => { });
  });
});
```

## Cobertura
- Casos felices
- Casos edge (null, undefined, vacío, límites)
- Casos de error
- Mocks para dependencias externas
```

### Tests E2E Cypress

```markdown
---
description: Genera tests E2E con Cypress
mode: agent
---

Genera tests E2E para el flujo: {descripcion}

## Estructura
```typescript
describe('Flujo: {nombre}', () => {
  beforeEach(() => {
    cy.visit('/path');
  });

  it('completa el flujo exitosamente', () => {
    // Pasos del flujo
  });

  it('maneja errores correctamente', () => {
    // Casos de error
  });
});
```

## Requisitos
- Selectores con data-testid
- Interceptors para API calls
- Screenshots en fallos
- Custom commands si necesario
```

## Documentación

### README de Proyecto

```markdown
---
description: Genera README completo
mode: agent
---

Genera README.md para el proyecto actual.

## Secciones
1. **Título y Badges**
2. **Descripción** - Qué hace, por qué existe
3. **Demo/Screenshots** - Si aplica
4. **Requisitos** - Prerequisitos
5. **Instalación** - Paso a paso
6. **Uso** - Ejemplos básicos
7. **API** - Referencia si aplica
8. **Configuración** - Variables de entorno
9. **Tests** - Cómo ejecutar
10. **Contribuir** - Guía básica
11. **Licencia**
```

### Documentación de API

```markdown
---
description: Genera documentación OpenAPI/Swagger
mode: agent
---

Genera especificación OpenAPI para: {descripcion}

## Formato
```yaml
openapi: 3.0.0
info:
  title: API Name
  version: 1.0.0
paths:
  /resource:
    get:
      summary: 
      responses:
        200:
          description: 
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Resource'
components:
  schemas:
    Resource:
      type: object
      properties:
```

## Incluir
- Descripciones claras
- Ejemplos de request/response
- Códigos de error
- Schemas reutilizables
```

## DevOps

### Dockerfile

```markdown
---
description: Genera Dockerfile optimizado
mode: agent
---

Genera Dockerfile para: {tecnologia}

## Requisitos
- Multi-stage build
- Usuario no-root
- Layer caching optimizado
- Health check
- Tamaño mínimo

## Estructura
```dockerfile
# Build stage
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage
FROM node:18-alpine AS runner
WORKDIR /app
RUN addgroup -S app && adduser -S app -G app
COPY --from=builder /app/dist ./dist
USER app
HEALTHCHECK --interval=30s CMD wget -q --spider http://localhost:3000/health
EXPOSE 3000
CMD ["node", "dist/main.js"]
```
```

### Pipeline CI/CD

```markdown
---
description: Genera pipeline GitHub Actions
mode: agent
---

Genera workflow para: {descripcion}

## Estructura
```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup
      - name: Install
      - name: Test
      - name: Coverage

  build:
    needs: test
    steps:
      - name: Build
      - name: Push

  deploy:
    needs: build
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Deploy
```
```
