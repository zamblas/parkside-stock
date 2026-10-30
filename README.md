# Stock Parkside Lidl PT

Página com a disponibilidade de produtos Parkside (sobretudo baterias e carregadores) nas lojas Lidl em Portugal.

Os dados são lidos do lidl.pt por um GitHub Action de hora a hora e publicados como site estático no GitHub Pages.

## Ficheiros

| Ficheiro | Para quê |
|---|---|
| `lidl.py` | Acesso ao lidl.pt: pesquisa de produtos, stock por loja, lista de lojas |
| `build.py` | Gera `site/index.html` + `site/data.json` |
| `server.py` | Pré-visualização local com dados ao vivo (`python server.py` → http://localhost:8765) |
| `index.html` | A página |
| `stores.json` | Lista das lojas (usada se a API de lojas não estiver disponível) |

## Lista de vigilância

Cada visitante pode "vigiar" produtos (ID ou URL do lidl.pt). A lista fica só no browser dele (localStorage) e o stock desses produtos é pedido ao lidl.pt ao vivo, directamente do browser (os endpoints permitem CORS).

## Publicar no GitHub Pages

1. Criar um repositório no GitHub e enviar estes ficheiros para o ramo `main`.
2. Em **Settings → Pages → Build and deployment**, escolher **Source: GitHub Actions**.
3. (Opcional) Em **Settings → Secrets and variables → Actions**, criar o secret `LIDL_STORES_KEY` para actualizar a lista de lojas automaticamente. Sem ele usa-se `stores.json`.
4. Em **Actions → Actualizar stock e publicar → Run workflow** para a primeira publicação.

O site fica em `https://<utilizador>.github.io/<repositório>/`.

## Notas

- O Lidl só publica stock por loja durante a campanha do produto; antes e depois aparece "Sem info".
- Usa endpoints internos do lidl.pt, sem garantias: podem mudar ou ser bloqueados.
- O agendamento do GitHub pode atrasar alguns minutos, e é desligado após 60 dias sem actividade no repositório (basta reactivar em Actions).
