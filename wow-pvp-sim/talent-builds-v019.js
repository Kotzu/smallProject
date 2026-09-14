(()=>{
  const D=window.WOW_DATA||{},T=window.WOW_TALENTS;
  if(!T)return;

  const canonical=T.get('rogue_imp_sprint_backstab_16_12_23');
  if(canonical){
    canonical.modifiers={...(canonical.modifiers||{}),vanishCooldownMs:210000,blindCooldownMs:210000,daggerWeaponSkill:303,weaponSkillMissReductionPct:0.12,weaponSkillDodgeReductionPct:0.12,improvedGougeDurationMs:5500};
    canonical.kernelBlockers=['MOVE_BEHIND / rear-arc parity','Initiative extra-combo-point proc path','Gouge control/break-on-damage path','policy parity QA'];
  }
  const variant=T.get('rogue_imp_sprint_backstab_17_12_22');
  if(variant){
    variant.modifiers={...(variant.modifiers||{}),daggerWeaponSkill:303,weaponSkillMissReductionPct:0.12,weaponSkillDodgeReductionPct:0.12,improvedGougeDurationMs:5500};
    variant.kernelBlockers=['MOVE_BEHIND / rear-arc parity','Gouge control/break-on-damage path','policy parity QA'];
  }

  // Current pre-beta Forever structure from Wowhead's /forever/talent-calc pages, checked 2026-09-14.
  // Wowhead explicitly labels these trees as BlizzCon/stream data that will be refreshed from the beta client.
  const classStructure={
    Warrior:{trees:{Arms:17,Fury:18,Protection:19}},
    Paladin:{trees:{Holy:18,Protection:16,Retribution:18}},
    Hunter:{trees:{'Beast Mastery':16,Marksmanship:16,Survival:18}},
    Rogue:{trees:{Assassination:17,Combat:17,Subtlety:19}},
    Priest:{trees:{Discipline:18,Holy:17,Shadow:18}},
    Shaman:{trees:{Elemental:16,Enhancement:18,Restoration:16}},
    Mage:{trees:{Arcane:18,Fire:17,Frost:19}},
    Warlock:{trees:{Affliction:17,Demonology:19,Destruction:16}},
    Druid:{trees:{Balance:17,'Feral Combat':19,Restoration:16}}
  };

  const rogueTrees={
    Assassination:[
      ['Improved Gouge',3],['Remorseless Attacks',2],['Malice',5],['Ruthlessness',3],['Murder',2],['Improved Slice and Dice',3],['Relentless Strikes',1],['Improved Expose Armor',2],['Lethality',5],['Vile Poisons',5],['Cold Blood',1],['Improved Poisons',5],['Vigor',2],['Mutilate',1],['Improved Kidney Shot',2],['Seal Fate',5],['Venom',1]
    ],
    Combat:[
      ['Improved Eviscerate',3],['Improved Sinister Strike',2],['Lightning Reflexes',5],['Puncturing Wounds',3],['Deflection',3],['Precision',3],['Endurance',2],['Riposte',1],['Improved Sprint',2],['Improved Kick',2],['Restless Blades',1],['Dual Wield Specialization',5],['Blade Flurry',1],['Hack and Slash',5],['Weapon Expertise',2],['Aggression',3],['Adrenaline Rush',1]
    ],
    Subtlety:[
      ['Camouflage',5],['Master of Deception',3],['Opportunity',2],['Setup',3],['Elusiveness',2],['Dirty Tricks',2],['Improved Ambush',3],['Initiative',3],['Ghostly Strike',1],['Improved Distract',2],['Heightened Senses',2],['Premeditation',1],['Serrated Blades',3],['Dirty Deeds',2],['Preparation',1],['Hemorrhage',1],['Quietus',5],['Cutthroat',5],['Thousand Cuts',1]
    ]
  };

  const mageTrees={
    Arcane:[
      ['Wand Specialization',2],['Arcane Focus',5],['Improved Channeling',5],['Arcane Subtlety',2],['Magic Absorption',2],['Arcane Concentration',5],['Arcane Resilience',2],['Arcane Geometry',2],['Arcane Impact',3],['Arcane Blast',1],['Arcane Shielding',2],['Improved Counterspell',2],['Arcane Meditation',3],['Missile Barrage',1],['Presence of Mind',1],['Arcane Mind',5],['Arcane Instability',3],['Arcane Power',1]
    ],
    Fire:[
      ['Wake of Fire',2],['Incineration',3],['Unverified Fire slot A',null],['Unverified Fire slot B',null],['Flame Throwing',2],['Impact',3],['Burning Soul',3],['Improved Flamestrike',3],['Pyroblast',1],['Improved Scorch',3],['Improved Fire Ward',2],['Hot Streak',1],['Master of Elements',3],['Critical Mass',3],['Blast Wave',1],['Fire Power',5],['Combustion',1]
    ],
    Frost:[
      ['Frost Warding',2],['Improved Frostbolt',5],['Elemental Precision',5],['Ice Shards',5],['Permafrost',3],['Improved Frost Nova',2],['Frostbite',3],['Piercing Ice',3],['Frost Channeling',3],['Ice Lance',1],['Improved Blizzard',3],['Arctic Reach',2],['Ice Block',1],['Shatter',3],['Improved Cone of Cold',3],['Cold Snap',1],['Fingers of Frost',2],['Winter\'s Chill',5],['Ice Barrier',1]
    ]
  };

  function nodes(arr){return arr.map(([name,maxRank],i)=>({index:i,name,maxRank,status:maxRank==null?'INCOMPLETE_DEMO_TOOLTIP':'DEMO_CAPTURED'}));}
  function totalNodes(){return Object.values(classStructure).reduce((sum,c)=>sum+Object.values(c.trees).reduce((a,b)=>a+b,0),0);}
  function classTotal(className){const c=classStructure[className];return c?Object.values(c.trees).reduce((a,b)=>a+b,0):0;}

  const forever={
    id:'wowhead-forever-prebeta-2026-09-14',
    game:'WoW Forever',
    snapshotDate:'2026-09-14',
    pointCap:51,
    status:'PRE_BETA_DEMO',
    strictFightStatus:'LOCKED_UNTIL_FOREVER_BUILD_AND_RUNTIME_CALIBRATED',
    officialSource:'https://www.wowhead.com/forever/talent-calc',
    officialNote:'Wowhead: trees use information from BlizzCon testing and event streams; data/icons will be refreshed from the beta client when available.',
    transcriptionSource:'https://classicwowforever.com/talents/',
    structure:classStructure,
    namedTrees:{Rogue:Object.fromEntries(Object.entries(rogueTrees).map(([k,v])=>[k,nodes(v)])),Mage:Object.fromEntries(Object.entries(mageTrees).map(([k,v])=>[k,nodes(v)]))},
    coverage:{totalNodes:470,namedClasses:['Rogue','Mage'],structureClasses:Object.keys(classStructure),mageIncompleteTalentNames:2},
    totalNodes,classTotal,
    tree(className,treeName){return this.namedTrees?.[className]?.[treeName]||null;},
    classInfo(className){return this.structure[className]||null;}
  };

  // Existing runnable builds are Classic Era builds. Never silently reinterpret them as Forever builds.
  Object.values(T.library||{}).forEach(b=>{if(b&&!b.dataset)b.dataset='ClassicEra';if(b&&b.dataset==='ClassicEra'&&!String(b.name||'').includes('Classic'))b.rulesetLabel='Classic Era';});

  D.foreverTalentSnapshot=forever;
  D.talentBuildLibrary=T.library;
  window.WOW_FOREVER_TALENTS=forever;
  window.WOW_TALENTS={...T,version:'0.28',foreverSnapshot:forever};
})();