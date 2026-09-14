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
    backstab:{status:'VERIFIED_LUA_ENGINE',spellId:11281,cost:60,weaponPct:150,flatDamage:210,requiresBehind:true,requiresDagger:true,formula:'((weapon roll + flat weapon enchant + AP/14*1.7)*1.5 + 210) * (1 + Opportunity%)',crit:'base 2.0 + 0.06 per Lethality rank'},
    ambush:{status:'VERIFIED_LUA_ENGINE',spellId:11269,cost:60,weaponPct:250,flatDamage:290,requiresBehind:true,requiresStealth:true,requiresDagger:true,formula:'((weapon roll + flat weapon enchant + AP/14*1.7)*2.5 + 290) * (1 + Opportunity%)',crit:'base 2.0; Classic Lethality does not affect Ambush'},
    gouge:{status:'VERIFIED_LUA_ENGINE',spellId:11286,cost:45,damage:75,cooldownMs:10000,baseDurationMs:4000,improvedGouge3DurationMs:5500,breaksOnDamage:true}
  };

  D.v022={
    positioning:{
      status:'REAR_ARC_VERIFIED_RUNTIME_PARTIAL',
      defaultBackArcRadians:Math.PI,
      backArcDegrees:180,
      meleeDistanceYards:5,
      webDistanceModel:'center-to-center 2D',
      exactParityPending:'CMaNGOS combat-reach/bounding-radius distance adjustment',
      source:'CMaNGOS mangos-classic Object.cpp WorldObject::isInBack + HasInArc; PlayerbotRogueAI uses isInBackInMap(..., 5.0f) for Ambush',
      policyAction:'MOVE_BEHIND'
    }
  };

  // Exact action inventory gaps that must be represented before the first matchup can be called complete.
  D.v027={
    rogueBlind:{
      status:'VERIFIED_DATA_KERNEL_LOCKED_HEARTBEAT',spellId:2094,cost:30,range:10,gcdMs:1000,cooldownMs:300000,durationMs:10000,
      school:'Nature',dispelType:'Poison',mechanic:'Disoriented',breaksOnDamage:true,stopsAutoAttack:true,heartbeatResist:true,
      source:'Wowhead Classic spell 2094 + CMaNGOS aura heartbeat system',
      blocker:'Exact retail heartbeat-resist distribution is not sufficiently verified; CMaNGOS labels its heartbeat approximation experimental.'
    },
    mageInsignia18859:{
      status:'VERIFIED_KERNEL_PENDING',itemId:18859,cooldownMs:300000,
      removes:['Fear','Polymorph','Slowing'],
      relevantCurrentMatchup:'Crippling Poison slow',
      source:'Wowhead Classic item 18859',
      blocker:'Mage action policy + web-kernel use path not active yet.'
    }
  };

  const canonical=T?.get?.('rogue_imp_sprint_backstab_16_12_23');
  if(canonical){
    canonical.kernelBlockers=[
      'web-kernel MOVE_BEHIND execution + CMaNGOS combat-reach radius parity',
      'web-kernel execution of Backstab/Ambush/Gouge via ClassCombat policy',
      'Initiative extra-combo-point execution on Ambush/Garrote/Cheap Shot',
      'Lua↔web policy parity QA'
    ];
    canonical.auditNotes=[...(canonical.auditNotes||[]),
      'CMaNGOS rear arc: default PI radians / 180 degrees — verified',
      'Rogue ClassCombat.lua emits MOVE_BEHIND before positional dagger attacks'
    ];
  }
  const variant=T?.get?.('rogue_imp_sprint_backstab_17_12_22');
  if(variant){
    variant.kernelBlockers=[
      'web-kernel MOVE_BEHIND execution + CMaNGOS combat-reach radius parity',
      'web-kernel execution of Backstab/Ambush/Gouge via ClassCombat policy',
      'Lua↔web policy parity QA'
    ];
    variant.auditNotes=[...(variant.auditNotes||[]),
      'CMaNGOS rear arc: default PI radians / 180 degrees — verified',
      'No Initiative blocker: this 17/12/22 variant does not use Initiative'
    ];
  }
})();