(function(){
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const SLOT_ORDER=['Head','Neck','Shoulder','Back','Chest','Wrist','Hands','Waist','Legs','Feet','Finger 1','Finger 2','Trinket 1','Trinket 2','Main Hand','Off Hand','Ranged'];
  const LEFT_SLOTS=['Head','Neck','Shoulder','Back','Chest','Wrist','Hands','Waist'];
  const RIGHT_SLOTS=['Legs','Feet','Finger 1','Finger 2','Trinket 1','Trinket 2','Ranged'];
  const WEAPON_SLOTS=['Main Hand','Off Hand'];
  const RESOURCE={Rogue:'Energy',Warrior:'Rage',Hunter:'Mana',Mage:'Mana',Paladin:'Mana',Priest:'Mana',Shaman:'Mana',Warlock:'Mana',Druid:'Mana'};
  const ARMOR={Rogue:'Leather',Warrior:'Plate',Hunter:'Mail',Mage:'Cloth',Paladin:'Plate',Priest:'Cloth',Shaman:'Mail',Warlock:'Cloth',Druid:'Leather'};

  function read(p){return{class:$(p+'c')?.value||'—',spec:$(p+'s')?.value||'—',race:$(p+'r')?.value||'—',gear:$(p+'g')?.value||'Forever PvP Loadout'};}
  function foreverBuild(p,s){
    const B=window.WOW_FOREVER_BUILDS,F=window.WOW_FOREVER_TALENTS;
    const audit=B?.audit?.(p,s.class)||{points:0,remaining:51,issues:['allocator unavailable'],pass:false};
    const selected=B?.selected?.(p,s.class)||[];
    const byTree={};
    const info=F?.classInfo?.(s.class);
    for(const [name,id] of Object.entries(info?.treeIds||{}))byTree[name]=B?.pointsInTree?.(p,s.class,id)||0;
    return{audit,selected,byTree,db:F?.db||null,status:F?.status||'loading'};
  }
  function auditForever(p,s,b){
    const talentReady=b.audit.points===51&&b.audit.pass;
    return{
      pass:false,status:'LOCKED',
      reason:'Forever gear + derived stats are not yet fully verified, so Armory is complete as a configuration surface but not combat-eligible.',
      checks:[
        {name:'Forever talent dataset',pass:b.status==='ready',value:b.status==='ready'?`db ${b.db}`:b.status},
        {name:'Talent allocation',pass:talentReady,value:`${b.audit.points}/51`},
        {name:'17 equipment slots',pass:false,value:'0/17 verified Forever records'},
        {name:'Enchant mapping',pass:false,value:'pending Forever verification'},
        {name:'Derived character stats',pass:false,value:'pending Forever verification'},
        {name:'Combat eligibility',pass:false,value:'LOCKED'}
      ]
    };
  }
  function slotShell(slot,side='left'){
    return `<div class="paperdoll-slot ${side} forever-unverified" data-slot="${esc(slot)}">
      ${side==='right'?`<div class="paperdoll-slot-copy">${slotCopy(slot)}</div>`:''}
      <div class="paperdoll-icon-wrap"><div class="armory-item-icon forever-slot-icon"><span>${esc(slot.slice(0,2).toUpperCase())}</span></div><div class="armory-native-tooltip forever-tooltip"><div class="tt-name">${esc(slot)}</div><div class="tt-slot">WoW Forever equipment slot</div><div class="tt-id">Item: —</div><div class="tt-verified">Not verified yet. No Classic item is substituted.</div></div></div>
      ${side!=='right'?`<div class="paperdoll-slot-copy">${slotCopy(slot)}</div>`:''}
    </div>`;
  }
  function slotCopy(slot){return `<div class="paperdoll-slot-label">${esc(slot)}</div><div class="armory-item-name empty-name">—</div><div class="paperdoll-ilvl">Forever item pending</div><div class="paperdoll-enchant muted">Enchant —</div>`;}
  function modelMarkup(s,b){
    const classKey=String(s.class).toLowerCase();
    const icon=`https://wow.zamimg.com/images/wow/icons/large/classicon_${encodeURIComponent(classKey)}.jpg`;
    const dist=Object.entries(b.byTree).map(([n,v])=>`${n} ${v}`).join(' / ')||'0/51';
    return `<div class="paperdoll-model ${classKey} forever-model">
      <div class="paperdoll-glow"></div>
      <div class="paperdoll-character">
        <div class="silhouette-head"></div><div class="silhouette-body"></div><div class="silhouette-arm left"></div><div class="silhouette-arm right"></div><div class="silhouette-leg left"></div><div class="silhouette-leg right"></div>
        <img class="paperdoll-class-icon" src="${icon}" alt="${esc(s.class)}" loading="lazy">
      </div>
      <div class="paperdoll-model-copy"><div class="paperdoll-level">Level 60 · WoW Forever</div><strong>${esc(s.race)} ${esc(s.class)}</strong><span>${esc(s.spec)}</span><span>${esc(dist)} · ${b.audit.points}/51 total</span></div>
      <div class="armory-audit-pill fail">FOREVER DATA LOCKED</div>
    </div>`;
  }
  function unknownStats(s){
    return [
      ['Health','—','resource'],[RESOURCE[s.class]||'Resource','—','resource'],
      ['Strength','—','primary'],['Agility','—','primary'],['Stamina','—','primary'],['Intellect','—','primary'],['Spirit','—','primary'],
      ['Attack Power','—','offense'],['Spell Power','—','offense'],['Hit','—','offense'],['Crit','—','offense'],['Expertise / Spell Pen','—','offense'],
      ['Armor','—','defense'],['Dodge','—','defense'],['Parry','—','defense'],
      ['Arcane Resist','—','resist'],['Fire Resist','—','resist'],['Frost Resist','—','resist'],['Nature Resist','—','resist'],['Shadow Resist','—','resist']
    ];
  }
  function groupedStats(rows){
    const order=[['resource','Resources'],['primary','Attributes'],['offense','Offense'],['defense','Defense'],['resist','Resistances']];
    return order.map(([key,title])=>{const group=rows.filter(x=>x[2]===key);return `<section class="armory-stat-section"><h4>${title}</h4><div class="armory-stat-list">${group.map(([k,v])=>`<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('')}</div></section>`;}).join('');
  }
  function quickStats(s){
    const items=[['Health','—'],[RESOURCE[s.class]||'Resource','—'],[s.class==='Mage'||s.class==='Priest'||s.class==='Warlock'?'Spell Power':'Attack Power','—'],['Crit','—'],['Hit','—'],['Armor','—']];
    return items.map(([k,v])=>`<div class="armory-quick-stat"><span>${esc(k)}</span><b>${v}</b></div>`).join('');
  }
  function auditMarkup(audit){
    return `<details class="armory-integrity" open><summary><span>Forever data integrity</span><b class="red">ARMORY: ${audit.status}</b></summary><div class="armory-integrity-copy">${esc(audit.reason)}</div><div class="audit-checks">${audit.checks.map(c=>`<div class="audit-check ${c.pass?'ok':'bad'}"><span>${c.pass?'✓':'✕'} ${esc(c.name)}</span><b>${esc(c.value)}</b></div>`).join('')}</div></details>`;
  }
  function buildSummary(b){
    const entries=Object.entries(b.byTree);
    return `<div class="armory-build-card"><span>WoW Forever Talent Build</span><strong>${b.audit.points}/51 points</strong><small>${entries.map(([n,v])=>`${esc(n)} ${v}`).join(' · ')||'No points allocated'} · Wowhead db ${esc(b.db||'loading')}</small></div>`;
  }
  function renderOne(p){
    const root=$(p+'Armory');if(!root)return;
    const s=read(p),b=foreverBuild(p,s),audit=auditForever(p,s,b),stats=unknownStats(s);
    root.innerHTML=`<div class="blizzard-armory forever-armory">
      <header class="blizzard-armory-header">
        <div class="armory-identity"><div class="armory-level-badge">60</div><div><h3>${esc(s.race)} ${esc(s.class)}</h3><p>${esc(s.spec)} · WoW Forever</p></div></div>
        <div class="armory-header-badges"><span class="build-pill ${b.audit.points===51?'ok':'warn'}">TALENTS ${b.audit.points}/51</span><span class="audit-badge fail">COMBAT LOCKED</span></div>
      </header>
      <div class="armory-subnav"><span class="active">CHARACTER</span><span>TALENTS · ${b.audit.points}/51</span><span>PVP LOADOUT · PENDING</span></div>
      <div class="forever-source-strip"><span>Source</span><b>Wowhead Forever talent db ${esc(b.db||'loading')}</b><em>Gear/stat values are never borrowed from Classic.</em></div>
      <div class="paperdoll-stage">
        <div class="paperdoll-column left">${LEFT_SLOTS.map(slot=>slotShell(slot,'left')).join('')}</div>
        ${modelMarkup(s,b)}
        <div class="paperdoll-column right">${RIGHT_SLOTS.map(slot=>slotShell(slot,'right')).join('')}</div>
        <div class="paperdoll-weapons">${WEAPON_SLOTS.map(slot=>slotShell(slot,'weapon')).join('')}</div>
      </div>
      <div class="armory-quick-stats">${quickStats(s)}</div>
      <div class="armory-details-grid">
        <div class="armory-stats-pane"><h3>Character Stats</h3>${groupedStats(stats)}<div class="forever-unknown-note">“—” means not verified for WoW Forever. It is intentionally not copied from Classic.</div></div>
        <div class="armory-build-pane"><h3>Specialization</h3>${buildSummary(b)}<h3>Loadout State</h3><div class="armory-scaling"><div><b>Armor</b><span>${esc(ARMOR[s.class]||'—')} class family; exact Forever items pending</span></div><div><b>Gear</b><span>17 slots modeled, 0 verified Forever item records</span></div><div><b>Enchants</b><span>Per-slot schema ready; values pending Forever verification</span></div><div><b>Talents</b><span>Live Forever tree + allocator active</span></div></div></div>
      </div>
      ${auditMarkup(audit)}
      <div class="armory-footnote">Armory UI is complete and Forever-only. Gear, enchants and derived stats will populate only from verified Forever records; until then they stay “—” and cannot unlock combat.</div>
    </div>`;
  }
  function render(){renderOne('a');renderOne('b');}
  ['ac','as','ar','ag','bc','bs','br','bg'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(render,0)));
  document.addEventListener('wow-forever-talents-ready',()=>setTimeout(render,0));
  document.addEventListener('wow-forever-build-changed',e=>{if(e.detail?.player==='a'||e.detail?.player==='b')setTimeout(render,0);});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',render,{once:true});else render();
  window.WOW_ARMORY_UI={render,version:'0.40-forever-only-complete-surface'};
})();