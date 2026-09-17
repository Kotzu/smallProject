(function(){
  const $=id=>document.getElementById(id);
  const PLAYER_IDS=['ac','as','ar','ag','abuild','bc','bs','br','bg','bbuild'];
  const FIGHT_IDS=['runBtn','batch1Btn','batchBtn','batch100Btn','fightRunBtn'];
  let timer=null,announced=false;

  function lockLegacyBuildSelectors(){
    ['abuild','bbuild'].forEach(id=>{
      const el=$(id);if(!el)return;
      el.disabled=true;
      el.setAttribute('aria-disabled','true');
      const label=el.closest('label');if(label)label.classList.add('legacy-build-select');
    });
  }
  function guardFightEvent(e){e.preventDefault();e.stopImmediatePropagation();}
  function apply(){
    document.documentElement.dataset.ruleset='forever';
    document.documentElement.dataset.project='wow-forever-only';
    lockLegacyBuildSelectors();
    FIGHT_IDS.forEach(id=>{const el=$(id);if(el)el.disabled=true;});
    const gate=$('gateReason');
    if(gate)gate.innerHTML='<span class="amber">WOW FOREVER ONLY · FIGHT LOCKED · Talent builds and Armory are being migrated to the live Forever dataset. Combat unlocks only after full Forever parity.</span>';
    if(!announced){announced=true;document.dispatchEvent(new CustomEvent('wow-ruleset-changed',{detail:{mode:'forever'}}));}
    window.WOW_ARMORY_UI?.render?.();
    window.WOW_ARMORY_TALENTS?.render?.();
  }
  function schedule(delay=0){clearTimeout(timer);timer=setTimeout(apply,delay);}
  function start(){
    document.getElementById('rulesetMode')?.closest('label')?.remove();
    PLAYER_IDS.forEach(id=>$(id)?.addEventListener('change',()=>schedule(0)));
    FIGHT_IDS.forEach(id=>$(id)?.addEventListener('click',guardFightEvent,true));
    apply();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
  window.WOW_RULESET={mode:'forever',isForever:()=>true,apply:()=>schedule(0),version:'0.33-forever-only'};
})();
