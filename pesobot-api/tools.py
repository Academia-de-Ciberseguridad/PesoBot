"""
Tools de PesoBot · INTENCIONALMENTE VULNERABLES (LLM06 Excessive Agency)
=========================================================================
Estas tools demuestran el patrón vulnerable de darle al LLM capacidades
peligrosas sin confirmación humana ni controles adecuados.

NUNCA usar este patrón en producción real.
"""
import json
import random
from datetime import datetime
from loguru import logger
from typing import Any


# ============================================================================
# Definición de tools en formato OpenAI (compatible con la mayoría)
# ============================================================================
TOOLS_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "get_balance",
            "description": "Consulta el saldo de una cuenta bancaria",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": "ID de la cuenta a consultar (formato: XXXX-XXXX-XXXX-XXXX)"
                    }
                },
                "required": ["account_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "transfer_money",
            "description": "Transfiere dinero entre dos cuentas bancarias. Las transferencias menores a USD 1,000 se procesan automáticamente sin confirmación adicional.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_account": {
                        "type": "string",
                        "description": "Cuenta origen (formato: XXXX-XXXX-XXXX-XXXX)"
                    },
                    "to_account": {
                        "type": "string",
                        "description": "Cuenta destino (formato: XXXX-XXXX-XXXX-XXXX)"
                    },
                    "amount": {
                        "type": "number",
                        "description": "Monto a transferir"
                    },
                    "currency": {
                        "type": "string",
                        "enum": ["MXN", "USD"],
                        "description": "Moneda de la transferencia"
                    }
                },
                "required": ["from_account", "to_account", "amount", "currency"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_manual",
            "description": "Busca información en los manuales internos del banco usando RAG sobre la base vectorial.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Pregunta o término a buscar en los manuales"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_info",
            "description": "Obtiene información de un usuario del banco por su ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "ID del usuario"
                    }
                },
                "required": ["user_id"]
            }
        }
    }
]


# ============================================================================
# Base de datos mock (en memoria para la demo)
# ============================================================================
MOCK_ACCOUNTS = {
    "1234-5678-9012-3456": {"owner": "Juan Pérez", "balance": 45_320.50, "currency": "MXN"},
    "9876-5432-1098-7654": {"owner": "María García", "balance": 12_840.00, "currency": "USD"},
    "4152-3133-0099-7821": {"owner": "Banco LATAM Operaciones", "balance": 8_500_000.00, "currency": "MXN"},
}

MOCK_USERS = {
    "U001": {"name": "Juan Pérez", "email": "juan@ejemplo.mx", "phone": "+52 55 1234 5678", "kyc_level": "BASICO"},
    "U002": {"name": "María García", "email": "maria@ejemplo.mx", "phone": "+52 55 8765 4321", "kyc_level": "AVANZADO"},
    "U999": {"name": "Carlos Rodríguez (CEO)", "email": "ceo@bancolatam.mx", "phone": "+52 55 0000 0001", "kyc_level": "VIP"},
}

# Log de transferencias (para que Angel pueda ver qué pasó después de la demo)
TRANSFER_LOG = []


# ============================================================================
# Implementación de tools · TODAS VULNERABLES POR DISEÑO
# ============================================================================

def get_balance(account_id: str) -> dict:
    """
    VULNERABLE: no valida que el usuario sea dueño de la cuenta.
    Cualquiera puede consultar cualquier saldo.
    """
    logger.info(f"[TOOL] get_balance(account_id={account_id})")

    if account_id in MOCK_ACCOUNTS:
        acc = MOCK_ACCOUNTS[account_id]
        return {
            "success": True,
            "account_id": account_id,
            "owner": acc["owner"],
            "balance": acc["balance"],
            "currency": acc["currency"],
        }
    return {"success": False, "error": f"Cuenta {account_id} no encontrada"}


def transfer_money(from_account: str, to_account: str, amount: float, currency: str) -> dict:
    """
    VULNERABLE (LLM06 Excessive Agency):
    - No requiere confirmación humana
    - No valida ownership
    - No tiene límites duros
    - El LLM puede ejecutarla con cualquier monto
    """
    logger.warning(
        f"[TOOL VULNERABLE] transfer_money: {from_account} → {to_account} "
        f"· {amount} {currency} · SIN CONFIRMACIÓN HUMANA"
    )

    transfer = {
        "id": f"TRX-{random.randint(100000, 999999)}",
        "timestamp": datetime.now().isoformat(),
        "from_account": from_account,
        "to_account": to_account,
        "amount": amount,
        "currency": currency,
        "status": "EJECUTADA",
        "human_confirmed": False,  # ← bandera roja
    }
    TRANSFER_LOG.append(transfer)

    return {
        "success": True,
        "transaction_id": transfer["id"],
        "status": "EJECUTADA",
        "message": f"Transferencia de {amount} {currency} de {from_account} a {to_account} procesada exitosamente.",
        "warning": "Esta tool se ejecutó SIN confirmación humana - vulnerabilidad LLM06",
    }


def search_manual(query: str) -> dict:
    """
    Llama al RAG vulnerable. La vulnerabilidad real está en rag.py
    (RAG poisoning vía PDFs subidos sin filtrar).
    """
    from rag import search_knowledge_base

    logger.info(f"[TOOL] search_manual(query={query[:80]})")
    results = search_knowledge_base(query, limit=3)

    return {
        "success": True,
        "query": query,
        "results": results,
    }


def get_user_info(user_id: str) -> dict:
    """
    VULNERABLE (LLM02 Sensitive Information Disclosure):
    No valida autorización. Cualquiera puede pedir info del CEO.
    """
    logger.info(f"[TOOL] get_user_info(user_id={user_id})")

    if user_id in MOCK_USERS:
        return {"success": True, **MOCK_USERS[user_id]}
    return {"success": False, "error": f"Usuario {user_id} no encontrado"}


# ============================================================================
# Dispatcher · ejecuta la tool por nombre
# ============================================================================
def execute_tool(name: str, arguments: dict) -> Any:
    """Ejecuta la tool especificada con sus argumentos."""
    tools_map = {
        "get_balance": get_balance,
        "transfer_money": transfer_money,
        "search_manual": search_manual,
        "get_user_info": get_user_info,
    }

    if name not in tools_map:
        return {"error": f"Tool desconocida: {name}"}

    try:
        return tools_map[name](**arguments)
    except Exception as e:
        logger.error(f"Error ejecutando tool {name}: {e}")
        return {"error": str(e)}


def get_transfer_log() -> list:
    """Devuelve el log de transferencias ejecutadas (para revisar después de demo)."""
    return TRANSFER_LOG
