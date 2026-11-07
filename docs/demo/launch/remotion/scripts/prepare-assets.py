"""Copy local source media; validate coordinator motion manifest; no network/API."""
from pathlib import Path
import json,shutil,hashlib
ROOT=Path(__file__).resolve().parents[5];PROJECT=Path(__file__).resolve().parents[1];PUBLIC=PROJECT/'public';PUBLIC.mkdir(exist_ok=True)
files={'pep-finding.png':'reports/demo-output/launch/pep-finding.png','pep-citation.png':'reports/demo-output/launch/pep-citation.png','report-scope.png':'reports/demo-output/current/02-draft-scope.png','report-pep.png':'reports/demo-output/current/03-regulatory-facts.png','report-gap.png':'reports/demo-output/current/07-coverage-gaps.png','pep-source.png':'reports/demo-output/launch/motion/pep-source-page-2.png','review-raw.webm':'reports/demo-output/authenticated/raw/page@bb202f021ab21334ab86fca9ca3f68d6.webm','evidence.png':'reports/demo-output/authenticated/05-evidence.png','amendment.png':'reports/demo-output/authenticated/06-amendment.png','stale.png':'reports/demo-output/authenticated/07-stale-block.png','fresh.png':'reports/demo-output/authenticated/08-fresh-review.png','needs-evidence.png':'reports/demo-output/authenticated/09-evidence-block.png','rejection.png':'reports/demo-output/authenticated/10-rejection.png','signed.png':'reports/demo-output/authenticated/11-signed.png','original.png':'reports/demo-output/authenticated/14-original-body.png','reviewed.png':'reports/demo-output/authenticated/16-reviewed-body.png','reviewed-summary.png':'reports/demo-output/authenticated/15-reviewed-summary.png','brief.png':'reports/demo-output/launch/workflow-brief.png','plan.png':'reports/demo-output/launch/workflow-plan.png','approved.png':'reports/demo-output/launch/workflow-approved.png','progress.png':'reports/demo-output/launch/workflow-progress.png','complete.png':'reports/demo-output/launch/workflow-complete.png'}
manifest=json.loads((ROOT/'docs/demo/launch/motion-manifest.json').read_text());assert (manifest['fps'],manifest['width'],manifest['height'])==(30,1920,1080)
motion={}
for seq in manifest['sequences']:
 p=ROOT/seq['renderPath'];motion[seq['id']]={'available':p.is_file(),'durationSeconds':seq['durationSeconds'],'startSeconds':seq['startSeconds'],'asset':f"motion-{seq['id']}.mp4"}
 if p.is_file():files[f"motion-{seq['id']}.mp4"]=seq['renderPath']
(PROJECT/'src/motion.json').write_text(json.dumps(motion,indent=2))
missing=[];ledger=[]
for dest,src in files.items():
 path=ROOT/src
 if not path.is_file():missing.append(src);continue
 shutil.copy2(path,PUBLIC/dest);ledger.append({'asset':dest,'source':src,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(PUBLIC/'asset-ledger.json').write_text(json.dumps({'assets':ledger,'missing':missing},indent=2));print(json.dumps({'copied':len(ledger),'missing':missing,'motion':motion},indent=2))
