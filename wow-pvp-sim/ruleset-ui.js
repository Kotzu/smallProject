(function(){
  const $=id=>document.getElementById(id);
  const FIGHT_IDS=['runBtn','batch1Btn','batchBtn','batch100Btn','fightRunBtn'];
  let announced=false,timer=null;

  function config(){return window.WOW_APP?.config?.();}
  function refresh(){
    document.documentElement.dataset.ruleset='forever';
    document.documentElement.dataset.project='wow-forever-only';
    const qa=window.WOW_FOREVER_COMBAT_QA,engine=window.WOW_FOREVER_COMBAT_ENGINE;
    const gate=engine?.supported?.(config())||{ready:false,issues:['Reference engine loading']};
    const ready=qa?.pass===true&&gate.ready===true;
    FIGHT_IDS.forEach(id=>{const el=$(id);if(el)el.disabled=!ready;});
    const reason=$('gateReason');
    if(reason){
      if(ready)reason.innerHTML='<span class="green">FOREVER REFERENCE SIM READY</span> · <span class="amber">not parity-certified</span> · beta-client spells/talents + explicitly disclosed provisional combat-table/stat assumptions.';
      else reason.innerHTML='<span class="amber">REFERENCE SIM LOCKED</span> · '+[...(gate.issues||[]),qa&&!qa.pass?'combat QA failed':''].filter(Boolean).join(' · ');
    }
    if(!announced){announced=true;document.dispatchEvent(new CustomEvent('wow-ruleset-changed',{detail:{mode:'forever'}}));}
    document.dispatchEvent(new CustomEvent('wow-forever-combat-gate',{detail:{ready,gate,qa}}));
    return ready;
  }
  function schedule(delay=0){clearTimeout(timer);timer=setTimeout(refresh,delay);}
  function start(){
    FIGHT_IDS.forEach(id=>{const el=$(id);if(el)el.disabled=true;});
    ['ac','as','ar','ag','bc','bs','br','bg'].forEach(id=>$(id)?.addEventListener('change',()=>schedule(50)));
    document.addEventListener('wow-forever-build-changed',()=>schedule(50));
    document.addEventListener('wow-forever-combat-qa',()=>schedule(0));
    document.addEventListener('wow-forever-combat-gate-refresh',()=>schedule(0));
    schedule(100);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
  window.WOW_RULESET={mode:'forever',isForever:()=>true,apply:()=>schedule(0),refresh,version:'0.50-forever-reference-gate'};
})();