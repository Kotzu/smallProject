(()=>{
  const D=window.WOW_DATA=window.WOW_DATA||{};
  D.pvpSpellbooks=D.pvpSpellbooks||{};
  D.pvpSpellbooks.Mage=D.pvpSpellbooks.Mage||{};
  Object.assign(D.pvpSpellbooks.Mage,{
    iceBarrier:{id:13033,name:'Ice Barrier',rank:4,cost:480,gcdMs:1500,cooldownMs:30000,durationMs:60000,absorbBase:818,spCoeff:0.10,school:'Frost'},
    manaShield:{id:10193,name:'Mana Shield',rank:6,cost:140,gcdMs:1500,durationMs:60000,absorbBase:570,manaPerDamage:2,school:'Arcane'},
    mageArmor:{id:22783,name:'Mage Armor',rank:3,cost:490,gcdMs:1500,durationMs:1800000,resistanceAll:15,castingRegenPct:30,school:'Arcane'},
    escapeArtist:{id:20589,name:'Escape Artist',castMs:500,gcdMs:1500,cooldownMs:60000,school:'Physical',removes:['root','snare']}
  });

  D.pvpMechanics=D.pvpMechanics||{};
  D.pvpMechanics.v010={
    version:'0.10.1',
    dualWield:{baseSameLevelMissPct:5,whitePenaltyPct:19,offhandDamageMultiplier:0.50},
    poisons:{
      cripplingII:{itemId:3776,procPct:30,slowPct:70,durationMs:12000},
      mindNumbingIII:{itemId:9186,procPct:20,castTimeIncreasePct:60,durationMs:14000}
    },
    handOfJustice:{itemId:11815,procPct:2,internalCooldownMs:2000,extraMainHandAttacks:1},
    bonescythe4p:{piecesRequired:4,energyOnBuilderCrit:5,builders:['Hemorrhage','Backstab','Sinister Strike']},
    bonescythe2p:{piecesRequired:2,healMin:90,healMax:110,status:'CALIBRATION_REQUIRED',note:'Current sources disagree on exact PPM; excluded from duel outcome until resolved.'},
    crusader:{effectId:1900,procSpellId:20007,ppm:1,strength:100,healMin:75,healMax:125,durationMs:15000,status:'VERIFIED',note:'WoWSims Classic uses a 1.0 PPM manager; Wowhead Classic Holy Strength confirms +100 STR and 75-125 heal for 15s at level 60.'},
    magePvpSet:{piecesEquipped:3,blinkCooldownReductionMs:1500},
    frostfire6p:{piecesEquipped:6,procPct:20,debuffMs:30000,bonusSpellPowerForNextHit:200},
    elementalPrecision:{rank:3,spellHitPct:6,manaCostReductionPct:3,schools:['Frost','Fire']},
    permafrost:{rank:3,slowPctBonus:10,slowDurationBonusMs:3000},
    sources:{
      combatTable:'CMaNGOS Unit.cpp: dual-wield white attacks add 19% miss penalty.',
      offhand:'WoW Classic Dual Wield: off-hand auto attacks deal 50% damage.',
      poisons:'Wowhead Classic Crippling Poison II / Mind-numbing Poison III tooltips.',
      hoj:'Wowhead Classic Hand of Justice: 2% proc, 2s cooldown.',
      crusader:'WoWSims Classic enchant_effects.go: Crusader NewPPMManager(1.0); Wowhead Classic spell 20007: heal 75-125, +100 STR, 15s.',
      mageSpells:'Wowhead Classic spell tooltips; CMaNGOS spell bonus data for coefficients.',
      frostfire:'Wowhead Classic Frostfire Regalia / Elemental Vulnerability.',
      escapeArtist:'Wowhead Classic Escape Artist: 0.5s cast, 60s cooldown.'
    }
  };

  const mp=D.pvpProfiles?.mage_frost_gnome_p6_core;
  if(mp){
    mp.setBonuses={
      fieldMarshals:{pieces:3,blinkCooldownMs:13500},
      frostfire:{pieces:6,elementalVulnerabilityProcPct:20,elementalVulnerabilityDurationMs:30000,elementalVulnerabilitySpellPower:200}
    };
    mp.prebuffs={mageArmorRank3:true,iceBarrierRank4:true,manaShieldRank6:true};
    mp.gearEffects={manaShieldBonusAbsorb:285};
  }
  const rp=D.pvpProfiles?.rogue_sub_undead_p6_static;
  if(rp){
    rp.weaponSetup={mainHandPoison:'cripplingII',offHandPoison:'mindNumbingIII'};
    rp.verifiedDynamics={
      dualWieldWhitePenaltyPct:19,
      offhandDamageMultiplier:0.50,
      handOfJusticeProcPct:2,
      handOfJusticeIcdMs:2000,
      bonescythe4pEnergyOnBuilderCrit:5,
      crusaderPpm:1
    };
    rp.calibrationRequired=['Bonescythe 2p exact PPM','binary poison resistance vs target Nature resistance'];
  }
})();
