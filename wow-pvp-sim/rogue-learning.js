(()=>{
  const duel=window.WOW_DUEL;
  if(!duel?.comparePolicies||!duel?.defaultRoguePolicy)return;
  const KEY='wow-pvp-sim.rogue-learning.v017';
  const clone=x=>JSON.parse(JSON.stringify(x));
  const safeLoad=()=>{try{return JSON.parse(localStorage.getItem(KEY)||'null');}catch{return null;}};
  const safeSave=x=>{try{localStorage.setItem(KEY,JSON.stringify(x));}catch{}};
  const fresh=()=>({
    version:'0.17',generation:0,observedFights:0,rogueWins:0,rogueLosses:0,
    champion:clone(duel.defaultRoguePolicy),candidateIndex:0,candidate:null,evidence:null,
    history:[]
  });
  let state=safeLoad()||fresh();
  state.champion=duel.normalizeRoguePolicy(state.champion||duel.defaultRoguePolicy);

  const mutations=[
    ['kidneyMinCp',4,'try Kidney Shot at 4+ CP instead of always waiting for 5'],
    ['kidneyEnergyReserve',20,'keep 20 Energy after Kidney Shot requirement'],
    ['evisMinCp',4,'allow 4 CP Eviscerate when control timing favors damage'],
    ['executeEvisHpPct',25,'allow 4+ CP Eviscerate as execute below 25% target HP'],
    ['coldBloodMinCp',4,'allow Cold Blood setup from 4+ CP'],
    ['sprintMinRange',8,'hold Sprint until target creates a larger gap'],
    ['kickMinRemainingMs',300,'avoid spending Kick on casts that are effectively already finished'],
    ['hemoMinEnergy',55,'pool more Energy before Hemorrhage to preserve reaction budget']
  ];

  function candidateFor(champion,index){
    const [field,value,reason]=mutations[index%mutations.length];
    const p=duel.normalizeRoguePolicy({...champion,[field]:value,id:`rogue_learn_g${state.generation}_c${index}_${field}_${value}`,version:(champion.version||1)+1});
    return {policy:p,field,value,reason};
  }
  function ensureCandidate(){if(!state.candidate){state.candidate=candidateFor(state.champion,state.candidateIndex);state.evidence={tests:0,championWins:0,challengerWins:0,championScoreWeighted:0,challengerScoreWeighted:0,championHpWeighted:0,challengerHpWeighted:0};}return state.candidate;}

  function diagnose(result){
    const ev=result?.timeline||[];
    const mageCasts=ev.filter(e=>e.actor==='Mage'&&String(e.text).includes('Frostbolt cast started')).length;
    const kicks=ev.filter(e=>e.actor==='Rogue'&&String(e.text).includes('Kick')).length;
    const blinks=ev.filter(e=>e.actor==='Mage'&&String(e.text).includes('Blink')).length;
    const sprints=ev.filter(e=>e.actor==='Rogue'&&String(e.text).includes('Sprint')).length;
    const kidneys=ev.filter(e=>e.actor==='Rogue'&&String(e.text).includes('Kidney Shot')).length;
    const evis=ev.filter(e=>e.actor==='Rogue'&&String(e.text).includes('Eviscerate')).length;
    const reasons=[];
    if(result?.winner!=='Rogue'&&mageCasts>kicks)reasons.push('cast pressure not fully interrupted');
    if(result?.winner!=='Rogue'&&blinks>0&&sprints===0)reasons.push('range recovery was weak after Blink');
    if(result?.winner!=='Rogue'&&kidneys===0)reasons.push('no Kidney Shot control window landed');
    if(result?.winner!=='Rogue'&&evis===0)reasons.push('no Eviscerate conversion before death/timeout');
    return {mageCasts,kicks,blinks,sprints,kidneys,evis,reasons};
  }

  function accumulate(cmp){
    const n=cmp.count,e=state.evidence;
    e.tests+=n;
    e.championWins+=cmp.champion.wins.Rogue||0;
    e.challengerWins+=cmp.challenger.wins.Rogue||0;
    e.championScoreWeighted+=cmp.champion.score*n;
    e.challengerScoreWeighted+=cmp.challenger.score*n;
    e.championHpWeighted+=cmp.champion.avgRogueHpPct*n;
    e.challengerHpWeighted+=cmp.challenger.avgRogueHpPct*n;
  }

  function evaluatePromotion(){
    const e=state.evidence;if(!e||e.tests<1000)return {ready:false};
    const winDelta=e.challengerWins-e.championWins;
    const scoreDelta=(e.challengerScoreWeighted-e.championScoreWeighted)/e.tests;
    const hpDelta=(e.challengerHpWeighted-e.championHpWeighted)/e.tests;
    const promote=winDelta>=5||(winDelta>=0&&scoreDelta>1&&hpDelta>0.5);
    const record={generation:state.generation,candidate:clone(state.candidate),tests:e.tests,winDelta,scoreDelta:Number(scoreDelta.toFixed(4)),hpDelta:Number(hpDelta.toFixed(4)),promote};
    state.history.push(record);if(state.history.length>40)state.history.shift();
    if(promote){state.champion=clone(state.candidate.policy);state.generation++;state.candidateIndex=0;}
    else state.candidateIndex++;
    state.candidate=null;state.evidence=null;
    safeSave(state);
    return {ready:true,...record,champion:clone(state.champion)};
  }

  function trainChunk(cfg,seed,count=250){
    const c=ensureCandidate();
    const cmp=duel.comparePolicies(seed,count,cfg,state.champion,c.policy);
    if(cmp.error)return {error:cmp.error};
    accumulate(cmp);
    const promotion=evaluatePromotion();
    safeSave(state);
    return {candidate:clone(c),comparison:cmp,evidence:clone(state.evidence),promotion};
  }

  function observe(result,cfg){
    if(!result||result.error)return null;
    state.observedFights++;
    if(result.winner==='Rogue')state.rogueWins++;else if(result.winner==='Mage')state.rogueLosses++;
    const diagnosis=diagnose(result);
    const seed=((Number(result.seed)||1)+(state.observedFights*104729))>>>0;
    const training=trainChunk(cfg,seed,250);
    const summary={observedFights:state.observedFights,rogueWins:state.rogueWins,rogueLosses:state.rogueLosses,generation:state.generation,champion:clone(state.champion),diagnosis,training};
    safeSave(state);
    return summary;
  }

  const originalRun=duel.run.bind(duel);
  function run(seed,cfg){
    const r=originalRun(seed,cfg);
    if(r&&!r.error)r.learning=observe(r,cfg);
    return r;
  }
  function getChampionPolicy(){return clone(state.champion);}
  function getState(){return clone(state);}
  function reset(){state=fresh();safeSave(state);return getState();}

  window.WOW_ROGUE_LEARNER={version:'0.17',getChampionPolicy,getState,observe,trainChunk,reset,mutations:clone(mutations)};
  window.WOW_DUEL={...duel,run,version:'0.17.0-learning'};
})();
