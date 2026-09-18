(function(){
  const PRESETS=[
    {
      id:'rogue_assassination_popular_38_11_2_20260918',className:'Rogue',spec:'Assassination',
      label:'Popular Assassination · 38/11/2',distribution:'38/11/2',sourceType:'PUBLIC_MOST_VIEWED',
      source:'https://wowforevertalents.com/rogue/?t=x00531310551521051-320303-002',sourceIndex:'https://wowforevertalents.com/builds/',
      observedAt:'2026-09-18',popularity:{views:3519},notRecommendation:true,
      ranks:{'Malice':5,'Ruthlessness':3,'Murder':1,'Improved Slice and Dice':3,'Relentless Strikes':1,'Lethality':5,'Vile Poisons':5,'Cold Blood':1,'Improved Poisons':5,'Vigor':2,'Mutilate':1,'Seal Fate':5,'Venom':1,'Improved Eviscerate':3,'Improved Sinister Strike':2,'Puncturing Wounds':3,'Precision':3,'Opportunity':2}
    },
    {
      id:'rogue_sub_popular_22_3_26_20260918',className:'Rogue',spec:'Subtlety',
      label:'Popular Subtlety · 22/3/26',distribution:'22/3/26',sourceType:'PUBLIC_BUILD',
      source:'https://wowforevertalents.com/rogue/?t=x005320104410002-3-5300200312213211',sourceIndex:'https://wowforevertalents.com/builds/',
      observedAt:'2026-09-18',popularity:{views:2077},notRecommendation:true,
      ranks:{'Malice':5,'Ruthlessness':3,'Murder':2,'Relentless Strikes':1,'Lethality':4,'Vile Poisons':4,'Cold Blood':1,'Improved Kidney Shot':2,'Improved Eviscerate':3,'Camouflage':5,'Master of Deception':3,'Elusiveness':2,'Initiative':3,'Ghostly Strike':1,'Improved Distract':2,'Heightened Senses':2,'Premeditation':1,'Serrated Blades':3,'Dirty Deeds':2,'Preparation':1,'Hemorrhage':1}
    },
    {
      id:'rogue_sub_popular_11_8_32_20260918',className:'Rogue',spec:'Subtlety',
      label:'Popular Subtlety · 11/8/32',distribution:'11/8/32',sourceType:'PUBLIC_BUILD',
      source:'https://wowforevertalents.com/rogue/?t=x0052031-3023-0323003302213211051',sourceIndex:'https://wowforevertalents.com/builds/',
      observedAt:'2026-09-18',popularity:{views:1456},notRecommendation:true,
      ranks:{'Malice':5,'Ruthlessness':2,'Improved Slice and Dice':3,'Relentless Strikes':1,'Improved Eviscerate':3,'Lightning Reflexes':2,'Puncturing Wounds':3,'Master of Deception':3,'Opportunity':2,'Setup':3,'Improved Ambush':3,'Initiative':3,'Improved Distract':2,'Heightened Senses':2,'Premeditation':1,'Serrated Blades':3,'Dirty Deeds':2,'Preparation':1,'Hemorrhage':1,'Cutthroat':5,'Thousand Cuts':1}
    },
    {
      id:'mage_arcane_popular_37_0_14_20260918',className:'Mage',spec:'Arcane',
      label:'Popular Arcane · 37/0/14',distribution:'37/0/14',sourceType:'PUBLIC_MOST_VIEWED',
      source:'https://wowforevertalents.com/mage/?t=x055205023100311531--05003200013',sourceIndex:'https://wowforevertalents.com/builds/',
      observedAt:'2026-09-18',popularity:{views:1577},notRecommendation:true,
      ranks:{'Arcane Focus':5,'Improved Channeling':5,'Arcane Subtlety':2,'Arcane Concentration':5,'Arcane Geometry':2,'Arcane Impact':3,'Arcane Blast':1,'Arcane Meditation':3,'Missile Barrage':1,'Presence of Mind':1,'Arcane Mind':5,'Arcane Instability':3,'Arcane Power':1,'Improved Frostbolt':5,'Permafrost':3,'Improved Frost Nova':2,'Ice Lance':1,'Improved Blizzard':3}
    },
    {
      id:'mage_frost_popular_18_0_33_19163a',className:'Mage',spec:'Frost',
      label:'Popular Frost · 18/0/33',distribution:'18/0/33',sourceType:'PUBLIC_BUILD',
      source:'https://wowforevertalents.com/mage/builds/frost-18-0-33-19163a/',sourceIndex:'https://wowforevertalents.com/builds/',
      observedAt:'2026-09-18',popularity:{views:591,upvotes:5,downvotes:0},notRecommendation:true,
      ranks:{'Improved Channeling':5,'Arcane Concentration':5,'Arcane Resilience':2,'Arcane Geometry':2,'Arcane Impact':1,'Improved Counterspell':2,'Missile Barrage':1,'Improved Frostbolt':5,'Ice Shards':5,'Permafrost':3,'Improved Frost Nova':2,'Frostbite':3,'Piercing Ice':3,'Ice Lance':1,'Improved Blizzard':1,'Arctic Reach':2,'Ice Block':1,'Shatter':3,'Cold Snap':1,'Fingers of Frost':2,'Ice Barrier':1}
    },
    {
      id:'warrior_fury_popular_17_34_0_20260918',className:'Warrior',spec:'Fury',
      label:'Popular Fury · 17/34/0',distribution:'17/34/0',sourceType:'PUBLIC_MOST_VIEWED',
      source:'https://wowforevertalents.com/warrior/?t=x30305013002-050530025150110051',sourceIndex:'https://wowforevertalents.com/builds/',
      observedAt:'2026-09-18',popularity:{views:3101},notRecommendation:true,
      ranks:{'Improved Heroic Strike':3,'Improved Rend':3,'Improved Tactical Mastery':5,'Anger Management':1,'Deep Wounds':3,'Impale':2,'Cruelty':5,'Unbridled Wrath':5,'Improved Cleave':3,'Boundless Rage':2,'Dual Wield Specialization':5,'Raging Blows':1,'Enrage':5,'Precision':1,'Death Wish':1,'Flurry':5,'Bloodthirst':1}
    },
    {
      id:'paladin_prot_popular_2_31_18_20260918',className:'Paladin',spec:'Protection',
      label:'Popular Protection · 2/31/18',distribution:'2/31/18',sourceType:'PUBLIC_MOST_VIEWED',
      source:'https://wowforevertalents.com/paladin/?t=x2-0530513321001151-542200002012',sourceIndex:'https://wowforevertalents.com/builds/',
      observedAt:'2026-09-18',popularity:{views:4365},notRecommendation:true,
      ranks:{'Improved Holy Strike':2,'Redoubt':5,'Precision':3,'Anticipation':5,'Improved Seal of Fury':1,'Improved Righteous Fury':3,'Shield Specialization':3,'Sacred Duty':2,'Swift Judgement':1,"Templar's Bulwark":1,'Reckoning':1,'Iron Creed':5,'Holy Shield':1,'Deflection':5,'Benediction':4,'Improved Judgement':2,'Holy Conduit':2,'Pursuit of Justice':2,'Sacred Arbiter':1,'Crusade':2}
    },
    {
      id:'hunter_survival_popular_5_11_35_20260918',className:'Hunter',spec:'Survival',
      label:'Popular Survival · 5/11/35',distribution:'5/11/35',sourceType:'PUBLIC_MOST_VIEWED',
      source:'https://wowforevertalents.com/hunter/?t=x5-005005001-500250230050222151',sourceIndex:'https://wowforevertalents.com/builds/',
      observedAt:'2026-09-18',popularity:{views:8896},notRecommendation:true,
      ranks:{'Deadly Aspects':5,'Lethal Attacks':5,'Careful Aim':5,'Lone Wolf':1,'Improved Tracking':5,'Savage Strikes':2,'Survivalist':5,'Clever Traps':2,'Surefooted':3,"Predator's Edge":5,'Resourcefulness':2,'Expose Prey':2,"Survivalist's Discipline":2,'Strider Kick':1,'Lightning Reflexes':5,'Lacerating Strikes':1}
    },
    {
      id:'priest_disc_popular_32_19_0_20260918',className:'Priest',spec:'Discipline',
      label:'Popular Discipline · 32/19/0',distribution:'32/19/0',sourceType:'PUBLIC_MOST_VIEWED',
      source:'https://wowforevertalents.com/priest/?t=x005003221305101531-205050030301',sourceIndex:'https://wowforevertalents.com/builds/',
      observedAt:'2026-09-18',popularity:{views:5017},notRecommendation:true,
      ranks:{'Twin Disciplines':5,'Improved Power Word: Shield':3,'Martyrdom':2,'Mental Agility':2,'Inner Focus':1,'Meditation':3,'Mental Strength':5,'Soul Warding':1,'Penance':1,'Renewed Hope':5,'Divine Aegis':3,'Power Infusion':1,'Twilight Focus':2,'Holy Specialization':5,'Divine Fury':5,'Inspiration':3,'Improved Healing':3,'Binding Heal':1}
    },
    {
      id:'shaman_enh_popular_19_32_0_20260918',className:'Shaman',spec:'Enhancement',
      label:'Popular Enhancement · 19/32/0',distribution:'19/32/0',sourceType:'PUBLIC_MOST_VIEWED',
      source:'https://wowforevertalents.com/shaman/?t=x05003305201-050032131005112251',sourceIndex:'https://wowforevertalents.com/builds/',
      observedAt:'2026-09-18',popularity:{views:4607},notRecommendation:true,
      ranks:{'Concussion':5,'Call of Flame':3,'Elemental Devastation':3,'Elemental Fury':5,'Improved Fire Nova':2,'Call of Thunder':1,'Thundering Strikes':5,'Mental Dexterity':3,'Improved Ghost Wolf':2,'Improved Lightning Shield':1,'Elemental Weapons':3,'Shamanistic Focus':1,'Flurry':5,'Stormstrike':1,'Spirit Weapons':1,'Mental Quickness':2,'Improved Stormstrike':2,'Maelstrom Weapon':5,'Rage of the Farseer':1}
    },
    {
      id:'warlock_demo_popular_5_31_15_20260918',className:'Warlock',spec:'Demonology',
      label:'Popular Demonology · 5/31/15',distribution:'5/31/15',sourceType:'PUBLIC_MOST_VIEWED',
      source:'https://wowforevertalents.com/warlock/?t=x05-0055003201221001351-0550005',sourceIndex:'https://wowforevertalents.com/builds/',
      observedAt:'2026-09-18',popularity:{views:4785},notRecommendation:true,
      ranks:{'Suppression':5,'Demonic Embrace':5,'Unholy Power':5,'Fel Vitality':3,'Demonic Energies':2,'Demonic Sacrifice':1,'Master Summoner':2,'Decimation':2,'Fel Domination':1,'Soul Link':1,'Demonic Knowledge':3,'Master Demonologist':5,'Demonic Pact':1,'Improved Shadow Bolt':5,'Bane':5,'Ruin':5}
    },
    {
      id:'druid_resto_popular_11_7_33_20260918',className:'Druid',spec:'Restoration',
      label:'Popular Restoration · 11/7/33',distribution:'11/7/33',sourceType:'PUBLIC_MOST_VIEWED',
      source:'https://wowforevertalents.com/druid/?t=x05302001-052-5050035103113051',sourceIndex:'https://wowforevertalents.com/builds/',
      observedAt:'2026-09-18',popularity:{views:5858},notRecommendation:true,
      ranks:{'Genesis':5,'Moonglow':3,"Nature's Majesty":2,"Nature's Splendor":1,'Heart of the Wild':5,'Feral Swiftness':2,"Nature's Focus":5,'Naturalist':5,'Reflection':3,'Gift of Nature':5,'Gift of the Earthmother':1,'Improved Rejuvenation':3,'Swiftmend':1,"Nature's Swiftness":1,'Living Spirit':3,'Improved Regrowth':5,'Wild Growth':1}
    }
  ];

  const clone=v=>JSON.parse(JSON.stringify(v));
  function list(className,spec){
    return PRESETS.filter(p=>(!className||p.className===className)&&(!spec||p.spec===spec))
      .sort((a,b)=>(b.popularity?.views||0)-(a.popularity?.views||0))
      .map(clone);
  }
  function get(id){const p=PRESETS.find(x=>x.id===id);return p?clone(p):null;}
  function defaultFor(className,spec){return list(className,spec)[0]||null;}
  function popularityLabel(p){
    const bits=[];
    if(p?.popularity?.views!=null)bits.push(Number(p.popularity.views).toLocaleString('ro-RO')+' views');
    if(p?.popularity?.upvotes!=null)bits.push(p.popularity.upvotes+' up');
    return bits.join(' · ')||'public build';
  }
  function points(p){return Object.values(p?.ranks||{}).reduce((n,v)=>n+Number(v||0),0);}
  function apply(player,id){
    const p=get(id);if(!p)return{ok:false,reason:'Unknown preset'};
    return window.WOW_FOREVER_BUILDS?.applyPreset?.(player,p)||{ok:false,reason:'Build allocator unavailable'};
  }
  function applyDefault(player,className,spec,{force=false}={}){
    const p=defaultFor(className,spec);if(!p)return{ok:false,reason:'No popular preset for this class/spec'};
    const B=window.WOW_FOREVER_BUILDS,current=B?.get?.(player);
    if(!force&&current?.points>0)return{ok:false,reason:'Existing build preserved'};
    return B?.applyPreset?.(player,p)||{ok:false,reason:'Build allocator unavailable'};
  }

  window.WOW_FOREVER_PRESETS={
    version:'0.2-popular-public-builds',
    observedAt:'2026-09-18',
    sourceIndex:'https://wowforevertalents.com/builds/',
    note:'Popularity reflects saved public pre-release builds, not a best-build recommendation.',
    all:()=>PRESETS.map(clone),list,get,defaultFor,popularityLabel,points,apply,applyDefault
  };
})();