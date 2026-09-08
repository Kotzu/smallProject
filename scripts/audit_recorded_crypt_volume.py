"""Bounded offline evaluation only; no client or input connection."""
from pathlib import Path
import json
import time
from hashlib import sha256

from perfect_assassin.adapter.wmo_bundle import load_wmo_bundle
from perfect_assassin.adapter.wmo_swept_volume import evaluate_wmo_sweep
from perfect_assassin.movement.world_pack_runtime import load_world_pack_runtime_profile
from perfect_assassin.movement.world_structure_index import load_world_structure_index
from perfect_assassin.runtime_paths import external_runtime_root

def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "data/runtime/operator/crypt-summary-index-repeat"
    t = time.perf_counter()
    binding = load_world_pack_runtime_profile(
        root/'config/navigation/world-pack-runtime-tbc243-azeroth-full-v3.json',
        store_root=external_runtime_root(root)/'worldpacks',
        profile_schema_path=root/'contracts/world-pack-runtime-profile.schema.json',
        pack_schema_path=root/'contracts/standalone-world-pack.schema.json',
        catalog_schema_path=root/'contracts/client-world-catalog.schema.json')
    index = load_world_structure_index(
        root/'data/runtime/client-catalog/tbc243-8606/azeroth-full-v3-world-structure-index-v1.json',
        pack=binding.pack, schema_path=root/'contracts/world-structure-index.schema.json')
    bundle = load_wmo_bundle(root/'data/runtime/wmo-bundles/azeroth-wmo-observer-v1',
        expected_sha256='a92d925975dcfeb86cd1cd73baa831a8f136eb957bbadd9b86efc70623f61bbd',
        pack=binding.pack,index=index)
    print('verified_load_seconds',round(time.perf_counter()-t,3),flush=True)
    path=root/'data/runtime/navigation-f3b/results/navmesh-roaming-ebd340cd-ba97-4a5b-a726-40246ce9d0eb.json'
    raw=path.read_bytes()
    run=json.loads(raw)
    frames={a['frame_index']:a for a in run['actions'] if a['kind']=='CONTINUOUS_FRAME'}
    records=[]
    for i in range(64,96):
        pair=[frames[i],frames[i+1]]
        points=[(a['decision_observation']['world_x'],a['decision_observation']['world_y'],
                 a['projected_z_world']) for a in pair]
        t=time.perf_counter()
        result=evaluate_wmo_sweep(bundle,map_id=0,start=points[0],stop=points[1],radius_yards=.389,height_yards=2)
        record={'run_id':run['run_id'],'result_sha256':sha256(raw).hexdigest(),
                'frame_pair':[i,i+1],
                'decision_observed_monotonic_s':[a['decision_observation']['observed_monotonic_s'] for a in pair],
                'z_source':[a['projected_z_source'] for a in pair],
                'elapsed_s':time.perf_counter()-t,'evaluation':result}
        records.append(record)
        print(i,round(record['elapsed_s'],3),{k:round(v['minimum_separation_yards'],6) if v['minimum_separation_yards'] is not None else None for k,v in result['distances'].items()},flush=True)
    (output/'swept-volume-evidence.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    worst = min(records,key=lambda r:r['evaluation']['distances']['steep']['minimum_separation_yards'])
    sensitivity=[]
    for dz,radius,height in ((-.25,.389,2),(.25,.389,2),(0,.489,2.2)):
        first=worst['evaluation']['start_foot_xyz']
        last=worst['evaluation']['stop_foot_xyz']
        result=evaluate_wmo_sweep(bundle,map_id=0,
            start=(first[0],first[1],first[2]+dz),stop=(last[0],last[1],last[2]+dz),
            radius_yards=radius,height_yards=height)
        sensitivity.append({'frame_pair':worst['frame_pair'],'z_offset_yards':dz,
                            'status':'ILLUSTRATIVE_NOT_CALIBRATED_ERROR_BOUND','evaluation':result})
        print('sensitivity',worst['frame_pair'],dz,radius,height,
            result['distances']['steep']['minimum_separation_yards'],flush=True)
    (output/'swept-volume-sensitivity.json').write_text(json.dumps(sensitivity,indent=2),encoding='utf-8')


if __name__ == "__main__":
    main()
