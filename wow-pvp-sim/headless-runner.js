const fs=require('fs');
const path=require('path');
const vm=require('vm');

const root=__dirname;
const CORE_FILES=[
  'data.js','character-data.js','pvp-data.js','pvp-data-v010.js','pvp-data-v011.js','pvp-data-v012.js','pvp-data-v017.js','pvp-data-v018.js','rogue-dagger-profile-v017.js','pvp-data-v019.js','classic-stat-system.js','talent-builds.js','talent-builds-v019.js','pvp-data-v021.js','engine.js','character-engine.js','duel-engine-v022.js'
];

function boot(){
  const window={};
  const sandbox={window,console,Math,JSON,Number,String,Boolean,Object,Array,Date,Set,Map,parseInt,parseFloat,isFinite};
  window.window=window;
  vm.createContext(sandbox);
  for(const file of CORE_FILES){
    const full=path.join(root,file);
    if(!fs.existsSync(full))continue;
    vm.runInContext(fs.readFileSync(full,'utf8'),sandbox,{filename:file});
  }
  return window;
}

function config(){
  return {
    a:{class:'Rogue',spec:'Subtlety',race:'Undead',gear:'Level 60 PvP BiS',build:'rogue_cb_hemo_21_3_27'},
    b:{class:'Mage',spec:'Frost',race:'Gnome',gear:'Level 60 PvP BiS',build:'mage_deep_frost_17_0_34'}
  };
}

const VARIANTS=[
  ['kidneyMinCp',4],
  ['kidneyEnergyReserve',20],
  ['evisMinCp',4],
  ['executeEvisHpPct',25],
  ['coldBloodMinCp',4],
  ['sprintMinRange',8],
  ['kickMinRemainingMs',300],
  ['hemoMinEnergy',55]
];

function runTraining(count=1000,seed=1337){
  const w=boot(),duel=w.WOW_DUEL,cfg=config(),champion=duel.defaultRoguePolicy;
  const self=duel.selfTest(cfg);
  const results=[];
  for(const [field,value] of VARIANTS){
    const challenger=duel.normalizeRoguePolicy({...champion,[field]:value,id:`headless_${field}_${value}`});
    const cmp=duel.comparePolicies(seed,count,cfg,champion,challenger);
    results.push({field,value,deltaWinRate:cmp.deltaWinRate,deltaScore:cmp.deltaScore,promote:cmp.promote,championWins:cmp.champion?.wins?.Rogue,challengerWins:cmp.challenger?.wins?.Rogue,championAvgHp:cmp.champion?.avgRogueHpPct,challengerAvgHp:cmp.challenger?.avgRogueHpPct});
  }
  results.sort((a,b)=>b.deltaScore-a.deltaScore);
  return {engine:duel.version,deterministic:self.deterministic,count,seed,champion,results,best:results[0]};
}

function runDuel(seed=1337){
  const w=boot();
  return w.WOW_DUEL.run(seed,config());
}

module.exports={runTraining,runDuel};
