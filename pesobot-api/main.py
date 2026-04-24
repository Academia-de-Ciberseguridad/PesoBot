"""
PesoBot API · FastAPI principal
================================
Backend del chatbot bancario LATAM con las 5 vulnerabilidades OWASP LLM
intencionales para la demo de OAIF Sesión 1.

Endpoints:
  POST /chat              · Conversación con PesoBot (vulnerable a LLM01, LLM07, LLM10)
  POST /upload-complaint  · Sube PDF de queja al RAG (vulnerable a LLM04+08)
  POST /reset             · Resetea base vectorial entre demos
  GET  /transfer-log      · Audita transferencias ejecutadas (post-mortem)
  GET  /documents         · Lista documentos en Qdrant
  GET  /health            · Healthcheck
"""
import os
import json
import shutil
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from loguru import logger

from llm_client import get_llm_client
from tools import TOOLS_DEFINITION, execute_tool, get_transfer_log
from rag import init_collection, ingest_pdf_complaint, list_all_documents, reset_collection


# ============================================================================
# Configuración
# ============================================================================
UPLOAD_DIR = Path("/app/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"


def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


# ============================================================================
# Lifespan · inicialización al arranque
# ============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 70)
    logger.info("PesoBot API arrancando...")
    logger.info(f"LLM_PROVIDER: {os.getenv('LLM_PROVIDER', 'openai')}")
    logger.info(f"VULNERABLE_MODE: {os.getenv('VULNERABLE_MODE', 'true')}")
    logger.info("=" * 70)

    # Inicializar Qdrant collection con datos seed
    try:
        init_collection()
    except Exception as e:
        logger.error(f"Error inicializando Qdrant: {e}")

    # Validar cliente LLM
    try:
        get_llm_client()
        logger.info("Cliente LLM validado correctamente")
    except Exception as e:
        logger.error(f"Error inicializando LLM client: {e}")

    yield

    logger.info("PesoBot API apagando...")


app = FastAPI(
    title="PesoBot API",
    description="Banco LATAM · Asistente Virtual (DEMO VULNERABLE - SOLO USO EDUCATIVO)",
    version="3.4.2",
    lifespan=lifespan,
)

# CORS abierto (es un lab, no producción)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Schemas
# ============================================================================
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    response: str
    tool_calls: list | None = None
    tools_executed: list = []
    usage: dict


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health")
async def health():
    """Healthcheck del servicio."""
    return {
        "status": "ok",
        "service": "PesoBot API",
        "version": "3.4.2",
        "llm_provider": os.getenv("LLM_PROVIDER", "openai"),
        "vulnerable_mode": True,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Endpoint principal de chat.

    VULNERABILIDADES INTENCIONALES:
    - LLM01 (Prompt Injection): user input pasa directo al LLM sin sanitizar
    - LLM07 (System Prompt Leakage): system prompt no protegido contra extraction
    - LLM10 (Unbounded Consumption): sin rate-limiting ni límite de tokens
    """
    logger.info(f"[CHAT] Nueva pregunta: {request.message[:200]}")

    client = get_llm_client()
    system_prompt = load_system_prompt()

    history = [{"role": m.role, "content": m.content} for m in request.conversation_history]

    # ===== Primera pasada: el LLM puede decidir usar tools =====
    result = await client.chat(
        system_prompt=system_prompt,
        user_message=request.message,
        conversation_history=history,
        tools=TOOLS_DEFINITION,
    )

    tools_executed = []

    # ===== Si el LLM llamó tools, ejecutarlas y dar resultado de vuelta =====
    if result.get("tool_calls"):
        logger.warning(f"[VULNERABLE] LLM solicitó ejecutar {len(result['tool_calls'])} tools SIN confirmación humana")

        # Ejecutar cada tool
        tool_results = []
        for tc in result["tool_calls"]:
            tool_output = execute_tool(tc["name"], tc["arguments"])
            tools_executed.append({
                "name": tc["name"],
                "arguments": tc["arguments"],
                "result": tool_output,
            })
            tool_results.append({
                "tool_call_id": tc["id"],
                "name": tc["name"],
                "output": tool_output,
            })

        # Segunda pasada: el LLM genera respuesta final con los resultados de tools
        # Reconstruimos historia incluyendo los tool calls
        new_history = history + [
            {"role": "user", "content": request.message},
            {
                "role": "assistant",
                "content": result["content"] or "",
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        }
                    }
                    for tc in result["tool_calls"]
                ],
            },
        ]
        for tr in tool_results:
            new_history.append({
                "role": "tool",
                "tool_call_id": tr["tool_call_id"],
                "content": json.dumps(tr["output"], ensure_ascii=False),
            })

        # Llamada final al LLM (sin tools, solo para sintetizar respuesta)
        final = await client.chat(
            system_prompt=system_prompt,
            user_message="Responde al usuario con base en los resultados de las tools.",
            conversation_history=new_history,
        )
        response_text = final["content"]
        usage = final["usage"]
    else:
        response_text = result["content"]
        usage = result["usage"]

    return ChatResponse(
        response=response_text,
        tool_calls=result.get("tool_calls"),
        tools_executed=tools_executed,
        usage=usage,
    )


@app.post("/upload-complaint")
async def upload_complaint(
    file: UploadFile = File(...),
    complainant_name: str = "anonimo"
):
    """
    Sube PDF de queja al RAG.

    VULNERABILIDADES INTENCIONALES:
    - LLM04 (Data Poisoning): cualquier PDF se vectoriza sin filtros
    - LLM08 (Vector Weaknesses): no se distingue fuente confiable de no confiable
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF")

    logger.warning(f"[VULNERABLE] Subida de PDF SIN sanitizar: {file.filename} por '{complainant_name}'")

    # Guardar archivo subido
    file_path = UPLOAD_DIR / f"{complainant_name}_{file.filename}"
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Ingestar al RAG sin filtros
    result = ingest_pdf_complaint(str(file_path), complainant_name)

    return {
        "filename": file.filename,
        "complainant": complainant_name,
        "ingest_result": result,
        "message": "Queja registrada. Será procesada en máximo 5 días hábiles.",
    }


@app.post("/reset")
async def reset():
    """
    Resetea el estado del lab para hacer otra demo limpia.
    - Limpia la base vectorial
    - Vuelve a sembrar con manuales oficiales
    - Limpia el log de transferencias
    """
    logger.info("[ADMIN] Reseteando base vectorial y logs...")

    # Reset Qdrant
    reset_collection()

    # Limpiar transfer log (en memoria, así que basta con vaciar la lista)
    from tools import TRANSFER_LOG
    TRANSFER_LOG.clear()

    # Limpiar PDFs subidos
    for f in UPLOAD_DIR.glob("*"):
        f.unlink()

    return {"success": True, "message": "Lab reseteado. Listo para otra demo."}


@app.get("/transfer-log")
async def transfer_log():
    """Devuelve el log de transferencias ejecutadas (para audit post-demo)."""
    transfers = get_transfer_log()
    return {
        "total_transfers": len(transfers),
        "transfers": transfers,
        "warning": "Estas transferencias se ejecutaron SIN confirmación humana (LLM06 demo).",
    }


@app.get("/documents")
async def documents():
    """Lista todos los docs en la base vectorial (para demo de poisoning)."""
    docs = list_all_documents()
    return {
        "total": len(docs),
        "documents": docs,
        "tip": "Documentos con trusted=false son potencialmente envenenados (LLM04).",
    }


@app.get("/")
async def root():
    return {
        "service": "PesoBot API",
        "endpoints": {
            "chat": "POST /chat",
            "upload_complaint": "POST /upload-complaint",
            "reset": "POST /reset",
            "transfer_log": "GET /transfer-log",
            "documents": "GET /documents",
            "health": "GET /health",
        },
    }
