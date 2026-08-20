#!/usr/bin/env python3
import json, os, re, html, hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests

OUT = Path('data/jobs.json')
UA = {'User-Agent': 'Be-Safe-Academy-Jobs/1.0 (+https://marianabsctba.github.io/Be_Safe_Academy/)'}
TIMEOUT = 20
MAX_AGE_DAYS = 45

CYBER_TERMS = [
    'cybersecurity','cyber security','cibersegurança','segurança da informação','information security',
    'security analyst','security engineer','soc analyst','analista soc','blue team','red team','pentest','pentester',
    'application security','appsec','devsecops','cloud security','iam','identity access','pam','privileged access',
    'grc','governance risk compliance','threat intelligence','cti','dfir','incident response','security operations',
    'vulnerability management','gestão de vulnerabilidades','security architect','security specialist','waf','siem','soar','edr','xdr'
]

NEGATIVE_TERMS = ['security guard','segurança patrimonial','vigilante','porteiro','loss prevention','physical security']

TRACKS = [
    ('SOC / BLUE TEAM', ['soc','siem','soar','edr','xdr','blue team','security operations','detection','monitoring']),
    ('RED TEAM / PENTEST', ['red team','pentest','pentester','offensive security','ethical hacker','burp','exploit']),
    ('APPSEC', ['appsec','application security','sast','dast','owasp','secure code','product security']),
    ('GRC', ['grc','governance','compliance','iso 27001','risk','riscos','lgpd','privacy','privacidade']),
    ('IAM / PAM', ['iam','pam','identity','access management','privileged access','entra id','okta','sailpoint']),
    ('CTI', ['threat intelligence','cti','osint','threat hunting','inteligência de ameaças']),
    ('DFIR / IR', ['dfir','forensic','forense','incident response','resposta a incidentes','malware analysis']),
    ('CLOUD SECURITY', ['cloud security','aws security','azure security','gcp security','cnapp','cspm','cwpp']),
    ('DEVSECOPS', ['devsecops','pipeline security','ci/cd security','container security','kubernetes security']),
    ('IA SECURITY', ['ai security','security ai','llm security','genai security','machine learning security','segurança de ia']),
    ('VULNERABILITY', ['vulnerability','vulnerabilidade','ctem','exposure management','patch management'])
]

LABS = {
    'SOC / BLUE TEAM': [('Curso SOC N1','https://github.com/marianabsctba/Curso_SOC_N1'),('SIEM Deploy Lab','https://github.com/marianabsctba/SIEM_Deploy_Lab'),('Syslog Lab','https://github.com/marianabsctba/Syslog_Lab')],
    'RED TEAM / PENTEST': [('Desafio Red Team','https://github.com/marianabsctba/Desafio_Estagio_Red_Team'),('Brute Force','https://github.com/marianabsctba/Aulinha_Brute_Force')],
    'APPSEC': [('Aulinha WAAP','https://github.com/marianabsctba/Aulinha_WAAP')],
    'GRC': [('GRC Tour','https://github.com/marianabsctba/GRC_Tour_Senhor_dos_Aneis'),('Desafio GRC','https://github.com/marianabsctba/Desafio_Pratico_GRC')],
    'IAM / PAM': [('Aulinha PAM','https://github.com/marianabsctba/Aulinha_PAM')],
    'CTI': [('CTI Elite','https://github.com/marianabsctba/CTI_Elite_Free_Certification'),('EASM Tour','https://github.com/marianabsctba/EASM_Tour')],
    'DFIR / IR': [('Forensics Solutions','https://github.com/marianabsctba/Forensics_Solutions'),('Desafio DFIR','https://github.com/marianabsctba/Desafio_DFIR')],
    'VULNERABILITY': [('EASM Tour','https://github.com/marianabsctba/EASM_Tour')],
}


def clean_text(value):
    if value is None: return ''
    value = html.unescape(str(value))
    value = re.sub(r'<[^>]+>', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def norm(s):
    return clean_text(s).lower()


def is_cyber(title, desc='', tags=''):
    blob = norm(' '.join([title, desc, tags]))
    if any(x in blob for x in NEGATIVE_TERMS): return False
    return any(x in blob for x in CYBER_TERMS)


def classify(title, desc='', tags=''):
    blob = norm(' '.join([title, desc, tags]))
    scores=[]
    for track, words in TRACKS:
        score=sum(2 if w in norm(title) else 1 for w in words if w in blob)
        if score: scores.append((score, track))
    return max(scores)[1] if scores else 'CYBERSECURITY'


def seniority(title, desc=''):
    t=norm(title+' '+desc[:1000])
    if any(x in t for x in ['estágio','estagio','intern','trainee']): return 'ESTÁGIO'
    if any(x in t for x in ['júnior','junior',' jr','entry level','assistente']): return 'START'
    if any(x in t for x in ['pleno','mid-level','mid level']): return 'PLENO'
    if any(x in t for x in ['sênior','senior',' sr','lead','staff','principal','especialista']): return 'SÊNIOR'
    return 'NÃO INFORMADO'


def br_ok(location, desc='', remote=False):
    blob=norm(location+' '+desc[:2500])
    br_tokens=['brazil','brasil','são paulo','sao paulo','rio de janeiro','curitiba','brasília','brasilia','belo horizonte','porto alegre','recife','salvador','fortaleza','campinas','florianópolis','florianopolis','goiânia','goiania','manaus','vitória','vitoria','paraná','parana','bahia','ceará','ceara','pernambuco','minas gerais','rio grande do sul','santa catarina']
    global_ok=['worldwide','anywhere','global','latin america','latam','south america','americas']
    excluded=['united states only','usa only','us only','canada only','europe only','uk only']
    if any(x in blob for x in excluded): return False
    if any(x in blob for x in br_tokens): return True
    return bool(remote and any(x in blob for x in global_ok))


def parse_date(v):
    if not v: return None
    s=str(v).replace('Z','+00:00')
    try: return datetime.fromisoformat(s).astimezone(timezone.utc)
    except Exception:
        for fmt in ('%Y-%m-%d','%Y-%m-%d %H:%M:%S'):
            try: return datetime.strptime(s[:19],fmt).replace(tzinfo=timezone.utc)
            except Exception: pass
    return None


def make_id(source,url,title,company):
    raw='|'.join([source,url,title,company]).lower().encode()
    return hashlib.sha1(raw).hexdigest()[:16]


def job(source,title,company,location,url,published=None,desc='',remote=False,tags='',logo=''):
    title=clean_text(title); company=clean_text(company); location=clean_text(location) or ('Remoto' if remote else 'Não informado')
    desc=clean_text(desc)
    if not title or not url or not is_cyber(title,desc,tags): return None
    if not br_ok(location,desc,remote): return None
    dt=parse_date(published)
    if dt and dt < datetime.now(timezone.utc)-timedelta(days=MAX_AGE_DAYS): return None
    track=classify(title,desc,tags)
    return {
      'id': make_id(source,url,title,company), 'title':title, 'company':company or 'Não informado',
      'location':location, 'remote':bool(remote or 'remote' in norm(location) or 'remoto' in norm(location)),
      'track':track, 'seniority':seniority(title,desc), 'source':source, 'url':url,
      'published': dt.isoformat().replace('+00:00','Z') if dt else None,
      'summary': desc[:360] + ('…' if len(desc)>360 else ''), 'logo':logo or '',
      'labs':[{'name':n,'url':u} for n,u in LABS.get(track,[])][:3]
    }


def get_json(url, params=None):
    r=requests.get(url,params=params,headers=UA,timeout=TIMEOUT)
    r.raise_for_status(); return r.json()


def fetch_jobicy():
    out=[]
    # geo=brazil is the first choice; multiple cyber tags broaden discovery.
    for tag in ['cybersecurity','security','soc','appsec','devsecops']:
        try:
            data=get_json('https://jobicy.com/api/v2/remote-jobs',{'count':100,'geo':'brazil','tag':tag})
            for x in data.get('jobs',[]):
                j=job('Jobicy',x.get('jobTitle'),x.get('companyName'),x.get('jobGeo'),x.get('url'),x.get('pubDate'),x.get('jobDescription') or x.get('jobExcerpt'),True,' '.join(x.get('jobIndustry') or []),x.get('companyLogo'))
                if j: out.append(j)
        except Exception as e: print('Jobicy:',e)
    return out


def fetch_remotive():
    out=[]
    for q in ['cybersecurity','security analyst','soc','appsec','devsecops','pentest']:
        try:
            data=get_json('https://remotive.com/api/remote-jobs',{'search':q,'limit':100})
            for x in data.get('jobs',[]):
                loc=x.get('candidate_required_location') or ''
                j=job('Remotive',x.get('title'),x.get('company_name'),loc,x.get('url'),x.get('publication_date'),x.get('description'),True,' '.join(x.get('tags') or []),x.get('company_logo'))
                if j: out.append(j)
        except Exception as e: print('Remotive:',e)
    return out


def google_cse_links():
    key=os.getenv('GOOGLE_API_KEY'); cx=os.getenv('GOOGLE_CSE_ID')
    if not key or not cx: return []
    queries=[
      'site:br.linkedin.com/jobs/view (cybersecurity OR "segurança da informação" OR "security analyst") Brasil',
      'site:br.linkedin.com/jobs/view (SOC OR AppSec OR DevSecOps OR Pentest OR GRC) Brasil',
      'site:br.linkedin.com/jobs/view (IAM OR PAM OR "cloud security" OR "incident response") Brasil'
    ]
    links=[]
    for q in queries:
        try:
            data=get_json('https://www.googleapis.com/customsearch/v1',{'key':key,'cx':cx,'q':q,'num':10,'gl':'br','cr':'countryBR'})
            for item in data.get('items',[]):
                u=item.get('link','')
                if 'linkedin.com/jobs/view/' in u: links.append(u)
        except Exception as e: print('Google CSE:',e)
    return list(dict.fromkeys(links))


def fetch_linkedin_public(url):
    try:
        r=requests.get(url,headers=UA,timeout=TIMEOUT,allow_redirects=True)
        if r.status_code >= 400: return None
        # Public LinkedIn job pages commonly expose schema.org JobPosting JSON-LD.
        scripts=re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',r.text,re.I|re.S)
        for raw in scripts:
            try: data=json.loads(html.unescape(raw))
            except Exception: continue
            blocks=data if isinstance(data,list) else [data]
            for x in blocks:
                if isinstance(x,dict) and x.get('@type')=='JobPosting':
                    org=x.get('hiringOrganization') or {}; loc=x.get('jobLocation') or []
                    if isinstance(loc,dict): loc=[loc]
                    loc_text=[]
                    for item in loc:
                        addr=(item or {}).get('address') or {}
                        loc_text.append(', '.join(filter(None,[addr.get('addressLocality'),addr.get('addressRegion'),addr.get('addressCountry')])))
                    remote=str(x.get('jobLocationType','')).upper()=='TELECOMMUTE'
                    return job('LinkedIn',x.get('title'),org.get('name'),'; '.join(filter(None,loc_text)) or ('Remoto' if remote else ''),url,x.get('datePosted'),x.get('description'),remote)
    except Exception as e: print('LinkedIn public:',e)
    return None


def dedupe(items):
    seen=set(); out=[]
    for x in sorted(items,key=lambda z:z.get('published') or '',reverse=True):
        key=re.sub(r'\W+','',norm(x['title']))[:70]+'|'+re.sub(r'\W+','',norm(x['company']))[:50]
        if key in seen: continue
        seen.add(key); out.append(x)
    return out


def main():
    items=[]
    items += fetch_jobicy()
    items += fetch_remotive()
    for u in google_cse_links():
        x=fetch_linkedin_public(u)
        if x: items.append(x)
    items=dedupe(items)
    payload={'updated_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'scope':'Brasil + remoto elegível para Brasil','count':len(items),'items':items}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{len(items)} vagas publicadas em {OUT}')

if __name__=='__main__': main()
