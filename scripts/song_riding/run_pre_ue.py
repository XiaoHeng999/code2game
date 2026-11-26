"""Reproduce the dedicated pre-UE branch without changing the original pipeline."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/game_staging/song_riding_20261124'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--from-stage',type=int,choices=range(1,8),default=1)
    p.add_argument('--to-stage',type=int,choices=range(1,8),default=7)
    p.add_argument('--gpu',default='1')
    p.add_argument('--blender',default='/home/zjh/.cache/blender-video/blender-4.5.3-linux-x64/blender')
    args=p.parse_args()
    if args.from_stage>args.to_stage:p.error('from-stage must be <= to-stage')
    py=str(ROOT/'.venv/bin/python');hy=str(ROOT/'.venv-hunyuan3d/bin/python')
    def blender(file,*extra):return [args.blender,'-b','-t','12','--python-exit-code','1','--python',str(ROOT/'scripts/song_riding'/file),*extra]
    stages=[('references',[py,str(ROOT/'scripts/song_riding/generate_references.py')]),
        ('hunyuan',[hy,str(ROOT/'scripts/run_codex_pipeline.py'),'meshes','--demo','song_riding_20261124','--asset-plan',str(OUT/'asset_realization/asset_plan.json'),'--skip-existing']),
        ('world',blender('build_world.py')),('rig',blender('rig_mount.py')),('validation',blender('validate_exports.py')),
        ('preview',blender('assemble_preview.py','--','--video','--frames','450')),
        ('package',[py,str(ROOT/'scripts/song_riding/package_delivery.py')])]
    (OUT/'logs').mkdir(parents=True,exist_ok=True)
    record={'kind':'dedicated pre-UE branch','started_unix':time.time(),'UE_executed':False,'stages':[]}
    path=OUT/'logs'/f'pre_ue_run_{time.time_ns()}.json'
    env=dict(os.environ,CUDA_VISIBLE_DEVICES=args.gpu)
    for index,(name,command) in enumerate(stages,1):
        if not args.from_stage<=index<=args.to_stage:continue
        entry={'stage':index,'name':name,'command':command,'status':'running','start':time.time()}
        record['stages'].append(entry);path.write_text(json.dumps(record,ensure_ascii=False,indent=2))
        log=OUT/'logs'/f'{name}_{time.time_ns()}.log'
        print(f'[{index}/7] {name}: {log}',flush=True)
        try:
            with log.open('w') as stream:subprocess.run(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
            entry['status']='passed'
        except BaseException as exc:
            entry['status']='failed';entry['error']=str(exc);raise
        finally:
            entry['elapsed_seconds']=time.time()-entry['start'];entry['log']=str(log)
            path.write_text(json.dumps(record,ensure_ascii=False,indent=2))
    print(OUT/'ue_export/index.html',flush=True)

if __name__=='__main__':main()
