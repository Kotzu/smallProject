const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const {runTraining, runVariant, runDuel} = require('./headless-runner');

const root = path.resolve(__dirname);
const port = Number(process.env.PORT || 10000);
const mime = {'.html':'text/html; charset=utf-8','.js':'application/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.lua':'text/plain; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.ico':'image/x-icon'};
const vendorCache = new Map();
let trainingCache={status:'pending',stage:'screen',screenCount:100,validationCount:1000,seed:1337};
let foreverTalentCache={payload:null,fetchedAt:0,loading:false,waiters:[]};

function fetchRemote(url, redirects, cb) {
  if (redirects < 0) return cb(new Error('too many redirects'));
  const request = https.get(url, {headers:{'user-agent':'wow-pvp-simulator-preview'}}, r => {
    if (r.statusCode >= 300 && r.statusCode < 400 && r.headers.location) {r.resume();return fetchRemote(new URL(r.headers.location,url).toString(),redirects-1,cb);}
    if (r.statusCode !== 200) {r.resume();return cb(new Error('upstream HTTP '+r.statusCode));}
    const chunks=[];r.on('data',c=>chunks.push(c));r.on('end',()=>cb(null,Buffer.concat(chunks)));
  });
  request.setTimeout(12000,()=>request.destroy(new Error('upstream timeout')));request.on('error',cb);
}
function sendJson(res,status,value){const body=JSON.stringify(value);res.writeHead(status,{'content-type':'application/json; charset=utf-8','cache-control':'no-store','content-length':Buffer.byteLength(body)});res.end(body);}

function extractJsonObject(text,fromIndex){
  const start=text.indexOf('{',fromIndex);if(start<0)throw new Error('Forever talent JSON object not found');
  let depth=0,inString=false,escaped=false;
  for(let i=start;i<text.length;i++){
    const ch=text[i];
    if(inString){
      if(escaped){escaped=false;continue;}
      if(ch==='\\\\'){escaped=true;continue;}
      if(ch==='"')inString=false;
      continue;
    }
    if(ch==='"'){inString=true;continue;}
    if(ch==='{')depth++;
    else if(ch==='}'){depth--;if(depth===0)return text.slice(start,i+1);}
  }
  throw new Error('Forever talent JSON object is incomplete');
}
function parseForeverTalentJs(text,db){
  const prefix='WH.setPageData("wow.talentCalcClassic.classicplus.data",';
  const start=text.indexOf(prefix);if(start<0)throw new Error('Forever talent payload marker not found');
  const json=extractJsonObject(text,start+prefix.length);
  const data=JSON.parse(json);
  let totalNodes=0;for(const tree of Object.values(data.talents||{}))totalNodes+=Object.keys(tree||{}).length;
  return {provenance:{source:'Wowhead Forever',calculator:'https://www.wowhead.com/forever/talent-calc',endpoint:`https://nether.wowhead.com/forever/data/talents-classic?dv=20&db=${db}`,db:String(db),fetchedAt:new Date().toISOString(),status:'PROVISIONAL_UNTIL_BETA_DATAMINING',note:'Exact current Wowhead Forever calculator dataset; values may be refreshed after beta datamining.'},summary:{trees:Object.keys(data.trees||{}).length,totalNodes},data};
}
function fetchForeverTalents(cb){
  const maxAge=6*60*60*1000;if(foreverTalentCache.payload&&Date.now()-foreverTalentCache.fetchedAt<maxAge)return cb(null,foreverTalentCache.payload);
  if(foreverTalentCache.loading){foreverTalentCache.waiters.push(cb);return;}
  foreverTalentCache.loading=true;foreverTalentCache.waiters.push(cb);
  fetchRemote('https://www.wowhead.com/forever/talent-calc/rogue',3,(err,htmlBuf)=>{
    if(err)return finish(err);
    const html=htmlBuf.toString('utf8');
    const match=html.match(/https:\/\/nether\.wowhead\.com\/forever\/data\/talents-classic\?dv=20(?:&amp;|&)db=(\d+)/i);
    const db=match?.[1]||'1789642865';
    const endpoint=`https://nether.wowhead.com/forever/data/talents-classic?dv=20&db=${db}`;
    fetchRemote(endpoint,3,(err2,jsBuf)=>{
      if(err2)return finish(err2);
      try{const payload=parseForeverTalentJs(jsBuf.toString('utf8'),db);foreverTalentCache.payload=payload;foreverTalentCache.fetchedAt=Date.now();finish(null,payload);}catch(e){finish(e);}
    });
  });
  function finish(err,payload){const list=foreverTalentCache.waiters.splice(0);foreverTalentCache.loading=false;for(const fn of list)fn(err,payload);}
}

function computeDefaultTraining(){
  const started=Date.now();
  try{
    const screen=runTraining(100,1337);
    const bestIndex=screen.best?.index ?? 0;
    trainingCache={status:'validating',stage:'validate-best',screen,seed:1337,bestIndex,elapsedMs:Date.now()-started};
    console.log('ROGUE_SCREEN_READY '+JSON.stringify({deterministic:screen.deterministic,best:screen.best,elapsedMs:trainingCache.elapsedMs}));
    setTimeout(()=>{
      const vStarted=Date.now();
      try{
        const validation=runVariant(bestIndex,1000,1337);
        trainingCache={status:'ready',stage:'complete',screen,validation,seed:1337,elapsedMs:(Date.now()-started),scope:'Rogue CB/Hemo vs Frost Mage; paired seeds; decision-policy only'};
        console.log('ROGUE_VALIDATION_READY '+JSON.stringify({deterministic:validation.deterministic,result:validation.result,elapsedMs:Date.now()-vStarted,totalElapsedMs:trainingCache.elapsedMs}));
      }catch(err){trainingCache={status:'error',stage:'validation',screen,message:String(err?.stack||err)};console.error('ROGUE_VALIDATION_FAILED '+trainingCache.message);}
    },50);
  }catch(err){trainingCache={status:'error',stage:'screen',message:String(err?.stack||err),elapsedMs:Date.now()-started};console.error('ROGUE_SCREEN_FAILED '+trainingCache.message);}
}

const server=http.createServer((req,res)=>{
  let parsed,pathname;try{parsed=new URL(req.url,'http://localhost');pathname=decodeURIComponent(parsed.pathname);}catch{res.writeHead(400).end('Bad request');return;}
  if(pathname==='/api/forever-talents')return fetchForeverTalents((err,payload)=>err?sendJson(res,502,{error:'FOREVER_TALENTS_FETCH_FAILED',message:String(err?.message||err)}):sendJson(res,200,payload));
  if(pathname==='/api/rogue-training-status')return sendJson(res,200,trainingCache);
  if(pathname==='/api/rogue-variant'){
    try{const index=Math.max(0,Math.min(7,Math.trunc(Number(parsed.searchParams.get('index'))||0))),count=Math.max(100,Math.min(2500,Math.trunc(Number(parsed.searchParams.get('count'))||1000))),seed=(Number(parsed.searchParams.get('seed'))||1337)>>>0;return sendJson(res,200,runVariant(index,count,seed));}
    catch(err){return sendJson(res,500,{error:'VARIANT_FAILED',message:String(err?.stack||err)});}
  }
  if(pathname==='/api/rogue-train'){
    try{const count=Math.max(50,Math.min(500,Math.trunc(Number(parsed.searchParams.get('count'))||100))),seed=(Number(parsed.searchParams.get('seed'))||1337)>>>0;return sendJson(res,200,runTraining(count,seed));}
    catch(err){return sendJson(res,500,{error:'TRAINING_FAILED',message:String(err?.stack||err)});}
  }
  if(pathname==='/api/duel'){
    try{const seed=(Number(parsed.searchParams.get('seed'))||1337)>>>0;return sendJson(res,200,runDuel(seed));}
    catch(err){return sendJson(res,500,{error:'DUEL_FAILED',message:String(err?.stack||err)});}
  }
  if(pathname==='/vendor/fengari-web.js'){
    const key='fengari-web-0.1.4',cached=vendorCache.get(key);if(cached){res.writeHead(200,{'content-type':'application/javascript; charset=utf-8','cache-control':'public, max-age=86400'});res.end(cached);return;}
    fetchRemote('https://cdn.jsdelivr.net/npm/fengari-web@0.1.4/dist/fengari-web.js',3,(err,body)=>{if(err){res.writeHead(502,{'content-type':'text/plain; charset=utf-8'}).end('Vendor fetch failed: '+err.message);return;}vendorCache.set(key,body);res.writeHead(200,{'content-type':'application/javascript; charset=utf-8','cache-control':'public, max-age=86400'});res.end(body);});return;
  }
  if(pathname==='/')pathname='/index.html';
  if(pathname==='/index.html'){
    const indexPath=path.join(root,'index.html');
    fs.readFile(indexPath,'utf8',(err,html)=>{
      if(err){res.writeHead(404,{'content-type':'text/plain; charset=utf-8'}).end('Not found');return;}
      let body=html;
      if(!body.includes('armory-talents.css'))body=body.replace('</head>','<link rel="stylesheet" href="armory-talents.css">\n</head>');\n      if(!body.includes('forever-armory.css'))body=body.replace('</head>','<link rel="stylesheet" href="forever-armory.css">\n</head>');
      const extras=[];
      if(!body.includes('forever-talents-runtime.js'))extras.push('<script src="forever-talents-runtime.js"></script>');
      if(!body.includes('forever-builds.js'))extras.push('<script src="forever-builds.js"></script>');
      if(!body.includes('armory-talent-tree.js'))extras.push('<script src="armory-talent-tree.js"></script>');
      if(!body.includes('forever-qa.js'))extras.push('<script src="forever-qa.js"></script>');
      if(!body.includes('armory-3d.js'))extras.push('<script src="armory-3d.js"></script>');
      if(extras.length)body=body.replace('</body>',extras.join('\n')+'\n</body>');
      res.writeHead(200,{'content-type':'text/html; charset=utf-8','cache-control':'no-store','content-length':Buffer.byteLength(body)});res.end(body);
    });
    return;
  }
  const filePath=path.resolve(root,'.'+pathname);if(!filePath.startsWith(root+path.sep)&&filePath!==path.join(root,'index.html')){res.writeHead(403).end('Forbidden');return;}
  fs.stat(filePath,(err,stat)=>{if(err||!stat.isFile()){res.writeHead(404,{'content-type':'text/plain; charset=utf-8'}).end('Not found');return;}const ext=path.extname(filePath).toLowerCase();res.writeHead(200,{'content-type':mime[ext]||'application/octet-stream','cache-control':ext==='.html'?'no-store':'public, max-age=30'});fs.createReadStream(filePath).pipe(res);});
});
server.listen(port,'0.0.0.0',()=>{console.log(`WoW Forever PvP Simulator preview listening on ${port}`);fetchForeverTalents((e,p)=>console.log(e?'FOREVER_TALENTS_WARM_FAILED '+e.message:`FOREVER_TALENTS_READY trees=${p.summary.trees} nodes=${p.summary.totalNodes} db=${p.provenance.db}`));setTimeout(computeDefaultTraining,750);});
