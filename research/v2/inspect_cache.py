from pathlib import Path
import json, gzip, csv, os
root=Path('research/cache/fxcm')
out=Path('research/results_v2'); out.mkdir(parents=True,exist_ok=True)
files=[p for p in root.rglob('*') if p.is_file()]
rows=[]
for p in files[:5000]:
    rec={'path':str(p),'size':p.stat().st_size,'suffixes':p.suffixes}
    try:
        if p.suffix=='.gz':
            with gzip.open(p,'rt',errors='replace') as f:
                rec['line1']=f.readline().strip()[:500]
                rec['line2']=f.readline().strip()[:500]
        elif p.suffix.lower() in ['.csv','.txt']:
            with p.open('r',errors='replace') as f:
                rec['line1']=f.readline().strip()[:500]
                rec['line2']=f.readline().strip()[:500]
    except Exception as e:
        rec['error']=repr(e)
    rows.append(rec)
(out/'cache_inventory.json').write_text(json.dumps({'count':len(files),'rows':rows},indent=2),encoding='utf-8')
print('count',len(files))
