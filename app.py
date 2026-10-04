"""Ponto de entrada do assistente (o Hugging Face procura este arquivo).

Rodar no computador:  python app.py   →   http://localhost:7860
"""

import os

# ZeroGPU (Fase B): o Hugging Face exige pelo menos uma função marcada com @spaces.GPU,
# senão o Space não inicia. A IA roda no OpenRouter, não aqui; por isso a função
# abaixo é vazia e NUNCA é chamada (não gasta a cota de GPU). Ver SPEC RF24.
# A biblioteca "spaces" precisa ser importada antes de tudo.
NO_HUGGING_FACE = bool(os.environ.get("SPACE_ID"))
if NO_HUGGING_FACE:
    import spaces

    @spaces.GPU(duration=1)
    def _reserva_zerogpu():
        return None


import logging  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

from dotenv import load_dotenv  # noqa: E402

from agente.config import ConfigInvalida, avisos, carregar_config  # noqa: E402
from agente.interface import criar_interface, opcoes_de_lancamento  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("agente")


def principal():
    load_dotenv(RAIZ / ".env")  # só no computador; no Hugging Face as chaves vêm dos Secrets
    try:
        config = carregar_config(RAIZ / "config.yaml")
    except ConfigInvalida as erro:
        print("O config.yaml tem erros e o app não pode iniciar:\n", file=sys.stderr)
        print(erro, file=sys.stderr)
        sys.exit(1)
    for aviso in avisos(config):
        log.warning(aviso)
    log.info("Provedores ativos: %s", ", ".join(f"{p.provedor}/{p.modelo}" for p in config.ia.provedores_ativos))

    demo = criar_interface(config)
    porta = int(os.environ.get("PORT", os.environ.get("GRADIO_SERVER_PORT", "7860")))
    demo.queue().launch(
        server_name="0.0.0.0" if NO_HUGGING_FACE else "127.0.0.1", server_port=porta, **opcoes_de_lancamento(config)
    )


if __name__ == "__main__":
    principal()
