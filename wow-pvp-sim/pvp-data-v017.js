(()=>{
  const D=window.WOW_DATA||{},R=D.pvpSpellbooks?.Rogue;
  if(!R)return;

  R.backstab={
    id:11281,name:'Backstab',rank:9,cost:60,gcdMs:1000,range:5,combo:1,
    requiresMainHandType:'Dagger',requiresBehind:true,weaponDamagePct:150,flatDamage:225,
    kernelStatus:'VERIFIED_LOCKED_POSITIONAL'
  };
  R.ambush={
    id:11269,name:'Ambush',rank:6,cost:60,gcdMs:1000,range:5,combo:1,
    requiresStealth:true,requiresMainHandType:'Dagger',requiresBehind:true,weaponDamagePct:250,flatDamage:290,
    kernelStatus:'VERIFIED_LOCKED_POSITIONAL'
  };
  R.sinisterStrike={
    id:11294,name:'Sinister Strike',rank:8,cost:45,gcdMs:1000,range:5,combo:1,
    weaponDamagePct:100,flatDamage:68,kernelStatus:'VERIFIED_NOT_ACTIVE_FOR_CURRENT_BUILD'
  };

  D.v017=D.v017||{};
  D.v017.rogueDaggerKernel={
    buildId:'rogue_imp_sprint_backstab_17_12_22',
    loadoutProfileId:'rogue_subtlety_lvl60_pvp_bis_p6_daggers',
    status:'STRICT_LOCKED',
    verifiedAbilities:['Backstab Rank 9','Ambush Rank 6','Sinister Strike Rank 8'],
    remaining:['positional behind-state model','Gouge exact active rank/damage/control model','dagger weapon-skill combat-table validation','policy parity QA']
  };
})();
