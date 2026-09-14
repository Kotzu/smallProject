(()=>{
  const base=window.WOW_DUEL,D=window.WOW_DATA,T=window.WOW_TALENTS;
  if(!base)return;
  const $=id=>document.getElementById(id);
  const normalize=cfg=>{
    const c={a:{...(cfg?.a||{})},b:{...(cfg?.b||{})}};
    if(T){c.a.build=c.a.build||$('abuild')?.value||T.defaultBuild(c.a.class,c.a.spec);c.b.build=c.b.build||$('bbuild')?.value||T.defaultBuild(c.b.class,c.b.spec);}
    return c;
  };
  const canRun=cfg=>{
    const c=normalize(cfg),g=base.canRun(c),ta=T?.kernelAudit(c)||{pass:true,missing:[]};
    const missing=[...new Set([...(g.missing||[]),...(ta.missing||[])])];
    return {ready:g.ready&&ta.pass,missing,config:c,talents:ta};
  };
  const run=(seed,cfg)=>{
    const c=normalize(cfg),gate=canRun(c);
    if(!gate.ready)return {error:'STRICT_DATA_GATE',missing:gate.missing};
    const r=base.run(seed,c);
    if(r&&!r.error){
      r.calibrationRequired=[];
      r.poisonAudit=D.pvpProfiles?.rogue_sub_undead_p6_static?.poisonApplicationAudit||null;
      r.kernelStatus='FIRST_MATCHUP_CALIBRATED_WITH_TALENTS';
      if(T)r.builds={a:{id:c.a.build,name:T.get(c.a.build)?.name,points:T.get(c.a.build)?.points},b:{id:c.b.build,name:T.get(c.b.build)?.name,points:T.get(c.b.build)?.points}};
    }
    return r;
  };
  const batch=(seed,count,cfg)=>{const c=normalize(cfg),gate=canRun(c);if(!gate.ready)return{error:'STRICT_DATA_GATE',missing:gate.missing};const b=base.batch(seed,count,c);if(b&&!b.error&&T)b.builds={a:c.a.build,b:c.b.build};return b;};
  const selfTest=cfg=>{const c=normalize(cfg),a=run(1337,c),b=run(1337,c);return{deterministic:JSON.stringify(a)===JSON.stringify(b),winner:a.winner,duration:a.duration,version:'0.16.0',builds:a.builds};};
  window.WOW_DUEL={...base,version:'0.16.0',canRun,run,batch,selfTest,normalizeConfig:normalize};
})();