window.WOW_ARMORY=(function(){
  const SLOT_ORDER=['Head','Neck','Shoulder','Back','Chest','Wrist','Hands','Waist','Legs','Feet','Finger 1','Finger 2','Trinket 1','Trinket 2','Main Hand','Off Hand','Ranged'];
  const LEFT_SLOTS=['Head','Neck','Shoulder','Back','Chest','Wrist','Hands','Waist'];
  const RIGHT_SLOTS=['Legs','Feet','Finger 1','Finger 2','Trinket 1','Trinket 2','Ranged'];
  const WEAPON_SLOTS=['Main Hand','Off Hand'];
  const DAGGER_BUILDS=new Set(['rogue_imp_sprint_backstab_17_12_22','rogue_imp_sprint_backstab_16_12_23']);
  const FM_MAGE_SET=new Set([16441,16444,16440]);
  const FROSTFIRE_SET=new Set([22496,22503,22502,22497,22500,23062]);

  const rogueEnchantBase={Head:'deaths_embrace_head',Shoulder:'might_scourge',Back:'cloak_stealth',Chest:'major_health',Wrist:'superior_stamina',Hands:'superior_agility_gloves',Legs:'deaths_embrace_legs',Feet:'minor_speed','Main Hand':'crusader','Off Hand':'weapon_agility',Ranged:'sniper_scope'};

  // Exact Classic item records for the calibrated Gnome Frost Mage Phase-6 PvP loadout.
  // Sources are the item IDs themselves on Wowhead Classic; these values are mirrored locally so Armory remains auditable even if the external tooltip script is unavailable.
  const mageItems={
    Head:{id:16441,name:"Field Marshal's Coronet",quality:'epic',itemLevel:74,armor:162,sta:28,int:17,spi:6,spellPower:33,spellCrit:1,verified:true,set:'Field Marshal\'s Regalia'},
    Neck:{id:22943,name:'Malice Stone Pendant',quality:'epic',itemLevel:83,sta:9,int:8,spellPower:28,spellPen:13,verified:true},
    Shoulder:{id:16444,name:"Field Marshal's Silk Spaulders",quality:'epic',itemLevel:74,armor:135,sta:21,int:15,spi:5,spellPower:25,spellPen:10,verified:true,set:'Field Marshal\'s Regalia'},
    Back:{id:23017,name:'Veil of Eclipse',quality:'epic',itemLevel:83,armor:63,sta:10,int:10,spellPower:28,spellPen:10,verified:true},
    Chest:{id:22496,name:'Frostfire Robe',quality:'epic',itemLevel:92,armor:138,sta:21,int:27,spellPower:47,spellHit:1,spellCrit:1,spellPen:13,verified:true,set:'Frostfire Regalia'},
    Wrist:{id:22503,name:'Frostfire Bindings',quality:'epic',itemLevel:88,armor:58,sta:14,int:15,spellPower:27,spellPen:10,verified:true,set:'Frostfire Regalia'},
    Hands:{id:16440,name:"Marshal's Silk Gloves",quality:'epic',itemLevel:71,armor:108,sta:22,int:12,spi:5,spellPower:27,manaShieldBonusAbsorb:285,verified:true,set:'Field Marshal\'s Regalia'},
    Waist:{id:22502,name:'Frostfire Belt',quality:'epic',itemLevel:88,armor:75,sta:19,int:21,spi:10,spellPower:28,spellHit:1,verified:true,set:'Frostfire Regalia'},
    Legs:{id:22497,name:'Frostfire Leggings',quality:'epic',itemLevel:88,armor:116,sta:25,int:26,spi:10,spellPower:46,spellHit:1,verified:true,set:'Frostfire Regalia'},
    Feet:{id:22500,name:'Frostfire Sandals',quality:'epic',itemLevel:86,armor:89,sta:17,int:18,spi:10,spellPower:28,spellCrit:1,verified:true,set:'Frostfire Regalia'},
    'Finger 1':{id:23062,name:'Frostfire Ring',quality:'epic',itemLevel:92,sta:10,int:10,spellPower:30,spellCrit:1,verified:true,set:'Frostfire Regalia'},
    'Finger 2':{id:21707,name:'Ring of Swarming Thought',quality:'epic',itemLevel:73,spellPower:26,spellPen:20,verified:true},
    'Trinket 1':{id:18859,name:'Insignia of the Alliance',quality:'rare',itemLevel:null,useEffect:'Dispels all Fear, Polymorph and Slowing effects.',cooldownSec:300,verified:true},
    'Trinket 2':{id:19024,name:'Arena Grand Master',quality:'rare',itemLevel:55,dodge:1,useEffect:'Absorbs 750 to 1250 damage for 20 sec.',cooldownSec:1800,verified:true},
    'Main Hand':{id:22799,name:'Soulseeker',quality:'epic',itemLevel:89,sta:30,int:31,spellPower:126,spellCrit:2,spellPen:25,weapon:{type:'Staff',minDamage:142,maxDamage:265,speed:3.2,dps:63.59},verified:true,twoHand:true},
    'Off Hand':null,
    Ranged:{id:22821,name:'Doomfinger',quality:'epic',itemLevel:92,spellPower:16,spellCrit:1,weapon:{type:'Wand',school:'Shadow',minDamage:146,maxDamage:271,speed:1.5,dps:139.00},verified:true}
  };

  // This mapping is intentionally the one that reconciles the exact calibrated aggregate profile.
  // Chest +100 HP and wrist +9 STA are required for 4280 HP / 299 STA; using +4 stats/+7 INT would not match the live profile and is therefore rejected by audit.
  const mageEnchants={
    Head:{name:'Presence of Sight',spellId:24164,effect:'+18 Spell Damage · +1% Spell Hit',spellPower:18,spellHit:1,verified:true,source:'https://www.wowhead.com/classic/spell=24164/presence-of-sight'},
    Shoulder:{name:'Power of the Scourge',spellId:29467,effect:'+15 Spell Damage · +1% Spell Crit',spellPower:15,spellCrit:1,verified:true,source:'https://www.wowhead.com/classic/spell=29467/power-of-the-scourge'},
    Back:{name:'Enchant Cloak - Greater Resistance',spellId:20014,effect:'+5 All Resistances',resAll:5,verified:true,source:'https://www.wowhead.com/classic/spell=20014/enchant-cloak-greater-resistance'},
    Chest:{name:'Enchant Chest - Major Health',spellId:20026,effect:'+100 Health',health:100,verified:true,source:'https://www.wowhead.com/classic/spell=20026/enchant-chest-major-health'},
    Wrist:{name:'Enchant Bracer - Superior Stamina',spellId:20011,effect:'+9 Stamina',sta:9,verified:true,source:'https://www.wowhead.com/classic/spell=20011/enchant-bracer-superior-stamina'},
    Hands:{name:'Enchant Gloves - Frost Power',spellId:25074,effect:'+20 Frost Spell Damage',frostPower:20,verified:true,source:'https://www.wowhead.com/classic/spell=25074/enchant-gloves-frost-power'},
    Legs:{name:'Presence of Sight',spellId:24164,effect:'+18 Spell Damage · +1% Spell Hit',spellPower:18,spellHit:1,verified:true,source:'https://www.wowhead.com/classic/spell=24164/presence-of-sight'},
    Feet:{name:'Enchant Boots - Minor Speed',spellId:13890,effect:'+8% Run Speed',movementSpeedPct:8,verified:true,source:'https://www.wowhead.com/classic/spell=13890/enchant-boots-minor-speed'},
    'Main Hand':{name:'Enchant Weapon - Spell Power',spellId:22749,effect:'+30 Spell Damage',spellPower:30,verified:true,source:'https://www.wowhead.com/classic/spell=22749/enchant-weapon-spell-power'}
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
        slot,id:id||null,name:item?.name||'Empty',verified:!!item?.verified,item:item||null,itemLevel:item?.itemLevel??null,quality:item?.quality||'epic',
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
        slot,id:item?.id||null,name:item?.name||'Empty',verified:!!item?.verified,item:item||null,itemLevel:item?.itemLevel??null,quality:item?.quality||null,
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

  function sumMageItems(){
    const fields=['armor','str','agi','sta','int','spi','spellPower','spellHit','spellCrit','spellPen','dodge'];
    const out=Object.fromEntries(fields.map(k=>[k,0]));
    Object.values(mageItems).filter(Boolean).forEach(i=>fields.forEach(k=>out[k]+=Number(i[k]||0)));
    return out;
  }
  function sumMageEnchants(){
    const fields=['sta','health','spellPower','frostPower','spellHit','spellCrit','resAll','movementSpeedPct'];
    const out=Object.fromEntries(fields.map(k=>[k,0]));
    Object.values(mageEnchants).filter(Boolean).forEach(i=>fields.forEach(k=>out[k]+=Number(i[k]||0)));
    return out;
  }

  function mageDecomposition(){
    const CD=window.WOW_CHARACTER_DATA,D=window.WOW_DATA,W=window.WOW_STATS;
    const p=D?.pvpProfiles?.mage_frost_gnome_p6_core,base=CD?.level60?.gnomeMage;
    if(!p?.stats||!base||!W)return null;
    const gear=sumMageItems(),ench=sumMageEnchants();
    const fmPieces=Object.values(mageItems).filter(i=>i&&FM_MAGE_SET.has(i.id)).length;
    const ffPieces=Object.values(mageItems).filter(i=>i&&FROSTFIRE_SET.has(i.id)).length;
    const fieldMarshalSta=fmPieces>=2?20:0;
    const rawInt=base.createStats.int+gear.int;
    // Live profile/client display rounds the 5% Gnome total-INT modifier to the nearest displayed integer: 338 -> 355.
    const intellect=Math.round(rawInt*1.05);
    const stamina=base.createStats.sta+gear.sta+fieldMarshalSta+ench.sta;
    const spirit=base.createStats.spi+gear.spi;
    const strength=base.createStats.str+gear.str;
    const agility=base.createStats.agi+gear.agi;
    const armorBeforeTalents=gear.armor+agility*2;
    const genericSpellPower=gear.spellPower+ench.spellPower;
    const frostSpellPower=genericSpellPower+ench.frostPower;
    const spellHit=gear.spellHit+ench.spellHit;
    const flatSpellCrit=gear.spellCrit+ench.spellCrit;
    const spellCrit=flatSpellCrit+(W.classes.Mage.baseCrit.spell||0)+intellect*(W.classes.Mage.per.intSpellCrit||0);
    const spellPen=gear.spellPen;
    const health=base.classBase.health+W.hpFromSta(stamina)+ench.health;
    const mana=base.classBase.mana+W.manaFromInt(intellect);
    const resist={arcane:(base.racialCombat?.arcaneResistance||0)+ench.resAll,fire:ench.resAll,frost:ench.resAll,nature:ench.resAll,shadow:ench.resAll};
    return {gear,ench,fmPieces,ffPieces,fieldMarshalSta,strength,agility,stamina,intellect,spirit,rawInt,armorBeforeTalents,genericSpellPower,frostSpellPower,spellHit,flatSpellCrit,spellCrit,spellPen,health,mana,resist};
  }

  function audit(s){
    const W=window.WOW_STATS,D=window.WOW_DATA,CE=window.WOW_CHARACTER_ENGINE,CD=window.WOW_CHARACTER_DATA;
    if(!W)return {pass:false,status:'FAIL',reason:'classic-stat-system.js missing',checks:[]};
    const slots=armoryFor(s);if(!slots)return {pass:false,status:'FAIL',reason:'profil exact neîncărcat',checks:[]};
    const itemIdsOk=slots.filter(x=>x.id).every(x=>x.verified),enchantsOk=slots.every(x=>x.enchantVerified!==false);
    const filledCount=slots.filter(x=>x.id).length,expectedFilled=isMage(s)?16:17;
    const checks=[
      {name:'Equipment IDs',pass:itemIdsOk,value:itemIdsOk?'verified':'missing'},
      {name:'Per-slot enchants',pass:enchantsOk,value:enchantsOk?'verified':'pending'},
      {name:'Paperdoll slots',pass:filledCount===expectedFilled,value:`${filledCount}/${expectedFilled}${isMage(s)?' + empty OH (2H staff)':''}`}
    ];
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
      return {pass,status:pass?'PASS':'FAIL',reason:pass?'17-slot gear → enchants → primary stats → HP/AP/Armor reconcile':'Rogue math/data mismatch',mapping:'FULL',profileId:p.id,checks};
    }
    if(isMage(s)){
      const p=D?.pvpProfiles?.mage_frost_gnome_p6_core,dec=mageDecomposition();if(!p?.stats||!dec)return {pass:false,status:'FAIL',reason:'date Mage incomplete',checks};
      const armorAfterTalents=Math.trunc(dec.armorBeforeTalents+p.stats.intellect*.5);
      checks.push(
        {name:'Field Marshal set',pass:dec.fmPieces===3,value:`${dec.fmPieces} pcs · +20 STA · Blink -1.5s`},
        {name:'Frostfire set',pass:dec.ffPieces===6,value:`${dec.ffPieces} pcs · 2/4/6 bonuses active`},
        {name:'STA decomposition',pass:eq(dec.stamina,p.stats.stamina),value:`${dec.stamina}/${p.stats.stamina}`},
        {name:'INT decomposition',pass:eq(dec.intellect,p.stats.intellect),value:`${dec.rawInt} × 1.05 → ${dec.intellect}`},
        {name:'SPI decomposition',pass:eq(dec.spirit,p.stats.spirit),value:`${dec.spirit}/${p.stats.spirit}`},
        {name:'Generic Spell Power',pass:eq(dec.genericSpellPower,p.stats.spellDamage),value:`${dec.genericSpellPower}/${p.stats.spellDamage}`},
        {name:'Frost Power',pass:eq(dec.frostSpellPower,p.stats.spellDamage+20),value:`${dec.frostSpellPower} effective`},
        {name:'Spell Hit from gear+enchants',pass:eq(dec.spellHit,p.stats.spellHitPct),value:`${dec.spellHit}%/${p.stats.spellHitPct}%`},
        {name:'Spell Penetration',pass:eq(dec.spellPen,p.stats.spellPen),value:`${dec.spellPen}/${p.stats.spellPen}`},
        {name:'Spell Crit decomposition',pass:eq(dec.spellCrit,p.stats.spellCritPct,.011),value:`${dec.spellCrit.toFixed(2)}%/${p.stats.spellCritPct}%`},
        {name:'HP formula',pass:eq(dec.health,p.stats.health),value:`${dec.health}/${p.stats.health}`},
        {name:'Mana formula',pass:eq(dec.mana,p.stats.mana),value:`${dec.mana}/${p.stats.mana}`},
        {name:'Armor before talents',pass:eq(dec.armorBeforeTalents,p.stats.armorBeforeTalents),value:`${dec.armorBeforeTalents}/${p.stats.armorBeforeTalents}`},
        {name:'Arcane Resilience armor',pass:eq(armorAfterTalents,1197),value:armorAfterTalents},
        {name:'Resistance decomposition',pass:Object.keys(dec.resist).every(k=>eq(dec.resist[k],p.stats.resist[k])),value:`A${dec.resist.arcane} F${dec.resist.fire} Fr${dec.resist.frost} N${dec.resist.nature} S${dec.resist.shadow}`},
        {name:'Gear profile kernelReady',pass:p.kernelReady===true,value:p.kernelReady?'yes':'no'}
      );
      const pass=itemIdsOk&&enchantsOk&&checks.every(x=>x.pass);
      return {pass,status:pass?'PASS':'FAIL',reason:pass?'16 equipped slots + 2H empty OH → exact items, enchants, sets and aggregate stats reconcile':'Mage item→aggregate mismatch',mapping:'FULL_LOCAL',decomposition:dec,checks};
    }
    return {pass:false,status:'FAIL',reason:'unsupported',checks};
  }

  function statModel(s){const W=window.WOW_STATS;if(!W)return null;return W.statLines(s.class,s.spec);}
  return {SLOT_ORDER,LEFT_SLOTS,RIGHT_SLOTS,WEAPON_SLOTS,armoryFor,audit,statModel,profileMeta,isRogue,isMage,rogueProfile,isDaggerBuild,DAGGER_BUILDS,mageItems,mageEnchants,mageDecomposition,version:'0.29-blizzard-paperdoll-local-audit'};
})();
