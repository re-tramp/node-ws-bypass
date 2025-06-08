const express = require('express');

const { connect } = require('net');

const { Server, createWebSocketStream } = require('ws');

const server = 'bexnxx.nyc.mn'

const app = express();


const uuidv4 = () => 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c =>

  ((Math.random() * 16) | 0).toString(16)

);


function run(config) {

  if (!config.port) {

    console.error('port?')

    return

  }

  app.get('*', (req, res) => {

    //res.setHeader('Content-Type', 'text/plain');
    res.redirect(`https://newsnow.busiyi.world/`);

//     res.send(`TLS: vless://${config.uuid ? config.uuid : uuidv4()}@${server}:443?encryption=none&security=tls&sni=${server}&fp=randomized&type=ws&host=${server}&path=${encodeURIComponent('/' + btoa(`${req.protocol}://${req.headers.host}${config.path ? config.path : "/"}`))}#vless+ws+tls


// NONTLS: vless://${config.uuid ? config.uuid : uuidv4()}@${server}:80?path=${encodeURIComponent('/' + btoa(`${req.protocol}://${req.headers.host}${config.path ? config.path : "/"}`))}&security=none&encryption=none&host=${server}&fp=randomized&type=ws&sni=${server}#vless+ws+nontls`);

  });


  const httpServer = app.listen(config.port, () => {

    console.log(`Server running on http://localhost:${config.port}`);

  });

  const wss = new Server({ noServer: true, path: config.path || null });


  wss.on('connection', (ws) => {

    ws.once('message', (msg) => {

      const [version] = msg;

      const id = msg.subarray(1, 17).toString('hex');

      if (config.uuid && (id !== config.uuid.replace(/-/g, ''))) return;

      let offset = msg.readUInt8(17) + 19;

      const targetPort = msg.readUInt16BE(offset);

      offset += 2;

      const addressType = msg.readUInt8(offset++);

      const getHost = {

        1: () => Array.from(msg.subarray(offset, offset += 4)).join('.'),

        2: () => new TextDecoder().decode(msg.subarray(offset + 1, offset += 1 + msg[offset])),

        3: () => Array.from(msg.subarray(offset, offset += 16))
          .map((b, i, arr) => (i % 2 ? arr.slice(i - 1, i + 1) : [])
            .map(x => x.readUInt16BE(0).toString(16)).join(':')).filter(Boolean).join(':'),

      };

      const targetHost = getHost[addressType] ? getHost[addressType]() : '';

      ws.send(Uint8Array.of(version, 0));

      const duplex = createWebSocketStream(ws);

      connect({ host: targetHost, port: targetPort }, function () {

        this.write(msg.subarray(offset));

        duplex.pipe(this).pipe(duplex);

      }).on('error', () => { });

    });

  });

  httpServer.on('upgrade', (request, socket, head) => {

    if (request.headers.upgrade.toLowerCase() !== 'websocket') {

      socket.end('HTTP/1.1 400 Bad Request');

      return;

    }

    wss.handleUpgrade(request, socket, head, (ws) => {

      wss.emit('connection', ws, request);

    });

  });

}


process.on('uncaughtException', error => { console.log(error) });

process.on('unhandledRejection', error => { console.log(error) });


run({
  port: 8080,
  uuid: 'f65c45c4-08c0-49f4-a2bf-aed46e0c008a',
})