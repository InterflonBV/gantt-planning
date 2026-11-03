#!/usr/bin/env python3
"""Create public gantt-data.json from a GitHub repository_dispatch payload.
NEVER publish raw SharePoint records or private metadata.
"""
import datetime,json,os,re,sys
from pathlib import Path

def fail(msg): raise ValueError(msg)
def is_date(x):
    if not isinstance(x,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',x):return False
    try:return datetime.date.fromisoformat(x).isoformat()==x
    except ValueError:return False

def build(payload):
    if not isinstance(payload,dict):fail('Geen object als client_payload')
    projects=payload.get('projects');sp=payload.get('sharepointProjects');milestones=payload.get('milestones')
    if not isinstance(projects,list) or not projects:fail('Geen projecten ontvangen')
    if not isinstance(sp,list) or not isinstance(milestones,list):fail('SharePoint-projecten of mijlpalen ontbreken')
    if len(projects)>1500 or len(milestones)>3000:fail('Onverwacht grote planning; verwerking gestopt')
    byid={}
    for p in projects:
        if not isinstance(p,dict):fail('Project is geen object')
        pid=str(p.get('wrikeId','')).strip()
        if not re.fullmatch(r'\d+',pid):fail('Ongeldige Wrike-ID')
        if pid in byid:fail('Dubbele Wrike-ID: '+pid)
        if not p.get('name') or not p.get('status'):fail('Projectnaam/status ontbreekt')
        if not is_date(p.get('startDate')) or not is_date(p.get('endDate')) or p['endDate']<p['startDate']:fail('Ongeldige projectdatums: '+pid)
        byid[pid]=p
    for pid,p in byid.items():
        par=str(p.get('parentWrikeId') or '')
        if par and par not in byid:fail('Onbekende parentWrikeId voor '+pid)
        if par==pid:fail('Zelfverwijzende projectrelatie: '+pid)
        visited={pid}
        while par:
            if par in visited:fail('Cirkel in hiërarchie: '+pid)
            visited.add(par);par=str(byid[par].get('parentWrikeId') or '')
    spmap={}
    for p in sp:
        sid=str(p.get('id','')).strip();wid=str(p.get('wrikeId','')).strip()
        if not sid.isdigit() or not wid.isdigit():fail('Ongeldig actief SharePoint-project')
        if sid in spmap:fail('Dubbel SharePoint item ID: '+sid)
        spmap[sid]=wid
    if len(set(spmap.values()))!=len(spmap):fail('Meerdere SharePoint-items voor dezelfde Wrike-ID')
    if set(spmap.values())!=set(byid):fail('Actieve SharePoint-projecten wijken af van Wrike-export. Publicatie geblokkeerd.')
    checked=[];seen=set()
    for m in milestones:
        mid=str(m.get('id','')).strip();sid=str(m.get('projectId','')).strip()
        if not mid.isdigit() or mid in seen:fail('Dubbele/ongeldige mijlpaal-ID')
        seen.add(mid)
        if not m.get('title') or not is_date(m.get('date')):fail('Ongeldige mijlpaal: '+mid)
        if sid not in spmap:fail('Mijlpaal '+mid+' heeft geen actief gekoppeld project')
        checked.append({'id':int(mid),'title':str(m['title']),'date':m['date'],'status':str(m.get('status') or 'Planned'),'wrikeId':spmap[sid]})
    cleaned=[]
    for pid,p in byid.items():
        cleaned.append({'wrikeId':pid,'name':str(p['name']),'status':str(p['status']),'startDate':p['startDate'],'endDate':p['endDate'],'parentWrikeId':str(p.get('parentWrikeId') or ''),'parentName':str(p.get('parentName') or ''),'level':int(p.get('level') or 1)})
    return {'schema':'interflon-stakeholder-gantt-v1','publishedAt':datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),'projects':cleaned,'milestones':checked}

if __name__=='__main__':
    raw=os.environ.get('GANTT_DISPATCH_PAYLOAD')
    if not raw:fail('GANTT_DISPATCH_PAYLOAD ontbreekt')
    obj=json.loads(raw)
    result=build(obj)
    Path('gantt-data.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('Gevalideerd:',len(result['projects']),'projecten;',len(result['milestones']),'mijlpalen')
