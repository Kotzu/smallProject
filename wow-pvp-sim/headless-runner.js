const fs=require('fs');
const path=require('path');
const vm=require('vm');

const root=__dirname;
const CORE_FILES=[
  'data.js','character-data.js','pvp-data.js','pvp-data-v010.js','pvp-data-v011.js','pvp-data-v012.js','pvp-data-v017.js','pvp-data-v018.js','rogue-dagger-profile-v017.js','pvp-data-v019.js','classic-stat-system.js','talent-builds.js','talent-builds-v019.js','pvp-data-v021.js','engine.js','character-engine.js','duel-engine-v022.js','pvp-policy-v024.js'
];

function boot(){
  const window={};
  const sandbox={window,console,Math,JSON,Number,String,Boolean,Object,Array,Date,Set,Map,parseInt,parseFloat,isFinite};
  window.window=window;
  vm.createContext(sandbox);
  for(const file of CORE_FILES){const full=path.join(root,file);if(!fs.existsSync(full))continue;vm.runInContext(fs.readFileSync(full,'utf8'),sandbox,{filename:file});}
  return window;
}

function config(){return {a:{class:'Rogue',spec:'Subtlety',race:'Undead',gear:'Level 60 PvP BiS',build:'rogue_cb_hemo_21_3_27'},b:{class:'Mage',spec:'Frost',race:'Gnome',gear:'Level 60 PvP BiS',build:'mage_deep_frost_17_0_34'}};}

const VARIANTS=[
  ['kidneyMinCp',4],
  ['kidneyEnergyReserve',20],
  ['evisMinCp',3],
  ['executeEvisHpPct',25],
  ['coldBloodMinCp',4],
  ['sprintMinRange',8],
  ['kickMinRemainingMs',300],
  ['hemoMinEnergy',75]
];

function championFor(w,duel){return duel.normalizeRoguePolicy(w.WOW_DATA?.roguePolicyChampion||duel.defaultRoguePolicy);}
function compareOne(duel,cfg,champion,index,count,seed){
  const i=Math.max(0,Math.min(VARIANTS.length-1,Math.trunc(Number(index)||0))),[field,value]=VARIANTS[i];
  const challenger=duel.normalizeRoguePolicy({...champion,[field]:value,id:`headless_g4_${field}_${value}`});
  const cmp=duel.comparePolicies(seed,count,cfg,champion,challenger);
  return {index:i,field,value,deltaWinRate:cmp.deltaWinRate,deltaScore:cmp.deltaScore,promote:cmp.promote,championWins:cmp.champion?.wins?.Rogue,challengerWins:cmp.challenger?.wins?.Rogue,championRate:cmp.champion?.rates?.Rogue,challengerRate:cmp.challenger?.rates?.Rogue,championAvgHp:cmp.champion?.avgRogueHpPct,challengerAvgHp:cmp.challenger?.avgRogueHpPct,championScore:cmp.champion?.score,challengerScore:cmp.challenger?.score};
}

function runTraining(count=100,seed=1337){
  const w=boot(),duel=w.WOW_DUEL,cfg=config(),champion=championFor(w,duel),self=duel.selfTest({...cfg,roguePolicy:champion}),results=[];
  for(let i=0;i<VARIANTS.length;i++)results.push(compareOne(duel,cfg,champion,i,count,seed));
  results.sort((a,b)=>b.deltaScore-a.deltaScore);
  return {engine:duel.version,deterministic:self.deterministic,count,seed,champion,results,best:results[0]};
}

function runVariant(index=0,count=1000,seed=1337){
  const w=boot(),duel=w.WOW_DUEL,cfg=config(),champion=championFor(w,duel),self=duel.selfTest({...cfg,roguePolicy:champion}),result=compareOne(duel,cfg,champion,index,count,seed);
  return {engine:duel.version,deterministic:self.deterministic,count,seed,champion,result};
}

function runDuel(seed=1337){const w=boot(),duel=w.WOW_DUEL,cfg=config(),champion=championFor(w,duel);return duel.runWithPolicy(seed,cfg,champion);}
module.exports={runTraining,runVariant,runDuel,VARIANTS};
