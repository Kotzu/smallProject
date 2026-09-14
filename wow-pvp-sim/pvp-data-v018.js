(()=>{
  const D=window.WOW_DATA=window.WOW_DATA||{};
  const R=D.pvpSpellbooks?.Rogue;
  if(!R)return;

  // Accuracy correction: Classic Backstab rank 9 (spell 11281) is 150% weapon damage +210.
  if(R.backstab){
    R.backstab.rank=9;
    R.backstab.id=11281;
    R.backstab.flatDamage=210;
    R.backstab.weaponDamagePct=150;
    R.backstab.cost=60;
    R.backstab.requiresBehind=true;
    R.backstab.requiresMainHandType='Dagger';
    R.backstab.source='Wowhead Classic spell 11281';
  }

  R.gouge={
    id:11286,name:'Gouge',rank:5,cost:45,gcdMs:1000,cooldownMs:10000,range:5,
    damage:75,combo:1,incapacitateMs:4000,breaksOnDamage:true,requiresTargetFacingCaster:true,
    requiresMainHandWeapon:true,school:'Physical',
    source:'Wowhead Classic spell 11286'
  };

  // CMaNGOS Classic Rogue.cpp: Preparation removes cooldown from Rogue-family spells except Preparation itself.
  const prep=R.preparation||(R.preparation={id:14185,name:'Preparation',cost:0,gcdMs:1000,cooldownMs:600000});
  prep.resetsRogueFamilyCooldowns=true;
  prep.excludesSelf=true;
  prep.source='CMaNGOS mangos-classic Rogue.cpp :: Preparation';

  D.v018=D.v018||{};
  D.v018.rogueTalentMechanics={
    backstab:{status:'VERIFIED',spellId:11281,weaponDamagePct:150,flatDamage:210,cost:60,requiresBehind:true},
    ambush:{status:'VERIFIED',spellId:11269,weaponDamagePct:250,flatDamage:290,cost:60,requiresBehind:true,cannotDodgeParryBlock:true},
    gouge:{status:'VERIFIED_DATA_KERNEL_PENDING',spellId:11286,damage:75,cost:45,durationMs:4000,cooldownMs:10000},
    preparation:{status:'VERIFIED_DATA_KERNEL_PENDING',spellId:14185,resets:'all Rogue-family cooldowns except itself'},
    canonicalDaggerBuild:{id:'rogue_imp_sprint_backstab_16_12_23',points:'16/12/23',status:'VERIFIED_LOCKED_KERNEL'},
    forumDaggerVariant:{id:'rogue_imp_sprint_backstab_17_12_22',points:'17/12/22',status:'VERIFIED_LOCKED_KERNEL'}
  };
})();
