const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname);
const port = Number(process.env.PORT || 10000);
const mime = {
  '.html':'text/html; charset=utf-8','.js':'application/javascript; charset=utf-8','.css':'text/css; charset=utf-8',
  '.json':'application/json; charset=utf-8','.lua':'text/plain; charset=utf-8','.md':'text/plain; charset=utf-8',
  '.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.ico':'image/x-icon'
};
let foreverTalentCache={payload:null,fetchedAt:0,loading:false,waiters:[]};

function fetchRemote(url, redirects, cb) {
  if (redirects < 0) return cb(new Error('too many redirects'));
  const request = https.get(url, {headers:{'user-agent':'wow-forever-pvp-simulator'}}, r => {
    if (r.statusCode >= 300 && r.statusCode < 400 && r.headers.location) {
      r.resume();return fetchRemote(new URL(r.headers.location,url).toString(),redirects-1,cb);
    }
    if (r.statusCode !== 200) {r.resume();return cb(new Error('upstream HTTP '+r.statusCode));}
    const chunks=[];r.on('data',c=>chunks.push(c));r.on('end',()=>cb(null,Buffer.concat(chunks)));
  });
  request.setTimeout(12000,()=>request.destroy(new Error('upstream timeout')));
  request.on('error',cb);
}
function sendJson(res,status,value){
  const body=JSON.stringify(value);
  res.writeHead(status,{'content-type':'application/json; charset=utf-8','cache-control':'no-store','content-length':Buffer.byteLength(body)});
  res.end(body);
}
function extractJsonObject(text,fromIndex){
  const start=text.indexOf('{',fromIndex);if(start<0)throw new Error('Forever talent JSON object not found');
  let depth=0,inString=false,escaped=false;
  for(let i=start;i<text.length;i++){
    const ch=text[i],code=ch.charCodeAt(0);
    if(inString){
      if(escaped){escaped=false;continue;}
      if(code===92){escaped=true;continue;}
      if(code===34)inString=false;
      continue;
    }
    if(code===34){inString=true;continue;}
    if(ch==='{')depth++;
    else if(ch==='}'){depth--;if(depth===0)return text.slice(start,i+1);}
  }
  throw new Error('Forever talent JSON object is incomplete');
}
function parseForeverTalentJs(text,db){
  const prefix='WH.setPageData("wow.talentCalcClassic.classicplus.data",';
  const start=text.indexOf(prefix);if(start<0)throw new Error('Forever talent payload marker not found');
  const data=JSON.parse(extractJsonObject(text,start+prefix.length));
  let totalNodes=0;for(const tree of Object.values(data.talents||{}))totalNodes+=Object.keys(tree||{}).length;
  const endpoint='https://nether.wowhead.com/forever/data/talents-classic?dv=20&db='+String(db);
  return {
    provenance:{
      source:'Wowhead Forever',calculator:'https://www.wowhead.com/forever/talent-calc',endpoint,db:String(db),
      fetchedAt:new Date().toISOString(),status:'PROVISIONAL_UNTIL_BETA_DATAMINING',
      note:'Current Wowhead Forever calculator dataset; refreshed independently of legacy Classic calibration.'
    },
    summary:{trees:Object.keys(data.trees||{}).length,totalNodes},
    data
  };
}
function fetchForeverTalents(cb){
  const maxAge=6*60*60*1000;
  if(foreverTalentCache.payload&&Date.now()-foreverTalentCache.fetchedAt<maxAge)return cb(null,foreverTalentCache.payload);
  if(foreverTalentCache.loading){foreverTalentCache.waiters.push(cb);return;}
  foreverTalentCache.loading=true;foreverTalentCache.waiters.push(cb);
  fetchRemote('https://www.wowhead.com/forever/talent-calc/rogue',3,(err,htmlBuf)=>{
    if(err)return finish(err);
    const html=htmlBuf.toString('utf8');
    const match=html.match(/https:\/\/nether\.wowhead\.com\/forever\/data\/talents-classic\?dv=20(?:&amp;|&)db=(\d+)/i);
    const db=match?.[1]||'1789642865';
    const endpoint='https://nether.wowhead.com/forever/data/talents-classic?dv=20&db='+db;
    fetchRemote(endpoint,3,(err2,jsBuf)=>{
      if(err2)return finish(err2);
      try{
        const payload=parseForeverTalentJs(jsBuf.toString('utf8'),db);
        foreverTalentCache.payload=payload;foreverTalentCache.fetchedAt=Date.now();finish(null,payload);
      }catch(e){finish(e);}
    });
  });
  function finish(err,payload){
    const list=foreverTalentCache.waiters.splice(0);foreverTalentCache.loading=false;
    for(const fn of list)fn(err,payload);
  }
}

const server=http.createServer((req,res)=>{
  let pathname;
  try{pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);}
  catch{res.writeHead(400).end('Bad request');return;}

  if(pathname==='/health')return sendJson(res,200,{ok:true,ruleset:'Forever',talentCache:!!foreverTalentCache.payload});
  if(pathname==='/api/forever-talents'){
    return fetchForeverTalents((err,payload)=>err
      ?sendJson(res,502,{error:'FOREVER_TALENTS_FETCH_FAILED',message:String(err?.message||err)})
      :sendJson(res,200,payload));
  }

  if(pathname==='/')pathname='/index.html';
  const filePath=path.resolve(root,'.'+pathname);
  if(!filePath.startsWith(root+path.sep)&&filePath!==path.join(root,'index.html')){res.writeHead(403).end('Forbidden');return;}
  fs.stat(filePath,(err,stat)=>{
    if(err||!stat.isFile()){res.writeHead(404,{'content-type':'text/plain; charset=utf-8'}).end('Not found');return;}
    const ext=path.extname(filePath).toLowerCase();
    const cache=ext==='.html'?'no-store':(ext==='.js'||ext==='.css'?'public, max-age=60':'public, max-age=300');
    res.writeHead(200,{'content-type':mime[ext]||'application/octet-stream','cache-control':cache});
    fs.createReadStream(filePath).pipe(res);
  });
});
server.listen(port,'0.0.0.0',()=>{
  console.log(`WoW Forever PvP Simulator preview listening on ${port}`);
  fetchForeverTalents((e,p)=>console.log(e
    ?'FOREVER_TALENTS_WARM_FAILED '+e.message
    :`FOREVER_TALENTS_READY trees=${p.summary.trees} nodes=${p.summary.totalNodes} db=${p.provenance.db}`));
});