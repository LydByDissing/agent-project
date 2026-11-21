// [origin ref=llm-dsl-gu1y.3 req=REQ-OPERATOR-EDU-001,REQ-OPERATOR-EDU-002,REQ-OPERATOR-EDU-003 c4=learn_app/lesson_library]
//   [intent]Process entry for the bundled cli.js: runs the learn command on argv and sets the exit code.[/intent]
// [/origin]
import { runCli } from './cli.js';

const res = runCli(process.argv.slice(2));
for (const line of res.stdout) console.log(line);
for (const line of res.stderr) console.error(line);
process.exitCode = res.code;
