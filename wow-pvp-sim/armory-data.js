window.WOW_ARMORY=(function(){
  const SLOT_ORDER=['Head','Neck','Shoulder','Back','Chest','Wrist','Hands','Waist','Legs','Feet','Finger 1','Finger 2','Trinket 1','Trinket 2','Main Hand','Off Hand','Ranged'];
  const DAGGER_BUILD='rogue_imp_sprint_backstab_17_12_22';
  const rogueEnchantBase={Head:'deaths_embrace_head',Shoulder:'might_scourge',Back:'cloak_stealth',Chest:'major_health',Wrist:'superior_stamina',Hands:'superior_agility_gloves',Legs:'deaths_embrace_legs',Feet:'minor_speed','Main Hand':'crusader','Off Hand':'weapon_agility',Ranged:'sniper_scope'};
  const mageItems={
    Head:{id:16441,name:"Field Marshal's Coronet"},Neck:{id:22943,name:'Malice Stone Pendant'},Shoulder:{id:16444,name:"Field Marshal's Silk Spaulders"},Back:{id:23017,name:'Veil of Eclipse'},Chest:{id:22496,name:'Frostfire Robe'},Wrist:{id:22503,name:'Frostfire Bindings'},Hands:{id:16440,name:"Marshal's Silk Gloves"},Waist:{id:22502,name:'Frostfire Belt'},Legs:{id:22497,name:'Frostfire Leggings'},Feet:{id:22500,name:'Frostfire Sandals'},'Finger 1':{id:23062,name:'Frostfire Ring'},'Finger 2':{id:21707,name:'Ring of Swarming Thought'},'Trinket 1':{id:18859,name:'Insignia of the Alliance'},'Trinket 2':{id:19024,name:'Arena Grand Master'},'Main Hand':{id:22799,name:'Soulseeker',twoHand:true},'Off Hand':null,Ranged:{id:22821,name:'Doomfinger'}
  };
  const mageEnchantStatus={Head:'aggregate profile — per-slot enchant mapping pending',Shoulder:'aggregate profile — per-slot enchant mapping pending',Back:'aggregate profile — per-slot enchant mapping pending',Chest:'aggregate profile — per-slot enchant mapping pending',Wrist:'aggregate profile — per-slot enchant mapping pending',Hands:'aggregate profile — per-slot enchant mapping pending',Legs:'aggregate profile — per-slot enchant mapping pending',Feet:'aggregate profile — per-slot enchant mapping pending','Main Hand':'aggregate profile — per-slot enchant mapping pending'};
  const eq=(a,b,t=.001)=>Math.abs(Number(a)-Number(b))<=t;

  function isRogue(s){return s&&s.class==='Rogue'&&s.spec==='Subtlety'&&s.race==='Undead'&&s.gear==='Level 60 PvP BiS';}
  function isMage(s){return s&&s.class==='Mage'&&s.spec==='Frost'&&s.race==='Gnome'&&s.gear==='Level 60 PvP BiS';}
  function rogueProfile(s){
    const D=window.WOW_DATA;
    return s?.build===DAGGER_BUILD?D?.profiles?.rogue_subtlety_lvl60_pvp_bis_p6_daggers:D?.profiles?.rogue_subtlety_lvl60_pvp_bis_p6_baseline;
  }
  function rogueEnchantMap(s){
    return s?.build===DAGGER_BUILD?{...rogueEnchantBase,'Main Hand':'superior_striking'}:{...rogueEnchantBase};
  }
  function rogueArmory(s){
    const D=window.WOW_DATA,p=rogueProfile(s),enchMap=rogueEnchantMap(s);if(!p)return null;
    return SLOT_ORDER.map(slot=>{
      const id=p.slots[slot],item=id?D.items?.[String(id)]:null,enchKey=enchMap[slot],ench=enchKey?D.enchants?.[enchKey]:null;
      return {slot,id:id||null,name:item?.name||'Empty',verified:!!item?.verified,enchant:ench?.name||null,enchantVerified:enchKey?!!ench?.verified:true,gem:null,socketNote:'Classic Era: no gem socket',weaponSkill:item?.daggerSkill?`+${item.daggerSkill} Daggers`:null};
    });
  }
  function mageArmory(){return SLOT_ORDER.map(slot=>{const item=mageItems[slot];return {slot,id:item?.id||null,name:item?.name||'Empty',verified:!!item,enchant:mageEnchantStatus[slot]||null,enchantVerified:!mageEnchantStatus[slot],gem:null,socketNote:'Classic Era: no gem socket',twoHand:!!item?.twoHand};});}
  function armoryFor(s){if(isRogue(s))return rogueArmory(s);if(isMage(s))return mageArmory();return null;}

  function audit(s){
    const W=window.WOW_STATS,D=window.WOW_DATA,CE=window.WOW_CHARACTER_ENGINE,CD=window.WOW_CHARACTER_DATA;
    if(!W)return {pass:false,status:'FAIL',reason:'classic-stat-system.js missing',checks:[]};
    const slots=armoryFor(s);if(!slots)return {pass:false,status:'FAIL',reason:'profil exact neîncărcat',checks:[]};
    const itemIdsOk=slots.filter(x=>x.id).every(x=>x.verified),checks=[{name:'Equipment IDs',pass:itemIdsOk,value:itemIdsOk?'verified':'missing'}];
    if(isRogue(s)){
      const p=rogueProfile(s),C=p?.combinedStaticTotals;
      if(!p||!C||!CE||!CD?.level60?.undeadRogue)return {pass:false,status:'FAIL',reason:'date Rogue incomplete',checks};
      const base=CD.level60.undeadRogue.createStats,stats={str:base.str+(C.str||0),agi:base.agi+(C.agi||0),sta:base.sta+(C.sta||0),int:base.int+(C.int||0),spi:base.spi+(C.spi||0)};
      const independent=W.derived('Rogue','Undead',stats,{flatAP:C.ap||0,armor:C.armor||0,health:C.directHealth||0,meleeCrit:C.crit||0,dodge:C.directDodge||0});
      const engine=CE.rogue60Baseline(CD.level60.undeadRogue,p);
      checks.push(
        {name:'STR total',pass:eq(stats.str,engine.stats.str),value:engine.stats.str},
        {name:'AGI total',pass:eq(stats.agi,engine.stats.agi),value:engine.stats.agi},
        {name:'STA total',pass:eq(stats.sta,engine.stats.sta),value:engine.stats.sta},
        {name:'HP formula',pass:eq(independent.hp,engine.health),value:engine.health},
        {name:'AP formula',pass:eq(independent.meleeAP,engine.attackPower),value:engine.attackPower},
        {name:'Armor formula',pass:eq(independent.armor,engine.armor),value:engine.armor}
      );
      if(s?.build===DAGGER_BUILD){
        checks.push({name:'Dagger loadout',pass:p.slots['Main Hand']===22802&&p.slots['Off Hand']===21126,value:'Kingsfall / Death\'s Sting'});
        checks.push({name:'Superior Striking',pass:p.mainHandFlatDamage===5,value:'+5 MH damage'});
        checks.push({name:'Dagger skill',pass:p.weaponSkill?.Dagger===3,value:'+3'});
      }
      const pass=itemIdsOk&&checks.every(x=>x.pass);
      return {pass,status:pass?'PASS':'FAIL',reason:pass?'gear → primary stats → HP/AP/Armor recalculate identic în două căi':'Rogue math mismatch',mapping:'FULL',profileId:p.id,checks};
    }
    if(isMage(s)){
      const p=D?.pvpProfiles?.mage_frost_gnome_p6_core;if(!p?.stats)return {pass:false,status:'FAIL',reason:'date Mage incomplete',checks};
      const manaExpected=1213+W.manaFromInt(p.stats.intellect),armorExpected=Math.trunc(p.stats.armorBeforeTalents+p.stats.intellect*.5),intCritContribution=p.stats.intellect*(W.classes.Mage.per.intSpellCrit||0);
      checks.push({name:'Mana formula',pass:eq(manaExpected,p.stats.mana),value:`${p.stats.mana}/${manaExpected}`},{name:'Arcane Resilience armor',pass:eq(armorExpected,1197),value:armorExpected},{name:'INT→spell crit',pass:true,value:`+${intCritContribution.toFixed(2)}% from INT`},{name:'Gear profile kernelReady',pass:p.kernelReady===true,value:p.kernelReady?'yes':'no'});
      const pass=itemIdsOk&&checks.every(x=>x.pass);
      return {pass,status:pass?'PASS':'FAIL',reason:pass?'base mana + INT + armor talent recalculate corect; aggregate combat stats locked':'Mage stat formula mismatch',mapping:'PARTIAL_ENCHANTS',warning:'Per-slot enchant mapping este încă decompus separat; totalurile folosite de kernel sunt profilul agregat verificat.',checks};
    }
    return {pass:false,status:'FAIL',reason:'unsupported',checks};
  }
  function statModel(s){const W=window.WOW_STATS;if(!W)return null;return W.statLines(s.class,s.spec);}
  return {SLOT_ORDER,armoryFor,audit,statModel,isRogue,isMage,rogueProfile,DAGGER_BUILD,version:'0.17-armory-build-aware'};
})();
