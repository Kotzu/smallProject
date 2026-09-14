window.WOW_ENGINE=(function(){
  const TAU=Math.PI*2;
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

  // 2D facing helpers follow CMaNGOS WorldObject::HasInArc/isInBack semantics.
  // Important: CMaNGOS distance also accounts for combat reach / bounding radii;
  // this web helper intentionally uses center-to-center yards until radii are modeled.
  function normalizeAngle(rad){
    let a=Number(rad)||0;
    a%=TAU;
    if(a<=-Math.PI)a+=TAU;
    if(a>Math.PI)a-=TAU;
    return a;
  }
  function distance2D(a,b){return Math.hypot((Number(b?.x)||0)-(Number(a?.x)||0),(Number(b?.y)||0)-(Number(a?.y)||0));}
  function angleTo(a,b){return Math.atan2((Number(b?.y)||0)-(Number(a?.y)||0),(Number(b?.x)||0)-(Number(a?.x)||0));}
  function hasInArc(source,target,arc=Math.PI){
    const width=clamp(Number(arc)||0,0,TAU);
    if(width>=TAU)return true;
    const delta=Math.abs(normalizeAngle(angleTo(source,target)-(Number(source?.o)||0)));
    return delta<=width/2+1e-12;
  }
  function isInBack(target,attacker,maxDistance=5,arc=Math.PI){
    if(distance2D(target,attacker)>Number(maxDistance))return false;
    return !hasInArc(target,attacker,TAU-(Number(arc)||Math.PI));
  }
  function pointBehind(target,distance=2){
    const o=Number(target?.o)||0,d=Number(distance)||0;
    return {x:(Number(target?.x)||0)-Math.cos(o)*d,y:(Number(target?.y)||0)-Math.sin(o)*d,o:normalizeAngle(o)};
  }
  function moveToward(from,to,maxDistance){
    const d=distance2D(from,to),step=Math.max(0,Number(maxDistance)||0);
    if(d===0||step>=d)return {x:Number(to?.x)||0,y:Number(to?.y)||0,o:Number(from?.o)||0};
    const r=step/d;
    return {x:(Number(from?.x)||0)+((Number(to?.x)||0)-(Number(from?.x)||0))*r,y:(Number(from?.y)||0)+((Number(to?.y)||0)-(Number(from?.y)||0))*r,o:Number(from?.o)||0};
  }
  return {RNG,physicalArmorReduction,sameLevelSpellMiss,sameLevelMeleeSpecialMiss,baseCritMultiplier,profileReady,normalizeAngle,distance2D,angleTo,hasInArc,isInBack,pointBehind,moveToward};
})();
