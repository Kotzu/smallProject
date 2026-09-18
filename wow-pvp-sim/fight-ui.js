(()=>{
  const $=id=>document.getElementById(id);
  const E=()=>window.WOW_FOREVER_COMBAT_ENGINE;
  const D=()=>window.WOW_FOREVER_COMBAT_DATA;
  let result=null,index=0,timer=null,speed=2,batchRunning=false;

  function cfg(){return window.WOW_APP?.config?.();}
  function setBar(id,value,max){const el=$(id);if(el)el.style.width=Math.max(0,Math.min(100,max?value/max*100:0))+'%';}
  function setText(id,v){const el=$(id);if(el)el.textContent=v;}
  function switchTab(id){
    document.querySelectorAll('.tabs button').forEach(x=>x.classList.toggle('active',x.dataset.tab===id));
    document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.id===id));
  }
  function buildName(p){
    const b=window.WOW_FOREVER_BUILDS?.get?.(p),pr=b?.preset;
    return pr?.label?pr.label+(pr.status==='CUSTOMIZED'?' · customized':''):'Custom Forever build';
  }
  function baseline(){
    const d=D()?.referenceProfiles;
    return{rogue:d?.Rogue||{health:1,maxEnergy:100},mage:d?.Mage||{health:1,mana:1}};
  }
  function currentGate(){
    const c=cfg(),engine=E(),qa=window.WOW_FOREVER_COMBAT_QA;
    const g=engine?.supported?.(c)||{ready:false,issues:['Combat engine loading']};
    if(!qa?.pass)return{ready:false,issues:[...(g.issues||[]),'Reference combat QA not passed']};
    return g;
  }
  function resetView(){
    stop();index=0;result=null;
    const b=baseline();
    setText('fightRogueBuild',buildName('a'));setText('fightMageBuild',buildName('b'));
    setText('fightRogueHp',b.rogue.health+' / '+b.rogue.health);setText('fightMageHp',b.mage.health+' / '+b.mage.health);
    setText('fightRogueRes',b.rogue.maxEnergy+' Energy');setText('fightMageRes',b.mage.mana+' Mana');
    setBar('fightRogueHpBar',b.rogue.health,b.rogue.health);setBar('fightMageHpBar',b.mage.health,b.mage.health);
    setBar('fightRogueResBar',b.rogue.maxEnergy,b.rogue.maxEnergy);setBar('fightMageResBar',b.mage.mana,b.mage.mana);
    setText('fightTime','0.0s');setText('fightAction','Reference simulation ready');
    const log=$('fightLiveLog');if(log)log.innerHTML='<div class="muted">Apasă Start Fight. Rezultatul este un model Forever beta/reference; mecanicile provizorii sunt listate în Technical.</div>';
    $('fightAnalysisModal')?.classList.add('hidden');
  }
  function applyState(e){
    const b=baseline(),s=e.state;if(!s)return;
    setText('fightRogueHp',s.rogueHp+' / '+b.rogue.health);setText('fightMageHp',s.mageHp+' / '+b.mage.health);
    setText('fightRogueRes',s.rogueEnergy+' Energy · '+s.rogueCp+' CP');setText('fightMageRes',s.mageMana+' Mana');
    setBar('fightRogueHpBar',s.rogueHp,b.rogue.health);setBar('fightMageHpBar',s.mageHp,b.mage.health);
    setBar('fightRogueResBar',s.rogueEnergy,b.rogue.maxEnergy);setBar('fightMageResBar',s.mageMana,b.mage.mana);
    setText('fightTime',Number(e.t||0).toFixed(1)+'s');setText('fightAction',e.actor+' · '+e.text+' · '+s.range+' yd');
  }
  function appendEvent(e){
    const row=document.createElement('div');row.className='fight-log-row '+(e.kind||'');
    row.innerHTML='<span>'+Number(e.t||0).toFixed(1)+'s</span><b>'+e.actor+'</b><em>'+e.text+'</em>';
    const root=$('fightLiveLog');root?.appendChild(row);if(root)root.scrollTop=root.scrollHeight;
  }
  function step(){
    if(!result||index>=result.timeline.length){finishPlayback();return;}
    const e=result.timeline[index++];applyState(e);appendEvent(e);
    if(index>=result.timeline.length)finishPlayback();
  }
  function play(){if(!result)return;stop();timer=setInterval(step,Math.max(45,340/speed));}
  function stop(){if(timer){clearInterval(timer);timer=null;}}
  function renderComplete(){
    stop();const root=$('fightLiveLog');if(root)root.innerHTML='';index=0;
    for(const e of result.timeline){applyState(e);appendEvent(e);index++;}
    finishPlayback();
  }
  function actionCounts(actor){
    const out={};for(const d of result?.decisionTrace||[])if(d.actor===actor&&d.action!=='HOLD')out[d.action]=(out[d.action]||0)+1;return out;
  }
  function factList(){
    const m=result.metrics||{},facts=[
      'Seed '+result.seed+' · '+result.duration.toFixed(2)+'s · '+result.timeline.length+' timeline events.',
      'Rogue damage: '+Math.round(m.rogue?.damage||0)+' · Mage damage: '+Math.round(m.mage?.damage||0)+'.',
      'Rogue: '+(m.rogue?.kicks||0)+' Kick interrupts · '+(m.rogue?.kidneys||0)+' Kidney Shots · '+(m.rogue?.resets||0)+' reset actions.',
      'Mage: '+(m.mage?.blinks||0)+' Blinks · '+(m.mage?.novas||0)+' Frost Novas · '+(m.mage?.fakeCasts||0)+' deliberate fake-casts · '+(m.mage?.iceBlocks||0)+' Ice Blocks.',
      'Provisional mechanics used: '+(m.provisionalRulesUsed||[]).join(', ')+'.'
    ];
    return facts;
  }
  function evidenceAnalysis(){
    const win=result.winner,lose=win==='Rogue'?'Mage':win==='Mage'?'Rogue':'Neither',rc=actionCounts('Rogue'),mc=actionCounts('Mage'),m=result.metrics||{};
    const why=[];
    if(win==='Rogue'){why.push('Rogue ended with '+result.final.rogue.hp+' HP while Mage reached 0 HP.');if(m.rogue?.kicks)why.push('Rogue denied '+m.rogue.kicks+' Mage cast(s) with Kick.');if(rc['Kidney Shot'])why.push('Rogue converted combo points into '+rc['Kidney Shot']+' Kidney control window(s).');}
    if(win==='Mage'){why.push('Mage ended with '+result.final.mage.hp+' HP while Rogue reached 0 HP.');if(m.mage?.blinks)why.push('Mage used Blink '+m.mage.blinks+' time(s) to break/control separation.');if(m.mage?.novas)why.push('Mage created '+m.mage.novas+' Frost Nova root window(s).');}
    if(win==='Timeout')why.push('Neither player reached 0 HP before the 120s scenario limit.');
    const hypotheses=[];
    if(lose==='Rogue'){
      if(!(m.rogue?.kicks))hypotheses.push('Policy hypothesis: inspect why no high-value Mage cast was converted into Kick; do not promote without paired-seed evidence.');
      if((m.rogue?.energyStarveAvoided||0)>10)hypotheses.push('Policy hypothesis: Rogue held Energy frequently; A/B-test the reserve threshold rather than removing reservation blindly.');
    }else if(lose==='Mage'){
      if(!(m.mage?.fakeCasts))hypotheses.push('Policy hypothesis: test more interrupt-bait opportunities against Rogue Kick.');
      if(!(m.mage?.iceBlocks))hypotheses.push('Policy hypothesis: inspect the Ice Block emergency threshold against the actual kill timeline.');
    }
    if(!hypotheses.length)hypotheses.push('No single policy defect is proven by one duel; compare paired seeds before changing ClassCombat thresholds.');
    return{win,lose,why,hypotheses};
  }
  function list(title,items,cls=''){return '<section class="fight-analysis-block '+cls+'"><h3>'+title+'</h3><ul>'+items.map(x=>'<li>'+x+'</li>').join('')+'</ul></section>';}
  function showAnalysis(){
    if(!result)return;let modal=$('fightAnalysisModal');
    if(!modal){
      modal=document.createElement('div');modal.id='fightAnalysisModal';modal.className='fight-modal hidden';
      modal.innerHTML='<div class="fight-modal-card"><button class="fight-modal-close" id="fightAnalysisClose">×</button><div id="fightAnalysisBody"></div><div class="fight-modal-actions"><button id="fightAnalysisAgain" class="fight-primary">Fight Again</button><button id="fightAnalysisCombat">Open Combat.lua</button><button id="fightAnalysisTalents">Open Talents</button></div></div>';
      document.body.appendChild(modal);
      $('fightAnalysisClose').onclick=()=>modal.classList.add('hidden');
      modal.addEventListener('click',e=>{if(e.target===modal)modal.classList.add('hidden');});
      $('fightAnalysisAgain').onclick=()=>{modal.classList.add('hidden');startFight(true);};
      $('fightAnalysisCombat').onclick=()=>{modal.classList.add('hidden');switchTab('combat');};
      $('fightAnalysisTalents').onclick=()=>{modal.classList.add('hidden');switchTab('talents');};
    }
    const a=evidenceAnalysis();
    $('fightAnalysisBody').innerHTML='<div class="fight-analysis-title"><span>Forever reference fight · '+result.duration.toFixed(2)+'s</span><strong>'+a.win.toUpperCase()+(a.win==='Timeout'?'':' WINS')+'</strong></div>'+
      '<div class="fight-build-line"><b>Builds:</b> Rogue '+buildName('a')+' · Mage '+buildName('b')+'</div>'+
      '<div class="fight-analysis-grid"><div>'+list('De ce a rezultat '+a.win,a.why,'winner-side')+'</div><div>'+list('Policy hypotheses pentru '+a.lose,a.hypotheses,'loser-side')+'</div></div>'+
      list('Fight facts',factList(),'facts')+
      '<div class="fight-policy-targets"><b>Model status:</b> FOREVER_REFERENCE_MODEL · client data '+result.clientBuild+' · certified parity: NO.<br><b>Policy files:</b> <code>combat/Rogue/ClassCombat.lua</code> · <code>combat/Mage/ClassCombat.lua</code></div>';
    modal.classList.remove('hidden');
  }
  function finishPlayback(){
    stop();if(!result)return;
    setText('fightAction','WINNER: '+result.winner+' · reference model');
    setText('fightRogueRes',result.final.rogue.energy+' Energy · '+result.final.rogue.comboPoints+' CP');
    setText('fightMageRes',result.final.mage.mana+' Mana');
    $('fightPlayBtn').disabled=false;$('fightStepBtn').disabled=false;
    showAnalysis();
  }
  function startFight(immediate=true){
    const gate=currentGate();
    if(!gate.ready){$('fightError').textContent='Fight blocat: '+(gate.issues||[]).join(' · ');return;}
    const seed=(Number($('duelCode').value)||1337)>>>0;
    const r=E().run(seed,cfg());
    if(r.error){$('fightError').textContent=r.error+': '+(r.missing||[]).join(' · ');return;}
    result=r;index=0;$('fightError').textContent='';switchTab('fight');
    const root=$('fightLiveLog');if(root)root.innerHTML='';
    setText('fightAction','Duel #'+seed+' calculated · '+r.timeline.length+' events');
    $('fightPlayBtn').disabled=false;$('fightPauseBtn').disabled=false;$('fightStepBtn').disabled=false;
    if(immediate)renderComplete();else play();
  }
  async function runBatch(count){
    if(batchRunning)return;const gate=currentGate();if(!gate.ready){$('fightError').textContent='Batch blocat: '+gate.issues.join(' · ');return;}
    batchRunning=true;const seed=(Number($('duelCode').value)||1337)>>>0;
    const buttons=['batch1Btn','batchBtn','batch100Btn'];buttons.forEach(id=>{if($(id))$(id).disabled=true;});
    const out=$('batchSummary');if(out)out.innerHTML='<div class="muted">Rulez '+count.toLocaleString('ro-RO')+' reference fights…</div>';
    try{
      const r=await E().batch(count,seed,cfg(),(done,total)=>{if(out)out.innerHTML='<div class="muted">Batch '+done.toLocaleString('ro-RO')+' / '+total.toLocaleString('ro-RO')+'…</div>';});
      if(r.error)throw new Error(r.error+': '+(r.missing||[]).join(' · '));
      if(out)out.innerHTML='<div class="duel-summary"><div><b>'+count.toLocaleString('ro-RO')+' reference fights</b> · Rogue '+r.Rogue+' ('+r.roguePct.toFixed(1)+'%) · Mage '+r.Mage+' ('+r.magePct.toFixed(1)+'%) · Timeout '+r.Timeout+' · avg '+r.avgDuration.toFixed(1)+'s</div><div class="result-meta">Nu interpreta win-rate-ul ca echilibru Forever până la parity completă a stat/combat table/DR.</div></div>';
    }catch(err){if(out)out.innerHTML='<div class="red">'+String(err.message||err)+'</div>';}
    finally{batchRunning=false;document.dispatchEvent(new Event('wow-forever-combat-gate-refresh'));}
  }

  $('fightRunBtn')?.addEventListener('click',()=>startFight(true));
  $('runBtn')?.addEventListener('click',()=>startFight(true));
  $('fightPlayBtn')?.addEventListener('click',()=>{if(result){const old=result;resetView();result=old;play();}});
  $('fightPauseBtn')?.addEventListener('click',stop);
  $('fightStepBtn')?.addEventListener('click',()=>{stop();step();});
  $('fightResetBtn')?.addEventListener('click',resetView);
  $('fightSpeed')?.addEventListener('change',e=>{speed=Number(e.target.value)||2;if(timer)play();});
  $('batch1Btn')?.addEventListener('click',()=>runBatch(1000));
  $('batchBtn')?.addEventListener('click',()=>runBatch(10000));
  $('batch100Btn')?.addEventListener('click',()=>runBatch(100000));
  document.addEventListener('wow-forever-build-changed',()=>{setText('fightRogueBuild',buildName('a'));setText('fightMageBuild',buildName('b'));});
  resetView();
  window.WOW_FIGHT_UI={startFight,runBatch,resetView,showAnalysis,version:'0.50-forever-reference'};
})();