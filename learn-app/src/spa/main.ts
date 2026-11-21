// [origin ref=llm-dsl-gu1y.1 req=REQ-OPERATOR-EDU-011 c4=learn_app/learn_spa]
//   [intent]SPA entry: loads PoC styling and mounts the empty shell with its wave strip.[/intent]
// [/origin]
import './style.css';

const app = document.getElementById('app');
if (app) app.textContent = 'Loading lessons...';
