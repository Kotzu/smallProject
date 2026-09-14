(()=>{
  const $=id=>document.getElementById(id);
  const policies={
    rogue:{label:'Rogue',path:'combat/Rogue/ClassCombat.lua',status:'ACTIVE'},
    mage:{label:'Mage',path:'combat/Mage/ClassCombat.lua',status:'ACTIVE'},
    warrior:{label:'Warrior',path:'combat/Warrior/ClassCombat.lua',status:'LOCKED'},
    paladin:{label:'Paladin',path:'combat/Paladin/ClassCombat.lua',status:'LOCKED'},
    hunter:{label:'Hunter',path:'combat/Hunter/ClassCombat.lua',status:'LOCKED'},
    priest:{label:'Priest',path:'combat/Priest/ClassCombat.lua',status:'LOCKED'},
    shaman:{label:'Shaman',path:'combat/Shaman/ClassCombat.lua',status:'LOCKED'},
    warlock:{label:'Warlock',path:'combat/Warlock/ClassCombat.lua',status:'LOCKED'},
    druid:{label:'Druid',path:'combat/Druid/ClassCombat.lua',status:'LOCKED'},
    engine:{label:'Combat Engine',path:'combat/CombatEngine.lua',status:'ENGINE'}
  };
  const selector=document.querySelector('.combat-selector');
  if(selector){
    selector.innerHTML='';
    Object.entries(policies).forEach(([key,p])=>{
      const b=document.createElement('button');b.dataset.policy=key;b.textContent=p.label+(p.status==='LOCKED'?' · locked':'');
      selector.appendChild(b);
    });
  }
  const esc=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  async function load(key){
    const p=policies[key];if(!p)return;
    document.querySelectorAll('.combat-selector button').forEach(b=>b.classList.toggle('active',b.dataset.policy===key));
    $('combatPath').textContent=p.path+' · '+p.status;
    $('combatCode').textContent='Încarc '+p.path+'…';
    try{
      const r=await fetch(p.path+'?v='+Date.now(),{cache:'no-store'});
      if(!r.ok)throw new Error('HTTP '+r.status);
      const text=await r.text();$('combatCode').innerHTML=esc(text);
    }catch(err){$('combatCode').textContent='Nu pot încărca fișierul Lua: '+err;}
  }
  document.querySelectorAll('.combat-selector button').forEach(b=>b.addEventListener('click',()=>load(b.dataset.policy)));
  load('rogue');
  window.WOW_COMBAT_VIEWER={load,policies,version:'0.15'};
})();
