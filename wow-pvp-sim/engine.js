window.WOW_ENGINE=(function(){
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  class RNG{
    constructor(seed){this.state=(Number(seed)||1)>>>0;if(this.state===0)this.state=1;}
    nextU32(){let x=this.state>>>0;x^=(x<<13)>>>0;x^=x>>>17;x^=(x<<5)>>>0;this.state=x>>>0;return this.state;}
    next(){return this.nextU32()/4294967296;}
  }
  function physicalArmorReduction(armor,attackerLevel){
    const x=0.1*armor/(8.5*attackerLevel+40);
    return clamp(x/(1+x),0,0.75);
  }
  function sameLevelSpellMiss(spellHitPct){return Math.max(1,4-Number(spellHitPct||0));}
  function sameLevelMeleeSpecialMiss(hitPct){return Math.max(0,5-Number(hitPct||0));}
  function baseCritMultiplier(kind){if(kind==='physical')return 2;if(kind==='spell')return 1.5;throw new Error('STRICT_DATA_GATE');}
  function profileReady(p){return !!p && p.fullCharacterStatsReady===true;}
  return {RNG,physicalArmorReduction,sameLevelSpellMiss,sameLevelMeleeSpecialMiss,baseCritMultiplier,profileReady};
})();
