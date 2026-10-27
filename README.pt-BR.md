# Micro-POCs — Experimentos pequenos, resultados mensuráveis

**Experimentos independentes e reproduzíveis de engenharia de software.**

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

Este repositório público reúne microprovas de conceito que isolam uma hipótese técnica, oferecem código executável e testes, registram medições e deixam claras as limitações. O foco é verificar comportamento, inclusive quando o resultado não demonstra ganho.

## Catálogo de experimentos

| Experimento | Investigação | Execução |
|---|---|---|
| [01 · Paginação de APIs](api-pagination/README.md) | OFFSET/LIMIT versus paginação por cursor, SQLite e HTTP | `python3 certify.py --repeat 100` |
| [02 · Logging assíncrono](async-logging/README.md) | Escrita síncrona em buffer versus fila assíncrona limitada | `python3 poc.py certify --events 10000` |
| [03 · Cache](caching/README.md) | SQLite direto versus cache-aside com LRU e TTL | `python3 poc.py certify` |

## Requisitos e instalação

Ambiente: **Linux**, **Python 3.10+**, biblioteca padrão do Python. Sem dependências externas.

```bash
git clone https://github.com/mikeninerbravog/micro-pocs.git
cd micro-pocs

# Paginação
cd api-pagination
python3 poc.py init
python3 certify.py --repeat 100

# Logging assíncrono
cd ../async-logging
python3 poc.py bench --events 100000
python3 poc.py certify --events 10000

# Cache
cd ../caching
python3 poc.py init --rows 100000
python3 poc.py bench --requests 100000
python3 poc.py certify
```

Para explorar a API HTTP de paginação: `python3 poc.py serve --port 8080` e, em outro terminal, `python3 benchmark.py --repeat 100`. Cada subdiretório contém documentação de comandos, critérios, resultados e limites.

## Resultados observados

- **Paginação:** o cursor reduziu o custo de consultas em páginas profundas neste workload.
- **Logging assíncrono:** a fila aumentou custos e descartou eventos quando saturada; não houve ganho de desempenho.
- **Cache:** maior throughput e menor latência mediana com chaves frequentemente acessadas, mas p95 não melhorou.

## Leitura correta dos resultados

**p50** é a mediana; **p95**, o percentil 95. Throughput é a taxa de operações concluídas ou persistidas, conforme definição de cada POC. **PASS** indica aprovação dos testes definidos para o experimento, e **COMPLETE** indica que o experimento terminou; nenhum dos dois significa prontidão para produção.

Os números dependem do hardware, armazenamento, versão do Python, escalonamento e distribuição da carga. Execute novamente no seu ambiente para comparar.

## Estrutura, dados e licença

Cada diretório oferece fontes, README e evidências de exemplo. Bancos SQLite gerados, logs volumosos e arquivos compilados não são versionados. Os experimentos são pequenos e intencionalmente não incluem todas as exigências de um sistema de produção.

Consulte [LICENSE](LICENSE) para a licença.
