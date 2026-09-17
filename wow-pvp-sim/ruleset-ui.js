(function(){
  const $=id=>document.getElementById(id);
  const PLAYER_IDS=['ac','as','ar','ag','abuild','bc','bs','br','bg','bbuild'];
  const FIGHT_IDS=['runBtn','batch1Btn','batchBtn','batch100Btn','fightRunBtn'];
  let lastMode='classic',timer=null;

  function ensureControl(){
    let select=$('rulesetMode');
    if(select)return select;
    const bar=document.querySelector('.duel-bar');if(!bar)return null;
    const label=document.createElement('label');
    label.className='ruleset-field';
    label.innerHTML='Ruleset<select id="rulesetMode"><option value="classic">Classic Era</option><option value="forever">WoW Forever</option></select>';
    bar.prepend(label);
    return $('rulesetMode');
  }
  function readPlayer(p){return{class:$(p+'c')?.value,spec:$(p+'s')?.value,race:$(p+'r')?.value,gear:$(p+'g')?.value,build:$(p+'build')?.value||null};}
  function classicReady(){
    try{
      const cfg={a:readPlayer('a'),b:readPlayer('b')};
      const gate=window.WOW_DUEL?.canRun?.(cfg),aa=window.WOW_ARMORY?.audit?.(cfg.a),ab=window.WOW_ARMORY?.audit?.(cfg.b);
      return {ready:!!gate?.ready&&!!aa?.pass&&!!ab?.pass,missing:[...(gate?.missing||[]),...(!aa?.pass?['Player A stat audit']:[]),...(!ab?.pass?['Player B stat audit']:[])]};
    }catch(err){return{ready:false,missing:[String(err?.message||err)]};}
  }
  function isForever(){return $('rulesetMode')?.value==='forever';}
  function guardFightEvent(e){if(!isForever())return;e.preventDefault();e.stopImmediatePropagation();}
  function apply(){
    const select=ensureControl();if(!select)return;
    const mode=select.value,forever=mode==='forever';
    document.documentElement.dataset.ruleset=mode;
    ['abuild','bbuild'].forEach(id=>{const el=$(id);if(el)el.disabled=forever;});
    const gate=$('gateReason');
    if(forever){
      FIGHT_IDS.forEach(id=>{const el=$(id);if(el)el.disabled=true;});
      if(gate)gate.innerHTML='<span class="amber">WOW FOREVER · FIGHT LOCKED · Talent trees/builds can be configured, but CombatEngine parity is not complete yet.</span>';
    }else{
      const state=classicReady();
      ['runBtn','batch1Btn','batchBtn','batch100Btn'].forEach(id=>{const el=$(id);if(el)el.disabled=!state.ready;});
      const fr=$('fightRunBtn');if(fr)fr.disabled=!state.ready;
      if(gate&&!state.ready)gate.textContent='STRICT DATA GATE: '+state.missing.join(' · ');
    }
    if(mode!==lastMode){lastMode=mode;document.dispatchEvent(new CustomEvent('wow-ruleset-changed',{detail:{mode}}));}
    window.WOW_ARMORY_UI?.render?.();
    window.WOW_ARMORY_TALENTS?.render?.();
  }
  function schedule(delay=0){clearTimeout(timer);timer=setTimeout(apply,delay);}
  function start(){
    const select=ensureControl();if(!select)return;
    select.addEventListener('change',()=>schedule(0));
    PLAYER_IDS.forEach(id=>$(id)?.addEventListener('change',()=>schedule(0)));
    FIGHT_IDS.forEach(id=>$(id)?.addEventListener('click',guardFightEvent,true));
    apply();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
  window.WOW_RULESET={get mode(){return $('rulesetMode')?.value||'classic';},isForever,apply:()=>schedule(0),version:'0.32'};
})();
