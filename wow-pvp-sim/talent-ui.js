(()=>{
  const T=window.WOW_TALENTS,F=window.WOW_FOREVER_TALENTS;
  const $=id=>document.getElementById(id);
  if(!T)return;
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const ruleset=()=>$('rulesetMode')?.value||'classic';

  function playerState(p){return{class:$(p+'c')?.value,spec:$(p+'s')?.value,race:$(p+'r')?.value,gear:$(p+'g')?.value,build:$(p+'build')?.value||null,ruleset:ruleset()};}

  function ensureRulesetUi(){
    const bar=document.querySelector('.duel-bar');
    if(bar&&!$('rulesetMode')){
      const label=document.createElement('label');
      label.className='ruleset-field';
      label.innerHTML='<span>Talent dataset</span><select id="rulesetMode"><option value="classic">Classic Era · calibrated</option><option value="forever">Forever · current pre-beta</option></select>';
      bar.insertBefore(label,bar.firstChild);
    }
    const tab=$('talents');
    if(tab&&!$('talentDatasetStatus')){
      const box=document.createElement('div');
      box.id='talentDatasetStatus';box.className='talent-dataset-status';
      const head=tab.querySelector('.combat-head');head?.insertAdjacentElement('afterend',box);
      const grid=document.createElement('div');grid.id='foreverTalentGrid';grid.className='talent-grid hidden';
      grid.innerHTML='<article id="aForeverTalentPanel" class="talent-panel"></article><article id="bForeverTalentPanel" class="talent-panel"></article>';
      const classicGrid=tab.querySelector('.talent-grid');classicGrid?.insertAdjacentElement('afterend',grid);
    }
    const hero=document.querySelector('.hero p');
    if(hero)hero.textContent='v0.28 · Forever talent snapshot updated · Classic calibrated fight kept separate · strict accuracy';
  }

  function refreshSelect(p){
    const el=$(p+'build');if(!el)return;
    const s=playerState(p),ids=T.idsFor(s.class,s.spec),previous=el.value;
    if(!ids.length){el.innerHTML='<option value="">LOCKED — no verified Classic build</option>';el.disabled=true;}
    else{
      el.innerHTML=ids.map(id=>{const b=T.get(id),suffix=b.status==='ACTIVE_CALIBRATED'?'':' · KERNEL LOCKED';return `<option value="${esc(id)}">${esc(b.name)} · ${esc(b.points)} · Classic${suffix}</option>`;}).join('');
      el.value=ids.includes(previous)?previous:T.defaultBuild(s.class,s.spec)||ids[0];
      el.disabled=ruleset()==='forever';
    }
    renderPlayer(p);
  }

  function modifierText(b){
    if(!b)return '';
    const m=b.modifiers||{},bits=[];
    if(m.meleeCritPct!=null)bits.push(`+${m.meleeCritPct}% melee crit`);
    if(m.meleeHitPct!=null)bits.push(`+${m.meleeHitPct}% melee hit`);
    if(m.eviscerateDamagePct!=null)bits.push(`Eviscerate +${m.eviscerateDamagePct}%`);
    if(m.backstabCritBonusPct!=null)bits.push(`Backstab crit +${m.backstabCritBonusPct}%`);
    if(m.opportunityDamagePct!=null)bits.push(`Backstab/Ambush +${m.opportunityDamagePct}%`);
    if(m.improvedSprint)bits.push('Sprint breaks movement impairing effects');
    if(m.frostFireHitPct!=null)bits.push(`Frost/Fire hit +${m.frostFireHitPct}%`);
    if(m.frostDamagePct!=null)bits.push(`Frost damage +${m.frostDamagePct}%`);
    if(m.frostboltCastMs!=null)bits.push(`Frostbolt ${(m.frostboltCastMs/1000).toFixed(1)}s`);
    return bits.join(' · ');
  }

  function renderClassicPlayer(p){
    const root=$(p+'TalentPanel');if(!root)return;
    const s=playerState(p),audit=T.auditSelection(s);
    if(!audit.pass){root.innerHTML=`<div class="talent-locked"><b>CLASSIC BUILD: ${esc(audit.status)}</b><span>${esc(audit.reason)}</span></div>`;return;}
    const b=audit.build,active=!!audit.kernelReady,blockers=(b.kernelBlockers||[]).map(x=>`<li>${esc(x)}</li>`).join('');
    root.innerHTML=`<div class="talent-head"><div><h3>${esc(b.name)}</h3><span>${esc(b.class)} ${esc(b.spec)} · ${esc(b.points)} · ${T.pointTotal(b.points)} points</span></div><div class="audit-badge ${active?'pass':'fail'}">${active?'CLASSIC BUILD + KERNEL: PASS':'CLASSIC BUILD VERIFIED · KERNEL LOCKED'}</div></div><div class="talent-role">Dataset: <b>Classic Era</b> · ${esc(b.role||'PvP build')}${b.weaponStyle?` · ${esc(b.weaponStyle)}`:''}</div><div class="talent-effects">${(b.combatTalents||[]).map(t=>`<div><b>${esc(t.name)} <span>${esc(t.rank)}</span></b><p>${esc(t.effect)}</p></div>`).join('')}</div><div class="talent-summary"><b>Combat modifiers:</b> ${esc(modifierText(b)||'verified by build registry')}</div>${blockers?`<div class="talent-lock-reasons"><b>Nu intră încă în Fight:</b><ul>${blockers}</ul></div>`:''}<div class="talent-links"><a href="${esc(b.calculatorUrl)}" target="_blank" rel="noreferrer">Open Classic talent calculator</a><code>${esc(b.calculator||'')}</code></div>`;
    const fightLabel=p==='a'?$('fightRogueBuild'):$('fightMageBuild');
    if(fightLabel)fightLabel.textContent=`${b.name} · ${b.points} · Classic${active?'':' · LOCKED'}`;
  }

  function namedTreeHtml(className,treeName,count){
    const nodes=F?.tree?.(className,treeName);
    if(!nodes)return `<details class="forever-tree"><summary>${esc(treeName)} · ${count} talents</summary><div class="forever-structure-only">Structura este confirmată pe Wowhead. Numele/tooltips pentru această clasă nu sunt încă importate în snapshot-ul local.</div></details>`;
    return `<details class="forever-tree" ${treeName==='Subtlety'||treeName==='Frost'?'open':''}><summary>${esc(treeName)} · ${count} talents</summary><div class="forever-node-list">${nodes.map(n=>`<div><span>${n.index+1}. ${esc(n.name)}</span><b>${n.maxRank==null?'?':n.maxRank} rank${n.maxRank===1?'':'s'}</b></div>`).join('')}</div></details>`;
  }

  function renderForeverPlayer(p){
    const root=$(p+'ForeverTalentPanel');if(!root||!F)return;
    const s=playerState(p),info=F.classInfo(s.class);
    if(!info){root.innerHTML='<div class="talent-locked"><b>FOREVER DATA MISSING</b></div>';return;}
    const trees=Object.entries(info.trees);
    root.innerHTML=`<div class="talent-head"><div><h3>${esc(s.class)} · Forever</h3><span>${trees.map(([n,c])=>`${esc(n)} ${c}`).join(' · ')} · ${F.classTotal(s.class)} nodes</span></div><div class="audit-badge fail">PRE-BETA · FIGHT LOCKED</div></div><div class="talent-role">Selected spec: <b>${esc(s.spec)}</b> · 51-point pool. Current Classic build is deliberately not re-used here.</div>${trees.map(([n,c])=>namedTreeHtml(s.class,n,c)).join('')}<div class="talent-lock-reasons"><b>Strict gate:</b> Forever Fight stays locked until a current Forever build is selected and every talent effect used by Combat.lua has engine parity.</div>`;
  }

  function renderPlayer(p){ruleset()==='forever'?renderForeverPlayer(p):renderClassicPlayer(p);}

  function renderDataset(){
    ensureRulesetUi();
    const mode=ruleset(),status=$('talentDatasetStatus'),classicGrid=$('aTalentPanel')?.parentElement,foreverGrid=$('foreverTalentGrid');
    if(status){
      if(mode==='forever')status.innerHTML=`<b>FOREVER CURRENT SNAPSHOT · ${F?.snapshotDate||'—'}</b><span>${F?.coverage?.totalNodes||'—'} talent nodes across 9 classes · pre-beta BlizzCon/stream dataset from Wowhead. Wowhead states it will be refreshed from the beta client. Fight is strict-locked; no Classic build is silently translated.</span><a href="${esc(F?.officialSource||'https://www.wowhead.com/forever/talent-calc')}" target="_blank" rel="noreferrer">Wowhead Forever calculator</a>`;
      else status.innerHTML='<b>CLASSIC ERA CALIBRATED DATASET</b><span>The current playable kernel remains Classic. Switch “Talent dataset” to Forever to inspect the updated 470-node pre-beta trees.</span>';
    }
    classicGrid?.classList.toggle('hidden',mode==='forever');
    foreverGrid?.classList.toggle('hidden',mode!=='forever');
    ['a','b'].forEach(p=>{const el=$(p+'build');if(el)el.disabled=mode==='forever'||!T.idsFor($(p+'c')?.value,$(p+'s')?.value).length;});
    if(mode==='forever'){renderForeverPlayer('a');renderForeverPlayer('b');}else{renderClassicPlayer('a');renderClassicPlayer('b');}
  }

  function refreshAll(){refreshSelect('a');refreshSelect('b');renderDataset();window.WOW_ARMORY_UI?.render?.();}
  function notifyGate(p){$(p+'g')?.dispatchEvent(new Event('change'));}

  ensureRulesetUi();
  ['ac','as','ar','ag'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(()=>{refreshSelect('a');renderDataset();},0)));
  ['bc','bs','br','bg'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(()=>{refreshSelect('b');renderDataset();},0)));
  $('abuild')?.addEventListener('change',()=>{renderPlayer('a');window.WOW_ARMORY_UI?.render?.();notifyGate('a');});
  $('bbuild')?.addEventListener('change',()=>{renderPlayer('b');window.WOW_ARMORY_UI?.render?.();notifyGate('b');});
  $('rulesetMode')?.addEventListener('change',()=>{refreshAll();notifyGate('a');notifyGate('b');});
  setTimeout(refreshAll,0);
  window.WOW_TALENT_UI={refreshAll,renderPlayer,renderDataset,version:'0.28'};
})();