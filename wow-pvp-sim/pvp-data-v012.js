(()=>{
  const D=window.WOW_DATA||{},M=D.pvpMechanics?.v010,mp=D.pvpProfiles?.mage_frost_gnome_p6_core,rp=D.pvpProfiles?.rogue_sub_undead_p6_static;
  if(!M||!mp)return;

  const attackerLevel=60;
  const baseSpellMissPct=4;
  const targetNatureResistance=(mp.stats?.resist?.nature||0)+(mp.prebuffs?.mageArmorRank3?15:0);
  const spellPenetration=0;
  const effectiveResistance=Math.max(0,targetNatureResistance-spellPenetration);
  const resistancePct=Math.min(75,(effectiveResistance/(attackerLevel*5))*100*0.75);
  const totalResistPct=Math.min(100,baseSpellMissPct+resistancePct);
  const successMultiplier=1-totalResistPct/100;

  M.poisonBinaryResistance={version:'0.12.0',school:'Nature',attackerLevel,baseSpellMissPct,targetNatureResistance,spellPenetration,resistancePct:Number(resistancePct.toFixed(4)),totalResistPct:Number(totalResistPct.toFixed(4)),source:'CMaNGOS mangos-classic src/game/Entities/Unit.cpp',status:'ACTIVE_IN_KERNEL'};
  M.poisons.cripplingII.rawProcPct=M.poisons.cripplingII.rawProcPct||M.poisons.cripplingII.procPct;
  M.poisons.mindNumbingIII.rawProcPct=M.poisons.mindNumbingIII.rawProcPct||M.poisons.mindNumbingIII.procPct;
  M.poisons.cripplingII.binaryResistPct=totalResistPct;
  M.poisons.mindNumbingIII.binaryResistPct=totalResistPct;
  M.poisons.cripplingII.procPct=Number((M.poisons.cripplingII.rawProcPct*successMultiplier).toFixed(4));
  M.poisons.mindNumbingIII.procPct=Number((M.poisons.mindNumbingIII.rawProcPct*successMultiplier).toFixed(4));

  if(rp){rp.calibrationRequired=[];rp.poisonApplicationAudit={status:'PASS',natureResistance:targetNatureResistance,binaryResistPct:totalResistPct,cripplingRawProcPct:M.poisons.cripplingII.rawProcPct,cripplingEffectiveProcPct:M.poisons.cripplingII.procPct,mindNumbingRawProcPct:M.poisons.mindNumbingIII.rawProcPct,mindNumbingEffectiveProcPct:M.poisons.mindNumbingIII.procPct};}

  const builds={
    rogue_cb_hemo_21_3_27:{...(D.pvpBuilds?.rogue_cb_hemo_21_3_27||{}),name:'Cold Blood Hemorrhage',status:'ACTIVE_CALIBRATED',role:'PvP control / reset / burst',calculatorUrl:'https://www.wowhead.com/classic/talent-calc/rogue/305320115001-3-500253000332121',combatTalents:[
      ['Improved Eviscerate','3/3','+15% Eviscerate damage'],['Malice','5/5','+5% melee critical strike chance'],['Relentless Strikes','1/1','20% chance per combo point to restore 25 Energy after a finisher'],['Lethality','5/5','higher critical damage for combo-point builders'],['Cold Blood','1/1','guaranteed critical strike for the next eligible attack'],['Dirty Deeds','2/2','Cheap Shot cost reduced to 40 Energy'],['Hemorrhage','1/1','primary Subtlety builder'],['Preparation','1/1','reset-oriented PvP utility']
    ].map(x=>({name:x[0],rank:x[1],effect:x[2]})),modifiers:{...(D.pvpBuilds?.rogue_cb_hemo_21_3_27?.modifiers||{}),murderDamagePct:2,hemorrhageCritMultiplier:2.3,coldBlood:true,hemorrhage:true,preparation:true}},
    mage_deep_frost_17_0_34:{...(D.pvpBuilds?.mage_deep_frost_17_0_34||{}),name:'Deep Frost PvP',status:'ACTIVE_CALIBRATED',role:'PvP control / kite / defensive reset',calculatorUrl:'https://www.wowhead.com/classic/talent-calc/mage/23001503102--05350233102351001',combatTalents:[
      ['Improved Frostbolt','5/5','Frostbolt cast time 3.0s → 2.5s'],['Elemental Precision','3/3','+6% Frost/Fire spell hit and -3% mana cost'],['Ice Shards','5/5','Frost critical strikes resolve at 2.0×'],['Improved Frost Nova','2/2','Frost Nova cooldown 25s → 21s'],['Permafrost','3/3','longer and stronger chills'],['Piercing Ice','3/3','+6% Frost damage'],['Shatter','5/5','+50% critical chance against frozen targets'],['Improved Cone of Cold','3/3','+35% Cone of Cold damage'],['Arcane Resilience','1/1','Armor increased by 50% of Intellect'],['Cold Snap','1/1','Frost cooldown reset'],['Ice Block','1/1','emergency immunity'],['Ice Barrier','1/1','defensive absorb'],['Improved Counterspell','2/2','Counterspell silence 4s']
    ].map(x=>({name:x[0],rank:x[1],effect:x[2]})),modifiers:{...(D.pvpBuilds?.mage_deep_frost_17_0_34?.modifiers||{}),coldSnap:true,iceBlock:true,iceBarrier:true}}
  };
  const byKey={};Object.entries(builds).forEach(([id,b])=>((byKey[b.class+'::'+b.spec]??=[]).push(id)));
  const pointTotal=p=>String(p||'').split('/').reduce((s,x)=>s+(Number(x)||0),0);
  const idsFor=(c,s)=>byKey[c+'::'+s]||[];
  const get=id=>builds[id]||null;
  const defaultBuild=(c,s)=>idsFor(c,s)[0]||null;
  const auditSelection=side=>{const id=side?.build||defaultBuild(side?.class,side?.spec),b=get(id);if(!b)return{pass:false,status:'LOCKED',reason:`no verified talent build for ${side?.class||'?'} ${side?.spec||'?'}`};if(b.class!==side.class||b.spec!==side.spec)return{pass:false,status:'FAIL',reason:'talent build does not match class/spec'};if(b.status!=='ACTIVE_CALIBRATED')return{pass:false,status:'LOCKED',reason:'build not calibrated'};if(b.level===60&&pointTotal(b.points)!==51)return{pass:false,status:'FAIL',reason:'level 60 build point total is not 51'};return{pass:true,status:'PASS',buildId:id,build:b,reason:`${b.name} · ${b.points} · calibrated`};};
  const kernelBindings={a:'rogue_cb_hemo_21_3_27',b:'mage_deep_frost_17_0_34'};
  const kernelAudit=cfg=>{const a=auditSelection(cfg?.a),b=auditSelection(cfg?.b),missing=[];if(!a.pass)missing.push('Player A talent build: '+a.reason);else if(a.buildId!==kernelBindings.a)missing.push('Player A build not supported by current kernel');if(!b.pass)missing.push('Player B talent build: '+b.reason);else if(b.buildId!==kernelBindings.b)missing.push('Player B build not supported by current kernel');return{pass:missing.length===0,missing,a,b};};
  D.talentBuildLibrary=builds;if(D.pvpKernel?.supported){D.pvpKernel.supported.a.build=kernelBindings.a;D.pvpKernel.supported.b.build=kernelBindings.b;}
  window.WOW_TALENTS={version:'0.16',library:builds,idsFor,get,defaultBuild,auditSelection,kernelAudit,kernelBindings,pointTotal};
})();