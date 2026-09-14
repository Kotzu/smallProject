(function(){
  const A=window.WOW_ARMORY,W=window.WOW_STATS,D=window.WOW_DATA,CE=window.WOW_CHARACTER_ENGINE,CD=window.WOW_CHARACTER_DATA,T=window.WOW_TALENTS;
  const $=id=>document.getElementById(id);
  const read=p=>({class:$(p+'c')?.value,spec:$(p+'s')?.value,race:$(p+'r')?.value,gear:$(p+'g')?.value,build:$(p+'build')?.value||T?.defaultBuild($(p+'c')?.value,$(p+'s')?.value)});
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function canonicalStats(s){
    const build=T?.get(s.build),tm=build?.modifiers||{};
    if(A.isRogue(s)){
      const P=A.rogueProfile(s),r=CE.rogue60Baseline(CD.level60.undeadRogue,P);
      const gearCrit=P.combinedStaticTotals.crit||0;
      const meleeCrit=gearCrit+r.stats.agi/29+(tm.meleeCritPct||0);
      const hit=r.hitPct+(tm.meleeHitPct||0);
      const rows=[['STR',r.stats.str],['AGI',r.stats.agi],['STA',r.stats.sta],['INT',r.stats.int],['SPI',r.stats.spi],['HP',r.health],['Energy',100],['Melee AP',r.attackPower],['Armor',r.armor],['Hit',hit.toFixed(1)+'%'],['Melee Crit',meleeCrit.toFixed(2)+'%'],['Shadow Resist',r.shadowResistance],['MH damage',r.mainHand.min.toFixed(1)+'–'+r.mainHand.max.toFixed(1)]];
      if(r.weaponSkill?.Dagger)rows.push(['Dagger skill','+'+r.weaponSkill.Dagger]);
      return rows;
    }
    if(A.isMage(s)){
      const p=D.pvpProfiles.mage_frost_gnome_p6_core;
      return [['STR',p.stats.strength],['AGI',p.stats.agility],['STA',p.stats.stamina],['INT',p.stats.intellect],['SPI',p.stats.spirit],['HP',p.stats.health],['Mana',p.stats.mana],['Spell Power',p.stats.spellDamage],['Spell Crit',p.stats.spellCritPct+'%'],['Frost/Fire Hit',(p.stats.spellHitPct+(tm.frostFireHitPct||0))+'%'],['Shatter','+'+(tm.frozenCritBonusPct||0)+'% frozen'],['Frost crit dmg',(tm.frostCritMultiplier||1.5).toFixed(1)+'×'],['Spell Pen',p.stats.spellPen],['Armor',Math.trunc(p.stats.armorBeforeTalents+p.stats.intellect*((tm.armorFromIntellectPct||0)/100))],['Dodge',p.stats.dodgePct+'%'],['Arcane Resist',p.stats.resist.arcane],['Fire Resist',p.stats.resist.fire],['Frost Resist',p.stats.resist.frost],['Nature Resist',p.stats.resist.nature],['Shadow Resist',p.stats.resist.shadow]];
    }
    return [];
  }
  function itemRow(x){
    const empty=!x.id,enchant=x.enchant?`<div class="armory-enchant ${x.enchantVerified?'':'pending'}">Enchant: ${esc(x.enchant)}</div>`:'<div class="armory-enchant muted">Enchant: —</div>',gem='<div class="armory-gem muted">Gem: — · Classic Era fără socket</div>',skill=x.weaponSkill?`<div class="item-id">${esc(x.weaponSkill)}</div>`:'';
    return `<div class="armory-slot ${empty?'empty':''}"><div class="slot-icon">${empty?'—':esc(x.slot.slice(0,2).toUpperCase())}</div><div class="slot-copy"><div class="slot-label">${esc(x.slot)}</div><div class="item-name">${esc(x.name)}</div><div class="item-id">${x.id?'Item #'+x.id:'slot liber'}</div>${skill}${enchant}${gem}</div><div class="verify-dot ${x.verified?'ok':'warn'}"></div></div>`;
  }
  function renderOne(p){
    const s=read(p),root=$(p+'Armory');if(!root)return;
    const slots=A.armoryFor(s),audit=A.audit(s),model=A.statModel(s),talent=T?.auditSelection(s);
    if(!slots){root.innerHTML=`<div class="armory-empty"><b>Mini Armory blocat</b><span>Profilul exact pentru ${esc(s.class)} ${esc(s.spec)} / ${esc(s.race)} nu este încă încărcat.</span></div>`;return;}
    const stats=canonicalStats(s),badge=audit.pass?'pass':'fail',checks=(audit.checks||[]).map(c=>`<div class="audit-check ${c.pass?'ok':'bad'}"><span>${c.pass?'✓':'✕'} ${esc(c.name)}</span><b>${esc(c.value)}</b></div>`).join('');
    const buildStatus=talent?.pass?`${talent.build?.name} · ${talent.build?.points} · ${talent.kernelReady?'kernel active':'kernel locked'}`:'talent build unavailable';
    root.innerHTML=`<div class="armory-head"><div><h3>${esc(s.race)} ${esc(s.class)} · ${esc(s.spec)}</h3><span>${esc(s.gear)}</span></div><div class="audit-badge ${badge}">STAT AUDIT: ${audit.status}</div></div><div class="armory-meta"><b>Talent build:</b> ${esc(buildStatus)}<br><b>Main scaling:</b> ${esc(model?.primary||'—')}<br><span>${esc(audit.reason)}</span>${audit.warning?`<br><span class="amber">${esc(audit.warning)}</span>`:''}</div><div class="audit-checks">${checks}</div><div class="armory-slots">${slots.map(itemRow).join('')}</div><h4>Character Stats · după talent build</h4><div class="armory-stats">${stats.map(([k,v])=>`<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('')}</div><h4>Stat breakdown pe clasă</h4><div class="stat-breakdown">${(model?.lines||[]).map(x=>`<div><b>${esc(x.stat)}</b><span>${esc(x.effect)}</span></div>`).join('')}${model?.note?`<div class="amber">${esc(model.note)}</div>`:''}</div>`;
  }
  function render(){renderOne('a');renderOne('b');}
  ['ac','as','ar','ag','abuild','bc','bs','br','bg','bbuild'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(render,0)));
  render();
  window.WOW_ARMORY_UI={render,version:'0.17'};
})();
