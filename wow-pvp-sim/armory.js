(function(){
  const A=window.WOW_ARMORY,W=window.WOW_STATS,D=window.WOW_DATA,CE=window.WOW_CHARACTER_ENGINE,CD=window.WOW_CHARACTER_DATA;
  const $=id=>document.getElementById(id);
  const read=p=>({class:$(p+'c')?.value,spec:$(p+'s')?.value,race:$(p+'r')?.value,gear:$(p+'g')?.value});
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function canonicalStats(s){
    if(A.isRogue(s)){
      const P=D.profiles.rogue_subtlety_lvl60_pvp_bis_p6_baseline,r=CE.rogue60Baseline(CD.level60.undeadRogue,P);
      return [['STR',r.stats.str],['AGI',r.stats.agi],['STA',r.stats.sta],['INT',r.stats.int],['SPI',r.stats.spi],['HP',r.health],['Energy',100],['Melee AP',r.attackPower],['Armor',r.armor],['Hit',r.hitPct+'%'],['Shadow Resist',r.shadowResistance]];
    }
    if(A.isMage(s)){
      const p=D.pvpProfiles.mage_frost_gnome_p6_core,m=W.statModel?null:null;
      return [['STR',p.stats.strength],['AGI',p.stats.agility],['STA',p.stats.stamina],['INT',p.stats.intellect],['SPI',p.stats.spirit],['HP',p.stats.health],['Mana',p.stats.mana],['Spell Power',p.stats.spellDamage],['Spell Crit',p.stats.spellCritPct+'%'],['Spell Hit',p.stats.spellHitPct+'%'],['Spell Pen',p.stats.spellPen],['Armor',Math.trunc(p.stats.armorBeforeTalents+p.stats.intellect*.5)],['Dodge',p.stats.dodgePct+'%'],['Arcane Resist',p.stats.resist.arcane],['Fire Resist',p.stats.resist.fire],['Frost Resist',p.stats.resist.frost],['Nature Resist',p.stats.resist.nature],['Shadow Resist',p.stats.resist.shadow]];
    }
    return [];
  }
  function itemRow(x){
    const empty=!x.id;
    const enchant=x.enchant?`<div class="armory-enchant ${x.enchantVerified?'':'pending'}">Enchant: ${esc(x.enchant)}</div>`:'<div class="armory-enchant muted">Enchant: —</div>';
    const gem='<div class="armory-gem muted">Gem: — · Classic Era fără socket</div>';
    return `<div class="armory-slot ${empty?'empty':''}"><div class="slot-icon">${empty?'—':esc(x.slot.slice(0,2).toUpperCase())}</div><div class="slot-copy"><div class="slot-label">${esc(x.slot)}</div><div class="item-name">${esc(x.name)}</div><div class="item-id">${x.id?'Item #'+x.id:'slot liber'}</div>${enchant}${gem}</div><div class="verify-dot ${x.verified?'ok':'warn'}" title="${x.verified?'verified':'pending'}"></div></div>`;
  }
  function renderOne(p){
    const s=read(p),root=$(p+'Armory');if(!root)return;
    const slots=A.armoryFor(s),audit=A.audit(s),model=A.statModel(s);
    if(!slots){root.innerHTML=`<div class="armory-empty"><b>Mini Armory blocat</b><span>Profilul exact pentru ${esc(s.class)} ${esc(s.spec)} / ${esc(s.race)} nu este încă încărcat.</span></div>`;return;}
    const stats=canonicalStats(s);
    const badge=audit.pass?'pass':'fail';
    root.innerHTML=`
      <div class="armory-head"><div><h3>${esc(s.race)} ${esc(s.class)} · ${esc(s.spec)}</h3><span>${esc(s.gear)}</span></div><div class="audit-badge ${badge}">STAT AUDIT: ${audit.status}</div></div>
      <div class="armory-meta"><b>Main scaling:</b> ${esc(model?.primary||'—')}<br><span>${esc(audit.reason)}</span>${audit.warning?`<br><span class="amber">${esc(audit.warning)}</span>`:''}</div>
      <div class="armory-slots">${slots.map(itemRow).join('')}</div>
      <h4>Character Stats</h4><div class="armory-stats">${stats.map(([k,v])=>`<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('')}</div>
      <h4>Stat breakdown pe clasă</h4><div class="stat-breakdown">${(model?.lines||[]).map(x=>`<div><b>${esc(x.stat)}</b><span>${esc(x.effect)}</span></div>`).join('')}${model?.note?`<div class="amber">${esc(model.note)}</div>`:''}</div>`;
  }
  function render(){renderOne('a');renderOne('b');}
  ['ac','as','ar','ag','bc','bs','br','bg'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(render,0)));
  render();
})();