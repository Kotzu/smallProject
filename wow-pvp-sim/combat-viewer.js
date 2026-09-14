(()=>{
  const $=id=>document.getElementById(id);
  const policies={
    rogue:{label:'Rogue · Subtlety',path:'combat/Rogue/Subtlety/ClassCombat.lua'},
    mage:{label:'Mage · Frost',path:'combat/Mage/Frost/ClassCombat.lua'},
    engine:{label:'Combat Engine',path:'combat/CombatEngine.lua'}
  };
  const selector=document.querySelector('.combat-selector');
  if(selector&&!selector.querySelector('[data-policy="engine"]')){
    const b=document.createElement('button');b.dataset.policy='engine';b.textContent='Combat Engine';selector.appendChild(b);
  }
  const esc=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  async function load(key){
    const p=policies[key];if(!p)return;
    document.querySelectorAll('.combat-selector button').forEach(b=>b.classList.toggle('active',b.dataset.policy===key));
    $('combatPath').textContent=p.path;
    $('combatCode').textContent='Încarc '+p.path+'…';
    try{
      const r=await fetch(p.path+'?v='+Date.now(),{cache:'no-store'});
      if(!r.ok)throw new Error('HTTP '+r.status);
      const text=await r.text();$('combatCode').innerHTML=esc(text);
    }catch(err){$('combatCode').textContent='Nu pot încărca fișierul Lua: '+err;}
  }
  document.querySelectorAll('.combat-selector button').forEach(b=>b.addEventListener('click',()=>load(b.dataset.policy)));
  load('rogue');
  window.WOW_COMBAT_VIEWER={load,policies,version:'0.14'};
})();
