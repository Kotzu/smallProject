(()=>{
  const D=window.WOW_DATA=window.WOW_DATA||{};
  const base=D.profiles?.rogue_subtlety_lvl60_pvp_bis_p6_baseline;
  if(!base)return;

  D.items=D.items||{};
  D.items['22802']={
    id:22802,name:'Kingsfall',slot:'Main Hand',itemLevel:89,armor:0,str:0,agi:16,sta:0,ap:0,hit:1,crit:1,shadowRes:0,
    weapon:{type:'Dagger',minDamage:105,maxDamage:158,speed:1.8,dps:73.06},
    verified:true,source:'https://www.wowhead.com/classic/item=22802/kingsfall'
  };
  D.items['21126']={
    id:21126,name:"Death's Sting",slot:'Off Hand',itemLevel:84,armor:0,str:0,agi:0,sta:10,ap:38,hit:0,crit:0,shadowRes:0,daggerSkill:3,
    weapon:{type:'Dagger',minDamage:95,maxDamage:144,speed:1.8,dps:66.39},
    verified:true,source:'https://www.wowhead.com/classic/item=21126/deaths-sting'
  };

  D.enchants=D.enchants||{};
  D.enchants.superior_striking={
    name:'Enchant Weapon - Superior Striking',slot:'Main Hand',spellId:20031,weaponDamage:5,verified:true,
    source:'https://www.wowhead.com/classic/spell=20031/enchant-weapon-superior-striking'
  };

  const c=base.combinedStaticTotals;
  const combinedStaticTotals={
    ...c,
    agi:(c.agi||0)-8+16,
    sta:(c.sta||0)-23+10,
    ap:(c.ap||0)-40+38,
    hit:c.hit,
    crit:c.crit
  };

  D.profiles.rogue_subtlety_lvl60_pvp_bis_p6_daggers={
    ...base,
    id:'rogue_subtlety_lvl60_pvp_bis_p6_daggers',
    name:'Rogue Improved Sprint / Backstab — Level 60 PvP BiS Phase 6 daggers',
    buildId:'rogue_imp_sprint_backstab_17_12_22',
    status:'STATIC_GEAR_VERIFIED_KERNEL_LOCKED',
    note:'Verified dagger loadout for the 17/12/22 Improved Sprint Backstab build. Combat kernel remains locked until positional Backstab/Ambush logic is calibrated.',
    slots:{...base.slots,'Main Hand':22802,'Off Hand':21126},
    enchants:(base.enchants||[]).filter(x=>x!=='crusader').concat('superior_striking'),
    combinedStaticTotals,
    mainHandFlatDamage:5,
    offHandFlatDamage:0,
    weaponSkill:{Dagger:3},
    fullCharacterStatsReady:false,
    fullCharacterStatsMissing:['positional Backstab/Ambush kernel calibration','weapon-skill PvP combat-table validation for +3 Dagger skill']
  };

  const p=D.profiles.rogue_subtlety_lvl60_pvp_bis_p6_daggers;
  const agi=p.combinedStaticTotals.agi,sta=p.combinedStaticTotals.sta,str=p.combinedStaticTotals.str;
  p.derivedRogueLevel60GearContributions={
    meleeAttackPowerFromStrAgi:str+agi,
    totalStaticGearMeleeAPContribution:str+agi+p.combinedStaticTotals.ap,
    armorFromAgility:agi*2,
    totalStaticGearArmorContribution:p.combinedStaticTotals.armor+agi*2,
    healthFromStamina:sta*10,
    totalStaticGearHealthContribution:sta*10+(p.combinedStaticTotals.directHealth||0),
    critFromAgilityPct:agi/29,
    totalStaticGearCritContributionPct:(p.combinedStaticTotals.crit||0)+agi/29,
    dodgeFromAgilityPct:agi/14.5,
    totalStaticGearDodgeContributionPct:(p.combinedStaticTotals.directDodge||0)+agi/14.5,
    hitPct:p.combinedStaticTotals.hit||0
  };
})();
