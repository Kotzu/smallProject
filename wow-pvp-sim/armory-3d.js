/* Experimental Classic 1.12 character renderer for the Blizzard-style Armory.
 * Combat does not depend on this file. If WebGL/CDN/API loading fails, the audited
 * paperdoll remains fully functional and the CSS silhouette stays visible.
 */
(function(){
  const MODULE_URL='https://esm.sh/classic-wow-model-viewer@0.1.0?bundle&target=es2022';
  const ASSET_CDN='https://cdn.jsdelivr.net/gh/JollyGrin/wow-model-viewer@main/public';
  const ITEM_API='https://chronicleclassic.com/api/v1/internal/gamedata/display/item';
  const TEXTURE_REGION_DIRS=['ArmUpperTexture','ArmLowerTexture','HandTexture','TorsoUpperTexture','TorsoLowerTexture','LegUpperTexture','LegLowerTexture','FootTexture'];
  const states=new Map();
  let libPromise=null;

  const style=document.createElement('style');
  style.textContent=`
    .armory-model-3d{position:absolute;inset:0;z-index:3;opacity:0;transition:opacity .24s ease;pointer-events:auto}
    .paperdoll-model.model3d-ready .armory-model-3d{opacity:1}
    .paperdoll-model.model3d-ready .paperdoll-character{opacity:0;pointer-events:none}
    .armory-model-3d canvas{display:block;width:100%!important;height:100%!important;outline:none}
    .armory-3d-state{position:absolute;z-index:7;left:50%;top:10px;transform:translateX(-50%);max-width:90%;padding:4px 7px;border:1px solid rgba(175,137,78,.36);border-radius:999px;background:rgba(4,7,10,.72);color:#a99e91;font-size:7.5px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;white-space:nowrap;pointer-events:none;overflow:hidden;text-overflow:ellipsis}
    .paperdoll-model.model3d-ready .armory-3d-state{color:#7fd5a1;border-color:rgba(77,166,111,.38)}
    .armory-3d-gender{position:absolute;z-index:8;right:8px;top:8px;display:flex;gap:3px}
    .armory-3d-gender button{appearance:none;border:1px solid #51432f;border-radius:4px;background:#0b1015;color:#857b70;font:800 8px system-ui;padding:4px 6px;cursor:pointer}
    .armory-3d-gender button.active{border-color:#aa7f43;color:#f0c97f;background:#241a0f}
    @media(max-width:760px){.armory-model-3d{pointer-events:none}.armory-3d-gender{pointer-events:auto}.armory-3d-state{top:7px}}
  `;
  document.head.appendChild(style);

  function loadLib(){
    if(!libPromise)libPromise=import(MODULE_URL);
    return libPromise;
  }
  function slugify(filename){return String(filename||'').replace(/\.\w+$/,'').toLowerCase().replace(/_/g,'-');}
  function texBase(idx,name){return `/item-textures/${TEXTURE_REGION_DIRS[idx]}/${String(name).replace(/\.blp$/i,'')}`;}
  function invTypeToSlot(t){
    if([13,15,17,21,25,26].includes(t))return 'weapon';
    if([14,22,23].includes(t))return 'offhand';
    if(t===1)return 'head'; if(t===3)return 'shoulder'; if(t===5||t===20)return 'chest';
    if(t===7)return 'legs'; if(t===8)return 'feet'; if(t===10)return 'hands'; return null;
  }
  async function getItem(id){
    const r=await fetch(`${ITEM_API}/${id}`,{mode:'cors'});if(!r.ok)throw new Error(`item ${id}: HTTP ${r.status}`);return r.json();
  }
  function buildEquipment(equipped){
    const eq={},armor={};
    const w=equipped.weapon;
    if(w?.model_name?.[0]){const slug=slugify(w.model_name[0]);eq.weapon={path:`/items/weapon/${slug}`,texture:w.model_texture?.[0]?`/items/weapon/${slug}/textures/${slugify(w.model_texture[0])}.tex`:undefined};}
    const oh=equipped.offhand;
    if(oh?.model_name?.[0]){const dir=oh.inventory_type===14?'shield':'weapon',slug=slugify(oh.model_name[0]);eq.offhand={path:`/items/${dir}/${slug}`,texture:oh.model_texture?.[0]?`/items/${dir}/${slug}/textures/${slugify(oh.model_texture[0])}.tex`:undefined};}
    const head=equipped.head;
    if(head?.model_name?.[0]){armor.helmet=slugify(head.model_name[0]);if(head.geoset_vis_id?.[0]||head.geoset_vis_id?.[1])armor.helmetGeosetVisID=[head.geoset_vis_id[0],head.geoset_vis_id[1]];if(head.model_texture?.[0])armor.helmetTexture=slugify(head.model_texture[0]);}
    const shoulder=equipped.shoulder;
    if(shoulder?.model_name?.[0]){armor.shoulderSlug=slugify(shoulder.model_name[0].replace(/^[LR]Shoulder_/i,''));armor.shoulderHasRight=true;if(shoulder.model_texture?.[0])armor.shoulderTexture=slugify(shoulder.model_texture[0]);}
    const chest=equipped.chest;
    if(chest){const tex=chest.texture||[],gg=chest.geoset_group||[];if(tex[0])armor.armUpperBase=texBase(0,tex[0]);if(tex[3])armor.torsoUpperBase=texBase(3,tex[3]);if(tex[4])armor.torsoLowerBase=texBase(4,tex[4]);if(gg[0]>0)armor.sleeveGeoset=gg[0]+1;if(gg[2]>0)armor.robeGeoset=gg[2]+1;if(armor.robeGeoset){if(tex[5])armor.legUpperBase=texBase(5,tex[5]);if(tex[6])armor.legLowerBase=texBase(6,tex[6]);if(tex[1])armor.armLowerBase=texBase(1,tex[1]);}}
    const legs=equipped.legs;
    if(legs&&!armor.robeGeoset){const tex=legs.texture||[],gg=legs.geoset_group||[];if(tex[5])armor.legUpperBase=texBase(5,tex[5]);if(tex[6])armor.legLowerBase=texBase(6,tex[6]);if(gg[2]>0)armor.robeGeoset=gg[2]+1;}
    const feet=equipped.feet;
    if(feet){const tex=feet.texture||[],gg=feet.geoset_group||[];if(tex[7])armor.footBase=texBase(7,tex[7]);if(gg[0]>0)armor.footGeoset=gg[0]+1;if(!armor.robeGeoset&&tex[6])armor.legLowerBase=texBase(6,tex[6]);}
    const hands=equipped.hands;
    if(hands){const tex=hands.texture||[],gg=hands.geoset_group||[];if(tex[2])armor.handBase=texBase(2,tex[2]);if(gg[0]>0)armor.handGeoset=gg[0]+1;if(tex[1])armor.armLowerBase=texBase(1,tex[1]);if(!armor.robeGeoset&&gg[1]>0)armor.wristGeoset=gg[1]+1;}
    if(Object.keys(armor).length)eq.armor=armor;
    return eq;
  }
  function uiConfig(prefix){
    const q=id=>document.getElementById(id)?.value;
    return {class:q(prefix+'c'),race:q(prefix+'r'),spec:q(prefix+'s'),gear:q(prefix+'g'),build:q(prefix+'build')};
  }
  function raceSlug(race){return race==='Undead'?'scourge':String(race||'human').toLowerCase().replace(/\s+/g,'-');}
  function renderableIds(cfg){
    const slots=window.WOW_ARMORY?.armoryFor?.(cfg)||[];
    const wanted=new Set(['Head','Shoulder','Chest','Hands','Legs','Feet','Main Hand','Off Hand']);
    return slots.filter(x=>x.id&&wanted.has(x.slot)).map(x=>x.id);
  }
  function signature(cfg,gender){return [cfg.race,cfg.class,cfg.build,cfg.gear,gender,...renderableIds(cfg)].join('|');}
  function ensureUi(panel,prefix){
    const model=panel.querySelector('.paperdoll-model');if(!model)return null;
    let mount=model.querySelector('.armory-model-3d');if(!mount){mount=document.createElement('div');mount.className='armory-model-3d';model.appendChild(mount);}
    let state=model.querySelector('.armory-3d-state');if(!state){state=document.createElement('div');state.className='armory-3d-state';state.textContent='3D · loading';model.appendChild(state);}
    let controls=model.querySelector('.armory-3d-gender');
    if(!controls){controls=document.createElement('div');controls.className='armory-3d-gender';controls.innerHTML='<button data-gender="male">M</button><button data-gender="female">F</button>';model.appendChild(controls);controls.addEventListener('click',e=>{const b=e.target.closest('button[data-gender]');if(!b)return;localStorage.setItem(`wow-armory-${prefix}-gender`,b.dataset.gender);mountPanel(prefix,true);});}
    return {model,mount,state,controls};
  }
  async function mountPanel(prefix,force=false){
    const panel=document.getElementById(prefix+'Armory');if(!panel?.querySelector('.blizzard-armory'))return;
    const cfg=uiConfig(prefix);if(!window.WOW_ARMORY?.armoryFor?.(cfg))return;
    const gender=localStorage.getItem(`wow-armory-${prefix}-gender`)||'male';
    const sig=signature(cfg,gender),previous=states.get(prefix);
    if(!force&&previous?.signature===sig&&panel.querySelector('.model3d-ready'))return;
    try{previous?.viewer?.dispose?.();}catch(_e){}
    const ui=ensureUi(panel,prefix);if(!ui)return;
    ui.model.classList.remove('model3d-ready');ui.state.textContent='3D · loading';ui.mount.innerHTML='';
    ui.controls.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.gender===gender));
    states.set(prefix,{signature:sig,viewer:null});
    try{
      const {ModelViewer,createCdnResolver}=await loadLib();
      const viewer=new ModelViewer({container:ui.mount,assets:createCdnResolver(ASSET_CDN),backgroundColor:0x0b0f14});
      states.set(prefix,{signature:sig,viewer});
      await viewer.loadCharacter(raceSlug(cfg.race),gender);
      let ok=0,total=0;const equipped={};
      for(const id of renderableIds(cfg)){
        total++;
        try{const item=await getItem(id),slot=invTypeToSlot(item.inventory_type);if(slot){equipped[slot]=item;ok++;}}catch(err){console.warn('[Armory3D] item lookup failed',id,err);}
      }
      const eq=buildEquipment(equipped);if(Object.keys(eq).length)await viewer.equip(eq);
      try{viewer.playAnimationByName('Stand');}catch(_e){}
      ui.model.classList.add('model3d-ready');ui.state.textContent=`3D Classic · ${ok}/${total} visual slots`;
    }catch(err){
      console.warn('[Armory3D] fallback active',err);
      const reason=String(err?.message||err||'unknown').replace(/\s+/g,' ').slice(0,72);
      ui.state.textContent=`3D fallback · ${reason}`;ui.state.title=String(err?.stack||err||'');ui.model.classList.remove('model3d-ready');
    }
  }
  function mountAll(){mountPanel('a');mountPanel('b');}
  let timer=0;
  const observer=new MutationObserver(()=>{clearTimeout(timer);timer=setTimeout(mountAll,80);});
  const start=()=>{const app=document.querySelector('.app')||document.body;observer.observe(app,{childList:true,subtree:true});mountAll();};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
  window.WOW_ARMORY_3D={mountAll,mountPanel,version:'0.2-classic-renderer-debug'};
})();
