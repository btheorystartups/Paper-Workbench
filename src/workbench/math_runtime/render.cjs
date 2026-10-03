// Offline TeX-to-vector-math worker. No user JavaScript, HTML or extensions run.
const {mathjax} = require('mathjax-full/js/mathjax.js');
const {TeX} = require('mathjax-full/js/input/tex.js');
const {SVG} = require('mathjax-full/js/output/svg.js');
const {liteAdaptor} = require('mathjax-full/js/adaptors/liteAdaptor.js');
const {RegisterHTMLHandler} = require('mathjax-full/js/handlers/html.js');
require('mathjax-full/js/input/tex/ams/AmsConfiguration.js');
const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const document = mathjax.document('', {
  InputJax: new TeX({packages: ['base', 'ams'], maxBuffer: 20000, maxMacros: 1000}),
  OutputJax: new SVG({fontCache: 'none'})
});
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  input += chunk;
  if (input.length > 1000000) process.exit(2);
});
process.stdin.on('end', () => {
  try {
    const formulas = JSON.parse(input);
    const output = formulas.map(item => {
      const node = document.convert(item.tex, {display: item.display});
      const svg = adaptor.outerHTML(adaptor.firstChild(node));
      if (svg.includes('data-mjx-error')) throw new Error('Unsupported equation');
      return svg;
    });
    process.stdout.write(JSON.stringify(output));
  } catch (_) { process.stderr.write('Math typesetting failed.'); process.exitCode = 2; }
});
