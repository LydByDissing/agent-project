# SDD Learn app

Local server and SPA that teach the operator while agents work.

    node learn-app/server.js --project <dir>   # http://127.0.0.1:${SDD_LEARN_PORT:-4747}

Only `node` is needed at runtime: `server.js` is a bundle and `dist/` is committed.

Development:

    npm install
    npm test
    npm run build   # rebuilds dist/ and server.js; commit the output
