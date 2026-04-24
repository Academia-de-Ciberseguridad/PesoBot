# OAIF · Lab Sesión 1 · PesoBot Vulnerable

Stack Docker para la demo en vivo de las **5 vulnerabilidades OWASP LLM 2025** durante la Sesión 1 del programa **OAIF (Offensive AI Foundations)** de la Academia de Ciberseguridad LATAM.

## Qué es este lab

**PesoBot** es un chatbot bancario LATAM ficticio del "Banco LATAM" — intencionalmente vulnerable para fines educativos. Implementa las 5 vulnerabilidades del slide 29 del curso:

| # | Vulnerabilidad OWASP LLM 2025 | Vector de ataque |
|---|-------------------------------|------------------|
| 1 | **LLM01** Prompt Injection | Mensajes del usuario sin sanitizar |
| 2 | **LLM07** System Prompt Leakage | Secretos en el system prompt extraíbles |
| 3 | **LLM04 + LLM08** Data Poisoning + Vector Weaknesses | PDFs de "queja" se ingieren al RAG sin filtros |
| 4 | **LLM06** Excessive Agency | Tool `transfer_money` ejecuta sin human-in-the-loop |
| 5 | **LLM10** Unbounded Consumption | Sin rate-limiting ni límite de tokens |

## Stack técnico

```
┌──────────────────────────────────────────────────────────┐
│  Frontend (nginx)                                        │
│  http://VPS:8080                                         │
│  Chat UI estilo banco + panel debug instructor           │
└────────────────────────┬─────────────────────────────────┘
                         │ /api/*
                         ▼
┌──────────────────────────────────────────────────────────┐
│  PesoBot API (FastAPI)                                   │
│  http://VPS:8000                                         │
│  - /chat              (vulnerable a LLM01, LLM07, LLM10) │
│  - /upload-complaint  (vulnerable a LLM04+08)            │
│  - tools transfer_money (vulnerable a LLM06)             │
└────────────────────────┬─────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   ┌─────────┐      ┌─────────┐    ┌──────────────┐
   │ Qdrant  │      │  Redis  │    │ OpenAI/Claude│
   │ Vector  │      │  Cache  │    │ /Ollama API  │
   │   DB    │      │         │    │              │
   └─────────┘      └─────────┘    └──────────────┘
```

## Quick start

### 1. Clonar y configurar

```bash
# Copiar el lab a tu VPS Hetzner
scp -r oaif-lab-sesion1/ user@cobra.tudominio.com:/opt/

# SSH al VPS
ssh user@cobra.tudominio.com
cd /opt/oaif-lab-sesion1

# Configurar variables de entorno
cp .env.example .env
nano .env  # ← agrega tu OPENAI_API_KEY
```

### 2. Levantar el stack

```bash
# Construir y levantar todo
docker compose up -d --build

# Ver logs en tiempo real
docker compose logs -f pesobot-api

# Verificar estado
docker compose ps
```

Espera ~2 minutos la primera vez (descarga del modelo de embeddings multilingüe).

### 3. Verificar funcionamiento

```bash
# Healthcheck
curl http://localhost:8000/health

# Acceder al chat
# Abre en tu navegador: http://VPS_IP:8080
```

### 4. Validar las 5 vulnerabilidades

```bash
# Script automatizado · ejecuta los 5 ataques pre-cargados
chmod +x scripts/test_attacks.sh
./scripts/test_attacks.sh http://localhost:8000

# O contra el VPS desde tu Kali
./scripts/test_attacks.sh http://cobra.tudominio.com:8000
```

Si los 5 ataques tienen éxito, el lab está listo para la sesión.

## Configuración LLM provider

Por defecto usa **OpenAI** (`gpt-4o-mini`). Puedes cambiar a Anthropic o Ollama editando `.env`:

```bash
# Opción A · OpenAI (recomendado para demo · mejor calidad)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o-mini   # ~$0.15 por 1M tokens

# Opción B · Anthropic Claude
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-5-haiku-20241022

# Opción C · Ollama local (gratis pero más lento, sin tools)
LLM_PROVIDER=ollama
OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3
```

**⚠ Nota sobre Ollama:** Si quieres usar tu Ollama local desde el VPS, necesitas exponerlo (túnel SSH inverso, ngrok, o cloudflared). Para la demo en vivo es más simple usar OpenAI con `gpt-4o-mini` (~$0.50 por toda la sesión).

## Endpoints de la API

| Método | Endpoint | Propósito |
|--------|----------|-----------|
| POST | `/chat` | Conversación con PesoBot |
| POST | `/upload-complaint` | Sube PDF de queja al RAG |
| POST | `/reset` | Resetea estado del lab |
| GET | `/transfer-log` | Audita transferencias ejecutadas |
| GET | `/documents` | Lista documentos en Qdrant |
| GET | `/health` | Healthcheck |

## Comandos útiles

```bash
# Ver logs
docker compose logs -f pesobot-api

# Reiniciar solo el backend
docker compose restart pesobot-api

# Reset completo (borra TODOS los datos)
docker compose down -v
docker compose up -d --build

# Reset suave (solo limpia el lab, mantiene contenedores)
curl -X POST http://localhost:8000/reset

# Ver transferencias ejecutadas
curl http://localhost:8000/transfer-log | jq

# Ver documentos en RAG (incluye envenenados)
curl http://localhost:8000/documents | jq
```

## Estructura del repo

```
oaif-lab-sesion1/
├── docker-compose.yml           # Orquestador principal
├── .env.example                 # Template de variables
├── README.md                    # Este archivo
├── INSTRUCTOR_GUIDE.md          # Guion paso a paso para sesión en vivo
│
├── pesobot-api/                 # Backend FastAPI
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                  # Endpoints
│   ├── llm_client.py            # Cliente OpenAI/Claude/Ollama
│   ├── system_prompt.txt        # System prompt CON SECRETOS (LLM07)
│   ├── tools.py                 # Tools vulnerables (LLM06)
│   └── rag.py                   # RAG vulnerable (LLM04+08)
│
├── pesobot-frontend/            # UI nginx
│   ├── nginx.conf
│   └── public/
│       ├── index.html           # Chat UI
│       ├── style.css
│       └── app.js
│
└── scripts/
    └── test_attacks.sh          # Validador de los 5 ataques
```

## Costos estimados

Para una sesión de 3h con ~30 estudiantes interactuando:

| Modelo | Costo aproximado |
|--------|-----------------|
| `gpt-4o-mini` | $0.50 - $2 USD |
| `gpt-4o` | $5 - $15 USD |
| `claude-3-5-haiku` | $1 - $4 USD |
| Ollama local | $0 |

## Troubleshooting

**El backend no arranca:**
```bash
docker compose logs pesobot-api
# Verifica: OPENAI_API_KEY configurada, Qdrant healthy
```

**Qdrant tarda mucho:**
```bash
# Espera ~2 min la primera vez (descarga modelo embeddings 90MB)
docker compose logs qdrant
```

**El frontend no se conecta:**
```bash
# Verifica que pesobot-api esté healthy
docker compose ps
# Si está en estado unhealthy: revisar logs
```

**Quiero usar mi Ollama local desde el VPS:**
```bash
# Desde tu Kali, hacer un túnel SSH inverso al VPS
ssh -R 11434:localhost:11434 user@cobra.tudominio.com
# En .env del VPS, poner:
# OLLAMA_URL=http://host.docker.internal:11434
```

## Licencia y uso

Este lab es **estrictamente educativo** y forma parte del programa OAIF. NO desplegar en producción ni con datos reales.

## Soporte

Academia de Ciberseguridad LATAM
- Web: https://academia-ciberseguridad.com
- Email: contacto@academia-ciberseguridad.com
- Director: Jose Angel Alamillo
