#!/usr/bin/env python3
import json, os, re, html, hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests

OUT=Path("data/jobs.json")
UA={"User-Agent":"Mozilla/5.0 (compatible; BeSafeJobs/2.0; +https://github.com/marianabsctba/Be_Safe_Academy)"}
TIMEOUT=25
MAX_AGE_DAYS=60

CYBER=["cybersecurity","cyber security","cibersegurança","segurança da informação","information security","soc analyst","analista soc","security analyst","security engineer","appsec","application security","pentest","pentester","red team","blue team","grc","iam","pam","cloud security","threat intelligence","dfir","incident response","devsecops","vulnerability","siem","soar","edr","xdr","waf","firewall"]
NEG=["security guard","segurança patrimonial","vigilante","porteiro","loss prevention"]

TRACKS=[
("SOC / BLUE TEAM",["soc","siem","soar","edr","xdr","blue team","security operations","csirt","firewall"]),
("RED TEAM / PENTEST",["red team","pentest","pentester","offensive security","ethical hacker","burp"]),
("APPSEC",["appsec","application security","sast","dast","sca","owasp","secure code"]),
("GRC",["grc","governance","compliance","risk","riscos","iso 27001","lgpd","dlp","privacy"]),
("IAM / PAM",["iam","pam","identity","access management","privileged access"]),
("CTI",["threat intelligence","cti","osint","threat hunting","inteligência de ameaças"]),
("DFIR / IR",["dfir","forensic","forense","incident response","resposta a incidentes","csirt"]),
("CLOUD SECURITY",["cloud security","aws security","azure security","gcp security","cnapp","cspm"]),
("DEVSECOPS",["devsecops","pipeline security","ci/cd security","container security","kubernetes security"]),
("IA SECURITY",["ai security","llm security","genai security","segurança de ia"]),
("VULNERABILITY",["vulnerability","vulnerabilidade","ctem","exposure management"])
]

def clean(v):
    v=html.unescape(str(v or ""))
    v=re.sub(r"<[^>]+>"," ",v)
    return re.sub(r"\s+"," ",v).strip()
def n(v): return clean(v).lower()

def cyber(title,desc="",tags=""):
    b=n(" ".join([title,desc,tags]))
    return not any(x in b for x in NEG) and any(x in b for x in CYBER)

def classify(title,desc="",tags=""):
    b=n(" ".join([title,desc,tags])); t=n(title); best=(0,"CYBERSECURITY")
    for track,words in TRACKS:
        score=sum(2 if w in t else 1 for w in words if w in b)
        if score>best[0]: best=(score,track)
    return best[1]

def seniority(title,desc=""):
    b=n(title+" "+desc[:1000])
    if any(x in b for x in ["estágio","estagio","intern","trainee","júnior","junior"," jr","assistente","entry level"]): return "START"
    if any(x in b for x in ["pleno","mid-level","mid level"]): return "PLENO"
    if any(x in b for x in ["sênior","senior"," sr","lead","staff","principal","especialista","architect","arquiteto"]): return "SÊNIOR"
    return "NÃO INFORMADO"

def br(location,desc="",remote=False):
    b=n(location+" "+desc[:2200])
    tokens=["brazil","brasil","são paulo","sao paulo","rio de janeiro","curitiba","brasília","brasilia","belo horizonte","porto alegre","recife","salvador","fortaleza","campinas","florianópolis","florianopolis","goiânia","goiania","manaus","vitória","vitoria","paraná","parana","bahia","ceará","ceara","pernambuco","minas gerais","rio grande do sul","santa catarina"]
    if any(x in b for x in ["us only","usa only","united states only","canada only","europe only"]): return False
    if any(x in b for x in tokens): return True
    return remote and any(x in b for x in ["worldwide","anywhere","global","latam","latin america","south america","americas"])

def dt(v):
    if not v:return None
    try:return datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(timezone.utc)
    except:return None

def mk(source,title,company,location,url,published=None,desc="",remote=False,tags=""):
    title=clean(title); company=clean(company); location=clean(location); desc=clean(desc)
    if not title or not url or not cyber(title,desc,tags) or not br(location,desc,remote): return None
    d=dt(published)
    if d and d<datetime.now(timezone.utc)-timedelta(days=MAX_AGE_DAYS): return None
    return {
      "id":hashlib.sha1((source+url).encode()).hexdigest()[:16],
      "title":title,"company":company or "Não informado","location":location or ("Brasil · Remoto" if remote else "Brasil"),
      "remote":bool(remote or "remote" in n(location) or "remoto" in n(location)),
      "work_model":"REMOTO" if (remote or "remote" in n(location) or "remoto" in n(location)) else "NÃO INFORMADO",
      "track":classify(title,desc,tags),"seniority":seniority(title,desc),"source":source,"url":url,
      "published":d.isoformat().replace("+00:00","Z") if d else None,"summary":desc[:360]+("…" if len(desc)>360 else ""),"labs":[]
    }

def get(url,params=None):
    r=requests.get(url,params=params,headers=UA,timeout=TIMEOUT); r.raise_for_status(); return r.json()

def jobicy():
    out=[]
    for params in [
      {"count":100,"geo":"brazil","industry":"cybersecurity"},
      {"count":100,"geo":"brazil","tag":"security"},
      {"count":100,"industry":"cybersecurity"}
    ]:
      try:
        data=get("https://jobicy.com/api/v2/remote-jobs",params)
        for x in data.get("jobs",[]):
          j=mk("Jobicy",x.get("jobTitle"),x.get("companyName"),x.get("jobGeo"),x.get("url"),x.get("pubDate"),x.get("jobDescription") or x.get("jobExcerpt"),True," ".join(x.get("jobIndustry") or []))
          if j: out.append(j)
      except Exception as e: print("Jobicy:",e)
    return out

def remotive():
    out=[]
    for q in ["security","cybersecurity"]:
      try:
        data=get("https://remotive.com/api/remote-jobs",{"search":q,"limit":100})
        for x in data.get("jobs",[]):
          j=mk("Remotive",x.get("title"),x.get("company_name"),x.get("candidate_required_location"),x.get("url"),x.get("publication_date"),x.get("description"),True," ".join(x.get("tags") or []))
          if j: out.append(j)
      except Exception as e: print("Remotive:",e)
    return out

def dedupe(items):
    seen=set(); out=[]
    for x in sorted(items,key=lambda z:z.get("published") or "",reverse=True):
      k=re.sub(r"\W+","",n(x["title"]))[:90]+"|"+re.sub(r"\W+","",n(x["company"]))[:60]
      if k in seen: continue
      seen.add(k); out.append(x)
    return out

def main():
    previous={"items":[]}
    if OUT.exists():
      try: previous=json.loads(OUT.read_text(encoding="utf-8"))
      except: pass
    items=dedupe(jobicy()+remotive())
    # Nunca destrói a lista válida por falha de APIs.
    if not items:
      print("Nenhuma fonte retornou vagas novas; mantendo jobs.json atual.")
      return
    payload={"updated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"scope":"Brasil inteiro + remoto elegível para Brasil","count":len(items),"items":items}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Vagas:",len(items))

if __name__=="__main__": main()
