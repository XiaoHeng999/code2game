"""Optional UE5 Editor Python asset importer. Authored here, NOT executed in UE.

Enable Python Editor Script Plugin and Editor Scripting Utilities, then execute
this copy inside the exported package with UE's Tools > Execute Python Script.
Uses the legacy FBX factory; no level or runtime gameplay is created.
"""
import json
from pathlib import Path
import unreal

ROOT=Path(__file__).resolve().parent
DEST='/Game/SongRiding'

def import_file(path,folder,kind,skeleton=None):
    options=unreal.FbxImportUI()
    options.set_editor_property('automated_import_should_detect_type',False)
    options.set_editor_property('import_materials',kind!='animation')
    options.set_editor_property('import_textures',kind!='animation')
    options.set_editor_property('import_animations',kind=='animation')
    options.set_editor_property('import_mesh',kind!='animation')
    options.set_editor_property('import_as_skeletal',kind!='static')
    if kind=='static':
        options.set_editor_property('mesh_type_to_import',unreal.FBXImportType.FBXIT_STATIC_MESH)
        data=options.get_editor_property('static_mesh_import_data')
        data.set_editor_property('combine_meshes',True)
        data.set_editor_property('auto_generate_collision',False)
        data.set_editor_property('generate_lightmap_u_vs',True)
    else:
        options.set_editor_property('mesh_type_to_import',unreal.FBXImportType.FBXIT_ANIMATION if kind=='animation' else unreal.FBXImportType.FBXIT_SKELETAL_MESH)
        if skeleton:options.set_editor_property('skeleton',skeleton)
        data=options.get_editor_property('anim_sequence_import_data' if kind=='animation' else 'skeletal_mesh_import_data')
    data.set_editor_property('convert_scene',True)
    data.set_editor_property('convert_scene_unit',True)
    data.set_editor_property('force_front_x_axis',False)
    task=unreal.AssetImportTask()
    task.set_editor_property('filename',str(path))
    task.set_editor_property('destination_path',DEST+'/'+folder)
    task.set_editor_property('destination_name',path.stem)
    task.set_editor_property('automated',True)
    task.set_editor_property('replace_existing',False)
    task.set_editor_property('save',True)
    task.set_editor_property('factory',unreal.FbxFactory())
    task.set_editor_property('options',options)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    paths=list(task.get_editor_property('imported_object_paths'))
    if not paths:raise RuntimeError('No imported assets: '+str(path))
    return [unreal.load_asset(p) for p in paths]

def main():
    if unreal.EditorAssetLibrary.does_directory_exist(DEST):
        raise RuntimeError(DEST+' already exists. Change DEST to a new folder before rerunning; this script does not overwrite assets.')
    world=json.loads((ROOT/'world_manifest.json').read_text(encoding='utf-8'))
    for entry in world['meshes']:
        assets=import_file(ROOT/entry['file'],'StaticMeshes','static')
        if entry['collision']=='complex_as_simple':
            for asset in assets:
                if isinstance(asset,unreal.StaticMesh):
                    setup=asset.get_editor_property('body_setup')
                    if not setup:raise RuntimeError('Missing BodySetup: '+asset.get_name())
                    setup.set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
                    unreal.EditorAssetLibrary.save_loaded_asset(asset)
    assets=import_file(ROOT/'SkeletalMeshes/SK_SongMount.fbx','Characters','skeletal')
    meshes=[a for a in assets if isinstance(a,unreal.SkeletalMesh)]
    if len(meshes)!=1:raise RuntimeError('Expected one combined skeletal mesh')
    skeleton=meshes[0].get_editor_property('skeleton')
    for path in sorted((ROOT/'Animations').glob('*.fbx')):import_file(path,'Animations','animation',skeleton)
    # The separate horse/rider are alternatives, not additional characters to spawn.
    unreal.log('SongRiding assets imported. Next: assemble static meshes at origin, verify scale/axes, reconstruct PBR channels, create controller/AnimBP/triggers. No playable level has been created.')

if __name__=='__main__':main()
