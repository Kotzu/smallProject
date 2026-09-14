(()=>{
  const D=window.WOW_DATA=window.WOW_DATA||{};
  const src=D.pvpBuilds||{};

  const library={
    rogue_cb_hemo_21_3_27:{
      ...(src.rogue_cb_hemo_21_3_27||{}),
      name:'Cold Blood Hemorrhage',
      status:'ACTIVE_CALIBRATED',
      role:'PvP control / reset / burst',
      weaponStyle:'Slow MH + fast OH',
      calculatorUrl:'https://www.wowhead.com/classic/talent-calc/rogue/305320115001-3-500253000332121',
      combatTalents:[
        {name:'Improved Eviscerate',rank:'3/3',effect:'+15% Eviscerate damage',modifier:'eviscerateDamagePct',value:15},
        {name:'Malice',rank:'5/5',effect:'+5% melee critical strike chance',modifier:'meleeCritPct',value:5},
        {name:'Murder',rank:'2/2',effect:'+2% damage against eligible Humanoid targets',modifier:'murderDamagePct',value:2},
        {name:'Relentless Strikes',rank:'1/1',effect:'20% chance per combo point to restore 25 Energy after a finisher',modifier:'relentless',value:'20%/CP → 25 Energy'},
        {name:'Lethality',rank:'5/5',effect:'combo-point builder critical damage bonus +30%; Hemorrhage crit resolves at 2.30×',modifier:'builderCritMultiplier',value:2.3},
        {name:'Cold Blood',rank:'1/1',effect:'guarantees the next eligible critical strike',modifier:'coldBlood',value:true},
        {name:'Dirty Deeds',rank:'2/2',effect:'Cheap Shot cost reduced by 20 Energy → 40',modifier:'cheapShotEnergy',value:40},
        {name:'Hemorrhage',rank:'1/1',effect:'unlocks Hemorrhage as the primary builder',modifier:'hemorrhage',value:true},
        {name:'Preparation',rank:'1/1',effect:'resets Rogue-family cooldowns except Preparation',modifier:'preparation',value:true}
      ],
      modifiers:{
        ...(src.rogue_cb_hemo_21_3_27?.modifiers||{}),
        murderDamagePct:2,builderCritMultiplier:2.3,hemorrhageCritMultiplier:2.3,
        coldBlood:true,hemorrhage:true,preparation:true,improvedSprint:false
      },
      sourceNote:'Classic Cold Blood Hemorrhage PvP build. Active numeric effects are explicitly registered; Preparation is verified from CMaNGOS Rogue.cpp.'
    },

    rogue_imp_sprint_backstab_17_12_22:{
      id:'rogue_imp_sprint_backstab_17_12_22',class:'Rogue',spec:'Subtlety',level:60,points:'17/12/22',
      calculator:'005320124-320302002-05024303030011',
      name:'Improved Sprint Backstab · Expose Armor variant',
      status:'VERIFIED_LOCKED_KERNEL',
      role:'PvP dagger burst / anti-kite / reset',
      weaponStyle:'Daggers — Kingsfall MH / Death\'s Sting OH profile',
      calculatorUrl:'https://classic.wowhead.com/talent-calc/rogue/005320124-320302002-05024303030011',
      combatTalents:[
        {name:'Malice',rank:'5/5',effect:'+5% melee critical strike chance',modifier:'meleeCritPct',value:5},
        {name:'Ruthlessness',rank:'3/3',effect:'60% chance to add a combo point after a finisher',modifier:'ruthlessnessProcPct',value:60},
        {name:'Murder',rank:'2/2',effect:'+2% damage against eligible Humanoid targets',modifier:'murderDamagePct',value:2},
        {name:'Relentless Strikes',rank:'1/1',effect:'20% chance per combo point to restore 25 Energy after a finisher',modifier:'relentless',value:'20%/CP → 25 Energy'},
        {name:'Improved Expose Armor',rank:'2/2',effect:'+50% armor reduction from Expose Armor',modifier:'improvedExposeArmorPct',value:50},
        {name:'Lethality',rank:'4/5',effect:'Backstab/Sinister/Gouge builder critical damage bonus +24%; total builder crit multiplier 2.24×',modifier:'builderCritMultiplier',value:2.24},
        {name:'Improved Gouge',rank:'3/3',effect:'+1.5 sec Gouge duration → 5.5s',modifier:'gougeDurationBonusMs',value:1500},
        {name:'Improved Sinister Strike',rank:'2/2',effect:'Sinister Strike Energy cost 45 → 40',modifier:'sinisterStrikeEnergy',value:40},
        {name:'Improved Backstab',rank:'3/3',effect:'+30% Backstab critical strike chance',modifier:'backstabCritBonusPct',value:30},
        {name:'Precision',rank:'2/5',effect:'+2% melee and ranged hit',modifier:'meleeHitPct',value:2},
        {name:'Improved Sprint',rank:'2/2',effect:'Sprint removes all movement-impairing effects on activation',modifier:'improvedSprint',value:true},
        {name:'Opportunity',rank:'5/5',effect:'+20% Backstab, Ambush and Garrote damage from behind',modifier:'opportunityDamagePct',value:20},
        {name:'Improved Ambush',rank:'3/3',effect:'+45% Ambush critical strike chance',modifier:'ambushCritBonusPct',value:45},
        {name:'Preparation',rank:'1/1',effect:'resets Rogue-family cooldowns except Preparation',modifier:'preparation',value:true},
        {name:'Dirty Deeds',rank:'1/2',effect:'Cheap Shot / Garrote cost reduced by 10 Energy; Cheap Shot costs 50',modifier:'cheapShotEnergy',value:50}
      ],
      modifiers:{
        meleeCritPct:5,ruthlessnessProcPct:60,murderDamagePct:2,relentlessEnergy:25,relentlessChancePerComboPct:20,
        improvedExposeArmorPct:50,builderCritMultiplier:2.24,gougeDurationBonusMs:1500,sinisterStrikeEnergy:40,
        backstabCritBonusPct:30,meleeHitPct:2,improvedSprint:true,opportunityDamagePct:20,ambushCritBonusPct:45,
        preparation:true,cheapShotEnergy:50,hemorrhage:false,coldBlood:false
      },
      loadoutId:'rogue_p6_pvp_daggers_kingsfall_deaths_sting',
      kernelBlockers:['positional behind-state model','Gouge control/break-on-damage path','dagger weapon-skill PvP combat-table validation','policy parity QA'],
      sourceNote:'Exact calculator variant published in Blizzard Classic forum discussion. It totals 17/12/22 and is kept separate from the canonical 16/12/23 dagger build.'
    },

    rogue_imp_sprint_backstab_16_12_23:{
      id:'rogue_imp_sprint_backstab_16_12_23',class:'Rogue',spec:'Subtlety',level:60,points:'16/12/23',
      calculator:'305020105-320302002-05024303030012',
      name:'Improved Sprint Backstab · 16/12/23',
      status:'VERIFIED_LOCKED_KERNEL',
      role:'PvP dagger burst / anti-kite / Preparation control',
      weaponStyle:'Daggers — uses dagger PvP loadout',
      calculatorUrl:'https://classic.wowhead.com/talent-calc/rogue/305020105-320302002-05024303030012',
      combatTalents:[
        {name:'Improved Eviscerate',rank:'3/3',effect:'+15% Eviscerate damage',modifier:'eviscerateDamagePct',value:15},
        {name:'Malice',rank:'5/5',effect:'+5% melee critical strike chance',modifier:'meleeCritPct',value:5},
        {name:'Murder',rank:'2/2',effect:'+2% damage against eligible Humanoid targets',modifier:'murderDamagePct',value:2},
        {name:'Relentless Strikes',rank:'1/1',effect:'20% chance per combo point to restore 25 Energy after a finisher',modifier:'relentless',value:'20%/CP → 25 Energy'},
        {name:'Lethality',rank:'5/5',effect:'builder critical damage bonus +30%; total builder crit multiplier 2.30×',modifier:'builderCritMultiplier',value:2.3},
        {name:'Improved Gouge',rank:'3/3',effect:'+1.5 sec Gouge duration → 5.5s',modifier:'gougeDurationBonusMs',value:1500},
        {name:'Improved Sinister Strike',rank:'2/2',effect:'Sinister Strike Energy cost 45 → 40',modifier:'sinisterStrikeEnergy',value:40},
        {name:'Improved Backstab',rank:'3/3',effect:'+30% Backstab critical strike chance',modifier:'backstabCritBonusPct',value:30},
        {name:'Precision',rank:'2/5',effect:'+2% melee and ranged hit',modifier:'meleeHitPct',value:2},
        {name:'Improved Sprint',rank:'2/2',effect:'Sprint removes all movement-impairing effects on activation',modifier:'improvedSprint',value:true},
        {name:'Opportunity',rank:'5/5',effect:'+20% Backstab, Ambush and Garrote damage from behind',modifier:'opportunityDamagePct',value:20},
        {name:'Elusiveness',rank:'2/2',effect:'reduces Blind and Vanish cooldowns',modifier:'elusiveness',value:true},
        {name:'Camouflage',rank:'4/5',effect:'improves stealth movement/detection interaction',modifier:'camouflageRank',value:4},
        {name:'Initiative',rank:'3/3',effect:'75% chance for an additional combo point from Ambush/Garrote/Cheap Shot',modifier:'initiativeProcPct',value:75},
        {name:'Improved Ambush',rank:'3/3',effect:'+45% Ambush critical strike chance',modifier:'ambushCritBonusPct',value:45},
        {name:'Improved Sap',rank:'3/3',effect:'90% chance to remain in Stealth after Sap',modifier:'improvedSapStayStealthPct',value:90},
        {name:'Preparation',rank:'1/1',effect:'resets Rogue-family cooldowns except Preparation',modifier:'preparation',value:true},
        {name:'Dirty Deeds',rank:'2/2',effect:'Cheap Shot / Garrote cost reduced by 20 Energy; Cheap Shot costs 40',modifier:'cheapShotEnergy',value:40}
      ],
      modifiers:{
        eviscerateDamagePct:15,meleeCritPct:5,murderDamagePct:2,relentlessEnergy:25,relentlessChancePerComboPct:20,
        builderCritMultiplier:2.3,gougeDurationBonusMs:1500,sinisterStrikeEnergy:40,backstabCritBonusPct:30,meleeHitPct:2,
        improvedSprint:true,opportunityDamagePct:20,elusiveness:true,camouflageRank:4,initiativeProcPct:75,
        ambushCritBonusPct:45,improvedSapStayStealthPct:90,preparation:true,cheapShotEnergy:40,hemorrhage:false,coldBlood:false
      },
      loadoutId:'rogue_p6_pvp_daggers_kingsfall_deaths_sting',
      kernelBlockers:['positional behind-state model','Initiative extra-combo-point proc path','Gouge control/break-on-damage path','Elusiveness cooldown adjustments','dagger weapon-skill PvP combat-table validation','policy parity QA'],
      sourceNote:'16/12/23 Improved Sprint/Backstab is independently documented as a standard Classic PvP dagger build; calculator 305020105-320302002-05024303030012 is from a 2019 Blizzard Classic forum post.'
    },

    mage_deep_frost_17_0_34:{
      ...(src.mage_deep_frost_17_0_34||{}),
      name:'Deep Frost PvP',status:'ACTIVE_CALIBRATED',role:'PvP control / kite / defensive reset',
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
      modifiers:{...(src.mage_deep_frost_17_0_34?.modifiers||{}),coldSnap:true,iceBlock:true,iceBarrier:true}
    }
  };

  const buildIds=Object.keys(library),byClassSpec={};
  for(const id of buildIds){const b=library[id];if(!b.class||!b.spec)continue;(byClassSpec[b.class+'::'+b.spec]??=[]).push(id);}
  const kernelBindings={a:'rogue_cb_hemo_21_3_27',b:'mage_deep_frost_17_0_34'};
  function idsFor(className,spec){return byClassSpec[className+'::'+spec]||[];}
  function get(id){return library[id]||null;}
  function defaultBuild(className,spec){const ids=idsFor(className,spec);return ids.find(id=>library[id]?.status==='ACTIVE_CALIBRATED')||ids[0]||null;}
  function pointTotal(points){return String(points||'').split('/').reduce((s,x)=>s+(Number(x)||0),0);}
  function auditSelection(side){
    if(!side)return {pass:false,status:'FAIL',reason:'missing player config'};
    const id=side.build||defaultBuild(side.class,side.spec),b=get(id);
    if(!b)return {pass:false,status:'FAIL',reason:`no verified talent build for ${side.class} ${side.spec}`};
    if(b.class!==side.class||b.spec!==side.spec)return {pass:false,status:'FAIL',reason:'talent build does not match class/spec'};
    if(b.level===60&&pointTotal(b.points)!==51)return {pass:false,status:'FAIL',reason:`level 60 build has ${pointTotal(b.points)} points, expected 51`};
    const active=b.status==='ACTIVE_CALIBRATED';
    return {pass:true,status:active?'PASS':'VERIFIED_LOCKED',buildId:id,build:b,kernelReady:active,reason:active?`${b.name} · ${b.points} · calibrated`:`${b.name} · ${b.points} · verified build, kernel locked`};
  }
  function kernelAudit(cfg){
    const a=auditSelection(cfg?.a),b=auditSelection(cfg?.b),missing=[];
    if(!a.pass)missing.push('Player A talent build: '+a.reason);else if(!a.kernelReady)missing.push(`Player A build ${a.build.name} is verified but not kernel-calibrated`);else if(a.buildId!==kernelBindings.a)missing.push('Player A build not supported by current kernel');
    if(!b.pass)missing.push('Player B talent build: '+b.reason);else if(!b.kernelReady)missing.push(`Player B build ${b.build.name} is verified but not kernel-calibrated`);else if(b.buildId!==kernelBindings.b)missing.push('Player B build not supported by current kernel');
    return {pass:missing.length===0,missing,a,b};
  }
  D.talentBuildLibrary=library;
  if(D.pvpKernel?.supported){D.pvpKernel.supported.a.build=kernelBindings.a;D.pvpKernel.supported.b.build=kernelBindings.b;}
  window.WOW_TALENTS={version:'0.18',library,buildIds,idsFor,get,defaultBuild,auditSelection,kernelAudit,kernelBindings,pointTotal};
})();
