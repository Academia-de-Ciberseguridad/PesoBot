"""
Cliente LLM unificado · soporta OpenAI, Anthropic y Ollama.
Todos exponen la misma interfaz async para que el resto del código no se
preocupe del provider.
"""
import os
import json
import httpx
from abc import ABC, abstractmethod
from typing import Optional
from loguru import logger


class LLMClient(ABC):
    """Interfaz abstracta para clientes LLM."""

    @abstractmethod
    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        conversation_history: list = None,
        tools: list = None,
    ) -> dict:
        """
        Genera una respuesta del LLM.

        Returns:
            {
                "content": str,           # Respuesta en texto
                "tool_calls": list | None, # Llamadas a tools (si aplica)
                "usage": dict,             # Tokens usados
            }
        """
        pass


class OpenAIClient(LLMClient):
    """Cliente para OpenAI (GPT-4o, GPT-4o-mini, etc)."""

    def __init__(self):
        from openai import AsyncOpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY no configurada")
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        logger.info(f"OpenAI client inicializado · modelo: {self.model}")

    async def chat(self, system_prompt, user_message, conversation_history=None, tools=None):
        messages = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": user_message})

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        return {
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                }
                for tc in (msg.tool_calls or [])
            ] if msg.tool_calls else None,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
        }


class AnthropicClient(LLMClient):
    """Cliente para Anthropic Claude."""

    def __init__(self):
        from anthropic import AsyncAnthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY no configurada")
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
        logger.info(f"Anthropic client inicializado · modelo: {self.model}")

    async def chat(self, system_prompt, user_message, conversation_history=None, tools=None):
        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": user_message})

        kwargs = {
            "model": self.model,
            "system": system_prompt,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.7,
        }

        if tools:
            # Anthropic usa formato distinto para tools
            kwargs["tools"] = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"]["description"],
                    "input_schema": t["function"]["parameters"],
                }
                for t in tools
            ]

        response = await self.client.messages.create(**kwargs)

        content_text = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input,
                })

        return {
            "content": content_text,
            "tool_calls": tool_calls if tool_calls else None,
            "usage": {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            },
        }


class OllamaClient(LLMClient):
    """Cliente para Ollama local (Llama 3, Mistral, etc)."""

    def __init__(self):
        self.base_url = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
        self.model = os.getenv("OLLAMA_MODEL", "llama3")
        logger.info(f"Ollama client inicializado · {self.base_url} · modelo: {self.model}")

    async def chat(self, system_prompt, user_message, conversation_history=None, tools=None):
        messages = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": user_message})

        # Ollama no soporta tools nativamente en todos los modelos
        # Para la demo basta con chat simple
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.7},
                },
            )
            response.raise_for_status()
            data = response.json()

        return {
            "content": data["message"]["content"],
            "tool_calls": None,
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            },
        }


def get_llm_client() -> LLMClient:
    """Factory para obtener el cliente según LLM_PROVIDER env var."""
    provider = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider == "openai":
        return OpenAIClient()
    elif provider == "anthropic":
        return AnthropicClient()
    elif provider == "ollama":
        return OllamaClient()
    else:
        raise ValueError(f"LLM_PROVIDER desconocido: {provider}. Opciones: openai, anthropic, ollama")
