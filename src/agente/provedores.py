"""Conversa com os provedores de IA (OpenRouter, Anthropic, OpenAI) com fallback automático.

Fluxo (SPEC RF8–RF12):
  1. Tenta os provedores na ordem do config.yaml.
  2. Pula os desativados e os que não têm chave configurada.
  3. Se um provedor falhar ANTES do primeiro pedaço de texto, tenta o próximo.
  4. Se falhar NO MEIO da resposta, mantém o texto parcial e avisa.
  5. Se todos falharem, devolve uma mensagem em português com o motivo de cada um.

As chaves vêm só de variáveis de ambiente e nunca aparecem em mensagens nem logs.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Protocol

from agente.config import Config, Ia, Provedor

log = logging.getLogger("agente.provedores")

# Nome da variável de ambiente (Secret) de cada provedor.
VARIAVEIS_DE_CHAVE = {
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}

URL_OPENROUTER = "https://openrouter.ai/api/v1"

AVISO_INTERROMPIDA = "\n\n⚠️ A resposta foi interrompida. Tente perguntar de novo."
AVISO_CORTADA = "\n\n_(A resposta atingiu o limite de tamanho e foi cortada.)_"


class ErroProvedor(Exception):
    """Falha de um provedor, já com o motivo em português (sem dados sensíveis)."""

    def __init__(self, motivo: str):
        self.motivo = motivo
        super().__init__(motivo)


@dataclass(frozen=True)
class Falha:
    provedor: str
    modelo: str
    motivo: str


Mensagens = list[dict[str, str]]


class Adaptador(Protocol):
    """Fala com um provedor e devolve a resposta em pedaços de texto (streaming)."""

    def transmitir(self, chave: str, provedor: Provedor, ia: Ia, sistema: str, mensagens: Mensagens) -> Iterator[str]:
        """Levanta ErroProvedor quando algo dá errado."""
        ...


# ---------------------------------------------------------------------------
# Tradução de erros das bibliotecas para português
# ---------------------------------------------------------------------------

MOTIVOS_POR_STATUS = {
    400: "o provedor recusou o pedido (erro 400). Confira o nome do modelo e o tamanho da conversa.",
    401: "chave inválida ou expirada (erro 401). Gere uma nova chave no site do provedor.",
    402: "sem crédito na conta do provedor (erro 402).",
    403: "a chave não tem permissão para usar este modelo (erro 403).",
    404: "modelo não encontrado (erro 404). Confira o nome exato no site do provedor.",
    408: "o provedor demorou demais para responder (erro 408).",
    413: "a conversa ficou longa demais para este modelo (erro 413). Clique em Limpar conversa.",
    429: "modelo lotado ou limite de uso atingido (erro 429). Tente em alguns minutos.",
}


def traduzir_excecao(erro: BaseException, tempo_limite: int) -> ErroProvedor:
    """Converte qualquer erro das bibliotecas openai/anthropic em ErroProvedor."""
    if isinstance(erro, ErroProvedor):
        return erro
    nome = type(erro).__name__
    if "Timeout" in nome or isinstance(erro, TimeoutError):
        return ErroProvedor(f"tempo limite de {tempo_limite}s esgotado.")
    if "Connection" in nome:
        return ErroProvedor("não foi possível conectar ao provedor (internet ou provedor fora do ar).")
    status = getattr(erro, "status_code", None)
    if isinstance(status, int):
        if status in MOTIVOS_POR_STATUS:
            return ErroProvedor(MOTIVOS_POR_STATUS[status])
        if status >= 500:
            return ErroProvedor(f"o provedor está fora do ar ou instável (erro {status}). Tente mais tarde.")
        return ErroProvedor(f"erro inesperado do provedor (erro {status}).")
    return ErroProvedor(f"erro inesperado ({nome}).")


# ---------------------------------------------------------------------------
# Adaptadores reais
# ---------------------------------------------------------------------------

# Modelos de raciocínio da OpenAI não aceitam o parâmetro temperature.
_PREFIXOS_SEM_TEMPERATURA_OPENAI = ("gpt-5", "o1", "o3", "o4")

# Modelos Claude atuais: aceitam o fallback de recusa no servidor (fallbacks: "default").
_CLAUDE_COM_FALLBACK = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
# Modelos Claude atuais com "effort" (esforço de raciocínio). "low" deixa o chat rápido e
# reserva os tokens da resposta para o texto, e não para o raciocínio interno.
_PREFIXOS_CLAUDE_COM_EFFORT = (
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
)


class AdaptadorCompativelOpenAI:
    """OpenRouter e OpenAI usam o mesmo formato de API (chat completions)."""

    def __init__(self, url_base: str | None = None, openrouter: bool = False):
        self.url_base = url_base
        self.openrouter = openrouter

    def transmitir(self, chave: str, provedor: Provedor, ia: Ia, sistema: str, mensagens: Mensagens) -> Iterator[str]:
        import openai

        cliente = openai.OpenAI(api_key=chave, base_url=self.url_base, timeout=ia.tempo_limite_segundos, max_retries=0)
        parametros: dict = {
            "model": provedor.modelo,
            "messages": [{"role": "system", "content": sistema}, *mensagens],
            "stream": True,
        }
        if self.openrouter:
            parametros["max_tokens"] = ia.max_tokens
            parametros["temperature"] = ia.temperatura
        else:  # OpenAI
            parametros["max_completion_tokens"] = ia.max_tokens
            if not provedor.modelo.startswith(_PREFIXOS_SEM_TEMPERATURA_OPENAI):
                parametros["temperature"] = ia.temperatura

        try:
            fluxo = cliente.chat.completions.create(**parametros)
            cortada = False
            for pedaco in fluxo:
                if not pedaco.choices:
                    continue
                escolha = pedaco.choices[0]
                texto = getattr(escolha.delta, "content", None)
                if texto:
                    yield texto
                if escolha.finish_reason == "length":
                    cortada = True
            if cortada:
                yield AVISO_CORTADA
        except Exception as erro:  # noqa: BLE001 — qualquer falha vira motivo em português
            raise traduzir_excecao(erro, ia.tempo_limite_segundos) from None


class AdaptadorAnthropic:
    def transmitir(self, chave: str, provedor: Provedor, ia: Ia, sistema: str, mensagens: Mensagens) -> Iterator[str]:
        import anthropic

        cliente = anthropic.Anthropic(api_key=chave, timeout=ia.tempo_limite_segundos, max_retries=0)
        # A biblioteca atual da Anthropic não envia "temperature": os modelos Claude
        # mais novos não aceitam esse ajuste. Por isso ia.temperatura é ignorada aqui.
        parametros: dict = {
            "model": provedor.modelo,
            "max_tokens": ia.max_tokens,
            "system": sistema,
            "messages": mensagens,
        }
        if provedor.modelo.startswith(_PREFIXOS_CLAUDE_COM_EFFORT):
            parametros["output_config"] = {"effort": "low"}

        try:
            if provedor.modelo in _CLAUDE_COM_FALLBACK:
                # Se o modelo recusar por segurança, o próprio servidor tenta o modelo recomendado.
                gerenciador = cliente.beta.messages.stream(
                    **parametros, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                )
            else:
                gerenciador = cliente.messages.stream(**parametros)
            with gerenciador as fluxo:
                for texto in fluxo.text_stream:
                    if texto:
                        yield texto
                final = fluxo.get_final_message()
            if final.stop_reason == "refusal":
                raise ErroProvedor("o modelo recusou responder a esta pergunta.")
            if final.stop_reason == "max_tokens":
                yield AVISO_CORTADA
        except Exception as erro:  # noqa: BLE001
            raise traduzir_excecao(erro, ia.tempo_limite_segundos) from None


ADAPTADORES: dict[str, Adaptador] = {
    "openrouter": AdaptadorCompativelOpenAI(URL_OPENROUTER, openrouter=True),
    "openai": AdaptadorCompativelOpenAI(),
    "anthropic": AdaptadorAnthropic(),
}


# ---------------------------------------------------------------------------
# Orquestração com fallback
# ---------------------------------------------------------------------------


def preparar_mensagens(historico: Iterable[Mapping], pergunta: str) -> Mensagens:
    """Mantém só mensagens de texto de usuário/assistente e acrescenta a pergunta nova."""
    mensagens: Mensagens = []
    for item in historico or []:
        papel, conteudo = item.get("role"), item.get("content")
        if papel in ("user", "assistant") and isinstance(conteudo, str) and conteudo.strip():
            mensagens.append({"role": papel, "content": conteudo})
    mensagens.append({"role": "user", "content": pergunta})
    return mensagens


def mensagem_de_falhas(falhas: list[Falha]) -> str:
    linhas = ["😕 Não consegui responder agora. Tentei:", ""]
    for numero, falha in enumerate(falhas, start=1):
        linhas.append(f"{numero}. **{falha.provedor}** / `{falha.modelo}`: {falha.motivo}")
    if not falhas:
        linhas.append("_(nenhum provedor configurado)_")
    return "\n".join(linhas)


def responder(
    pergunta: str,
    historico: Iterable[Mapping],
    config: Config,
    adaptadores: Mapping[str, Adaptador] | None = None,
    ambiente: Mapping[str, str] | None = None,
    ao_responder: Callable[[Provedor], None] | None = None,
) -> Iterator[str]:
    """Gera a resposta em pedaços. Nunca levanta exceção: falhas viram texto para o chat."""
    adaptadores = ADAPTADORES if adaptadores is None else adaptadores
    ambiente = os.environ if ambiente is None else ambiente
    mensagens = preparar_mensagens(historico, pergunta)
    sistema = config.comportamento.instrucoes
    falhas: list[Falha] = []

    for provedor in config.ia.provedores:
        if not provedor.ativo:
            falhas.append(Falha(provedor.provedor, provedor.modelo, "desativado no config.yaml."))
            continue
        variavel = VARIAVEIS_DE_CHAVE[provedor.provedor]
        chave = (ambiente.get(variavel) or "").strip()
        if not chave:
            falhas.append(Falha(provedor.provedor, provedor.modelo, f"chave não configurada ({variavel})."))
            continue

        recebeu_texto = False
        try:
            for pedaco in adaptadores[provedor.provedor].transmitir(chave, provedor, config.ia, sistema, mensagens):
                if pedaco:
                    recebeu_texto = True
                    yield pedaco
            if not recebeu_texto:
                raise ErroProvedor("o provedor devolveu uma resposta vazia.")
        except Exception as erro:  # noqa: BLE001
            motivo = traduzir_excecao(erro, config.ia.tempo_limite_segundos).motivo
            log.warning("Falha em %s/%s: %s", provedor.provedor, provedor.modelo, motivo)
            if recebeu_texto:
                yield AVISO_INTERROMPIDA
                return
            falhas.append(Falha(provedor.provedor, provedor.modelo, motivo))
            continue

        log.info("Respondido por %s/%s", provedor.provedor, provedor.modelo)
        if ao_responder:
            ao_responder(provedor)
        return

    log.error("Nenhum provedor respondeu (%d tentativas).", len(falhas))
    yield mensagem_de_falhas(falhas)
