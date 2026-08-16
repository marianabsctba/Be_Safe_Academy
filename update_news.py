#!/usr/bin/env python3
import datetime as dt
import email.utils
import html
import json
import os
import re
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
import time
from pathlib import Path

FEEDS = [
    ("BleepingComputer", "https://www.bleepingcomputer.com/feed/"),
    ("The Hacker News", "https://feeds.feedburner.com/TheHackersNews"),
    ("KrebsOnSecurity", "https://krebsonsecurity.com/feed/"),
    ("SecurityWeek", "https://feeds.feedburner.com/securityweek"),
    ("Dark Reading", "https://www.darkreading.com/rss.xml"),
    ("Microsoft Security", "https://www.microsoft.com/en-us/security/blog/feed/"),
    ("Cisco Talos", "https://blog.talosintelligence.com/rss/"),
    ("Google Security", "https://security.googleblog.com/feeds/posts/default"),
    ("Cloudflare Security", "https://blog.cloudflare.com/tag/security/rss/"),
    ("Fontes selecionadas", "https://news.google.com/rss/search?q=cybersecurity+(site%3Ableepingcomputer.com+OR+site%3Athehackernews.com+OR+site%3Akrebsonsecurity.com+OR+site%3Asecurityweek.com+OR+site%3Adarkreading.com)&hl=en-US&gl=US&ceid=US%3Aen"),
]
UA = "BeSafeAcademy-News/1.0 (+https://marianabsctba.github.io/Be_Safe_Academy/)"
OUT = Path("data/news.json")
CYBER_TERMS = ("security", "cyber", "vulnerability", "cve-", "malware", "ransomware", "breach", "attack", "exploit", "phishing", "botnet", "threat", "zero-day", "privacy", "authentication", "password", "infosec", "patch", "backdoor")

def text(node, names):
    for child in node.iter():
        if child.tag.split("}")[-1].lower() in names and child.text:
            return html.unescape(re.sub(r"<[^>]+>", " ", child.text)).strip()
    return ""

def link(node):
    for child in node.iter():
        if child.tag.split("}")[-1].lower() == "link":
            value = child.attrib.get("href") or (child.text or "")
            if value.startswith("http"):
                return value.strip()
    return ""

def image(node):
    for child in node.iter():
        tag = child.tag.split("}")[-1].lower()
        if tag in ("content", "thumbnail", "enclosure"):
            url = child.attrib.get("url", "")
            kind = child.attrib.get("type", "")
            if url.startswith("http") and (tag != "enclosure" or "image" in kind):
                return url
    raw = ET.tostring(node, encoding="unicode")
    match = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)', raw, re.I)
    return html.unescape(match.group(1)) if match else ""

def iso_date(raw):
    if not raw:
        return dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except Exception:
        try:
            return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(dt.timezone.utc).isoformat()
        except Exception:
            return dt.datetime.now(dt.timezone.utc).isoformat()

def fetch_feed(source, url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36", "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml,*/*", "Accept-Language": "en-US,en;q=0.9", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=25) as response:
        root = ET.fromstring(response.read())
    nodes = [n for n in root.iter() if n.tag.split("}")[-1].lower() in ("item", "entry")]
    rows = []
    for node in nodes[:12]:
        title = text(node, {"title"})
        url = link(node)
        if title and url:
            item_source = text(node, {"source"}) or source
            rows.append({"source": item_source, "original_title": title[:300], "original_summary": text(node, {"description", "summary", "content"})[:700], "url": url, "published": iso_date(text(node, {"pubdate", "published", "updated", "date"})), "image": image(node)})
    return rows

def fetch_cisa_fallback():
    url = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.load(response)
    rows = []
    for item in data.get("vulnerabilities", [])[-20:]:
        cve = item.get("cveID", "Vulnerabilidade")
        vendor = item.get("vendorProject", "")
        product = item.get("product", "")
        rows.append({"source": "CISA KEV", "original_title": f"{cve}: {vendor} {product}".strip(), "original_summary": item.get("shortDescription", "")[:700], "url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog", "published": iso_date(item.get("dateAdded", "")), "image": ""})
    return rows

def translate_batch(items, token):
    prompt = """Você é editor técnico de cibersegurança. Analise os itens recebidos e devolva SOMENTE JSON válido, sem markdown, no formato {\"items\":[{\"index\":0,\"keep\":true,\"title\":\"...\",\"summary\":\"...\",\"category\":\"...\"}]}. Mantenha apenas conteúdo estritamente ligado a segurança cibernética, vulnerabilidades, malware, ataques, defesa, privacidade técnica, segurança de IA/cloud, threat intelligence ou incidentes. Exclua tecnologia genérica, negócios, política sem impacto cyber, publieditorial e opinião vazia. Traduza o título para português brasileiro sem sensacionalismo. Crie resumo factual de uma frase, no máximo 240 caracteres, apenas com fatos presentes no texto fornecido. Categorias permitidas: AMEAÇAS, VULNERABILIDADES, INCIDENTES, DEFESA, CLOUD & IA, PRIVACIDADE. Não invente CVEs, vítimas ou impactos."""
    body = json.dumps({"model": os.getenv("NEWS_MODEL", "openai/gpt-4.1"), "temperature": 0.1, "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps([{"index": i, "source": x["source"], "title": x["original_title"], "description": x["original_summary"]} for i, x in enumerate(items)], ensure_ascii=False)}]}).encode()
    req = urllib.request.Request("https://models.github.ai/inference/chat/completions", data=body, method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/vnd.github+json"})
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.load(response)
            content = result["choices"][0]["message"]["content"].strip()
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I)
            return json.loads(content)["items"]
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", "replace")[:1000]
            last_error = RuntimeError(f"GitHub Models HTTP {exc.code}: {details}")
            if exc.code not in (429, 500, 502, 503, 504):
                break
        except Exception as exc:
            last_error = exc
        time.sleep(3 * (attempt + 1))
    raise last_error or RuntimeError("Falha desconhecida no GitHub Models")

def local_category(value):
    value = value.lower()
    if any(x in value for x in ("cve-", "vulnerability", "zero-day", "exploit", "patch")):
        return "VULNERABILIDADES"
    if any(x in value for x in ("ransomware", "malware", "phishing", "botnet", "threat")):
        return "AMEAÇAS"
    if any(x in value for x in ("breach", "incident", "leak", "stolen", "attack")):
        return "INCIDENTES"
    if any(x in value for x in ("cloud", " ai ", "artificial intelligence", "llm")):
        return "CLOUD & IA"
    if any(x in value for x in ("privacy", "tracking", "surveillance")):
        return "PRIVACIDADE"
    return "DEFESA"

def google_translate(value):
    value = re.sub(r"\s+", " ", value or "").strip()
    if not value:
        return ""
    query = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": "pt", "dt": "t", "q": value[:1200]})
    req = urllib.request.Request("https://translate.googleapis.com/translate_a/single?" + query, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as response:
        data = json.load(response)
    return "".join(part[0] for part in data[0] if part and part[0]).strip()

def fallback_items(items):
    selected = [x for x in items if any(term in (x["original_title"] + " " + x["original_summary"]).lower() for term in CYBER_TERMS)]
    if not selected:
        selected = items
    rows = []
    for source in selected[:18]:
        combined = source["original_title"] + " " + source["original_summary"]
        try:
            title = google_translate(source["original_title"])
        except Exception as exc:
            print(f"Aviso: tradução alternativa do título falhou: {exc}")
            title = source["original_title"]
        try:
            summary = google_translate(source["original_summary"][:500]) if source["original_summary"] else ""
        except Exception as exc:
            print(f"Aviso: tradução alternativa do resumo falhou: {exc}")
            summary = "Notícia de cibersegurança publicada pela fonte original. Acesse o link para consultar os detalhes técnicos."
        rows.append({"title": title[:220], "summary": summary[:260], "category": local_category(combined), "source": source["source"], "url": source["url"], "published": source["published"], "image": source["image"]})
    return rows

def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN ausente")
    found = []
    for source, url in FEEDS:
        try:
            found.extend(fetch_feed(source, url))
        except Exception as exc:
            print(f"Aviso: {source}: {exc}")
    if not found:
        print("Feeds indisponíveis; usando catálogo oficial CISA KEV como contingência")
        try:
            found.extend(fetch_cisa_fallback())
        except Exception as exc:
            raise SystemExit(f"Nenhuma fonte pôde ser consultada: {exc}")
    print(f"Coletados {len(found)} itens antes da triagem")
    unique, seen = [], set()
    for item in sorted(found, key=lambda x: x["published"], reverse=True):
        key = re.sub(r"\W+", "", item["original_title"].lower())[:90]
        if key not in seen:
            seen.add(key); unique.append(item)
    output = []
    for start in range(0, min(len(unique), 60), 10):
        batch = unique[start:start+10]
        try:
            decisions = translate_batch(batch, token)
        except Exception as exc:
            print(f"Aviso: tradução do lote falhou: {exc}"); continue
        for decision in decisions:
            idx = decision.get("index")
            if decision.get("keep") and isinstance(idx, int) and 0 <= idx < len(batch):
                source = batch[idx]
                output.append({"title": decision.get("title", source["original_title"])[:220], "summary": decision.get("summary", "")[:260], "category": decision.get("category", "DEFESA"), "source": source["source"], "url": source["url"], "published": source["published"], "image": source["image"]})
    output = sorted(output, key=lambda x: x["published"], reverse=True)[:36]
    if not output:
        print("GitHub Models indisponível; ativando triagem e tradução alternativas")
        output = fallback_items(unique)
    if not output:
        raise SystemExit("Nenhuma notícia encontrada nas fontes consultadas")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"updated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "items": output}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(output)} notícias publicadas")

if __name__ == "__main__":
    main()
