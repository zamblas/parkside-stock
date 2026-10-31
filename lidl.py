"""Acesso aos dados do lidl.pt: lojas, produtos Parkside e stock por loja."""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
STORES_FILE = HERE / "stores.json"

UA = {"User-Agent": "Mozilla/5.0 (parkside-stock)"}
SEARCH_URL = "https://www.lidl.pt/q/api/search"
STOCK_URL = "https://www.lidl.pt/p/api/storestock/PT/pt/{item}?storeids={ids}"
STORES_URL = "https://live.api.schwarz/odj/stores-api/v2/myapi/stores-frontend/stores"
# Chave do frontend do lidl.pt. Opcional: sem ela usa-se stores.json.
STORES_KEY = os.environ.get("LIDL_STORES_KEY", "")

STORES_TTL = 24 * 3600
SEARCH_TTL = 10 * 60
STOCK_TTL = 5 * 60

_cache = {}
_lock = threading.Lock()


def cached(key, ttl, fn):
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    val = fn()
    with _lock:
        _cache[key] = (time.time(), val)
    return val


def clear_cache():
    with _lock:
        _cache.clear()


def get_json(url, headers=None, tries=4):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or i == tries - 1:
                raise
            time.sleep(2 ** i)


# ---------- lojas ----------

def fetch_stores():
    items, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"limit": 250, "offset": offset, "country_code": "PT"})
        j = get_json(f"{STORES_URL}?{q}", {"x-apikey": STORES_KEY})
        items += j["items"]
        offset += 250
        if offset >= j["meta"]["total"]:
            break
    out = []
    for s in items:
        if s.get("objectType") != "STORE":
            continue
        a = s["address"]
        out.append({
            "id": str(int(s["objectNumber"][2:])),
            "name": s["storeName"],
            "street": " ".join(x for x in (a.get("streetName"), a.get("streetNumber")) if x),
            "city": a.get("city") or "",
            "zip": a.get("zip") or "",
            "lat": a.get("latitude"),
            "lng": a.get("longitude"),
        })
    out.sort(key=lambda s: (s["city"], s["name"]))
    return out


def load_stores():
    """API se houver chave (e grava stores.json); senão, ou se falhar, stores.json."""
    if STORES_KEY:
        try:
            s = fetch_stores()
            STORES_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
            return s
        except Exception as e:
            print(f"aviso: API de lojas falhou ({e}); a usar stores.json")
    return json.loads(STORES_FILE.read_text(encoding="utf-8"))


def stores():
    return cached("stores", STORES_TTL, load_stores)


# ---------- produtos ----------

BATTERY_RE = re.compile(r"\b(bateria|baterias|carregador|acumulador|power ?bank|ah)\b", re.I)
NO_BATTERY_RE = re.compile(r"sem bateria", re.I)


def classify(title):
    if NO_BATTERY_RE.search(title):
        return "tool"           # ferramenta "sem bateria" (compatível)
    if BATTERY_RE.search(title):
        return "battery"
    if re.search(r"\b\d{1,2} ?v\b", title, re.I):
        return "tool"
    return "other"


def badge_text(stock):
    for b in (stock or {}).get("badgeInfo", {}).get("badges", []):
        if b.get("text"):
            return b["text"]
    return ""


def product_from_grid(g):
    return {
        "id": str(g["productId"]),
        "title": g.get("fullTitle") or g.get("title") or "",
        "price": (g.get("price") or {}).get("price"),
        "image": g.get("image"),
        "url": "https://www.lidl.pt" + (g.get("canonicalUrl") or g.get("canonicalPath") or ""),
        "badge": badge_text(g.get("stockAvailability")),
        "start": g.get("storeStartDate"),
        "end": g.get("storeEndDate"),
        "kind": classify(g.get("fullTitle") or ""),
    }


def search(q):
    def run():
        params = {"q": q, "locale": "pt_PT", "assortment": "PT", "version": "2.1.0", "fetchsize": 200}
        j = get_json(f"{SEARCH_URL}?{urllib.parse.urlencode(params)}")
        out = []
        for it in j.get("items", []):
            g = (it.get("gridbox") or {}).get("data")
            if not g:
                continue
            brand = g.get("brand")
            brand = brand.get("name") if isinstance(brand, dict) else brand
            if "parkside" not in f"{brand} {g.get('fullTitle')}".lower():
                continue
            out.append(product_from_grid(g))
        return out
    return cached(f"search:{q}", SEARCH_TTL, run)


# ---------- variantes ----------
# O stock é por variante (número de artigo de 11 dígitos: ID + 001, 002, …), e o sufixo
# não é sempre 001. A pesquisa não o indica; a página do produto sim, no payload Nuxt.

def _nuxt_payload(html):
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    raw = json.loads(m.group(1))
    memo = {}

    def un(i):  # formato "devalue": listas/objectos referenciam índices do array
        if not isinstance(i, int) or i < 0:
            return None
        if i in memo:
            return memo[i]
        v = raw[i]
        if isinstance(v, list):
            if v and isinstance(v[0], str) and v[0] in ("Reactive", "ShallowReactive", "Ref", "ShallowRef"):
                memo[i] = un(v[1]) if len(v) > 1 else None
                return memo[i]
            r = memo[i] = []
            r.extend(un(x) for x in v)
            return r
        if isinstance(v, dict):
            r = memo[i] = {}
            for k, x in v.items():
                r[k] = un(x)
            return r
        return v
    return un(0)


def variants(p):
    """[(número de artigo, nome da variante ou None)]; na dúvida assume-se ID+001."""
    def run():
        try:
            req = urllib.request.Request(p["url"], headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                html = r.read().decode("utf-8", "replace")
            attrs = (_nuxt_payload(html)["data"].get(f"&erp{p['id']}") or {}).get("attributes") or {}
            labels = {o["key"]: o["value"] for a in attrs.get("attributes") or [] for o in a.get("options") or []}
            out = []
            for key, v in (attrs.get("attributesFlattened") or {}).items():
                names = [lab for k, lab in labels.items() if k in key] or [key.split("|")[-1]]
                for erp in v.get("erpNumbers") or []:
                    out.append((str(erp), " / ".join(names)))
            if out:
                return sorted(out)
        except Exception as e:
            print(f"aviso: variantes de {p['id']} não lidas ({e}); a usar 001")
        return [(f"{p['id']}001", None)]
    return cached(f"variants:{p['id']}", SEARCH_TTL, run)


def all_products():
    found = {}
    for q in ("parkside", "parkside bateria", "parkside carregador"):
        for p in search(q):
            found[p["id"]] = p
    with ThreadPoolExecutor(max_workers=2) as ex:
        vs = dict(zip(found, ex.map(variants, found.values())))
    out = []
    for pid, p in found.items():
        v = vs[pid]
        if len(v) == 1:
            out.append({**p, "erp": v[0][0]})
        else:  # várias variantes com stock próprio: uma entrada por variante
            for erp, label in v:
                title = f"{p['title']} · {label}" if label else f"{p['title']} ({erp[-3:]})"
                out.append({**p, "id": erp, "productId": pid, "erp": erp, "title": title})
    order = {"battery": 0, "tool": 1, "other": 2}
    return sorted(out, key=lambda p: (order[p["kind"]], p["title"]))


# ---------- stock ----------

def stock(erp):
    def run():
        ids = ",".join(s["id"] for s in stores())
        rows = get_json(STOCK_URL.format(item=erp, ids=ids))
        return {r["storeId"]: r["storeAvailabilityIndicator"] for r in rows}
    return cached(f"stock:{erp}", STOCK_TTL, run)


def _safe_stock(erp):
    try:
        return stock(erp)
    except Exception as e:  # produto retirado ou erro de rede
        return {"error": str(e)}


def build_data():
    """Tudo o que a página precisa, num só objecto."""
    products = all_products()
    with ThreadPoolExecutor(max_workers=2) as ex:
        st = dict(zip([p["id"] for p in products], ex.map(_safe_stock, [p["erp"] for p in products])))
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stores": stores(),
        "products": products,
        "stock": st,
    }
