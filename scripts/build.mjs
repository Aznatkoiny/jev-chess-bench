import { access } from 'node:fs/promises';
for (const f of ['public/index.html','public/app.js','public/styles.css']) await access(f);
console.log('Static app and API source ready.');
