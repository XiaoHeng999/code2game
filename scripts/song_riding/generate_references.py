"""Generate the two image-to-3D inputs using the existing native Codex bridge."""
import concurrent.futures
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from codex_backend import CodexBackend

OUT = ROOT / 'output/game_staging/song_riding_20261124'
ASSETS = [
    ('song_horse', 'Song Horse', [0.85, 2.65, 2.05],
     'One anatomically believable strong dark chestnut Chinese riding horse, standing in a neutral square stance, all four slender legs clearly separate, all hooves on the same ground plane. Black mane and tail, subtle dark leather bridle, historically inspired dark brown leather saddle and muted crimson saddle blanket, empty saddle, absolutely no rider. Full body three-quarter view from front left, head faces toward viewer-left. Realistic premium game sculpt with elegant proportions, matte PBR materials, highly legible anatomy, visible separate ears and muzzle, no platform. Isolated on pure white background, soft even studio light, entire hooves and tail in frame. No text, no vegetation, no dramatic cast shadows.'),
    ('song_rider', 'Song Rider', [0.80, 0.90, 1.55],
     'One fictional heroic adult Chinese Song-era cavalry courier, handsome determined face, hair gathered under a small plain dark headwrap, dark iron lamellar cuirass over desaturated blue-grey tunic, ochre waist belt, worn leather boots, small crimson shoulder cloak resting close to the upper back. Historically inspired Chinese medieval clothing, not fantasy spikes, not Japanese samurai armor, no modern equipment. Seated horseback-riding posture WITHOUT horse or saddle: upright torso, knees bent down at sides and slightly apart, boots below hips, both elbows bent with hands forward loosely holding invisible reins. Full body three-quarter front view, entire boots and head in frame, physically coherent person isolated on plain white, invisible support. Detailed realistic premium game character sculpt, matte PBR surfaces, no text, no scenery, no pedestal, no weapons, no props, no horse.')
]

def generate(asset):
    aid, name, size, prompt = asset
    dest = OUT / 'asset_generation/reference_images' / (aid + '_' + name.replace(' ', '_') + '.png')
    if dest.exists():
        return {'asset_id': aid, 'path': str(dest), 'status': 'existing_not_regenerated'}
    backend = CodexBackend(OUT / 'codex/images', timeout=900)
    entry = backend.generate_image(prompt, dest)
    return dict(entry, asset_id=aid, status='succeeded')

def main():
    (OUT / 'asset_realization').mkdir(parents=True, exist_ok=True)
    if (OUT/'asset_generation/codex_image_manifest.json').is_file() and all((OUT/'asset_generation/reference_images'/(aid+'_'+name.replace(' ','_')+'.png')).is_file() for aid,name,_,_ in ASSETS):
        print('Reusing existing references and preserving original generation provenance',flush=True)
        return
    plan = {'assets': [dict(asset_id=aid, asset_name=name, asset_role='animated_character_source',
        placement_ids=[], generation_prompt_en=prompt, negative_prompt_en='background scenery, pedestal, text, extra limbs',
        expected_glb_path=f'./assets/generated_glb/song_riding_20261124/{aid}.glb',
        expected_size_meters=size, flat_base_policy='allow',
        flat_base_reason='Natural boot or hoof soles; no additional base.') for aid,name,size,prompt in ASSETS],
        'notes': ['Static generated meshes only. Rigging and animation are separate downstream operations.']}
    (OUT / 'asset_realization/asset_plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        entries = list(pool.map(generate, ASSETS))
    (OUT / 'asset_generation/codex_image_manifest.json').write_text(json.dumps({'assets':entries},ensure_ascii=False,indent=2))
    print(json.dumps(entries,ensure_ascii=False),flush=True)

if __name__ == '__main__':
    main()
