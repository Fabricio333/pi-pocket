import {build} from '../bridge/node_modules/esbuild/lib/main.js';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('..',import.meta.url));
await build({entryPoints:[root+'bridge/sky-bridge.mjs'],bundle:true,platform:'node',target:'node22',format:'esm',
 external:['bufferutil','utf-8-validate'],banner:{js:'import { createRequire } from "node:module"; const require = createRequire(import.meta.url);'},
 legalComments:'eof',outfile:root+'bridge/dist/sky-bridge.mjs'});
console.log('Built optional Sky bridge.');
