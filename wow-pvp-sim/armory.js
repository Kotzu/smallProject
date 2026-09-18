(function(){
  const $=id=>document.getElementById(id);
  const DB=()=>window.WOW_FOREVER_ARMORY_DATA;
  const F=()=>window.WOW_FOREVER_TALENTS;
  const B=()=>window.WOW_FOREVER_BUILDS;
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const LEFT=['Head','Neck','Shoulder','Back','Chest','Wrist','Hands','Waist'];
  const RIGHT=['Legs','Feet','Finger 1','Finger 2','Trinket 1','Trinket 2','Ranged'];
  const WEAPONS=['Main Hand','Off Hand'];
  const RESOURCE={Rogue:'Energy',Warrior:'Rage',Hunter:'Mana',Mage:'Mana',Paladin:'Mana',Priest:'Mana',Shaman:'Mana',Warlock:'Mana',Druid:'Mana'};

  function read(p){return{class:$(p+'c')?.value||'—',spec:$(p+'s')?.value||'—',race:$(p+'r')?.value||'—',gear:$(p+'g')?.value||'Forever PvP Loadout'};}
  function talentState(p,s){
    const audit=B()?.audit?.(p,s.class)||{points:0,remaining:51,pass:false,issues:[]};
    const info=F()?.classInfo?.(s.class),trees={};
    for(const [name,id] of Object.entries(info?.treeIds||{}))trees[name]=B()?.pointsInTree?.(p,s.class,id)||0;
    return{...audit,trees,db:F()?.db||null};
  }
  function factRows(i){
    if(!i)return[];
    const x=[];
    if(i.armor)x.push(i.armor+' Armor');
    if(i.str)x.push('+'+i.str+' Strength');if(i.agi)x.push('+'+i.agi+' Agility');if(i.sta)x.push('+'+i.sta+' Stamina');if(i.int)x.push('+'+i.int+' Intellect');if(i.spi)x.push('+'+i.spi+' Spirit');
    if(i.ap)x.push('+'+i.ap+' Attack Power');if(i.hit)x.push('+'+i.hit+'% Hit');if(i.crit)x.push('+'+i.crit+'% Crit');
    if(i.spellPower)x.push('+'+i.spellPower+' Spell Damage');if(i.spellHit)x.push('+'+i.spellHit+'% Spell Hit');if(i.spellCrit)x.push('+'+i.spellCrit+'% Spell Crit');if(i.spellPen)x.push('+'+i.spellPen+' Spell Penetration');
    if(i.dodge)x.push('+'+i.dodge+'% Dodge');if(i.shadowRes)x.push('+'+i.shadowRes+' Shadow Resistance');
    if(i.weapon){let w=i.weapon.type+': '+i.weapon.minDamage+'–'+i.weapon.maxDamage+' Damage';if(i.weapon.schoolMin)x.push('+'+i.weapon.schoolMin+'–'+i.weapon.schoolMax+' '+(i.weapon.school||'')+' Damage');x.push(w+' · '+Number(i.weapon.speed).toFixed(2)+' Speed · '+Number(i.weapon.dps).toFixed(2)+' DPS');}
    if(i.special)x.push(i.special);if(i.useEffect)x.push('Use: '+i.useEffect+(i.cooldownSec?' · '+(i.cooldownSec/60)+' min cooldown':''));
    if(i.set)x.push('Set: '+i.set);
    return x;
  }
  function itemLink(i,icon=false){
    if(!i)return icon?'<div class="armory-item-icon forever-slot-icon"><span>—</span></div>':'<span class="armory-item-name empty-name">Empty</span>';
    const attr='href="'+esc(i.source)+'" data-wowhead="item='+i.id+'&domain=forever" target="_blank" rel="noopener"';
    return icon?'<a class="armory-item-icon quality-'+esc(i.quality)+'" '+attr+'><span class="slot-fallback">'+esc(i.slot.slice(0,2).toUpperCase())+'</span></a>':'<a class="armory-item-name quality-'+esc(i.quality)+'" '+attr+'>'+esc(i.name)+'</a>';
  }
  function tooltip(i,e,slot){
    if(!i)return '<div class="armory-native-tooltip forever-tooltip"><div class="tt-name">'+esc(slot)+'</div><div class="tt-verified">Verified empty slot for this two-hand loadout.</div></div>';
    const ef=e?'<div class="tt-enchant">'+esc(e.name)+' · '+esc(e.effect)+'</div>':'';
    return '<div class="armory-native-tooltip"><div class="tt-name quality-'+esc(i.quality)+'">'+esc(i.name)+'</div>'+(i.itemLevel?'<div class="tt-ilvl">Item Level '+i.itemLevel+'</div>':'')+'<div class="tt-slot">'+esc(slot)+'</div>'+factRows(i).map(v=>'<div>'+esc(v)+'</div>').join('')+ef+'<div class="tt-id">Item #'+i.id+'</div><div class="tt-verified">✓ Verified WoW Forever record</div></div>';
  }
  function copy(i,e,slot,emptyVerified){
    if(!i)return '<div class="paperdoll-slot-label">'+esc(slot)+'</div><div class="armory-item-name empty-name">'+(emptyVerified?'Empty (2H weapon)':'—')+'</div><div class="paperdoll-ilvl">'+(emptyVerified?'Verified loadout state':'No verified Forever item')+'</div>';
    return '<div class="paperdoll-slot-label">'+esc(slot)+'</div>'+itemLink(i,false)+(i.itemLevel?'<div class="paperdoll-ilvl">Item Level '+i.itemLevel+'</div>':'')+(e?'<div class="paperdoll-enchant">✦ '+esc(e.name)+'</div><div class="paperdoll-enchant-effect">'+esc(e.effect)+'</div>':'<div class="paperdoll-enchant muted">Enchant —</div>');
  }
  function slotCard(x,side){
    const i=x.item,e=x.enchant,verified=i||x.emptyVerified;
    return '<div class="paperdoll-slot '+side+' '+(verified?'forever-verified':'forever-unverified')+'" data-slot="'+esc(x.slot)+'">'+
      (side==='right'?'<div class="paperdoll-slot-copy">'+copy(i,e,x.slot,x.emptyVerified)+'</div>':'')+
      '<div class="paperdoll-icon-wrap">'+itemLink(i,true)+tooltip(i,e,x.slot)+'</div>'+
      (side!=='right'?'<div class="paperdoll-slot-copy">'+copy(i,e,x.slot,x.emptyVerified)+'</div>':'')+
      '</div>';
  }
  function model(s,t,a){
    const icon='https://wow.zamimg.com/images/wow/icons/large/classicon_'+encodeURIComponent(String(s.class).toLowerCase())+'.jpg';
    const dist=Object.entries(t.trees).map(([n,v])=>n+' '+v).join(' / ')||'0/51';
    return '<div class="paperdoll-model '+esc(String(s.class).toLowerCase())+' forever-model"><div class="paperdoll-glow"></div><div class="paperdoll-character">'+
      '<div class="silhouette-head"></div><div class="silhouette-body"></div><div class="silhouette-arm left"></div><div class="silhouette-arm right"></div><div class="silhouette-leg left"></div><div class="silhouette-leg right"></div>'+
      '<img class="paperdoll-class-icon" src="'+icon+'" alt="'+esc(s.class)+'" loading="lazy"></div>'+
      '<div class="paperdoll-model-copy"><div class="paperdoll-level">Level 60 · WoW Forever</div><strong>'+esc(s.race)+' '+esc(s.class)+'</strong><span>'+esc(s.spec)+'</span><span>'+esc(dist)+' · '+t.points+'/51</span></div>'+
      '<div class="armory-audit-pill '+(a.gearIdentityPass?'pass':'fail')+'">'+(a.gearIdentityPass?'GEAR VERIFIED':'PROFILE LOCKED')+'</div></div>';
  }
  function gearContributionRows(t){
    const c=t.combined;
    return [
      ['Armor',c.armor],['Strength',c.str],['Agility',c.agi],['Stamina',c.sta],['Intellect',c.int],['Spirit',c.spi],
      ['Attack Power',c.ap],['Hit',c.hit+'%'],['Crit',c.crit+'%'],['Spell Damage',c.spellPower],['Frost Damage',c.frostPower],
      ['Spell Hit',c.spellHit+'%'],['Spell Crit',c.spellCrit+'%'],['Spell Penetration',c.spellPen],['Dodge',c.dodge+'%'],['Shadow Resist',c.shadowRes],['All Resist',c.resAll],['Direct Health',c.health],['Ranged +Damage',c.rangedDamage]
    ].filter(([,v])=>v!==0&&v!=='0%');
  }
  function finalStats(s){
    const names=['Health',RESOURCE[s.class]||'Resource','Strength','Agility','Stamina','Intellect','Spirit','Attack Power','Spell Power','Armor','Hit','Crit','Dodge','Spell Penetration'];
    return names.map(n=>'<div><span>'+esc(n)+'</span><b>—</b></div>').join('');
  }
  function auditPanel(s,t,a){
    const talentOk=t.points===51&&t.pass;
    const checks=[
      ['Forever talent dataset',F()?.status==='ready','db '+(t.db||'—')],
      ['Talent allocation',talentOk,t.points+'/51'],
      ['Equipment identity',a.gearIdentityPass,(a.verifiedItems+a.emptyVerified)+'/'+a.modeledSlots+' slots'],
      ['Verified enchants',a.totalEnchants===a.verifiedEnchants,a.verifiedEnchants+'/'+a.totalEnchants],
      ['Final derived stats',false,'gated until Forever base-stat/scaling audit'],
      ['Fight eligibility',false,'LOCKED until CombatEngine parity']
    ];
    return '<details class="armory-integrity" open><summary><span>WoW Forever data integrity</span><b class="'+(a.gearIdentityPass?'green':'red')+'">ARMORY '+(a.gearIdentityPass?'GEAR PASS':'LOCKED')+'</b></summary>'+
      '<div class="armory-integrity-copy">Items and enchants are Forever-sourced. Character totals stay “—” until Forever base stats and class conversions are independently verified.</div>'+
      '<div class="audit-checks">'+checks.map(([n,p,v])=>'<div class="audit-check '+(p?'ok':'bad')+'"><span>'+(p?'✓':'✕')+' '+esc(n)+'</span><b>'+esc(v)+'</b></div>').join('')+'</div></details>';
  }
  function renderOne(p){
    const root=$(p+'Armory');if(!root)return;
    const s=read(p),db=DB(),profile=db?.profileFor?.(s),slots=db?.slotsFor?.(s)||[],a=db?.audit?.(s)||{gearIdentityPass:false,verifiedItems:0,emptyVerified:0,modeledSlots:17,verifiedEnchants:0,totalEnchants:0},t=talentState(p,s);
    if(!profile){
      root.innerHTML='<div class="armory-empty"><b>Forever Armory profile locked</b><span>'+esc(s.race)+' '+esc(s.class)+' '+esc(s.spec)+' does not yet have a verified equipment reference profile. Talent tree remains available below.</span><div class="blizzard-armory"><div class="armory-talent-anchor"></div></div></div>';return;
    }
    const by=Object.fromEntries(slots.map(x=>[x.slot,x])),tot=db.totalsFor(s),gearRows=gearContributionRows(tot);
    root.innerHTML='<div class="blizzard-armory forever-armory">'+
      '<header class="blizzard-armory-header"><div class="armory-identity"><div class="armory-level-badge">60</div><div><h3>'+esc(s.race)+' '+esc(s.class)+'</h3><p>'+esc(s.spec)+' · '+esc(profile.label)+'</p></div></div><div class="armory-header-badges"><span class="build-pill '+(t.points===51?'ok':'warn')+'">TALENTS '+t.points+'/51</span><span class="audit-badge '+(a.gearIdentityPass?'pass':'fail')+'">'+(a.verifiedItems+a.emptyVerified)+'/17 SLOTS VERIFIED</span></div></header>'+
      '<div class="armory-subnav"><span class="active">CHARACTER</span><span>TALENTS · '+t.points+'/51</span><span>PVP LOADOUT · VERIFIED</span></div>'+
      '<div class="forever-source-strip"><span>Authority</span><b>WoW Forever / Wowhead Forever</b><em>No Classic item fallback.</em></div>'+
      '<div class="paperdoll-stage"><div class="paperdoll-column left">'+LEFT.map(x=>slotCard(by[x]||{slot:x},'left')).join('')+'</div>'+model(s,t,a)+'<div class="paperdoll-column right">'+RIGHT.map(x=>slotCard(by[x]||{slot:x},'right')).join('')+'</div><div class="paperdoll-weapons">'+WEAPONS.map(x=>slotCard(by[x]||{slot:x},'weapon')).join('')+'</div></div>'+
      '<div class="armory-quick-stats">'+[['Verified slots',(a.verifiedItems+a.emptyVerified)+'/17'],['Enchants',a.verifiedEnchants+'/'+a.totalEnchants],['Talents',t.points+'/51'],['Forever DB',t.db||'—'],['Combat','LOCKED'],['Final stats','—']].map(([k,v])=>'<div class="armory-quick-stat"><span>'+esc(k)+'</span><b>'+esc(v)+'</b></div>').join('')+'</div>'+
      '<div class="armory-details-grid"><div class="armory-stats-pane"><h3>Verified Gear Contributions</h3><div class="armory-stat-list">'+gearRows.map(([k,v])=>'<div><span>'+esc(k)+'</span><b>'+esc(v)+'</b></div>').join('')+'</div><h3 style="margin-top:14px">Final Character Stats</h3><div class="armory-stat-list">'+finalStats(s)+'</div><div class="forever-unknown-note">Final totals are intentionally “—”: base stats and class conversion formulas must be verified specifically for WoW Forever before they become Armory authority.</div></div>'+
      '<div class="armory-build-pane"><h3>Talent Build</h3><div class="armory-build-card"><span>WoW Forever</span><strong>'+t.points+'/51 points</strong><small>'+Object.entries(t.trees).map(([n,v])=>esc(n)+' '+v).join(' · ')+'</small></div><h3>Loadout Audit</h3><div class="armory-scaling"><div><b>Items</b><span>'+a.verifiedItems+' verified Forever item records</span></div><div><b>Empty slots</b><span>'+a.emptyVerified+' verified empty (two-hand loadout)</span></div><div><b>Enchants</b><span>'+a.verifiedEnchants+' verified Forever effects</span></div><div><b>Item tooltips</b><span>Local strict facts + Wowhead Forever links</span></div></div></div></div>'+
      auditPanel(s,t,a)+
      '<div class="armory-footnote">Armory surface is Forever-only. Gear identity, item stats and listed enchant effects are verified from Forever pages. Combat remains locked until derived character stats and combat formulas pass their own Forever audits.</div></div>';
    setTimeout(()=>{try{window.$WowheadPower?.refreshLinks?.();}catch(_e){}try{window.WH?.Tooltips?.refreshLinks?.();}catch(_e){}window.WOW_ARMORY_TALENTS?.render?.();},40);
  }
  function render(){renderOne('a');renderOne('b');}
  ['ac','as','ar','ag','bc','bs','br','bg'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(render,0)));
  document.addEventListener('wow-forever-talents-ready',()=>setTimeout(render,0));
  document.addEventListener('wow-forever-build-changed',e=>{if(e.detail?.player==='a'||e.detail?.player==='b')setTimeout(render,0);});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',render,{once:true});else render();
  window.WOW_ARMORY_UI={render,version:'0.41-forever-armory-items-enchants'};
})();