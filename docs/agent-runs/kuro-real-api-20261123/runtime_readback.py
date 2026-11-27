"""Read current formal backend inventory and verify the launcher-pinned signed renderer."""
from live import *
import urllib.request,re
sys.path.insert(0,str(ROOT))
from kuro_launcher.qt_web_release import RELEASE_PIN, VerifiedOwnerBundle
def main():
    uri='http://127.0.0.1:23456/launcher/tool-inventory'
    with urllib.request.urlopen(urllib.request.Request(uri,data=b'{}',headers={'Content-Type':'application/json'}),timeout=10) as f:
        status=f.status; inventory=json.load(f)
    section=yaml.safe_load((RT/'conf.launcher_runtime.yaml').read_text(encoding='utf8'))['character_config']
    saved=section['agent_config']['llm_configs']['openai_llm']['model']
    folder=ROOT/'assets/qt-owner'/RELEASE_PIN.fingerprint
    bundle=VerifiedOwnerBundle.load(folder,RELEASE_PIN)
    lineage=json.loads((folder/'owner-build.json').read_text(encoding='utf8'))['lineage']['sources']
    ui=ROOT/'devtools/original-git-web-host-20261010/frontend'
    comparisons={}
    for name in ('src/owner-presentation.ts','src/owner-presentation.css','src/work-panel/main.ts'):
        raw=(ui/name).read_bytes()
        actual=hashlib.sha256(raw).hexdigest()
        normalized=hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()
        comparisons[name]={'signed':lineage.get(name),'workspace':actual,'workspace_lf':normalized,
                           'matches':lineage.get(name) in (actual,normalized)}
    script=b'\n'.join(v for k,v in bundle.assets.items() if k.endswith('.js'))
    logs=sorted((ROOT/'launcher_logs/launcher-qt').rglob('*combined.log'),key=lambda p:p.stat().st_mtime,reverse=True)
    matches=re.findall(r'llm_model:\s*(gpt-[\w.-]+)',logs[0].read_text('utf8',errors='replace')) if logs else []
    save('production-readback.json',{'time':now(),'method':'POST','url':uri,'http':status,'ok':inventory['ok'],
        'session_sha256':sha(inventory['client_uid']),'config_model':saved,'role':section['conf_uid'],
        'latest_launcher_log_model':matches[-1] if matches else None,'loaded_policy_digest':inventory['policy_digest'],
        'disk_policy_digest':ToolPolicy.load_default().digest,
        'services':{k:{**v,'callable':sum(r['allowed'] for r in inventory['tools'] if r['service']==k)} for k,v in inventory['services'].items()},
        'verified_disk_pin':RELEASE_PIN.fingerprint,'verified_manifest':RELEASE_PIN.manifest_sha256,
        'renderer_sources':comparisons,'compiled_js_contains_call_summary':b'call_summary' in script,
        'new_tool_page_source_contains_call_summary':b'call_summary' in (ui/'src/owner-presentation.ts').read_bytes(),
        'gui_gesture_readback':False})
if __name__=='__main__':main()
