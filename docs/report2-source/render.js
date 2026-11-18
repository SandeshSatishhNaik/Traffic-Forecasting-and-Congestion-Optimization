const { chromium } = require('/opt/node22/lib/node_modules/playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto('file://' + process.argv[2]);
  await p.pdf({
    path: process.argv[3], format: 'A4', printBackground: true,
    margin: { top: '27mm', bottom: '22mm', left: '25mm', right: '25mm' },
    displayHeaderFooter: true,
    headerTemplate: `<div style="width:100%;box-sizing:border-box;padding:0 25mm;font-family:'Liberation Serif','Times New Roman',serif;font-size:10pt;font-weight:bold;text-align:right"><div style="border-bottom:2px solid #632523;padding-bottom:3px">Traffic Intelligence System</div></div>`,
    footerTemplate: `<div style="width:100%;box-sizing:border-box;padding:0 25mm;font-family:'Liberation Serif','Times New Roman',serif;font-size:10pt;text-align:right"><span class="pageNumber"></span></div>`
  });
  await b.close();
})();
