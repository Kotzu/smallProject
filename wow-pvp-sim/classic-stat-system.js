window.WOW_STATS=(function(){
  const classes={
    Warrior:{base:{health:1689,mana:0,str:120,agi:80,sta:110,int:30,spi:45,baseAP:160},baseCrit:{melee:0,spell:0,dodge:0},per:{strAP:2,agiAP:0,agiCrit:0.0500,agiDodge:0.0500,intSpellCrit:0},primaryBySpec:{Arms:'Strength',Fury:'Strength',Protection:'Strength / Stamina'}},
    Paladin:{base:{health:1381,mana:1512,str:105,agi:65,sta:100,int:70,spi:75,baseAP:160},baseCrit:{melee:0.7,spell:3.5,dodge:0.7},per:{strAP:2,agiAP:0,agiCrit:0.0506,agiDodge:0.0506,intSpellCrit:0.0167},primaryBySpec:{Holy:'Intellect',Protection:'Stamina / Strength',Retribution:'Strength'}},
    Hunter:{base:{health:1467,mana:1720,str:55,agi:125,sta:90,int:65,spi:70,baseAP:100,baseRAP:100},baseCrit:{melee:0,spell:3.6,dodge:0},per:{strAP:1,agiAP:0,agiRAP:2,agiCrit:0.0189,agiDodge:0.0378,intSpellCrit:0.0165},primaryBySpec:{'Beast Mastery':'Agility',Marksmanship:'Agility',Survival:'Agility'}},
    Rogue:{base:{health:1523,mana:0,str:80,agi:130,sta:75,int:35,spi:50,baseAP:100,baseRAP:50},baseCrit:{melee:0,spell:0,dodge:0},per:{strAP:1,agiAP:1,agiRAP:1,agiCrit:0.0345,agiDodge:0.0690,intSpellCrit:0},primaryBySpec:{Assassination:'Agility',Combat:'Agility',Subtlety:'Agility'}},
    Priest:{base:{health:1397,mana:1376,str:35,agi:40,sta:50,int:120,spi:125,baseAP:-10},baseCrit:{melee:3.0,spell:0.8,dodge:3.0},per:{strAP:1,agiAP:0,agiCrit:0.0500,agiDodge:0.0500,intSpellCrit:0.0168},primaryBySpec:{Discipline:'Intellect / Spirit',Holy:'Intellect / Spirit',Shadow:'Intellect / Spell Power'}},
    Shaman:{base:{health:1280,mana:1520,str:85,agi:55,sta:95,int:90,spi:100,baseAP:100},baseCrit:{melee:1.7,spell:2.3,dodge:1.7},per:{strAP:2,agiAP:0,agiCrit:0.0508,agiDodge:0.0508,intSpellCrit:0.0169},primaryBySpec:{Elemental:'Intellect / Spell Power',Enhancement:'Strength / Agility',Restoration:'Intellect / Spirit'}},
    Mage:{base:{health:1370,mana:1213,str:30,agi:35,sta:45,int:125,spi:120,baseAP:-10},baseCrit:{melee:3.2,spell:0.2,dodge:3.2},per:{strAP:1,agiAP:0,agiCrit:0.0514,agiDodge:0.0514,intSpellCrit:0.0168},primaryBySpec:{Arcane:'Intellect / Spell Power',Fire:'Intellect / Spell Power',Frost:'Intellect / Spell Power'}},
    Warlock:{base:{health:1414,mana:1373,str:45,agi:50,sta:65,int:110,spi:115,baseAP:-10},baseCrit:{melee:2.0,spell:1.7,dodge:2.0},per:{strAP:1,agiAP:0,agiCrit:0.0500,agiDodge:0.0500,intSpellCrit:0.0165},primaryBySpec:{Affliction:'Intellect / Spell Power',Demonology:'Stamina / Intellect',Destruction:'Intellect / Spell Power'}},
    Druid:{base:{health:1483,mana:1244,str:65,agi:60,sta:70,int:100,spi:110,baseAP:-20},baseCrit:{melee:0.9,spell:1.8,dodge:0.9},per:{strAP:2,agiAP:1,agiCrit:0.0500,agiDodge:0.0500,intSpellCrit:0.0167},primaryBySpec:{Balance:'Intellect / Spell Power','Feral Combat':'Agility / Strength',Restoration:'Intellect / Spirit'},note:'Feral attack power and weapon behavior are form-dependent and must be evaluated inside the form-specific combat kernel.'}
  };
  const raceOffsets={
    Human:{str:0,agi:0,sta:0,int:0,spi:0},
    Orc:{str:3,agi:-3,sta:2,int:-3,spi:3},
    Dwarf:{str:2,agi:-4,sta:3,int:-1,spi:-1},
    'Night Elf':{str:-3,agi:5,sta:-1,int:0,spi:0},
    Undead:{str:-1,agi:-2,sta:1,int:-2,spi:5},
    Tauren:{str:5,agi:-5,sta:2,int:-5,spi:2},
    Gnome:{str:-5,agi:3,sta:-1,int:3,spi:0},
    Troll:{str:1,agi:2,sta:1,int:-4,spi:1}
  };
  const racialPct={Gnome:{int:5},Tauren:{health:5}};
  const manaRegen={Mage:{flat:13,spiDiv:4},Priest:{flat:13,spiDiv:4},Warlock:{flat:8,spiDiv:4},Druid:{flat:15,spiDiv:5},Shaman:{flat:15,spiDiv:5},Paladin:{flat:15,spiDiv:5},Hunter:{flat:15,spiDiv:5}};

  const add=(a,b)=>({str:a.str+(b.str||0),agi:a.agi+(b.agi||0),sta:a.sta+(b.sta||0),int:a.int+(b.int||0),spi:a.spi+(b.spi||0)});
  function baseFor(className,race){
    const c=classes[className],o=raceOffsets[race];if(!c||!o)return null;
    const stats=add(c.base,o);
    return {class:className,race,level:60,stats,classBase:{health:c.base.health,mana:c.base.mana,baseAP:c.base.baseAP,baseRAP:c.base.baseRAP||null},racialPct:racialPct[race]||{},baseCrit:{...c.baseCrit},per:{...c.per}};
  }
  function primary(className,spec){return classes[className]?.primaryBySpec?.[spec]||'Spec-dependent';}
  function hpFromSta(sta){const b=Math.min(sta,20);return b+(sta-b)*10;}
  function manaFromInt(int){const b=Math.min(int,20);return b+(int-b)*15;}
  function afterRacialStats(className,race,stats){
    const p=racialPct[race]||{},out={...stats};
    if(p.int)out.int=Math.trunc(out.int*(1+p.int/100));
    return out;
  }
  function derived(className,race,stats,extra={}){
    const c=classes[className];if(!c)return null;
    const s=afterRacialStats(className,race,stats);
    const meleeAP=(c.base.baseAP||0)+s.str*(c.per.strAP||0)+s.agi*(c.per.agiAP||0)+(extra.flatAP||0);
    const rangedAP=c.base.baseRAP==null?null:c.base.baseRAP+s.agi*(c.per.agiRAP||0)+(extra.flatRAP||0);
    const meleeCrit=(c.baseCrit.melee||0)+s.agi*(c.per.agiCrit||0)+(extra.meleeCrit||0);
    const dodge=(c.baseCrit.dodge||0)+s.agi*(c.per.agiDodge||0)+(extra.dodge||0);
    const spellCrit=(c.baseCrit.spell||0)+s.int*(c.per.intSpellCrit||0)+(extra.spellCrit||0);
    const armor=s.agi*2+(extra.armor||0);
    let hp=c.base.health+hpFromSta(s.sta)+(extra.health||0);
    if((racialPct[race]||{}).health)hp=Math.round(hp*(1+racialPct[race].health/100));
    const mana=c.base.mana>0?c.base.mana+manaFromInt(s.int)+(extra.mana||0):0;
    return {stats:s,meleeAP,rangedAP,meleeCrit,dodge,spellCrit,armor,hp,mana};
  }
  function statLines(className,spec){
    const c=classes[className];if(!c)return [];
    const p=c.per;
    const lines=[];
    lines.push({stat:'STR',effect:`${p.strAP||0} melee AP / point${className==='Warrior'||className==='Paladin'||className==='Shaman'?' (major physical scaling)':''}`});
    const agi=[];if(p.agiAP)agi.push(`${p.agiAP} melee AP`);if(p.agiRAP)agi.push(`${p.agiRAP} ranged AP`);agi.push(`${p.agiCrit.toFixed(4)}% physical crit`);agi.push(`${p.agiDodge.toFixed(4)}% dodge`);agi.push('2 Armor');
    lines.push({stat:'AGI',effect:agi.join(' · ')});
    lines.push({stat:'STA',effect:'10 HP / point after the first 20 total Stamina'});
    if(c.base.mana>0)lines.push({stat:'INT',effect:`15 Mana / point after the first 20 total Intellect · ${p.intSpellCrit.toFixed(4)}% spell crit / point`});
    else lines.push({stat:'INT',effect:'No mana pool for this class; no meaningful direct PvP damage scaling in the current kernel.'});
    if(manaRegen[className]){const r=manaRegen[className];lines.push({stat:'SPI',effect:`out-of-5-second-rule mana tick = ${r.flat} + Spirit/${r.spiDiv} (every 2s)`});}
    else lines.push({stat:'SPI',effect:'Health regeneration; class has no Mana pool.'});
    return {primary:primary(className,spec),lines,note:c.note||''};
  }
  return {classes,raceOffsets,racialPct,manaRegen,baseFor,primary,derived,statLines,hpFromSta,manaFromInt,version:'Classic60-live-audit-v1'};
})();
