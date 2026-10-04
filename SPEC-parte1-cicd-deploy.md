# SPEC — Parte 1: assistente de IA no ar, com CI/CD e deploy automático

> **Status:** rascunho para aprovação · **Versão:** 0.1 · **Data:** 04/10/2026
> **Autor:** Lucas M. Surmani (LMS) · **Ideia original:** [`docs/IDEIA-parte1.md`](docs/IDEIA-parte1.md)
>
> Esta spec descreve **o que** será construído e **como saberemos que está pronto**.
> Nenhum código foi escrito ainda. Cada tarefa da seção 9 será feita **uma de cada vez**, com a sua aprovação.

---

## Glossário rápido (para iniciantes)

| Termo | O que significa aqui |
|---|---|
| **Repositório (repo)** | A pasta do projeto guardada no GitHub, com todo o histórico de mudanças. |
| **Commit** | Um "salvamento" de alterações no repositório, com uma mensagem explicando o que mudou. |
| **Branch `main`** | A linha principal do projeto. O que entra nela é publicado. |
| **GitHub Actions** | Robô do GitHub que roda tarefas automáticas (testes, publicação) a cada commit. |
| **Workflow** | O "roteiro" que diz ao GitHub Actions o que fazer. Fica em `.github/workflows/`. |
| **Portão de testes** | Conjunto de verificações que **precisa passar** antes de publicar. Se falhar, nada é publicado. |
| **Space** | Um "mini-site" hospedado no Hugging Face. |
| **Static / Gradio** | Tipos de Space. *Static* = página fixa (HTML). *Gradio* = aplicativo Python com chat. |
| **ZeroGPU** | Tipo de hardware gratuito do Hugging Face que libera Spaces Gradio em contas grátis. |
| **Secret (segredo)** | Valor sensível (como uma chave de API) guardado de forma protegida, fora do código. |
| **Chave de API** | "Senha" que permite ao assistente usar a IA de um provedor (OpenRouter, Anthropic, OpenAI). |
| **Provedor / modelo** | Provedor = empresa que dá acesso à IA. Modelo = a IA específica (ex.: `google/gemma-4-31b-it:free`). |
| **Fallback** | Plano B automático: se o primeiro provedor falhar, tenta o próximo. |
| **Token** | Pedacinho de texto que a IA conta. 1024 tokens ≈ 700 palavras ≈ 1 página. |
| **YAML** | Formato de arquivo de configuração fácil de ler, com `campo: valor` e recuo por espaços. |

---

## 1. Objetivo, público e escopo

### 1.1 Objetivo
Publicar na internet, de graça, um **chat com IA** que tira dúvidas sobre **Engenharia de Dados e Inteligência Artificial** de forma didática, como um professor. Qualquer pessoa abre um link e conversa.

Tudo o que é personalizável fica em **um único arquivo** (`config.yaml`), editável pelo site do GitHub. Cada alteração salva na `main` passa por um **portão de testes** e, se estiver tudo certo, é **publicada sozinha** no Hugging Face Spaces.

### 1.2 Público
- **Usuário final:** alunos e interessados em dados e IA, sem conhecimento técnico. Tudo em português.
- **Dono do projeto (você):** iniciante em programação, que edita o `config.yaml` pelo GitHub e acompanha a publicação pelo GitHub Actions.

### 1.3 Identidade definida

| Item | Valor |
|---|---|
| Nome | **LMS Labs · Assistente** |
| Descrição | "Aprenda pipelines, modelos e IA conversando." |
| Cor primária (preto) | `#0B0F19` |
| Cor secundária (azul) | `#2563EB` |
| Cor neutra (cinza-ardósia) | `#94A3B8` |
| Logo no chat (fundo escuro) | `assets/logo-claro.svg` |
| Logo para portfólio (fundo claro) | `assets/logo.svg` |
| Hugging Face | usuário `Surmani`, Space `agente-personalizado` |
| Link final | `https://huggingface.co/spaces/Surmani/agente-personalizado` |

### 1.4 As duas fases

A conta `Surmani` foi criada em **01/10/2026**. O Hugging Face só libera **Gradio + ZeroGPU** gratuitamente para contas com **mais de 30 dias** e e-mail verificado. Por isso:

| Fase | Quando | O que vai ao ar no Space |
|---|---|---|
| **Fase A** | Agora | **Vitrine estática** (Static): logo, nome, descrição, cores e o aviso "Chat em breve". O chat completo roda **no seu computador** para testes. O portão de testes e o pipeline já funcionam. |
| **Fase B** | A partir de **~31/10/2026** | O **chat completo** (Gradio + ZeroGPU) substitui a vitrine **no mesmo link**. |

A troca de fase é feita mudando **uma variável** no GitHub (`HF_SPACE_MODE`: `static` → `gradio`) e o hardware do Space. Detalhes na seção 7.

### 1.5 O que entra na Parte 1
- Chat com IA em português, com respostas em *streaming* (o texto aparece aos poucos).
- Vários provedores (OpenRouter, Anthropic, OpenAI) em ordem de preferência, com **fallback automático**.
- Mensagem clara no chat com o **motivo de cada falha** quando nenhum provedor funciona.
- Personalização total via `config.yaml`: nome, descrição, cores, logo e tamanho, provedores e modelos, limite de resposta, instruções de comportamento e perguntas de exemplo.
- Portão de testes: validação do `config.yaml`, varredura de chaves vazadas, testes automáticos.
- Deploy automático GitHub → Hugging Face com GitHub Actions.
- Vitrine estática gerada a partir do mesmo `config.yaml` (Fase A).

### 1.6 O que fica para depois
| Item | Onde |
|---|---|
| Base de conhecimento com seus documentos (RAG) | **Parte 2** |
| Site próprio, domínio próprio e visual feito do zero | **Parte 3** |
| Login de usuários e conversas salvas | Fora do escopo (sem data) |
| Histórico persistente, analytics, limite de uso por pessoa | Fora do escopo |
| Upload de arquivos ou imagens no chat | Fora do escopo |

---

## 2. Stack escolhida e restrições conhecidas

### 2.1 Stack

| Camada | Escolha | Por quê |
|---|---|---|
| Linguagem | **Python 3.10** | Versão suportada pelo ZeroGPU e fácil para iniciantes. |
| Interface do chat | **Gradio** (versão estável mais recente, **fixada** no `requirements.txt` e no README do Space) | É o padrão do Hugging Face e já traz um componente de chat pronto. |
| IA, provedor principal | **OpenRouter** (API compatível com OpenAI) | Uma conta dá acesso a vários modelos, inclusive gratuitos (`:free`). |
| IA, provedores opcionais | **Anthropic** e **OpenAI** | Usados se você tiver as chaves. |
| Bibliotecas de IA | SDK `openai` (para OpenRouter e OpenAI) e SDK `anthropic` | São as bibliotecas oficiais. O OpenRouter aceita o SDK da OpenAI trocando só o endereço. |
| Configuração | **YAML** (`config.yaml`) lido com `PyYAML` e validado com `pydantic` | Fácil de editar no GitHub, e as mensagens de erro saem claras. |
| ZeroGPU | Biblioteca `spaces` (só no Hugging Face) | Exigida pelo ZeroGPU (ver 2.3). |
| Testes | `pytest` | Padrão do Python. |
| Qualidade de código | `ruff` | Encontra erros comuns e padroniza o código. |
| Varredura de chaves | **gitleaks** (gratuito para contas pessoais) | Bloqueia a publicação se houver chave no código ou no histórico. |
| Publicação | `huggingface_hub` (Python) dentro do GitHub Actions | Envia os arquivos ao Space e lida sozinho com arquivos binários (imagens). |
| CI/CD | **GitHub Actions** | Gratuito para repositórios públicos e já integrado ao GitHub. |

### 2.2 Modelos iniciais (ordem de preferência)

| # | Provedor | Modelo | Ativo? | Observação |
|---|---|---|---|---|
| 1 | OpenRouter | `google/gemma-4-31b-it:free` | Sim | Gratuito. |
| 2 | OpenRouter | segundo modelo `:free` | Sim | **Escolhido na tarefa 3** com base na lista atual em openrouter.ai/models (filtro "free"), porque os modelos gratuitos mudam com frequência. |
| 3 | Anthropic | `claude-haiku-4-5` | **Não** | Ativar quando tiver a chave. |
| 4 | OpenAI | modelo pequeno e barato da linha atual | **Não** | Confirmado na tarefa 3. Ativar quando tiver a chave. |

- **Limite de resposta:** `max_tokens: 1024`.
- **Chaves esperadas**, como *Secrets* no Hugging Face ou no arquivo `.env` local: `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`.

### 2.3 Restrições conhecidas do Hugging Face Spaces

| Restrição | Impacto no projeto |
|---|---|
| **Gradio em CPU básica exige plano PRO (pago).** | Não usaremos. |
| **Gradio em ZeroGPU é grátis** para contas pessoais com e-mail verificado e **mais de 30 dias**, com no máximo **2 Spaces** ZeroGPU por conta. | A Fase B começa por volta de 31/10/2026. |
| **Static é grátis para todos.** | É a vitrine da Fase A. |
| O ZeroGPU **só funciona com Gradio**. | O chat precisa ser Gradio. |
| O ZeroGPU **exige pelo menos uma função marcada com `@spaces.GPU`**, senão o Space não inicia ("No @spaces.GPU function detected"). | O app terá uma **função vazia de GPU que nunca é chamada**. Como ela não é chamada, **não consome a cota de GPU**. A IA roda no OpenRouter, não no Space. |
| O ZeroGPU suporta versões específicas de Python e Gradio (Gradio 4+). | Python 3.10 e Gradio fixados. Conferir na tarefa 10. |
| Space gratuito **dorme** depois de um tempo sem visitas (cerca de 48h no ZeroGPU). | A primeira visita depois disso demora alguns segundos para "acordar". Isso é normal. |
| O README do Space precisa de um **cabeçalho YAML** (`sdk`, `app_file`, `sdk_version`, cores do cartão etc.). | Gerado automaticamente pelo script de publicação. Não editar à mão. |
| As cores do **cartão** do Space (`colorFrom`/`colorTo`) aceitam **só nomes** (`blue`, `gray`, `indigo`…), não hex. | Usaremos `gray` → `blue`. Isso só afeta a miniatura na listagem do HF, não o chat. |
| Envio por `git push` rejeita arquivos binários (PNG, JPG) sem LFS/Xet. | Por isso a publicação usa `huggingface_hub`, que trata isso sozinho. |
| As chaves ficam em **Settings → Variables and secrets** do Space. | Elas nunca vão para o GitHub. |
| O Space reinicia e reconstrói a cada publicação, o que leva de 1 a 5 minutos. | Durante a reconstrução, o Space mostra "Building". |

### 2.4 Restrições conhecidas do OpenRouter (modelos gratuitos)
- Os modelos `:free` têm **limite de uso**: algumas requisições por minuto e um teto diário, que aumenta se a conta tiver créditos comprados. Os números atuais ficam em openrouter.ai/docs.
- Modelos gratuitos podem ficar **lotados** (erro 429) ou **sair do ar**. É por isso que existe o fallback.

---

## 3. Estrutura de arquivos do projeto

```
agente-personalizado/
├── .github/
│   └── workflows/
│       └── publicar.yml          # Pipeline: portão de testes + publicação no HF
├── assets/
│   ├── logo.svg                  # Logo LMS azul (fundo claro / portfólio)
│   ├── logo-claro.svg            # Logo LMS clara (fundo escuro / chat)
│   └── logo-preview.png          # Prévia das logos (não vai para o Space)
├── docs/
│   └── IDEIA-parte1.md           # Ideia original, em linguagem simples
├── scripts/
│   ├── validar_config.py         # Roda o portão de configuração com mensagens amigáveis
│   ├── gerar_vitrine.py          # Gera a página estática (Fase A) a partir do config.yaml
│   └── publicar_hf.py            # Monta a pasta de publicação e envia ao Space
├── src/
│   └── agente/
│       ├── __init__.py
│       ├── config.py             # Lê e valida o config.yaml (o "contrato" da seção 4)
│       ├── provedores.py         # Conversa com OpenRouter/Anthropic/OpenAI + fallback
│       ├── interface.py          # Monta a tela Gradio (logo, cores, chat, botões)
│       └── textos.py             # Todos os textos da tela, em português
├── tests/
│   ├── test_config.py            # T1–T8
│   ├── test_segredos.py          # T9
│   ├── test_provedores.py        # T10–T11
│   ├── test_interface.py         # T12–T13
│   └── test_vitrine.py           # T14
├── app.py                        # Ponto de entrada (o HF procura este arquivo)
├── config.yaml                   # ⭐ O ÚNICO arquivo que você precisa editar
├── requirements.txt              # Bibliotecas que o Space instala
├── requirements-dev.txt          # Bibliotecas extras para testes (só GitHub/local)
├── .gitleaks.toml                # Regras da varredura de chaves
├── .env.example                  # Modelo de .env local (sem chaves de verdade)
├── .gitignore                    # Ignora .env, caches, pasta dist/
├── README.md                     # Como usar o projeto (para humanos)
└── SPEC-parte1-cicd-deploy.md    # Este documento
```

**Pasta gerada (não versionada):** `dist/`, montada pelo `publicar_hf.py` a cada publicação.
- Modo `static`: `index.html`, `assets/logo-claro.svg` e `README.md` (cabeçalho `sdk: static`).
- Modo `gradio`: `app.py`, `src/`, `config.yaml`, `assets/*.svg`, `requirements.txt` e `README.md` (cabeçalho `sdk: gradio`).

---

## 4. Contrato do arquivo de configuração (`config.yaml`)

### 4.1 Regras gerais
- O arquivo fica na **raiz** do repositório e se chama exatamente `config.yaml`.
- Usa **espaços** para recuo (2 por nível), **nunca TAB**.
- Textos com `:` ou `#` devem ficar **entre aspas**.
- **Campos desconhecidos são erro.** Isso pega erros de digitação, como `cor_primaira`, e o portão sugere o nome correto.
- **Nenhuma chave de API pode aparecer aqui.** Chaves ficam só nos *Secrets*.

### 4.2 Campos

#### Bloco `assistente`
| Campo | Obrigatório? | Valores aceitos | Padrão |
|---|---|---|---|
| `assistente.nome` | **Sim** | Texto de 1 a 60 caracteres, não vazio | — |
| `assistente.descricao` | **Sim** | Texto de 1 a 160 caracteres, não vazio | — |

#### Bloco `aparencia`
| Campo | Obrigatório? | Valores aceitos | Padrão |
|---|---|---|---|
| `aparencia.cor_primaria` | **Sim** | Cor hex `#RRGGBB` (ex.: `#0B0F19`) | — |
| `aparencia.cor_secundaria` | Não | Cor hex `#RRGGBB`. Se informada, o fundo vira um degradê primária → secundária. | igual à `cor_primaria` (fundo sólido) |
| `aparencia.cor_neutra` | Não | Cor hex `#RRGGBB`, usada em textos secundários, bordas e botões de exemplo | `#94A3B8` |
| `aparencia.logo` | **Sim** | Caminho relativo **dentro de `assets/`**, extensão `.svg`, `.png`, `.jpg`, `.jpeg` ou `.webp`. O arquivo **precisa existir** e ter **até 1 MB**. | — |
| `aparencia.logo_tamanho` | Não | Número inteiro de **32 a 256** (pixels de altura) | `96` |

#### Bloco `ia`
| Campo | Obrigatório? | Valores aceitos | Padrão |
|---|---|---|---|
| `ia.max_tokens` | Não | Inteiro de **64 a 4096** | `1024` |
| `ia.temperatura` | Não | Número de **0.0 a 2.0** (quanto maior, mais criativo) | `0.7` |
| `ia.tempo_limite_segundos` | Não | Inteiro de **5 a 120**, o tempo máximo de espera por provedor | `60` |
| `ia.provedores` | **Sim** | Lista com **1 a 10** itens. A **ordem da lista é a ordem de preferência**. | — |
| `ia.provedores[].provedor` | **Sim** | `openrouter`, `anthropic` ou `openai` (minúsculas) | — |
| `ia.provedores[].modelo` | **Sim** | Texto não vazio (ex.: `google/gemma-4-31b-it:free`) | — |
| `ia.provedores[].ativo` | Não | `true` ou `false` | `true` |

Regras extras do bloco `ia`:
- Pelo menos **1 provedor com `ativo: true`**.
- Não pode haver o **mesmo par provedor + modelo repetido**.

#### Bloco `comportamento`
| Campo | Obrigatório? | Valores aceitos | Padrão |
|---|---|---|---|
| `comportamento.instrucoes` | **Sim** | Texto de **20 a 8000** caracteres. Diz quem o assistente é, com quem fala e o que não deve fazer. Use `\|` para escrever várias linhas. | — |

#### Bloco `perguntas_exemplo`
| Campo | Obrigatório? | Valores aceitos | Padrão |
|---|---|---|---|
| `perguntas_exemplo` | Não | Lista de **0 a 6** textos, cada um com **3 a 150** caracteres, sem repetição | `[]` (nenhum botão) |

### 4.3 Exemplo do `config.yaml` inicial

```yaml
assistente:
  nome: "LMS Labs · Assistente"
  descricao: "Aprenda pipelines, modelos e IA conversando."

aparencia:
  cor_primaria: "#0B0F19"     # preto
  cor_secundaria: "#2563EB"   # azul
  cor_neutra: "#94A3B8"       # cinza-ardósia
  logo: "assets/logo-claro.svg"
  logo_tamanho: 96

ia:
  max_tokens: 1024
  temperatura: 0.7
  tempo_limite_segundos: 60
  provedores:                 # ordem = preferência
    - provedor: openrouter
      modelo: "google/gemma-4-31b-it:free"
    - provedor: openrouter
      modelo: "<segundo modelo :free — definido na tarefa 3>"
    - provedor: anthropic
      modelo: "claude-haiku-4-5"
      ativo: false
    - provedor: openai
      modelo: "<modelo pequeno — definido na tarefa 3>"
      ativo: false

comportamento:
  instrucoes: |
    Você é o assistente do LMS Labs, um professor paciente de Engenharia de Dados e IA.
    Fale com estudantes iniciantes e intermediários, sempre em português do Brasil.
    Explique passo a passo, use exemplos do dia a dia e, quando útil, pequenos trechos de código.
    Termine respostas longas com um resumo de 1 a 3 linhas.
    Não invente fatos: se não souber, diga que não sabe e sugira onde pesquisar.
    Não responda a pedidos fora de dados e IA; redirecione educadamente.
    Nunca peça nem revele senhas, chaves de API ou dados pessoais.

perguntas_exemplo:
  - "O que é um pipeline de dados?"
  - "Qual a diferença entre ETL e ELT?"
  - "Como funciona um modelo de linguagem?"
  - "Por onde começo a estudar engenharia de dados?"
```

### 4.4 Formato das mensagens de erro do portão
Cada erro aparece em **uma linha**, em português, dizendo **o campo**, **o problema** e **como corrigir**. Quando possível, também traz a **linha do arquivo**. Por exemplo:

```
❌ config.yaml, linha 8 — aparencia.cor_primaria: "azulzinho" não é uma cor válida.
   Como corrigir: use o formato #RRGGBB, por exemplo "#2563EB".
❌ aparencia.logo: o arquivo "assets/logo-nova.svg" não existe.
   Como corrigir: envie o arquivo para a pasta assets/ ou corrija o nome.
❌ aparencia.cor_primaira: campo desconhecido. Você quis dizer "cor_primaria"?
```

---

## 5. Requisitos funcionais

### Configuração
- **RF1.** O app lê **todas** as personalizações do `config.yaml`. Mudar a aparência ou o comportamento **não exige mexer em código**.
- **RF2.** Ao iniciar, o app valida o `config.yaml` com as **mesmas regras** do portão (seção 4). Se houver erro, não inicia e mostra a lista de erros no log.
- **RF3.** Campos opcionais ausentes recebem os **valores padrão** da seção 4.2.

### Chat e IA
- **RF4.** O usuário digita uma pergunta e recebe a resposta **em streaming** (o texto aparece aos poucos).
- **RF5.** O chat mantém o **contexto da conversa** enquanto a página está aberta. Ao recarregar a página, a conversa recomeça.
- **RF6.** As `comportamento.instrucoes` são enviadas como **instrução de sistema** em toda conversa.
- **RF7.** Cada resposta respeita `ia.max_tokens`, `ia.temperatura` e `ia.tempo_limite_segundos`.
- **RF8. Fallback:** o app tenta os provedores **ativos, na ordem da lista**. Ele passa para o próximo quando:
  - a chave daquele provedor **não está configurada** (o provedor é pulado sem chamar a rede);
  - a chave é inválida (401/403);
  - não há crédito (402);
  - o modelo está lotado ou há limite de uso (429);
  - o modelo não existe (404);
  - há erro do servidor (5xx);
  - o tempo limite é estourado;
  - a resposta vem vazia.
- **RF9.** O fallback só acontece **antes do primeiro pedaço de texto** chegar. Se um provedor cair **no meio** da resposta, o texto parcial é mantido e o chat avisa: "⚠️ A resposta foi interrompida. Tente perguntar de novo."
- **RF10.** Se **todos** os provedores falharem, o chat mostra **uma mensagem em português** listando, para cada um, o provedor, o modelo e o motivo traduzido. Exemplo:
  > Não consegui responder agora. Tentei:
  > 1. openrouter / google/gemma-4-31b-it:free: modelo lotado (limite de uso). Tente em alguns minutos.
  > 2. openrouter / …: tempo limite de 60s esgotado.
  > 3. anthropic / claude-haiku-4-5: desativado no config.yaml.
- **RF11.** O log do servidor registra **qual provedor respondeu** e os motivos das falhas, **sem nunca registrar chaves** nem o conteúdo completo das conversas.
- **RF12.** Uma mensagem vazia (só espaços) não é enviada à IA.

### Aparência
- **RF13.** O topo da página mostra a **logo** (com a altura de `logo_tamanho`), o **nome** e a **descrição**.
- **RF14.** O fundo da página usa `cor_primaria`, ou o degradê `cor_primaria` → `cor_secundaria`.
- **RF15.** A área do chat usa **fundo próprio** com contraste alto (texto claro sobre superfície escura neutra), para ser fácil de ler com qualquer cor escolhida.
- **RF16.** As `perguntas_exemplo` aparecem como **botões clicáveis**. Clicar envia a pergunta ao chat.
- **RF17.** **Todos os textos visíveis** ficam em **português**: placeholder, botões ("Enviar", "Limpar conversa"), mensagens de erro e avisos. Eles são centralizados em `src/agente/textos.py`.
- **RF18.** A página funciona em **celular** e em computador.
- **RF19.** O rodapé mostra um aviso curto: "As respostas são geradas por IA e podem conter erros."

### Segurança
- **RF20.** As chaves de API são lidas **só de variáveis de ambiente**: *Secrets* no HF, ou `.env` local, que é ignorado pelo Git. O código e o `config.yaml` **nunca** contêm chaves.
- **RF21.** As chaves nunca aparecem na tela, nos logs nem nas mensagens de erro (no máximo aparece "chave não configurada").

### Vitrine (Fase A)
- **RF22.** O `scripts/gerar_vitrine.py` gera uma página estática `index.html` usando o **mesmo `config.yaml`**: logo, nome, descrição, cores e o aviso "💬 Chat em breve". Ela **não tem chat e não contém nenhuma chave**.

### Publicação
- **RF23.** O `scripts/publicar_hf.py` monta a pasta `dist/` conforme o modo (`static` ou `gradio`), gera o `README.md` do Space com o cabeçalho correto e envia tudo ao Space, **substituindo** os arquivos antigos.
- **RF24.** No modo `gradio`, o `app.py` contém a função vazia `@spaces.GPU` exigida pelo ZeroGPU. Ela só é ativada quando o app roda no Hugging Face. Localmente, o app funciona sem a biblioteca `spaces`.

### Uso local
- **RF25.** O app roda no computador com um único comando, lendo as chaves do `.env`, e abre em `http://localhost:7860`.

---

## 6. Verificações do portão de testes

O portão roda **a cada push e a cada pull request**. **Se qualquer item falhar, nada é publicado** e o site antigo continua no ar.

| ID | Verificação | Bloqueia? |
|---|---|---|
| **T1** | O `config.yaml` existe e é um YAML válido (sem TAB, recuo correto, aspas fechadas). | Sim |
| **T2** | Todos os campos obrigatórios existem e não estão vazios. | Sim |
| **T3** | Todas as cores estão no formato `#RRGGBB`. | Sim |
| **T4** | A logo existe dentro de `assets/`, tem extensão permitida e até 1 MB, e o `logo_tamanho` está entre 32 e 256. | Sim |
| **T5** | Os provedores são válidos (`openrouter`/`anthropic`/`openai`), têm modelo não vazio e não se repetem, e há pelo menos 1 ativo. | Sim |
| **T6** | Os números estão nas faixas permitidas (`max_tokens`, `temperatura`, `tempo_limite_segundos`). | Sim |
| **T7** | As perguntas de exemplo têm entre 0 e 6 itens, cada um com 3 a 150 caracteres, sem repetição. | Sim |
| **T8** | Não há campos desconhecidos (com sugestão de correção). | Sim |
| **T9** | **Varredura de chaves:** o gitleaks não encontra chaves no código **nem no histórico**, e o `config.yaml` não contém textos com cara de chave (`sk-…`, `sk-or-…`, `sk-ant-…`, `hf_…`). | Sim |
| **T10** | **Fallback (testes com provedores falsos, sem internet):** o 1º falha com 429 e o 2º responde; um provedor sem chave é pulado; um provedor desativado é ignorado. | Sim |
| **T11** | **Todos falham:** a mensagem final está em português e lista cada provedor, modelo e motivo, sem expor nenhuma chave. | Sim |
| **T12** | **Interface monta sem erro:** a tela Gradio é criada a partir do `config.yaml` sem chamar a internet, e os botões de exemplo correspondem às `perguntas_exemplo`. | Sim |
| **T13** | **Textos em português:** os textos visíveis vêm de `textos.py`, e nenhum texto padrão em inglês do Gradio fica aparente (lista verificada no teste). | Sim |
| **T14** | **Vitrine:** o `index.html` gerado contém o nome, a descrição, a logo e as cores do config, e não contém nenhuma chave. | Sim |
| **T15** | **Qualidade de código:** o `ruff` passa sem erros. | Sim |
| **T16** | **Contraste:** o texto do topo (nome/descrição) tem contraste mínimo de 4.5:1 sobre as cores do fundo. | **Não**, só gera um aviso ⚠️ |

**Como o resultado aparece:** na aba **Actions** do GitHub, o passo "Portão de testes" fica ✅ ou ❌. Quando falha, um **resumo em português** com a lista de erros (formato da seção 4.4) aparece na página do workflow, e o GitHub manda um e-mail.

---

## 7. Pipeline de deploy (GitHub Actions)

### 7.1 Visão geral

```
Você salva o config.yaml no GitHub (commit na main)
        │
        ▼
┌──────────────────────────────┐
│ Job 1: PORTÃO DE TESTES      │  ruff · pytest (T1–T16) · validar_config · gitleaks
└──────────────┬───────────────┘
               │ passou? ── não ──► ❌ para aqui. Site antigo continua no ar.
               ▼ sim                   Resumo do erro na aba Actions + e-mail.
┌──────────────────────────────┐
│ Job 2: PUBLICAR NO HF        │  só na main · só se HF_SPACE_MODE estiver definido
│  modo static → vitrine       │
│  modo gradio → chat completo │
└──────────────┬───────────────┘
               ▼
Hugging Face reconstrói o Space (1–5 min) → link atualizado
```

### 7.2 Regras do workflow (`.github/workflows/publicar.yml`)
- **Gatilhos:** `push` na `main`, `pull_request` para a `main` (só o portão, sem publicar) e `workflow_dispatch` (botão "Run workflow" para rodar à mão).
- **Job 1, `portao`:** Ubuntu + Python 3.10. Instala o `requirements-dev.txt` e roda `ruff`, `pytest`, `scripts/validar_config.py` e o gitleaks (com histórico completo).
- **Job 2, `publicar`:** depende do `portao` (`needs`) e só roda quando:
  1. o evento é `push` na `main` ou `workflow_dispatch`; **e**
  2. a variável `HF_SPACE_MODE` vale `static` ou `gradio`.

  Ele roda `scripts/publicar_hf.py --modo <HF_SPACE_MODE>` usando o secret `HF_TOKEN`.
- **Concorrência:** só uma publicação por vez. Se você salvar duas vezes seguidas, a segunda espera a primeira terminar.
- **Permissões mínimas:** o workflow só tem permissão de leitura no repositório.

### 7.3 O que você precisa configurar à mão (uma vez)

#### No Hugging Face, Fase A (agora)
1. **Verificar o e-mail** da conta (Settings → Account). Sem isso, a Fase B não libera.
2. **Criar o Space:** huggingface.co → *New Space*
   - Owner: `Surmani` · Space name: `agente-personalizado`
   - License: `mit` (ou a que preferir)
   - **SDK: Static** · Visibility: **Public**
3. **Criar um token de acesso:** Settings → *Access Tokens* → *Create new token* → tipo **Fine-grained**
   - Nome: `github-actions-agente`
   - Permissão: **Write** apenas no repositório `spaces/Surmani/agente-personalizado`
   - Copie o token (começa com `hf_`). **Ele só aparece uma vez.**

#### No GitHub, Fase A (agora)
4. No repositório → **Settings → Secrets and variables → Actions**:
   - Aba **Secrets** → *New repository secret*: `HF_TOKEN` = o token do passo 3.
   - Aba **Variables** → *New repository variable*:
     - `HF_SPACE_ID` = `Surmani/agente-personalizado`
     - `HF_SPACE_MODE` = `static`
5. **Settings → General → Default branch:** confirmar que é `main`.
6. (Opcional, recomendado) **Settings → Branches → Add rule** para `main`: marcar "Require status checks to pass" e escolher `portao`. Assim um pull request com erro não entra na `main`.

#### No seu computador, para testar o chat na Fase A
7. Copiar o `.env.example` para `.env` e colar sua `OPENROUTER_API_KEY`. O `.env` **nunca** vai para o GitHub, porque está no `.gitignore`.

#### No Hugging Face, Fase B (a partir de ~31/10/2026)
8. No Space → **Settings → Variables and secrets** → *New secret*:
   - `OPENROUTER_API_KEY` = sua chave do OpenRouter
   - (opcional) `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
9. No Space → **Settings → Space hardware** → escolher **ZeroGPU**. Se aparecer pedido de PRO, a conta ainda não completou 30 dias: espere 1 dia e tente de novo.

#### No GitHub, Fase B
10. Mudar a variável `HF_SPACE_MODE` de `static` para **`gradio`**.
11. Ir em **Actions → Publicar → Run workflow** (ou fazer qualquer commit). O script troca o README do Space para `sdk: gradio` e envia o chat.

> Se a troca de Static para Gradio no mesmo Space não funcionar, apague o Space e recrie com **o mesmo nome**, já como **Gradio + ZeroGPU**. Depois repita os passos 8 e 11. O link continua o mesmo.

---

## 8. Critérios de aceite

### Fase A
- [ ] O `config.yaml` inicial (seção 4.3) passa no portão de testes (T1–T16 ✅).
- [ ] `https://huggingface.co/spaces/Surmani/agente-personalizado` mostra a **vitrine**: logo LMS, "LMS Labs · Assistente", a descrição, o fundo preto → azul e o aviso "Chat em breve".
- [ ] No computador, o chat abre em `localhost:7860` e **responde em português** a "O que é um pipeline de dados?".
- [ ] Os botões de perguntas de exemplo funcionam localmente.
- [ ] **Fallback local:** com o 1º modelo trocado por um nome inexistente, o chat responde pelo 2º.
- [ ] **Todos falham local:** sem nenhuma chave no `.env`, o chat mostra a lista de motivos em português.
- [ ] **Mudança pelo GitHub:** trocar a `cor_secundaria` no site do GitHub → em poucos minutos a vitrine mostra a nova cor.
- [ ] **Erro proposital:** colocar `cor_primaria: "azulzinho"` → o workflow fica ❌, o resumo diz o que corrigir e **a vitrine anterior continua no ar**.
- [ ] **Chave proposital:** colocar um texto `sk-or-v1-teste123...` falso no `config.yaml` → a publicação é bloqueada pelo T9. Depois, desfazer.
- [ ] Nenhuma chave aparece no repositório, no histórico ou nos logs do Actions.

### Fase B
- [ ] O Space roda como **Gradio + ZeroGPU**, sem pagar nada.
- [ ] Abrir o link público e **conversar** com o assistente, com a resposta aparecendo aos poucos.
- [ ] Topo com logo, nome e descrição. Fundo com as cores do config. Chat fácil de ler. Tudo em português.
- [ ] Trocar uma **pergunta de exemplo** pelo GitHub → em poucos minutos o botão novo aparece no site.
- [ ] Erro proposital no config → publicação barrada e **o chat antigo continua funcionando**.
- [ ] Remover a `OPENROUTER_API_KEY` do Space (teste) → o chat mostra os motivos de falha. Depois, devolver a chave.
- [ ] Funciona no celular.

---

## 9. Ordem das tarefas de implementação

> Uma tarefa por vez. Ao fim de cada uma: os testes passam, há um commit, eu te mostro o resultado e **espero o seu OK** antes da próxima.

**Fase A**

1. **Esqueleto do projeto.** Criar `.gitignore`, `.env.example`, `requirements.txt`, `requirements-dev.txt`, `README.md` inicial e o `config.yaml` da seção 4.3, além das pastas `src/`, `tests/` e `scripts/` vazias.
   *Pronto quando:* a estrutura da seção 3 existe e o `.env` está ignorado pelo Git.
2. **Contrato do config.** Escrever `src/agente/config.py` (leitura, validação, padrões e mensagens em PT com a linha do arquivo), `scripts/validar_config.py` e os testes T1–T8 e T16.
   *Pronto quando:* configs com erros conhecidos geram as mensagens da seção 4.4.
3. **Provedores e fallback.** Escrever `src/agente/provedores.py` (OpenRouter, Anthropic, OpenAI, streaming e fallback) e os testes T10–T11 com provedores falsos. Escolher o 2º modelo `:free` e o modelo OpenAI com base nas listas atuais.
   *Pronto quando:* T10–T11 passam sem internet.
4. **Interface Gradio.** Escrever `src/agente/textos.py`, `src/agente/interface.py` (topo, cores, chat, botões, rodapé, layout para celular), `app.py` (com a função vazia `@spaces.GPU` ativada só no HF) e os testes T12–T13.
   *Pronto quando:* T12–T13 passam e a tela abre localmente.
5. **Teste local real.** Você coloca a chave do OpenRouter no `.env` e conversa com o assistente no computador. Ajustamos o visual juntos.
   *Pronto quando:* os itens "local" do checklist da Fase A estão ✅.
6. **Segurança.** Criar `.gitleaks.toml`, o teste T9 e uma checagem de que nenhum log imprime chave.
   *Pronto quando:* uma chave falsa plantada é detectada e removida.
7. **Vitrine estática.** Escrever `scripts/gerar_vitrine.py` e o teste T14.
   *Pronto quando:* o `index.html` gerado abre no navegador com a identidade LMS.
8. **Portão no GitHub Actions.** Criar o `publicar.yml` **só com o Job 1** e testar com um commit correto (✅) e um commit com erro proposital (❌).
   *Pronto quando:* o resumo de erro em PT aparece no Actions.
9. **Publicação da vitrine.** Escrever `scripts/publicar_hf.py`, adicionar o Job 2 e **você faz os passos manuais 1–6 da seção 7.3**.
   *Pronto quando:* a vitrine está no ar e todos os critérios da Fase A estão ✅.

**Fase B (a partir de ~31/10/2026)**

10. **Liberar o chat.** Conferir as versões de Python e Gradio aceitas pelo ZeroGPU, **você faz os passos manuais 8–11** e publicamos no modo `gradio`.
    *Pronto quando:* o chat responde no link público.
11. **Ensaio final.** Percorrer o checklist da Fase B (mudança de pergunta, erro proposital, falta de chave, celular) e atualizar o `README.md` com o link final para o portfólio.
    *Pronto quando:* todos os critérios da Fase B estão ✅.

---

## 10. Erros comuns e como resolver

| Sintoma | Causa provável | Como resolver |
|---|---|---|
| Workflow ❌ com "não é uma cor válida" | A cor não está no formato `#RRGGBB` (faltou `#`, tem 3 dígitos, ou é um nome como "azul"). | Use 6 dígitos hex com `#` e entre aspas: `"#2563EB"`. |
| Workflow ❌ com "erro de YAML" / "mapping values are not allowed" | Recuo errado, TAB, ou texto com `:` sem aspas. | Use 2 espaços por nível e coloque textos entre aspas. No GitHub, a aba *Preview* ajuda a ver o recuo. |
| Workflow ❌ com "campo desconhecido" | Erro de digitação no nome do campo. | Use o nome sugerido na mensagem ("Você quis dizer…"). |
| Workflow ❌ com "logo não existe" | O arquivo não foi enviado para `assets/` ou o nome difere (maiúsculas contam!). | Envie a imagem em `assets/` (*Add file → Upload files*) e copie o nome exato. |
| Workflow ❌ no gitleaks | Há uma chave (real ou parecida) no código ou no histórico. | Remova a chave. **Se for real, revogue-a no site do provedor e gere outra**: apagar do arquivo não basta, porque ela continua no histórico. |
| Job "publicar" não aparece / foi pulado | `HF_SPACE_MODE` vazia, ou o commit não foi na `main`. | Confira a variável em Settings → Variables e se o commit foi na `main`. |
| Publicar ❌ com 401/403 | `HF_TOKEN` errado, expirado ou sem permissão de escrita no Space. | Gere um novo token *fine-grained* com **Write** no Space e atualize o secret. |
| Publicar ❌ com 404 / "Repository not found" | `HF_SPACE_ID` errado ou Space não criado. | Use exatamente `Surmani/agente-personalizado` e crie o Space antes. |
| Space mostra "No @spaces.GPU function detected" | Faltou a função vazia exigida pelo ZeroGPU, ou ela não foi carregada. | Confirme que o `app.py` publicado tem a função `@spaces.GPU` (RF24) e que `spaces` está no `requirements.txt`. |
| Ao escolher ZeroGPU, o HF pede PRO | A conta tem menos de 30 dias ou o e-mail não foi verificado. | Verifique o e-mail e espere completar 30 dias (desde 01/10/2026). Plano B: hospedar o Gradio no **Render** (gratuito, 750h/mês, dorme depois de ~15 min sem uso). |
| Space em "Runtime error" logo após publicar | Biblioteca faltando ou versão de Gradio/Python incompatível. | Abra a aba **Logs** do Space, leia a última linha de erro e ajuste o `requirements.txt` / `sdk_version`. |
| Space demora para abrir | O Space estava dormindo por falta de visitas. | Normal no plano grátis. Espere alguns segundos. |
| Chat: "modelo lotado (limite de uso)" | Limite dos modelos `:free` do OpenRouter atingido. | Espere alguns minutos, adicione outro modelo `:free` à lista ou ative um provedor pago. |
| Chat: "chave não configurada" | O secret não existe no Space, ou o nome está errado. | Crie o secret com o nome **exato** (`OPENROUTER_API_KEY`) e reinicie o Space (*Settings → Restart*). |
| Chat: "sem crédito" (402) | A conta do provedor está sem saldo. | Adicione créditos ou use só modelos `:free`. |
| Chat: "modelo não encontrado" (404) | O nome do modelo mudou ou foi removido. | Copie o nome exato em openrouter.ai/models e atualize o `config.yaml`. |
| Mudei o config, mas o site não mudou | O workflow ainda está rodando, falhou, ou o navegador mostra a versão em cache. | Veja a aba **Actions**, espere o Space terminar o "Building" e recarregue com Ctrl+F5. |
| Local: `ModuleNotFoundError` | As bibliotecas não estão instaladas. | Rode a instalação do `requirements-dev.txt` (o comando estará no README). |
| Local: porta 7860 ocupada | Outro app (ou o mesmo, já aberto) está usando a porta. | Feche o outro terminal ou use outra porta (instruções no README). |
| Texto do topo difícil de ler (aviso T16) | Cor de fundo clara com texto claro. | Escolha cores de fundo mais escuras ou mude a combinação. O aviso não bloqueia a publicação. |

---

### Referências
- Hugging Face — Spaces ZeroGPU: https://huggingface.co/docs/hub/en/spaces-zerogpu
- Hugging Face — Spaces Overview (cabeçalho do README, secrets): https://huggingface.co/docs/hub/en/spaces-overview
- OpenRouter — documentação e modelos: https://openrouter.ai/docs · https://openrouter.ai/models
- Gradio — documentação: https://www.gradio.app/docs
- gitleaks: https://github.com/gitleaks/gitleaks
