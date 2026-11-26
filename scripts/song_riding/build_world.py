"""Build an exportable Song-inspired valley; background Blender, original scene read-only."""
import argparse
import json
import math
from pathlib import Path
import random
import sys
import bpy
import numpy as np
from mathutils import Vector, noise

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/game_staging/song_riding_20261124'
PACKAGE = OUT / 'ue_export'
SOURCE = Path('/home/zjh/project/blender/zhaogouqiao/output/v4/zhaogouqiao_detail_v4.blend')
random.seed(741)

def material(name, color, rough=.85, metallic=0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color,1)
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*color,1)
    p.inputs['Roughness'].default_value = rough
    p.inputs['Metallic'].default_value = metallic
    return m

def mesh(name, verts, faces, mat):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    if mat: obj.data.materials.append(mat)
    return obj

def cube(name, loc, scale, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if mat: obj.data.materials.append(mat)
    return obj

def beam(name, a,b,r,mat, vertices=8):
    delta=Vector(b)-Vector(a)
    bpy.ops.mesh.primitive_cone_add(vertices=vertices,radius1=r,radius2=r*.85,depth=delta.length,location=(Vector(a)+Vector(b))/2)
    o=bpy.context.object; o.name=name
    o.rotation_euler=delta.to_track_quat('Z','Y').to_euler()
    o.data.materials.append(mat)
    return o

def road_y(x):
    return 70*math.sin(x/170)*(1-math.exp(-(x/55)**2))

def road_z(x):
    return 2.4+0.00018*x*x+3.5*(1-math.exp(-(x/95)**2))

def height(x,y):
    # River is intentionally lower than the two banks; the bridge is the crossing.
    distance=max(0,abs(y-road_y(x))-6)
    bank=1-math.exp(-(abs(x)/15)**4)
    corridor=math.exp(-(distance/23)**2)
    hills=(16+12*noise.noise_vector(Vector((x/110,y/110,.8)))[0])*(1-corridor)
    edge=85*(abs(y)/430)**2.2 + 20*(abs(x)/620)**3
    river_fade=1-math.exp(-(abs(x)/65)**2)
    return -2.2 + bank*(road_z(x)+2.2)+river_fade*(hills+edge*(1-corridor))

def textured_ground(mat):
    """Bake an authored Blender noise shader to portable UV base color."""
    nodes=mat.node_tree.nodes; links=mat.node_tree.links
    tex=nodes.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=7;tex.inputs['Detail'].default_value=5
    coord=nodes.new('ShaderNodeTexCoord');links.new(coord.outputs['UV'],tex.inputs['Vector'])
    ramp=nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position=.15;ramp.color_ramp.elements[0].color=(.055,.085,.025,1)
    ramp.color_ramp.elements[1].position=.85;ramp.color_ramp.elements[1].color=(.28,.30,.12,1)
    links.new(tex.outputs['Fac'],ramp.inputs[0]);links.new(ramp.outputs['Color'],nodes['Principled BSDF'].inputs['Base Color'])
    image=bpy.data.images.new('T_Meadow_BaseColor',1024,1024)
    target=nodes.new('ShaderNodeTexImage');target.image=image;nodes.active=target
    bpy.ops.mesh.primitive_plane_add(size=2)
    plane=bpy.context.object;plane.data.materials.append(mat)
    scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=1
    scene.render.bake.use_pass_direct=False;scene.render.bake.use_pass_indirect=False;scene.render.bake.use_pass_color=True
    bpy.ops.object.bake(type='DIFFUSE')
    image.filepath_raw=str(PACKAGE/'Textures/T_Meadow_BaseColor.png');image.file_format='PNG';image.save()
    bpy.data.objects.remove(plane,do_unlink=True)
    links.new(target.outputs['Color'],nodes['Principled BSDF'].inputs['Base Color'])
    return mat

def pine_geometry(x,y,z,h,index,bark,needles):
    vs=[];fs=[];mi=[]
    def rod(a,b,r,material_index):
        a,b=Vector(a),Vector(b);axis=(b-a).normalized();u=axis.cross(Vector((0,1,.01))).normalized();v=axis.cross(u)
        k=len(vs)
        for c,rr in [(a,r),(b,r*.5)]:
            for j in range(6):vs.append(tuple(c+rr*(math.cos(j*math.tau/6)*u+math.sin(j*math.tau/6)*v)))
        for j in range(6):fs.append((k+j,k+(j+1)%6,k+(j+1)%6+6,k+j+6));mi.append(material_index)
    rod((x,y,z),(x,y,z+h),h*.024,0)
    for j in range(26):
        frac=.28+.69*j/26;angle=j*2.399+index
        reach=h*(.28*(1-frac)+.055)*random.uniform(.8,1.2)
        start=Vector((x,y,z+h*frac));end=start+Vector((reach*math.cos(angle),reach*math.sin(angle),h*.04))
        rod(start,end,h*.008*(1-frac),0)
        for k in range(45):
            t=random.uniform(.25,1.12)
            c=start.lerp(end,t)+Vector((random.gauss(0,reach*.18),random.gauss(0,reach*.18),random.gauss(0,h*.028)))
            yaw=random.random()*math.tau;l=h*random.uniform(.025,.055);w=l*.32
            d=Vector((math.cos(yaw),math.sin(yaw),random.uniform(-.3,.4)))
            cross=Vector((-d.y,d.x,0));p=len(vs)
            vs.extend([tuple(c-d*l),tuple(c+cross*w),tuple(c+d*l),tuple(c-cross*w)])
            fs.append((p,p+1,p+2,p+3));mi.append(1+(j+k)%len(needles))
    obj=mesh('NaturalPine',vs,fs,None)
    for m in [bark]+needles:obj.data.materials.append(m)
    for p,i in zip(obj.data.polygons,mi):p.material_index=i
    return obj

def join(objects,name):
    objects=[o for o in objects if o.type=='MESH']
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:o.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]
    bpy.ops.object.join()
    obj=bpy.context.object; obj.name=name
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    return obj

def camera(loc,target,lens=40):
    bpy.ops.object.camera_add(location=loc)
    o=bpy.context.object; o.name='OverviewCamera'
    o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
    o.data.lens=lens; o.data.clip_end=10000
    bpy.context.scene.camera=o
    return o

def pavilion(x,y,levels=1):
    z=height(x,y)
    objs=[cube('PavilionStone', (x,y,z+.45),(13,11,.9),stone)]
    for level in range(levels):
        base=z+.9+level*6
        width=12-level*2
        depth=10-level*1.5
        for dx in [-width*.36,width*.36]:
            for dy in [-depth*.36,depth*.36]:
                objs.append(beam('RedPillar',(x+dx,y+dy,base),(x+dx,y+dy,base+4.3),.28,red))
        for dy in [-depth*.36,depth*.36]:
            objs.append(cube('Lintel',(x,y+dy,base+3.9),(width,.35,.48),wood))
        # Curved pitched eaves, not an ornamental cone.
        for side in [-1,1]:
            vs=[];fs=[]
            for i in range(25):
                xx=-width/2+width*i/24
                for j in range(9):
                    t=j/8
                    zz=base+6-2.2*t+.75*t**4+.32*(abs(xx)/(width/2))**5
                    vs.append((x+xx,y+side*depth*.58*t,zz))
            for i in range(24):
                for j in range(8):
                    k=i*9+j;fs.append((k,k+9,k+10,k+1))
            objs.append(mesh('SweptTileRoof',vs,fs,roof))
            for i in range(25):
                xx=-width/2+width*i/24
                for j in range(4):
                    a=j/4;b=(j+1)/4
                    def p(t): return (x+xx,y+side*depth*.58*t,base+6-2.2*t+.75*t**4+.32*(abs(xx)/(width/2))**5+.05)
                    objs.append(beam('TileSeam',p(a),p(b),.055,roofedge,6))
        objs.append(beam('RoofRidge',(x-width*.53,y,base+6.1),(x+width*.53,y,base+6.1),.16,roofedge))
    return objs

def export_fbx(obj, path, extra=()):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    for o in extra:o.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH'},
        apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',axis_forward='-Y',axis_up='Z',
        bake_anim=False, use_mesh_modifiers=True, path_mode='COPY',embed_textures=True)

def main():
    global stone,red,wood,roof,roofedge
    PACKAGE.mkdir(parents=True,exist_ok=True)
    (PACKAGE/'StaticMeshes').mkdir(exist_ok=True)
    (PACKAGE/'Textures').mkdir(exist_ok=True)
    (OUT/'previews').mkdir(exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
    stone=material('M_Stone',(.32,.34,.31))
    red=material('M_OxideRed',(.23,.045,.028))
    wood=material('M_Timber',(.13,.065,.027))
    roof=material('M_GreyTile',(.065,.105,.11))
    roofedge=material('M_TileEdge',(.12,.16,.15))
    grass=[material('M_Meadow_%d'%i,(.14+i*.013,.19+i*.012,.065+i*.008)) for i in range(6)]
    ground=textured_ground(material('M_Ground',(.18,.23,.08)))
    rock=[material('M_Mountain_%d'%i,(.20+i*.022,.25+i*.023,.23+i*.022)) for i in range(5)]
    roadmat=material('M_EarthRoad',(.32,.255,.16))
    water=material('M_River',(.035,.17,.18),.2,.25)
    # Reuse only the actual modeled bridge, with a documented scalar PBR approximation.
    with bpy.data.libraries.load(str(SOURCE),link=False) as (src,dst):
        dst.objects=[n for n in src.objects if n.startswith('Bridge')]
    bridgeparts=[]
    for o in dst.objects:
        if o and o.type=='MESH':
            scene.collection.objects.link(o)
            o.location.x*=3;o.location.y*=3;o.location.z*=1.5
            o.scale.x*=3;o.scale.y*=3;o.scale.z*=1.5
            o.data.materials.clear();o.data.materials.append(stone)
            bridgeparts.append(o)
    bridge=join(bridgeparts,'SM_Bridge')
    static=[bridge]
    # Surface samples retain the real arched deck instead of substituting a flat crossing.
    samples=[]
    for i in range(101):
        x=-21+i*.42
        hit,point,normal,index=bridge.ray_cast(Vector((x,0,80)),Vector((0,0,-1)))
        if hit:samples.append([x,float(point.z)])
    fitted=np.polyfit([p[0] for p in samples if abs(p[0])<19], [p[1] for p in samples if abs(p[0])<19],2)
    def deck(x):
        if abs(x)<19:return float(np.polyval(fitted,x))+.20
        t=min(1,(abs(x)-19)/7)
        return (float(np.polyval(fitted,math.copysign(19,x)))+.20)*(1-t)+(height(math.copysign(26,x),road_y(math.copysign(26,x)))+.075)*t
    # Smooth riding deck repairs meter-scale steps in the enlarged source abutments.
    vs=[];fs=[]
    for i in range(131):
        x=-26+52*i/130
        for y in [-4.04,4.04]:vs.append((x,y,deck(x)))
    for i in range(130):
        k=i*2;fs.append((k,k+2,k+3,k+1))
    static.append(mesh('SM_BridgeDeck',vs,fs,stone))
    # Two terrain tiles preserve the river gap and modest export size.
    for side in [-1,1]:
        vs=[];fs=[];nx=121;ny=161
        for i in range(nx):
            x=side*600*i/(nx-1)
            for j in range(ny):
                y=-400+800*j/(ny-1);vs.append((x,y,height(x,y)))
        for i in range(nx-1):
            for j in range(ny-1):
                k=i*ny+j
                f=(k,k+ny,k+ny+1,k+1)
                fs.append(f if side==1 else tuple(reversed(f)))
        obj=mesh('SM_Terrain_'+('East' if side==1 else 'West'),vs,fs,None)
        obj.data.materials.append(ground)
        uv=obj.data.uv_layers.new(name='UVMap')
        for poly in obj.data.polygons:
            poly.use_smooth=True
            for li in poly.loop_indices:
                co=obj.data.vertices[obj.data.loops[li].vertex_index].co
                uv.data[li].uv=(co.x/80,co.y/80)
        static.append(obj)
    # Ribbon road, split at actual bridge abutments.
    for side in [-1,1]:
        vs=[];fs=[]
        for i in range(241):
            x=side*(26+(520-26)*i/240)
            for d in [-4.3,4.3]:
                y=road_y(x)+d;vs.append((x,y,height(x,y)+.075))
        for i in range(240):
            k=i*2;f=(k,k+2,k+3,k+1);fs.append(f if side==1 else tuple(reversed(f)))
        static.append(mesh('SM_Road_'+str(side),vs,fs,roadmat))
    static.append(mesh('SM_River',[(-10,-420,0),(10,-420,0),(10,420,0),(-10,420,0)],[(0,1,2,3)],water))
    # Distant layered ridges are geometry, not a concept-art backdrop.
    for idx,(yc,zc) in enumerate([(550,160),(830,260),(1200,400),(-700,190)]):
        vs=[];fs=[];nx=101;ny=21
        for i in range(nx):
            x=-1600+i*32
            peak=zc*(.65+.30*math.sin(i*.31+idx)+.18*math.cos(i*.67)+.09*math.sin(i*1.73))
            for j in range(ny):
                t=j/(ny-1)
                y=yc+(t-.5)*400
                z=-10+peak*math.sin(math.pi*t)**.75+38*noise.noise_vector(Vector((x/65,y/65,idx)))[2]*math.sin(math.pi*t)
                vs.append((x,y,z))
        for i in range(nx-1):
            for j in range(ny-1):
                k=i*ny+j;fs.append((k,k+ny,k+ny+1,k+1))
        ob=mesh('SM_DistantRidge_%d'%idx,vs,fs,rock[idx])
        for p in ob.data.polygons:p.use_smooth=True
        static.append(ob)
    architecture=[]
    for x,dy,levels in [(-440,19,1),(-100,30,1),(220,35,1),(470,25,3)]:
        architecture.extend(pavilion(x,road_y(x)+dy,levels))
    static.append(join(architecture,'SM_Stations'))
    # Pines: reusable mesh instances during construction, merged for portable FBX.
    bark=material('M_PineBark',(.12,.07,.035))
    needles=[material('M_Pine_%d'%i,(.025+i*.014,.085+i*.019,.052+i*.008)) for i in range(4)]
    trees=[]
    for i in range(420):
        x=random.uniform(-550,550);y=random.uniform(-310,340)
        if abs(x)<23 or abs(y-road_y(x))<16 or math.hypot(x-75,y+110)<40:continue
        z=height(x,y);h=random.uniform(9,21)
        trees.append(pine_geometry(x,y,z,h,i,bark,needles))
    static.append(join(trees,'SM_PineForest'))
    # Milestones, red pennants and low boulders establish road scale.
    props=[]
    for i,x in enumerate(range(-480,501,40)):
        if abs(x)<30:continue
        y=road_y(x)+7;z=height(x,y)
        props.append(cube('Milestone',(x,y,z+.7),(.5,.5,1.4),stone))
        if i%3==0:
            props.append(beam('BannerPole',(x,y,z),(x,y,z+6),.08,wood))
            props.append(mesh('CourierPennant',[(x,y,z+5.8),(x+2.5,y+.1,z+5.4),(x,y,z+3.8)],[(0,1,2)],red))
    static.append(join(props,'SM_RoadMarkers'))
    scene.world=bpy.data.worlds.new('MountainMorning');scene.world.use_nodes=True
    sky=scene.world.node_tree.nodes.new('ShaderNodeTexSky');sky.sky_type='NISHITA';sky.sun_disc=False
    sky.sun_elevation=math.radians(20);sky.sun_rotation=math.radians(130);sky.air_density=1.1;sky.dust_density=1.8
    scene.world.node_tree.links.new(sky.outputs[0],scene.world.node_tree.nodes['Background'].inputs[0])
    scene.world.node_tree.nodes['Background'].inputs[1].default_value=.25
    bpy.ops.object.light_add(type='SUN',location=(100,-200,300))
    sun=bpy.context.object;sun.name='MorningSun';sun.rotation_euler=(math.radians(58),math.radians(-25),math.radians(-35));sun.data.energy=2.5;sun.data.color=(1,.79,.52);sun.data.angle=math.radians(4)
    fogmat=bpy.data.materials.new('PreviewAtmosphere');fogmat.use_nodes=True
    nodes=fogmat.node_tree.nodes;nodes.clear();out=nodes.new('ShaderNodeOutputMaterial');vol=nodes.new('ShaderNodeVolumePrincipled')
    vol.inputs['Density'].default_value=.00065;vol.inputs['Color'].default_value=(.62,.73,.8,1);vol.inputs['Anisotropy'].default_value=.25
    fogmat.node_tree.links.new(vol.outputs['Volume'],out.inputs['Volume'])
    cube('PreviewFogVolume',(0,400,220),(3600,3600,900),fogmat)
    camera((75,-110,48),(0,160,55),30)
    scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
    scene.render.resolution_x=1600;scene.render.resolution_y=900;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX'
    scene.render.fps=30
    # Collision proxies: each bridge strip is convex; terrain needs complex-as-simple.
    collisions=[]
    for i in range(60):
        x=-26+52*(i+.5)/60
        o=cube('UCX_SM_Bridge_%02d'%i,(x,0,deck(x)-.20),(.90,8.1,.4),None)
        # The surface follows the local deck tangent.
        slope=(deck(x+.42)-deck(x-.42))/.84
        o.rotation_euler.y=-math.atan(slope)
        collisions.append(o)
    for side in [-1,1]:
        for i in range(30):
            x=-20+40*(i+.5)/30
            o=cube('UCX_SM_Bridge_Rail_%s_%02d'%(side,i),(x,side*4.6,deck(x)+.55),(1.5,.65,1.1),None)
            collisions.append(o)
    for o in collisions:o.hide_render=True
    manifest={'schema_version':1,'units':'meters','blender_axes':'X forward / Y left / Z up',
        'ue_position_conversion':'[x*100, -y*100, z*100] centimeters; reflection handled on export/import',
        'fbx_export_axes':{'forward':'-Y','up':'Z','apply_scale_options':'FBX_SCALE_UNITS'},
        'source_bridge':str(SOURCE),'bridge_scale_xyz':[3,3,1.5],
        'material_note':'Bridge procedural shaders simplified to scalar PBR; ground procedural color baked to UV texture. No automatic shader equivalence to UE.',
        'lighting_intent':{'sun_elevation_degrees':20,'sun_color':[1,.79,.52],'atmospheric_fog':'blue-grey distance haze; recreate with UE SkyAtmosphere and ExponentialHeightFog, Blender volume not exported'},
        'meshes':[],'ue_import_tested':False}
    for obj in static:
        filename='StaticMeshes/'+obj.name+'.fbx'
        export_fbx(obj,PACKAGE/filename,collisions if obj==bridge else ())
        manifest['meshes'].append({'id':obj.name,'file':filename,'vertices':len(obj.data.vertices),
            'faces':len(obj.data.polygons),'transform':'baked world-space; place actor at origin',
            'collision':'UCX' if obj==bridge else ('complex_as_simple' if 'Terrain' in obj.name or 'Road_' in obj.name else 'none'),
            'materials':[m.name for m in obj.data.materials]})
    for o in collisions:o.hide_set(True)
    route=[]
    for i in range(501):
        x=-460+940*i/500
        y=0 if abs(x)<26 else road_y(x)
        z=deck(x) if abs(x)<26 else height(x,y)+.08
        route.append([x,y,z])
    checkpoints=[]
    for name,x in [('bridge_east',27),('river_milestone',125),('hill_pavilion',225),('summit_station',470)]:
        checkpoints.append({'id':name,'position_m':[x,road_y(x),height(x,road_y(x))], 'radius_m':7,'kind':'finish' if x==470 else 'checkpoint'})
    config={'status':'authored_not_UE_executed','spawn_m':route[0],'heading_blender_degrees':0,
        'route_samples_m':route,'checkpoints':checkpoints,'ordered':True,
        'speed_mps':{'walk':1.8,'trot':4,'gallop':8},'stamina':{'max':100,'drain_per_second':20,'restore_per_second':10,'unlock_at':25},
        'world_extent_m':[1200,800],'water_hazard':{'center_x':0,'half_width_m':10,'bridge_exception_x':[-22,22],'bridge_exception_y':[-4,4]},
        'runtime_required':['input controller','collision configuration','camera sweep','animation blending','ordered trigger logic','stamina and restart']}
    (PACKAGE/'world_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    (PACKAGE/'gameplay_config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2))
    (OUT/'bridge_deck_samples.json').write_text(json.dumps(samples))
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'world.blend'))
    scene.render.filepath=str(OUT/'previews/world_overview.png');bpy.ops.render.render(write_still=True)
    cam=scene.camera;cam.location=(-200,-110,53);cam.rotation_euler=(Vector((150,130,85))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=28
    scene.render.filepath=str(OUT/'previews/valley_route.png');bpy.ops.render.render(write_still=True)
    print('WORLD_DONE',flush=True)

if __name__=='__main__':main()
