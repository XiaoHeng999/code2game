import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/game_staging/song_riding_20261124'

def main():
    names=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else ['song_horse','song_rider']
    for name in names:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(ROOT/'assets/generated_glb/song_riding_20261124'/f'{name}.glb'))
        objs=[o for o in bpy.context.scene.objects if o.type=='MESH']
        pts=[o.matrix_world@v.co for o in objs for v in o.data.vertices]
        lo=Vector([min(p[i] for p in pts) for i in range(3)]);hi=Vector([max(p[i] for p in pts) for i in range(3)])
        print(name,'BOUNDS',list(lo),list(hi),flush=True)
        center=(lo+hi)/2;size=max(hi-lo)
        top=[p for p in pts if p.z>lo.z+.82*(hi.z-lo.z)]
        print('TOP_CENTER',list(sum(top,Vector())/len(top)),flush=True)
        scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=16;scene.cycles.use_denoising=True
        scene.render.resolution_x=768;scene.render.resolution_y=768;scene.render.resolution_percentage=100
        scene.world=bpy.data.worlds.new('Studio');scene.world.use_nodes=True
        scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.65,.65,.65,1)
        scene.world.node_tree.nodes['Background'].inputs[1].default_value=.6
        for offset,power in [((2,-3,4),400),((-3,-1,2),250)]:
            bpy.ops.object.light_add(type='AREA',location=center+Vector(offset)*size)
            light=bpy.context.object;light.data.energy=power*size*size;light.data.size=3*size
            light.rotation_euler=(center-light.location).to_track_quat('-Z','Y').to_euler()
        bpy.ops.object.camera_add();cam=bpy.context.object;scene.camera=cam;cam.data.lens=48
        for view,offset in [('front',(0,-3.2,.7)),('side',(3.2,0,.7)),('three_quarter',(2.6,-3.1,1.4))]:
            cam.location=center+Vector(offset)*size;cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler()
            scene.render.filepath=str(OUT/'previews'/f'{name}_{view}.png');bpy.ops.render.render(write_still=True)

if __name__=='__main__':main()
