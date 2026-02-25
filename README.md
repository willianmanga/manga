# 📖 MangaNexus

> Leitor de mangás, manhwas e manhuas sem anúncios — múltiplas fontes, um só lugar.

![Tecnologias](https://img.shields.io/badge/Backend-Python%203-blue?style=flat-square)
![Frontend](https://img.shields.io/badge/Frontend-HTML%2FJS%2FCSS-yellow?style=flat-square)
![Deploy Backend](https://img.shields.io/badge/Deploy-Render-purple?style=flat-square)
![Deploy Frontend](https://img.shields.io/badge/Deploy-Vercel-black?style=flat-square)
![DB](https://img.shields.io/badge/Database-Supabase-green?style=flat-square)
![Licença](https://img.shields.io/badge/Licença-MIT-orange?style=flat-square)

---

## ✨ Funcionalidades

- 🔍 **Busca simultânea** em MangaZord, MangaDex e ComicK (busca paralela)
- 🆕 **Lançamentos diários** na tela inicial — veja o que saiu hoje
- 🔥 **Mais populares** — títulos com mais seguidores no MangaDex
- 📖 **Leitor integrado** com lazy loading por Intersection Observer
- ⏭️ **Navegação no fim do capítulo** — botão Próximo sem precisar rolar
- ⭐ **Score do MyAnimeList** via Jikan API (carregado em background)
- ❤️ **Favoritos** persistidos no Supabase
- 📅 **Histórico de leitura** persistido no Supabase
- 🌐 **Filtro por gênero** em busca e exploração
- 🇧🇷 Suporte a PT-BR, PT e EN com fallback automático
- ⚡ **Cache em memória** no backend (10–60 min por tipo de dados)
- 📱 Interface responsiva para mobile

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────┐
│              FRONTEND (Vercel)                  │
│           HTML + CSS + JavaScript               │
│     (SPA sem frameworks, arquivo único)         │
└───────────────────┬─────────────────────────────┘
                    │ HTTP REST
┌───────────────────▼─────────────────────────────┐
│             BACKEND (Render)                    │
│         Python 3 — http.server                  │
│    Cache em memória + ThreadPoolExecutor        │
└──────────┬──────────────────────────────────────┘
           │                      │
   ┌───────▼──────┐      ┌───────▼──────┐
   │   APIs de    │      │   Supabase   │
   │   Conteúdo   │      │ (PostgreSQL) │
   │ MangaDex     │      │ favoritos    │
   │ MangaZord    │      │ historico    │
   │ ComicK       │      └──────────────┘
   │ Jikan (MAL)  │
   └──────────────┘
```

---

## 🚀 Como rodar localmente

### Pré-requisitos
- Python 3.8+
- Conta no [Supabase](https://supabase.com) (gratuita)

### 1. Clone o repositório

```bash
git clone https://github.com/seu-usuario/manganexus.git
cd manganexus
```

### 2. Configure o Supabase

No painel do Supabase, crie as seguintes tabelas:

**Tabela `historico`:**
```sql
create table historico (
  id            bigserial primary key,
  manga_id      text not null,
  manga_title   text,
  manga_cover   text,
  manga_source  text,
  chapter_id    text unique,
  chapter_num   text,
  manga_data    jsonb,
  lido_em       timestamptz default now()
);
```

**Tabela `favoritos`:**
```sql
create table favoritos (
  id            bigserial primary key,
  manga_id      text unique not null,
  manga_title   text,
  manga_cover   text,
  manga_source  text,
  manga_data    jsonb,
  salvo_em      timestamptz default now()
);
```

### 3. Configure as variáveis de ambiente

```bash
export SUPABASE_URL="https://seu-projeto.supabase.co"
export SUPABASE_KEY="sua-chave-anon-publica"
export PORT=8765
```

Ou crie um arquivo `.env` na pasta `backend/` e carregue com `python-dotenv`.

### 4. Inicie o backend

```bash
cd backend
pip install -r requirements.txt   # se houver dependências extras
python server.py
```

O backend sobe em `http://localhost:8765`.

### 5. Sirva o frontend

Abra o arquivo `frontend/index.html` diretamente no navegador, **ou** use um servidor local:

```bash
cd frontend
python -m http.server 3000
# Acesse http://localhost:3000
```

> ⚠️ Lembre de alterar a variável `API` no `index.html` para `http://localhost:8765/api` durante o desenvolvimento local.

---

## ☁️ Deploy em produção (gratuito)

### Backend → Render

1. Crie uma conta em [render.com](https://render.com)
2. Clique em **New → Web Service**
3. Aponte para a pasta `backend/`
4. Configure:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt` (ou deixe vazio se não tiver deps)
   - **Start Command:** `python server.py`
5. Adicione as variáveis de ambiente:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
6. Deploy! A URL ficará no formato `https://seu-app.onrender.com`

> ℹ️ O plano gratuito do Render hiberna após 15 min de inatividade. O primeiro acesso pode demorar ~30s para "acordar" o servidor.

### Frontend → Vercel

1. Crie uma conta em [vercel.com](https://vercel.com)
2. Importe o repositório
3. Configure o **Root Directory** como `frontend/`
4. Na variável `API` do `index.html`, use a URL do Render:
   ```js
   const API = 'https://seu-app.onrender.com/api';
   ```
5. Deploy!

---

## 📡 Endpoints da API

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/api/search?q=...&lang=pt-br` | Busca paralela em todas as fontes |
| `GET` | `/api/chapters?id=...&source=...` | Capítulos de um mangá |
| `GET` | `/api/pages?id=...&source=...` | URLs das páginas de um capítulo |
| `GET` | `/api/image?url=...` | Proxy de imagem (resolve CORS) |
| `GET` | `/api/explore?type=manga&offset=0` | Explorar por tipo |
| `GET` | `/api/releases?lang=pt-br` | Lançamentos das últimas horas |
| `GET` | `/api/popular?lang=pt-br` | Títulos mais populares |
| `GET` | `/api/score?title=...` | Score no MyAnimeList |
| `GET` | `/api/historico` | Lista histórico de leitura |
| `POST` | `/api/historico/salvar` | Salva capítulo lido |
| `GET` | `/api/favoritos` | Lista favoritos |
| `POST` | `/api/favoritos/salvar` | Adiciona favorito |
| `POST` | `/api/favoritos/remover` | Remove favorito |
| `GET` | `/api/cache/stats` | Estatísticas do cache |

---

## ⚙️ Sistema de Cache

O backend utiliza cache em memória com TTL configurável por tipo de dado:

| Tipo | TTL |
|------|-----|
| Busca por título | 10 minutos |
| Capítulos de um mangá | 30 minutos |
| Páginas de um capítulo | 1 hora |
| Lançamentos diários | 15 minutos |
| Populares | 1 hora |
| Explore/Descobrir | 30 minutos |
| Score MAL (Jikan) | 24 horas |

Cache não persiste entre reinicializações do servidor.

---

## 🔍 Fontes de Conteúdo

| Fonte | Tipo | Idiomas | Prioridade |
|-------|------|---------|------------|
| [MangaZord](https://mangazord.com) | Mangá/Manhwa/Manhua | PT-BR | 1ª |
| [MangaDex](https://mangadex.org) | Mangá/Manhwa/Manhua | Multi | 2ª |
| [ComicK](https://comick.fun) | Mangá/Manhwa/Manhua | Multi | 3ª |
| [Jikan](https://jikan.moe) | Scores MAL | — | Auxiliar |

---

## 📁 Estrutura do Projeto

```
manga-main/
├── backend/
│   ├── server.py          # Servidor HTTP Python (toda a lógica)
│   ├── requirements.txt   # Dependências Python (vazio — usa stdlib)
│   └── render.yaml        # Configuração de deploy no Render
├── frontend/
│   ├── index.html         # SPA completa (HTML + CSS + JS em um arquivo)
│   └── vercel.json        # Configuração de deploy na Vercel
└── README.md
```

---

## 🛠️ Tecnologias

- **Backend:** Python 3, `http.server`, `urllib`, `threading`, `concurrent.futures`
- **Frontend:** HTML5, CSS3 (variáveis CSS, grid, flexbox), JavaScript ES2020
- **Banco de dados:** Supabase (PostgreSQL gerenciado)
- **APIs externas:** MangaDex, MangaZord, ComicK, Jikan (MyAnimeList)
- **Fontes:** Google Fonts (Bebas Neue + Syne)

---

## 🤝 Contribuições

Contribuições são bem-vindas! Por favor, leia o nosso [Guia de Contribuição](CONTRIBUTING.md) para saber como você pode ajudar.

## ⚖️ Licença

Este projeto está licenciado sob a [Licença MIT](LICENSE). Consulte o arquivo `LICENSE` para mais detalhes.

## 🤝 Código de Conduta

Para garantir um ambiente acolhedor e respeitoso, este projeto adota o [Código de Conduta do Contribuidor](.github/CODE_OF_CONDUCT.md). Ao participar, você concorda em seguir este código.


---


