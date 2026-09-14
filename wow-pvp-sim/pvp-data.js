(()=>{
  const D=window.WOW_DATA=window.WOW_DATA||{};

  D.pvpBuilds={
    rogue_cb_hemo_21_3_27:{
      id:'rogue_cb_hemo_21_3_27',class:'Rogue',spec:'Subtlety',level:60,points:'21/3/27',
      calculator:'305320115001-3-500253000332121',
      keyTalents:{improvedEviscerate:3,malice:5,ruthlessness:3,murder:2,relentlessStrikes:1,lethality:5,coldBlood:1,improvedGouge:3,masterOfDeception:5,elusiveness:2,initiative:3,improvedSap:3,preparation:1,dirtyDeeds:2,hemorrhage:1,heightenedSenses:2},
      modifiers:{eviscerateDamagePct:15,meleeCritPct:5,hemorrhageCritBonusMultiplier:1.3,cheapShotEnergy:40,relentlessEnergy:25,relentlessChancePerComboPct:20},
      sourceNote:'Classic Cold Blood Hemorrhage PvP build; exact active ranks used by duel kernel are explicitly listed.'
    },
    mage_deep_frost_17_0_34:{
      id:'mage_deep_frost_17_0_34',class:'Mage',spec:'Frost',level:60,points:'17/0/34',
      calculator:'23001503102--05350233102351001',
      keyTalents:{improvedFrostbolt:5,elementalPrecision:3,iceShards:5,improvedFrostNova:2,permafrost:3,piercingIce:3,coldSnap:1,arcticReach:2,shatter:5,iceBlock:1,improvedConeOfCold:3,iceBarrier:1,arcaneResilience:1,improvedCounterspell:2},
      modifiers:{frostboltCastMs:2500,frostFireHitPct:6,frostCritMultiplier:2,frozenCritBonusPct:50,frostDamagePct:6,frostNovaCooldownMs:21000,chillDurationBonusMs:3000,chillSlowBonusPct:10,coneOfColdDamagePct:35,armorFromIntellectPct:50,counterspellSilenceMs:4000},
      sourceNote:'Classic Deep Frost PvP 17/0/34. Kernel only applies talents whose numeric effects are verified.'
    }
  };

  D.pvpSpellbooks={
    Rogue:{
      stealth:{id:1787,name:'Stealth',cost:0,gcdMs:0,cooldownMs:10000,movePct:-30,stealthValue:300},
      cheapShot:{id:1833,name:'Cheap Shot',cost:60,gcdMs:1000,range:5,stunMs:4000,combo:2,requiresStealth:true,cannotDodgeParryBlock:true},
      hemorrhage:{id:17348,name:'Hemorrhage',cost:35,gcdMs:1000,range:5,weaponDamagePct:100,combo:1,debuffDamageTaken:7,debuffCharges:30,debuffMs:15000},
      kidneyShot:{id:8643,name:'Kidney Shot',cost:25,gcdMs:1000,cooldownMs:20000,range:5,stunMsByCombo:[0,2000,3000,4000,5000,6000]},
      eviscerate:{id:31016,name:'Eviscerate',cost:35,gcdMs:1000,range:5,baseByCombo:{1:[224,332],2:[394,502],3:[564,672],4:[734,842],5:[904,1012]},apCoeffPerCombo:0.03},
      blind:{id:2094,name:'Blind',cost:30,gcdMs:1000,cooldownMs:300000,range:10,disorientMs:10000,breaksOnDamage:true},
      kick:{id:1769,name:'Kick',cost:25,gcdMs:1000,cooldownMs:10000,range:5,damage:80,schoolLockMs:5000},
      coldBlood:{id:14177,name:'Cold Blood',cost:0,gcdMs:0,cooldownMs:180000,nextCritBonusPct:100},
      preparation:{id:14185,name:'Preparation',cost:0,gcdMs:1000,cooldownMs:600000},
      vanish:{id:1857,name:'Vanish',cost:0,gcdMs:0,cooldownMs:300000},
      sprint:{id:11305,name:'Sprint',cost:0,gcdMs:0,cooldownMs:300000}
    },
    Mage:{
      frostbolt:{id:25304,name:'Frostbolt',cost:290,gcdMs:1500,range:30,castMs:3000,damage:[515,555],spCoeff:0.8143,slowPct:40,slowMs:9000,school:'Frost'},
      frostNova:{id:10230,name:'Frost Nova',cost:145,gcdMs:1500,cooldownMs:25000,radius:10,damage:[71,79],spCoeff:0.193,rootMs:8000,school:'Frost'},
      coneOfCold:{id:10161,name:'Cone of Cold',cost:555,gcdMs:1500,cooldownMs:10000,radius:10,damage:[335,365],spCoeff:0.1357,slowPct:50,slowMs:8000,school:'Frost'},
      fireBlast:{id:10199,name:'Fire Blast',cost:340,gcdMs:1500,cooldownMs:8000,range:20,damage:[446,524],spCoeff:0.4286,school:'Fire'},
      polymorph:{id:12826,name:'Polymorph',cost:150,gcdMs:1500,range:30,castMs:1500,disorientMs:50000,breaksOnDamage:true,school:'Arcane'},
      blink:{id:1953,name:'Blink',costPctBaseMana:35,gcdMs:1500,cooldownMs:15000,distance:20,breaks:['stun','root']},
      counterspell:{id:2139,name:'Counterspell',cost:100,gcdMs:0,cooldownMs:30000,range:30,schoolLockMs:10000},
      iceBarrier:{id:11426,name:'Ice Barrier',cost:305,gcdMs:1500,cooldownMs:30000,durationMs:60000,absorbBase:455,spCoeff:0.10,school:'Frost'},
      manaShield:{id:10193,name:'Mana Shield',cost:140,gcdMs:1500,durationMs:60000,absorb:570,manaPerDamage:2,schools:['Physical']},
      iceBlock:{id:11958,name:'Ice Block',cost:15,gcdMs:1500,cooldownMs:300000,durationMs:10000,immune:true,school:'Frost'},
      coldSnap:{id:12472,name:'Cold Snap',cost:0,gcdMs:0,cooldownMs:600000,resetsSchool:'Frost'}
    }
  };

  D.pvpProfiles=D.pvpProfiles||{};
  D.pvpProfiles.mage_frost_gnome_p6_core={
    id:'mage_frost_gnome_p6_core',class:'Mage',spec:'Frost',race:'Gnome',level:60,gearLabel:'Level 60 PvP BiS',buildId:'mage_deep_frost_17_0_34',
    itemIds:[16441,22943,16444,23017,22496,22503,16440,22502,22497,22500,23062,21707,22799,22821],
    trinkets:[{id:18859,name:'Insignia of the Alliance'},{id:19024,name:'Arena Grand Master'}],
    stats:{health:4280,mana:6257,armorBeforeTalents:1020,strength:25,agility:38,stamina:299,intellect:355,spirit:166,spellDamage:596,spellCritPct:14.16,spellHitPct:5,spellPen:101,dodgePct:5.15,resist:{arcane:15,fire:5,nature:5,frost:5,shadow:5}},
    utility:{arenaGrandMaster:{dodgePct:1,absorb:[750,1250],durationMs:20000,cooldownMs:1800000},insignia:{cooldownMs:300000,removes:['fear','polymorph','slow']}},
    kernelReady:true,
    provenance:'Current Classic Wowhead Gnome Phase-6 PvP core aggregate + explicit utility trinkets. Talent modifiers are applied separately by the duel kernel.'
  };

  D.pvpProfiles.rogue_sub_undead_p6_static={
    id:'rogue_sub_undead_p6_static',class:'Rogue',spec:'Subtlety',race:'Undead',level:60,gearLabel:'Level 60 PvP BiS',buildId:'rogue_cb_hemo_21_3_27',
    kernelReady:true,
    dynamic:{energyMax:100,energyTick:20,energyTickMs:2000,bonescythe2pPPM:1,bonescythe4pEnergyOnBuilderCrit:5,crusaderPPM:1,crusaderStrength:100,crusaderDurationMs:15000,crusaderHeal:[75,125]},
    provenance:'Existing 17-slot verified static profile + verified 21/3/27 PvP build. Dynamic PPM values are isolated from static totals.'
  };

  D.pvpKernel={
    id:'rogue_sub_vs_mage_frost_p6_v1',version:'0.9.0',
    supported:{a:{class:'Rogue',spec:'Subtlety',race:'Undead',gear:'Level 60 PvP BiS'},b:{class:'Mage',spec:'Frost',race:'Gnome',gear:'Level 60 PvP BiS'}},
    assumptions:[
      'Duel starts at 5 yd: Rogue stealthed; Mage has Ice Barrier and Mana Shield pre-cast and starts with full mana.',
      'Arena Grand Master starts available and is used defensively.',
      'No consumables, Engineering explosives or matchup weapon swaps in kernel v1.',
      'Movement is one-dimensional distance using the verified 7 yd/s base run speed; facing and terrain are not yet modeled.'
    ],
    sources:{
      movement:'Warcraft Wiki API_GetUnitSpeed: normal run 7 yd/s',
      damageCoefficients:'CMaNGOS classic spell_bonus_data / current Spell.sql fixes',
      characterMath:'CMaNGOS classic StatSystem.cpp'
    }
  };
})();
