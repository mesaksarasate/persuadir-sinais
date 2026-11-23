# Persuadir Sinais — V3 (stack 100% gratuita, sem cartão)

Mesmo motor de decisão da V2 (confirmação multi-timeframe + autocalibração), rodando numa combinação de três serviços gratuitos que **não pedem cartão em etapa nenhuma**:

- **GitHub Actions** — executa o código Python (o mesmo de sempre, sem limite de CPU)
- **cron-job.org** — dispara a execução a cada 1 minuto exato, por fora do agendador do GitHub
- **Cloudflare Workers KV** — guarda o histórico/acurácia entre uma execução e outra (substitui o Firestore)

## O que muda em relação à V2

| | V2 (Google Cloud) | V3 (sem cartão) |
|---|---|---|
| Execução | Cloud Functions | GitHub Actions |
| Agendamento | Cloud Scheduler (nativo, 1min) | cron-job.org → `repository_dispatch` (externo, 1min) |
| Memória persistente | Firestore | Cloudflare Workers KV |
| Exige cartão | Sim | **Não** |

## Arquivos

Iguais à V2 (`indicators.py`, `signal_engine.py`, `data_feed.py`, `notifier.py`, `config.py`, `backtest.py`), mais:

- `state_store.py` — agora com um terceiro backend, `CloudflareKVStore` (testado com chamadas simuladas — lê, grava, resolve sinais e calcula acurácia corretamente)
- `main.py` — simplificado, sem dependência do Cloud Functions
- `.github/workflows/sinais.yml` — o workflow que o GitHub vai rodar
- `requirements.txt` — agora inclui `requests` (para falar com a API da Cloudflare)

## Validação feita até agora

- Sintaxe de todos os módulos, correta.
- `CloudflareKVStore` testado com chamadas HTTP simuladas (sem gastar nenhuma chamada real): grava histórico, grava e resolve sinal pendente, calcula acurácia — tudo correto.
- Seleção automática de backend (`get_store()`) confirmada: usa arquivo local quando não há configuração da Cloudflare, usa Cloudflare quando há.

**Falta** testar com a Cloudflare de verdade (só dá pra fazer depois que você criar a conta e o namespace — próximos passos) e rodar o backtest com dados reais da Binance (fora desta sandbox).

## Próximos passos de configuração (vou te guiar um de cada vez)

1. Criar o repositório no GitHub (pode ser público — sem segredo nenhum exposto)
2. Criar a conta Cloudflare + namespace do Workers KV + token de API
3. Criar a conta no cron-job.org e configurar o disparo a cada 1 minuto
4. Cadastrar os 3 secrets no GitHub (`CF_ACCOUNT_ID`, `CF_KV_NAMESPACE_ID`, `CF_API_TOKEN`)
5. Testar manualmente (botão "Run workflow") antes de ligar o cron de verdade

Me avise quando quiser começar pelo passo 1.
