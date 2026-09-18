(function(){
  const $=id=>document.getElementById(id);
  let last=null,timer=null,attempts=0;

  function config(){
    return window.WOW_APP?.config?.()||null;
  }
  function stableSignature(r){
    return JSON.stringify({winner:r?.winner,duration:r?.duration,final:r?.final,timeline:(r?.timeline||[]).map(e=>[e.tMs,e.actor,e.kind,e.text])});
  }
  function check(name,pass,details){return{name,pass:!!pass,details};}
  function run(){
    const E=window.WOW_FOREVER_COMBAT_ENGINE,D=window.WOW_FOREVER_COMBAT_DATA,P=window.WOW_FOREVER_COMBAT_POLICIES,c=config();
    if(!E||!D||!P||!c){return null;}
    const gate=E.supported(c),checks=[];
    checks.push(check('Reference matchup gate',gate.ready,gate.ready?'Undead Subtlety Rogue vs Gnome Frost Mage · gear + 51-point builds':gate.issues.join(' · ')));
    if(!gate.ready){
      last={pass:false,checks,gate,status:'WAITING_CONFIG'};window.WOW_FOREVER_COMBAT_QA=last;return last;
    }
    const a=E.run(1337,c),b=E.run(1337,c),alt=E.run(7331,c);
    checks.push(check('Deterministic seed',stableSignature(a)===stableSignature(b),a.winner+' · '+a.duration.toFixed(2)+'s · '+a.timeline.length+' events'));
    checks.push(check('Fight terminates',a.winner==='Rogue'||a.winner==='Mage'||a.winner==='Timeout',a.winner+' @ '+a.duration.toFixed(2)+'s'));
    checks.push(check('Finite final state',Number.isFinite(a.final?.rogue?.hp)&&Number.isFinite(a.final?.mage?.hp)&&Number.isFinite(a.final?.rogue?.energy)&&Number.isFinite(a.final?.mage?.mana),JSON.stringify(a.final)));
    checks.push(check('Timeline produced',a.timeline?.length>5,a.timeline?.length+' events'));
    checks.push(check('Decision trace produced',a.decisionTrace?.length>10,a.decisionTrace?.length+' decisions'));
    checks.push(check('Rogue expert layers active',a.decisionTrace?.some(x=>x.actor==='Rogue'&&['CONTROL','DEADLINE_INTERRUPT','DAMAGE','MOBILITY','HOLD','RESET','KILL'].includes(x.layer)), 'stateful Rogue policy'));
    checks.push(check('Mage expert layers active',a.decisionTrace?.some(x=>x.actor==='Mage'&&['CONTROL','DEFENSIVE','DAMAGE','MOBILITY','HOLD','EMERGENCY'].includes(x.layer)), 'stateful Mage policy'));
    checks.push(check('Premeditation opener path',a.timeline?.some(x=>x.text?.includes('Premeditation')), 'Premeditation observed'));
    checks.push(check('Cheap Shot opener path',a.timeline?.some(x=>x.text?.includes('Cheap Shot')), 'Cheap Shot observed'));
    checks.push(check('Mage Blink response',a.timeline?.some(x=>x.text?.includes('Blink')), 'Blink observed'));
    checks.push(check('Reference status is explicit',a.status==='FOREVER_REFERENCE_MODEL'&&a.certifiedParity===false,a.status+' · certifiedParity='+a.certifiedParity));
    checks.push(check('Provisional mechanics disclosed',(a.metrics?.provisionalRulesUsed||[]).length>0,(a.metrics?.provisionalRulesUsed||[]).join(' · ')));
    checks.push(check('Different seed executes',alt?.seed===7331&&alt?.timeline?.length>5,alt?.winner+' · '+alt?.timeline?.length+' events'));
    const failed=checks.filter(x=>!x.pass);
    last={pass:failed.length===0,passed:checks.length-failed.length,failed:failed.length,checks,gate,sample:{winner:a.winner,duration:a.duration,events:a.timeline.length,final:a.final,provisional:a.metrics.provisionalRulesUsed},status:failed.length?'FAIL':'REFERENCE_READY'};
    window.WOW_FOREVER_COMBAT_QA=last;
    document.dispatchEvent(new CustomEvent('wow-forever-combat-qa',{detail:last}));
    render(last);
    return last;
  }
  function render(q){
    const root=$('qaReport');if(!root||!q)return;
    root.querySelector('.forever-combat-qa-block')?.remove();
    const s=document.createElement('section');s.className='forever-combat-qa-block';
    s.innerHTML='<div class="duel-summary"><div class="'+(q.pass?'winner':'red')+'">FOREVER COMBAT REFERENCE QA '+(q.pass?'PASS':'FAIL')+' · '+(q.passed||0)+'/'+(q.checks?.length||0)+'</div><div class="result-meta">Functional simulation is a REFERENCE MODEL. Client spell/talent data are Forever beta; inherited combat-table/stat assumptions remain provisional.</div></div><div class="rule-grid" style="margin-top:10px">'+(q.checks||[]).map(c=>'<div class="rule-card"><h3 class="'+(c.pass?'green':'red')+'">'+(c.pass?'✓':'✗')+' '+c.name+'</h3><p>'+String(c.details??'')+'</p></div>').join('')+'</div>';
    root.prepend(s);
  }
  function schedule(delay=80){
    clearTimeout(timer);timer=setTimeout(()=>{
      const q=run();
      if((!q||q.status==='WAITING_CONFIG')&&attempts++<12)schedule(150);
    },delay);
  }
  document.addEventListener('wow-forever-talents-ready',()=>schedule(150));
  document.addEventListener('wow-forever-build-changed',e=>{if(e.detail?.player==='a'||e.detail?.player==='b')schedule(80);});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>schedule(200),{once:true});else schedule(200);
  window.WOW_FOREVER_COMBAT_QA_RUN=run;
})();