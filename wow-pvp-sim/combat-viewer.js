(()=>{
  const $=id=>document.getElementById(id);
  const policies={
    rogue:{label:'Rogue · 3 builds',path:'combat/Rogue/ClassCombat.lua',status:'ACTIVE'},
    mage:{label:'Mage',path:'combat/Mage/ClassCombat.lua',status:'ACTIVE'},
    warrior:{label:'Warrior',path:'combat/Warrior/ClassCombat.lua',status:'LOCKED'},
    paladin:{label:'Paladin',path:'combat/Paladin/ClassCombat.lua',status:'LOCKED'},
    hunter:{label:'Hunter',path:'combat/Hunter/ClassCombat.lua',status:'LOCKED'},
    priest:{label:'Priest',path:'combat/Priest/ClassCombat.lua',status:'LOCKED'},
    shaman:{label:'Shaman',path:'combat/Shaman/ClassCombat.lua',status:'LOCKED'},
    warlock:{label:'Warlock',path:'combat/Warlock/ClassCombat.lua',status:'LOCKED'},
    druid:{label:'Druid',path:'combat/Druid/ClassCombat.lua',status:'LOCKED'},
    talents:{label:'Talent Builds',path:'combat/TalentBuilds.lua',status:'DATA'},
    engine:{label:'Combat Engine',path:'combat/CombatEngine.lua',status:'ENGINE'}
  };
  const selector=document.querySelector('.combat-selector');
  if(selector){selector.innerHTML='';Object.entries(policies).forEach(([key,p])=>{const b=document.createElement('button');b.dataset.policy=key;b.textContent=p.label+(p.status==='LOCKED'?' · locked':'');selector.appendChild(b);});}
  const esc=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  async function load(key){
    const p=policies[key];if(!p)return;
    document.querySelectorAll('.combat-selector button').forEach(b=>b.classList.toggle('active',b.dataset.policy===key));
    $('combatPath').textContent=p.path+' · '+p.status;
    $('combatCode').textContent='Încarc '+p.path+'…';
    try{const r=await fetch(p.path+'?v='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);$('combatCode').innerHTML=esc(await r.text());}
    catch(err){$('combatCode').textContent='Nu pot încărca fișierul Lua: '+err;}
  }
  document.querySelectorAll('.combat-selector button').forEach(b=>b.addEventListener('click',()=>load(b.dataset.policy)));

  const pathEl=$('combatPath');
  if(pathEl&&!$('luaRuntimeStatus')){
    const row=document.createElement('div');row.style.cssText='display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0';
    row.innerHTML='<span id="luaRuntimeStatus" class="amber">Lua runtime: loading…</span><button id="luaRuntimeTest" type="button">Test ClassCombat.lua</button><span id="luaRuntimeDetails" class="muted"></span>';
    pathEl.after(row);
    $('luaRuntimeTest').onclick=async()=>{
      const rt=window.WOW_LUA_RUNTIME;if(!rt){$('luaRuntimeDetails').textContent='runtime încă nu este încărcat';return;}
      $('luaRuntimeDetails').textContent='rulez…';
      try{const t=await rt.selfTest();$('luaRuntimeDetails').textContent=t.checks.map(x=>`${x.pass?'✓':'✗'} ${x.name}: ${x.actual}`).join(' · ');}
      catch(err){$('luaRuntimeDetails').textContent=String(err?.message||err);}
    };
  }
  function renderRuntime(rt){
    const el=$('luaRuntimeStatus');if(!el)return;
    const ok=rt?.status==='READY'&&rt?.lastSelfTest?.pass===true;
    el.className=ok?'green':'red';
    el.textContent=ok?'Lua runtime: DIRECT EXECUTION PASS':`Lua runtime: ${rt?.status||'ERROR'}`;
    if(rt?.lastError)$('luaRuntimeDetails').textContent=rt.lastError;
    else if(rt?.lastSelfTest)$('luaRuntimeDetails').textContent=rt.lastSelfTest.checks.map(x=>`${x.pass?'✓':'✗'} ${x.name}`).join(' · ');
  }
  document.addEventListener('wow-lua-runtime-ready',e=>renderRuntime(e.detail));
  if(!document.querySelector('script[data-wow-lua-runtime]')){
    const s=document.createElement('script');s.src='lua-runtime.js?v='+Date.now();s.dataset.wowLuaRuntime='1';document.head.appendChild(s);
  }else if(window.WOW_LUA_RUNTIME)renderRuntime(window.WOW_LUA_RUNTIME);

  function patchVisibleVersion(){
    const hero=document.querySelector('.hero p');
    if(hero)hero.textContent='v0.26 · Rogue ClassCombat learning · talent-aware combat · strict accuracy';
    const metrics=[...document.querySelectorAll('.metric')];
    const champion=window.WOW_DATA?.roguePolicyChampion;
    for(const m of metrics){
      const label=m.querySelector('span')?.textContent||'';
      if(label==='Rogue champion'&&champion)m.querySelector('b').textContent='g3 · Evis 4 CP · Hemo pool 65';
      if(label==='Evidence')m.querySelector('b').textContent='3 × 1.000 paired seeds';
    }
    const note=document.querySelector('#combat .note');
    if(note)note.textContent='Current Rogue champion g3: Eviscerate la 4+ CP și pool 65 Energy înainte de Hemorrhage. Win rate pe setul calibrat de 1.000 seed-uri: 83.8% baseline → 89.2% → 92.0% → 93.0%. Generation 4 threshold screen nu a produs încă un challenger validat mai bun.';
  }

  function ensureLearningPanel(){
    const combat=document.getElementById('combat');if(!combat||$('rogueLearningPanel'))return;
    const panel=document.createElement('div');panel.id='rogueLearningPanel';panel.className='note';panel.style.marginTop='12px';
    panel.innerHTML='<b>Rogue learning</b><br><span id="rogueLearningText">Încarc evidence…</span>';
    combat.appendChild(panel);
    fetch('/api/rogue-training-status?ts='+Date.now(),{cache:'no-store'}).then(r=>r.json()).then(x=>{
      const c=x?.validation?.champion||x?.screen?.champion||window.WOW_DATA?.roguePolicyChampion;
      const v=x?.validation?.result;
      let txt=c?`Champion: ${c.id} · Evis ${c.evisMinCp}+ CP · Hemo pool ${c.hemoMinEnergy} Energy.`:'Champion indisponibil.';
      if(v)txt+=` Ultimul challenger validat: ${v.field}=${v.value} · ${v.challengerRate}% vs ${v.championRate}% · ${v.promote?'PROMOTE':'REJECT'}.`;
      txt+=' Următorul salt de calitate trebuie să vină din acțiuni PvP noi verificate (Blind/Gouge/positional daggers), nu din schimbarea regulilor WoW.';
      $('rogueLearningText').textContent=txt;
    }).catch(()=>{$('rogueLearningText').textContent='Evidence API indisponibil; ClassCombat.lua rămâne sursa policy curentă.';});
  }

  patchVisibleVersion();
  ensureLearningPanel();
  load('rogue');
  window.WOW_COMBAT_VIEWER={load,policies,version:'0.26'};
})();
