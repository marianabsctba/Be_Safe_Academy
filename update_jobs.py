#!/usr/bin/env python3
import json, os, re, html, hashlib, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, unquote
import requests
from bs4 import BeautifulSoup

OUT = Path("data/jobs.json")
UA = {
    "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
    "Accept-Language":"pt-BR,pt;q=0.9,en;q=0.7",
}
TIMEOUT = 25
MAX_AGE_DAYS = 90

CYBER = [
 "cybersecurity","cyber security","cibersegurança","segurança da informação","information security",
 "soc","security analyst","analista de segurança","security engineer","appsec","application security",
 "pentest","pentester","red team","blue team","grc","iam","pam","cloud security","threat intelligence",
 "dfir","incident response","devsecops","vulnerability","vulnerabilidade","siem","soar","edr","xdr",
 "waf","firewall","dlp","zero trust","security operations","csirt","gestão de acessos","gestao de acessos",
 "ciberdefesa","cyber defense","segurança cloud","seguranca cloud","secure sdLC","sast","dast","sca"
]
NEG = ["security guard","segurança patrimonial","vigilante","porteiro","loss prevention","técnico de segurança do trabalho"]

TRACKS = [
 ("SOC / BLUE TEAM",["soc","siem","soar","edr","xdr","blue team","security operations","csirt","firewall","monitoramento","ciberdefesa"]),
 ("RED TEAM / PENTEST",["red team","pentest","pentester","offensive security","ethical hacker","burp"]),
 ("APPSEC",["appsec","application security","sast","dast","sca","owasp","secure code","security by design","secure sdlc"]),
 ("GRC",["grc","governance","governança","compliance","risk","riscos","iso 27001","lgpd","dlp","privacy"]),
 ("IAM / PAM",["iam","pam","identity","identidade","access management","gestão de acessos","gestao de acessos","privileged access","sailpoint"]),
 ("CTI",["threat intelligence","cti","osint","threat hunting","inteligência de ameaças"]),
 ("DFIR / IR",["dfir","forensic","forense","incident response","resposta a incidentes","csirt"]),
 ("CLOUD SECURITY",["cloud security","segurança cloud","seguranca cloud","aws security","azure security","gcp security","cnapp","cspm"]),
 ("DEVSECOPS",["devsecops","pipeline security","ci/cd security","container security","kubernetes security"]),
 ("IA SECURITY",["ai security","llm security","genai security","segurança de ia","security ai"]),
 ("VULNERABILITY",["vulnerability","vulnerabilidade","ctem","exposure management","gestão de vulnerabilidades"])
]

GUPY_BOARDS = [
 "netsecurity.gupy.io",
 "visioncybersecurity.gupy.io",
 "compass.gupy.io",
 "abcbrasil.gupy.io",
 "creditas.gupy.io",
 "cresolcarreiras.gupy.io",
 "clicksign.gupy.io",
 "bib.gupy.io",
 "uoledtech.gupy.io",
 "gruposc.gupy.io",
 "digio.gupy.io",
 "darede.gupy.io",
 "novaredbrasil.gupy.io",
 "afip.gupy.io",
 "centralailos.gupy.io",
 "fcamara.gupy.io",
 "mtpbrasil.gupy.io",
 "vwbrasil.gupy.io",
 "bellinatiperez.gupy.io",
 "netconn.gupy.io",
]

SEARCH_QUERIES = [
 'site:gupy.io/jobs "segurança da informação"',
 'site:gupy.io/jobs cybersecurity Brasil',
 'site:gupy.io/jobs "analista SOC"',
 'site:gupy.io/jobs appsec Brasil',
 'site:gupy.io/jobs devsecops segurança',
 'site:gupy.io/jobs IAM PAM segurança',
 'site:gupy.io/jobs GRC segurança',
 'site:gupy.io/jobs "cloud security" Brasil',
 'site:gupy.io/jobs "gestão de vulnerabilidades"',
 'site:br.linkedin.com/jobs/view cybersecurity Brasil',
 'site:br.linkedin.com/jobs/view "segurança da informação"',
 'site:br.linkedin.com/jobs/view "analista SOC"',
 'site:br.linkedin.com/jobs/view appsec Brasil',
]

def clean(v):
    v = html.unescape(str(v or ""))
    v = re.sub(r"<[^>]+>", " ", v)
    return re.sub(r"\s+", " ", v).strip()

def n(v): return clean(v).lower()

def cyber(title, desc="", tags=""):
    b=n(" ".join([title,desc,tags]))
    return not any(x in b for x in NEG) and any(x in b for x in CYBER)

def classify(title,desc="",tags=""):
    b=n(" ".join([title,desc,tags])); t=n(title); best=(0,"CYBERSECURITY")
    for track,words in TRACKS:
        score=sum(3 if w in t else 1 for w in words if w in b)
        if score>best[0]: best=(score,track)
    return best[1]

def seniority(title,desc=""):
    b=n(title+" "+desc[:1200])
    if any(x in b for x in ["estágio","estagio","intern","trainee","júnior","junior"," jr","assistente","entry level","n1","tier i"]): return "START"
    if any(x in b for x in ["pleno","mid-level","mid level"," n2","tier ii"]): return "PLENO"
    if any(x in b for x in ["sênior","senior"," sr","lead","staff","principal","especialista","architect","arquiteto"," n3","tier iii","coordenador","gerente"]): return "SÊNIOR"
    return "NÃO INFORMADO"

def br(location,desc="",remote=False):
    b=n(location+" "+desc[:2600])
    tokens=[
      "brazil","brasil","são paulo","sao paulo","rio de janeiro","curitiba","brasília","brasilia",
      "belo horizonte","porto alegre","recife","salvador","fortaleza","campinas","florianópolis",
      "florianopolis","goiânia","goiania","manaus","vitória","vitoria","paraná","parana","bahia",
      "ceará","ceara","pernambuco","minas gerais","rio grande do sul","santa catarina","distrito federal",
      "osasco","sorocaba","barueri","alphaville","blumenau","joinville","londrina","maringá","maringa",
      "trabalho remoto","remoto","híbrido","hibrido"
    ]
    if any(x in b for x in ["us only","usa only","united states only","canada only","europe only","uk only"]): return False
    if any(x in b for x in tokens): return True
    return remote and any(x in b for x in ["worldwide","anywhere","global","latam","latin america","south america","americas"])

def dt(v):
    if not v:return None
    try:return datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(timezone.utc)
    except:return None

def labs_for(track):
    m={
      "SOC / BLUE TEAM":[("Curso SOC N1","https://github.com/marianabsctba/Curso_SOC_N1"),("SIEM Deploy Lab","https://github.com/marianabsctba/SIEM_Deploy_Lab")],
      "DFIR / IR":[("Desafio DFIR","https://github.com/marianabsctba/Desafio_DFIR"),("Forensics Solutions","https://github.com/marianabsctba/Forensics_Solutions")],
      "GRC":[("GRC Tour","https://github.com/marianabsctba/GRC_Tour_Senhor_dos_Aneis"),("Desafio GRC","https://github.com/marianabsctba/Desafio_Pratico_GRC")],
      "APPSEC":[("Aulinha WAAP","https://github.com/marianabsctba/Aulinha_WAAP")],
      "RED TEAM / PENTEST":[("Desafio Red Team","https://github.com/marianabsctba/Desafio_Estagio_Red_Team")],
      "IAM / PAM":[("Aulinha PAM","https://github.com/marianabsctba/Aulinha_PAM")],
    }
    return [{"name":a,"url":b} for a,b in m.get(track,[])]

def mk(source,title,company,location,url,published=None,desc="",remote=False,tags=""):
    title=clean(title); company=clean(company); location=clean(location); desc=clean(desc)
    if not title or not url or not cyber(title,desc,tags) or not br(location,desc,remote): return None
    d=dt(published)
    if d and d < datetime.now(timezone.utc)-timedelta(days=MAX_AGE_DAYS): return None
    track=classify(title,desc,tags)
    is_remote=bool(remote or "remote" in n(location) or "remoto" in n(location) or "trabalho remoto" in n(location))
    return {
      "id":hashlib.sha1((source+url).encode()).hexdigest()[:16],
      "title":title,"company":company or "Não informado",
      "location":location or ("Brasil · Remoto" if is_remote else "Brasil"),
      "remote":is_remote,
      "work_model":"REMOTO" if is_remote else ("HÍBRIDO" if "híbr" in n(location+" "+desc[:700]) else "NÃO INFORMADO"),
      "track":track,"seniority":seniority(title,desc),"source":source,"url":url,
      "published":d.isoformat().replace("+00:00","Z") if d else None,
      "summary":desc[:380]+("…" if len(desc)>380 else ""),"labs":labs_for(track)
    }

def request(url,params=None):
    r=requests.get(url,params=params,headers=UA,timeout=TIMEOUT,allow_redirects=True)
    r.raise_for_status()
    return r

def get_json(url,params=None): return request(url,params).json()

def extract_job_links(html_text,base):
    soup=BeautifulSoup(html_text,"html.parser")
    urls=set()
    for a in soup.find_all("a",href=True):
        href=a["href"]
        if re.search(r"/jobs?/(?:\d+|eyJ)",href,re.I) or "/job/" in href:
            u=urljoin(base,href).split("#")[0]
            urls.add(u)
    # fallback: captura URLs/paths embutidos em scripts JSON
    for m in re.findall(r'https?://[A-Za-z0-9.-]+\.gupy\.io/(?:jobs|job)/[^"\'<>\s\\]+',html_text):
        urls.add(html.unescape(m).replace("\\u002F","/"))
    for m in re.findall(r'["\'](/(?:jobs|job)/(?:\d+|eyJ)[^"\']*)["\']',html_text):
        urls.add(urljoin(base,html.unescape(m).replace("\\u002F","/")))
    return list(urls)

def parse_job_jsonld(soup):
    def walk(obj):
        if isinstance(obj,list):
            for x in obj: yield from walk(x)
        elif isinstance(obj,dict):
            if obj.get("@type")=="JobPosting": yield obj
            for k in ("@graph","mainEntity","itemListElement"):
                if k in obj: yield from walk(obj[k])
    for s in soup.find_all("script",attrs={"type":"application/ld+json"}):
        try:
            obj=json.loads(s.string or s.get_text())
            yield from walk(obj)
        except: pass

def parse_gupy_job(url, fallback_title="", fallback_company=""):
    try:
        r=request(url)
        soup=BeautifulSoup(r.text,"html.parser")
        for job in parse_job_jsonld(soup):
            title=job.get("title") or fallback_title
            org=job.get("hiringOrganization") or {}
            company=(org.get("name") if isinstance(org,dict) else "") or fallback_company
            remote=str(job.get("jobLocationType","")).upper()=="TELECOMMUTE"
            locs=job.get("jobLocation") or []
            if isinstance(locs,dict): locs=[locs]
            parts=[]
            for loc in locs:
                addr=(loc or {}).get("address") or {}
                txt=", ".join(clean(x) for x in [addr.get("addressLocality"),addr.get("addressRegion"),addr.get("addressCountry")] if x)
                if txt: parts.append(txt)
            req=job.get("applicantLocationRequirements") or []
            if isinstance(req,dict): req=[req]
            for x in req:
                nm=clean((x or {}).get("name"))
                if nm: parts.append(nm)
            location=" / ".join(dict.fromkeys(parts))
            desc=job.get("description") or ""
            j=mk("Gupy",title,company,location,url,job.get("datePosted"),desc,remote)
            if j:return j
        # fallback textual
        h1=soup.find("h1")
        title=clean(h1.get_text(" ",strip=True) if h1 else fallback_title)
        text=clean(soup.get_text(" ",strip=True))
        company=fallback_company or urlparse(url).hostname.split(".")[0].replace("-"," ").title()
        # Gupy é BR; usa texto para detectar remoto/híbrido e mantém localização Brasil se não exposta
        return mk("Gupy",title,company,"Brasil",url,None,text,"remot" in n(text))
    except Exception as e:
        print("Gupy job falhou:",url,e); return None

def gupy_boards():
    out=[]; seen=set()
    for host in GUPY_BOARDS:
        base="https://"+host+"/"
        try:
            r=request(base)
            links=extract_job_links(r.text,base)
            print("Gupy board",host,"links encontrados:",len(links))
            for u in links[:120]:
                if u in seen: continue
                seen.add(u)
                j=parse_gupy_job(u,fallback_company=host.split(".")[0].replace("-"," ").title())
                if j: out.append(j)
                time.sleep(0.05)
        except Exception as e: print("Gupy board falhou:",host,e)
    return out

def unwrap_search_url(href):
    if not href:return ""
    href=html.unescape(href)
    if href.startswith("//"): href="https:"+href
    p=urlparse(href)
    q=parse_qs(p.query)
    for key in ("uddg","q","url"):
        if key in q and q[key]:
            u=unquote(q[key][0])
            if u.startswith("http"): return u
    return href

def duckduckgo_discovery():
    found={}
    endpoint="https://html.duckduckgo.com/html/"
    for q in SEARCH_QUERIES:
        try:
            r=request(endpoint,{"q":q})
            soup=BeautifulSoup(r.text,"html.parser")
            for a in soup.select("a.result__a, a[href]"):
                u=unwrap_search_url(a.get("href",""))
                if ("gupy.io/" in u and ("/jobs/" in u or "/job/" in u)) or "br.linkedin.com/jobs/view/" in u:
                    found[u.split("&rut=")[0]]=clean(a.get_text(" ",strip=True))
            print("DDG:",q,"acumulado:",len(found))
        except Exception as e: print("DDG falhou:",q,e)
        time.sleep(0.15)
    return found

def google_html_discovery():
    found={}
    for q in SEARCH_QUERIES[:9]:
        try:
            r=request("https://www.google.com/search",{"q":q,"num":50,"filter":"0"})
            soup=BeautifulSoup(r.text,"html.parser")
            for a in soup.find_all("a",href=True):
                u=unwrap_search_url(a["href"])
                if u.startswith("/url?"):
                    u=unwrap_search_url("https://www.google.com"+u)
                if ("gupy.io/" in u and ("/jobs/" in u or "/job/" in u)) or "br.linkedin.com/jobs/view/" in u:
                    found[u.split("&ved=")[0]]=clean(a.get_text(" ",strip=True))
            print("Google HTML:",q,"acumulado:",len(found))
        except Exception as e: print("Google HTML falhou:",q,e)
        time.sleep(0.15)
    return found

def public_search_jobs():
    found={}
    for fn in (duckduckgo_discovery, google_html_discovery):
        try: found.update(fn())
        except Exception as e: print(fn.__name__,e)
    out=[]
    for u,title in found.items():
        if "gupy.io/" in u:
            j=parse_gupy_job(u,title)
        else:
            # LinkedIn público indexado: título/snippet precisam indicar cyber; país fixo Brasil por domínio br.
            company=""
            parts=[p.strip() for p in re.split(r"\s[-|]\s",title) if p.strip()]
            if len(parts)>1: company=parts[-1].replace("LinkedIn","").strip()
            j=mk("LinkedIn",title,company,"Brasil",u,None,title,False)
        if j: out.append(j)
    print("Busca pública validada:",len(out))
    return out

def arbeitnow():
    out=[]
    for page in range(1,8):
        try:
            data=get_json("https://www.arbeitnow.com/api/job-board-api",{"page":page})
            for x in data.get("data",[]):
                j=mk("Arbeitnow",x.get("title"),x.get("company_name"),x.get("location"),x.get("url"),
                     x.get("created_at"),x.get("description"),x.get("remote",False)," ".join(x.get("tags") or []))
                if j:out.append(j)
            if not data.get("links",{}).get("next"):break
        except Exception as e: print("Arbeitnow:",e);break
    return out

def jobicy():
    out=[]
    for params in [
      {"count":100,"geo":"brazil","industry":"cybersecurity"},
      {"count":100,"geo":"brazil","tag":"security"},
      {"count":100,"industry":"cybersecurity"},
    ]:
        try:
            for x in get_json("https://jobicy.com/api/v2/remote-jobs",params).get("jobs",[]):
                j=mk("Jobicy",x.get("jobTitle"),x.get("companyName"),x.get("jobGeo"),x.get("url"),
                     x.get("pubDate"),x.get("jobDescription") or x.get("jobExcerpt"),True," ".join(x.get("jobIndustry") or []))
                if j:out.append(j)
        except Exception as e:print("Jobicy:",e)
    return out

def remotive():
    out=[]
    for q in ["security","cybersecurity","appsec","devsecops"]:
        try:
            for x in get_json("https://remotive.com/api/remote-jobs",{"search":q,"limit":100}).get("jobs",[]):
                j=mk("Remotive",x.get("title"),x.get("company_name"),x.get("candidate_required_location"),x.get("url"),
                     x.get("publication_date"),x.get("description"),True," ".join(x.get("tags") or []))
                if j:out.append(j)
        except Exception as e:print("Remotive:",e)
    return out

def dedupe(items):
    seen_urls=set();seen_jobs=set();out=[]
    priority={"Gupy":5,"LinkedIn":4,"Arbeitnow":3,"Jobicy":2,"Remotive":1}
    def score(x):return (x.get("published") or "",priority.get(x.get("source"),0))
    for x in sorted(items,key=score,reverse=True):
        u=x["url"].split("?")[0].rstrip("/")
        k=re.sub(r"\W+","",n(x["title"]))[:100]+"|"+re.sub(r"\W+","",n(x["company"]))[:65]
        if u in seen_urls or k in seen_jobs:continue
        seen_urls.add(u);seen_jobs.add(k);out.append(x)
    return out

def main():
    prev={"items":[]}
    if OUT.exists():
        try:prev=json.loads(OUT.read_text(encoding="utf-8"))
        except:pass
    fresh=[]
    for fn in (gupy_boards, public_search_jobs, arbeitnow, jobicy, remotive):
        try:
            part=fn();print(fn.__name__,":",len(part));fresh.extend(part)
        except Exception as e:print(fn.__name__,"FALHOU:",e)

    merged=dedupe(fresh+prev.get("items",[]))
    if not merged:
        print("Sem resultados; arquivo anterior preservado.");return

    srcs={}
    for x in merged:srcs[x["source"]]=srcs.get(x["source"],0)+1
    payload={
      "updated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
      "scope":"Brasil inteiro + remoto elegível para Brasil",
      "count":len(merged),
      "sources":srcs,
      "items":merged
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print("TOTAL FINAL:",len(merged))
    print("POR FONTE:",srcs)

if __name__=="__main__":main()
