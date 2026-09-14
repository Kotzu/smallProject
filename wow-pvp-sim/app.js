(function(){
  const D=window.WOW_DATA,E=window.WOW_ENGINE,CD=window.WOW_CHARACTER_DATA,CE=window.WOW_CHARACTER_ENGINE,DUEL=window.WOW_DUEL;
  const RACES={Druid:['Night Elf','Tauren'],Hunter:['Dwarf','Night Elf','Orc','Tauren','Troll'],Mage:['Gnome','Human','Troll','Undead'],Paladin:['Dwarf','Human'],Priest:['Dwarf','Human','Night Elf','Troll','Undead'],Rogue:['Dwarf','Gnome','Human','Night Elf','Orc','Troll','Undead'],Shaman:['Orc','Tauren','Troll'],Warlock:['Gnome','Human','Orc','Undead'],Warrior:['Dwarf','Gnome','Human','Night Elf','Orc','Tauren','Troll','Undead']};
  const GEARS=['Level 10 BiS','Level 20 BiS','Level 30 BiS','Level 40 BiS','Level 50 BiS','Level 60 BiS','Level 60 Pre-Raid BiS','Level 60 Dungeon BiS','Level 60 Raid BiS','Level 60 PvP BiS'];
  const $=id=>document.getElementById(id);
  const specsByClass=D.specs.reduce((a,x)=>((a[x.class]??=[]).push(x.spec),a),{});
  const state={a:{class:'Rogue',spec:'Subtlety',race:'Undead',gear:'Level 60 PvP BiS'},b:{class:'Mage',spec:'Frost',race:'Gnome',gear:'Level 60 PvP BiS'}};
  const config=()=>({a:{...state.a},b:{...state.b}});

  function exactProfile(s){
    if(s.class==='Rogue'&&s.spec==='Subtlety'&&s.race==='Undead'&&s.gear==='Level 60 PvP BiS')return D.pvpProfiles?.rogue_sub_undead_p6_static;
    if(s.class==='Mage'&&s.spec==='Frost'&&s.race==='Gnome'&&s.gear==='Level 60 PvP BiS')return D.pvpProfiles?.mage_frost_gnome_p6_core;
    return null;
  }
  function fillSelect(el,arr,value){el.innerHTML=arr.map(v=>`<option>${v}</option>`).join('');if(arr.includes(value))el.value=value;}
  function bind(p){
    const c=$(p+'c'),s=$(p+'s'),r=$(p+'r'),g=$(p+'g');
    fillSelect(c,Object.keys(specsByClass),state[p].class);fillSelect(g,GEARS,state[p].gear);
    function refreshSpecRace(){
      state[p].class=c.value;fillSelect(s,specsByClass[state[p].class],state[p].spec);state[p].spec=s.value;
      fillSelect(r,RACES[state[p].class],state[p].race);state[p].race=r.value;renderStatus(p);
    }
    c.onchange=refreshSpecRace;
    s.onchange=()=>{state[p].spec=s.value;renderStatus(p)};
    r.onchange=()=>{state[p].race=r.value;renderStatus(p)};
    g.onchange=()=>{state[p].gear=g.value;renderStatus(p)};
    refreshSpecRace();
  }
  function renderStatus(p){
    const s=state[p],prof=exactProfile(s);
    let txt=prof?'<span class="green">✓ v0.10 kernel profile</span>':'<span class="amber">date exacte încă neîncărcate pentru această combinație</span>';
    if(s.class==='Rogue'&&s.race==='Undead')txt+=' · <span class="green">base stats ✓</span>';
    if(s.class==='Mage'&&s.race==='Gnome')txt+=' · <span class="green">base stats ✓</span>';
    $(p+'Status').innerHTML=txt;updateGate();
  }
  function setBatchButtons(disabled){['batch1Btn','batchBtn','batch100Btn'].forEach(id=>{if($(id))$(id).disabled=disabled;});}
  function updateGate(){
    if(!DUEL)return;
    const gate=DUEL.canRun(config());$('runBtn').disabled=!gate.ready;setBatchButtons(!gate.ready);
    if(gate.ready){
      const t=DUEL.selfTest(config());
      $('gateReason').innerHTML=`<span class="green">RUNNABLE v${DUEL.version} · reproducibil ${t.deterministic?'✓':'FAIL'}</span><br><span class="amber">3 calibrări stricte rămase</span>`;
    } else $('gateReason').textContent='STRICT DATA GATE: '+gate.missing.join(' · ');
  }
  bind('a');bind('b');

  $('ruleCount').textContent=D.rules.rules.length+19;
  function openTab(id){
    document.querySelectorAll('.tabs button').forEach(x=>x.classList.toggle('active',x.dataset.tab===id));
    document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.id===id));
  }
  document.querySelectorAll('.tabs button').forEach(btn=>btn.onclick=()=>openTab(btn.dataset.tab));

  const P=D.profiles.rogue_subtlety_lvl60_pvp_bis_p6_baseline,C=P.combinedStaticTotals,R=P.derivedRogueLevel60GearContributions;
  $('rogueStats').innerHTML=[['STR gear',C.str],['AGI gear',C.agi],['STA gear',C.sta],['Hit',C.hit+'%'],['AP gear contribution',R.totalStaticGearMeleeAPContribution],['Armor gear contribution',R.totalStaticGearArmorContribution],['HP gear contribution',R.totalStaticGearHealthContribution],['Crit gear+AGI',R.totalStaticGearCritContributionPct.toFixed(2)+'%']].map(x=>`<div class="stat"><span>${x[0]}</span><b>${x[1]}</b></div>`).join('');
  const order=['Head','Neck','Shoulder','Back','Chest','Wrist','Hands','Waist','Legs','Feet','Finger 1','Finger 2','Trinket 1','Trinket 2','Main Hand','Off Hand','Ranged'];
  $('gearRows').innerHTML=order.map(slot=>{const i=D.items[String(P.slots[slot])];return `<tr><td>${slot}</td><td>${i.name}</td><td>${i.id}</td><td>${i.sta||0}</td><td>${i.agi||0}</td><td>${i.ap||0}</td><td>${i.hit||0}%</td><td>${i.crit||0}%</td></tr>`}).join('');

  const rogue=CE.rogue60Baseline(CD.level60.undeadRogue,P);
  const mp=D.pvpProfiles.mage_frost_gnome_p6_core;
  const mageArmor=Math.trunc(mp.stats.armorBeforeTalents+mp.stats.intellect*0.5);
  const barrier=Math.round(D.pvpSpellbooks.Mage.iceBarrier.absorbBase+mp.stats.spellDamage*D.pvpSpellbooks.Mage.iceBarrier.spCoeff);
  const manaShield=D.pvpSpellbooks.Mage.manaShield.absorbBase+(mp.gearEffects?.manaShieldBonusAbsorb||0);
  $('rogueCharacter').innerHTML=[['STR total',rogue.stats.str],['AGI total',rogue.stats.agi],['STA total',rogue.stats.sta],['HP',rogue.health],['Melee AP',rogue.attackPower],['Armor',rogue.armor],['MH damage',rogue.mainHand.min.toFixed(1)+'–'+rogue.mainHand.max.toFixed(1)],['White miss dual wield',Math.max(0,24-rogue.hitPct).toFixed(1)+'%'],['Crippling MH','30% proc'],['Mind-numbing OH','20% proc']].map(x=>`<div class="stat"><span>${x[0]}</span><b>${x[1]}</b></div>`).join('');
  $('mageCharacter').innerHTML=[['HP',mp.stats.health],['Mana',mp.stats.mana],['STA',mp.stats.stamina],['INT',mp.stats.intellect],['Spell Damage',mp.stats.spellDamage],['Spell Crit',mp.stats.spellCritPct+'%'],['Frost/Fire Hit cu talent',(mp.stats.spellHitPct+6)+'%'],['Armor cu Arcane Resilience',mageArmor],['Spell Pen',mp.stats.spellPen],['Dodge + AGM',(mp.stats.dodgePct+1).toFixed(2)+'%'],['Ice Barrier R4',barrier],['Mana Shield + gloves',manaShield],['Blink CD','13.5s'],['Frostfire','6p active']].map(x=>`<div class="stat"><span>${x[0]}</span><b>${x[1]}</b></div>`).join('');

  $('ruleCards').innerHTML=D.rules.rules.map(r=>`<div class="rule-card"><h3 class="green">✓ ${r.id}</h3><p>${r.scope}</p><code>${r.formula}</code></div>`).join('');
  function updateLab(){
    const armor=Number($('armorInput').value)||0,level=Number($('levelInput').value)||60,spellHit=Number($('spellHitInput').value)||0,meleeHit=Number($('meleeHitInput').value)||0;
    $('armorOut').textContent=(E.physicalArmorReduction(armor,level)*100).toFixed(2)+'%';
    $('spellOut').textContent=E.sameLevelSpellMiss(spellHit).toFixed(2)+'% miss';
    $('meleeOut').textContent=E.sameLevelMeleeSpecialMiss(meleeHit).toFixed(2)+'% miss';
  }
  ['armorInput','levelInput','spellHitInput','meleeHitInput'].forEach(id=>$(id).addEventListener('input',updateLab));updateLab();

  function renderDuel(r){
    if(r.error){$('duelSummary').innerHTML=`<div class="red"><b>${r.error}</b>: ${r.missing.join(', ')}</div>`;return;}
    const winClass=r.winner==='Timeout'?'amber':'winner';
    const cal=(r.calibrationRequired||[]).map(x=>`<li>${x}</li>`).join('');
    $('duelSummary').innerHTML=`<div class="${winClass}">WINNER: ${r.winner}</div><div class="result-meta">Durată ${r.duration}s · Rogue ${r.final.rogue.hp} HP · Mage ${r.final.mage.hp} HP / ${r.final.mage.mana} mana · range ${r.final.range} yd</div>${cal?`<div class="calibration"><b>Încă neincluse în rezultat:</b><ul>${cal}</ul></div>`:''}`;
    $('timeline').innerHTML=r.timeline.map(e=>`<div class="timeline-row ${e.kind}"><span>${e.t.toFixed(1)}s</span><b>${e.actor}</b><em>${e.text}</em></div>`).join('');
    $('quickResult').classList.remove('hidden');
    $('quickResult').innerHTML=`<span class="${winClass}">WINNER: ${r.winner}</span><span>${r.duration}s</span><button id="seeTimeline">Timeline</button>`;
    $('seeTimeline').onclick=()=>openTab('duel');
  }
  $('runBtn').onclick=()=>{
    const seed=(Number($('duelCode').value)||1337)>>>0;
    const r=DUEL.run(seed,config());renderDuel(r);$('batchSummary').innerHTML='';openTab('duel');
  };
  function runBatch(button,count){
    const seed=(Number($('duelCode').value)||1337)>>>0;
    setBatchButtons(true);$('runBtn').disabled=true;
    const old=button.textContent;button.textContent='Simulez…';
    setTimeout(()=>{
      const b=DUEL.batch(seed,count,config());
      if(b.error)$('batchSummary').innerHTML=`<span class="red">${b.error}: ${b.missing.join(', ')}</span>`;
      else $('batchSummary').innerHTML=`<div class="batch-grid"><div><span>Duels</span><b>${b.count.toLocaleString('ro-RO')}</b></div><div><span>Rogue</span><b>${b.rates.Rogue}%</b></div><div><span>Mage</span><b>${b.rates.Mage}%</b></div><div><span>Timeout</span><b>${b.rates.Timeout}%</b></div><div><span>Avg</span><b>${b.avgDuration}s</b></div></div>`;
      button.textContent=old;$('runBtn').disabled=false;setBatchButtons(false);openTab('duel');
    },30);
  }
  $('batch1Btn').onclick=()=>runBatch($('batch1Btn'),1000);
  $('batchBtn').onclick=()=>runBatch($('batchBtn'),10000);
  $('batch100Btn').onclick=()=>runBatch($('batch100Btn'),100000);
  updateGate();
})();
