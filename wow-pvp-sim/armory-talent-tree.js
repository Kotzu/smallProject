(function(){
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const mode=()=>$('rulesetMode')?.value||'classic';
  function cfg(p){return{class:$(p+'c')?.value,spec:$(p+'s')?.value,build:$(p+'build')?.value||null};}
  function iconUrl(icon){return icon?`https://wow.zamimg.com/images/wow/icons/medium/${encodeURIComponent(icon)}.jpg`:'';}
  function talentTooltip(n){
    const desc=Object.entries(n.descriptions||{}).map(([r,t])=>`<div><b>Rank ${esc(r)}/${n.maxRank}</b> · ${esc(t)}</div>`).join('');
    const req=(n.requires||[]).length?`<div class="att-req">Prerequisite: ${n.requires.map(x=>`#${esc(x.id)} ${esc(x.qty)}/${esc(x.qty)}`).join(', ')}</div>`:'';
    const cost=(n.cost||[]).length?`<div class="att-cost">${n.cost.map(esc).join(' · ')}</div>`:'';
    const text=n.requiresText?`<div class="att-req">${esc(n.requiresText)}</div>`:'';
    return `<div class="att-tooltip"><strong>${esc(n.name)}</strong><span>Talent #${esc(n.id)} · ${n.maxRank} rank${n.maxRank===1?'':'s'}</span>${cost}${desc}${req}${text}</div>`;
  }
  function foreverTreeHtml(className,selectedSpec){
    const F=window.WOW_FOREVER_TALENTS;
    if(!F||F.status==='loading')return '<div class="att-loading">Loading current Forever talents…</div>';
    if(F.status==='error')return `<div class="att-error">Forever talent dataset unavailable: ${esc(F.error)}</div>`;
    const info=F.classInfo(className);if(!info)return '<div class="att-error">No Forever talent data for this class.</div>';
    const trees=Object.entries(info.treeIds||{});
    return `<div class="att-forever-head"><div><b>WoW Forever · ${esc(className)}</b><span>Current Wowhead db ${esc(F.db)} · PROVISIONAL until beta datamining</span></div><div class="att-lock">FIGHT LOCKED</div></div><div class="att-tree-grid">${trees.map(([name,id])=>{
      const nodes=F.treeById(id),active=String(name).toLowerCase()===String(selectedSpec||'').toLowerCase();
      return `<section class="att-tree ${active?'active':''}"><header><b>${esc(name)}</b><span>0 / 51 · ${nodes.length} talents</span></header><div class="att-node-grid">${nodes.map(n=>`<div class="att-node" style="--row:${n.row+1};--col:${n.col+1}"><div class="att-node-icon"><img src="${iconUrl(n.icon)}" alt="" loading="lazy"><span>0/${n.maxRank}</span></div><small>${esc(n.name)}</small>${talentTooltip(n)}</div>`).join('')}</div></section>`;
    }).join('')}</div><div class="att-provenance">Exact tree/name/rank/tooltip data is loaded from the current Wowhead Forever calculator at runtime. No Classic build is auto-converted to Forever.</div>`;
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
    const s=cfg(p);box.innerHTML=`<div class="att-title"><span>TALENT TREE</span><b>${p==='a'?'PLAYER A':'PLAYER B'} · ${esc(mode()==='forever'?'Forever':'Classic')}</b></div>${mode()==='forever'?foreverTreeHtml(s.class,s.spec):classicTreeHtml(p)}`;
  }
  function render(){injectOne('a');injectOne('b');}
  document.addEventListener('wow-forever-talents-ready',render);
  ['ac','as','abuild','bc','bs','bbuild','rulesetMode'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(render,20)));
  const obs=new MutationObserver(()=>{clearTimeout(obs._t);obs._t=setTimeout(render,50);});
  const start=()=>{obs.observe(document.querySelector('.app')||document.body,{childList:true,subtree:true});render();};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
  window.WOW_ARMORY_TALENTS={render,version:'0.30-forever-live-tree'};
})();
