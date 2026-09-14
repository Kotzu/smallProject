(()=>{
  const D=window.WOW_DATA=window.WOW_DATA||{};
  const src=D.pvpBuilds||{};

  const library={
    rogue_cb_hemo_21_3_27:{
      ...(src.rogue_cb_hemo_21_3_27||{}),
      name:'Cold Blood Hemorrhage',
      status:'ACTIVE_CALIBRATED',
      role:'PvP control / reset / burst',
      calculatorUrl:'https://www.wowhead.com/classic/talent-calc/rogue/305320115001-3-500253000332121',
      combatTalents:[
        {name:'Improved Eviscerate',rank:'3/3',effect:'+15% Eviscerate damage',modifier:'eviscerateDamagePct',value:15},
        {name:'Malice',rank:'5/5',effect:'+5% melee critical strike chance',modifier:'meleeCritPct',value:5},
        {name:'Murder',rank:'2/2',effect:'+2% damage against the Mage target type used by this kernel',modifier:'murderDamagePct',value:2},
        {name:'Relentless Strikes',rank:'1/1',effect:'20% chance per combo point to restore 25 Energy after a finisher',modifier:'relentless',value:'20%/CP → 25 Energy'},
        {name:'Lethality',rank:'5/5',effect:'increases critical damage bonus of combo-point builders; Hemorrhage crit resolves at 2.3× in this kernel',modifier:'hemorrhageCritMultiplier',value:2.3},
        {name:'Cold Blood',rank:'1/1',effect:'guarantees the next eligible critical strike',modifier:'coldBlood',value:true},
        {name:'Dirty Deeds',rank:'2/2',effect:'Cheap Shot cost reduced to 40 Energy',modifier:'cheapShotEnergy',value:40},
        {name:'Hemorrhage',rank:'1/1',effect:'unlocks Hemorrhage as the primary builder',modifier:'hemorrhage',value:true},
        {name:'Preparation',rank:'1/1',effect:'unlocks reset-oriented PvP policy branches',modifier:'preparation',value:true}
      ],
      modifiers:{
        ...(src.rogue_cb_hemo_21_3_27?.modifiers||{}),
        murderDamagePct:2,
        hemorrhageCritMultiplier:2.3,
        coldBlood:true,
        hemorrhage:true,
        preparation:true
      }
    },
    mage_deep_frost_17_0_34:{
      ...(src.mage_deep_frost_17_0_34||{}),
      name:'Deep Frost PvP',
      status:'ACTIVE_CALIBRATED',
      role:'PvP control / kite / defensive reset',
      calculatorUrl:'https://www.wowhead.com/classic/talent-calc/mage/23001503102--05350233102351001',
      combatTalents:[
        {name:'Improved Frostbolt',rank:'5/5',effect:'Frostbolt cast time 3.0s → 2.5s',modifier:'frostboltCastMs',value:2500},
        {name:'Elemental Precision',rank:'3/3',effect:'+6% Frost/Fire spell hit and -3% Frost/Fire mana cost',modifier:'frostFireHitPct',value:6},
        {name:'Ice Shards',rank:'5/5',effect:'Frost critical strikes resolve at 2.0×',modifier:'frostCritMultiplier',value:2},
        {name:'Improved Frost Nova',rank:'2/2',effect:'Frost Nova cooldown 25s → 21s',modifier:'frostNovaCooldownMs',value:21000},
        {name:'Permafrost',rank:'3/3',effect:'+3s chill duration and +10 percentage points slow',modifier:'permafrost',value:'+3s / +10%'},
        {name:'Piercing Ice',rank:'3/3',effect:'+6% Frost damage',modifier:'frostDamagePct',value:6},
        {name:'Shatter',rank:'5/5',effect:'+50% critical strike chance against frozen targets',modifier:'frozenCritBonusPct',value:50},
        {name:'Improved Cone of Cold',rank:'3/3',effect:'+35% Cone of Cold damage',modifier:'coneOfColdDamagePct',value:35},
        {name:'Arcane Resilience',rank:'1/1',effect:'Armor increased by 50% of Intellect',modifier:'armorFromIntellectPct',value:50},
        {name:'Cold Snap',rank:'1/1',effect:'unlocks Frost cooldown reset decision',modifier:'coldSnap',value:true},
        {name:'Ice Block',rank:'1/1',effect:'unlocks emergency immunity decision',modifier:'iceBlock',value:true},
        {name:'Ice Barrier',rank:'1/1',effect:'unlocks Ice Barrier defensive decision',modifier:'iceBarrier',value:true},
        {name:'Improved Counterspell',rank:'2/2',effect:'Counterspell also silences for 4s',modifier:'counterspellSilenceMs',value:4000}
      ],
      modifiers:{
        ...(src.mage_deep_frost_17_0_34?.modifiers||{}),
        coldSnap:true,
        iceBlock:true,
        iceBarrier:true
      }
    }
  };

  const buildIds=Object.keys(library);
  const byClassSpec={};
  for(const id of buildIds){
    const b=library[id];
    if(!b.class||!b.spec)continue;
    const key=b.class+'::'+b.spec;
    (byClassSpec[key]??=[]).push(id);
  }

  const kernelBindings={
    a:'rogue_cb_hemo_21_3_27',
    b:'mage_deep_frost_17_0_34'
  };

  function idsFor(className,spec){return byClassSpec[className+'::'+spec]||[];}
  function get(id){return library[id]||null;}
  function defaultBuild(className,spec){return idsFor(className,spec)[0]||null;}
  function pointTotal(points){return String(points||'').split('/').reduce((s,x)=>s+(Number(x)||0),0);}
  function auditSelection(side){
    if(!side)return {pass:false,status:'FAIL',reason:'missing player config'};
    const id=side.build||defaultBuild(side.class,side.spec);
    const b=get(id);
    if(!b)return {pass:false,status:'FAIL',reason:`no verified talent build for ${side.class} ${side.spec}`};
    if(b.class!==side.class||b.spec!==side.spec)return {pass:false,status:'FAIL',reason:'talent build does not match class/spec'};
    if(b.status!=='ACTIVE_CALIBRATED')return {pass:false,status:'LOCKED',reason:`build ${b.name||id} is not calibrated`};
    if(b.level===60&&pointTotal(b.points)!==51)return {pass:false,status:'FAIL',reason:`level 60 build has ${pointTotal(b.points)} points, expected 51`};
    return {pass:true,status:'PASS',buildId:id,build:b,reason:`${b.name} · ${b.points} · calibrated`};
  }
  function kernelAudit(cfg){
    const a=auditSelection(cfg?.a),b=auditSelection(cfg?.b);
    const exactA=a.pass&&a.buildId===kernelBindings.a;
    const exactB=b.pass&&b.buildId===kernelBindings.b;
    const missing=[];
    if(!a.pass)missing.push('Player A talent build: '+a.reason);else if(!exactA)missing.push('Player A build not supported by current kernel');
    if(!b.pass)missing.push('Player B talent build: '+b.reason);else if(!exactB)missing.push('Player B build not supported by current kernel');
    return {pass:missing.length===0,missing,a,b};
  }

  D.talentBuildLibrary=library;
  if(D.pvpKernel?.supported){
    D.pvpKernel.supported.a.build=kernelBindings.a;
    D.pvpKernel.supported.b.build=kernelBindings.b;
  }

  window.WOW_TALENTS={version:'0.16',library,buildIds,idsFor,get,defaultBuild,auditSelection,kernelAudit,kernelBindings,pointTotal};
})();
