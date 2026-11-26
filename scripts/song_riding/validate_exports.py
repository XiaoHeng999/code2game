"""Roundtrip all FBX files and inspect source skin/animation and riding ground."""
import json
import math
from pathlib import Path
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/game_staging/song_riding_20261124'
PACKAGE=OUT/'ue_export'

def bounds(objects):
    ps=[o.matrix_world@Vector(c) for o in objects if o.type=='MESH' for c in o.bound_box]
    return [max(p[i] for p in ps)-min(p[i] for p in ps) for i in range(3)] if ps else None

def main():
    results={'scope':'Blender FBX roundtrip and source geometry checks; NOT UE execution', 'ue_import_tested':False,'fbx':[],'failures':[]}
    bpy.ops.wm.open_mainfile(filepath=str(OUT/'mount_rig.blend'))
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    expected=bounds(meshes)
    skin=[]
    for obj in meshes:
        missing=sum(not v.groups for v in obj.data.vertices)
        sums=[sum(g.weight for g in v.groups) for v in obj.data.vertices]
        entry={'mesh':obj.name,'vertices':len(obj.data.vertices),'unweighted':missing,'max_influences':max(len(v.groups) for v in obj.data.vertices),'min_weight_sum':min(sums),'max_weight_sum':max(sums)}
        skin.append(entry)
        if missing or min(sums)<.98 or max(sums)>1.02:results['failures'].append('Invalid skin weights '+obj.name)
    results['skin']=skin
    for file in sorted(PACKAGE.rglob('*.fbx')):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        try:
            bpy.ops.import_scene.fbx(filepath=str(file),use_anim=True)
            obs=list(bpy.context.scene.objects);meshes=[o for o in obs if o.type=='MESH'];rigs=[o for o in obs if o.type=='ARMATURE']
            entry={'file':str(file.relative_to(PACKAGE)),'mesh_count':len(meshes),'vertices':sum(len(o.data.vertices) for o in meshes),
                'bounds_m':bounds(meshes),'rig_count':len(rigs),'bones':sum(len(o.data.bones) for o in rigs),
                'root_bones':[b.name for o in rigs for b in o.data.bones if not b.parent],
                'actions':[{'name':a.name,'frames':list(a.frame_range)} for a in bpy.data.actions],
                'texture_images':[{'name':i.name,'size':list(i.size),'available':bool(i.size[0])} for i in bpy.data.images if i.type=='IMAGE']}
            if file.parent.name=='Animations' and (not rigs or not entry['actions']):raise ValueError('Missing animated skeleton')
            if file.parent.name=='SkeletalMeshes':
                if not rigs or not meshes:raise ValueError('Missing skin or mesh')
                if len(entry['root_bones'])!=1:raise ValueError('Expected exactly one skeletal root')
                if not entry['texture_images'] or not all(i['available'] for i in entry['texture_images']):raise ValueError('Character textures missing on roundtrip')
                if file.stem=='SK_SongMount' and max(abs(a-b) for a,b in zip(entry['bounds_m'],expected))>.08:raise ValueError('Roundtrip bounds changed by more than 8 cm')
            if file.parent.name=='StaticMeshes' and not meshes:raise ValueError('No static mesh')
            entry['status']='passed'
        except Exception as exc:
            entry={'file':str(file.relative_to(PACKAGE)),'status':'failed','error':str(exc)};results['failures'].append(entry)
        results['fbx'].append(entry)
    # Ray tests use only actual walkable meshes, never the render-only volume.
    bpy.ops.wm.open_mainfile(filepath=str(OUT/'world.blend'))
    surface=[o for o in bpy.context.scene.objects if o.type=='MESH' and (o.name.startswith('SM_Terrain') or o.name.startswith('SM_Road_') or o.name.startswith('SM_Bridge'))]
    config=json.loads((PACKAGE/'gameplay_config.json').read_text())
    errors=[];heights=[];normals=[]
    depsgraph=bpy.context.evaluated_depsgraph_get()
    for point in config['route_samples_m']:
        hits=[]
        for obj in surface:
            evaluated=obj.evaluated_get(depsgraph)
            hit,loc,normal,face=evaluated.ray_cast(Vector((point[0],point[1],400)),Vector((0,0,-1)))
            if hit:hits.append((loc.z,normal))
        if not hits:
            errors.append({'point':point,'reason':'no supported surface'});continue
        ground,normal=max(hits,key=lambda x:x[0]);heights.append(ground);normals.append(normal)
        if abs(ground-point[2])>.4:errors.append({'point':point,'surface_height':ground,'error_m':ground-point[2]})
    grades=[]
    points=config['route_samples_m']
    for a,b in zip(points,points[1:]):
        horizontal=math.hypot(b[0]-a[0],b[1]-a[1]);grades.append(math.degrees(math.atan2(abs(b[2]-a[2]),horizontal)))
    results['route']={'samples':len(points),'support_errors':errors,'max_grade_degrees':max(grades),'length_m':sum((Vector(b)-Vector(a)).length for a,b in zip(points,points[1:])),'notes':'Centerline support only, not UE collision sweep, horse clearance or full free-roaming navigation.'}
    if errors:results['failures'].append('Route has unsupported or mismatched samples')
    if max(grades)>42:results['failures'].append('Route exceeds authored 42-degree slope limit')
    results['status']='passed' if not results['failures'] else 'failed'
    (PACKAGE/'validation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print(json.dumps({'status':results['status'],'failures':results['failures'],'route':{k:v for k,v in results['route'].items() if k!='support_errors'}},ensure_ascii=False),flush=True)
    if results['failures']:raise RuntimeError('Export validation failed; see validation.json')

if __name__=='__main__':main()
