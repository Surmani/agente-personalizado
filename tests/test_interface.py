"""Testes da interface Gradio (SPEC, seção 6: T12–T13; RF13–RF19, RF24). Sem internet."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agente import interface, textos
from agente.config import carregar_config, validar_texto

RAIZ = Path(__file__).resolve().parent.parent

# Textos padrão do Gradio em inglês que não podem aparecer na tela (T13).
INGLES_PROIBIDO = {"Submit", "Stop", "Clear", "Chatbot", "Textbox", "Message", "Type a message...", "Examples", "Retry"}


@pytest.fixture(scope="module")
def config():
    return carregar_config(RAIZ / "config.yaml")


@pytest.fixture(scope="module")
def demo(config):
    return interface.criar_interface(config)


@pytest.fixture(scope="module")
def configuracao_gradio(demo):
    return demo.get_config_file()


def _textos_visiveis(configuracao: dict) -> list[str]:
    """Todos os textos (strings) das propriedades dos componentes da tela."""
    encontrados: list[str] = []

    def coletar(valor):
        if isinstance(valor, str):
            encontrados.append(valor)
        elif isinstance(valor, dict):
            for chave, item in valor.items():
                if chave not in {"elem_id", "elem_classes", "name", "type", "_selectable"}:
                    coletar(item)
        elif isinstance(valor, list):
            for item in valor:
                coletar(item)

    for componente in configuracao["components"]:
        props = componente.get("props", {})
        if props.get("visible") is False:
            continue
        for chave in ("label", "placeholder", "value", "submit_btn", "stop_btn", "examples", "info"):
            coletar(props.get(chave))
    return encontrados


# --- T12: a interface monta a partir do config.yaml --------------------------


def test_t12_interface_monta_sem_erro(configuracao_gradio, config):
    assert configuracao_gradio["title"] == config.assistente.nome


def test_t12_botoes_de_exemplo_iguais_ao_config(configuracao_gradio, config):
    texto = json.dumps(configuracao_gradio, ensure_ascii=False, default=str)
    for pergunta in config.perguntas_exemplo:
        assert pergunta in texto


def test_t12_sem_perguntas_de_exemplo_tambem_funciona():
    dados = (RAIZ / "config.yaml").read_text(encoding="utf-8")
    inicio = dados.index("perguntas_exemplo:")
    config = validar_texto(dados[:inicio], raiz=RAIZ)
    assert config.perguntas_exemplo == []
    interface.criar_interface(config)


def test_t12_topo_tem_logo_nome_e_descricao(config):
    topo = interface.html_topo(config)
    assert "data:image/svg+xml;base64," in topo
    assert f"height:{config.aparencia.logo_tamanho}px" in topo
    assert "LMS Labs · Assistente" in topo
    assert config.assistente.descricao in topo


def test_t12_topo_escapa_html():
    texto = (
        (RAIZ / "config.yaml")
        .read_text(encoding="utf-8")
        .replace('nome: "LMS Labs · Assistente"', 'nome: "<script>alert(1)</script>"')
    )
    config = validar_texto(texto, raiz=RAIZ)
    topo = interface.html_topo(config)
    assert "<script>" not in topo
    assert "&lt;script&gt;" in topo


def test_t12_css_usa_as_cores_do_config(config):
    estilo = interface.css(config)
    for cor in (config.aparencia.cor_primaria, config.aparencia.cor_secundaria, config.aparencia.cor_neutra):
        assert cor in estilo


def test_t12_logo_png_vira_data_uri(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    assert interface.logo_como_data_uri("assets/logo.png", tmp_path).startswith("data:image/png;base64,")


# --- T13: textos em português ------------------------------------------------


def test_t13_textos_em_portugues_aparecem(configuracao_gradio, demo):
    visiveis = _textos_visiveis(configuracao_gradio)
    juntos = "\n".join(visiveis)
    for texto in (textos.PLACEHOLDER_ENTRADA, textos.BOTAO_ENVIAR, textos.BOTAO_LIMPAR, textos.AVISO_RODAPE):
        assert texto in juntos
    # O botão "Parar" só aparece enquanto a resposta está sendo escrita.
    assert demo.lms_chat.original_stop_btn == textos.BOTAO_PARAR


def test_t13_nenhum_texto_padrao_em_ingles(configuracao_gradio):
    visiveis = set(_textos_visiveis(configuracao_gradio))
    assert not (visiveis & INGLES_PROIBIDO)


def test_t13_rodape_e_limpar_sem_links_do_gradio(config):
    opcoes = interface.opcoes_de_lancamento(config)
    assert opcoes["footer_links"] == []  # esconde "Use via API · Built with Gradio · Settings"
    assert "Exemplo $1:" in opcoes["js"]  # traduz rótulos de acessibilidade


# --- Função do chat ----------------------------------------------------------


def test_chat_mensagem_vazia_nao_chama_a_ia(config, monkeypatch):
    def nao_deveria(*args, **kwargs):
        raise AssertionError("não deveria chamar a IA")

    monkeypatch.setattr(interface, "responder", nao_deveria)
    conversar = interface.criar_funcao_chat(config)
    assert list(conversar("   ", [])) == [textos.MENSAGEM_VAZIA]


def test_chat_acumula_os_pedacos(config, monkeypatch):
    recebido = {}

    def falso(pergunta, historico, cfg):
        recebido.update(pergunta=pergunta, historico=historico)
        yield from ["Olá", ", ", "aluno!"]

    monkeypatch.setattr(interface, "responder", falso)
    conversar = interface.criar_funcao_chat(config)
    historico = [{"role": "user", "content": "Oi"}, {"role": "assistant", "content": "Olá!"}]
    assert list(conversar("  E aí?  ", historico)) == ["Olá", "Olá, ", "Olá, aluno!"]
    assert recebido == {"pergunta": "E aí?", "historico": historico}


# --- RF24: função vazia exigida pelo ZeroGPU ---------------------------------


def _importar_app(ambiente_extra: dict) -> str:
    ambiente = {**os.environ, **ambiente_extra}
    resultado = subprocess.run(
        [sys.executable, "-c", "import app; print(hasattr(app, '_reserva_zerogpu'))"],
        cwd=RAIZ,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert resultado.returncode == 0, resultado.stderr
    return resultado.stdout.strip().splitlines()[-1]


def test_rf24_funcao_zerogpu_existe_no_hugging_face():
    assert _importar_app({"SPACE_ID": "Surmani/agente-personalizado"}) == "True"


def test_rf24_sem_zerogpu_no_computador():
    ambiente = {k: v for k, v in os.environ.items() if k != "SPACE_ID"}
    resultado = subprocess.run(
        [sys.executable, "-c", "import app; print(hasattr(app, '_reserva_zerogpu'))"],
        cwd=RAIZ,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert resultado.stdout.strip().splitlines()[-1] == "False"
