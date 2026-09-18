(function(){
  const PRESETS=[
    {
      id:'rogue_sub_popular_22_3_26_20260918',
      className:'Rogue',spec:'Subtlety',
      label:'Popular Subtlety · 22/3/26',
      distribution:'22/3/26',
      sourceType:'PUBLIC_BUILD',
      source:'https://wowforevertalents.com/rogue/?t=x005320104410002-3-5300200312213211',
      sourceIndex:'https://wowforevertalents.com/builds/',
      observedAt:'2026-09-18',
      popularity:{views:2077},
      notRecommendation:true,
      ranks:{
        'Malice':5,'Ruthlessness':3,'Murder':2,'Relentless Strikes':1,'Lethality':4,'Vile Poisons':4,'Cold Blood':1,'Improved Kidney Shot':2,
        'Improved Eviscerate':3,
        'Camouflage':5,'Master of Deception':3,'Elusiveness':2,'Initiative':3,'Ghostly Strike':1,'Improved Distract':2,'Heightened Senses':2,
        'Premeditation':1,'Serrated Blades':3,'Dirty Deeds':2,'Preparation':1,'Hemorrhage':1
      }
    },
    {
      id:'rogue_sub_popular_11_8_32_20260918',
      className:'Rogue',spec:'Subtlety',
      label:'Popular Subtlety · 11/8/32',
      distribution:'11/8/32',
      sourceType:'PUBLIC_BUILD',
      source:'https://wowforevertalents.com/rogue/?t=x0052031-3023-0323003302213211051',
      sourceIndex:'https://wowforevertalents.com/builds/',
      observedAt:'2026-09-18',
      popularity:{views:1456},
      notRecommendation:true,
      ranks:{
        'Malice':5,'Ruthlessness':2,'Improved Slice and Dice':3,'Relentless Strikes':1,
        'Improved Eviscerate':3,'Lightning Reflexes':2,'Puncturing Wounds':3,
        'Master of Deception':3,'Opportunity':2,'Setup':3,'Improved Ambush':3,'Initiative':3,'Improved Distract':2,'Heightened Senses':2,
        'Premeditation':1,'Serrated Blades':3,'Dirty Deeds':2,'Preparation':1,'Hemorrhage':1,'Cutthroat':5,'Thousand Cuts':1
      }
    },
    {
      id:'mage_frost_popular_18_0_33_19163a',
      className:'Mage',spec:'Frost',
      label:'Popular Frost · 18/0/33',
      distribution:'18/0/33',
      sourceType:'PUBLIC_BUILD',
      source:'https://wowforevertalents.com/mage/builds/frost-18-0-33-19163a/',
      sourceIndex:'https://wowforevertalents.com/builds/',
      observedAt:'2026-09-18',
      popularity:{views:591,upvotes:5,downvotes:0},
      notRecommendation:true,
      ranks:{
        'Improved Channeling':5,'Arcane Concentration':5,'Arcane Resilience':2,'Arcane Geometry':2,'Arcane Impact':1,'Improved Counterspell':2,'Missile Barrage':1,
        'Improved Frostbolt':5,'Ice Shards':5,'Permafrost':3,'Improved Frost Nova':2,'Frostbite':3,'Piercing Ice':3,'Ice Lance':1,
        'Improved Blizzard':1,'Arctic Reach':2,'Ice Block':1,'Shatter':3,'Cold Snap':1,'Fingers of Frost':2,'Ice Barrier':1
      }
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
    version:'0.1-popular-public-builds',
    observedAt:'2026-09-18',
    sourceIndex:'https://wowforevertalents.com/builds/',
    note:'Popularity reflects saved public pre-release builds, not a best-build recommendation.',
    all:()=>PRESETS.map(clone),list,get,defaultFor,popularityLabel,apply,applyDefault
  };
})();