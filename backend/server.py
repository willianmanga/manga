#!/usr/bin/env python3
"""
MangaRX Backend — Adaptado para Render + Supabase
"""

import json
import urllib.request
import urllib.parse
import os
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("PORT", 8765))

HEADERS = {"User-Agent": "MangaRX/2.0", "Accept": "application/json"}

# ─── SUPABASE ─────────────────────────────────────────────────────────────────

SUPA_URL = os.environ.get("SUPABASE_URL", "https://txfklnxsuzdawuhbxaov.supabase.co")
SUPA_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR4ZmtsbnhzdXpkYXd1aGJ4YW92Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE4NzM3OTksImV4cCI6MjA4NzQ0OTc5OX0.0vQ0DGm1h7GVUMBZKqUtfqsJS165Ed2_JvYxuVQyEeA")
SUPA_HEADERS = {
    "apikey": SUPA_KEY,
    "Authorization": f"Bearer {SUPA_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def supa_get(table, params=None):
    url = f"{SUPA_URL}/rest/v1/{table}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=SUPA_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def supa_post(table, data):
    url = f"{SUPA_URL}/rest/v1/{table}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=SUPA_HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def supa_delete(table, match_col, match_val):
    url = f"{SUPA_URL}/rest/v1/{table}?{match_col}=eq.{urllib.parse.quote(str(match_val))}"
    req = urllib.request.Request(url, headers=SUPA_HEADERS, method="DELETE")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status

def supa_upsert(table, data, on_conflict):
    url = f"{SUPA_URL}/rest/v1/{table}"
    headers = dict(SUPA_HEADERS)
    headers["Prefer"] = f"resolution=merge-duplicates,return=representation"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def fetch(url, extra_headers=None):
    headers = dict(HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

# ─── MANGADEX ────────────────────────────────────────────────────────────────

MDEX = "https://api.mangadex.org"
MDEX_UPLOADS = "https://uploads.mangadex.org"

def mdex_get(path, params=None):
    url = MDEX + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    return fetch(url)

# IDs de tags do MangaDex por gênero
MDEX_TAGS = {
    "action":       "391b0423-d847-456f-aff0-8b0cfc03066b",
    "adventure":    "87cc87cd-a395-47af-b27a-93258283bbc6",
    "comedy":       "4d32cc48-9f00-4cca-9b5a-a839f0764984",
    "drama":        "b9af3a63-f058-46de-a9a0-e0c13906197a",
    "fantasy":      "cdc58593-87dd-415e-bbc0-2ec27bf404cc",
    "horror":       "cdad7e68-1419-41dd-bdce-27753074a640",
    "mystery":      "ee968100-4191-4968-93d3-f82d72be7e46",
    "romance":      "423e2eae-a7a2-4a8b-ac03-a8351462d71d",
    "sci-fi":       "256c8bd9-4904-4360-bf4f-508a76d67183",
    "slice-of-life":"e5301a23-ebd9-49dd-a0cb-2add944c7fe9",
    "sports":       "69964a64-2f90-4d33-beeb-f3ed2875eb4c",
    "supernatural": "eabc5b4c-6aff-42f3-b657-3e90cbd00b75",
    "psychological":"3b60b75c-a2d7-4860-ab56-05f391bb889c",
    "historical":   "33771934-028e-4cb3-8744-691e866a923e",
    "mecha":        "50880a9d-5440-4732-9afb-8f457127e836",
    "isekai":       "ace04997-f6bd-436e-b261-779182193d3d",
    "martial-arts": "799c202e-7daa-44eb-9cf7-8a3c0441531e",
    "music":        "f8f62932-27da-4fe4-8ee1-6779a8c5edba",
    "school-life":  "caaa44eb-cd40-4177-b930-79d3ef2afe87",
    "harem":        "aafb99c1-7f60-43fa-b75f-fc9502ce29c7",
}

def mdex_search(q, lang, tags=None):
    params = {
        "title": q, "limit": 15,
        "availableTranslatedLanguage[]": [lang, "pt", "en"],
        "includes[]": ["cover_art"],
        "order[relevance]": "desc",
        "contentRating[]": ["safe", "suggestive", "erotica"]
    }
    if tags:
        tag_ids = [MDEX_TAGS[t] for t in tags if t in MDEX_TAGS]
        if tag_ids:
            params["includedTags[]"] = tag_ids
    data = mdex_get("/manga", params)
    results = []
    for m in data.get("data", []):
        mid = m["id"]
        attrs = m["attributes"]
        title_map = attrs.get("title", {})
        name = (title_map.get("pt-br") or title_map.get("pt") or
                title_map.get("en") or next(iter(title_map.values()), "Sem título"))
        desc_map = attrs.get("description", {})
        desc = desc_map.get("pt-br") or desc_map.get("pt") or desc_map.get("en") or ""
        cover = ""
        for rel in m.get("relationships", []):
            if rel["type"] == "cover_art":
                fname = rel.get("attributes", {}).get("fileName", "")
                if fname:
                    cover = f"{MDEX_UPLOADS}/covers/{mid}/{fname}.256.jpg"
        tags = [t["attributes"]["name"].get("en", "") for t in attrs.get("tags", [])]
        results.append({
            "id": mid, "source": "mangadex",
            "title": name, "description": desc[:400],
            "cover": cover, "status": attrs.get("status", ""),
            "tags": tags[:6], "score": None, "external": None
        })
    return results

def mdex_chapters(mid, lang):
    data = mdex_get(f"/manga/{mid}/feed", {
        "translatedLanguage[]": [lang, "pt", "en"],
        "order[chapter]": "asc", "limit": 200,
        "includes[]": ["scanlation_group"]
    })
    chapters = []
    for c in data.get("data", []):
        attrs = c["attributes"]
        chapters.append({
            "id": c["id"], "source": "mangadex",
            "chapter": attrs.get("chapter") or "?",
            "volume": attrs.get("volume") or "",
            "title": attrs.get("title") or "",
            "lang": attrs.get("translatedLanguage", ""),
            "pages": attrs.get("pages", 0)
        })
    return chapters, data.get("total", 0)

def mdex_pages(cid):
    data = fetch(f"{MDEX}/at-home/server/{cid}")
    base = data.get("baseUrl", "")
    ch = data.get("chapter", {})
    hash_ = ch.get("hash", "")
    imgs = ch.get("data", [])
    return [f"{base}/data/{hash_}/{img}" for img in imgs]

# ─── MANGAZORD ───────────────────────────────────────────────────────────────

MZORD = "https://mangazord.com/api"
MZORD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://mangazord.com",
    "Accept": "application/json",
    "Origin": "https://mangazord.com"
}

def mzord_get(path, params=None):
    url = MZORD + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers=MZORD_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def mzord_search(q):
    try:
        data = mzord_get("/search", {"title": q, "limit": 15, "offset": 0})
        results = []
        for m in data.get("data", []):
            mid = m["id"]
            attrs = m.get("attributes", {})
            title_map = attrs.get("title", {})
            name = (title_map.get("pt-br") or title_map.get("pt") or
                    title_map.get("en") or next(iter(title_map.values()), "?"))
            desc_map = attrs.get("description", {})
            desc = desc_map.get("pt-br") or desc_map.get("pt") or desc_map.get("en") or ""
            cover = ""
            for rel in m.get("relationships", []):
                if rel.get("type") == "cover_art":
                    fname = rel.get("attributes", {}).get("fileName", "")
                    if fname:
                        cover = f"https://mangazord.com/api/covers/{mid}/{fname}.256.jpg"
            tags = []
            for t in attrs.get("tags", []):
                tag_name = t.get("attributes", {}).get("name", {})
                n = tag_name.get("pt-br") or tag_name.get("en", "")
                if n: tags.append(n)
            orig_lang = attrs.get("originalLanguage", "")
            tipo_map = {"ja": "Manga", "ko": "Manhwa", "zh": "Manhua", "zh-hk": "Manhua"}
            results.append({
                "id": mid, "source": "mangazord",
                "title": name, "description": desc[:400],
                "cover": cover, "status": attrs.get("status", ""),
                "tags": tags[:6], "score": None, "external": None,
                "tipo": tipo_map.get(orig_lang, ""),
                "originalLanguage": orig_lang,
                "availableLangs": attrs.get("availableTranslatedLanguages", [])
            })
        return results
    except Exception as e:
        print(f"MangaZord search erro: {e}")
        return []

def mzord_chapters(mid, lang):
    try:
        lang_param = lang if lang in ("pt-br", "pt", "en") else "pt-br"
        data = mzord_get(f"/manga/{mid}/all-chapters", {
            "translatedLanguage": lang_param,
            "order": "asc"
        })
        chapters = []
        for c in data.get("data", []):
            attrs = c.get("attributes", {})
            chapters.append({
                "id": c["id"], "source": "mangazord",
                "chapter": attrs.get("chapter") or "?",
                "volume": attrs.get("volume") or "",
                "title": attrs.get("title") or "",
                "lang": attrs.get("translatedLanguage", "pt-br"),
                "pages": attrs.get("pages", 0)
            })
        return chapters, data.get("total", len(chapters))
    except Exception as e:
        print(f"MangaZord chapters erro: {e}")
        return [], 0

def mzord_pages(cid):
    try:
        data = mzord_get(f"/chapter/{cid}")
        pages_data = data.get("pages", {})
        base = pages_data.get("baseUrl", "")
        ch = pages_data.get("chapter", {})
        hash_ = ch.get("hash", "")
        imgs = ch.get("data", [])
        return [f"{base}/data/{hash_}/{img}" for img in imgs]
    except Exception as e:
        print(f"MangaZord pages erro: {e}")
        return []

COMICK = "https://api.comick.fun"

def comick_search(q, lang, tags=None):
    lang_code = "pt" if lang in ("pt-br", "pt") else "en"
    url = f"{COMICK}/v1.0/search?q={urllib.parse.quote(q)}&limit=15&lang={lang_code}&t=true"
    if tags:
        # ComicK aceita gêneros como parâmetro "genres"
        url += "&genres=" + ",".join(tags)
    try:
        data = fetch(url, {"Referer": "https://comick.fun"})
        results = []
        for m in (data if isinstance(data, list) else []):
            mid = m.get("hid") or m.get("id", "")
            slug = m.get("slug", "")
            title = m.get("title") or slug
            desc = m.get("desc") or m.get("description") or ""
            md_covers = m.get("md_covers", [])
            cover = ""
            if md_covers:
                b2key = md_covers[0].get("b2key", "")
                if b2key:
                    cover = f"https://meo.comick.pictures/{b2key}"
            tags = [g.get("name", "") for g in m.get("genres", [])]
            status_map = {1: "ongoing", 2: "completed", 3: "cancelled", 4: "hiatus"}
            status = status_map.get(m.get("status"), str(m.get("status", "")))
            results.append({
                "id": mid, "source": "comick", "slug": slug,
                "title": title, "description": str(desc)[:400],
                "cover": cover, "status": status,
                "tags": tags[:6], "score": m.get("rating"),
                "external": None
            })
        return results
    except:
        return []

def comick_chapters(hid, slug, lang):
    lang_code = "pt" if lang in ("pt-br", "pt") else "en"
    url = f"{COMICK}/comic/{hid}/chapters?lang={lang_code}&limit=200"
    try:
        data = fetch(url, {"Referer": "https://comick.fun"})
        chapters = []
        for c in data.get("chapters", []):
            chapters.append({
                "id": c.get("hid", ""), "source": "comick",
                "chapter": str(c.get("chap") or "?"),
                "volume": str(c.get("vol") or ""),
                "title": c.get("title") or "",
                "lang": c.get("lang", ""),
                "pages": c.get("images_count", 0)
            })
        return chapters, len(chapters)
    except:
        return [], 0

def comick_pages(hid):
    url = f"{COMICK}/chapter/{hid}?tachiyomi=true"
    try:
        data = fetch(url, {"Referer": "https://comick.fun"})
        chapter = data.get("chapter", {})
        imgs = chapter.get("md_images", []) or data.get("images", [])
        pages = []
        for img in imgs:
            b2key = img.get("b2key") or img.get("url", "")
            if b2key:
                if b2key.startswith("http"):
                    pages.append(b2key)
                else:
                    pages.append(f"https://meo.comick.pictures/{b2key}")
        return pages
    except:
        return []

# ─── JIKAN ───────────────────────────────────────────────────────────────────

JIKAN = "https://api.jikan.moe/v4"
_jikan_cache = {}
_jikan_lock = threading.Lock()

def jikan_score(title):
    with _jikan_lock:
        if title in _jikan_cache:
            return _jikan_cache[title]
    try:
        time.sleep(0.4)
        url = f"{JIKAN}/manga?q={urllib.parse.quote(title)}&limit=1"
        data = fetch(url)
        items = data.get("data", [])
        if items:
            score = items[0].get("score")
            with _jikan_lock:
                _jikan_cache[title] = score
            return score
    except:
        pass
    return None

# ─── HANDLER ─────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_json(self, data, status=200):
        try:
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Connection", "close")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_file(self, path, ct):
        if os.path.exists(path):
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}

            if path == "/api/historico/salvar":
                try:
                    supa_delete("historico", "chapter_id", body.get("chapter_id",""))
                except: pass
                supa_post("historico", {
                    "manga_id": body.get("manga_id",""),
                    "manga_title": body.get("manga_title",""),
                    "manga_cover": body.get("manga_cover",""),
                    "manga_source": body.get("manga_source",""),
                    "chapter_id": body.get("chapter_id",""),
                    "chapter_num": body.get("chapter_num",""),
                    "manga_data": body.get("manga_data",{})
                })
                self.send_json({"ok": True})

            elif path == "/api/favoritos/salvar":
                supa_upsert("favoritos", {
                    "manga_id": body.get("manga_id",""),
                    "manga_title": body.get("manga_title",""),
                    "manga_cover": body.get("manga_cover",""),
                    "manga_source": body.get("manga_source",""),
                    "manga_data": body.get("manga_data",{})
                }, "manga_id")
                self.send_json({"ok": True})

            elif path == "/api/favoritos/remover":
                supa_delete("favoritos", "manga_id", body.get("manga_id",""))
                self.send_json({"ok": True})

            else:
                self.send_response(404); self.end_headers()

        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_POST(self):
        self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        p = urllib.parse.parse_qs(parsed.query)
        g = lambda k, d="": p.get(k, [""])[0] or d

        try:
            if path in ("/", "/index.html"):
                self.send_file(os.path.join(os.path.dirname(__file__), "index.html"),
                               "text/html; charset=utf-8")

            elif path == "/api/search":
                q = g("q"); lang = g("lang", "pt-br"); source = g("source", "all")
                tags_raw = p.get("tags[]", [])
                tags = tags_raw if tags_raw else None
                results = []
                # MangaZord primeiro (melhor PT-BR)
                if source in ("all", "mangazord"):
                    mz = mzord_search(q)
                    results += mz
                # MangaDex como complemento/fallback
                if source in ("all", "mangadex"):
                    results += mdex_search(q, lang, tags)
                # ComicK
                if source in ("all", "comick"):
                    results += comick_search(q, lang, tags)
                seen = set()
                unique = []
                for r in results:
                    key = r["title"].lower().strip()[:30]
                    if key not in seen:
                        seen.add(key)
                        unique.append(r)
                self.send_json({"results": unique})

            elif path == "/api/chapters":
                mid = g("id"); lang = g("lang", "pt-br")
                source = g("source", "mangadex"); slug = g("slug")
                if source == "comick":
                    chs, total = comick_chapters(mid, slug, lang)
                elif source == "mangazord":
                    chs, total = mzord_chapters(mid, lang)
                    # fallback para MangaDex se MangaZord falhar
                    if not chs:
                        chs, total = mdex_chapters(mid, lang)
                else:
                    chs, total = mdex_chapters(mid, lang)
                self.send_json({"chapters": chs, "total": total})

            elif path == "/api/pages":
                cid = g("id"); source = g("source", "mangadex")
                if source == "comick":
                    pages = comick_pages(cid)
                elif source == "mangazord":
                    pages = mzord_pages(cid)
                    # fallback para MangaDex se MangaZord falhar
                    if not pages:
                        pages = mdex_pages(cid)
                else:
                    pages = mdex_pages(cid)
                self.send_json({"pages": pages})

            elif path == "/api/image":
                img_url = g("url")
                if not img_url or not img_url.startswith("https://"):
                    self.send_response(400); self.end_headers(); return
                try:
                    req = urllib.request.Request(img_url, headers={
                        "User-Agent": "MangaRX/2.0",
                        "Referer": "https://mangadex.org"
                    })
                    with urllib.request.urlopen(req, timeout=15) as r:
                        img_data = r.read()
                        ct = r.headers.get("Content-Type", "image/jpeg")
                    self.send_response(200)
                    self.send_header("Content-Type", ct)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Length", len(img_data))
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    self.wfile.write(img_data)
                except Exception as e:
                    self.send_response(404); self.end_headers()

            elif path == "/api/score":
                score = jikan_score(g("title"))
                self.send_json({"score": score})

            elif path == "/api/historico":
                try:
                    dados = supa_get("historico", {"order": "lido_em.desc", "limit": 100})
                    self.send_json({"historico": dados})
                except Exception as e:
                    self.send_json({"historico": [], "error": str(e)})

            elif path == "/api/historico/salvar":
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(length))
                    # remove duplicata do mesmo capitulo
                    try:
                        supa_delete("historico", "chapter_id", body["chapter_id"])
                    except: pass
                    supa_post("historico", {
                        "manga_id":     body["manga_id"],
                        "manga_title":  body["manga_title"],
                        "manga_cover":  body.get("manga_cover",""),
                        "manga_source": body.get("manga_source",""),
                        "chapter_id":   body["chapter_id"],
                        "chapter_num":  body.get("chapter_num",""),
                        "manga_data":   json.dumps(body.get("manga_data",{}))
                    })
                    self.send_json({"ok": True})
                except Exception as e:
                    self.send_json({"error": str(e)}, 500)

            elif path == "/api/favoritos":
                try:
                    dados = supa_get("favoritos", {"order": "salvo_em.desc"})
                    self.send_json({"favoritos": dados})
                except Exception as e:
                    self.send_json({"favoritos": [], "error": str(e)})

            elif path == "/api/favoritos/salvar":
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(length))
                    supa_upsert("favoritos", {
                        "manga_id":     body["manga_id"],
                        "manga_title":  body["manga_title"],
                        "manga_cover":  body.get("manga_cover",""),
                        "manga_source": body.get("manga_source",""),
                        "manga_data":   json.dumps(body.get("manga_data",{}))
                    }, "manga_id")
                    self.send_json({"ok": True})
                except Exception as e:
                    self.send_json({"error": str(e)}, 500)

            elif path == "/api/favoritos/remover":
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(length))
                    supa_delete("favoritos", "manga_id", body["manga_id"])
                    self.send_json({"ok": True})
                except Exception as e:
                    self.send_json({"error": str(e)}, 500)

            elif path == "/api/explore":
                # tipo: manga=japonês, manhwa=coreano, manhua=chinês, doujinshi, all
                tipo = g("type", "all")
                lang = g("lang", "pt-br")
                tags_raw = p.get("tags[]", [])
                tags = tags_raw if tags_raw else None
                offset = int(g("offset", "0"))

                lang_map = {
                    "manga":     ["ja", "ja-ro"],
                    "manhwa":    ["ko", "ko-ro"],
                    "manhua":    ["zh", "zh-hk", "zh-ro"],
                    "doujinshi": None,
                }

                params = {
                    "limit": 24,
                    "offset": offset,
                    "includes[]": ["cover_art"],
                    "order[followedCount]": "desc",
                    "contentRating[]": ["safe", "suggestive", "erotica"],
                    "availableTranslatedLanguage[]": [lang, "pt", "en"],
                    "hasAvailableChapters": "true",
                }

                if tipo in lang_map and lang_map[tipo]:
                    params["originalLanguage[]"] = lang_map[tipo]
                elif tipo == "doujinshi":
                    params["publicationDemographic[]"] = ["doujinshi"]

                if tags:
                    tag_ids = [MDEX_TAGS[t] for t in tags if t in MDEX_TAGS]
                    if tag_ids:
                        params["includedTags[]"] = tag_ids

                data = mdex_get("/manga", params)
                results = []
                for m in data.get("data", []):
                    mid = m["id"]
                    attrs = m["attributes"]
                    title_map = attrs.get("title", {})
                    name = (title_map.get("pt-br") or title_map.get("pt") or
                            title_map.get("en") or next(iter(title_map.values()), "?"))
                    desc_map = attrs.get("description", {})
                    desc = desc_map.get("pt-br") or desc_map.get("pt") or desc_map.get("en") or ""
                    cover = ""
                    for rel in m.get("relationships", []):
                        if rel["type"] == "cover_art":
                            fname = rel.get("attributes", {}).get("fileName", "")
                            if fname:
                                cover = f"{MDEX_UPLOADS}/covers/{mid}/{fname}.256.jpg"
                    orig_lang = attrs.get("originalLanguage", "")
                    tipo_label = {"ja":"Manga","ko":"Manhwa","zh":"Manhua","zh-hk":"Manhua"}.get(orig_lang, orig_lang.upper())
                    tags_list = [t["attributes"]["name"].get("en", "") for t in attrs.get("tags", [])]
                    results.append({
                        "id": mid, "source": "mangadex",
                        "title": name, "description": desc[:300],
                        "cover": cover, "status": attrs.get("status", ""),
                        "tags": tags_list[:5], "score": None,
                        "external": None, "tipo": tipo_label,
                        "originalLanguage": orig_lang
                    })
                self.send_json({"results": results, "total": data.get("total", 0), "offset": offset})

            else:
                self.send_response(404)
                self.end_headers()

        except Exception as e:
            self.send_json({"error": str(e)}, 500)

if __name__ == "__main__":
    print(f"✅ MangaRX backend rodando na porta {PORT}")
    HTTPServer(("", PORT), Handler).serve_forever()
