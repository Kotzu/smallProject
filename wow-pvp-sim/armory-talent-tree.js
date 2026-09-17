(function(){
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const mode=()=>$('rulesetMode')?.value||'classic';
  function cfg(p){return{class:$(p+'c')?.value,spec:$(p+'s')?.value,build:$(p+'build')?.value||null};}
  function iconUrl(icon){return icon?`https://wow.zamimg.com/images/wow/icons/medium/${encodeURIComponent(icon)}.jpg`:'';}
  function rankDescriptions(n){
    if(Array.isArray(n.ranks)&&n.ranks.length)return n.ranks.map((r,i)=>[i+1,r.description||r.tooltip||r]);
    return Object.entries(n.descriptions||{});
  }
  function talentTooltip(n,rank){
    const desc=rankDescriptions(n).map(([r,t])=>`<div class="${Number(r)===rank?'att-current-rank':''}"><b>Rank ${esc(r)}/${n.maxRank}</b> · ${esc(typeof t==='string'?t:(t?.description||JSON.stringify(t)))}</div>`).join('');
    const req=(n.requires||[]).length?`<div class="att-req">Prerequisite: ${n.requires.map(x=>`#${esc(x.id)} rank ${esc(x.qty||1)}`).join(', ')}</div>`:'';
    const cost=(n.cost||[]).length?`<div class="att-cost">${n.cost.map(x=>esc(typeof x==='string'?x:JSON.stringify(x))).join(' · ')}</div>`:'';
    const text=n.requiresText?`<div class="att-req">${esc(n.requiresText)}</div>`:'';
    return `<div class="att-tooltip"><strong>${esc(n.name)}</strong><span>Talent #${esc(n.id)} · ${n.maxRank} rank${n.maxRank===1?'':'s'} · selected ${rank}/${n.maxRank}</span>${cost}${desc}${req}${text}</div>`;
  }
  function foreverTreeHtml(p,className,selectedSpec){
    const F=window.WOW_FOREVER_TALENTS,B=window.WOW_FOREVER_BUILDS;
    if(!F||F.status==='loading')return '<div class="att-loading">Loading current Forever talents…</div>';
    if(F.status==='error')return `<div class="att-error">Forever talent dataset unavailable: ${esc(F.error)}</div>`;
    if(!B)return '<div class="att-error">Forever build allocator unavailable.</div>';
    const info=F.classInfo(className);if(!info)return '<div class="att-error">No Forever talent data for this class.</div>';
    const trees=Object.entries(info.treeIds||{}),audit=B.audit(p,className),exported=B.exportBuild(p);
    return `<div class="att-forever-head"><div><b>WoW Forever · ${esc(className)}</b><span>Wowhead db ${esc(F.db)} · ${audit.points}/51 selected · ${audit.remaining} remaining · PROVISIONAL until beta datamining</span></div><div class="att-head-actions"><button type="button" class="att-reset" data-player="${p}">Reset</button><div class="att-lock">FIGHT LOCKED</div></div></div><div class="att-tree-grid">${trees.map(([name,id])=>{
      const nodes=F.treeById(id),active=String(name).toLowerCase()===String(selectedSpec||'').toLowerCase(),spent=B.pointsInTree(p,className,id);
      return `<section class="att-tree ${active?'active':''}"><header><b>${esc(name)}</b><span>${spent} points · ${nodes.length} talents</span></header><div class="att-node-grid">${nodes.map(n=>{
        const rank=B.rank(p,className,n.id),add=B.canAdd(p,className,n.id),remove=B.canRemove(p,className,n.id),state=rank>0?'invested':add.ok?'available':'locked';
        return `<button type="button" class="att-node ${state}" style="--row:${n.row+1};--col:${n.col+1}" data-player="${p}" data-class="${esc(className)}" data-node="${esc(n.id)}" data-can-remove="${remove.ok?'1':'0'}" aria-label="${esc(n.name)} ${rank}/${n.maxRank}"><div class="att-node-icon"><img src="${iconUrl(n.icon)}" alt="" loading="lazy"><span>${rank}/${n.maxRank}</span></div><small>${esc(n.name)}</small>${talentTooltip(n,rank)}${!add.ok&&rank===0?`<i class="att-why">${esc(add.reason)}</i>`:''}</button>`;
      }).join('')}</div></section>`;
    }).join('')}</div><div class="att-build-summary"><b>Selected build:</b> ${audit.points}/51 · ${B.selected(p,className).map(x=>`${esc(x.node.name)} ${x.rank}/${x.node.maxRank}`).join(' · ')||'No points selected yet.'}</div><div class="att-provenance">Left click/tap adds a rank. Right click or Shift+click removes a rank. Tier and prerequisite rules are enforced. Build snapshot: Wowhead Forever db ${esc(exported?.db||F.db)}. Combat remains locked until each selected effect has CombatEngine parity.</div>`;
  }
  function classicTreeHtml(p){
    const T=window.WOW_TALENTS,s=cfg(p),audit=T?.auditSelection?.(s);
    if(!audit?.pass)return '<div class="att-error">Classic build is not verified.</div>';
    const b=audit.build;
    return `<div class="att-forever-head classic"><div><b>${esc(b.name)} · ${esc(b.points)}</b><span>Classic Era calibrated build · ${esc(T.pointTotal(b.points))} points</span></div><div class="att-lock ok">${audit.kernelReady?'KERNEL ACTIVE':'KERNEL LOCKED'}</div></div><div class="att-classic-list">${(b.combatTalents||[]).map(t=>`<div><b>${esc(t.name)} <span>${esc(t.rank)}</span></b><p>${esc(t.effect)}</p></div>`).join('')}</div><div class="att-provenance">This panel shows the combat-relevant verified allocation currently carried by the simulator registry. Full visual Classic allocation remains sourced by the saved calculator code.</div>`;
  }
  function injectOne(p){
    const root=$(p+'Armory')?.querySelector('.blizzard-armory');if(!root)return;
    let box=root.querySelector('.armory-talent-tree');if(!box){box=document.createElement('section');box.className='armory-talent-tree';const integrity=root.querySelector('.armory-integrity');(integrity||root.querySelector('.armory-footnote'))?.insertAdjacentElement('beforebegin',box);}
    const s=cfg(p);box.innerHTML=`<div class="att-title"><span>TALENT TREE</span><b>${p==='a'?'PLAYER A':'PLAYER B'} · ${esc(mode()==='forever'?'Forever':'Classic')}</b></div>${mode()==='forever'?foreverTreeHtml(p,s.class,s.spec):classicTreeHtml(p)}`;
  }
  function render(){injectOne('a');injectOne('b');}
  function handleTalentClick(e){
    if(mode()!=='forever')return;
    const node=e.target.closest('.att-node');if(!node)return;
    const B=window.WOW_FOREVER_BUILDS;if(!B)return;
    e.preventDefault();
    const p=node.dataset.player,className=node.dataset.class,id=node.dataset.node;
    const result=(e.shiftKey||e.button===2)?B.remove(p,className,id):B.add(p,className,id);
    if(!result.ok){node.classList.add('att-denied');setTimeout(()=>node.classList.remove('att-denied'),220);}
    render();
  }
  function handleReset(e){const btn=e.target.closest('.att-reset');if(!btn)return;const p=btn.dataset.player,s=cfg(p);window.WOW_FOREVER_BUILDS?.clear(p,s.class);render();}
  document.addEventListener('click',e=>{handleReset(e);handleTalentClick(e);});
  document.addEventListener('contextmenu',e=>{if(e.target.closest('.att-node'))handleTalentClick(e);});
  document.addEventListener('wow-forever-talents-ready',render);
  document.addEventListener('wow-forever-build-changed',render);
  ['ac','as','abuild','bc','bs','bbuild','rulesetMode'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(render,20)));
  const obs=new MutationObserver(()=>{clearTimeout(obs._t);obs._t=setTimeout(render,50);});
  const start=()=>{obs.observe(document.querySelector('.app')||document.body,{childList:true,subtree:true});render();};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
  window.WOW_ARMORY_TALENTS={render,version:'0.31-forever-interactive-tree'};
})();
