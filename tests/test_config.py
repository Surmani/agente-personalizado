"""Testes do portão de configuração (SPEC, seção 6: T1–T8 e T16)."""

from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from agente.config import (
    COR_NEUTRA_PADRAO,
    ConfigInvalida,
    avisos,
    carregar_config,
    contraste,
    validar_texto,
)

RAIZ = Path(__file__).resolve().parent.parent

BASE = {
    "assistente": {"nome": "Assistente Teste", "descricao": "Uma descrição qualquer."},
    "aparencia": {"cor_primaria": "#0B0F19", "logo": "assets/logo.svg"},
    "ia": {"provedores": [{"provedor": "openrouter", "modelo": "modelo/teste:free"}]},
    "comportamento": {"instrucoes": "Você é um professor paciente de dados e IA."},
}


@pytest.fixture
def pasta(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "logo.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    return tmp_path


def montar(**mudancas) -> dict:
    """Cópia da config base com mudanças no formato bloco__campo=valor (None apaga)."""
    dados = copy.deepcopy(BASE)
    for chave, valor in mudancas.items():
        partes = chave.split("__")
        alvo = dados
        for parte in partes[:-1]:
            alvo = alvo.setdefault(parte, {})
        if valor is None:
            alvo.pop(partes[-1], None)
        else:
            alvo[partes[-1]] = valor
    return dados


def validar(dados: dict | str, pasta: Path):
    texto = dados if isinstance(dados, str) else yaml.safe_dump(dados, allow_unicode=True)
    return validar_texto(texto, raiz=pasta)


def erros_de(dados: dict | str, pasta: Path) -> list:
    with pytest.raises(ConfigInvalida) as info:
        validar(dados, pasta)
    return info.value.erros


def campos(erros) -> set[str]:
    return {e.campo for e in erros}


# --- Config real do projeto ------------------------------------------------


def test_config_do_projeto_e_valida():
    config = carregar_config(RAIZ / "config.yaml")
    assert config.assistente.nome
    assert config.ia.provedores_ativos


def test_config_minima_recebe_padroes(pasta):
    config = validar(BASE, pasta)
    assert config.aparencia.cor_secundaria == config.aparencia.cor_primaria
    assert config.aparencia.cor_neutra == COR_NEUTRA_PADRAO
    assert config.aparencia.logo_tamanho == 96
    assert config.ia.max_tokens == 1024
    assert config.ia.temperatura == 0.7
    assert config.ia.tempo_limite_segundos == 60
    assert config.ia.provedores[0].ativo is True
    assert config.perguntas_exemplo == []


# --- T1: arquivo existe e é YAML válido -------------------------------------


def test_t1_arquivo_inexistente(tmp_path):
    with pytest.raises(ConfigInvalida) as info:
        carregar_config(tmp_path / "config.yaml")
    assert "não foi encontrado" in info.value.erros[0].problema


def test_t1_arquivo_vazio(pasta):
    assert "vazio" in erros_de("", pasta)[0].problema


def test_t1_tab_no_recuo(pasta):
    erro = erros_de("assistente:\n\tnome: x\n", pasta)[0]
    assert "TAB" in erro.problema
    assert erro.linha == 2


def test_t1_dois_pontos_sem_aspas(pasta):
    erro = erros_de("assistente:\n  nome: Lucas: professor\n", pasta)[0]
    assert "YAML" in erro.problema
    assert "aspas" in erro.correcao
    assert erro.linha == 2


def test_t1_aspas_nao_fechadas(pasta):
    erro = erros_de('assistente:\n  nome: "Lucas\n  descricao: x\n', pasta)[0]
    assert "YAML" in erro.problema


def test_t1_campo_repetido(pasta):
    texto = yaml.safe_dump(BASE, allow_unicode=True) + "assistente:\n  nome: outro\n"
    assert any("repetido" in e.problema for e in erros_de(texto, pasta))


# --- T2: obrigatórios presentes e não vazios --------------------------------


@pytest.mark.parametrize(
    "campo",
    [
        "assistente__nome",
        "assistente__descricao",
        "aparencia__cor_primaria",
        "aparencia__logo",
        "comportamento__instrucoes",
        "ia__provedores",
    ],
)
def test_t2_obrigatorio_faltando(pasta, campo):
    erros = erros_de(montar(**{campo: None}), pasta)
    assert campo.replace("__", ".") in campos(erros)
    assert any("obrigatório" in e.problema for e in erros)


@pytest.mark.parametrize("bloco", ["assistente", "aparencia", "ia", "comportamento"])
def test_t2_bloco_faltando(pasta, bloco):
    dados = copy.deepcopy(BASE)
    del dados[bloco]
    assert bloco in campos(erros_de(dados, pasta))


@pytest.mark.parametrize("valor", ["", "   "])
def test_t2_texto_vazio(pasta, valor):
    erros = erros_de(montar(assistente__nome=valor), pasta)
    assert erros[0].campo == "assistente.nome"
    assert "vazio" in erros[0].problema


def test_t2_mensagem_tem_linha_e_correcao(pasta):
    texto = yaml.safe_dump(montar(assistente__nome=""), allow_unicode=True, sort_keys=False)
    erro = erros_de(texto, pasta)[0]
    assert erro.linha == 2
    assert "Como corrigir" in str(erro)


# --- T3: cores ---------------------------------------------------------------


@pytest.mark.parametrize("cor", ["azul", "#FFF", "2563EB", "#2563EG", "#2563EB00"])
def test_t3_cor_invalida(pasta, cor):
    erro = erros_de(montar(aparencia__cor_primaria=cor), pasta)[0]
    assert "não é uma cor válida" in erro.problema
    assert "#RRGGBB" in erro.correcao


def test_t3_cor_sem_aspas_vira_comentario(pasta):
    texto = yaml.safe_dump(BASE, allow_unicode=True).replace("cor_primaria: '#0B0F19'", "cor_primaria: #0B0F19")
    erro = erros_de(texto, pasta)[0]
    assert "aspas" in erro.correcao


def test_t3_cores_validas_sao_normalizadas(pasta):
    config = validar(montar(aparencia__cor_primaria="#0b0f19", aparencia__cor_secundaria="#2563eb"), pasta)
    assert config.aparencia.cor_primaria == "#0B0F19"
    assert config.aparencia.cor_secundaria == "#2563EB"


# --- T4: logo ----------------------------------------------------------------


def test_t4_logo_inexistente(pasta):
    assert "não existe" in erros_de(montar(aparencia__logo="assets/outra.svg"), pasta)[0].problema


def test_t4_logo_fora_de_assets(pasta):
    for caminho in ["logo.svg", "../assets/logo.svg", "assets/../config.yaml"]:
        assert "fora da pasta" in erros_de(montar(aparencia__logo=caminho), pasta)[0].problema


def test_t4_logo_extensao_invalida(pasta):
    (pasta / "assets" / "logo.gif").write_bytes(b"GIF89a")
    assert "extensão" in erros_de(montar(aparencia__logo="assets/logo.gif"), pasta)[0].problema


def test_t4_logo_grande_demais(pasta):
    (pasta / "assets" / "grande.png").write_bytes(b"0" * (1024 * 1024 + 1))
    assert "máximo 1 MB" in erros_de(montar(aparencia__logo="assets/grande.png"), pasta)[0].problema


@pytest.mark.parametrize("tamanho", [31, 257, "grande", 96.5])
def test_t4_logo_tamanho_invalido(pasta, tamanho):
    assert "aparencia.logo_tamanho" in campos(erros_de(montar(aparencia__logo_tamanho=tamanho), pasta))


def test_t4_logos_do_projeto_existem():
    for nome in ["logo.svg", "logo-claro.svg"]:
        assert (RAIZ / "assets" / nome).is_file()


# --- T5: provedores ----------------------------------------------------------


def test_t5_provedor_desconhecido(pasta):
    dados = montar(ia__provedores=[{"provedor": "gemini", "modelo": "x"}])
    assert "não é um provedor aceito" in erros_de(dados, pasta)[0].problema


def test_t5_modelo_vazio(pasta):
    dados = montar(ia__provedores=[{"provedor": "openrouter", "modelo": " "}])
    assert erros_de(dados, pasta)[0].campo == "ia.provedores[0].modelo"


def test_t5_nenhum_ativo(pasta):
    dados = montar(ia__provedores=[{"provedor": "openrouter", "modelo": "x", "ativo": False}])
    assert "nenhum provedor está ativo" in erros_de(dados, pasta)[0].problema


def test_t5_repetido(pasta):
    item = {"provedor": "openrouter", "modelo": "x"}
    assert "repetido" in erros_de(montar(ia__provedores=[item, dict(item)]), pasta)[0].problema


def test_t5_lista_vazia_ou_grande(pasta):
    assert "vazia" in erros_de(montar(ia__provedores=[]), pasta)[0].problema
    muitos = [{"provedor": "openrouter", "modelo": f"m{i}"} for i in range(11)]
    assert "itens demais" in erros_de(montar(ia__provedores=muitos), pasta)[0].problema


def test_t5_ativo_precisa_ser_booleano(pasta):
    dados = montar(ia__provedores=[{"provedor": "openrouter", "modelo": "x", "ativo": "sim"}])
    assert "true ou false" in erros_de(dados, pasta)[0].problema


def test_t5_ordem_preservada(pasta):
    lista = [
        {"provedor": "openrouter", "modelo": "a"},
        {"provedor": "anthropic", "modelo": "b", "ativo": False},
        {"provedor": "openai", "modelo": "c"},
    ]
    config = validar(montar(ia__provedores=lista), pasta)
    assert [p.modelo for p in config.ia.provedores_ativos] == ["a", "c"]


# --- T6: faixas numéricas ----------------------------------------------------


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("max_tokens", 63),
        ("max_tokens", 4097),
        ("max_tokens", "1024"),
        ("temperatura", -0.1),
        ("temperatura", 2.1),
        ("temperatura", "0.7"),
        ("tempo_limite_segundos", 4),
        ("tempo_limite_segundos", 121),
    ],
)
def test_t6_fora_da_faixa(pasta, campo, valor):
    erro = erros_de(montar(**{f"ia__{campo}": valor}), pasta)[0]
    assert erro.campo == f"ia.{campo}"
    assert " a " in erro.correcao  # a mensagem informa a faixa "de X a Y"


@pytest.mark.parametrize(
    "campo,valor", [("max_tokens", 64), ("max_tokens", 4096), ("temperatura", 0), ("temperatura", 2.0)]
)
def test_t6_limites_aceitos(pasta, campo, valor):
    validar(montar(**{f"ia__{campo}": valor}), pasta)


# --- T7: perguntas de exemplo ------------------------------------------------


def test_t7_perguntas_validas(pasta):
    config = validar(montar(perguntas_exemplo=["O que é ETL?", "O que é RAG?"]), pasta)
    assert config.perguntas_exemplo == ["O que é ETL?", "O que é RAG?"]


@pytest.mark.parametrize(
    "perguntas,trecho",
    [
        ([f"Pergunta {i}?" for i in range(7)], "itens demais"),
        (["Oi"], "curto demais"),
        (["x" * 151], "longo demais"),
        (["O que é ETL?", "o que é etl?"], "repetida"),
    ],
)
def test_t7_perguntas_invalidas(pasta, perguntas, trecho):
    assert trecho in erros_de(montar(perguntas_exemplo=perguntas), pasta)[0].problema


# --- T8: campos desconhecidos -----------------------------------------------


def test_t8_erro_de_digitacao_com_sugestao(pasta):
    dados = montar(aparencia__cor_primaira="#000000")
    erro = next(e for e in erros_de(dados, pasta) if e.campo == "aparencia.cor_primaira")
    assert "desconhecido" in erro.problema
    assert "cor_primaria" in erro.correcao


def test_t8_campo_desconhecido_sem_sugestao(pasta):
    erro = erros_de(montar(extra_qualquer="x"), pasta)[0]
    assert "desconhecido" in erro.problema
    assert "Campos aceitos" in erro.correcao


def test_t8_varios_erros_de_uma_vez(pasta):
    dados = montar(assistente__nome="", aparencia__cor_primaria="azul", ia__max_tokens=1)
    assert len(erros_de(dados, pasta)) == 3


# --- T16: contraste (só aviso) ----------------------------------------------


def test_t16_contraste_calculo():
    assert contraste("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contraste("#2563EB", "#2563EB") == pytest.approx(1.0)


def test_t16_cores_claras_geram_aviso_mas_nao_erro(pasta):
    config = validar(montar(aparencia__cor_primaria="#FFFFFF", aparencia__cor_secundaria="#2563EB"), pasta)
    lista = avisos(config)
    assert len(lista) == 1
    assert "cor_primaria" in lista[0]


def test_t16_config_do_projeto_sem_avisos():
    assert avisos(carregar_config(RAIZ / "config.yaml")) == []


# --- Script de linha de comando ---------------------------------------------


def _rodar_script(caminho: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "validar_config.py"), str(caminho)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_script_aprova_config_do_projeto():
    resultado = _rodar_script(RAIZ / "config.yaml")
    assert resultado.returncode == 0
    assert "está correto" in resultado.stdout


def test_script_bloqueia_config_com_erro(pasta):
    arquivo = pasta / "config.yaml"
    arquivo.write_text(yaml.safe_dump(montar(aparencia__cor_primaria="azulzinho")), encoding="utf-8")
    resultado = _rodar_script(arquivo)
    assert resultado.returncode == 1
    assert "azulzinho" in resultado.stdout
    assert "bloqueada" in resultado.stdout
