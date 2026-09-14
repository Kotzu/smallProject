(()=>{
  const duel=window.WOW_DUEL,D=window.WOW_DATA;
  if(!duel?.comparePolicies||!duel?.defaultRoguePolicy)return;
  const KEY='wow-pvp-sim.rogue-learning.v026';
  const copy=x=>JSON.parse(JSON.stringify(x));
  const load=()=>{try{return JSON.parse(localStorage.getItem(KEY)||'null');}catch{return null;}};
  const save=x=>{try{localStorage.setItem(KEY,JSON.stringify(x));}catch{}};
  const initial=()=>duel.normalizeRoguePolicy(D.roguePolicyChampion||duel.defaultRoguePolicy);
  const fresh=()=>({version:'0.26',generation:4,observedFights:0,rogueWins:0,rogueLosses:0,champion:copy(initial()),candidateIndex:0,candidate:null,evidence:null,history:[]});
  let state=load()||fresh();
  if(state.version!=='0.26')state=fresh();
  state.champion=duel.normalizeRoguePolicy(state.champion||initial());

  const variants=[
    ['kidneyMinCp',4,'try Kidney Shot at 4+ CP'],
    ['kidneyEnergyReserve',20,'reserve 20 Energy for follow-up after Kidney Shot'],
    ['evisMinCp',3,'allow 3 CP Eviscerate conversion'],
    ['executeEvisHpPct',25,'allow 4+ CP Eviscerate below 25% target HP'],
    ['coldBloodMinCp',4,'allow Cold Blood from 4+ CP'],
    ['sprintMinRange',8,'hold Sprint until an 8 yd gap'],
    ['kickMinRemainingMs',300,'skip casts with under 300 ms remaining'],
    ['hemoMinEnergy',75,'pool to 75 Energy before Hemorrhage']
  ];

  function candidateFor(index){const [field,value,reason]=variants[index%variants.length];return {policy:duel.normalizeRoguePolicy({...state.champion,[field]:value,id:`rogue_g${state.generation}_c${index}_${field}`,version:(state.champion.version||4)+1}),field,value,reason};}
  function ensureCandidate(){if(!state.candidate){state.candidate=candidateFor(state.candidateIndex);state.evidence={tests:0,championWins:0,challengerWins:0,championScoreWeighted:0,challengerScoreWeighted:0,championHpWeighted:0,challengerHpWeighted:0};}return state.candidate;}
  function diagnose(result){
    const ev=result?.timeline||[],count=(actor,text)=>ev.filter(e=>e.actor===actor&&String(e.text).includes(text)).length;
    const d={mageCasts:count('Mage','Frostbolt cast started'),kicks:count('Rogue','Kick'),blinks:count('Mage','Blink'),sprints:count('Rogue','Sprint'),kidneys:count('Rogue','Kidney Shot'),evis:count('Rogue','Eviscerate'),prep:count('Rogue','Preparation'),vanish:count('Rogue','Vanish'),reasons:[]};
    if(result?.winner!=='Rogue'&&d.mageCasts>d.kicks)d.reasons.push('cast pressure not fully interrupted');
    if(result?.winner!=='Rogue'&&d.blinks>0&&d.sprints===0)d.reasons.push('range recovery was weak after Blink');
    if(result?.winner!=='Rogue'&&d.kidneys===0)d.reasons.push('no Kidney Shot control window landed');
    if(result?.winner!=='Rogue'&&d.evis===0)d.reasons.push('no Eviscerate conversion before death/timeout');
    return d;
  }
  function addEvidence(cmp){const n=cmp.count,e=state.evidence;e.tests+=n;e.championWins+=cmp.champion.wins.Rogue||0;e.challengerWins+=cmp.challenger.wins.Rogue||0;e.championScoreWeighted+=cmp.champion.score*n;e.challengerScoreWeighted+=cmp.challenger.score*n;e.championHpWeighted+=cmp.champion.avgRogueHpPct*n;e.challengerHpWeighted+=cmp.challenger.avgRogueHpPct*n;}
  function maybePromote(){
    const e=state.evidence;if(!e||e.tests<1000)return {ready:false,tests:e?.tests||0,required:1000};
    const winDelta=e.challengerWins-e.championWins,scoreDelta=(e.challengerScoreWeighted-e.championScoreWeighted)/e.tests,hpDelta=(e.challengerHpWeighted-e.championHpWeighted)/e.tests;
    const promote=winDelta>=5||(winDelta>=0&&scoreDelta>1&&hpDelta>0.5);
    const record={generation:state.generation,candidate:copy(state.candidate),tests:e.tests,winDelta,scoreDelta:Number(scoreDelta.toFixed(4)),hpDelta:Number(hpDelta.toFixed(4)),promote};
    state.history.push(record);if(state.history.length>40)state.history.shift();
    if(promote){state.champion=copy(state.candidate.policy);state.generation++;state.candidateIndex=0;}else state.candidateIndex++;
    state.candidate=null;state.evidence=null;save(state);return {ready:true,...record,champion:copy(state.champion)};
  }
  function trainChunk(cfg,seed,count=250){const c=ensureCandidate(),cmp=duel.comparePolicies(seed,count,cfg,state.champion,c.policy);if(cmp.error)return {error:cmp.error};addEvidence(cmp);const promotion=maybePromote();save(state);return {candidate:copy(c),comparison:cmp,evidence:copy(state.evidence),promotion};}
  function observe(result,cfg){if(!result||result.error)return null;state.observedFights++;if(result.winner==='Rogue')state.rogueWins++;else if(result.winner==='Mage')state.rogueLosses++;const diagnosis=diagnose(result),seed=((Number(result.seed)||1)+(state.observedFights*104729))>>>0,training=trainChunk(cfg,seed,250),summary={observedFights:state.observedFights,rogueWins:state.rogueWins,rogueLosses:state.rogueLosses,generation:state.generation,champion:copy(state.champion),diagnosis,training};save(state);return summary;}

  const rawRun=duel.run.bind(duel);
  function run(seed,cfg){const r=rawRun(seed,{...cfg,roguePolicy:state.champion});if(r&&!r.error)r.learning=observe(r,cfg);return r;}
  function getChampionPolicy(){return copy(state.champion);}
  function getState(){return copy(state);}
  function reset(){state=fresh();save(state);return getState();}

  window.WOW_ROGUE_LEARNER={version:'0.26',getChampionPolicy,getState,observe,trainChunk,reset,variants:copy(variants)};
  window.WOW_DUEL={...duel,run,version:'0.26-learning',learningVersion:'0.26'};
})();
