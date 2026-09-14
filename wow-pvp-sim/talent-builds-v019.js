(()=>{
  const D=window.WOW_DATA||{},T=window.WOW_TALENTS;
  if(!T)return;

  const canonical=T.get('rogue_imp_sprint_backstab_16_12_23');
  if(canonical){
    canonical.modifiers={
      ...(canonical.modifiers||{}),
      vanishCooldownMs:210000,
      blindCooldownMs:210000,
      daggerWeaponSkill:303,
      weaponSkillMissReductionPct:0.12,
      weaponSkillDodgeReductionPct:0.12,
      improvedGougeDurationMs:5500
    };
    canonical.kernelBlockers=[
      'positional behind-state model',
      'Initiative extra-combo-point proc path',
      'Gouge control/break-on-damage path',
      'policy parity QA'
    ];
    canonical.auditNotes=[
      'Improved Sprint 2/2: 100% movement-impair removal on Sprint activation — verified',
      'Initiative 3/3: 75% +1 CP on Ambush/Garrote/Cheap Shot — verified data, kernel path pending',
      'Improved Gouge 3/3: 5.5s total Gouge duration — verified data, kernel path pending',
      'Elusiveness 2/2: Blind/Vanish 300s → 210s — verified',
      "Death's Sting +3 Daggers: -0.12% miss and -0.12% target dodge vs level-60 player — verified CMaNGOS math"
    ];
  }

  const variant=T.get('rogue_imp_sprint_backstab_17_12_22');
  if(variant){
    variant.modifiers={
      ...(variant.modifiers||{}),
      daggerWeaponSkill:303,
      weaponSkillMissReductionPct:0.12,
      weaponSkillDodgeReductionPct:0.12,
      improvedGougeDurationMs:5500
    };
    variant.kernelBlockers=[
      'positional behind-state model',
      'Gouge control/break-on-damage path',
      'policy parity QA'
    ];
    variant.auditNotes=[
      'Improved Sprint 2/2 movement break — verified',
      'Improved Gouge 3/3 = 5.5s — verified data, kernel path pending',
      "Death's Sting +3 Daggers PvP miss/dodge interaction — verified CMaNGOS math"
    ];
  }

  D.talentBuildLibrary=T.library;
  window.WOW_TALENTS={...T,version:'0.19'};
})();
