(()=>{
  const base=window.WOW_DUEL,T=window.WOW_TALENTS,A=window.WOW_ARMORY;
  if(!base||!T)return;
  const $=id=>document.getElementById(id);
  function cloneCfg(cfg){return {a:{...(cfg?.a||{})},b:{...(cfg?.b||{})}};}
  function normalize(cfg){
    const c=cloneCfg(cfg);
    c.a.build=c.a.build||$('abuild')?.value||T.defaultBuild(c.a.class,c.a.spec);
    c.b.build=c.b.build||$('bbuild')?.value||T.defaultBuild(c.b.class,c.b.spec);
    return c;
  }
  function canRun(cfg){
    const c=normalize(cfg),g=base.canRun(c),ta=T.kernelAudit(c),missing=[...(g.missing||[]),...(ta.missing||[])];
    const aa=A?.audit?.(c.a),ab=A?.audit?.(c.b);
    if(aa&&!aa.pass)missing.push('Player A loadout/stat audit failed');
    if(ab&&!ab.pass)missing.push('Player B loadout/stat audit failed');
    return {ready:g.ready&&ta.pass&&(!aa||aa.pass)&&(!ab||ab.pass),missing:[...new Set(missing)],talents:ta,armory:{a:aa,b:ab},config:c};
  }
  function run(seed,cfg){
    const c=normalize(cfg),gate=canRun(c);
    if(!gate.ready)return {error:'STRICT_DATA_GATE',missing:gate.missing};
    const r=base.run(seed,c);
    if(r&&!r.error){
      r.builds={
        a:{id:c.a.build,name:T.get(c.a.build)?.name,points:T.get(c.a.build)?.points,class:c.a.class,spec:c.a.spec},
        b:{id:c.b.build,name:T.get(c.b.build)?.name,points:T.get(c.b.build)?.points,class:c.b.class,spec:c.b.spec}
      };
      r.talentAudit={status:'PASS',a:gate.talents.a.reason,b:gate.talents.b.reason};
      r.loadoutAudit={a:gate.armory.a?.status||'N/A',b:gate.armory.b?.status||'N/A'};
      r.kernelStatus='FIRST_MATCHUP_CALIBRATED_WITH_TALENTS';
    }
    return r;
  }
  function batch(seed,count,cfg){
    const c=normalize(cfg),gate=canRun(c);
    if(!gate.ready)return {error:'STRICT_DATA_GATE',missing:gate.missing};
    const b=base.batch(seed,count,c);
    if(b&&!b.error)b.builds={a:c.a.build,b:c.b.build};
    return b;
  }
  function selfTest(cfg){
    const c=normalize(cfg),a=run(1337,c),b=run(1337,c);
    return {deterministic:JSON.stringify(a)===JSON.stringify(b),winner:a.winner,duration:a.duration,version:'0.17.0',builds:a.builds};
  }
  window.WOW_DUEL={...base,version:'0.17.0',canRun,run,batch,selfTest,normalizeConfig:normalize};
})();
