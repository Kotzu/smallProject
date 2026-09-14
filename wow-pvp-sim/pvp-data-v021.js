(()=>{
  const D=window.WOW_DATA=window.WOW_DATA||{},T=window.WOW_TALENTS;
  D.v021=D.v021||{};
  D.v021.weaponNormalization={
    status:'VERIFIED',
    dagger:1.7,oneHand:2.4,twoHand:3.3,ranged:2.8,
    formula:'base weapon roll + normalizedSpeed * AP / 14',
    source:'Warcraft Wiki Normalization; Classic patch 1.8+ instant weapon attacks'
  };
  D.v021.rogueDaggerAbilityMath={
    backstab:{
      status:'VERIFIED_LUA_ENGINE',spellId:11281,cost:60,weaponPct:150,flatDamage:210,requiresBehind:true,requiresDagger:true,
      formula:'((weapon roll + flat weapon enchant + AP/14*1.7)*1.5 + 210) * (1 + Opportunity%)',
      crit:'base 2.0 + 0.06 per Lethality rank'
    },
    ambush:{
      status:'VERIFIED_LUA_ENGINE',spellId:11269,cost:60,weaponPct:250,flatDamage:290,requiresBehind:true,requiresStealth:true,requiresDagger:true,
      formula:'((weapon roll + flat weapon enchant + AP/14*1.7)*2.5 + 290) * (1 + Opportunity%)',
      crit:'base 2.0; Classic Lethality does not affect Ambush'
    },
    gouge:{
      status:'VERIFIED_LUA_ENGINE',spellId:11286,cost:45,damage:75,cooldownMs:10000,baseDurationMs:4000,improvedGouge3DurationMs:5500,breaksOnDamage:true
    }
  };

  for(const id of ['rogue_imp_sprint_backstab_16_12_23','rogue_imp_sprint_backstab_17_12_22']){
    const b=T?.get?.(id);if(!b)continue;
    b.kernelBlockers=[
      '2D/facing positional behind-state model',
      'web-kernel execution of Backstab/Ambush/Gouge via ClassCombat policy',
      'Initiative proc on Ambush/Garrote path',
      'Lua↔web policy parity QA'
    ];
    b.auditNotes=[...(b.auditNotes||[]),
      'Patch 1.8+ normalized dagger speed = 1.7 — verified',
      'Backstab R9 normalized formula + Opportunity + Lethality interaction — verified in CombatEngine.lua',
      'Ambush R6 normalized formula + Opportunity; Lethality excluded — verified in CombatEngine.lua',
      'Gouge R5 4.0s / Improved Gouge 3/3 5.5s and break-on-damage semantics — implemented in CombatEngine.lua'
    ];
  }
})();