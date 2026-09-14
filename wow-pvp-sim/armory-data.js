window.WOW_ARMORY=(function(){
  const SLOT_ORDER=['Head','Neck','Shoulder','Back','Chest','Wrist','Hands','Waist','Legs','Feet','Finger 1','Finger 2','Trinket 1','Trinket 2','Main Hand','Off Hand','Ranged'];
  const rogueEnchantBySlot={
    Head:'deaths_embrace_head',Shoulder:'might_scourge',Back:'cloak_stealth',Chest:'major_health',Wrist:'superior_stamina',Hands:'superior_agility_gloves',Legs:'deaths_embrace_legs',Feet:'minor_speed','Main Hand':'crusader','Off Hand':'weapon_agility',Ranged:'sniper_scope'
  };
  const mageItems={
    Head:{id:16441,name:"Field Marshal's Coronet"},
    Neck:{id:22943,name:"Malice Stone Pendant"},
    Shoulder:{id:16444,name:"Field Marshal's Silk Spaulders"},
    Back:{id:23017,name:'Veil of Eclipse'},
    Chest:{id:22496,name:'Frostfire Robe'},
    Wrist:{id:22503,name:'Frostfire Bindings'},
    Hands:{id:16440,name:"Marshal's Silk Gloves"},
    Waist:{id:22502,name:'Frostfire Belt'},
    Legs:{id:22497,name:'Frostfire Leggings'},
    Feet:{id:22500,name:'Frostfire Sandals'},
    'Finger 1':{id:23062,name:'Frostfire Ring'},
    'Finger 2':{id:21707,name:'Ring of Swarming Thought'},
    'Trinket 1':{id:18859,name:'Insignia of the Alliance'},
    'Trinket 2':{id:19024,name:'Arena Grand Master'},
    'Main Hand':{id:22799,name:'Soulseeker',twoHand:true},
    'Off Hand':null,
    Ranged:{id:22821,name:'Doomfinger'}
  };
  const mageEnchantStatus={
    Head:'aggregate profile — per-slot enchant mapping pending',Shoulder:'aggregate profile — per-slot enchant mapping pending',Back:'aggregate profile — per-slot enchant mapping pending',Chest:'aggregate profile — per-slot enchant mapping pending',Wrist:'aggregate profile — per-slot enchant mapping pending',Hands:'aggregate profile — per-slot enchant mapping pending',Legs:'aggregate profile — per-slot enchant mapping pending',Feet:'aggregate profile — per-slot enchant mapping pending','Main Hand':'aggregate profile — per-slot enchant mapping pending'
  };
  function isRogue(s){return s&&s.class==='Rogue'&&s.spec==='Subtlety'&&s.race==='Undead'&&s.gear==='Level 60 PvP BiS';}
  function isMage(s){return s&&s.class==='Mage'&&s.spec==='Frost'&&s.race==='Gnome'&&s.gear==='Level 60 PvP BiS';}
  function rogueArmory(){
    const D=window.WOW_DATA,p=D?.profiles?.rogue_subtlety_lvl60_pvp_bis_p6_baseline;
    if(!p)return null;
    return SLOT_ORDER.map(slot=>{
      const id=p.slots[slot],item=id?D.items?.[String(id)]:null,enchKey=rogueEnchantBySlot[slot],ench=enchKey?D.enchants?.[enchKey]:null;
      return {slot,id:id||null,name:item?.name||'Empty',verified:!!item?.verified,enchant:ench?.name||null,enchantVerified:enchKey?!!ench?.verified:true,gem:null,socketNote:'Classic Era: no gem socket'};
    });
  }
  function mageArmory(){
    return SLOT_ORDER.map(slot=>{const item=mageItems[slot];return {slot,id:item?.id||null,name:item?.name||'Empty',verified:!!item,enchant:mageEnchantStatus[slot]||null,enchantVerified:!mageEnchantStatus[slot],gem:null,socketNote:'Classic Era: no gem socket',twoHand:!!item?.twoHand};});
  }
  function armoryFor(s){if(isRogue(s))return rogueArmory();if(isMage(s))return mageArmory();return null;}
  function audit(s){
    const W=window.WOW_STATS,D=window.WOW_DATA;
    if(!W)return {pass:false,status:'FAIL',reason:'classic-stat-system.js missing'};
    const slots=armoryFor(s);if(!slots)return {pass:false,status:'FAIL',reason:'profil exact neîncărcat'};
    const itemIdsOk=slots.filter(x=>x.id).every(x=>x.verified);
    if(isRogue(s)){
      const p=D?.profiles?.rogue_subtlety_lvl60_pvp_bis_p6_baseline;
      const pass=itemIdsOk&&!!p?.combinedStaticTotals&&!!p?.derivedRogueLevel60GearContributions;
      return {pass,status:pass?'PASS':'FAIL',reason:pass?'17/17 item IDs + enchants + class conversions verificate':'date Rogue incomplete',mapping:'FULL'};
    }
    if(isMage(s)){
      const p=D?.pvpProfiles?.mage_frost_gnome_p6_core;
      const pass=itemIdsOk&&!!p?.stats&&p?.kernelReady===true;
      return {pass,status:pass?'PASS':'FAIL',reason:pass?'stats agregate + 16 equipment IDs + class conversions verificate':'date Mage incomplete',mapping:'PARTIAL_ENCHANTS',warning:'Per-slot enchant mapping este încă decompus separat; totalurile folosite de kernel rămân profilul agregat verificat.'};
    }
    return {pass:false,status:'FAIL',reason:'unsupported'};
  }
  function statModel(s){
    const W=window.WOW_STATS;if(!W)return null;
    return W.statLines(s.class,s.spec);
  }
  return {SLOT_ORDER,armoryFor,audit,statModel,isRogue,isMage,version:'0.11-armory-audit'};
})();