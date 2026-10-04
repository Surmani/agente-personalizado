"""Monta a tela do chat com Gradio a partir do config.yaml (SPEC RF4, RF5, RF13–RF19)."""

from __future__ import annotations

import base64
import html
import mimetypes
from collections.abc import Iterator
from pathlib import Path

import gradio as gr

from agente import textos
from agente.config import COR_TEXTO_TOPO, Config
from agente.provedores import responder

RAIZ = Path(__file__).resolve().parent.parent.parent

# Superfície da área do chat: escura e semi-opaca, para o texto ficar legível
# com qualquer cor de fundo escolhida no config.yaml (RF15).
SUPERFICIE_CHAT = "rgba(11, 15, 25, 0.78)"


def logo_como_data_uri(caminho_logo: str, raiz: Path = RAIZ) -> str:
    """Embute a logo no HTML (assim ela funciona igual no computador e no Hugging Face)."""
    arquivo = raiz / caminho_logo
    tipo = mimetypes.guess_type(arquivo.name)[0] or "image/svg+xml"
    if arquivo.suffix.lower() == ".svg":
        tipo = "image/svg+xml"
    conteudo = base64.b64encode(arquivo.read_bytes()).decode("ascii")
    return f"data:{tipo};base64,{conteudo}"


def html_topo(config: Config, raiz: Path = RAIZ) -> str:
    nome = html.escape(config.assistente.nome)
    descricao = html.escape(config.assistente.descricao)
    logo = logo_como_data_uri(config.aparencia.logo, raiz)
    alt = html.escape(textos.ALT_LOGO.format(nome=config.assistente.nome))
    return f"""
<header id="lms-topo">
  <img src="{logo}" alt="{alt}" style="height:{config.aparencia.logo_tamanho}px">
  <div>
    <h1>{nome}</h1>
    <p>{descricao}</p>
  </div>
</header>
"""


def css(config: Config) -> str:
    a = config.aparencia
    return f"""
:root, .dark {{
  --lms-primaria: {a.cor_primaria};
  --lms-secundaria: {a.cor_secundaria};
  --lms-neutra: {a.cor_neutra};
  --lms-texto: {COR_TEXTO_TOPO};
  --lms-superficie: {SUPERFICIE_CHAT};
}}
html {{
  min-height: 100%;
  background: linear-gradient(135deg, var(--lms-primaria) 0%, var(--lms-secundaria) 100%) !important;
}}
body, gradio-app, .gradio-container, .main, .wrap, .contain {{ background: transparent !important; }}
.gradio-container {{ max-width: 920px !important; margin: 0 auto !important; padding: 16px !important; }}
#lms-topo {{
  display: flex; align-items: center; gap: 20px; padding: 12px 4px 20px; color: var(--lms-texto);
}}
#lms-topo img {{ width: auto; max-width: 40vw; flex-shrink: 0; }}
#lms-topo h1 {{ margin: 0; font-size: clamp(1.4rem, 4vw, 2.1rem); font-weight: 700; color: var(--lms-texto); }}
#lms-topo p {{ margin: 6px 0 0; font-size: clamp(0.95rem, 2.5vw, 1.1rem); color: var(--lms-texto); opacity: 0.85; }}
#lms-chat {{
  background: var(--lms-superficie) !important;
  border: 1px solid color-mix(in srgb, var(--lms-neutra) 35%, transparent);
  border-radius: 16px; padding: 8px; backdrop-filter: blur(6px);
}}
#lms-chat button.example, #lms-chat .example {{
  border: 1px solid var(--lms-neutra) !important; color: var(--lms-texto) !important;
}}
#lms-chat .submit-button {{ background: var(--lms-secundaria) !important; color: #FFFFFF !important; }}
#lms-limpar {{ max-width: 220px; margin-left: auto; }}
#lms-rodape {{ text-align: center; color: var(--lms-texto); opacity: 0.7; font-size: 0.85rem; padding: 8px 0 4px; }}
@media (max-width: 600px) {{
  #lms-topo {{ gap: 12px; padding-bottom: 12px; }}
  #lms-chat .submit-button {{ background: var(--lms-secundaria) !important; color: #FFFFFF !important; }}
#lms-limpar {{ max-width: none; width: 100%; }}
}}
"""


def tema() -> gr.themes.Base:
    return gr.themes.Base(primary_hue="blue", neutral_hue="slate", radius_size="lg")


# Ao abrir a página:
#  1. força o modo escuro do Gradio (o fundo é escuro, então o texto do chat precisa ser claro);
#  2. traduz os rótulos invisíveis (lidos por leitores de tela) que o Gradio deixa em inglês.
JS_AO_CARREGAR = """
() => {
  document.body.classList.add('dark');
  document.documentElement.lang = 'pt-BR';
  const traduzir = () => {
    document.querySelectorAll('[aria-label]').forEach((el) => {
      const rotulo = el.getAttribute('aria-label');
      if (rotulo.startsWith('Select example')) {
        el.setAttribute('aria-label', rotulo.replace(/^Select example (\\d+):/, 'Exemplo $1:'));
      } else if (rotulo === 'chatbot conversation') {
        el.setAttribute('aria-label', 'Conversa com o assistente');
      }
    });
  };
  traduzir();
  new MutationObserver(traduzir).observe(document.body, { childList: true, subtree: true });
}
"""


def criar_funcao_chat(config: Config):
    def conversar(mensagem: str, historico: list) -> Iterator[str]:
        if not (mensagem or "").strip():
            yield textos.MENSAGEM_VAZIA
            return
        resposta = ""
        for pedaco in responder(mensagem.strip(), historico, config):
            resposta += pedaco
            yield resposta

    return conversar


def criar_interface(config: Config, raiz: Path = RAIZ) -> gr.Blocks:
    with gr.Blocks(title=config.assistente.nome, fill_height=False) as demo:
        gr.HTML(html_topo(config, raiz))
        with gr.Column(elem_id="lms-chat"):
            chatbot = gr.Chatbot(
                label=textos.ROTULO_CHAT,
                show_label=False,
                height=520,
                placeholder=textos.CHAT_VAZIO,
                buttons=["copy"],
            )
            chat = gr.ChatInterface(
                fn=criar_funcao_chat(config),
                chatbot=chatbot,
                textbox=gr.Textbox(
                    placeholder=textos.PLACEHOLDER_ENTRADA,
                    label=textos.ROTULO_ENTRADA,
                    show_label=False,
                    submit_btn=textos.BOTAO_ENVIAR,
                    stop_btn=textos.BOTAO_PARAR,
                    autofocus=True,
                ),
                examples=list(config.perguntas_exemplo) or None,
                examples_label=textos.ROTULO_EXEMPLOS,
                run_examples_on_click=True,
                cache_examples=False,
                save_history=False,
                flagging_mode="never",
                fill_height=False,
            )
            limpar = gr.Button(textos.BOTAO_LIMPAR, variant="secondary", size="sm", elem_id="lms-limpar")
            limpar.click(lambda: ([], []), None, [chat.chatbot, chat.chatbot_state], queue=False)
        gr.HTML(f'<div id="lms-rodape">{html.escape(textos.AVISO_RODAPE)}</div>')
    demo.lms_chat = chat  # guardado para os testes conferirem o botão "Parar"
    return demo


def opcoes_de_lancamento(config: Config) -> dict:
    """Parâmetros de aparência que o Gradio 6 recebe no launch()."""
    return {"theme": tema(), "css": css(config), "js": JS_AO_CARREGAR, "footer_links": []}
