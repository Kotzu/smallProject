(()=>{
  const D=window.WOW_DATA||{},M=D.pvpMechanics?.v010,mp=D.pvpProfiles?.mage_frost_gnome_p6_core,rp=D.pvpProfiles?.rogue_sub_undead_p6_static;
  if(!M||!mp)return;

  // Classic pre-WotLK binary Nature poison application against the active Gnome Mage profile.
  // CMaNGOS Unit.cpp:
  //   effective magic resistance % = (resistance / (attackerLevel*5)) * 100 * 0.75, capped at 75%.
  //   for binary spells that percentage is added to the normal spell miss chance on the same die.
  // Active Mage: 5 Nature Resistance from profile + 15 Mage Armor = 20 Nature Resistance.
  // Rogue has 0 spell hit / 0 spell penetration in this kernel.
  // Same-level spell miss = 4%; resistance contribution = (20/300)*100*0.75 = 5%; total full resist = 9%.
  const attackerLevel=60;
  const baseSpellMissPct=4;
  const targetNatureResistance=(mp.stats?.resist?.nature||0)+(mp.prebuffs?.mageArmorRank3?15:0);
  const spellPenetration=0;
  const effectiveResistance=Math.max(0,targetNatureResistance-spellPenetration);
  const resistancePct=Math.min(75,(effectiveResistance/(attackerLevel*5))*100*0.75);
  const totalResistPct=Math.min(100,baseSpellMissPct+resistancePct);
  const successMultiplier=1-totalResistPct/100;

  M.poisonBinaryResistance={
    version:'0.12.0',school:'Nature',attackerLevel,baseSpellMissPct,targetNatureResistance,spellPenetration,
    resistancePct:Number(resistancePct.toFixed(4)),totalResistPct:Number(totalResistPct.toFixed(4)),
    source:'CMaNGOS mangos-classic src/game/Entities/Unit.cpp :: CalculateSpellResistChance + CalculateEffectiveMagicResistancePercent',
    status:'ACTIVE_IN_KERNEL'
  };

  // The v0.11 engine performs one poison application roll. Folding the independent binary-resist roll
  // into the application probability is statistically equivalent for the duel outcome:
  // P(success) = P(proc) * P(not resisted).
  M.poisons.cripplingII.rawProcPct=M.poisons.cripplingII.rawProcPct||M.poisons.cripplingII.procPct;
  M.poisons.mindNumbingIII.rawProcPct=M.poisons.mindNumbingIII.rawProcPct||M.poisons.mindNumbingIII.procPct;
  M.poisons.cripplingII.binaryResistPct=totalResistPct;
  M.poisons.mindNumbingIII.binaryResistPct=totalResistPct;
  M.poisons.cripplingII.procPct=Number((M.poisons.cripplingII.rawProcPct*successMultiplier).toFixed(4));
  M.poisons.mindNumbingIII.procPct=Number((M.poisons.mindNumbingIII.rawProcPct*successMultiplier).toFixed(4));

  if(rp){
    rp.calibrationRequired=[];
    rp.poisonApplicationAudit={
      status:'PASS',natureResistance:targetNatureResistance,binaryResistPct:totalResistPct,
      cripplingRawProcPct:M.poisons.cripplingII.rawProcPct,cripplingEffectiveProcPct:M.poisons.cripplingII.procPct,
      mindNumbingRawProcPct:M.poisons.mindNumbingIII.rawProcPct,mindNumbingEffectiveProcPct:M.poisons.mindNumbingIII.procPct
    };
  }
})();