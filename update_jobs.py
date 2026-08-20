#!/usr/bin/env python3
import json, os, re, html, hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

OUT = Path("data/jobs.json")
UA = {"User-Agent":"Mozilla/5.0 (compatible; BeSafeJobs/3.0; +https://github.com/marianabsctba/Be_Safe_Academy)"}
TIMEOUT = 25
MAX_AGE_DAYS = 75

CYBER = [
 "cybersecurity","cyber security","cibersegurança","segurança da informação","information security",
 "soc","security analyst","analista de segurança","security engineer","appsec","application security",
 "pentest","pentester","red team","blue team","grc","iam","pam","cloud security","threat intelligence",
 "dfir","incident response","devsecops","vulnerability","vulnerabilidade","siem","soar","edr","xdr",
 "waf","firewall","dlp","zero trust","security operations","csirt","gestão de acessos","gestao de acessos"
]
NEG = ["security guard","segurança patrimonial","vigilante","porteiro","loss prevention","técnico de segurança do trabalho"]

TRACKS = [
 ("SOC / BLUE TEAM",["soc","siem","soar","edr","xdr","blue team","security operations","csirt","firewall","monitoramento"]),
 ("RED TEAM / PENTEST",["red team","pentest","pentester","offensive security","ethical hacker","burp"]),
 ("APPSEC",["appsec","application security","sast","dast","sca","owasp","secure code","security by design"]),
 ("GRC",["grc","governance","governança","compliance","risk","riscos","iso 27001","lgpd","dlp","privacy"]),
 ("IAM / PAM",["iam","pam","identity","identidade","access management","gestão de acessos","privileged access","sailpoint"]),
 ("CTI",["threat intelligence","cti","osint","threat hunting","inteligência de ameaças"]),
 ("DFIR / IR",["dfir","forensic","forense","incident response","resposta a incidentes","csirt"]),
 ("CLOUD SECURITY",["cloud security","aws security","azure security","gcp security","cnapp","cspm"]),
 ("DEVSECOPS",["devsecops","pipeline security","ci/cd security","container security","kubernetes security"]),
 ("IA SECURITY",["ai security","llm security","genai security","segurança de ia","security ai"]),
 ("VULNERABILITY",["vulnerability","vulnerabilidade","ctem","exposure management","gestão de vulnerabilidades"])
]

# Boards Gupy com histórico/volume de vagas de cyber no Brasil.
GUPY_BOARDS = [
 "netsecurity.gupy.io",
 "bellinatiperez.gupy.io",
 "centralailos.gupy.io",
 "vagasconfidenciaisoportunidades.gupy.io",
 "netconn.gupy.io",
 "fcamara.gupy.io",
 "mtpbrasil.gupy.io",
 "compass.gupy.io",
 "vwbrasil.gupy.io",
 "vagascappta.gupy.io",
]

def clean(v):
    v = html.unescape(str(v or ""))
    v = re.sub(r"<[^>]+>", " ", v)
    return re.sub(r"\s+", " ", v).strip()

def n(v): return clean(v).lower()

def cyber(title, desc="", tags=""):
    blob = n(" ".join([title, desc, tags]))
    return not any(x in blob for x in NEG) and any(x in blob for x in CYBER)

def classify(title, desc="", tags=""):
    blob=n(" ".join([title,desc,tags])); t=n(title); best=(0,"CYBERSECURITY")
    for track,words in TRACKS:
        score=sum(3 if w in t else 1 for w in words if w in blob)
        if score>best[0]: best=(score,track)
    return best[1]

def seniority(title,desc=""):
    b=n(title+" "+desc[:1200])
    if any(x in b for x in ["estágio","estagio","intern","trainee","júnior","junior"," jr","assistente","entry level","n1","tier i"]): return "START"
    if any(x in b for x in ["pleno","mid-level","mid level"," n2","tier ii"]): return "PLENO"
    if any(x in b for x in ["sênior","senior"," sr","lead","staff","principal","especialista","architect","arquiteto"," n3","tier iii"]): return "SÊNIOR"
    return "NÃO INFORMADO"

def br(location,desc="",remote=False):
    b=n(location+" "+desc[:2600])
    tokens=[
      "brazil","brasil","são paulo","sao paulo","rio de janeiro","curitiba","brasília","brasilia",
      "belo horizonte","porto alegre","recife","salvador","fortaleza","campinas","florianópolis",
      "florianopolis","goiânia","goiania","manaus","vitória","vitoria","paraná","parana","bahia",
      "ceará","ceara","pernambuco","minas gerais","rio grande do sul","santa catarina","distrito federal",
      "osasco","sorocaba","barueri","alphaville","blumenau","joinville","londrina","maringá","maringa"
    ]
    if any(x in b for x in ["us only","usa only","united states only","canada only","europe only","uk only"]): return False
    if any(x in b for x in tokens): return True
    return remote and any(x in b for x in ["worldwide","anywhere","global","latam","latin america","south america","americas"])

def dt(v):
    if not v: return None
    try:
        return datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(timezone.utc)
    except:
        return None

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
    is_remote=bool(remote or "remote" in n(location) or "remoto" in n(location))
    return {
      "id":hashlib.sha1((source+url).encode()).hexdigest()[:16],
      "title":title,"company":company or "Não informado",
      "location":location or ("Brasil · Remoto" if is_remote else "Brasil"),
      "remote":is_remote,
      "work_model":"REMOTO" if is_remote else ("HÍBRIDO" if "híbr" in n(location+" "+desc[:600]) else "NÃO INFORMADO"),
      "track":track,"seniority":seniority(title,desc),"source":source,"url":url,
      "published":d.isoformat().replace("+00:00","Z") if d else None,
      "summary":desc[:380]+("…" if len(desc)>380 else ""),
      "labs":labs_for(track)
    }

def request(url, params=None):
    r=requests.get(url,params=params,headers=UA,timeout=TIMEOUT)
    r.raise_for_status()
    return r

def get_json(url,params=None): return request(url,params).json()

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
          if j: out.append(j)
      except Exception as e: print("Jobicy:",e)
    return out

def remotive():
    out=[]
    for q in ["security","cybersecurity","appsec","devsecops"]:
      try:
        for x in get_json("https://remotive.com/api/remote-jobs",{"search":q,"limit":100}).get("jobs",[]):
          j=mk("Remotive",x.get("title"),x.get("company_name"),x.get("candidate_required_location"),x.get("url"),
               x.get("publication_date"),x.get("description"),True," ".join(x.get("tags") or []))
          if j: out.append(j)
      except Exception as e: print("Remotive:",e)
    return out

def arbeitnow():
    out=[]
    for page in range(1,6):
      try:
        data=get_json("https://www.arbeitnow.com/api/job-board-api",{"page":page})
        for x in data.get("data",[]):
          j=mk("Arbeitnow",x.get("title"),x.get("company_name"),x.get("location"),x.get("url"),
               x.get("created_at"),x.get("description"),x.get("remote",False)," ".join(x.get("tags") or []))
          if j: out.append(j)
        if not data.get("links",{}).get("next"): break
      except Exception as e:
        print("Arbeitnow:",e); break
    return out

def flatten_jsonld(obj):
    if isinstance(obj,list):
      for x in obj: yield from flatten_jsonld(x)
    elif isinstance(obj,dict):
      if obj.get("@type")=="JobPosting": yield obj
      if "@graph" in obj: yield from flatten_jsonld(obj["@graph"])

def gupy_location(job):
    remote=str(job.get("jobLocationType","")).upper()=="TELECOMMUTE"
    locs=job.get("jobLocation") or []
    if isinstance(locs,dict): locs=[locs]
    parts=[]
    for loc in locs:
      addr=(loc or {}).get("address") or {}
      p=[addr.get("addressLocality"),addr.get("addressRegion"),addr.get("addressCountry")]
      s=", ".join(clean(x) for x in p if x)
      if s: parts.append(s)
    location=" / ".join(dict.fromkeys(parts))
    if remote and "brasil" not in n(location) and "brazil" not in n(location):
      req=job.get("applicantLocationRequirements") or []
      if isinstance(req,dict): req=[req]
      for x in req:
        name=clean((x or {}).get("name"))
        if name: parts.append(name)
      location=" / ".join(dict.fromkeys(parts))
    return location,remote

def parse_gupy_job(url, fallback_title=""):
    try:
      r=request(url); soup=BeautifulSoup(r.text,"html.parser")
      postings=[]
      for s in soup.find_all("script",attrs={"type":"application/ld+json"}):
        try: postings.extend(flatten_jsonld(json.loads(s.string or s.get_text())))
        except: pass
      for job in postings:
        title=job.get("title") or fallback_title
        org=job.get("hiringOrganization") or {}
        company=org.get("name") if isinstance(org,dict) else ""
        location,remote=gupy_location(job)
        desc=job.get("description") or ""
        date=job.get("datePosted") or job.get("validThrough")
        j=mk("Gupy",title,company,location,url,date,desc,remote)
        if j: return j
      # fallback do HTML para páginas sem JSON-LD
      title=(soup.find("h1").get_text(" ",strip=True) if soup.find("h1") else fallback_title)
      text=soup.get_text(" ",strip=True)
      return mk("Gupy",title,urlparse(url).hostname.split(".")[0],"Brasil",url,None,text,False)
    except Exception as e:
      print("Gupy job:",url,e); return None

def gupy():
    out=[]; seen=set()
    for host in GUPY_BOARDS:
      base="https://"+host+"/"
      try:
        soup=BeautifulSoup(request(base).text,"html.parser")
        links=[]
        for a in soup.find_all("a",href=True):
          href=a["href"]
          if re.search(r"/jobs/\d+",href):
            url=urljoin(base,href.split("?")[0])
            title=clean(a.get_text(" ",strip=True))
            if url not in seen:
              seen.add(url); links.append((url,title))
        print("Gupy",host,"links",len(links))
        for url,title in links[:80]:
          j=parse_gupy_job(url,title)
          if j: out.append(j)
      except Exception as e: print("Gupy board:",host,e)
    return out

def google_cse():
    key=os.getenv("GOOGLE_API_KEY"); cx=os.getenv("GOOGLE_CSE_ID")
    if not key or not cx: return []
    out=[]
    queries=[
      'site:br.linkedin.com/jobs/view ("cybersecurity" OR "segurança da informação" OR "analista SOC" OR appsec OR pentest) Brasil',
      'site:gupy.io/jobs ("segurança da informação" OR cybersecurity OR "analista SOC" OR appsec OR IAM OR GRC)',
      'site:jobs.lever.co Brazil ("security engineer" OR cybersecurity OR appsec)',
      'site:boards.greenhouse.io Brazil ("security engineer" OR cybersecurity OR appsec)',
      'site:jobs.ashbyhq.com Brazil ("security engineer" OR cybersecurity OR appsec)'
    ]
    for q in queries:
      for start in (1,11,21):
        try:
          data=get_json("https://www.googleapis.com/customsearch/v1",{"key":key,"cx":cx,"q":q,"num":10,"start":start})
          for x in data.get("items",[]):
            link=x.get("link",""); title=clean(x.get("title")); snippet=clean(x.get("snippet"))
            source="LinkedIn" if "linkedin.com/jobs" in link else ("Gupy" if "gupy.io" in link else "Google / carreira")
            company=""
            if " - " in title: company=title.split(" - ")[-1]
            # Resultados CSE são descoberta: se localização não vier clara no snippet, marca Brasil
            j=mk(source,title,company,"Brasil",link,None,snippet,False)
            if j: out.append(j)
        except Exception as e: print("Google CSE:",e); break
    return out

def dedupe(items):
    seen_urls=set(); seen_jobs=set(); out=[]
    def rank(x):
      return (x.get("published") or "", 1 if x.get("source")=="Gupy" else 0)
    for x in sorted(items,key=rank,reverse=True):
      u=x["url"].split("?")[0].rstrip("/")
      key=re.sub(r"\W+","",n(x["title"]))[:95]+"|"+re.sub(r"\W+","",n(x["company"]))[:65]
      if u in seen_urls or key in seen_jobs: continue
      seen_urls.add(u); seen_jobs.add(key); out.append(x)
    return out

def main():
    previous={"items":[]}
    if OUT.exists():
      try: previous=json.loads(OUT.read_text(encoding="utf-8"))
      except: pass

    fresh=[]
    for fn in (gupy, arbeitnow, jobicy, remotive, google_cse):
      try:
        part=fn()
        print(fn.__name__,len(part))
        fresh.extend(part)
      except Exception as e: print(fn.__name__,"FALHOU:",e)

    # Merge com anterior: uma fonte temporariamente fora do ar não apaga vagas válidas.
    merged=dedupe(fresh + previous.get("items",[]))
    if not merged:
      print("Nenhuma vaga disponível; preservando arquivo existente.")
      return

    payload={
      "updated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
      "scope":"Brasil inteiro + remoto elegível para Brasil",
      "count":len(merged),
      "sources":{
        "Gupy":sum(x.get("source")=="Gupy" for x in merged),
        "LinkedIn":sum(x.get("source")=="LinkedIn" for x in merged),
        "Arbeitnow":sum(x.get("source")=="Arbeitnow" for x in merged),
        "Jobicy":sum(x.get("source")=="Jobicy" for x in merged),
        "Remotive":sum(x.get("source")=="Remotive" for x in merged),
      },
      "items":merged
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print("TOTAL:",len(merged),payload["sources"])

if __name__=="__main__":
    main()
