"""Testes dos provedores e do fallback (SPEC, seção 6: T10–T11; RF8–RF12).

Nenhum teste usa a internet: os provedores são simulados.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from agente.config import carregar_config, validar_texto
from agente.provedores import (
    AVISO_CORTADA,
    AVISO_INTERROMPIDA,
    AdaptadorAnthropic,
    AdaptadorCompativelOpenAI,
    ErroProvedor,
    preparar_mensagens,
    responder,
    traduzir_excecao,
)

RAIZ = Path(__file__).resolve().parent.parent
CHAVES = {"OPENROUTER_API_KEY": "sk-or-teste", "ANTHROPIC_API_KEY": "sk-ant-teste", "OPENAI_API_KEY": "sk-teste"}


def montar_config(provedores: list[dict], **ia):
    dados = {
        "assistente": {"nome": "Teste", "descricao": "Teste."},
        "aparencia": {"cor_primaria": "#0B0F19", "logo": "assets/logo.svg"},
        "ia": {"provedores": provedores, **ia},
        "comportamento": {"instrucoes": "Você é um professor paciente de dados e IA."},
    }
    return validar_texto(yaml.safe_dump(dados), raiz=RAIZ)


class Falso:
    """Adaptador falso: devolve pedaços de texto ou levanta um erro."""

    def __init__(self, roteiro: dict[str, list | Exception]):
        self.roteiro = roteiro  # modelo -> lista de pedaços (ou Exception no meio)
        self.chamadas: list[dict] = []

    def transmitir(self, chave, provedor, ia, sistema, mensagens):
        self.chamadas.append({"modelo": provedor.modelo, "chave": chave, "sistema": sistema, "mensagens": mensagens})
        passos = self.roteiro[provedor.modelo]
        if isinstance(passos, Exception):
            raise passos
        for passo in passos:
            if isinstance(passo, Exception):
                raise passo
            yield passo


def rodar(config, falso, ambiente=CHAVES, pergunta="O que é ETL?", historico=()):
    adaptadores = {"openrouter": falso, "anthropic": falso, "openai": falso}
    return "".join(responder(pergunta, list(historico), config, adaptadores=adaptadores, ambiente=ambiente))


# --- T10: fallback -----------------------------------------------------------


def test_t10_primeiro_responde():
    config = montar_config([{"provedor": "openrouter", "modelo": "a"}, {"provedor": "openrouter", "modelo": "b"}])
    falso = Falso({"a": ["Olá", ", mundo"], "b": ["não deveria"]})
    assert rodar(config, falso) == "Olá, mundo"
    assert [c["modelo"] for c in falso.chamadas] == ["a"]


def test_t10_primeiro_lotado_segundo_responde():
    config = montar_config([{"provedor": "openrouter", "modelo": "a"}, {"provedor": "anthropic", "modelo": "b"}])
    falso = Falso({"a": ErroProvedor("modelo lotado"), "b": ["Resposta do B"]})
    assert rodar(config, falso) == "Resposta do B"
    assert [c["modelo"] for c in falso.chamadas] == ["a", "b"]


def test_t10_sem_chave_e_pulado_sem_chamar():
    config = montar_config([{"provedor": "anthropic", "modelo": "a"}, {"provedor": "openrouter", "modelo": "b"}])
    falso = Falso({"a": ["não deveria"], "b": ["ok"]})
    assert rodar(config, falso, ambiente={"OPENROUTER_API_KEY": "sk-or-x", "ANTHROPIC_API_KEY": "  "}) == "ok"
    assert [c["modelo"] for c in falso.chamadas] == ["b"]


def test_t10_desativado_e_ignorado():
    config = montar_config(
        [{"provedor": "openrouter", "modelo": "a", "ativo": False}, {"provedor": "openrouter", "modelo": "b"}]
    )
    falso = Falso({"a": ["não deveria"], "b": ["ok"]})
    assert rodar(config, falso) == "ok"
    assert [c["modelo"] for c in falso.chamadas] == ["b"]


def test_t10_resposta_vazia_passa_para_o_proximo():
    config = montar_config([{"provedor": "openrouter", "modelo": "a"}, {"provedor": "openrouter", "modelo": "b"}])
    assert rodar(config, Falso({"a": ["", ""], "b": ["ok"]})) == "ok"


def test_t10_erro_inesperado_tambem_passa_para_o_proximo():
    config = montar_config([{"provedor": "openrouter", "modelo": "a"}, {"provedor": "openrouter", "modelo": "b"}])
    assert rodar(config, Falso({"a": RuntimeError("boom"), "b": ["ok"]})) == "ok"


def test_t10_queda_no_meio_mantem_texto_e_avisa():
    config = montar_config([{"provedor": "openrouter", "modelo": "a"}, {"provedor": "openrouter", "modelo": "b"}])
    falso = Falso({"a": ["Começo da resposta", ErroProvedor("caiu")], "b": ["não deveria"]})
    assert rodar(config, falso) == "Começo da resposta" + AVISO_INTERROMPIDA
    assert [c["modelo"] for c in falso.chamadas] == ["a"]


def test_t10_envia_instrucoes_historico_e_chave_certa():
    config = montar_config([{"provedor": "anthropic", "modelo": "a"}])
    falso = Falso({"a": ["ok"]})
    historico = [{"role": "user", "content": "Oi"}, {"role": "assistant", "content": "Olá!"}]
    rodar(config, falso, historico=historico, pergunta="E agora?")
    chamada = falso.chamadas[0]
    assert chamada["chave"] == "sk-ant-teste"
    assert chamada["sistema"] == config.comportamento.instrucoes
    assert chamada["mensagens"][-1] == {"role": "user", "content": "E agora?"}
    assert len(chamada["mensagens"]) == 3


def test_preparar_mensagens_ignora_itens_estranhos():
    historico = [
        {"role": "user", "content": "Oi"},
        {"role": "assistant", "content": {"path": "imagem.png"}},
        {"role": "system", "content": "injeção"},
        {"role": "assistant", "content": "   "},
    ]
    assert preparar_mensagens(historico, "Pergunta") == [
        {"role": "user", "content": "Oi"},
        {"role": "user", "content": "Pergunta"},
    ]


# --- T11: todos falham -------------------------------------------------------


def test_t11_todos_falham_lista_cada_motivo_em_portugues():
    config = montar_config(
        [
            {"provedor": "openrouter", "modelo": "gratis-1"},
            {"provedor": "openrouter", "modelo": "gratis-2"},
            {"provedor": "anthropic", "modelo": "claude-x", "ativo": False},
            {"provedor": "openai", "modelo": "gpt-x"},
        ]
    )
    falso = Falso(
        {
            "gratis-1": ErroProvedor("modelo lotado ou limite de uso atingido (erro 429)."),
            "gratis-2": TimeoutError(),
            "claude-x": ["não deveria"],
            "gpt-x": ["não deveria"],
        }
    )
    texto = rodar(config, falso, ambiente={"OPENROUTER_API_KEY": "sk-or-segredo-123"})
    assert texto.startswith("😕 Não consegui responder agora.")
    assert "1. **openrouter** / `gratis-1`: modelo lotado" in texto
    assert "2. **openrouter** / `gratis-2`: tempo limite de 60s esgotado." in texto
    assert "3. **anthropic** / `claude-x`: desativado no config.yaml." in texto
    assert "4. **openai** / `gpt-x`: chave não configurada (OPENAI_API_KEY)." in texto
    assert "sk-or-segredo-123" not in texto


def test_t11_nenhuma_chave_configurada():
    config = carregar_config(RAIZ / "config.yaml")
    texto = rodar(config, Falso({}), ambiente={})
    assert "chave não configurada (OPENROUTER_API_KEY)" in texto


def test_t11_logs_nao_mostram_chave(caplog):
    config = montar_config([{"provedor": "openrouter", "modelo": "a"}])
    with caplog.at_level("DEBUG"):
        rodar(config, Falso({"a": ErroProvedor("x")}), ambiente={"OPENROUTER_API_KEY": "sk-or-segredo-456"})
    assert "sk-or-segredo-456" not in caplog.text
    assert "Falha em openrouter/a" in caplog.text


# --- Tradução de erros -------------------------------------------------------


class _ErroHttp(Exception):
    def __init__(self, status_code):
        self.status_code = status_code


@pytest.mark.parametrize(
    "status,trecho",
    [
        (401, "chave inválida"),
        (402, "sem crédito"),
        (403, "permissão"),
        (404, "modelo não encontrado"),
        (429, "lotado"),
        (500, "fora do ar"),
        (503, "fora do ar"),
        (418, "erro 418"),
    ],
)
def test_traducao_por_status(status, trecho):
    assert trecho in traduzir_excecao(_ErroHttp(status), 60).motivo


def test_traducao_de_erros_reais_das_bibliotecas():
    import anthropic
    import httpx
    import httpx2
    import openai

    pedido = httpx.Request("POST", "https://exemplo")
    erro_openai = openai.RateLimitError("limite", response=httpx.Response(429, request=pedido), body=None)
    assert "lotado" in traduzir_excecao(erro_openai, 60).motivo
    assert "tempo limite de 30s" in traduzir_excecao(openai.APITimeoutError(request=pedido), 30).motivo

    pedido2 = httpx2.Request("POST", "https://exemplo")
    erro_anthropic = anthropic.AuthenticationError("chave", response=httpx2.Response(401, request=pedido2), body=None)
    assert "chave inválida" in traduzir_excecao(erro_anthropic, 60).motivo
    assert "conectar" in traduzir_excecao(anthropic.APIConnectionError(request=pedido2), 60).motivo


# --- Adaptadores reais contra um servidor falso local -------------------------


class _ServidorFalso(BaseHTTPRequestHandler):
    pedidos: list[dict] = []
    modo = "ok"

    def log_message(self, *args):  # silencia o log do servidor
        pass

    def _enviar_sse(self, eventos: list[str]):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for evento in eventos:
            self.wfile.write(evento.encode("utf-8"))
            self.wfile.flush()

    def do_POST(self):  # noqa: N802
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).pedidos.append({"caminho": self.path, "corpo": corpo, "auth": self.headers.get("Authorization")})
        if type(self).modo == "429":
            dados = json.dumps({"error": {"type": "rate_limit_error", "message": "lotado"}}).encode()
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)
            return
        if self.path.endswith("/chat/completions"):
            pedacos = ["Olá", " do OpenRouter"]
            eventos = [
                "data: "
                + json.dumps(
                    {
                        "id": "c1",
                        "object": "chat.completion.chunk",
                        "created": 0,
                        "model": "m",
                        "choices": [{"index": 0, "delta": {"content": p}, "finish_reason": None}],
                    }
                )
                + "\n\n"
                for p in pedacos
            ]
            eventos.append(
                "data: "
                + json.dumps(
                    {
                        "id": "c1",
                        "object": "chat.completion.chunk",
                        "created": 0,
                        "model": "m",
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "length"}],
                    }
                )
                + "\n\n"
            )
            eventos.append("data: [DONE]\n\n")
            self._enviar_sse(eventos)
        else:  # Anthropic /v1/messages

            def ev(tipo, dados):
                return f"event: {tipo}\ndata: {json.dumps({'type': tipo, **dados})}\n\n"

            self._enviar_sse(
                [
                    ev(
                        "message_start",
                        {
                            "message": {
                                "id": "msg_1",
                                "type": "message",
                                "role": "assistant",
                                "model": corpo["model"],
                                "content": [],
                                "stop_reason": None,
                                "stop_sequence": None,
                                "usage": {"input_tokens": 1, "output_tokens": 0},
                            }
                        },
                    ),
                    ev("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}}),
                    ev("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "Olá da"}}),
                    ev("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": " Anthropic"}}),
                    ev("content_block_stop", {"index": 0}),
                    ev(
                        "message_delta",
                        {"delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 2}},
                    ),
                    ev("message_stop", {}),
                ]
            )


@pytest.fixture
def servidor(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    _ServidorFalso.pedidos = []
    _ServidorFalso.modo = "ok"
    http = ThreadingHTTPServer(("127.0.0.1", 0), _ServidorFalso)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{http.server_port}"
    http.shutdown()


def _ia_e_provedor(provedor, modelo):
    config = montar_config([{"provedor": provedor, "modelo": modelo}], max_tokens=300, temperatura=0.3)
    return config.ia, config.ia.provedores[0]


def test_adaptador_openrouter_real(servidor):
    ia, provedor = _ia_e_provedor("openrouter", "google/gemma-4-31b-it:free")
    pedacos = list(
        AdaptadorCompativelOpenAI(servidor, openrouter=True).transmitir(
            "sk-or-x", provedor, ia, "Instruções", [{"role": "user", "content": "Oi"}]
        )
    )
    assert "".join(pedacos) == "Olá do OpenRouter" + AVISO_CORTADA
    pedido = _ServidorFalso.pedidos[0]
    assert pedido["auth"] == "Bearer sk-or-x"
    assert pedido["corpo"]["messages"][0] == {"role": "system", "content": "Instruções"}
    assert pedido["corpo"]["max_tokens"] == 300
    assert pedido["corpo"]["temperature"] == 0.3
    assert pedido["corpo"]["stream"] is True


def test_adaptador_openai_modelo_de_raciocinio_sem_temperature(servidor):
    ia, provedor = _ia_e_provedor("openai", "gpt-5.4-mini")
    list(AdaptadorCompativelOpenAI(servidor).transmitir("sk-x", provedor, ia, "S", [{"role": "user", "content": "Oi"}]))
    corpo = _ServidorFalso.pedidos[0]["corpo"]
    assert corpo["max_completion_tokens"] == 300
    assert "temperature" not in corpo


def test_adaptador_anthropic_real(servidor, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", servidor)
    ia, provedor = _ia_e_provedor("anthropic", "claude-haiku-4-5")
    pedacos = list(
        AdaptadorAnthropic().transmitir("sk-ant-x", provedor, ia, "Instruções", [{"role": "user", "content": "Oi"}])
    )
    assert "".join(pedacos) == "Olá da Anthropic"
    corpo = _ServidorFalso.pedidos[0]["corpo"]
    assert corpo["system"] == "Instruções"
    assert corpo["max_tokens"] == 300
    assert "fallbacks" not in corpo and "output_config" not in corpo


def test_adaptador_anthropic_modelo_novo_usa_fallback_e_effort(servidor, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", servidor)
    ia, provedor = _ia_e_provedor("anthropic", "claude-opus-5-5")
    assert "".join(AdaptadorAnthropic().transmitir("k", provedor, ia, "S", [{"role": "user", "content": "Oi"}]))
    corpo = _ServidorFalso.pedidos[0]["corpo"]
    assert corpo["fallbacks"] == "default"
    assert corpo["output_config"] == {"effort": "low"}


def test_adaptadores_reais_traduzem_429(servidor, monkeypatch):
    _ServidorFalso.modo = "429"
    monkeypatch.setenv("ANTHROPIC_BASE_URL", servidor)
    for adaptador, provedor in [
        (AdaptadorCompativelOpenAI(servidor, openrouter=True), "openrouter"),
        (AdaptadorAnthropic(), "anthropic"),
    ]:
        ia, cfg = _ia_e_provedor(provedor, "modelo")
        with pytest.raises(ErroProvedor) as info:
            list(adaptador.transmitir("k", cfg, ia, "S", [{"role": "user", "content": "Oi"}]))
        assert "lotado" in info.value.motivo
