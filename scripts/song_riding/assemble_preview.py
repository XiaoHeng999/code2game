"""Assemble the deliverable .blend and render an explicitly non-interactive riding preview."""
import argparse
import bisect
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/game_staging/song_riding_20261124'
PACKAGE=OUT/'ue_export'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--video',action='store_true');parser.add_argument('--frames',type=int,default=450)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    bpy.ops.wm.open_mainfile(filepath=str(OUT/'world.blend'))
    scene=bpy.context.scene
    with bpy.data.libraries.load(str(OUT/'mount_rig.blend'),link=False) as (src,dst):
        dst.objects=[n for n in src.objects if n=='SongMountRig' or n.startswith('SK_')]
        dst.actions=[n for n in src.actions if n.startswith('A_')]
    for o in dst.objects:
        if o:scene.collection.objects.link(o)
    rig=bpy.data.objects['SongMountRig']
    rig.animation_data_clear();rig.animation_data_create()
    action=next(a for a in dst.actions if a.name.startswith('A_Gallop'))
    track=rig.animation_data.nla_tracks.new();track.name='GallopCycle'
    strip=track.strips.new('Gallop',1,action);strip.repeat=args.frames/24;strip.blend_type='REPLACE'
    config=json.loads((PACKAGE/'gameplay_config.json').read_text())
    route=config['route_samples_m'];xs=[p[0] for p in route]
    surfaces=[o for o in scene.objects if o.type=='MESH' and (o.name.startswith('SM_Bridge') or o.name.startswith('SM_Terrain') or o.name.startswith('SM_Road_'))]
    def ground(x,y):
        hits=[]
        for o in surfaces:
            h,p,n,idx=o.ray_cast(Vector((x,y,400)),Vector((0,0,-1)))
            if h:hits.append(p.z)
        if not hits:raise RuntimeError('Unsupported preview root')
        return max(hits)
    def position(x):
        idx=max(1,min(len(xs)-1,bisect.bisect_left(xs,x)));a,b=route[idx-1],route[idx];t=(x-a[0])/(b[0]-a[0])
        y=a[1]*(1-t)+b[1]*t
        return Vector((x,y,ground(x,y)+.025))
    # Travel by arc length to keep preview speed close to the authored 8 m/s.
    path=[position(-55+i*.25) for i in range(441)]
    distances=[0.]
    for a,b in zip(path,path[1:]):distances.append(distances[-1]+(b-a).length)
    actual_frames=math.ceil(distances[-1]/8*30)+1
    if not args.video:args.frames=actual_frames
    strip.repeat=args.frames/24
    scene.frame_start=1;scene.frame_end=args.frames;scene.render.fps=30
    cam=scene.camera;cam.name='RidingPreviewCamera';cam.data.lens=32
    for f in range(1,args.frames+1):
        t=(f-1)/max(1,args.frames-1);s=t*distances[-1];j=max(1,min(len(path)-1,bisect.bisect_left(distances,s)))
        frac=(s-distances[j-1])/(distances[j]-distances[j-1]);p=path[j-1].lerp(path[j],frac)
        a=position(p.x-.6);b=position(p.x+.6);delta=b-a
        yaw=math.atan2(delta.y,delta.x);pitch=math.atan2(delta.z,math.hypot(delta.x,delta.y))
        rig.location=p;rig.rotation_euler=(0,-pitch,yaw)
        rig.keyframe_insert('location',frame=f,group='PreviewRootTravel');rig.keyframe_insert('rotation_euler',frame=f,group='PreviewRootTravel')
        target=p+Vector((0,0,1.2));cam.location=p+Vector((-6.0,-3.2,3.4))
        cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
        cam.keyframe_insert('location',frame=f);cam.keyframe_insert('rotation_euler',frame=f)
    # Preview action contains root travel only; exported gait clips remain in-place.
    rig.animation_data.action.name='PreviewRootTravel_NOT_RuntimeController'
    scene.frame_set(1)
    scene.cycles.samples=12;scene.cycles.use_denoising=True
    prefs=bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type='OPTIX';prefs.get_devices()
    for d in prefs.devices:d.use=d.type=='OPTIX'
    scene.cycles.device='GPU'
    scene.render.resolution_x=1280;scene.render.resolution_y=720;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.use_persistent_data=True
    (PACKAGE/'Source').mkdir(exist_ok=True)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(PACKAGE/'Source/gaming_world.blend'))
    for label,frame in [('riding_start',1),('riding_bridge',args.frames//2),('riding_exit',args.frames)]:
        scene.frame_set(frame);scene.render.filepath=str(OUT/'previews'/f'{label}.png');bpy.ops.render.render(write_still=True)
    metadata={'kind':'Blender pre-recorded riding preview, not a playable game','frames':args.frames,'fps':30,
        'distance_m':distances[-1],'mean_speed_mps':distances[-1]/((args.frames-1)/30),
        'camera':'third-person tracking showcase','runtime_controller_implemented':False,'preview_video_fps':15,
        'note':'Procedural gait; no runtime foot IK, so sloped terrain can show foot sliding or penetration.'}
    (OUT/'preview_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    if args.video:
        folder=OUT/'previews/frames';folder.mkdir(exist_ok=True)
        scene.render.resolution_x=960;scene.render.resolution_y=540;scene.cycles.samples=8
        scene.frame_step=2
        scene.render.filepath=str(folder/'ride_');bpy.ops.render.render(animation=True)
    print('ASSEMBLY_DONE',flush=True)

if __name__=='__main__':main()
