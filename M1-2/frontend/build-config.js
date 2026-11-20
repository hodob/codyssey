// Vercel 빌드 시 실행: API_BASE_URL 환경변수를 config.js 에 기록
const fs = require("fs");
const url = (process.env.API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
fs.writeFileSync(__dirname + "/config.js", `window.API_BASE_URL = ${JSON.stringify(url)};\n`);
console.log("config.js written:", url);
