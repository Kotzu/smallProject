(function(){
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const P=()=>window.WOW_FOREVER_PRESETS;
  const presetErrors={a:null,b:null};
  function cfg(p){return{class:$(p+'c')?.value,spec:$(p+'s')?.value};}
  function iconUrl(icon){return icon?`https://wow.zamimg.com/images/wow/icons/medium/${encodeURIComponent(icon)}.jpg`:'';}
  function rankDescriptions(n){
    if(Array.isArray(n.ranks)&&n.ranks.length)return n.ranks.map((r,i)=>[i+1,r?.description||r?.tooltip||r]);
    return Object.entries(n.descriptions||{});
  }
  function talentTooltip(n,rank){
    const desc=rankDescriptions(n).map(([r,t])=>`<div class="${Number(r)===rank?'att-current-rank':''}"><b>Rank ${esc(r)}/${n.maxRank}</b> · ${esc(typeof t==='string'?t:(t?.description||JSON.stringify(t)))}</div>`).join('');
    const req=(n.requires||[]).length?`<div class="att-req">Prerequisite: ${n.requires.map(x=>`#${esc(x.id)} rank ${esc(x.qty||1)}`).join(', ')}</div>`:'';
    const cost=(n.cost||[]).length?`<div class="att-cost">${n.cost.map(x=>esc(typeof x==='string'?x:JSON.stringify(x))).join(' · ')}</div>`:'';
    const text=n.requiresText?`<div class="att-req">${esc(n.requiresText)}</div>`:'';
    return `<div class="att-tooltip"><strong>${esc(n.name)}</strong><span>Talent #${esc(n.id)} · ${n.maxRank} rank${n.maxRank===1?'':'s'} · selected ${rank}/${n.maxRank}</span>${cost}${desc}${req}${text}</div>`;
  }
  function popularity(preset){
    return P()?.popularityLabel?.(preset)||'public build';
  }
  function presetToolbar(p,className,spec){
    const api=P(),build=window.WOW_FOREVER_BUILDS?.get?.(p),presets=api?.list?.(className,spec)||[];
    if(!presets.length)return '<div class="att-preset-bar empty"><div><b>PRE-BUILDS</b><span>Niciun preset popular verificat încă pentru '+esc(className)+' '+esc(spec)+'.</span></div></div>';
    const currentId=build?.preset?.id||'';
    const status=build?.preset?.status||'CUSTOM';
    let options='<option value="">Custom / manual</option>';
    for(const x of presets)options+='<option value="'+esc(x.id)+'" '+(x.id===currentId?'selected':'')+'>'+esc(x.label)+' · '+esc(popularity(x))+'</option>';
    const current=presets.find(x=>x.id===currentId);
    const detail=current?(popularity(current)+' · public pre-release build · not a recommendation'):'manual allocation';
    const error=presetErrors[p]?'<span class="att-preset-error">'+esc(presetErrors[p])+'</span>':'';
    return '<div class="att-preset-bar"><label><b>PRE-BUILD</b><select class="att-preset-select" data-player="'+p+'" data-class="'+esc(className)+'" data-spec="'+esc(spec)+'">'+options+'</select></label><div class="att-preset-meta"><span class="'+(status==='EXACT_SOURCE'?'ok':status==='CUSTOMIZED'?'warn':'')+'">'+esc(status)+'</span><small>'+esc(detail)+'</small>'+error+'</div></div>';
  }
  function foreverTreeHtml(p,className,selectedSpec){
    const F=window.WOW_FOREVER_TALENTS,B=window.WOW_FOREVER_BUILDS;
    if(!F||F.status==='loading')return '<div class="att-loading">Loading current WoW Forever talents…</div>';
    if(F.status==='error')return `<div class="att-error">WoW Forever talent dataset unavailable: ${esc(F.error)}</div>`;
    if(!B)return '<div class="att-error">Forever build allocator unavailable.</div>';
    const info=F.classInfo(className);if(!info)return '<div class="att-error">No WoW Forever talent data for this class.</div>';
    const trees=Object.entries(info.treeIds||{}),audit=B.audit(p,className),exported=B.exportBuild(p);
    return `<div class="att-forever-head"><div><b>WoW Forever · ${esc(className)}</b><span>Wowhead db ${esc(F.db)} · ${audit.points}/51 selected · ${audit.remaining} remaining · PROVISIONAL until beta datamining</span></div><div class="att-head-actions"><button type="button" class="att-reset" data-player="${p}">Reset</button><div class="att-lock">FIGHT LOCKED</div></div></div>${presetToolbar(p,className,selectedSpec)}<div class="att-tree-grid">${trees.map(([name,id])=>{
      const nodes=F.treeById(id),active=String(name).toLowerCase()===String(selectedSpec||'').toLowerCase(),spent=B.pointsInTree(p,className,id);
      return `<section class="att-tree ${active?'active':''}"><header><b>${esc(name)}</b><span>${spent} points · ${nodes.length} talents</span></header><div class="att-node-grid">${nodes.map(n=>{
        const rank=B.rank(p,className,n.id),add=B.canAdd(p,className,n.id),remove=B.canRemove(p,className,n.id),state=rank>0?'invested':add.ok?'available':'locked';
        return `<button type="button" class="att-node ${state}" style="--row:${n.row+1};--col:${n.col+1}" data-player="${p}" data-class="${esc(className)}" data-node="${esc(n.id)}" data-can-remove="${remove.ok?'1':'0'}" aria-label="${esc(n.name)} ${rank}/${n.maxRank}"><div class="att-node-icon"><img src="${iconUrl(n.icon)}" alt="" loading="lazy"><span>${rank}/${n.maxRank}</span></div><small>${esc(n.name)}</small>${talentTooltip(n,rank)}${!add.ok&&rank===0?`<i class="att-why">${esc(add.reason)}</i>`:''}</button>`;
      }).join('')}</div></section>`;
    }).join('')}</div><div class="att-build-summary"><b>Selected Forever build:</b> ${audit.points}/51 · ${B.selected(p,className).map(x=>`${esc(x.node.name)} ${x.rank}/${x.node.maxRank}`).join(' · ')||'No points selected yet.'}</div><div class="att-provenance">Tap/click adds a rank. Right click or Shift+click removes a rank. Tier and prerequisite rules are enforced. Snapshot source: Wowhead Forever db ${esc(exported?.db||F.db)}. Combat stays locked until every selected effect has Forever CombatEngine parity.</div>`;
  }
  function injectOne(p){
    const root=$(p+'Armory')?.querySelector('.blizzard-armory');if(!root)return;
    let box=root.querySelector('.armory-talent-tree');if(!box){box=document.createElement('section');box.className='armory-talent-tree';const integrity=root.querySelector('.armory-integrity');(integrity||root.querySelector('.armory-footnote'))?.insertAdjacentElement('beforebegin',box);}
    const s=cfg(p);box.innerHTML=`<div class="att-title"><span>WOW FOREVER TALENT TREE</span><b>${p==='a'?'PLAYER A':'PLAYER B'}</b></div>${foreverTreeHtml(p,s.class,s.spec)}`;
  }
  let renderTimer=null;
  function renderPlayer(p){injectOne(p);}
  function render(){renderPlayer('a');renderPlayer('b');}
  function scheduleRender(delay=0){clearTimeout(renderTimer);renderTimer=setTimeout(render,delay);}
  function applyDefault(p,force){
    const s=cfg(p),api=P(),builds=window.WOW_FOREVER_BUILDS;
    if(!api||!builds||window.WOW_FOREVER_TALENTS?.status!=='ready')return false;
    const preset=api.defaultFor?.(s.class,s.spec);
    if(!preset){if(force)builds.clear(p,s.class);presetErrors[p]=null;return false;}
    const current=builds.get?.(p);
    if(!force&&current?.points>0)return false;
    const result=builds.applyPreset(p,preset);
    presetErrors[p]=result?.ok?null:(result?.reason||'Preset invalid');
    return !!result?.ok;
  }
  function handlePreset(e){
    const sel=e.target.closest?.('.att-preset-select');if(!sel)return;
    const p=sel.dataset.player,s=cfg(p),builds=window.WOW_FOREVER_BUILDS;if(!builds)return;
    if(!sel.value){builds.clear(p,s.class);presetErrors[p]=null;scheduleRender(0);return;}
    const result=P()?.apply?.(p,sel.value);
    presetErrors[p]=result?.ok?null:(result?.reason||'Preset could not be applied');
    scheduleRender(0);
  }
  function handleTalentClick(e){
    const node=e.target.closest('.att-node');if(!node)return;
    const B=window.WOW_FOREVER_BUILDS;if(!B)return;
    e.preventDefault();
    const p=node.dataset.player,className=node.dataset.class,id=node.dataset.node;
    const result=(e.shiftKey||e.button===2)?B.remove(p,className,id):B.add(p,className,id);
    if(!result.ok){node.classList.add('att-denied');setTimeout(()=>node.classList.remove('att-denied'),220);}
    scheduleRender(0);
  }
  function handleReset(e){const btn=e.target.closest('.att-reset');if(!btn)return;const p=btn.dataset.player,s=cfg(p);window.WOW_FOREVER_BUILDS?.clear(p,s.class);scheduleRender(0);}
  document.addEventListener('click',e=>{handleReset(e);handleTalentClick(e);});
  document.addEventListener('contextmenu',e=>{if(e.target.closest('.att-node'))handleTalentClick(e);});
  document.addEventListener('change',handlePreset);
  document.addEventListener('wow-forever-talents-ready',()=>setTimeout(()=>{applyDefault('a',false);applyDefault('b',false);scheduleRender(0);},0));
  document.addEventListener('wow-forever-build-changed',e=>{if(e.detail?.player==='a'||e.detail?.player==='b')scheduleRender(0);});
  document.addEventListener('wow-ruleset-changed',()=>scheduleRender(0));
  ['ac','as'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(()=>{applyDefault('a',true);renderPlayer('a');},0)));
  ['bc','bs'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(()=>{applyDefault('b',true);renderPlayer('b');},0)));
  const start=()=>{if(window.WOW_FOREVER_TALENTS?.status==='ready'){applyDefault('a',false);applyDefault('b',false);}scheduleRender(0);};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
  window.WOW_ARMORY_TALENTS={render:()=>scheduleRender(0),renderPlayer,applyDefault,version:'0.42-popular-presets'};
})();
