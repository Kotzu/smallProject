(function(){
  const $=id=>document.getElementById(id);
  const CLASSES={
    Druid:['Balance','Feral','Restoration'],
    Hunter:['Beast Mastery','Marksmanship','Survival'],
    Mage:['Arcane','Fire','Frost'],
    Paladin:['Holy','Protection','Retribution'],
    Priest:['Discipline','Holy','Shadow'],
    Rogue:['Assassination','Combat','Subtlety'],
    Shaman:['Elemental','Enhancement','Restoration'],
    Warlock:['Affliction','Demonology','Destruction'],
    Warrior:['Arms','Fury','Protection']
  };
  // Current public WoW Forever race/class combinations (Wowhead, 2026-09-16).
  // Skyborne Mage is Alliance-only and Skyborne Shaman is Horde-only; faction
  // selection will be required before either can become combat-eligible.
  const RACES={
    Druid:['Night Elf','Tauren','Skyborne'],
    Hunter:['Dwarf','Human','Night Elf','Orc','Tauren','Troll','Skyborne'],
    Mage:['Gnome','Human','Orc','Troll','Undead','Skyborne'],
    Paladin:['Dwarf','Human','Undead'],
    Priest:['Dwarf','Gnome','Human','Night Elf','Troll','Undead'],
    Rogue:['Dwarf','Gnome','Human','Night Elf','Orc','Troll','Undead','Skyborne'],
    Shaman:['Dwarf','Orc','Tauren','Troll','Skyborne'],
    Warlock:['Gnome','Human','Orc','Troll','Undead'],
    Warrior:['Dwarf','Gnome','Human','Night Elf','Orc','Tauren','Troll','Undead','Skyborne']
  };
  const GEARS=['Forever PvP Loadout'];
  const state={a:{class:'Rogue',spec:'Subtlety',race:'Undead',gear:GEARS[0]},b:{class:'Mage',spec:'Frost',race:'Gnome',gear:GEARS[0]}};

  function fillSelect(el,arr,value){
    if(!el)return;
    el.innerHTML=arr.map(v=>`<option value="${v}">${v}</option>`).join('');
    el.value=arr.includes(value)?value:arr[0];
  }
  function buildPoints(p){
    try{return window.WOW_FOREVER_BUILDS?.audit?.(p,state[p].class)?.points??0;}catch(_e){return 0;}
  }
  function renderStatus(p){
    const el=$(p+'Status');if(!el)return;
    const F=window.WOW_FOREVER_TALENTS,B=window.WOW_FOREVER_BUILDS;
    const points=buildPoints(p),db=F?.db||'loading';
    const buildOk=!!B&&points===51;
    const skyborneNote=state[p].race==='Skyborne'?' · <span class="amber">Skyborne faction/racial variant required for combat</span>':'';
    el.innerHTML=`<span class="green">WoW Forever</span> · <span class="${buildOk?'green':'amber'}">Talents ${points}/51</span> · <span class="amber">Gear/stats verification pending</span>${skyborneNote} · <span class="muted">db ${db}</span>`;
  }
  function bind(p){
    const c=$(p+'c'),s=$(p+'s'),r=$(p+'r'),g=$(p+'g');
    fillSelect(c,Object.keys(CLASSES),state[p].class);fillSelect(g,GEARS,state[p].gear);
    function refreshSpecRace(){
      state[p].class=c.value;
      fillSelect(s,CLASSES[state[p].class],state[p].spec);state[p].spec=s.value;
      fillSelect(r,RACES[state[p].class],state[p].race);state[p].race=r.value;
      state[p].gear=g.value;renderStatus(p);
      window.WOW_ARMORY_UI?.render?.();window.WOW_ARMORY_TALENTS?.render?.();
    }
    c.onchange=refreshSpecRace;
    s.onchange=()=>{state[p].spec=s.value;renderStatus(p);window.WOW_ARMORY_UI?.render?.();window.WOW_ARMORY_TALENTS?.render?.();};
    r.onchange=()=>{state[p].race=r.value;renderStatus(p);window.WOW_ARMORY_UI?.render?.();};
    g.onchange=()=>{state[p].gear=g.value;renderStatus(p);window.WOW_ARMORY_UI?.render?.();};
    refreshSpecRace();
  }
  function openTab(id){
    document.querySelectorAll('.tabs button').forEach(x=>x.classList.toggle('active',x.dataset.tab===id));
    document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.id===id));
  }
  document.querySelectorAll('.tabs button').forEach(btn=>btn.onclick=()=>openTab(btn.dataset.tab));
  bind('a');bind('b');

  ['runBtn','batch1Btn','batchBtn','batch100Btn','fightRunBtn','fightPlayBtn','fightPauseBtn','fightStepBtn'].forEach(id=>{const el=$(id);if(el)el.disabled=true;});
  const gate=$('gateReason');if(gate)gate.innerHTML='<span class="amber">WOW FOREVER ONLY · FIGHT LOCKED · Armory poate fi configurat, dar duelul se deblochează numai după gear/stat/spell/CombatEngine parity verificată.</span>';

  const migrationMessage='<div class="armory-migration-note">Legacy Classic fixtures are not used as Forever authority. These diagnostics stay blank until a verified Forever module replaces them.</div>';
  ['rogueCharacter','mageCharacter','rogueStats','gearRows','ruleCards'].forEach(id=>{const el=$(id);if(el)el.innerHTML=migrationMessage;});
  ['armorOut','spellOut','meleeOut'].forEach(id=>{const el=$(id);if(el)el.textContent='—';});

  document.addEventListener('wow-forever-talents-ready',()=>{renderStatus('a');renderStatus('b');window.WOW_ARMORY_UI?.render?.();});
  document.addEventListener('wow-forever-build-changed',e=>{if(e.detail?.player==='a'||e.detail?.player==='b')renderStatus(e.detail.player);});

  window.WOW_APP={state,config:()=>({a:{...state.a,build:window.WOW_FOREVER_BUILDS?.exportBuild?.('a')||null},b:{...state.b,build:window.WOW_FOREVER_BUILDS?.exportBuild?.('b')||null}}),openTab,version:'0.40-forever-armory'};
})();