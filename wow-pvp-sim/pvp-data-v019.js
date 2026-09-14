(()=>{
  const D=window.WOW_DATA=window.WOW_DATA||{};
  const R=D.pvpSpellbooks?.Rogue;
  if(!R)return;

  D.v019=D.v019||{};

  // PvP weapon skill: CMaNGOS uses full weapon skill (including bonuses) against players.
  // Miss and avoidance use a 0.04% factor per skill point difference in Classic PvP.
  // Death's Sting grants +3 Daggers => 303 weapon skill vs 300 defense: -0.12% miss and -0.12% dodge.
  D.v019.rogueDaggerWeaponSkill={
    status:'VERIFIED',
    weaponSkill:303,
    targetDefense:300,
    skillDelta:3,
    missReductionPct:0.12,
    dodgeReductionPct:0.12,
    critBonusPctVsPlayer:0,
    source:'CMaNGOS mangos-classic Unit.cpp :: GetWeaponSkillValue / CalculateEffectiveMissChance / melee avoidance calculations',
    note:'Against player targets, +weapon skill affects miss/avoidance through the 0.04% per point factor; CMaNGOS does not grant the +skill crit benefit vs player-controlled targets.'
  };

  // Direct Classic talent mechanics used by the canonical 16/12/23 dagger build.
  D.v019.rogueTalentMechanics={
    improvedSprint:{
      rank:2,procPct:100,removesMovementImpairingOnActivation:true,status:'VERIFIED',
      source:'Wowhead Classic Improved Sprint spell 13875'
    },
    initiative:{
      rank:3,procPct:75,extraComboPoints:1,affected:['Ambush','Garrote','Cheap Shot'],status:'VERIFIED',
      source:'Wowhead Classic Initiative spell 13980'
    },
    improvedGouge:{
      rank:3,bonusDurationMs:1500,baseDurationMs:4000,totalDurationMs:5500,status:'VERIFIED',
      source:'Wowhead Classic Improved Gouge spell 13792 + Gouge rank 5 spell 11286'
    },
    elusiveness:{
      rank:2,vanishCooldownReductionMs:90000,blindCooldownReductionMs:90000,
      vanishCooldownMs:210000,blindCooldownMs:210000,status:'VERIFIED',
      source:'Wowhead Classic Rogue talent guide: Elusiveness reduces Vanish and Blind to 3.5 minutes'
    }
  };

  // Attach exact cooldown metadata to the spellbook so future kernels consume it instead of hardcoding.
  if(R.vanish){
    R.vanish.baseCooldownMs=R.vanish.baseCooldownMs||R.vanish.cooldownMs||300000;
    R.vanish.elusiveness2CooldownMs=210000;
  }
  if(R.blind){
    R.blind.baseCooldownMs=R.blind.baseCooldownMs||R.blind.cooldownMs||300000;
    R.blind.elusiveness2CooldownMs=210000;
  }
  if(R.gouge){
    R.gouge.improvedGouge3DurationMs=5500;
  }

  const p=D.profiles?.rogue_subtlety_lvl60_pvp_bis_p6_daggers;
  if(p){
    p.weaponSkillAudit={...D.v019.rogueDaggerWeaponSkill};
    p.fullCharacterStatsMissing=(p.fullCharacterStatsMissing||[]).filter(x=>!String(x).includes('weapon-skill'));
    p.fullCharacterStatsMissing.push('positional Backstab/Ambush kernel calibration');
    p.fullCharacterStatsMissing=[...new Set(p.fullCharacterStatsMissing)];
  }
})();
