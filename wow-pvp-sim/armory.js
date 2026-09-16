(function(){
  const A=window.WOW_ARMORY,W=window.WOW_STATS,D=window.WOW_DATA,CE=window.WOW_CHARACTER_ENGINE,CD=window.WOW_CHARACTER_DATA,T=window.WOW_TALENTS;
  const $=id=>document.getElementById(id);
  const read=p=>({class:$(p+'c')?.value,spec:$(p+'s')?.value,race:$(p+'r')?.value,gear:$(p+'g')?.value,build:$(p+'build')?.value||T?.defaultBuild($(p+'c')?.value,$(p+'s')?.value)});
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pct=v=>typeof v==='number'?`${v.toFixed(2)}%`:v;

  function canonicalStats(s){
    const build=T?.get(s.build),tm=build?.modifiers||{};
    if(A.isRogue(s)){
      const P=A.rogueProfile(s),r=CE.rogue60Baseline(CD.level60.undeadRogue,P);
      const gearCrit=P.combinedStaticTotals.crit||0;
      const meleeCrit=gearCrit+r.stats.agi/29+(tm.meleeCritPct||0);
      const hit=r.hitPct+(tm.meleeHitPct||0);
      const rows=[
        ['Strength',r.stats.str,'primary'],['Agility',r.stats.agi,'primary'],['Stamina',r.stats.sta,'primary'],['Intellect',r.stats.int,'primary'],['Spirit',r.stats.spi,'primary'],
        ['Health',r.health,'resource'],['Energy',100,'resource'],['Attack Power',r.attackPower,'offense'],['Armor',r.armor,'defense'],['Hit',hit.toFixed(1)+'%','offense'],['Melee Crit',meleeCrit.toFixed(2)+'%','offense'],['Shadow Resist',r.shadowResistance,'resist'],['MH Damage',r.mainHand.min.toFixed(1)+'–'+r.mainHand.max.toFixed(1),'offense']
      ];
      if(r.weaponSkill?.Dagger)rows.push(['Dagger Skill','+'+r.weaponSkill.Dagger,'offense']);
      return rows;
    }
    if(A.isMage(s)){
      const p=D.pvpProfiles.mage_frost_gnome_p6_core,dec=A.mageDecomposition?.();
      return [
        ['Strength',p.stats.strength,'primary'],['Agility',p.stats.agility,'primary'],['Stamina',p.stats.stamina,'primary'],['Intellect',p.stats.intellect,'primary'],['Spirit',p.stats.spirit,'primary'],
        ['Health',p.stats.health,'resource'],['Mana',p.stats.mana,'resource'],['Spell Power',p.stats.spellDamage,'offense'],['Frost Spell Power',dec?.frostSpellPower??p.stats.spellDamage,'offense'],['Spell Crit',pct(p.stats.spellCritPct),'offense'],['Frost / Fire Hit',(p.stats.spellHitPct+(tm.frostFireHitPct||0))+'%','offense'],['Spell Penetration',p.stats.spellPen,'offense'],
        ['Armor',Math.trunc(p.stats.armorBeforeTalents+p.stats.intellect*((tm.armorFromIntellectPct||0)/100)),'defense'],['Dodge',p.stats.dodgePct+'%','defense'],
        ['Arcane Resist',p.stats.resist.arcane,'resist'],['Fire Resist',p.stats.resist.fire,'resist'],['Frost Resist',p.stats.resist.frost,'resist'],['Nature Resist',p.stats.resist.nature,'resist'],['Shadow Resist',p.stats.resist.shadow,'resist'],
        ['Shatter','+'+(tm.frozenCritBonusPct||0)+'% frozen','talent'],['Frost Crit Damage',(tm.frostCritMultiplier||1.5).toFixed(1)+'×','talent']
      ];
    }
    return [];
  }

  function itemFacts(x){
    const i=x.item||{},bits=[];
    if(i.armor)bits.push(`${i.armor} Armor`);
    if(i.str)bits.push(`+${i.str} Strength`);if(i.agi)bits.push(`+${i.agi} Agility`);if(i.sta)bits.push(`+${i.sta} Stamina`);if(i.int)bits.push(`+${i.int} Intellect`);if(i.spi)bits.push(`+${i.spi} Spirit`);
    if(i.ap)bits.push(`+${i.ap} Attack Power`);if(i.hit)bits.push(`+${i.hit}% Hit`);if(i.crit)bits.push(`+${i.crit}% Crit`);if(i.shadowRes)bits.push(`+${i.shadowRes} Shadow Resistance`);
    if(i.spellPower)bits.push(`+${i.spellPower} Spell Damage`);if(i.spellHit)bits.push(`+${i.spellHit}% Spell Hit`);if(i.spellCrit)bits.push(`+${i.spellCrit}% Spell Crit`);if(i.spellPen)bits.push(`+${i.spellPen} Spell Penetration`);if(i.dodge)bits.push(`+${i.dodge}% Dodge`);
    if(i.manaShieldBonusAbsorb)bits.push(`Mana Shield absorbs +${i.manaShieldBonusAbsorb}`);
    if(i.weapon)bits.push(`${i.weapon.minDamage}–${i.weapon.maxDamage}${i.weapon.school?` ${i.weapon.school}`:''} Damage · ${i.weapon.speed.toFixed(2)} Speed · ${i.weapon.dps.toFixed(2)} DPS`);
    if(i.useEffect)bits.push(`Use: ${i.useEffect}${i.cooldownSec?` · ${i.cooldownSec/60} min cooldown`:''}`);
    if(i.set)bits.push(`Set: ${i.set}`);
    if(x.weaponSkill)bits.push(x.weaponSkill);
    return bits;
  }

  function qualityClass(x){return x?.quality?` quality-${esc(x.quality)}`:'';}
  function wowheadLink(x,icon=false){
    if(!x.id)return `<span class="armory-empty-icon">—</span>`;
    const attrs=`href="${esc(x.wowhead||`https://www.wowhead.com/classic/item=${x.id}`)}" data-wowhead="item=${x.id}&domain=classic" target="_blank" rel="noopener"`;
    if(icon)return `<a class="armory-item-icon${qualityClass(x)}" ${attrs} data-wh-icon-size="large"><span class="slot-fallback">${esc(x.slot.slice(0,2).toUpperCase())}</span></a>`;
    return `<a class="armory-item-name${qualityClass(x)}" ${attrs}>${esc(x.name)}</a>`;
  }

  function slotCard(x,side='left'){
    const facts=itemFacts(x),empty=!x.id;
    const nativeTooltip=empty?'':`<div class="armory-native-tooltip"><div class="tt-name${qualityClass(x)}">${esc(x.name)}</div>${x.itemLevel?`<div class="tt-ilvl">Item Level ${esc(x.itemLevel)}</div>`:''}<div class="tt-slot">${esc(x.slot)}</div>${facts.map(v=>`<div>${esc(v)}</div>`).join('')}${x.enchant?`<div class="tt-enchant">${esc(x.enchant)}${x.enchantEffect?` · ${esc(x.enchantEffect)}`:''}</div>`:''}<div class="tt-id">Item #${x.id}</div><div class="tt-verified">${x.verified?'✓ Verified local Classic record':'⚠ Unverified item record'}</div></div>`;
    return `<div class="paperdoll-slot ${side} ${empty?'empty':''}" data-slot="${esc(x.slot)}">
      ${side==='right'?'<div class="paperdoll-slot-copy">'+slotCopy(x)+'</div>':''}
      <div class="paperdoll-icon-wrap">${wowheadLink(x,true)}${nativeTooltip}</div>
      ${side!=='right'?'<div class="paperdoll-slot-copy">'+slotCopy(x)+'</div>':''}
    </div>`;
  }

  function slotCopy(x){
    return `<div class="paperdoll-slot-label">${esc(x.slot)}</div>${x.id?wowheadLink(x,false):'<div class="armory-item-name empty-name">Empty</div>'}${x.itemLevel?`<div class="paperdoll-ilvl">Item Level ${esc(x.itemLevel)}</div>`:''}${x.enchant?`<div class="paperdoll-enchant">${esc(x.enchant)}</div>`:'<div class="paperdoll-enchant muted">No enchant</div>'}${x.enchantEffect?`<div class="paperdoll-enchant-effect">${esc(x.enchantEffect)}</div>`:''}`;
  }

  function modelMarkup(s,meta,audit){
    const classKey=String(s.class||'unknown').toLowerCase();
    const icon=`https://wow.zamimg.com/images/wow/icons/large/classicon_${classKey}.jpg`;
    return `<div class="paperdoll-model ${classKey}">
      <div class="paperdoll-glow"></div>
      <div class="paperdoll-character">
        <div class="silhouette-head"></div><div class="silhouette-body"></div><div class="silhouette-arm left"></div><div class="silhouette-arm right"></div><div class="silhouette-leg left"></div><div class="silhouette-leg right"></div>
        <img class="paperdoll-class-icon" src="${icon}" alt="${esc(s.class)} class icon" loading="lazy">
      </div>
      <div class="paperdoll-model-copy"><div class="paperdoll-level">Level ${meta.level}</div><strong>${esc(meta.race)} ${esc(meta.class)}</strong><span>${esc(meta.spec)} · ${esc(meta.buildName)}</span><span>${esc(meta.buildPoints)} talents</span></div>
      <div class="armory-audit-pill ${audit.pass?'pass':'fail'}">${audit.pass?'VERIFIED':'AUDIT FAIL'}</div>
    </div>`;
  }

  function groupedStats(rows){
    const order=[['resource','Resources'],['primary','Attributes'],['offense','Offense'],['defense','Defense'],['resist','Resistances'],['talent','Talent Effects']];
    return order.map(([key,title])=>{
      const group=rows.filter(x=>x[2]===key);if(!group.length)return '';
      return `<section class="armory-stat-section"><h4>${title}</h4><div class="armory-stat-list">${group.map(([k,v])=>`<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('')}</div></section>`;
    }).join('');
  }

  function quickStats(rows,s){
    const find=name=>rows.find(x=>x[0]===name)?.[1]??'—';
    const second=A.isMage(s)?['Frost Spell Power','Spell Crit','Frost / Fire Hit']:['Attack Power','Melee Crit','Hit'];
    const resource=A.isMage(s)?['Mana','Mana']:['Energy','Energy'];
    const stats=[['Health',find('Health')],[resource[0],find(resource[1])],...second.map(k=>[k,find(k)]),['Armor',find('Armor')]];
    return stats.map(([k,v])=>`<div class="armory-quick-stat"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('');
  }

  function auditMarkup(audit){
    const checks=(audit.checks||[]).map(c=>`<div class="audit-check ${c.pass?'ok':'bad'}"><span>${c.pass?'✓':'✕'} ${esc(c.name)}</span><b>${esc(c.value)}</b></div>`).join('');
    return `<details class="armory-integrity" ${audit.pass?'':'open'}><summary><span>Data integrity</span><b class="${audit.pass?'green':'red'}">STAT AUDIT: ${esc(audit.status)}</b></summary><div class="armory-integrity-copy">${esc(audit.reason||'')}</div><div class="audit-checks">${checks}</div></details>`;
  }

  function renderOne(p){
    const s=read(p),root=$(p+'Armory');if(!root)return;
    const slots=A.armoryFor(s),audit=A.audit(s),model=A.statModel(s),meta=A.profileMeta(s),talent=T?.auditSelection(s);
    if(!slots){
      root.innerHTML=`<div class="armory-empty"><b>Armory locked</b><span>Exact profile for ${esc(s.class)} ${esc(s.spec)} / ${esc(s.race)} is not loaded yet.</span></div>`;return;
    }
    const bySlot=Object.fromEntries(slots.map(x=>[x.slot,x])),stats=canonicalStats(s),talentState=talent?.pass?'BUILD VERIFIED':'BUILD LOCKED';
    root.innerHTML=`
      <div class="blizzard-armory">
        <header class="blizzard-armory-header">
          <div class="armory-identity"><div class="armory-level-badge">60</div><div><h3>${esc(s.race)} ${esc(s.class)}</h3><p>${esc(s.spec)} · ${esc(s.gear)}</p></div></div>
          <div class="armory-header-badges"><span class="build-pill ${talent?.pass?'ok':'warn'}">${talentState}</span><span class="audit-badge ${audit.pass?'pass':'fail'}">STAT AUDIT: ${esc(audit.status)}</span></div>
        </header>
        <div class="armory-subnav"><span class="active">CHARACTER</span><span>TALENTS · ${esc(meta.buildPoints)}</span><span>PVP LOADOUT</span></div>
        <div class="paperdoll-stage">
          <div class="paperdoll-column left">${A.LEFT_SLOTS.map(slot=>slotCard(bySlot[slot],'left')).join('')}</div>
          ${modelMarkup(s,meta,audit)}
          <div class="paperdoll-column right">${A.RIGHT_SLOTS.map(slot=>slotCard(bySlot[slot],'right')).join('')}</div>
          <div class="paperdoll-weapons">${A.WEAPON_SLOTS.map(slot=>slotCard(bySlot[slot],'weapon')).join('')}</div>
        </div>
        <div class="armory-quick-stats">${quickStats(stats,s)}</div>
        <div class="armory-details-grid">
          <div class="armory-stats-pane"><h3>Character Stats</h3>${groupedStats(stats)}</div>
          <div class="armory-build-pane"><h3>Specialization</h3><div class="armory-build-card"><span>${esc(s.spec)}</span><strong>${esc(meta.buildName)}</strong><small>${esc(meta.buildPoints)} · ${talent?.kernelReady?'kernel active':'kernel locked'}</small></div><h3>Class Scaling</h3><div class="armory-scaling">${(model?.lines||[]).map(x=>`<div><b>${esc(x.stat)}</b><span>${esc(x.effect)}</span></div>`).join('')}${model?.note?`<p>${esc(model.note)}</p>`:''}</div></div>
        </div>
        ${auditMarkup(audit)}
        <div class="armory-footnote">Hover or tap an item for its exact Classic tooltip. Every Mage slot now also has a complete local Classic stat record, so the paperdoll can be audited without depending on the tooltip service.</div>
      </div>`;
    refreshExternalTooltips();
  }

  function refreshExternalTooltips(){
    setTimeout(()=>{
      try{window.$WowheadPower?.refreshLinks?.();}catch(_e){}
      try{window.WH?.Tooltips?.refreshLinks?.();}catch(_e){}
    },40);
  }

  function render(){renderOne('a');renderOne('b');}
  ['ac','as','ar','ag','abuild','bc','bs','br','bg','bbuild'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(render,0)));
  render();
  window.WOW_ARMORY_UI={render,version:'0.29-blizzard-paperdoll-local-audit'};
})();
