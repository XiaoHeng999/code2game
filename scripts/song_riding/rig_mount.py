"""Fit generated meshes, author an in-place prototype rig and bake four gait clips."""
import json
import math
from pathlib import Path
import sys
import bpy
import numpy as np
from mathutils import Vector, Matrix

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/game_staging/song_riding_20261124'
PACKAGE=OUT/'ue_export'

def import_mesh(name,height,angle):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.import_scene.gltf(filepath=str(ROOT/'assets/generated_glb/song_riding_20261124'/f'{name}.glb'))
    meshes=[o for o in bpy.context.selected_objects if o.type=='MESH']
    bpy.context.view_layer.objects.active=meshes[0]
    for o in list(bpy.context.selected_objects):o.select_set(o in meshes)
    bpy.ops.object.join();obj=bpy.context.object;obj.name='SK_'+name
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    coords=np.array([v.co[:] for v in obj.data.vertices]);lo=coords.min(0);hi=coords.max(0)
    coords-=[(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]]
    coords*=height/(hi[2]-lo[2])
    c,s=math.cos(angle),math.sin(angle);coords[:,:2]=coords[:,:2]@np.array([[c,s],[-s,c]])
    for v,co in zip(obj.data.vertices,coords):v.co=co
    obj.data.update()
    return obj,coords

def segment_distance(points,a,b):
    a=np.array(a);b=np.array(b);d=b-a
    t=np.clip(((points-a)@d)/float(d@d),0,1)
    return np.linalg.norm(points-a-t[:,None]*d,axis=1)

def weight(obj,coords,bones,kind,legs):
    groups={name:obj.vertex_groups.new(name=name) for name in bones}
    # Local anatomical partitions prevent a hind leg binding to the adjacent foreleg.
    names=[n for n in bones if (n.startswith('rider_') if kind=='rider' else not n.startswith('rider_')) and n not in ('root','saddle')]
    dist=np.stack([segment_distance(coords,*bones[n][:2]) for n in names],axis=1)
    if kind=='horse':
        for k,n in enumerate(names):
            if any(n.startswith(l) for l in legs):
                dist[:,k]+=np.maximum(0,coords[:,2]-1.15)*5
            elif n in ('body','neck','head'):
                dist[:,k]+=np.maximum(0,.8-coords[:,2])*4
        # Opposite-side leg groups must not pull each other's hooves.
        for k,n in enumerate(names):
            if '_L_' in n:dist[:,k]+=np.maximum(0,-coords[:,1]) * 8
            if '_R_' in n:dist[:,k]+=np.maximum(0,coords[:,1]) * 8
    best=np.argsort(dist,axis=1)[:,:3]
    for i,indices in enumerate(best):
        ds=dist[i,indices];ws=np.exp(-(ds-ds.min())/.065);ws/=ws.sum()
        for idx,w in zip(indices,ws):
            if w>.005:groups[names[idx]].add([i],float(w),'REPLACE')
    modifier=obj.modifiers.new('Skin','ARMATURE');modifier.object=rig
    obj.parent=rig

def fbx(path,objects,animation=False):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:o.select_set(True)
    bpy.context.view_layer.objects.active=rig
    bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'ARMATURE','MESH'},
        axis_forward='-Y',axis_up='Z',apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',
        add_leaf_bones=False,use_armature_deform_only=True,armature_nodetype='NULL',
        bake_anim=animation,bake_anim_use_nla_strips=False,bake_anim_use_all_actions=False,
        bake_anim_force_startend_keying=True,bake_anim_step=1,bake_anim_simplify_factor=0,
        path_mode='COPY',embed_textures=True)

def set_bone(name,a,b):
    p=rig.pose.bones[name]
    rest=p.bone
    rotation=(rest.tail_local-rest.head_local).rotation_difference(Vector(b)-Vector(a)) @ rest.matrix_local.to_quaternion()
    p.matrix=Matrix.Translation(Vector(a)) @ rotation.to_matrix().to_4x4()

def add_reins(horse,seat):
    mat=bpy.data.materials.new('M_Reins');mat.diffuse_color=(.045,.024,.012,1);mat.use_nodes=True
    mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=mat.diffuse_color
    ropes=[]
    for side in [-1,1]:
        curve=bpy.data.curves.new('Rein','CURVE');curve.dimensions='3D';curve.bevel_depth=.006;curve.bevel_resolution=2
        spline=curve.splines.new('POLY');spline.points.add(20)
        a=Vector((.30,side*.24,seat+.23));b=Vector((1.10,side*.14,1.57))
        for i,p in enumerate(spline.points):
            t=i/20;c=a.lerp(b,t);c.z-=.13*math.sin(math.pi*t);p.co=(*c,1)
        o=bpy.data.objects.new('LeatherRein',curve);bpy.context.collection.objects.link(o);o.data.materials.append(mat)
        bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o;bpy.ops.object.convert(target='MESH')
        o=bpy.context.object;g=o.vertex_groups.new(name='body');g.add(list(range(len(o.data.vertices))),1,'REPLACE');ropes.append(o)
    bpy.ops.object.select_all(action='DESELECT')
    for o in [horse]+ropes:o.select_set(True)
    bpy.context.view_layer.objects.active=horse;bpy.ops.object.join()

def render(path,loc,target,res=(1280,900)):
    scene=bpy.context.scene
    cam=scene.camera;cam.location=loc;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
    scene.render.resolution_x=res[0];scene.render.resolution_y=res[1];scene.render.resolution_percentage=100
    scene.render.filepath=str(path);bpy.ops.render.render(write_still=True)

def main():
    global rig
    for d in ['SkeletalMeshes','Animations','Textures']:(PACKAGE/d).mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1;scene.render.fps=30
    horse,hc=import_mesh('song_horse',2.05,math.pi)
    rider,rc=import_mesh('song_rider',1.55,math.pi/2)
    # The saddle surface is located from the actual generated mesh, not the requested size.
    back=hc[(abs(hc[:,0]+.12)<.13)&(abs(hc[:,1])<.10)&(hc[:,2]>.9)]
    seat=float(np.quantile(back[:,2],.90)) if len(back) else 1.36
    rider_shift=np.array([-.12,0,seat-.72])
    rc+=rider_shift
    for v,co in zip(rider.data.vertices,rc):v.co=co
    rider.data.update()
    footpoints=hc[hc[:,2]<.15]
    legs={}
    for front in [True,False]:
        for side in [1,-1]:
            pts=footpoints[(footpoints[:,0]>0 if front else footpoints[:,0]<0)&(footpoints[:,1]*side>0)]
            if len(pts)<3:raise RuntimeError('Cannot identify four separate horse hoof regions')
            foot=np.median(pts,axis=0);foot[2]=.10
            name=('fore' if front else 'hind')+('_L' if side>0 else '_R')
            hip=np.array([foot[0]-.03 if front else foot[0]+.08,foot[1],1.22 if front else 1.27])
            knee=(hip+foot)/2;knee[0]+=.13 if front else -.18
            legs[name]={'hip':hip,'knee':knee,'foot':foot,'front':front,'side':side}
    bones={'root':((0,0,0),(0,0,.25),None),
        'body':((-.5,0,1.25),(.5,0,1.25),'root'),
        'neck':((.45,0,1.3),(.80,0,1.8),'body'),
        'head':((.80,0,1.8),(1.17,0,1.65),'neck'),
        'tail':((-.85,0,1.35),(-1.12,0,.55),'body'),
        'saddle':((-.12,0,seat),(-.12,0,seat+.15),'body')}
    for n,l in legs.items():
        bones[n+'_upper']=(l['hip'],l['knee'],'body')
        bones[n+'_lower']=(l['knee'],l['foot'],n+'_upper')
        bones[n+'_hoof']=(l['foot'],l['foot']+np.array([.12,0,-.07]),n+'_lower')
    z=rider_shift[2]
    bones.update({'rider_pelvis':((-.12,0,z+.72),(-.12,0,z+.86),'saddle'),
        'rider_spine':((-.12,0,z+.86),(-.16,0,z+1.22),'rider_pelvis'),
        'rider_head':((-.16,0,z+1.22),(-.18,0,z+1.53),'rider_spine')})
    for sign,label in [(1,'L'),(-1,'R')]:
        bones['rider_arm_'+label]=((-.12,sign*.2,z+1.16),(.05,sign*.29,z+.95),'rider_spine')
        bones['rider_hand_'+label]=((.05,sign*.29,z+.95),(.35,sign*.27,z+.93),'rider_arm_'+label)
        bones['rider_thigh_'+label]=((-.12,sign*.16,z+.72),(.24,sign*.28,z+.51),'rider_pelvis')
        bones['rider_shin_'+label]=((.24,sign*.28,z+.51),(.29,sign*.32,z+.08),'rider_thigh_'+label)
    data=bpy.data.armatures.new('SongMountSkeleton');rig=bpy.data.objects.new('SongMountRig',data);scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
    for name,(a,b,parent) in bones.items():
        e=data.edit_bones.new(name);e.head=a;e.tail=b
        if parent:e.parent=data.edit_bones[parent]
        e.use_deform=True
    bpy.ops.object.mode_set(mode='OBJECT')
    weight(horse,hc,bones,'horse',legs);weight(rider,rc,bones,'rider',legs)
    add_reins(horse,seat)
    # Extract all GLB textures into the portable package; FBX also embeds these files.
    textures=[]
    for i,img in enumerate(list(bpy.data.images)):
        if img.type!='IMAGE' or not img.size[0]:continue
        # GLB packed images load lazily; has_data=False does not mean missing texture.
        _=img.pixels[0]
        path=PACKAGE/'Textures'/f'T_Character_{i:02d}.png'
        img.filepath_raw=str(path);img.file_format='PNG';img.save();textures.append({'image':img.name,'file':'Textures/'+path.name,'colorspace':img.colorspace_settings.name})
    material_map=[]
    for obj in [horse,rider]:
        for mat in obj.data.materials:
            material_map.append({'mesh':obj.name,'material':mat.name,
                'images':[{'image':n.image.name,'file':'Textures/'+Path(n.image.filepath_raw).name} for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.image],
                'note':'Base Color sRGB; metallic-roughness packed image uses G=roughness, B=metallic. Rebuild this channel mapping in UE if FBX loses it.'})
    fbx(PACKAGE/'SkeletalMeshes/SK_SongMount.fbx',[rig,horse,rider])
    fbx(PACKAGE/'SkeletalMeshes/SK_Horse.fbx',[rig,horse])
    fbx(PACKAGE/'SkeletalMeshes/SK_Rider.fbx',[rig,rider])
    actions={};validation=[]
    for gait,frames,stride,lift in [('Idle',60,0,0),('Walk',48,.24,.07),('Trot',30,.34,.13),('Gallop',24,.45,.20)]:
        action=bpy.data.actions.new('A_'+gait);action.use_fake_user=True
        rig.animation_data_create();rig.animation_data.action=action
        scene.frame_start=1;scene.frame_end=frames+1
        for f in range(1,frames+2):
            scene.frame_set(f);phase=(f-1)/frames;theta=math.tau*phase
            for p in rig.pose.bones:p.matrix_basis=Matrix.Identity(4);p.rotation_mode='QUATERNION'
            bodybob=(.008 if gait=='Idle' else .018 if gait=='Walk' else .035)*math.sin(theta*2)
            # Local Y of the horizontal body bone is world X; local Z remains vertical.
            rig.pose.bones['body'].location.z=bodybob
            bpy.context.view_layer.update()
            for n,l in legs.items():
                offsets={'fore_L':0,'hind_R':.5,'fore_R':.5,'hind_L':0} if gait=='Trot' else (
                    {'fore_L':0,'fore_R':.12,'hind_L':.5,'hind_R':.62} if gait=='Gallop' else
                    {'fore_L':0,'hind_R':.25,'fore_R':.5,'hind_L':.75})
                t=(phase+offsets[n])%1
                hip=l['hip'].copy();hip[2]+=bodybob
                foot=l['foot'].copy()
                if stride:
                    stance=.58
                    if t<stance:foot[0]+=stride*(.5-t/stance)
                    else:
                        swing=(t-stance)/(1-stance);foot[0]+=stride*(-.5+swing)
                        foot[2]+=lift*math.sin(math.pi*swing)
                a=np.linalg.norm(l['knee']-l['hip']);b=np.linalg.norm(l['foot']-l['knee'])
                delta=foot-hip;d=np.linalg.norm(delta);u=delta/d
                d=min(d,a+b-.0001);along=(a*a-b*b+d*d)/(2*d)
                perpendicular=np.array([-u[2],0,u[0]]);perpendicular/=np.linalg.norm(perpendicular)
                knee=hip+u*along+perpendicular*math.sqrt(max(0,a*a-along*along))*(1 if l['front'] else -1)
                set_bone(n+'_upper',hip,knee);bpy.context.view_layer.update()
                set_bone(n+'_lower',knee,foot);bpy.context.view_layer.update()
                set_bone(n+'_hoof',foot,foot+np.array([.12,0,-.07]))
            for p in rig.pose.bones:
                p.keyframe_insert('location',frame=f,group=p.name)
                p.keyframe_insert('rotation_quaternion',frame=f,group=p.name)
            bpy.context.view_layer.update()
        actions[gait]=action
        fbx(PACKAGE/'Animations'/f'A_{gait}.fbx',[rig],True)
        # Actual evaluated bone transforms at the cycle endpoints, not key counts alone.
        scene.frame_set(1);start={p.name:p.matrix.copy() for p in rig.pose.bones}
        scene.frame_set(frames+1);delta=max(abs(p.matrix[i][j]-start[p.name][i][j]) for p in rig.pose.bones for i in range(4) for j in range(4))
        validation.append({'clip':gait,'frames':[1,frames+1],'fps':30,'duration_seconds':frames/30,'cycle_endpoint_matrix_max_error':delta,'in_place_root':list(rig.pose.bones['root'].location)})
    rig.animation_data.action=actions['Idle'];scene.frame_start=1;scene.frame_end=61;scene.frame_set(1)
    scene.world=bpy.data.worlds.new('Studio');scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.22,.25,.28,1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value=.6
    for loc,power,size in [((3,-4,6),900,5),((-3,-2,4),600,4),((0,4,5),800,3)]:
        bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=power;l.data.shape='DISK';l.data.size=size
        l.rotation_euler=(Vector((0,0,1.1))-l.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.object.camera_add(location=(4,-5,2.7));scene.camera=bpy.context.object;scene.camera.data.lens=52
    scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
    scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX'
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'mount_rig.blend'))
    report={'status':'prototype_authored_and_exported','rigging':'anatomical region + distance skinning; no manual production retopology',
        'animation':'procedural two-link leg trajectories, baked every frame; not mocap',
        'seat_height_m':seat,'rider_translation_m':rider_shift.tolist(),'horse_height_m':2.05,'rider_seated_height_m':1.55,
        'bones':{n:{'head':list(map(float,a)),'tail':list(map(float,b)),'parent':p} for n,(a,b,p) in bones.items()},
        'clips':validation,'textures':textures,'materials':material_map,'ue_import_tested':False,
        'limitations':['Generated topology and inferred skin weights require close-up review.','No control rig, facial animation, runtime foot IK or cloth simulation.','Rider and horse share skeleton; use combined asset or synchronized separate assets, not both at once.']}
    (PACKAGE/'character_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    render(OUT/'previews/mount_hero.png',(3.8,-5,2.7),(0,0,1.30))
    render(OUT/'previews/mount_side.png',(0,-6.4,1.7),(0,0,1.3))
    rig.animation_data.action=actions['Gallop'];scene.frame_end=25
    for f in [1,7,13,19]:
        scene.frame_set(f);render(OUT/'previews'/f'gallop_{f:02}.png',(0,-6.4,1.7),(0,0,1.3),(960,675))
    print('RIG_DONE',flush=True)

if __name__=='__main__':main()
