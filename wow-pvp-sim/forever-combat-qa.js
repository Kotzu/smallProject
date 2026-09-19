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
    checks.push(check('Current beta combat dataset',D.clientBuild==='1.60.1.69913',D.clientBuild+' · '+D.version));
    checks.push(check('Rogue poison beta refresh',D.abilities.Rogue['Crippling Poison']?.slowPct===50&&D.abilities.Rogue['Mind-numbing Poison']?.castTimeIncreasePct===40&&D.abilities.Rogue['Mind-numbing Poison']?.durationMs===10000,'Crippling 50%/12s · Mind-numbing +40%/10s'));
    checks.push(check('Mage spell beta refresh',D.abilities.Mage['Ice Lance']?.min===133&&D.abilities.Mage['Ice Lance']?.max===157&&D.abilities.Mage['Ice Barrier']?.absorb===811&&D.abilities.Mage['Fire Blast']?.max===474,'Ice Lance 133–157 · Barrier 811 · Fire Blast max 474'));
    checks.push(check('Forever talent beta refresh',D.talents.Rogue['Improved Eviscerate']?.evisDamageByRankPct?.[2]===13&&D.talents.Mage['Fingers of Frost']?.procChanceByRankPct?.[2]===30&&D.talents.Mage['Fingers of Frost']?.charges===1,'Improved Evis R2 13% · FoF R2 30% / 1 charge'));
    checks.push(check('Reference matchup gate',gate.ready,gate.ready?'Undead Subtlety Rogue vs Gnome Frost Mage · gear + 51-point builds':gate.issues.join(' · ')));
    if(!gate.ready){
      last={pass:false,checks,gate,status:'WAITING_CONFIG'};window.WOW_FOREVER_COMBAT_QA=last;return last;
    }
    const policyBase={
      nowMs:10000,range:4,memory:{fakeCastRestarts:0,fakeCasts:0},
      talentRank:()=>0,cooldownRemaining:()=>0,
      ready:()=>true,cost:name=>name==='Blink'?2100:name==='Kick'?25:name==='Frostbolt'?290:0,
      self:{energy:100,mana:6258,baseMana:6258,healthPct:100,comboPoints:0,iceBarrierAbsorb:811,manaShieldAbsorb:0,fingersOfFrostCharges:0},
      enemy:{healthPct:100,casting:false,castHighValue:false,stunDRMultiplier:1,incapDRMultiplier:1,disorientDRMultiplier:1}
    };
    const early=P.chooseRogue({...policyBase,self:{...policyBase.self},enemy:{...policyBase.enemy,casting:true,castHighValue:true,castSpell:'Frostbolt',castDurationMs:2500,castElapsedMs:100,castRemainingMs:2400}});
    checks.push(check('Rogue anti-fake HOLD policy',early.action==='HOLD'&&String(early.reason).includes('anti-fake'),early.action+' · '+early.reason));
    const emergency=P.chooseRogue({...policyBase,self:{...policyBase.self},enemy:{...policyBase.enemy,casting:true,castHighValue:true,castSpell:'Frostbolt',castDurationMs:2500,castElapsedMs:2320,castRemainingMs:180}});
    checks.push(check('Rogue emergency Kick policy',emergency.action==='Kick',emergency.action+' · '+emergency.reason));
    const mageBlink=P.chooseMage({...policyBase,ready:name=>name==='Blink',self:{...policyBase.self,mana:6258,baseMana:6258,stunned:true},enemy:{...policyBase.enemy},range:4});
    checks.push(check('Mage emergency Blink policy',mageBlink.action==='Blink',mageBlink.action+' · '+mageBlink.reason));
    const mageFake=P.chooseMage({...policyBase,ready:name=>name==='Frostbolt',self:{...policyBase.self,mana:6258,baseMana:6258,iceBarrierAbsorb:811},enemy:{...policyBase.enemy,kickReady:true,rooted:false},range:4,memory:{fakeCasts:0}});
    checks.push(check('Mage anti-Kick fake-cast policy',mageFake.action==='Frostbolt'&&Number(mageFake.fakeAtMs)>0,mageFake.action+' · fakeAtMs='+String(mageFake.fakeAtMs)));
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
    const smoke={Rogue:0,Mage:0,Timeout:0,maxDuration:0};
    for(let seed=1;seed<=20;seed++){
      const rr=E.run(seed,c,{compact:true});
      smoke[rr.winner]=(smoke[rr.winner]||0)+1;
      smoke.maxDuration=Math.max(smoke.maxDuration,rr.duration||0);
    }
    checks.push(check('20-seed termination smoke',smoke.Timeout===0,`Rogue ${smoke.Rogue} · Mage ${smoke.Mage} · Timeout ${smoke.Timeout} · max ${smoke.maxDuration.toFixed(1)}s`));
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
    s.innerHTML='<div class="duel-summary"><div class="'+(q.pass?'winner':'red')+'">FOREVER COMBAT REFERENCE QA '+(q.pass?'PASS':'FAIL')+' · '+(q.passed||0)+'/'+(q.checks?.length||0)+'</div><div class="result-meta">Functional simulation is a REFERENCE MODEL on beta client 1.60.1.69913. Inherited combat-table/stat/DR assumptions remain provisional and are surfaced explicitly.</div></div><div class="rule-grid" style="margin-top:10px">'+(q.checks||[]).map(c=>'<div class="rule-card"><h3 class="'+(c.pass?'green':'red')+'">'+(c.pass?'✓':'✗')+' '+c.name+'</h3><p>'+String(c.details??'')+'</p></div>').join('')+'</div>';
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