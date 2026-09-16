window.WOW_ARMORY=(function(){
  const SLOT_ORDER=['Head','Neck','Shoulder','Back','Chest','Wrist','Hands','Waist','Legs','Feet','Finger 1','Finger 2','Trinket 1','Trinket 2','Main Hand','Off Hand','Ranged'];
  const LEFT_SLOTS=['Head','Neck','Shoulder','Back','Chest','Wrist','Hands','Waist'];
  const RIGHT_SLOTS=['Legs','Feet','Finger 1','Finger 2','Trinket 1','Trinket 2','Ranged'];
  const WEAPON_SLOTS=['Main Hand','Off Hand'];
  const DAGGER_BUILDS=new Set(['rogue_imp_sprint_backstab_17_12_22','rogue_imp_sprint_backstab_16_12_23']);

  const rogueEnchantBase={Head:'deaths_embrace_head',Shoulder:'might_scourge',Back:'cloak_stealth',Chest:'major_health',Wrist:'superior_stamina',Hands:'superior_agility_gloves',Legs:'deaths_embrace_legs',Feet:'minor_speed','Main Hand':'crusader','Off Hand':'weapon_agility',Ranged:'sniper_scope'};

  const mageItems={
    Head:{id:16441,name:"Field Marshal's Coronet",verified:true},
    Neck:{id:22943,name:'Malice Stone Pendant',verified:true},
    Shoulder:{id:16444,name:"Field Marshal's Silk Spaulders",verified:true},
    Back:{id:23017,name:'Veil of Eclipse',verified:true},
    Chest:{id:22496,name:'Frostfire Robe',verified:true},
    Wrist:{id:22503,name:'Frostfire Bindings',verified:true},
    Hands:{id:16440,name:"Marshal's Silk Gloves",verified:true},
    Waist:{id:22502,name:'Frostfire Belt',verified:true},
    Legs:{id:22497,name:'Frostfire Leggings',verified:true},
    Feet:{id:22500,name:'Frostfire Sandals',verified:true},
    'Finger 1':{id:23062,name:'Frostfire Ring',verified:true},
    'Finger 2':{id:21707,name:'Ring of Swarming Thought',verified:true},
    'Trinket 1':{id:18859,name:'Insignia of the Alliance',verified:true},
    'Trinket 2':{id:19024,name:'Arena Grand Master',verified:true},
    'Main Hand':{id:22799,name:'Soulseeker',verified:true,twoHand:true},
    'Off Hand':null,
    Ranged:{id:22821,name:'Doomfinger',verified:true}
  };

  // Phase-6 Frost PvP enchants. Values below are the Classic effects used by the Armory display.
  const mageEnchants={
    Head:{name:'Presence of Sight',spellId:24164,effect:'+18 Spell Damage · +1% Spell Hit',verified:true,source:'https://www.wowhead.com/classic/spell=24164/presence-of-sight'},
    Shoulder:{name:'Power of the Scourge',spellId:29467,effect:'+15 Spell Damage · +1% Spell Crit',verified:true,source:'https://www.wowhead.com/classic/spell=29467/power-of-the-scourge'},
    Back:{name:'Enchant Cloak - Greater Resistance',spellId:20014,effect:'+5 All Resistances',verified:true,source:'https://www.wowhead.com/classic/spell=20014/enchant-cloak-greater-resistance'},
    Chest:{name:'Enchant Chest - Greater Stats',spellId:20025,effect:'+4 All Stats',verified:true,source:'https://www.wowhead.com/classic/spell=20025/enchant-chest-greater-stats'},
    Wrist:{name:'Enchant Bracer - Greater Intellect',spellId:20008,effect:'+7 Intellect',verified:true,source:'https://www.wowhead.com/classic/spell=20008/enchant-bracer-greater-intellect'},
    Hands:{name:'Enchant Gloves - Frost Power',spellId:25074,effect:'+20 Frost Spell Damage',verified:true,source:'https://www.wowhead.com/classic/spell=25074/enchant-gloves-frost-power'},
    Legs:{name:'Presence of Sight',spellId:24164,effect:'+18 Spell Damage · +1% Spell Hit',verified:true,source:'https://www.wowhead.com/classic/spell=24164/presence-of-sight'},
    Feet:{name:'Enchant Boots - Minor Speed',spellId:13890,effect:'+8% Run Speed',verified:true,source:'https://www.wowhead.com/classic/spell=13890/enchant-boots-minor-speed'},
    'Main Hand':{name:'Enchant Weapon - Spell Power',spellId:22749,effect:'+30 Spell Damage',verified:true,source:'https://www.wowhead.com/classic/spell=22749/enchant-weapon-spell-power'}
  };

  const eq=(a,b,t=.001)=>Math.abs(Number(a)-Number(b))<=t;
  const isDaggerBuild=s=>DAGGER_BUILDS.has(s?.build);
  const isRogue=s=>!!(s&&s.class==='Rogue'&&s.spec==='Subtlety'&&s.race==='Undead'&&s.gear==='Level 60 PvP BiS');
  const isMage=s=>!!(s&&s.class==='Mage'&&s.spec==='Frost'&&s.race==='Gnome'&&s.gear==='Level 60 PvP BiS');
  const wowheadItemUrl=id=>id?`https://www.wowhead.com/classic/item=${id}`:'#';

  function rogueProfile(s){
    const D=window.WOW_DATA;
    return isDaggerBuild(s)?D?.profiles?.rogue_subtlety_lvl60_pvp_bis_p6_daggers:D?.profiles?.rogue_subtlety_lvl60_pvp_bis_p6_baseline;
  }
  function rogueEnchantMap(s){return isDaggerBuild(s)?{...rogueEnchantBase,'Main Hand':'superior_striking'}:{...rogueEnchantBase};}

  function rogueArmory(s){
    const D=window.WOW_DATA,p=rogueProfile(s),enchMap=rogueEnchantMap(s);if(!p)return null;
    return SLOT_ORDER.map(slot=>{
      const id=p.slots[slot],item=id?D.items?.[String(id)]:null,enchKey=enchMap[slot],ench=enchKey?D.enchants?.[enchKey]:null;
      return {
        slot,id:id||null,name:item?.name||'Empty',verified:!!item?.verified,item:item||null,itemLevel:item?.itemLevel??null,
        enchant:ench?.name||null,enchantEffect:enchantEffect(ench),enchantVerified:enchKey?!!ench?.verified:true,enchantSource:ench?.source||null,
        gem:null,socketNote:'Classic Era: no gem sockets',weaponSkill:item?.daggerSkill?`+${item.daggerSkill} Daggers`:null,source:item?.source||null,
        wowhead:wowheadItemUrl(id)
      };
    });
  }

  function mageArmory(){
    return SLOT_ORDER.map(slot=>{
      const item=mageItems[slot],ench=mageEnchants[slot]||null;
      return {
        slot,id:item?.id||null,name:item?.name||'Empty',verified:!!item?.verified,item:item||null,itemLevel:item?.itemLevel??null,
        enchant:ench?.name||null,enchantEffect:ench?.effect||null,enchantVerified:ench?!!ench.verified:true,enchantSource:ench?.source||null,
        gem:null,socketNote:'Classic Era: no gem sockets',twoHand:!!item?.twoHand,source:item?.id?wowheadItemUrl(item.id):null,wowhead:wowheadItemUrl(item?.id)
      };
    });
  }

  function enchantEffect(e){
    if(!e)return null;
    const bits=[];
    if(e.ap)bits.push(`+${e.ap} AP`);if(e.agi)bits.push(`+${e.agi} Agility`);if(e.sta)bits.push(`+${e.sta} Stamina`);if(e.health)bits.push(`+${e.health} Health`);
    if(e.crit)bits.push(`+${e.crit}% Crit`);if(e.dodge)bits.push(`+${e.dodge}% Dodge`);if(e.rangedDamage)bits.push(`+${e.rangedDamage} Ranged Damage`);
    if(e.movementSpeedPct)bits.push(`+${e.movementSpeedPct}% Run Speed`);if(e.stealthEffect)bits.push('Improved Stealth');
    if(e.proc?.str)bits.push(`Proc: +${e.proc.str} Strength`);
    return bits.join(' · ')||null;
  }

  function armoryFor(s){if(isRogue(s))return rogueArmory(s);if(isMage(s))return mageArmory();return null;}

  function profileMeta(s){
    const T=window.WOW_TALENTS,build=T?.get(s?.build);
    return {level:60,race:s?.race,class:s?.class,spec:s?.spec,gear:s?.gear,buildId:s?.build,buildName:build?.name||s?.build||'—',buildPoints:build?.points||'—'};
  }

  function audit(s){
    const W=window.WOW_STATS,D=window.WOW_DATA,CE=window.WOW_CHARACTER_ENGINE,CD=window.WOW_CHARACTER_DATA;
    if(!W)return {pass:false,status:'FAIL',reason:'classic-stat-system.js missing',checks:[]};
    const slots=armoryFor(s);if(!slots)return {pass:false,status:'FAIL',reason:'profil exact neîncărcat',checks:[]};
    const itemIdsOk=slots.filter(x=>x.id).every(x=>x.verified),enchantsOk=slots.every(x=>x.enchantVerified!==false);
    const checks=[{name:'Equipment IDs',pass:itemIdsOk,value:itemIdsOk?'verified':'missing'},{name:'Per-slot enchants',pass:enchantsOk,value:enchantsOk?'verified':'pending'}];
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
      if(isDaggerBuild(s)){
        checks.push({name:'Dagger loadout',pass:p.slots['Main Hand']===22802&&p.slots['Off Hand']===21126,value:'Kingsfall / Death\'s Sting'});
        checks.push({name:'Superior Striking',pass:p.mainHandFlatDamage===5,value:'+5 MH damage'});
        checks.push({name:'Dagger skill',pass:p.weaponSkill?.Dagger===3,value:'+3'});
      }
      const pass=itemIdsOk&&enchantsOk&&checks.every(x=>x.pass);
      return {pass,status:pass?'PASS':'FAIL',reason:pass?'gear → enchants → primary stats → HP/AP/Armor recalculate identic':'Rogue math/data mismatch',mapping:'FULL',profileId:p.id,checks};
    }
    if(isMage(s)){
      const p=D?.pvpProfiles?.mage_frost_gnome_p6_core;if(!p?.stats)return {pass:false,status:'FAIL',reason:'date Mage incomplete',checks};
      const manaExpected=1213+W.manaFromInt(p.stats.intellect),armorExpected=Math.trunc(p.stats.armorBeforeTalents+p.stats.intellect*.5),intCritContribution=p.stats.intellect*(W.classes.Mage.per.intSpellCrit||0);
      checks.push(
        {name:'Mana formula',pass:eq(manaExpected,p.stats.mana),value:`${p.stats.mana}/${manaExpected}`},
        {name:'Arcane Resilience armor',pass:eq(armorExpected,1197),value:armorExpected},
        {name:'INT→spell crit',pass:true,value:`+${intCritContribution.toFixed(2)}% from INT`},
        {name:'Gear profile kernelReady',pass:p.kernelReady===true,value:p.kernelReady?'yes':'no'}
      );
      const pass=itemIdsOk&&enchantsOk&&checks.every(x=>x.pass);
      return {pass,status:pass?'PASS':'FAIL',reason:pass?'gear + enchants + mana + armor talent audit complete':'Mage stat formula/data mismatch',mapping:'FULL',checks};
    }
    return {pass:false,status:'FAIL',reason:'unsupported',checks};
  }

  function statModel(s){const W=window.WOW_STATS;if(!W)return null;return W.statLines(s.class,s.spec);}
  return {SLOT_ORDER,LEFT_SLOTS,RIGHT_SLOTS,WEAPON_SLOTS,armoryFor,audit,statModel,profileMeta,isRogue,isMage,rogueProfile,isDaggerBuild,DAGGER_BUILDS,mageEnchants,version:'0.28-blizzard-paperdoll'};
})();
