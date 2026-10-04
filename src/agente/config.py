"""Leitura e validação do config.yaml (contrato da SPEC, seção 4).

Uso típico:
    config = carregar_config("config.yaml")   # levanta ConfigInvalida se houver erros

Todas as mensagens de erro são em português e dizem: campo, problema e como corrigir.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Constantes do contrato
# ---------------------------------------------------------------------------

PROVEDORES_ACEITOS = ("openrouter", "anthropic", "openai")
EXTENSOES_LOGO = (".svg", ".png", ".jpg", ".jpeg", ".webp")
TAMANHO_MAX_LOGO_BYTES = 1024 * 1024  # 1 MB
PASTA_LOGO = "assets"
COR_NEUTRA_PADRAO = "#94A3B8"
COR_TEXTO_TOPO = "#F8FAFC"  # texto quase branco usado no topo da página
CONTRASTE_MINIMO = 4.5

# Faixas numéricas (mínimo, máximo) — usadas na validação e nas mensagens.
FAIXAS = {
    "logo_tamanho": (32, 256),
    "max_tokens": (64, 4096),
    "temperatura": (0.0, 2.0),
    "tempo_limite_segundos": (5, 120),
}

_SEP = "||"  # separa "problema" de "como corrigir" nas mensagens dos validadores
_RE_COR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _erro(problema: str, correcao: str) -> ValueError:
    return ValueError(f"{problema}{_SEP}{correcao}")


# ---------------------------------------------------------------------------
# Tipos reutilizáveis
# ---------------------------------------------------------------------------


def _validar_cor(valor: str) -> str:
    if not _RE_COR.match(valor.strip()):
        raise _erro(
            f'"{valor}" não é uma cor válida.',
            'use o formato #RRGGBB entre aspas, por exemplo "#2563EB".',
        )
    return valor.strip().upper()


Cor = Annotated[str, Field(strict=True), AfterValidator(_validar_cor)]


def _texto(minimo: int, maximo: int):
    return Annotated[
        str,
        Field(strict=True),
        StringConstraints(strip_whitespace=True, min_length=minimo, max_length=maximo),
    ]


def _inteiro(nome: str, padrao: int):
    minimo, maximo = FAIXAS[nome]
    return Annotated[int, Field(default=padrao, strict=True, ge=minimo, le=maximo)]


class _Bloco(BaseModel):
    # extra="forbid" faz campos desconhecidos (erros de digitação) virarem erro.
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------------------
# Blocos do config.yaml
# ---------------------------------------------------------------------------


class Assistente(_Bloco):
    nome: _texto(1, 60)
    descricao: _texto(1, 160)


class Aparencia(_Bloco):
    cor_primaria: Cor
    cor_secundaria: Cor | None = None
    cor_neutra: Cor = COR_NEUTRA_PADRAO
    logo: _texto(1, 300)
    logo_tamanho: _inteiro("logo_tamanho", 96)

    @field_validator("logo")
    @classmethod
    def _logo_existe(cls, valor: str, info: ValidationInfo) -> str:
        caminho = valor.replace("\\", "/")
        if not caminho.startswith(f"{PASTA_LOGO}/") or ".." in caminho.split("/"):
            raise _erro(
                f'"{valor}" está fora da pasta {PASTA_LOGO}/.',
                f'coloque a imagem na pasta {PASTA_LOGO}/ e use, por exemplo, "{PASTA_LOGO}/logo.svg".',
            )
        if not caminho.lower().endswith(EXTENSOES_LOGO):
            raise _erro(
                f'"{valor}" não tem uma extensão de imagem aceita.',
                f"use um arquivo {', '.join(EXTENSOES_LOGO)}.",
            )
        raiz = (info.context or {}).get("raiz")
        if raiz is not None:
            arquivo = Path(raiz) / caminho
            if not arquivo.is_file():
                raise _erro(
                    f'o arquivo "{valor}" não existe.',
                    f"envie a imagem para a pasta {PASTA_LOGO}/ ou corrija o nome "
                    "(maiúsculas e minúsculas fazem diferença).",
                )
            tamanho = arquivo.stat().st_size
            if tamanho > TAMANHO_MAX_LOGO_BYTES:
                raise _erro(
                    f'o arquivo "{valor}" tem {tamanho / 1024 / 1024:.1f} MB (máximo 1 MB).',
                    "reduza a imagem (por exemplo em tinypng.com) ou use um SVG.",
                )
        return caminho

    @model_validator(mode="after")
    def _secundaria_padrao(self) -> Aparencia:
        # Sem cor secundária, o fundo fica sólido com a cor primária.
        if self.cor_secundaria is None:
            object.__setattr__(self, "cor_secundaria", self.cor_primaria)
        return self


class Provedor(_Bloco):
    provedor: Literal["openrouter", "anthropic", "openai"]
    modelo: _texto(1, 200)
    ativo: Annotated[bool, Field(strict=True)] = True


class Ia(_Bloco):
    max_tokens: _inteiro("max_tokens", 1024)
    temperatura: Annotated[float, Field(default=0.7, strict=True, ge=0.0, le=2.0)]
    tempo_limite_segundos: _inteiro("tempo_limite_segundos", 60)
    provedores: Annotated[list[Provedor], Field(min_length=1, max_length=10)]

    @model_validator(mode="after")
    def _regras_da_lista(self) -> Ia:
        if not any(p.ativo for p in self.provedores):
            raise _erro(
                "nenhum provedor está ativo.",
                "deixe pelo menos um provedor com ativo: true (ou apague a linha ativo: false).",
            )
        vistos: set[tuple[str, str]] = set()
        for p in self.provedores:
            par = (p.provedor, p.modelo)
            if par in vistos:
                raise _erro(
                    f'o par {p.provedor} / "{p.modelo}" aparece repetido.',
                    "apague a repetição — cada provedor + modelo só pode aparecer uma vez.",
                )
            vistos.add(par)
        return self

    @property
    def provedores_ativos(self) -> list[Provedor]:
        return [p for p in self.provedores if p.ativo]


class Comportamento(_Bloco):
    instrucoes: _texto(20, 8000)


class Config(_Bloco):
    assistente: Assistente
    aparencia: Aparencia
    ia: Ia
    comportamento: Comportamento
    perguntas_exemplo: Annotated[list[_texto(3, 150)], Field(max_length=6)] = []

    @field_validator("perguntas_exemplo")
    @classmethod
    def _sem_repeticao(cls, perguntas: list[str]) -> list[str]:
        vistas: set[str] = set()
        for pergunta in perguntas:
            chave = pergunta.casefold()
            if chave in vistas:
                raise _erro(
                    f'a pergunta "{pergunta}" aparece repetida.',
                    "apague uma das repetições.",
                )
            vistas.add(chave)
        return perguntas


# ---------------------------------------------------------------------------
# Erros amigáveis
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ErroConfig:
    campo: str
    problema: str
    correcao: str
    linha: int | None = None
    arquivo: str = "config.yaml"

    def __str__(self) -> str:
        onde = self.arquivo + (f", linha {self.linha}" if self.linha else "")
        campo = f"{self.campo}: " if self.campo else ""
        return f"❌ {onde} — {campo}{self.problema}\n   Como corrigir: {self.correcao}"


class ConfigInvalida(Exception):
    """O config.yaml tem um ou mais erros. Veja o atributo `erros`."""

    def __init__(self, erros: list[ErroConfig]):
        self.erros = erros
        super().__init__("\n".join(str(e) for e in erros))


# ---------------------------------------------------------------------------
# Leitura do YAML com número de linha de cada campo
# ---------------------------------------------------------------------------

Caminho = tuple[str | int, ...]


def _mapear_linhas(no: yaml.Node, caminho: Caminho, linhas: dict, repetidos: list) -> None:
    """Percorre o YAML guardando a linha de cada campo e anotando chaves repetidas."""
    linhas.setdefault(caminho, no.start_mark.line + 1)
    if isinstance(no, yaml.MappingNode):
        vistas: set[str] = set()
        for no_chave, no_valor in no.value:
            chave = no_chave.value
            filho = (*caminho, chave)
            if chave in vistas:
                repetidos.append((filho, no_chave.start_mark.line + 1))
            vistas.add(chave)
            linhas[filho] = no_chave.start_mark.line + 1
            _mapear_linhas(no_valor, filho, linhas, repetidos)
    elif isinstance(no, yaml.SequenceNode):
        for indice, item in enumerate(no.value):
            _mapear_linhas(item, (*caminho, indice), linhas, repetidos)


def _linha_de(caminho: Caminho, linhas: dict) -> int | None:
    # Se o campo não existe (ex.: obrigatório faltando), usa a linha do "pai".
    for fim in range(len(caminho), -1, -1):
        if caminho[:fim] in linhas:
            return linhas[caminho[:fim]]
    return None


def _nome_campo(caminho: Caminho) -> str:
    texto = ""
    for parte in caminho:
        texto += f"[{parte}]" if isinstance(parte, int) else (f".{parte}" if texto else parte)
    return texto


def _traduzir_erro_yaml(erro: yaml.YAMLError, arquivo: str) -> ErroConfig:
    marca = getattr(erro, "problem_mark", None)
    linha = marca.line + 1 if marca else None
    problema_original = (getattr(erro, "problem", None) or "").lower()
    if "mapping values are not allowed" in problema_original:
        correcao = 'há um ":" num lugar inesperado. Se o texto tiver ":", coloque-o entre aspas.'
    elif "could not find expected ':'" in problema_original:
        correcao = 'falta o ":" depois do nome do campo, ou uma aspa não foi fechada.'
    elif "found unexpected end of stream" in problema_original or "quoted scalar" in str(erro):
        correcao = "alguma aspa foi aberta e não foi fechada."
    else:
        correcao = "confira o recuo (2 espaços por nível) e se todas as aspas estão fechadas."
    return ErroConfig("", "o arquivo não é um YAML válido.", correcao, linha, arquivo)


def _ler_yaml(texto: str, arquivo: str) -> tuple[Any, dict, list[ErroConfig]]:
    erros: list[ErroConfig] = []
    for numero, conteudo in enumerate(texto.splitlines(), start=1):
        recuo = conteudo[: len(conteudo) - len(conteudo.lstrip(" \t"))]
        if "\t" in recuo:
            erros.append(
                ErroConfig(
                    "",
                    "há um TAB no recuo da linha.",
                    "troque o TAB por 2 espaços (o YAML não aceita TAB).",
                    numero,
                    arquivo,
                )
            )
    if erros:
        return None, {}, erros

    try:
        dados = yaml.safe_load(texto)
        raiz = yaml.compose(texto)
    except yaml.YAMLError as erro:
        return None, {}, [_traduzir_erro_yaml(erro, arquivo)]

    linhas: dict = {}
    repetidos: list = []
    if raiz is not None:
        _mapear_linhas(raiz, (), linhas, repetidos)
    for caminho, linha in repetidos:
        erros.append(
            ErroConfig(
                _nome_campo(caminho),
                "campo repetido (só o último valor seria usado).",
                "apague uma das repetições.",
                linha,
                arquivo,
            )
        )
    return dados, linhas, erros


# ---------------------------------------------------------------------------
# Tradução dos erros do pydantic para português
# ---------------------------------------------------------------------------


def _campos_validos(caminho: Caminho) -> list[str]:
    modelo: Any = Config
    for parte in caminho:
        if isinstance(parte, int):
            continue
        campo = modelo.model_fields.get(parte)
        if campo is None:
            return []
        anotacao = campo.annotation
        argumentos = getattr(anotacao, "__args__", ())
        candidatos = [anotacao, *argumentos]
        modelo = next((c for c in candidatos if isinstance(c, type) and issubclass(c, BaseModel)), None)
        if modelo is None:
            return []
    return list(modelo.model_fields)


def _faixa(nome: str) -> str:
    minimo, maximo = FAIXAS.get(nome, (None, None))
    return f"de {minimo} a {maximo}" if minimo is not None else "dentro da faixa permitida"


def _traduzir(erro: dict) -> tuple[str, str]:
    tipo = erro["type"]
    caminho = erro["loc"]
    nome = next((p for p in reversed(caminho) if isinstance(p, str)), "")
    valor = erro.get("input")
    ctx = erro.get("ctx") or {}

    if tipo == "value_error":
        mensagem = str(ctx.get("error", erro["msg"]))
        problema, _, correcao = mensagem.partition(_SEP)
        return problema, correcao or "corrija o valor."

    if tipo == "missing":
        return "campo obrigatório não encontrado.", f"adicione o campo `{nome}` com um valor."

    if tipo == "extra_forbidden":
        sugestao = difflib.get_close_matches(nome, _campos_validos(caminho[:-1]), n=1, cutoff=0.6)
        if sugestao:
            return "campo desconhecido.", f'você quis dizer "{sugestao[0]}"?'
        aceitos = ", ".join(_campos_validos(caminho[:-1])) or "veja a seção 4 da SPEC"
        return "campo desconhecido.", f"apague este campo. Campos aceitos aqui: {aceitos}."

    if valor is None and tipo in {"string_type", "int_type", "float_type", "bool_type"}:
        dica = ' Se for uma cor, coloque entre aspas: "#2563EB" (sem aspas, o # vira comentário).'
        return "está vazio.", "preencha um valor." + (dica if nome.startswith("cor_") else "")

    if tipo == "string_type":
        return f"deveria ser um texto, mas veio {valor!r}.", 'coloque o valor entre aspas, ex.: "texto".'

    if tipo == "string_too_short":
        minimo = ctx.get("min_length", 1)
        if minimo <= 1:
            return "está vazio.", "escreva um texto."
        return (
            f"é curto demais ({len(str(valor).strip())} caracteres; mínimo {minimo}).",
            "escreva um texto mais completo.",
        )

    if tipo == "string_too_long":
        return (
            f"é longo demais ({len(str(valor).strip())} caracteres; máximo {ctx.get('max_length')}).",
            "encurte o texto.",
        )

    if tipo in {"int_type", "int_parsing", "int_from_float"}:
        return (
            f"deveria ser um número inteiro, mas veio {valor!r}.",
            f"use um número inteiro {_faixa(nome)}, sem aspas.",
        )

    if tipo in {"float_type", "float_parsing"}:
        return f"deveria ser um número, mas veio {valor!r}.", f"use um número {_faixa(nome)}, sem aspas (ex.: 0.7)."

    if tipo in {"greater_than_equal", "less_than_equal", "greater_than", "less_than"}:
        return f"o valor {valor} está fora da faixa permitida.", f"use um valor {_faixa(nome)}."

    if tipo in {"bool_type", "bool_parsing"}:
        return (
            f"deveria ser true ou false, mas veio {valor!r}.",
            "escreva true (ligado) ou false (desligado), sem aspas.",
        )

    if tipo == "literal_error":
        return f'"{valor}" não é um provedor aceito.', "use openrouter, anthropic ou openai (em minúsculas)."

    if tipo == "list_type":
        return "deveria ser uma lista.", 'escreva cada item numa linha começando com "- ".'

    if tipo == "too_short":
        return "a lista está vazia.", "adicione pelo menos um item."

    if tipo == "too_long":
        return (
            f"tem itens demais ({ctx.get('actual_length')}; máximo {ctx.get('max_length')}).",
            "apague alguns itens.",
        )

    if tipo in {"model_type", "dict_type", "model_attributes_type"}:
        return "deveria ser um bloco com campos dentro.", "confira o recuo: os campos de dentro levam 2 espaços a mais."

    return f"valor inválido ({erro['msg']}).", "confira este campo na seção 4 da SPEC."


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def validar_texto(texto: str, raiz: str | Path = ".", arquivo: str = "config.yaml") -> Config:
    """Valida o conteúdo de um config.yaml. `raiz` é a pasta onde fica a pasta assets/."""
    dados, linhas, erros = _ler_yaml(texto, arquivo)
    if erros:
        raise ConfigInvalida(erros)
    if not isinstance(dados, dict):
        problema = "o arquivo está vazio." if dados is None else "o arquivo não tem o formato esperado."
        raise ConfigInvalida([ErroConfig("", problema, "use o exemplo da seção 4.3 da SPEC como modelo.", 1, arquivo)])
    try:
        return Config.model_validate(dados, context={"raiz": Path(raiz)})
    except ValidationError as erro_pydantic:
        convertidos = []
        for e in erro_pydantic.errors():
            problema, correcao = _traduzir(e)
            caminho = tuple(e["loc"])
            convertidos.append(
                ErroConfig(_nome_campo(caminho), problema, correcao, _linha_de(caminho, linhas), arquivo)
            )
        raise ConfigInvalida(convertidos) from None


def carregar_config(caminho: str | Path = "config.yaml") -> Config:
    """Lê e valida o config.yaml. Levanta ConfigInvalida com a lista de erros."""
    arquivo = Path(caminho)
    if not arquivo.is_file():
        raise ConfigInvalida(
            [
                ErroConfig(
                    "",
                    f'o arquivo "{arquivo.name}" não foi encontrado.',
                    "crie o config.yaml na raiz do projeto (veja a seção 4.3 da SPEC).",
                    arquivo=arquivo.name,
                )
            ]
        )
    texto = arquivo.read_text(encoding="utf-8")
    return validar_texto(texto, raiz=arquivo.parent, arquivo=arquivo.name)


# ---------------------------------------------------------------------------
# Avisos que não bloqueiam (T16 — contraste)
# ---------------------------------------------------------------------------


def _luminancia(cor: str) -> float:
    canais = [int(cor[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lineares = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canais]
    return 0.2126 * lineares[0] + 0.7152 * lineares[1] + 0.0722 * lineares[2]


def contraste(cor_a: str, cor_b: str) -> float:
    """Razão de contraste WCAG entre duas cores #RRGGBB (de 1 a 21)."""
    claro, escuro = sorted((_luminancia(cor_a), _luminancia(cor_b)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


def avisos(config: Config) -> list[str]:
    """Problemas que não impedem a publicação, mas merecem atenção."""
    resultado = []
    cores = {"cor_primaria": config.aparencia.cor_primaria, "cor_secundaria": config.aparencia.cor_secundaria}
    for nome, cor in cores.items():
        razao = contraste(COR_TEXTO_TOPO, cor)
        if razao < CONTRASTE_MINIMO:
            resultado.append(
                f"⚠️ aparencia.{nome} ({cor}): o texto claro do topo fica difícil de ler "
                f"(contraste {razao:.1f}:1; o recomendado é pelo menos {CONTRASTE_MINIMO}:1). "
                "Considere uma cor mais escura."
            )
    return resultado
