"""Portão de configuração: valida o config.yaml e explica os erros em português.

Uso:  python scripts/validar_config.py [caminho/do/config.yaml]
Sai com código 1 se houver erros (isso faz o GitHub Actions parar a publicação).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from agente.config import ConfigInvalida, avisos, carregar_config  # noqa: E402


def _no_github_actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"


def _resumo_github(linhas: list[str]) -> None:
    """Escreve o resultado na página do workflow (aba Actions → Summary)."""
    destino = os.environ.get("GITHUB_STEP_SUMMARY")
    if destino:
        with open(destino, "a", encoding="utf-8") as arquivo:
            arquivo.write("\n".join(linhas) + "\n")


def main(argv: list[str]) -> int:
    # No Windows o terminal pode não aceitar emojis (✅ ❌); forçamos UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    caminho = Path(argv[1]) if len(argv) > 1 else RAIZ / "config.yaml"
    print(f"🔎 Validando {caminho.name}...\n")

    try:
        config = carregar_config(caminho)
    except ConfigInvalida as erro:
        total = len(erro.erros)
        print(f"Encontrei {total} erro(s):\n")
        for item in erro.erros:
            print(f"{item}\n")
            if _no_github_actions():
                linha = f",line={item.linha}" if item.linha else ""
                texto = f"{item.campo + ': ' if item.campo else ''}{item.problema} Como corrigir: {item.correcao}"
                print(f"::error file={item.arquivo}{linha},title=Erro no {item.arquivo}::{texto}")
        print("🛑 A publicação foi bloqueada. O site antigo continua no ar.")
        _resumo_github(
            [
                f"## ❌ {caminho.name} com {total} erro(s)",
                "A publicação foi **bloqueada** e o site antigo continua no ar. Corrija e salve de novo:",
                "",
                *[
                    f"- {'linha ' + str(e.linha) + ' — ' if e.linha else ''}"
                    f"`{e.campo or e.arquivo}`: {e.problema} **Como corrigir:** {e.correcao}"
                    for e in erro.erros
                ],
            ]
        )
        return 1

    lista_avisos = avisos(config)
    for aviso in lista_avisos:
        print(aviso)
        if _no_github_actions():
            print(f"::warning file={caminho.name},title=Aviso::{aviso}")

    ativos = ", ".join(f"{p.provedor}/{p.modelo}" for p in config.ia.provedores_ativos)
    print(f"✅ {caminho.name} está correto.")
    print(f"   Assistente: {config.assistente.nome}")
    print(f"   Provedores ativos (em ordem): {ativos}")
    _resumo_github([f"## ✅ {caminho.name} está correto", *[f"- {a}" for a in lista_avisos]])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
