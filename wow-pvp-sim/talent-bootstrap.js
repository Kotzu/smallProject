(()=>{
  const T=window.WOW_TALENTS;if(!T)return;
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  if(!document.querySelector('link[href="talents.css"]')){const l=document.createElement('link');l.rel='stylesheet';l.href='talents.css?v=016';document.head.appendChild(l);}

  function addBuildSelect(p){
    if($(p+'build'))return;
    const grid=$(p+'g')?.closest('.field-grid');if(!grid)return;
    const label=document.createElement('label');label.innerHTML=`Talent build<select id="${p}build"></select>`;grid.appendChild(label);
  }
  addBuildSelect('a');addBuildSelect('b');

  const tabs=document.querySelector('.tabs'),combatBtn=tabs?.querySelector('[data-tab="combat"]');
  if(tabs&&!tabs.querySelector('[data-tab="talents"]')){
    const btn=document.createElement('button');btn.dataset.tab='talents';btn.textContent='Talents';tabs.insertBefore(btn,combatBtn||null);
    btn.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.classList.toggle('active',x===btn));document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.id==='talents'));};
  }
  if(!$('talents')){
    const sec=document.createElement('section');sec.id='talents';sec.className='tab card';
    sec.innerHTML='<div class="combat-head"><div><h2>Talent Builds</h2><div class="muted">Build-ul selectat este parte din configurația duelului. Un build neverificat blochează Fight-ul.</div></div><div class="badge ok">BUILD STRICT MODE</div></div><div class="talent-grid"><article id="aTalentPanel" class="talent-panel"></article><article id="bTalentPanel" class="talent-panel"></article></div><div class="note">Momentan sunt active numai build-urile calibrate. Alte build-uri devin selectabile numai după verificarea talentelor și a modificatorilor numerici.</div>';
    const combat=$('combat');combat?.parentElement.insertBefore(sec,combat);
  }

  function player(p){return{class:$(p+'c')?.value,spec:$(p+'s')?.value,race:$(p+'r')?.value,gear:$(p+'g')?.value,build:$(p+'build')?.value||null};}
  function refreshSelect(p){
    const el=$(p+'build');if(!el)return;
    const s=player(p),ids=T.idsFor(s.class,s.spec),prev=el.value;
    if(!ids.length){el.innerHTML='<option value="">LOCKED — no verified build</option>';el.disabled=true;}else{el.disabled=false;el.innerHTML=ids.map(id=>{const b=T.get(id);return `<option value="${esc(id)}">${esc(b.name)} · ${esc(b.points)}</option>`;}).join('');el.value=ids.includes(prev)?prev:ids[0];}
    renderPanel(p);
  }
  function renderPanel(p){
    const root=$(p+'TalentPanel');if(!root)return;
    const s=player(p),a=T.auditSelection(s);
    if(!a.pass){root.innerHTML=`<div class="talent-locked"><b>TALENT BUILD: ${esc(a.status)}</b><span>${esc(a.reason)}</span></div>`;return;}
    const b=a.build;
    root.innerHTML=`<div class="talent-head"><div><h3>${esc(b.name)}</h3><span>${esc(b.class)} ${esc(b.spec)} · ${esc(b.points)} · ${T.pointTotal(b.points)} points</span></div><div class="audit-badge pass">BUILD AUDIT: PASS</div></div><div class="talent-role">${esc(b.role||'PvP build')}</div><div class="talent-effects">${(b.combatTalents||[]).map(t=>`<div><b>${esc(t.name)} <span>${esc(t.rank)}</span></b><p>${esc(t.effect)}</p></div>`).join('')}</div><div class="talent-links"><a href="${esc(b.calculatorUrl)}" target="_blank" rel="noreferrer">Open talent calculator</a><code>${esc(b.calculator||'')}</code></div>`;
    const fightLabel=p==='a'?document.querySelector('#fight .fighter:first-child .sub'):document.querySelector('#fight .fighter:last-child .sub');
    if(fightLabel)fightLabel.textContent=`${s.spec} · ${b.name} · ${b.points}`;
  }
  function refreshAll(){refreshSelect('a');refreshSelect('b');}
  ['ac','as','ar','ag'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(()=>refreshSelect('a'),0)));
  ['bc','bs','br','bg'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(()=>refreshSelect('b'),0)));
  $('abuild')?.addEventListener('change',()=>{$('ag')?.dispatchEvent(new Event('change'));renderPanel('a');});
  $('bbuild')?.addEventListener('change',()=>{$('bg')?.dispatchEvent(new Event('change'));renderPanel('b');});

  const hero=document.querySelector('.hero p');if(hero)hero.textContent='v0.16 · ClassCombat.lua per class · verified talent builds · talent-aware post-fight analysis';
  const metrics=document.querySelector('.metrics');if(metrics&&!metrics.textContent.includes('Talent builds')){const m=document.createElement('div');m.className='metric';m.innerHTML='<span>Talent builds</span><b class="green">2 verified</b>';metrics.appendChild(m);}
  refreshAll();
  window.WOW_TALENT_UI={refreshAll,renderPanel,version:'0.16'};
})();
