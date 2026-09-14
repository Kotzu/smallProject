const http = require('http');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname);
const port = Number(process.env.PORT || 10000);

const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon'
};

http.createServer((req, res) => {
  let pathname;
  try { pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname); }
  catch { res.writeHead(400).end('Bad request'); return; }

  if (pathname === '/') pathname = '/index.html';
  const filePath = path.resolve(root, '.' + pathname);
  if (!filePath.startsWith(root + path.sep) && filePath !== path.join(root, 'index.html')) { res.writeHead(403).end('Forbidden'); return; }

  fs.stat(filePath, (err, stat) => {
    if (err || !stat.isFile()) { res.writeHead(404, {'content-type': 'text/plain; charset=utf-8'}).end('Not found'); return; }
    const ext = path.extname(filePath).toLowerCase();
    const headers = {'content-type': mime[ext] || 'application/octet-stream','cache-control': ext === '.html' ? 'no-store' : 'public, max-age=60'};
    if (ext === '.html') {
      fs.readFile(filePath, 'utf8', (readErr, html) => {
        if (readErr) { res.writeHead(500).end('Read error'); return; }
        if (!html.includes('talent-bootstrap.js')) html = html.replace('</body>','<script src="talent-bootstrap.js?v=016"></script></body>');
        res.writeHead(200, headers).end(html);
      });
      return;
    }
    res.writeHead(200, headers);fs.createReadStream(filePath).pipe(res);
  });
}).listen(port, '0.0.0.0', () => console.log(`WoW PvP Simulator preview listening on ${port}`));
