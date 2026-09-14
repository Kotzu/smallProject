window.WOW_CHARACTER_ENGINE=(function(){
  function healthBonusFromStamina(stamina){const base=Math.min(stamina,20);return base+(stamina-base)*10;}
  function manaBonusFromIntellect(intellect){const base=Math.min(intellect,20);return base+(intellect-base)*15;}
  function applyPctStat(value,pct){return Math.trunc(value*(1+pct/100));}
  function rogueMeleeAP(level,str,agi,flatAP){return level*2+str+agi-20+(flatAP||0);}
  function mageMeleeAP(str,flatAP){return str-10+(flatAP||0);}
  function armorFromAgility(agi){return agi*2;}
  function weaponDamageRange(min,max,speed,attackPower,flatWeaponDamage){const apPart=attackPower/14*speed;const add=flatWeaponDamage||0;return {min:min+apPart+add,max:max+apPart+add};}
  function mergeStats(base,gear){return {str:base.str+(gear.str||0),agi:base.agi+(gear.agi||0),sta:base.sta+(gear.sta||0),int:base.int+(gear.int||0),spi:base.spi+(gear.spi||0)};}
  function rogue60Baseline(character,profile){
    const s=mergeStats(character.createStats,profile.combinedStaticTotals);
    const hp=character.classBase.health+healthBonusFromStamina(s.sta)+(profile.combinedStaticTotals.directHealth||0);
    const ap=rogueMeleeAP(character.level,s.str,s.agi,profile.combinedStaticTotals.ap||0);
    const armor=(profile.combinedStaticTotals.armor||0)+armorFromAgility(s.agi);
    const mh=window.WOW_DATA.items[String(profile.slots['Main Hand'])].weapon;
    const oh=window.WOW_DATA.items[String(profile.slots['Off Hand'])].weapon;
    return {
      stats:s,health:hp,attackPower:ap,armor,
      mainHand:weaponDamageRange(mh.minDamage,mh.maxDamage,mh.speed,ap,profile.mainHandFlatDamage||0),
      offHandBeforeOffhandPenalty:weaponDamageRange(oh.minDamage,oh.maxDamage,oh.speed,ap,profile.offHandFlatDamage||0),
      hitPct:profile.combinedStaticTotals.hit||0,
      shadowResistance:(profile.combinedStaticTotals.shadowRes||0)+(character.racialCombat.shadowResistance||0),
      weaponSkill:{...(profile.weaponSkill||{})}
    };
  }
  function gnomeMage60Naked(character){
    const raw=character.createStats;
    const intellect=applyPctStat(raw.int,character.racialCombat.expansiveMindIntPct||0);
    const hp=character.classBase.health+healthBonusFromStamina(raw.sta);
    const mana=character.classBase.mana+manaBonusFromIntellect(intellect);
    return {stats:{...raw,int:intellect},health:hp,mana,armor:armorFromAgility(raw.agi)};
  }
  return {healthBonusFromStamina,manaBonusFromIntellect,applyPctStat,rogueMeleeAP,mageMeleeAP,armorFromAgility,weaponDamageRange,rogue60Baseline,gnomeMage60Naked};
})();
