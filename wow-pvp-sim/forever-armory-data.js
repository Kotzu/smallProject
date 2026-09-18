(function(){
  const SLOT_ORDER=['Head','Neck','Shoulder','Back','Chest','Wrist','Hands','Waist','Legs','Feet','Finger 1','Finger 2','Trinket 1','Trinket 2','Main Hand','Off Hand','Ranged'];
  const source=id=>id?('https://www.wowhead.com/forever/item='+id):null;
  const spell=id=>id?('https://www.wowhead.com/forever/spell='+id):null;
  const item=(id,name,slot,stats={})=>({id,name,slot,quality:stats.quality||'epic',verified:true,source:source(id),...stats});
  const enchant=(id,name,effect,stats={})=>({spellId:id,name,effect,verified:true,source:stats.source||spell(id),...stats});

  const rogueItems={
    Head:item(22478,'Bonescythe Helmet','Head',{itemLevel:88,armor:205,str:18,agi:30,sta:29,hit:1,crit:2,set:'Bonescythe Armor'}),
    Neck:item(23053,"Stormrage's Talisman of Seething",'Neck',{itemLevel:92,sta:12,ap:26,crit:2}),
    Shoulder:item(22479,'Bonescythe Pauldrons','Shoulder',{itemLevel:86,armor:186,str:22,agi:22,sta:15,hit:1,crit:1,set:'Bonescythe Armor'}),
    Back:item(23045,'Shroud of Dominion','Back',{itemLevel:90,armor:68,sta:11,ap:50,crit:1}),
    Chest:item(22476,'Bonescythe Breastplate','Chest',{itemLevel:92,armor:262,sta:29,ap:80,hit:1,crit:2,set:'Bonescythe Armor'}),
    Wrist:item(22483,'Bonescythe Bracers','Wrist',{itemLevel:88,armor:111,agi:26,sta:14,crit:1,set:'Bonescythe Armor'}),
    Hands:item(16907,'Bloodfang Gloves','Hands',{itemLevel:76,armor:140,str:19,agi:20,sta:20,shadowRes:10,set:'Bloodfang Armor',special:'Immune to Disarm'}),
    Waist:item(21586,'Belt of Never-ending Agony','Waist',{itemLevel:88,armor:142,sta:20,ap:64,hit:1,crit:1}),
    Legs:item(23071,'Leggings of Apocalypse','Legs',{itemLevel:83,armor:211,str:15,agi:31,sta:23,crit:2}),
    Feet:item(22480,'Bonescythe Sabatons','Feet',{itemLevel:86,armor:171,sta:18,ap:64,hit:1,crit:1,set:'Bonescythe Armor'}),
    'Finger 1':item(23038,'Band of Unnatural Forces','Finger 1',{itemLevel:85,ap:52,hit:1,crit:1}),
    'Finger 2':item(19376,"Archimtiros' Ring of Reckoning",'Finger 2',{itemLevel:83,agi:14,sta:28}),
    'Trinket 1':item(11815,'Hand of Justice','Trinket 1',{itemLevel:58,quality:'rare',ap:20,special:'2% chance on melee hit to gain 1 extra attack (2 sec cooldown)'}),
    'Trinket 2':item(13965,"Blackhand's Breadth",'Trinket 2',{itemLevel:63,quality:'rare',crit:2}),
    'Main Hand':item(23054,'Gressil, Dawn of Ruin','Main Hand',{itemLevel:89,sta:15,ap:40,weapon:{type:'One-Hand Sword',minDamage:37,maxDamage:114,speed:2.70,dps:27.96}}),
    'Off Hand':item(23044,'Harbinger of Doom','Off Hand',{itemLevel:83,agi:8,sta:8,hit:1,crit:1,weapon:{type:'One-Hand Dagger',minDamage:22,maxDamage:67,speed:1.60,dps:27.81}}),
    Ranged:item(22812,'Nerubian Slavemaker','Ranged',{itemLevel:89,ap:24,crit:1,weapon:{type:'Crossbow',minDamage:57,maxDamage:173,speed:3.20,dps:35.94}})
  };
  const rogueEnchants={
    Head:enchant(null,"Death's Embrace",'+28 Attack Power · +1% Dodge',{ap:28,dodge:1,source:'https://www.wowhead.com/forever/item=19784/deaths-embrace'}),
    Shoulder:enchant(29483,'Might of the Scourge','+26 Attack Power · +1% Melee/Ranged Crit',{ap:26,crit:1}),
    Back:enchant(25083,'Enchant Cloak - Stealth','Stealth detection as if 1 level higher',{stealthLevel:1}),
    Chest:enchant(20026,'Enchant Chest - Major Health','+100 Health',{health:100}),
    Wrist:enchant(20011,'Enchant Bracer - Superior Stamina','+9 Stamina',{sta:9}),
    Hands:enchant(25080,'Enchant Gloves - Superior Agility','+15 Agility',{agi:15}),
    Legs:enchant(null,"Death's Embrace",'+28 Attack Power · +1% Dodge',{ap:28,dodge:1,source:'https://www.wowhead.com/forever/item=19784/deaths-embrace'}),
    Feet:enchant(13890,'Enchant Boots - Minor Speed','Minor movement speed increase'),
    'Main Hand':enchant(20034,'Enchant Weapon - Crusader','On melee attacks: heals for 100 and grants +100 Strength for 15 sec',{procStrength:100,procHeal:100}),
    'Off Hand':enchant(23800,'Enchant Weapon - Agility','+15 Agility',{agi:15}),
    Ranged:enchant(12460,'Sniper Scope','+7 ranged weapon damage',{rangedDamage:7})
  };

  const mageItems={
    Head:item(16441,"Field Marshal's Coronet",'Head',{itemLevel:74,armor:162,sta:28,int:17,spi:6,spellPower:33,spellCrit:1,set:"Field Marshal's Regalia"}),
    Neck:item(22943,'Malice Stone Pendant','Neck',{itemLevel:83,sta:9,int:8,spellPower:28,spellPen:13}),
    Shoulder:item(16444,"Field Marshal's Silk Spaulders",'Shoulder',{itemLevel:74,armor:135,sta:21,int:15,spi:5,spellPower:25,spellPen:10,set:"Field Marshal's Regalia"}),
    Back:item(23017,'Veil of Eclipse','Back',{itemLevel:83,armor:63,sta:10,int:10,spellPower:28,spellPen:10}),
    Chest:item(22496,'Frostfire Robe','Chest',{itemLevel:92,armor:138,sta:21,int:27,spellPower:47,spellHit:1,spellCrit:1,spellPen:13,set:'Frostfire Regalia'}),
    Wrist:item(22503,'Frostfire Bindings','Wrist',{itemLevel:88,armor:58,sta:14,int:15,spellPower:27,spellPen:10,set:'Frostfire Regalia'}),
    Hands:item(16440,"Marshal's Silk Gloves",'Hands',{itemLevel:71,armor:108,sta:22,int:12,spi:5,spellPower:27,set:"Field Marshal's Regalia",special:'Mana Shield absorbs +285'}),
    Waist:item(22502,'Frostfire Belt','Waist',{itemLevel:88,armor:75,sta:19,int:21,spi:10,spellPower:28,spellHit:1,set:'Frostfire Regalia'}),
    Legs:item(22497,'Frostfire Leggings','Legs',{itemLevel:88,armor:116,sta:25,int:26,spi:10,spellPower:46,spellHit:1,set:'Frostfire Regalia'}),
    Feet:item(22500,'Frostfire Sandals','Feet',{itemLevel:86,armor:89,sta:17,int:18,spi:10,spellPower:28,spellCrit:1,set:'Frostfire Regalia'}),
    'Finger 1':item(23062,'Frostfire Ring','Finger 1',{itemLevel:92,sta:10,int:10,spellPower:30,spellCrit:1,set:'Frostfire Regalia'}),
    'Finger 2':item(21707,'Ring of Swarming Thought','Finger 2',{itemLevel:73,spellPower:26,spellPen:20}),
    'Trinket 1':item(18859,'Insignia of the Alliance','Trinket 1',{itemLevel:null,quality:'rare',useEffect:'Dispels all Fear, Polymorph and Slowing effects.',cooldownSec:300}),
    'Trinket 2':item(19024,'Arena Grand Master','Trinket 2',{itemLevel:55,quality:'rare',dodge:1,useEffect:'Absorbs 750 to 1250 damage for 20 sec.',cooldownSec:1800}),
    'Main Hand':item(22799,'Soulseeker','Main Hand',{itemLevel:89,sta:30,int:31,spellPower:126,spellCrit:2,spellPen:25,twoHand:true,weapon:{type:'Staff',minDamage:57,maxDamage:173,speed:3.20,dps:35.94}}),
    'Off Hand':null,
    Ranged:item(22821,'Doomfinger','Ranged',{itemLevel:92,spellPower:16,spellCrit:1,weapon:{type:'Wand',minDamage:10,maxDamage:31,school:'Shadow',schoolMin:146,schoolMax:271,speed:1.50,dps:152.67}})
  };
  const mageEnchants={
    Head:enchant(24164,'Presence of Sight','+18 Spell Damage/Healing · +1% Spell Hit',{spellPower:18,spellHit:1}),
    Shoulder:enchant(29467,'Power of the Scourge','+15 Spell Damage/Healing · +1% Spell Crit',{spellPower:15,spellCrit:1}),
    Back:enchant(20014,'Enchant Cloak - Greater Resistance','+5 All Resistances',{resAll:5}),
    Chest:enchant(20026,'Enchant Chest - Major Health','+100 Health',{health:100}),
    Wrist:enchant(20011,'Enchant Bracer - Superior Stamina','+9 Stamina',{sta:9}),
    Hands:enchant(25074,'Enchant Gloves - Frost Power','+20 Frost Spell Damage',{frostPower:20}),
    Legs:enchant(24164,'Presence of Sight','+18 Spell Damage/Healing · +1% Spell Hit',{spellPower:18,spellHit:1}),
    Feet:enchant(13890,'Enchant Boots - Minor Speed','Minor movement speed increase'),
    'Main Hand':enchant(22749,'Enchant Weapon - Spell Power','+30 Spell Damage',{spellPower:30})
  };

  const profiles={
    'Rogue|Subtlety|Undead':{id:'forever_rogue_subtlety_undead_reference',label:'Forever PvP reference loadout',items:rogueItems,enchants:rogueEnchants},
    'Mage|Frost|Gnome':{id:'forever_mage_frost_gnome_reference',label:'Forever PvP reference loadout',items:mageItems,enchants:mageEnchants}
  };
  function profileFor(s){return profiles[[s?.class,s?.spec,s?.race].join('|')]||null;}
  function slotsFor(s){
    const p=profileFor(s);
    return SLOT_ORDER.map(slot=>{
      const i=p?.items?.[slot]||null,e=p?.enchants?.[slot]||null;
      return {slot,item:i,enchant:e,verified:!!i?.verified,emptyVerified:slot==='Off Hand'&&s?.class==='Mage'&&s?.spec==='Frost'&&s?.race==='Gnome'};
    });
  }
  function totalsFor(s){
    const p=profileFor(s),fields=['armor','str','agi','sta','int','spi','ap','hit','crit','spellPower','spellHit','spellCrit','spellPen','dodge','shadowRes','health','resAll','frostPower','rangedDamage'];
    const items=Object.fromEntries(fields.map(k=>[k,0])),enchants=Object.fromEntries(fields.map(k=>[k,0]));
    for(const i of Object.values(p?.items||{}).filter(Boolean))for(const k of fields)items[k]+=Number(i[k]||0);
    for(const e of Object.values(p?.enchants||{}).filter(Boolean))for(const k of fields)enchants[k]+=Number(e[k]||0);
    return {items,enchants,combined:Object.fromEntries(fields.map(k=>[k,items[k]+enchants[k]]))};
  }
  function audit(s){
    const p=profileFor(s),slots=slotsFor(s),verified=slots.filter(x=>x.verified).length,emptyVerified=slots.filter(x=>x.emptyVerified).length;
    const enchants=Object.values(p?.enchants||{}),verifiedEnchants=enchants.filter(x=>x?.verified).length;
    return {profile:!!p,verifiedItems:verified,modeledSlots:SLOT_ORDER.length,emptyVerified,verifiedEnchants,totalEnchants:enchants.length,gearIdentityPass:!!p&&(verified+emptyVerified===SLOT_ORDER.length)};
  }
  window.WOW_FOREVER_ARMORY_DATA={SLOT_ORDER,profiles,profileFor,slotsFor,totalsFor,audit,itemUrl:source,spellUrl:spell,version:'0.41-wowhead-forever-items-enchants'};
})();