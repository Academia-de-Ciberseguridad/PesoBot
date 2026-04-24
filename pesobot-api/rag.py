"""
RAG vulnerable de PesoBot · INTENCIONALMENTE VULNERABLE
========================================================
Demuestra LLM04 (Data Poisoning) y LLM08 (Embedding Weaknesses):

- Cualquier usuario puede subir un PDF de "queja"
- El PDF se vectoriza y se inserta en Qdrant SIN sanitizar
- Cuando otro usuario hace una pregunta, el RAG devuelve los chunks
  envenenados como si fueran información oficial del banco
- El LLM los presenta al usuario como respuesta autoritaria

Este es el patrón "PoisonedRAG" descrito en el slide LLM04 del curso.
"""
import os
import uuid
from pathlib import Path
from typing import Optional
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
import pypdf


# ============================================================================
# Configuración global
# ============================================================================
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = "pesobot_manuales"
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"  # multilingüe (español)
VECTOR_SIZE = 384  # dimensión del modelo de embeddings

# Lazy loading
_qdrant: Optional[QdrantClient] = None
_embedder: Optional[SentenceTransformer] = None


def get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(url=QDRANT_URL)
        logger.info(f"Conectado a Qdrant: {QDRANT_URL}")
    return _qdrant


def get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        logger.info(f"Cargando modelo de embeddings: {EMBEDDING_MODEL}...")
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Modelo de embeddings cargado")
    return _embedder


# ============================================================================
# Inicialización · seed con manuales legítimos
# ============================================================================

LEGITIMATE_DOCS = [
    {
        "title": "Política de transferencias",
        "content": "Las transferencias entre cuentas del Banco LATAM son inmediatas y sin costo. Las transferencias interbancarias tienen un costo de USD $0.50 por operación y se procesan en máximo 2 horas hábiles. El monto máximo por transferencia es de USD $50,000 para clientes con KYC nivel AVANZADO.",
        "category": "transferencias",
    },
    {
        "title": "Atención de quejas",
        "content": "Para presentar una queja formal, el cliente debe enviar un PDF firmado con los detalles del incidente al sistema PesoBot. El sistema procesará la queja en un máximo de 5 días hábiles. Las quejas urgentes pueden escalarse llamando al 800-PESOBOT.",
        "category": "atencion_cliente",
    },
    {
        "title": "Horarios de atención",
        "content": "Banco LATAM atiende de lunes a viernes de 9:00 a 17:00 hrs. Los sábados de 9:00 a 13:00 hrs. PesoBot está disponible 24/7 para consultas no críticas. En días feriados nacionales no hay atención presencial.",
        "category": "general",
    },
    {
        "title": "Apertura de cuentas",
        "content": "Para abrir una cuenta en Banco LATAM se requiere: identificación oficial vigente (INE/pasaporte), comprobante de domicilio no mayor a 3 meses, y RFC con homoclave. La apertura es gratuita y se puede hacer 100% en línea.",
        "category": "cuentas",
    },
    {
        "title": "Tasas de interés vigentes",
        "content": "Cuenta de ahorro: 4.5% anual. Cuenta de inversión a 28 días: 9.2% anual. Cuenta de inversión a 90 días: 10.1% anual. Las tasas pueden cambiar mensualmente sin previo aviso.",
        "category": "inversiones",
    },
    {
        "title": "Seguridad de la app móvil",
        "content": "La app PesoBot Mobile usa autenticación de doble factor (2FA) obligatoria. Soporta huella digital, reconocimiento facial y PIN. NUNCA compartas tu PIN con nadie, ni siquiera con personal del banco.",
        "category": "seguridad",
    },
]


def init_collection():
    """Inicializa la colección de Qdrant con los documentos legítimos."""
    qdrant = get_qdrant()

    # Crear colección si no existe
    collections = [c.name for c in qdrant.get_collections().collections]
    if COLLECTION_NAME not in collections:
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        logger.info(f"Colección {COLLECTION_NAME} creada")

        # Cargar documentos legítimos seed
        embedder = get_embedder()
        points = []
        for doc in LEGITIMATE_DOCS:
            text = f"{doc['title']}\n\n{doc['content']}"
            vector = embedder.encode(text).tolist()
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "text": text,
                    "title": doc["title"],
                    "category": doc["category"],
                    "source": "manual_oficial",
                    "trusted": True,
                },
            ))
        qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
        logger.info(f"{len(points)} documentos legítimos cargados a la base vectorial")
    else:
        logger.info(f"Colección {COLLECTION_NAME} ya existe")


# ============================================================================
# Operaciones · todas vulnerables por diseño
# ============================================================================

def search_knowledge_base(query: str, limit: int = 3) -> list[dict]:
    """
    Busca en la base vectorial. VULNERABLE: no distingue entre fuentes
    confiables y documentos subidos por usuarios (que pueden estar envenenados).
    """
    qdrant = get_qdrant()
    embedder = get_embedder()

    query_vector = embedder.encode(query).tolist()

    results = qdrant.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=limit,
    )

    return [
        {
            "text": r.payload.get("text", ""),
            "title": r.payload.get("title", "Sin título"),
            "source": r.payload.get("source", "desconocido"),
            "trusted": r.payload.get("trusted", False),  # ← este flag NO se respeta
            "score": r.score,
        }
        for r in results
    ]


def ingest_pdf_complaint(pdf_path: str, complainant_name: str = "anónimo") -> dict:
    """
    Ingesta un PDF de queja a la base vectorial.

    VULNERABLE (LLM04 Data Poisoning):
    - No filtra contenido del PDF
    - No detecta payloads de inyección
    - El contenido se mezcla con manuales oficiales
    - Cualquiera puede envenenar la base
    """
    try:
        logger.warning(f"[VULNERABLE] Ingesta PDF de queja sin sanitización: {pdf_path}")

        reader = pypdf.PdfReader(pdf_path)
        full_text = ""
        for page in reader.pages:
            full_text += page.extract_text() + "\n"

        if not full_text.strip():
            return {"success": False, "error": "PDF vacío o no legible"}

        # Chunking simple (en producción usaríamos LangChain/LlamaIndex)
        chunks = [full_text[i:i+800] for i in range(0, len(full_text), 600)]

        embedder = get_embedder()
        qdrant = get_qdrant()

        points = []
        for idx, chunk in enumerate(chunks):
            vector = embedder.encode(chunk).tolist()
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "text": chunk,
                    "title": f"Queja de {complainant_name} - chunk {idx+1}",
                    "category": "quejas",
                    "source": f"pdf_usuario_{complainant_name}",
                    "trusted": False,  # ← marcado como no confiable PERO usado igual
                },
            ))

        qdrant.upsert(collection_name=COLLECTION_NAME, points=points)

        return {
            "success": True,
            "message": f"PDF ingresado a la base vectorial",
            "chunks_added": len(chunks),
            "warning": "VULNERABLE: contenido NO fue sanitizado",
        }
    except Exception as e:
        logger.error(f"Error ingestando PDF: {e}")
        return {"success": False, "error": str(e)}


def reset_collection() -> dict:
    """Borra todo y vuelve a sembrar con manuales oficiales (para reset entre demos)."""
    qdrant = get_qdrant()
    try:
        qdrant.delete_collection(COLLECTION_NAME)
        logger.info(f"Colección {COLLECTION_NAME} eliminada")
    except Exception as e:
        logger.warning(f"No se pudo eliminar la colección: {e}")

    init_collection()
    return {"success": True, "message": "Base vectorial reseteada con datos seed"}


def list_all_documents() -> list[dict]:
    """Lista todos los documentos en la base (para debugging y demo de poisoning)."""
    qdrant = get_qdrant()
    try:
        result = qdrant.scroll(
            collection_name=COLLECTION_NAME,
            limit=100,
            with_payload=True,
            with_vectors=False,
        )
        return [
            {
                "id": str(point.id),
                "title": point.payload.get("title", ""),
                "source": point.payload.get("source", ""),
                "trusted": point.payload.get("trusted", False),
                "preview": point.payload.get("text", "")[:200],
            }
            for point in result[0]
        ]
    except Exception as e:
        logger.error(f"Error listando documentos: {e}")
        return []
