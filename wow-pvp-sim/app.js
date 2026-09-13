(function(){
  const D=window.WOW_DATA,E=window.WOW_ENGINE;
  const RACES={Druid:['Night Elf','Tauren'],Hunter:['Dwarf','Night Elf','Orc','Tauren','Troll'],Mage:['Gnome','Human','Troll','Undead'],Paladin:['Dwarf','Human'],Priest:['Dwarf','Human','Night Elf','Troll','Undead'],Rogue:['Dwarf','Gnome','Human','Night Elf','Orc','Troll','Undead'],Shaman:['Orc','Tauren','Troll'],Warlock:['Gnome','Human','Orc','Undead'],Warrior:['Dwarf','Gnome','Human','Night Elf','Orc','Tauren','Troll','Undead']};
  const GEARS=['Level 10 BiS','Level 20 BiS','Level 30 BiS','Level 40 BiS','Level 50 BiS','Level 60 BiS','Level 60 Pre-Raid BiS','Level 60 Dungeon BiS','Level 60 Raid BiS','Level 60 PvP BiS'];
  const $=id=>document.getElementById(id);
  const specsByClass=D.specs.reduce((a,x)=>((a[x.class]??=[]).push(x.spec),a),{});
  const state={a:{class:'Rogue',spec:'Subtlety',race:'Undead',gear:'Level 60 PvP BiS'},b:{class:'Mage',spec:'Frost',race:'Gnome',gear:'Level 60 PvP BiS'}};
  function profileFor(s){if(s.class==='Rogue'&&s.spec==='Subtlety'&&s.gear==='Level 60 PvP BiS')return D.profiles.rogue_subtlety_lvl60_pvp_bis_p6_baseline;return null;}
  function fillSelect(el,arr,value){el.innerHTML=arr.map(v=>`<option>${v}</option>`).join('');if(arr.includes(value))el.value=value;}
  function bind(p){const c=$(p+'c'),s=$(p+'s'),r=$(p+'r'),g=$(p+'g');fillSelect(c,Object.keys(specsByClass),state[p].class);fillSelect(g,GEARS,state[p].gear);function refreshSpecRace(){state[p].class=c.value;fillSelect(s,specsByClass[state[p].class],state[p].spec);state[p].spec=s.value;fillSelect(r,RACES[state[p].class],state[p].race);state[p].race=r.value;renderStatus(p);}c.onchange=refreshSpecRace;s.onchange=()=>{state[p].spec=s.value;renderStatus(p)};r.onchange=()=>{state[p].race=r.value;renderStatus(p)};g.onchange=()=>{state[p].gear=g.value;renderStatus(p)};refreshSpecRace();}
  function renderStatus(p){const prof=profileFor(state[p]);$(p+'Status').innerHTML=prof?'<span class="green">✓ profil static verificat</span> · final player stats încă incomplete':'<span class="amber">profil exact încă neîncărcat</span>';updateGate();}
  function updateGate(){const pa=profileFor(state.a),pb=profileFor(state.b);const ready=E.profileReady(pa)&&E.profileReady(pb);$('runBtn').disabled=!ready;$('batchBtn').disabled=!ready;$('gateReason').textContent=ready?'Gata de simulat':'STRICT DATA GATE: lipsesc stats/spells complete pentru cel puțin un player.';}
  bind('a');bind('b');

  $('ruleCount').textContent=D.rules.rules.length;
  document.querySelectorAll('.tabs button').forEach(btn=>btn.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.classList.toggle('active',x===btn));document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.id===btn.dataset.tab));});

  const P=D.profiles.rogue_subtlety_lvl60_pvp_bis_p6_baseline,C=P.combinedStaticTotals,R=P.derivedRogueLevel60GearContributions;
  $('rogueStats').innerHTML=[['STR',C.str],['AGI',C.agi],['STA',C.sta],['Hit',C.hit+'%'],['AP gear',R.totalStaticGearMeleeAPContribution],['Armor gear',R.totalStaticGearArmorContribution],['HP gear',R.totalStaticGearHealthContribution],['Crit gear+AGI',R.totalStaticGearCritContributionPct.toFixed(2)+'%']].map(x=>`<div class="stat"><span>${x[0]}</span><b>${x[1]}</b></div>`).join('');
  const order=['Head','Neck','Shoulder','Back','Chest','Wrist','Hands','Waist','Legs','Feet','Finger 1','Finger 2','Trinket 1','Trinket 2','Main Hand','Off Hand','Ranged'];
  $('gearRows').innerHTML=order.map(slot=>{const i=D.items[String(P.slots[slot])];return `<tr><td>${slot}</td><td>${i.name}</td><td>${i.id}</td><td>${i.sta||0}</td><td>${i.agi||0}</td><td>${i.ap||0}</td><td>${i.hit||0}%</td><td>${i.crit||0}%</td></tr>`}).join('');
  $('ruleCards').innerHTML=D.rules.rules.map(r=>`<div class="rule-card"><h3 class="green">✓ ${r.id}</h3><p>${r.scope}</p><code>${r.formula}</code></div>`).join('');
  function updateLab(){const armor=Number($('armorInput').value)||0,level=Number($('levelInput').value)||60,spellHit=Number($('spellHitInput').value)||0,meleeHit=Number($('meleeHitInput').value)||0;$('armorOut').textContent=(E.physicalArmorReduction(armor,level)*100).toFixed(2)+'%';$('spellOut').textContent=E.sameLevelSpellMiss(spellHit).toFixed(2)+'% miss';$('meleeOut').textContent=E.sameLevelMeleeSpecialMiss(meleeHit).toFixed(2)+'% miss';}
  ['armorInput','levelInput','spellHitInput','meleeHitInput'].forEach(id=>$(id).addEventListener('input',updateLab));updateLab();
})();
