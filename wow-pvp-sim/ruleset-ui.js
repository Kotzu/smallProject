(function(){
  const $=id=>document.getElementById(id);
  const FIGHT_IDS=['runBtn','batch1Btn','batchBtn','batch100Btn','fightRunBtn','fightPlayBtn','fightPauseBtn','fightStepBtn'];
  let announced=false;
  function guardFightEvent(e){e.preventDefault();e.stopImmediatePropagation();}
  function apply(){
    document.documentElement.dataset.ruleset='forever';
    document.documentElement.dataset.project='wow-forever-only';
    FIGHT_IDS.forEach(id=>{const el=$(id);if(el)el.disabled=true;});
    const gate=$('gateReason');
    if(gate)gate.innerHTML='<span class="amber">WOW FOREVER ONLY · FIGHT LOCKED · Armory + talent builds are usable; combat unlocks only after full Forever CombatEngine parity.</span>';
    if(!announced){announced=true;document.dispatchEvent(new CustomEvent('wow-ruleset-changed',{detail:{mode:'forever'}}));}
  }
  function start(){
    FIGHT_IDS.forEach(id=>$(id)?.addEventListener('click',guardFightEvent,true));
    apply();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
  window.WOW_RULESET={mode:'forever',isForever:()=>true,apply,version:'0.40-forever-only-light'};
})();