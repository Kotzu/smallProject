(()=>{
  const $=id=>document.getElementById(id);
  const policies={
    rogue:{label:'Rogue · Forever expert',path:'combat/Rogue/ClassCombat.lua',status:'POLICY READY · KERNEL GATED'},
    mage:{label:'Mage',path:'combat/Mage/ClassCombat.lua',status:'MIGRATION'},
    warrior:{label:'Warrior',path:'combat/Warrior/ClassCombat.lua',status:'LOCKED'},
    paladin:{label:'Paladin',path:'combat/Paladin/ClassCombat.lua',status:'LOCKED'},
    hunter:{label:'Hunter',path:'combat/Hunter/ClassCombat.lua',status:'LOCKED'},
    priest:{label:'Priest',path:'combat/Priest/ClassCombat.lua',status:'LOCKED'},
    shaman:{label:'Shaman',path:'combat/Shaman/ClassCombat.lua',status:'LOCKED'},
    warlock:{label:'Warlock',path:'combat/Warlock/ClassCombat.lua',status:'LOCKED'},
    druid:{label:'Druid',path:'combat/Druid/ClassCombat.lua',status:'LOCKED'},
    talents:{label:'Forever Talent Builds',path:'combat/TalentBuilds.lua',status:'DATA'},
    racials:{label:'Forever Racials',path:'combat/ForeverRacials.lua',status:'DATA · GATED'},
    standard:{label:'ClassCombat Standard',path:'combat/CLASSCOMBAT_STANDARD.md',status:'ARCHITECTURE'},
    engine:{label:'Combat Engine',path:'combat/CombatEngine.lua',status:'FOREVER PARITY IN PROGRESS'}
  };
  const selector=document.querySelector('.combat-selector');
  if(selector){
    selector.innerHTML='';
    Object.entries(policies).forEach(([key,p])=>{
      const b=document.createElement('button');b.dataset.policy=key;b.textContent=p.label+(p.status==='LOCKED'?' · locked':'');selector.appendChild(b);
    });
  }
  const esc=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  async function load(key){
    const p=policies[key];if(!p)return;
    document.querySelectorAll('.combat-selector button').forEach(b=>b.classList.toggle('active',b.dataset.policy===key));
    $('combatPath').textContent=p.path+' · '+p.status;
    $('combatCode').textContent='Încarc '+p.path+'…';
    try{
      const res=await fetch(p.path+'?v='+Date.now(),{cache:'no-store'});
      if(!res.ok)throw new Error('HTTP '+res.status);
      $('combatCode').innerHTML=esc(await res.text());
    }catch(err){$('combatCode').textContent='Nu pot încărca fișierul: '+err;}
  }
  document.querySelectorAll('.combat-selector button').forEach(b=>b.addEventListener('click',()=>load(b.dataset.policy)));
  load('rogue');
  window.WOW_COMBAT_VIEWER={load,policies,version:'0.40-forever-source-viewer'};
})();