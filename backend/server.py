#!/usr/bin/env python3
"""
MangaNexus Backend — Render + Supabase
Auth completa: JWT, hash de senha, multi-usuário, admin, progresso por usuário
"""

import json
import urllib.request
import urllib.parse
import os
import threading
import time
import hashlib
import hmac
import secrets
import jwt  # PyJWT
from http.server import HTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor

PORT     = int(os.environ.get("PORT", 8765))
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))  # defina no Render como env var
JWT_EXPIRE  = 60 * 60 * 24 * 30  # 30 dias

HEADERS = {"User-Agent": "MangaNexus/2.0", "Accept": "application/json"}

# ─── CACHE EM MEMÓRIA ──────────────────────────────────────────────────────────

class Cache:
    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            entry = self._data.get(key)
            if entry and time.time() < entry["expires"]:
                return entry["value"]
            return None

    def set(self, key, value, ttl=600):
        with self._lock:
            self._data[key] = {"value": value, "expires": time.time() + ttl}

    def delete_expired(self):
        with self._lock:
            now = time.time()
            self._data = {k: v for k, v in self._data.items() if v["expires"] > now}

cache = Cache()

def _cache_cleaner():
    while True:
        time.sleep(600)
        cache.delete_expired()

threading.Thread(target=_cache_cleaner, daemon=True).start()

# ─── SUPABASE ──────────────────────────────────────────────────────────────────

SUPA_URL = os.environ.get("SUPABASE_URL", "https://txfklnxsuzdawuhbxaov.supabase.co")
SUPA_ANON_KEY = os.environ.get("SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR4ZmtsbnhzdXpkYXd1aGJ4YW92Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE4NzM3OTksImV4cCI6MjA4NzQ0OTc5OX0.0vQ0DGm1h7GVUMBZKqUtfqsJS165Ed2_JvYxuVQyEeA")

# Service role key é necessária para bypassar RLS e gerenciar usuários
# Defina SUPABASE_SERVICE_KEY no Render. Se não definida, usa anon (sem RLS bypass).
SUPA_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", SUPA_ANON_KEY)

def _supa_headers(use_service=False):
    key = SUPA_SERVICE_KEY if use_service else SUPA_ANON_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def supa_get(table, params=None, use_service=False):
    url = f"{SUPA_URL}/rest/v1/{table}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_supa_headers(use_service))
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def supa_post(table, data, use_service=False):
    url = f"{SUPA_URL}/rest/v1/{table}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=_supa_headers(use_service), method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def supa_patch(table, match_col, match_val, data, use_service=False):
    url = f"{SUPA_URL}/rest/v1/{table}?{match_col}=eq.{urllib.parse.quote(str(match_val))}"
    headers = dict(_supa_headers(use_service))
    headers["Prefer"] = "return=representation"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def supa_delete(table, match_col, match_val, use_service=False):
    url = f"{SUPA_URL}/rest/v1/{table}?{match_col}=eq.{urllib.parse.quote(str(match_val))}"
    req = urllib.request.Request(url, headers=_supa_headers(use_service), method="DELETE")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status

def supa_upsert(table, data, on_conflict, use_service=False):
    url = f"{SUPA_URL}/rest/v1/{table}"
    headers = dict(_supa_headers(use_service))
    headers["Prefer"] = f"resolution=merge-duplicates,return=representation"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def supa_rpc(func, params, use_service=False):
    url = f"{SUPA_URL}/rest/v1/rpc/{func}"
    body = json.dumps(params).encode()
    req = urllib.request.Request(url, data=body, headers=_supa_headers(use_service), method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def fetch(url, extra_headers=None):
    headers = dict(HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

# ─── AUTH HELPERS ──────────────────────────────────────────────────────────────

def hash_senha(senha):
    """SHA-256 com salt fixo por senha via PBKDF2 (stdlib pura)."""
    return hashlib.pbkdf2_hmac("sha256", senha.encode(), b"manganexus_salt_v1", 200_000).hex()

def gerar_token(user_id, username, role):
    payload = {
        "user_id":  str(user_id),
        "username": username,
        "role":     role,
        "exp":      int(time.time()) + JWT_EXPIRE,
        "iat":      int(time.time()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def validar_token(token_str):
    """Retorna payload dict ou None."""
    try:
        return jwt.decode(token_str, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return None

def extrair_token(headers_dict):
    """Extrai Bearer token do header Authorization."""
    auth = headers_dict.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None

# ─── MANGADEX ─────────────────────────────────────────────────────────────────

MDEX        = "https://api.mangadex.org"
MDEX_UPLOADS = "https://uploads.mangadex.org"

def mdex_get(path, params=None):
    url = MDEX + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    return fetch(url)

MDEX_TAGS = {
    "action":"391b0423-d847-456f-aff0-8b0cfc03066b","adventure":"87cc87cd-a395-47af-b27a-93258283bbc6",
    "comedy":"4d32cc48-9f00-4cca-9b5a-a839f0764984","drama":"b9af3a63-f058-46de-a9a0-e0c13906197a",
    "fantasy":"cdc58593-87dd-415e-bbc0-2ec27bf404cc","horror":"cdad7e68-1419-41dd-bdce-27753074a640",
    "mystery":"ee968100-4191-4968-93d3-f82d72be7e46","romance":"423e2eae-a7a2-4a8b-ac03-a8351462d71d",
    "sci-fi":"256c8bd9-4904-4360-bf4f-508a76d67183","slice-of-life":"e5301a23-ebd9-49dd-a0cb-2add944c7fe9",
    "sports":"69964a64-2f90-4d33-beeb-f3ed2875eb4c","supernatural":"eabc5b4c-6aff-42f3-b657-3e90cbd00b75",
    "psychological":"3b60b75c-a2d7-4860-ab56-05f391bb889c","historical":"33771934-028e-4cb3-8744-691e866a923e",
    "mecha":"50880a9d-5440-4732-9afb-8f457127e836","isekai":"ace04997-f6bd-436e-b261-779182193d3d",
    "martial-arts":"799c202e-7daa-44eb-9cf7-8a3c0441531e","music":"f8f62932-27da-4fe4-8ee1-6779a8c5edba",
    "school-life":"caaa44eb-cd40-4177-b930-79d3ef2afe87","harem":"aafb99c1-7f60-43fa-b75f-fc9502ce29c7",
}

def _mdex_parse_manga(m):
    mid   = m["id"]
    attrs = m["attributes"]
    title_map = attrs.get("title", {})
    name = (title_map.get("pt-br") or title_map.get("pt") or
            title_map.get("en")    or next(iter(title_map.values()), "Sem título"))
    desc_map = attrs.get("description", {})
    desc = desc_map.get("pt-br") or desc_map.get("pt") or desc_map.get("en") or ""
    cover = ""
    for rel in m.get("relationships", []):
        if rel["type"] == "cover_art":
            fname = rel.get("attributes", {}).get("fileName", "")
            if fname:
                cover = f"{MDEX_UPLOADS}/covers/{mid}/{fname}.256.jpg"
    orig_lang = attrs.get("originalLanguage", "")
    tipo_map  = {"ja":"Manga","ko":"Manhwa","zh":"Manhua","zh-hk":"Manhua"}
    tags_list = [t["attributes"]["name"].get("en","") for t in attrs.get("tags",[])]
    return {
        "id": mid, "source": "mangadex",
        "title": name, "description": desc[:400],
        "cover": cover, "status": attrs.get("status",""),
        "tags": tags_list[:6], "score": None, "external": None,
        "tipo": tipo_map.get(orig_lang,""), "originalLanguage": orig_lang
    }

def mdex_search(q, lang, tags=None):
    ck = f"mdex_search:{q}:{lang}:{sorted(tags or [])}"
    c  = cache.get(ck)
    if c is not None: return c
    params = {
        "title": q, "limit": 15,
        "availableTranslatedLanguage[]": [lang,"pt","en"],
        "includes[]": ["cover_art"], "order[relevance]": "desc",
        "contentRating[]": ["safe","suggestive","erotica"]
    }
    if tags:
        tag_ids = [MDEX_TAGS[t] for t in tags if t in MDEX_TAGS]
        if tag_ids: params["includedTags[]"] = tag_ids
    try:
        data    = mdex_get("/manga", params)
        results = [_mdex_parse_manga(m) for m in data.get("data",[])]
        if results: cache.set(ck, results, 600)
        return results
    except Exception as e:
        print(f"MangaDex search erro: {e}"); return []

def mdex_chapters(mid, lang):
    ck = f"mdex_chapters:{mid}:{lang}"
    c  = cache.get(ck)
    if c is not None: return c[0], c[1]
    data = mdex_get(f"/manga/{mid}/feed", {
        "translatedLanguage[]": [lang,"pt","en"],
        "order[chapter]": "asc", "limit": 200, "includes[]": ["scanlation_group"]
    })
    chapters = []
    for c2 in data.get("data",[]):
        attrs = c2["attributes"]
        chapters.append({"id":c2["id"],"source":"mangadex","chapter":attrs.get("chapter") or "?",
            "volume":attrs.get("volume") or "","title":attrs.get("title") or "",
            "lang":attrs.get("translatedLanguage",""),"pages":attrs.get("pages",0)})
    total = data.get("total",0)
    if chapters: cache.set(ck, (chapters,total), 1800)
    return chapters, total

def mdex_pages(cid):
    # NÃO cacheia: baseUrl do MangaDex expira em ~15min
    data  = fetch(f"{MDEX}/at-home/server/{cid}")
    base  = data.get("baseUrl","")
    ch    = data.get("chapter",{})
    hash_ = ch.get("hash","")
    imgs  = ch.get("data",[])
    return [f"{base}/data/{hash_}/{img}" for img in imgs]

# ─── MANGAZORD ────────────────────────────────────────────────────────────────

MZORD = "https://mangazord.com/api"
MZORD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://mangazord.com", "Accept": "application/json",
    "Origin": "https://mangazord.com"
}

def mzord_get(path, params=None):
    url = MZORD + path
    if params: url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers=MZORD_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def mzord_search(q):
    ck = f"mzord_search:{q}"
    c  = cache.get(ck)
    if c is not None: return c
    try:
        data    = mzord_get("/search", {"title": q, "limit": 15, "offset": 0})
        results = []
        for m in data.get("data",[]):
            mid = m["id"]; attrs = m.get("attributes",{})
            title_map = attrs.get("title",{})
            name = (title_map.get("pt-br") or title_map.get("pt") or
                    title_map.get("en")    or next(iter(title_map.values()),"?"))
            desc_map = attrs.get("description",{})
            desc = desc_map.get("pt-br") or desc_map.get("pt") or desc_map.get("en") or ""
            cover = ""
            for rel in m.get("relationships",[]):
                if rel.get("type") == "cover_art":
                    fname = rel.get("attributes",{}).get("fileName","")
                    if fname: cover = f"https://mangazord.com/api/proxy/cover/{mid}/{fname}"
            tags = []
            for t in attrs.get("tags",[]):
                n     = t.get("attributes",{}).get("name",{})
                tag_n = n.get("pt-br") or n.get("en","")
                if tag_n: tags.append(tag_n)
            orig_lang = attrs.get("originalLanguage","")
            tipo_map  = {"ja":"Manga","ko":"Manhwa","zh":"Manhua","zh-hk":"Manhua"}
            results.append({"id":mid,"source":"mangazord","title":name,"description":desc[:400],
                "cover":cover,"status":attrs.get("status",""),"tags":tags[:6],"score":None,
                "external":None,"tipo":tipo_map.get(orig_lang,""),"originalLanguage":orig_lang,
                "availableLangs":attrs.get("availableTranslatedLanguages",[])})
        if results: cache.set(ck, results, 600)
        return results
    except Exception as e:
        print(f"MangaZord search erro: {e}"); return []

def mzord_chapters(mid, lang):
    ck = f"mzord_chapters:{mid}:{lang}"
    c  = cache.get(ck)
    if c is not None: return c[0], c[1]
    try:
        lang_param = lang if lang in ("pt-br","pt","en") else "pt-br"
        data = mzord_get(f"/manga/{mid}/all-chapters", {"translatedLanguage":lang_param,"order":"asc"})
        chapters = []
        for c2 in data.get("data",[]):
            attrs = c2.get("attributes",{})
            chapters.append({"id":c2["id"],"source":"mangazord","chapter":attrs.get("chapter") or "?",
                "volume":attrs.get("volume") or "","title":attrs.get("title") or "",
                "lang":attrs.get("translatedLanguage","pt-br"),"pages":attrs.get("pages",0)})
        total = data.get("total", len(chapters))
        if chapters: cache.set(ck, (chapters,total), 1800)
        return chapters, total
    except Exception as e:
        print(f"MangaZord chapters erro: {e}"); return [], 0

def mzord_pages(cid):
    ck = f"mzord_pages:{cid}"
    c  = cache.get(ck)
    if c is not None: return c
    try:
        data      = mzord_get(f"/chapter/{cid}")
        hash_ = ""; imgs = []
        pages_data = data.get("pages",{})
        if pages_data and isinstance(pages_data, dict):
            ch    = pages_data.get("chapter",{}); hash_ = ch.get("hash",""); imgs = ch.get("data",[])
        if not imgs:
            ch = data.get("chapter",{})
            if isinstance(ch, dict): hash_ = ch.get("hash",""); imgs = ch.get("data",[])
        if imgs and hash_:
            pages = [f"https://mangazord.com/api/proxy/page/{cid}/{hash_}/{img}" for img in imgs]
            cache.set(ck, pages, 3600)
            return pages
        return []
    except Exception as e:
        print(f"MangaZord pages erro {cid}: {e}"); return []

# ─── COMICK ───────────────────────────────────────────────────────────────────

COMICK = "https://api.comick.fun"

def comick_search(q, lang, tags=None):
    ck = f"comick_search:{q}:{lang}"
    c  = cache.get(ck)
    if c is not None: return c
    lang_code = "pt" if lang in ("pt-br","pt") else "en"
    url = f"{COMICK}/v1.0/search?q={urllib.parse.quote(q)}&limit=15&lang={lang_code}&t=true"
    if tags: url += "&genres=" + ",".join(tags)
    try:
        data    = fetch(url, {"Referer":"https://comick.fun"})
        results = []
        for m in (data if isinstance(data,list) else []):
            mid  = m.get("hid") or m.get("id",""); slug = m.get("slug","")
            title = m.get("title") or slug
            desc  = m.get("desc") or m.get("description") or ""
            md_covers = m.get("md_covers",[]); cover = ""
            if md_covers:
                b2key = md_covers[0].get("b2key","")
                if b2key: cover = f"https://meo.comick.pictures/{b2key}"
            tags_list  = [g.get("name","") for g in m.get("genres",[])]
            status_map = {1:"ongoing",2:"completed",3:"cancelled",4:"hiatus"}
            status     = status_map.get(m.get("status"), str(m.get("status","")))
            results.append({"id":mid,"source":"comick","slug":slug,"title":title,
                "description":str(desc)[:400],"cover":cover,"status":status,
                "tags":tags_list[:6],"score":m.get("rating"),"external":None})
        if results: cache.set(ck, results, 600)
        return results
    except: return []

def comick_chapters(hid, slug, lang):
    ck = f"comick_chapters:{hid}:{lang}"
    c  = cache.get(ck)
    if c is not None: return c[0], c[1]
    lang_code = "pt" if lang in ("pt-br","pt") else "en"
    url = f"{COMICK}/comic/{hid}/chapters?lang={lang_code}&limit=200"
    try:
        data     = fetch(url, {"Referer":"https://comick.fun"})
        chapters = []
        for c2 in data.get("chapters",[]):
            chapters.append({"id":c2.get("hid",""),"source":"comick",
                "chapter":str(c2.get("chap") or "?"),"volume":str(c2.get("vol") or ""),
                "title":c2.get("title") or "","lang":c2.get("lang",""),"pages":c2.get("images_count",0)})
        result = (chapters, len(chapters))
        if chapters: cache.set(ck, result, 1800)
        return result
    except: return [], 0

def comick_pages(hid):
    ck = f"comick_pages:{hid}"
    c  = cache.get(ck)
    if c is not None: return c
    url = f"{COMICK}/chapter/{hid}?tachiyomi=true"
    try:
        data    = fetch(url, {"Referer":"https://comick.fun"})
        chapter = data.get("chapter",{}); imgs = chapter.get("md_images",[]) or data.get("images",[])
        pages   = []
        for img in imgs:
            b2key = img.get("b2key") or img.get("url","")
            if b2key:
                pages.append(b2key if b2key.startswith("http") else f"https://meo.comick.pictures/{b2key}")
        if pages: cache.set(ck, pages, 3600)
        return pages
    except: return []

# ─── BUSCA COM PRIORIDADE ──────────────────────────────────────────────────────

def priority_search(q, lang, tags=None):
    mzord_result = []; mdex_result = []; comick_result = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        fut_mzord  = executor.submit(mzord_search, q)
        fut_mdex   = executor.submit(mdex_search,  q, lang, tags)
        fut_comick = executor.submit(comick_search, q, lang, tags)
        try: mzord_result  = fut_mzord.result(timeout=10)
        except Exception as e: print(f"MangaZord timeout: {e}")
        try: mdex_result   = fut_mdex.result(timeout=10)
        except Exception as e: print(f"MangaDex timeout: {e}")
        try: comick_result = fut_comick.result(timeout=10)
        except Exception as e: print(f"ComicK timeout: {e}")
    if mzord_result:
        print(f"Busca '{q}': MangaZord ({len(mzord_result)})")
        return mzord_result
    print(f"Busca '{q}': MangaDex+ComicK")
    results = mdex_result + comick_result
    seen = set(); unique = []
    for r in results:
        key = r["title"].lower().strip()[:30]
        if key not in seen:
            seen.add(key); unique.append(r)
    return unique

# ─── JIKAN ────────────────────────────────────────────────────────────────────

JIKAN = "https://api.jikan.moe/v4"

def jikan_score(title):
    ck = f"jikan:{title}"
    c  = cache.get(ck)
    if c is not None: return c
    try:
        time.sleep(0.4)
        data  = fetch(f"{JIKAN}/manga?q={urllib.parse.quote(title)}&limit=1")
        items = data.get("data",[])
        if items:
            score = items[0].get("score")
            cache.set(ck, score, 86400)
            return score
    except: pass
    return None

# ─── LANÇAMENTOS DIÁRIOS ──────────────────────────────────────────────────────

def get_recent_releases(lang="pt-br", limit=20):
    ck = f"releases:{lang}"
    c  = cache.get(ck)
    if c is not None: return c
    try:
        params = {
            "translatedLanguage[]": [lang,"pt","en"],
            "order[readableAt]": "desc", "limit": limit,
            "includes[]": ["manga","scanlation_group"],
            "contentRating[]": ["safe","suggestive","erotica"]
        }
        data     = mdex_get("/chapter", params)
        releases = []; seen_manga = set()
        for c2 in data.get("data",[]):
            attrs     = c2["attributes"]
            manga_rel = next((r for r in c2.get("relationships",[]) if r["type"]=="manga"), None)
            if not manga_rel: continue
            manga_id = manga_rel["id"]
            if manga_id in seen_manga: continue
            seen_manga.add(manga_id)
            manga_attrs = manga_rel.get("attributes") or {}
            title_map   = manga_attrs.get("title",{}) if manga_attrs else {}
            manga_title = ""
            if title_map:
                manga_title = (title_map.get("pt-br") or title_map.get("pt") or
                               title_map.get("en") or next(iter(title_map.values()),""))
            releases.append({
                "chapter_id": c2["id"], "chapter_num": attrs.get("chapter") or "?",
                "chapter_title": attrs.get("title") or "", "manga_id": manga_id,
                "manga_title": manga_title or manga_id[:8]+"...", "cover": "",
                "lang": attrs.get("translatedLanguage",""),
                "readable_at": attrs.get("readableAt",""), "source": "mangadex"
            })
        if releases:
            manga_ids = list({r["manga_id"] for r in releases})[:20]
            try:
                manga_data = mdex_get("/manga",{"ids[]":manga_ids,"includes[]":["cover_art"],"limit":20})
                covers = {}; titles = {}
                for m in manga_data.get("data",[]):
                    mid = m["id"]
                    tm  = m["attributes"].get("title",{})
                    titles[mid] = (tm.get("pt-br") or tm.get("pt") or tm.get("en") or next(iter(tm.values()),""))
                    for rel in m.get("relationships",[]):
                        if rel["type"]=="cover_art":
                            fname = rel.get("attributes",{}).get("fileName","")
                            if fname: covers[mid] = f"{MDEX_UPLOADS}/covers/{mid}/{fname}.256.jpg"
                for r in releases:
                    mid = r["manga_id"]
                    r["cover"] = covers.get(mid,"")
                    if titles.get(mid): r["manga_title"] = titles[mid]
            except: pass
        cache.set(ck, releases, 900)
        return releases
    except Exception as e:
        print(f"Erro releases: {e}"); return []

# ─── POPULARES ────────────────────────────────────────────────────────────────

def get_popular(lang="pt-br", limit=12):
    ck = f"popular:{lang}"
    c  = cache.get(ck)
    if c is not None: return c
    try:
        params = {
            "limit": limit, "offset": 0, "includes[]": ["cover_art"],
            "order[followedCount]": "desc",
            "contentRating[]": ["safe","suggestive","erotica"],
            "availableTranslatedLanguage[]": [lang,"pt","en"],
            "hasAvailableChapters": "true",
        }
        data    = mdex_get("/manga", params)
        results = [_mdex_parse_manga(m) for m in data.get("data",[])]
        cache.set(ck, results, 3600)
        return results
    except Exception as e:
        print(f"Erro popular: {e}"); return []

# ─── HTTP HANDLER ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ── util ──────────────────────────────────────────────────────────────────

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
            with open(path,"rb") as f: data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404); self.end_headers()

    def get_token_payload(self):
        """Extrai e valida o JWT do request. Retorna payload ou None."""
        token = extrair_token(dict(self.headers))
        if not token: return None
        return validar_token(token)

    def require_auth(self):
        """Retorna payload se autenticado, envia 401 e retorna None se não."""
        payload = self.get_token_payload()
        if not payload:
            self.send_json({"error": "Não autenticado."}, 401)
        return payload

    def require_admin(self):
        """Retorna payload se admin, envia 403 e retorna None se não."""
        payload = self.require_auth()
        if payload and payload.get("role") != "admin":
            self.send_json({"error": "Acesso negado."}, 403)
            return None
        return payload

    # ── OPTIONS ───────────────────────────────────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    # ── POST ──────────────────────────────────────────────────────────────────

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length)) if length else {}

            # ── AUTH ──────────────────────────────────────────────────────────

            if path == "/api/auth/registro":
                username = (body.get("username","")).strip().lower()
                senha    = body.get("senha","")
                if len(username) < 3:
                    self.send_json({"error":"Username deve ter mínimo 3 caracteres."}, 400); return
                if len(senha) < 6:
                    self.send_json({"error":"Senha deve ter mínimo 6 caracteres."}, 400); return
                # Verifica se já existe
                try:
                    existing = supa_get("usuarios", {"username": f"eq.{username}"}, use_service=True)
                    if existing:
                        self.send_json({"error":"Username já está em uso."}, 409); return
                except Exception as e:
                    self.send_json({"error": f"Erro ao verificar usuário: {e}"}, 500); return
                # Define primeiro usuário como admin
                try:
                    total = supa_get("usuarios", {"select":"id","limit":"1"}, use_service=True)
                    role  = "admin" if not total else "user"
                except:
                    role = "user"
                # Cria usuário
                try:
                    novo = supa_post("usuarios", {
                        "username": username,
                        "senha_hash": hash_senha(senha),
                        "role": role,
                        "bloqueado": False
                    }, use_service=True)
                    u = novo[0] if isinstance(novo, list) else novo
                    token = gerar_token(u["id"], u["username"], u["role"])
                    self.send_json({"token": token, "username": u["username"],
                                    "role": u["role"], "user_id": u["id"]})
                except Exception as e:
                    self.send_json({"error": f"Erro ao criar usuário: {e}"}, 500)

            elif path == "/api/auth/login":
                username = (body.get("username","")).strip().lower()
                senha    = body.get("senha","")
                try:
                    rows = supa_get("usuarios", {"username": f"eq.{username}"}, use_service=True)
                except Exception as e:
                    self.send_json({"error": f"Erro de banco: {e}"}, 500); return
                if not rows:
                    self.send_json({"error": "Usuário não encontrado."}, 401); return
                u = rows[0]
                if u.get("bloqueado"):
                    self.send_json({"error": "Conta bloqueada. Entre em contato com o admin."}, 403); return
                if not hmac.compare_digest(u.get("senha_hash",""), hash_senha(senha)):
                    self.send_json({"error": "Senha incorreta."}, 401); return
                token = gerar_token(u["id"], u["username"], u["role"])
                self.send_json({"token": token, "username": u["username"],
                                "role": u["role"], "user_id": u["id"]})

            elif path == "/api/auth/logout":
                # JWT é stateless; o frontend descarta o token
                self.send_json({"ok": True})

            # ── PROGRESSO ─────────────────────────────────────────────────────

            elif path == "/api/progresso/salvar":
                user = self.require_auth()
                if not user: return
                uid = user["user_id"]
                supa_upsert("progresso", {
                    "user_id":          uid,
                    "manga_id":         body.get("manga_id",""),
                    "manga_title":      body.get("manga_title",""),
                    "manga_cover":      body.get("manga_cover",""),
                    "manga_source":     body.get("manga_source",""),
                    "manga_data":       body.get("manga_data",{}),
                    "last_chapter_id":  body.get("last_chapter_id",""),
                    "last_chapter_num": body.get("last_chapter_num",""),
                    "last_chapter_src": body.get("last_chapter_src",""),
                    "read_chapters":    body.get("read_chapters",{}),
                }, "user_id,manga_id", use_service=True)
                self.send_json({"ok": True})

            # ── FAVORITOS ─────────────────────────────────────────────────────

            elif path == "/api/favoritos/salvar":
                user = self.require_auth()
                if not user: return
                uid = user["user_id"]
                supa_upsert("favoritos", {
                    "user_id":      uid,
                    "manga_id":     body.get("manga_id",""),
                    "manga_title":  body.get("manga_title",""),
                    "manga_cover":  body.get("manga_cover",""),
                    "manga_source": body.get("manga_source",""),
                    "manga_data":   body.get("manga_data",{})
                }, "user_id,manga_id", use_service=True)
                self.send_json({"ok": True})

            elif path == "/api/favoritos/remover":
                user = self.require_auth()
                if not user: return
                uid      = user["user_id"]
                manga_id = body.get("manga_id","")
                url = (f"{SUPA_URL}/rest/v1/favoritos"
                       f"?user_id=eq.{urllib.parse.quote(str(uid))}"
                       f"&manga_id=eq.{urllib.parse.quote(str(manga_id))}")
                headers = dict(_supa_headers(use_service=True))
                req = urllib.request.Request(url, headers=headers, method="DELETE")
                urllib.request.urlopen(req, timeout=10).close()
                self.send_json({"ok": True})

            # ── HISTÓRICO ─────────────────────────────────────────────────────

            elif path == "/api/historico/salvar":
                user = self.require_auth()
                if not user: return
                uid = user["user_id"]
                # Remove entrada anterior para o mesmo capítulo deste usuário
                try:
                    url = (f"{SUPA_URL}/rest/v1/historico"
                           f"?user_id=eq.{urllib.parse.quote(str(uid))}"
                           f"&chapter_id=eq.{urllib.parse.quote(str(body.get('chapter_id','')))}") 
                    req = urllib.request.Request(url, headers=_supa_headers(True), method="DELETE")
                    urllib.request.urlopen(req, timeout=10).close()
                except: pass
                supa_post("historico", {
                    "user_id":      uid,
                    "manga_id":     body.get("manga_id",""),
                    "manga_title":  body.get("manga_title",""),
                    "manga_cover":  body.get("manga_cover",""),
                    "manga_source": body.get("manga_source",""),
                    "chapter_id":   body.get("chapter_id",""),
                    "chapter_num":  body.get("chapter_num",""),
                    "manga_data":   body.get("manga_data",{})
                }, use_service=True)
                self.send_json({"ok": True})

            # ── NOTIFICAÇÕES ──────────────────────────────────────────────────

            elif path == "/api/notif/salvar":
                user = self.require_auth()
                if not user: return
                uid  = user["user_id"]
                seen = body.get("seen", {})
                supa_upsert("notif_seen", {
                    "user_id": uid,
                    "seen":    seen
                }, "user_id", use_service=True)
                self.send_json({"ok": True})

            # ── ADMIN ─────────────────────────────────────────────────────────

            elif path == "/api/admin/usuario/bloquear":
                adm = self.require_admin()
                if not adm: return
                supa_patch("usuarios","id", body.get("user_id"),
                           {"bloqueado": body.get("bloqueado", True)}, use_service=True)
                self.send_json({"ok": True})

            elif path == "/api/admin/usuario/role":
                adm = self.require_admin()
                if not adm: return
                supa_patch("usuarios","id", body.get("user_id"),
                           {"role": body.get("role","user")}, use_service=True)
                self.send_json({"ok": True})

            elif path == "/api/admin/usuario/deletar":
                adm = self.require_admin()
                if not adm: return
                uid = body.get("user_id","")
                # Remove dados relacionados
                for table in ["historico","favoritos","progresso","notif_seen"]:
                    try: supa_delete(table, "user_id", uid, use_service=True)
                    except: pass
                supa_delete("usuarios","id", uid, use_service=True)
                self.send_json({"ok": True})

            else:
                self.send_response(404); self.end_headers()

        except Exception as e:
            print(f"POST error {path}: {e}")
            self.send_json({"error": str(e)}, 500)

    # ── GET ───────────────────────────────────────────────────────────────────

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path
        p      = urllib.parse.parse_qs(parsed.query)
        g      = lambda k, d="": p.get(k,[""])[0] or d

        try:
            if path in ("/","/index.html"):
                self.send_file(os.path.join(os.path.dirname(__file__),"index.html"),
                               "text/html; charset=utf-8")

            # ── AUTH ──────────────────────────────────────────────────────────

            elif path == "/api/auth/me":
                payload = self.get_token_payload()
                if payload:
                    self.send_json({"username": payload["username"],
                                    "role": payload["role"],
                                    "user_id": payload["user_id"]})
                else:
                    self.send_json({"error": "Não autenticado."}, 401)

            # ── ADMIN ─────────────────────────────────────────────────────────

            elif path == "/api/admin/usuarios":
                adm = self.require_admin()
                if not adm: return
                rows = supa_get("usuarios",
                    {"select":"id,username,role,bloqueado,criado_em","order":"criado_em.asc"},
                    use_service=True)
                self.send_json({"usuarios": rows})

            # ── PROGRESSO ─────────────────────────────────────────────────────

            elif path == "/api/progresso":
                user = self.require_auth()
                if not user: return
                uid  = user["user_id"]
                rows = supa_get("progresso",
                    {"user_id": f"eq.{uid}", "order":"atualizado_em.desc"},
                    use_service=True)
                self.send_json({"progresso": rows})

            # ── FAVORITOS ─────────────────────────────────────────────────────

            elif path == "/api/favoritos":
                user = self.require_auth()
                if not user: return
                uid  = user["user_id"]
                rows = supa_get("favoritos",
                    {"user_id": f"eq.{uid}", "order":"salvo_em.desc"},
                    use_service=True)
                self.send_json({"favoritos": rows})

            # ── HISTÓRICO ─────────────────────────────────────────────────────

            elif path == "/api/historico":
                user = self.require_auth()
                if not user: return
                uid  = user["user_id"]
                rows = supa_get("historico",
                    {"user_id": f"eq.{uid}", "order":"lido_em.desc","limit":"100"},
                    use_service=True)
                self.send_json({"historico": rows})

            # ── NOTIFICAÇÕES ──────────────────────────────────────────────────

            elif path == "/api/notif/seen":
                user = self.require_auth()
                if not user: return
                uid  = user["user_id"]
                rows = supa_get("notif_seen", {"user_id": f"eq.{uid}"}, use_service=True)
                seen = rows[0]["seen"] if rows else {}
                self.send_json({"seen": seen})

            # ── MANGA/CHAPTERS/PAGES ───────────────────────────────────────────

            elif path == "/api/search":
                q      = g("q"); lang = g("lang","pt-br"); source = g("source","all")
                tags_raw = p.get("tags[]",[]); tags = tags_raw if tags_raw else None
                if source == "mangazord":  results = mzord_search(q)
                elif source == "mangadex": results = mdex_search(q, lang, tags)
                elif source == "comick":   results = comick_search(q, lang, tags)
                else:                      results = priority_search(q, lang, tags)
                self.send_json({"results": results})

            elif path == "/api/chapters":
                mid    = g("id"); lang = g("lang","pt-br")
                source = g("source","mangadex"); slug = g("slug")
                if source == "comick":
                    chs, total = comick_chapters(mid, slug, lang)
                elif source == "mangazord":
                    chs, total = mzord_chapters(mid, lang)
                    if not chs: chs, total = mdex_chapters(mid, lang)
                else:
                    chs, total = mdex_chapters(mid, lang)
                self.send_json({"chapters": chs, "total": total})

            elif path == "/api/pages":
                cid    = g("id"); source = g("source","mangadex")
                if source == "comick":       pages = comick_pages(cid)
                elif source == "mangazord":  pages = mzord_pages(cid)
                else:                        pages = mdex_pages(cid)
                self.send_json({"pages": pages, "source_used": source})

            elif path == "/api/image":
                img_url = g("url")
                if not img_url or not img_url.startswith("https://"):
                    self.send_response(400); self.end_headers(); return
                try:
                    req = urllib.request.Request(img_url, headers={
                        "User-Agent":"MangaNexus/2.0","Referer":"https://mangadex.org"})
                    with urllib.request.urlopen(req, timeout=15) as r:
                        img_data = r.read(); ct = r.headers.get("Content-Type","image/jpeg")
                    self.send_response(200)
                    self.send_header("Content-Type", ct)
                    self.send_header("Access-Control-Allow-Origin","*")
                    self.send_header("Content-Length", len(img_data))
                    self.send_header("Cache-Control","public, max-age=86400")
                    self.end_headers()
                    self.wfile.write(img_data)
                except:
                    self.send_response(404); self.end_headers()

            elif path == "/api/score":
                title = g("title")
                cached_score = cache.get(f"jikan:{title}")
                if cached_score is not None:
                    self.send_json({"score": cached_score})
                else:
                    threading.Thread(target=lambda: jikan_score(title), daemon=True).start()
                    self.send_json({"score": None, "pending": True})

            elif path == "/api/releases":
                lang = g("lang","pt-br")
                self.send_json({"releases": get_recent_releases(lang)})

            elif path == "/api/popular":
                lang = g("lang","pt-br")
                self.send_json({"results": get_popular(lang)})

            elif path == "/api/explore":
                tipo   = g("type","all"); lang = g("lang","pt-br")
                tags_raw = p.get("tags[]",[]); tags = tags_raw if tags_raw else None
                offset = int(g("offset","0"))
                lang_map = {"manga":["ja","ja-ro"],"manhwa":["ko","ko-ro"],
                            "manhua":["zh","zh-hk","zh-ro"],"doujinshi":None}
                params2 = {
                    "limit":24,"offset":offset,"includes[]":["cover_art"],
                    "order[followedCount]":"desc",
                    "contentRating[]":["safe","suggestive","erotica"],
                    "availableTranslatedLanguage[]":[lang,"pt","en"],
                    "hasAvailableChapters":"true",
                }
                if tipo in lang_map and lang_map[tipo]: params2["originalLanguage[]"] = lang_map[tipo]
                elif tipo == "doujinshi": params2["publicationDemographic[]"] = ["doujinshi"]
                if tags:
                    tag_ids = [MDEX_TAGS[t] for t in tags if t in MDEX_TAGS]
                    if tag_ids: params2["includedTags[]"] = tag_ids
                ck = f"explore:{tipo}:{lang}:{offset}:{sorted(tags or [])}"
                cached_exp = cache.get(ck)
                if cached_exp: self.send_json(cached_exp); return
                data    = mdex_get("/manga", params2)
                results = [_mdex_parse_manga(m) for m in data.get("data",[])]
                resp    = {"results":results,"total":data.get("total",0),"offset":offset}
                cache.set(ck, resp, 1800)
                self.send_json(resp)

            elif path == "/api/cache/stats":
                with cache._lock: stats = {"entries": len(cache._data)}
                self.send_json(stats)

            elif path == "/api/debug/mzord":
                cid = g("id")
                if not cid: self.send_json({"error":"Informe ?id=<chapter_id>"})
                else:
                    try: raw = mzord_get(f"/chapter/{cid}"); self.send_json({"raw":raw})
                    except Exception as e: self.send_json({"error":str(e)})

            else:
                self.send_response(404); self.end_headers()

        except Exception as e:
            print(f"GET error {path}: {e}")
            self.send_json({"error": str(e)}, 500)


if __name__ == "__main__":
    print(f"✅ MangaNexus backend — porta {PORT}")
    print(f"   JWT_SECRET: {'[env]' if os.environ.get('JWT_SECRET') else '[gerado em memória — defina JWT_SECRET no Render]'}")
    print(f"   SERVICE_KEY: {'[env]' if os.environ.get('SUPABASE_SERVICE_KEY') else '[usando anon key — defina SUPABASE_SERVICE_KEY no Render]'}")
    HTTPServer(("", PORT), Handler).serve_forever()
