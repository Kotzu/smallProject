(()=>{
  const T=window.WOW_TALENTS,D=window.WOW_DATA;
  if(!T)return;
  const id='rogue_cb_hemo_21_3_27',b=T.get(id);
  if(!b)return;

  const byName=new Map((b.combatTalents||[]).map(x=>[x.name,x]));
  const add=x=>{if(!byName.has(x.name)){b.combatTalents.push(x);byName.set(x.name,x);}};

  add({name:'Ruthlessness',rank:'3/3',effect:'60% chance to add 1 combo point after any finishing move',modifier:'ruthlessnessProcPct',value:60});
  add({name:'Elusiveness',rank:'2/2',effect:'Vanish and Blind cooldown reduced by 90 sec',modifier:'elusivenessCooldownReductionMs',value:90000});
  add({name:'Initiative',rank:'3/3',effect:'75% chance for +1 combo point from Cheap Shot, Ambush or Garrote',modifier:'initiativeProcPct',value:75});
  add({name:'Improved Sap',rank:'3/3',effect:'90% chance to return to Stealth after Sap',modifier:'improvedSapStayStealthPct',value:90});
  add({name:'Heightened Senses',rank:'2/2',effect:'stealth detection +6; attackers have -4% spell and ranged hit against Rogue',modifier:'attackerSpellRangedHitPenaltyPct',value:4});
  add({name:'Master of Deception',rank:'5/5',effect:'+15 Stealth effectiveness',modifier:'stealthEffectivenessBonus',value:15});

  Object.assign(b.modifiers||={}, {
    ruthlessnessProcPct:60,
    initiativeProcPct:75,
    elusivenessCooldownReductionMs:90000,
    improvedSapStayStealthPct:90,
    attackerSpellRangedHitPenaltyPct:4,
    stealthDetectionBonus:6,
    stealthEffectivenessBonus:15
  });

  b.runtimeFidelity=b.runtimeFidelity||{};
  Object.assign(b.runtimeFidelity,{
    initiative:'REGISTERED_PENDING_ENGINE_V018',
    ruthlessness:'REGISTERED_PENDING_ENGINE_V018',
    preparation:'REGISTERED_PENDING_ENGINE_V018',
    elusiveness:'REGISTERED_PENDING_ENGINE_V018',
    heightenedSenses:'REGISTERED_FORMULA_AUDIT'
  });

  if(D?.pvpBuilds?.[id]){
    Object.assign(D.pvpBuilds[id].modifiers||={},b.modifiers);
  }
})();
