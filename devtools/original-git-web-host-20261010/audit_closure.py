"""Read-only independent SHA/index/G7 check against this run's exact preimages."""
import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
TASK=HERE.relative_to(ROOT).as_posix()
CHANGED={
    'kuro_launcher/qt_web_host.py','kuro_launcher/qt_web_adapter.py',
    'tests/qt_web_frontend.test.cjs','tests/test_qt_web_w4_w5.py',
    'tests/web_candidate_fixtures.py','tests/test_qt_web_transport.py',
    TASK+'/frontend/src/owner-bootstrap.ts',TASK+'/validate_candidate.py',
}


def sha(data): return hashlib.sha256(data).hexdigest()
def git(*args): return subprocess.check_output(['git','--no-optional-locks',*args],cwd=ROOT)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--before',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve()
    if not out.is_relative_to(HERE/'.runtime') or out.exists(): parser.error('New task-local output required')
    before=json.loads(args.before.read_text(encoding='utf-8'))
    paths=set(git('ls-files','--cached','--others','--exclude-standard','-z').decode().split('\0'))-{''}
    current={p:sha((ROOT/p).read_bytes()) if (ROOT/p).is_file() else None for p in sorted(paths)}
    changed=sorted(p for p,v in before['files'].items() if current.get(p)!=v)
    added=sorted(paths-set(before['files']))
    source=json.loads((HERE/'SourceVerification.json').read_text(encoding='utf-8'))['sources']
    pinned=[{'path':s['destination'],'sha256':sha((ROOT/s['destination']).read_bytes()),
        'originalSha256':sha(git('show','995c23c7c8d1be62000229d58610d2214f3bb745:'+s['source']))} for s in source]
    g7=json.loads((ROOT/'docs/agent-runs/qt-ui-convergence-20261007/G7DeletionManifest.json').read_text(encoding='utf-8'))['files']
    resurrected=[s['path'] for s in g7 if (ROOT/s['path']).exists()]
    index=sha((ROOT/'.git/index').read_bytes())
    patch=[]
    for relative in changed:
        old=args.before.parent/'preimages'/relative
        if relative in CHANGED and old.is_file():
            patch.extend(difflib.unified_diff(old.read_text(encoding='utf-8').splitlines(True),
                (ROOT/relative).read_text(encoding='utf-8').splitlines(True),fromfile='preimage/'+relative,tofile='worktree/'+relative))
    status=git('status','--porcelain=v1','-z','-uall').decode()
    result={'utc':datetime.now(timezone.utc).isoformat(),'head':git('rev-parse','HEAD').decode().strip(),
        'branch':git('branch','--show-current').decode().strip(),'indexSha256':index,'indexUnchanged':index==before['indexSha256'],
        'stagedDiffUnchanged':git('diff','--cached','--binary')==(args.before.parent/'Index.diff').read_bytes(),
        'changedExisting':changed,'unexpectedExistingChanges':sorted(set(changed)-CHANGED),
        'added':added,'unexpectedAdded':[p for p in added if not p.startswith(TASK+'/')],
        'pinned':pinned,'g7Count':len(g7),'g7Resurrected':resurrected,
        'files':{p:current[p] for p in changed+added},'status':status,
        'dirtyPathCount':len([s for s in status.split('\0') if s]),'auditAuthor':'root agent independent reread; no external reviewer claim'}
    result['pass']=all([result['indexUnchanged'],result['stagedDiffUnchanged'],not result['unexpectedExistingChanges'],
        not result['unexpectedAdded'],not resurrected,len(g7)==35,len(pinned)==6,
        all(s['sha256']==s['originalSha256'] for s in pinned),result['head']==before['head'],result['branch']==before['branch']])
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    out.with_suffix('.patch').write_text(''.join(patch),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['pass','indexUnchanged','changedExisting','unexpectedExistingChanges','unexpectedAdded','dirtyPathCount','g7Count']},ensure_ascii=True))
    return int(not result['pass'])


if __name__=='__main__': raise SystemExit(main())
