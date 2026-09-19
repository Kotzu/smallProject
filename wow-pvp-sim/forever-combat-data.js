(function(){
  const CLIENT='1.60.1.69913';
  const SRC={
    rogue:'https://foreverchanges.pro/spellbook/rogue',
    mage:'https://foreverchanges.pro/spellbook/mage',
    rogueTalents:'https://foreverchanges.pro/talents/rogue',
    mageTalents:'https://foreverchanges.pro/talents/mage',
    racials:'https://www.wowhead.com/forever/guide/new-race-class-combinations'
  };
  const V='CLIENT_VERIFIED',P='CORE_INHERITED_PROVISIONAL',R='REFERENCE_PROFILE_PROVISIONAL';

  const rogue={
    'Cheap Shot':{cost:60,range:5,gcdMs:1000,stunMs:4000,combo:2,stealth:true,confidence:V,source:SRC.rogue},
    'Kick':{cost:25,range:5,gcdMs:0,cooldownMs:10000,damage:80,lockMs:5000,confidence:V,source:SRC.rogue},
    'Kidney Shot':{cost:25,range:5,gcdMs:1000,cooldownMs:20000,durationsMs:[0,2000,3000,4000,5000,6000],finisher:true,confidence:V,source:SRC.rogue},
    'Eviscerate':{cost:35,range:5,gcdMs:1000,finisher:true,baseByCp:[[0,0],[199,295],[350,446],[501,597],[652,748],[803,899]],apCoeffPerCp:0.03,apCoeffConfidence:P,confidence:V,source:SRC.rogue},
    'Hemorrhage':{cost:35,range:5,gcdMs:1000,weaponPct:1.00,daggerPct:1.45,combo:1,ruptureTakenPct:15,debuffMs:15000,confidence:V,source:'https://foreverchanges.pro/talents/rogue#hemorrhage/'},
    'Gouge':{cost:45,range:5,gcdMs:1000,cooldownMs:10000,damage:75,combo:1,incapMs:4000,breakOnDamage:true,requiresFacing:true,confidence:V,source:SRC.rogue},
    'Blind':{cost:30,range:10,gcdMs:1000,cooldownMs:300000,disorientMs:10000,breakOnDamage:true,confidence:V,source:SRC.rogue},
    'Vanish':{cost:0,gcdMs:0,cooldownMs:300000,stealthMs:10000,breakMovement:true,confidence:V,source:SRC.rogue},
    'Sprint':{cost:0,gcdMs:0,cooldownMs:300000,speedPct:70,durationMs:15000,confidence:V,source:SRC.rogue},
    'Evasion':{cost:0,gcdMs:0,cooldownMs:300000,dodgePct:50,durationMs:15000,confidence:V,source:SRC.rogue},
    'Preparation':{cost:0,gcdMs:0,cooldownMs:600000,resetOtherRogue:true,confidence:V,source:'https://foreverchanges.pro/talents/rogue#preparation/'},
    'Cold Blood':{cost:0,gcdMs:0,cooldownMs:180000,critBonusPct:100,confidence:V,source:'https://foreverchanges.pro/talents/rogue#cold-blood/'},
    'Premeditation':{cost:0,range:20,gcdMs:0,cooldownMs:120000,combo:2,comboExpiryMs:20000,confidence:V,source:'https://foreverchanges.pro/talents/rogue#premeditation/'},
    'Backstab':{cost:60,range:5,gcdMs:1000,weaponPct:1.50,flat:150,combo:1,requiresDagger:true,requiresBehind:true,confidence:V,source:SRC.rogue},
    'Ambush':{cost:60,range:5,gcdMs:1000,weaponPct:2.50,flat:290,combo:1,requiresDagger:true,requiresBehind:true,stealth:true,confidence:V,source:SRC.rogue},
    'Mutilate':{cost:60,range:5,gcdMs:1000,weaponPct:.75,flat:50,combo:2,poisonedDamagePct:20,requiresDualWeapons:true,confidence:V,source:SRC.rogue},
    'Crippling Poison':{procPct:30,slowPct:50,durationMs:12000,confidence:V,source:SRC.rogue},
    'Mind-numbing Poison':{procPct:20,castTimeIncreasePct:40,durationMs:10000,confidence:V,source:SRC.rogue}
  };

  const mage={
    'Frostbolt':{cost:290,range:30,gcdMs:1500,castMs:3000,min:457,max:493,slowPct:40,slowMs:9000,spCoeff:0.814,spCoeffConfidence:P,school:'Frost',confidence:V,source:SRC.mage},
    'Frost Nova':{cost:145,range:10,gcdMs:1500,cooldownMs:25000,min:69,max:77,rootMs:8000,breakOnDamage:true,school:'Frost',confidence:V,source:SRC.mage},
    'Cone of Cold':{cost:555,range:10,gcdMs:1500,cooldownMs:10000,min:325,max:355,slowPct:40,slowMs:6000,spCoeff:0.135,spCoeffConfidence:P,school:'Frost',confidence:V,source:SRC.mage},
    'Ice Lance':{cost:160,range:30,gcdMs:1500,min:133,max:157,frozenMultiplier:4,spCoeff:0.143,spCoeffConfidence:P,school:'Frost',confidence:V,source:SRC.mage},
    'Ice Barrier':{cost:480,gcdMs:1500,cooldownMs:30000,absorb:811,durationMs:60000,confidence:V,source:SRC.mage},
    'Blink':{costPctBaseMana:35,gcdMs:0,cooldownMs:15000,distance:20,breakStun:true,breakImmobilize:true,confidence:V,source:SRC.mage},
    'Fire Blast':{cost:340,range:20,gcdMs:1500,cooldownMs:8000,min:402,max:474,spCoeff:0.429,spCoeffConfidence:P,school:'Fire',confidence:V,source:SRC.mage},
    'Mana Shield':{cost:140,gcdMs:1500,cooldownMs:0,absorb:570,durationMs:60000,manaPerDamage:2,manaPerDamageConfidence:P,confidence:V,source:SRC.mage},
    'Polymorph':{cost:150,range:30,gcdMs:1500,castMs:1500,disorientMs:10000,pvpDurationConfidence:P,breakOnDamage:true,school:'Arcane',confidence:V,source:SRC.mage},
    'Counterspell':{cost:100,range:30,gcdMs:0,cooldownMs:30000,lockMs:10000,confidence:V,source:SRC.mage},
    'Ice Block':{cost:15,gcdMs:0,cooldownMs:300000,durationMs:10000,immuneAll:true,confidence:V,source:'https://foreverchanges.pro/talents/mage#ice-block/'},
    'Cold Snap':{cost:0,gcdMs:0,cooldownMs:600000,resetFrost:true,confidence:V,source:'https://foreverchanges.pro/talents/mage#cold-snap/'}
  };

  const talents={
    Rogue:{
      'Dirty Deeds':{cheapGarroteCostReductionPerRank:10,confidence:V},
      'Initiative':{extraCpChanceByRank:[0,33,67,100],confidence:V},
      'Lethality':{builderCritBonusPerRankPct:4,confidence:V},
      'Murder':{humanoidGiantDamagePerRankPct:2,confidence:V},
      'Improved Kidney Shot':{damageTakenPerRankPct:5,confidence:V},
      'Improved Eviscerate':{evisDamageByRankPct:[0,7,13,20],confidence:V},
      'Serrated Blades':{armorIgnorePerRankPct:3,rupturePerRankPct:10,confidence:V},
      'Elusiveness':{vanishBlindCdReductionPerRankMs:45000,confidence:V}
    },
    Mage:{
      'Improved Frostbolt':{castReductionPerRankMs:100,confidence:V},
      'Ice Shards':{frostCritBonusDamageAtRank5Pct:100,confidence:V},
      'Permafrost':{chillDurationAtRank3Pct:33,extraSlowAtRank3Pct:10,confidence:V},
      'Improved Frost Nova':{cdReductionPerRankMs:2000,confidence:V},
      'Frostbite':{freezeChanceAtRank3Pct:15,freezeMs:5000,confidence:V},
      'Piercing Ice':{damagePerRankPct:2,confidence:V},
      'Shatter':{frozenCritAtRank3Pct:50,confidence:V},
      'Fingers of Frost':{procChanceByRankPct:[0,15,30],charges:1,durationMs:15000,confidence:V},
      'Arcane Resilience':{armorFromIntellectAtRank2Pct:50,confidence:V},
      'Improved Counterspell':{silenceAtRank2Ms:4000,confidence:V},
      'Arcane Concentration':{clearcastAtRank5Pct:10,confidence:V}
    }
  };

  // These are scenario/reference character baselines reconstructed from the verified
  // Forever gear surface plus the previous level-60 calibration. They are deliberately
  // NOT promoted to client-verified facts; the UI labels the simulator REFERENCE MODEL.
  const referenceProfiles={
    Rogue:{
      class:'Rogue',spec:'Subtlety',race:'Undead',level:60,
      health:4713,maxEnergy:100,energyRegenPerSec:10,energyRegenConfidence:P,
      strength:153,agility:309,stamina:327,attackPower:1020,critPct:34.66,hitPct:7,
      armor:1496,shadowRes:10,
      mh:{name:'Gressil, Dawn of Ruin',type:'Sword',min:37,max:114,speed:2.70},
      oh:{name:'Harbinger of Doom',type:'Dagger',min:22,max:67,speed:1.60},
      confidence:R
    },
    Mage:{
      class:'Mage',spec:'Frost',race:'Gnome',level:60,
      health:4280,mana:6258,baseMana:6258,stamina:299,intellect:355,
      spellPower:596,frostSpellPower:616,spellCritPct:14.16,spellHitPct:5,spellPen:101,
      armor:1122,dodgePct:5.15,
      resist:{Arcane:15,Fire:5,Frost:5,Nature:5,Shadow:5},
      confidence:R
    }
  };

  const inherited={
    armorFormula:{confidence:P,note:'Classic core armor formula used as a reference until Forever combat-table extraction is audited.'},
    sameLevelSpellBaseMissPct:{value:4,floorPct:1,confidence:P},
    rogueEnergyRegen:{value:10,unit:'energy/sec',confidence:P},
    meleeSpecialBaseMissPct:{value:5,confidence:P},
    dualWieldWhiteBaseMissPct:{value:24,confidence:P},
    movementSpeedYps:{value:7,confidence:P},
    effectiveMeleeRangeYards:{value:5.5,confidence:P,note:'Reference combat-reach tolerance; exact Forever unit combat reach is not yet client-audited.'},
    evisApCoefficient:{value:'3% AP per combo point',confidence:P},
    spellCoefficients:{confidence:P,note:'Classic inherited coefficients; client tooltips do not expose coefficients.'},
    pvpControlDiminishingReturns:{confidence:P,note:'Forever-specific DR table is not yet client-audited; reference simulation uses conservative category rules.'}
  };

  const scenario={
    id:'rogue_subtlety_vs_frost_mage_reference_v1',
    label:'Rogue Subtlety vs Frost Mage · reference duel',
    startRange:20,
    rogueStartsStealthed:true,
    mageStartsIceBarrier:true,
    mageStartsIceArmor:true,
    roguePoisons:{mh:'Crippling Poison',oh:'Mind-numbing Poison'},
    maxDurationMs:120000,
    tickMs:50,
    status:'REFERENCE_MODEL_NOT_PARITY_CERTIFIED'
  };

  window.WOW_FOREVER_COMBAT_DATA={
    version:'0.51-beta-69913-reference-data',
    clientDataBuild:CLIENT,
    clientBuild:CLIENT,
    confidence:{CLIENT_VERIFIED:V,CORE_INHERITED_PROVISIONAL:P,REFERENCE_PROFILE_PROVISIONAL:R},
    sources:SRC,abilities:{Rogue:rogue,Mage:mage},talents,referenceProfiles,inherited,scenario
  };
})();