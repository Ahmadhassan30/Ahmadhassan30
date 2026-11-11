// Renders assets/activity-{light,dark}.svg with Apache ECharts (server-side, SVG, animated).
//
//   npm install --no-save --no-package-lock echarts@6.1.0
//   GITHUB_TOKEN=$(gh auth token) node assets/activity.mjs
//
// The workflow (.github/workflows/activity.yml) runs this every 6 hours and commits the SVGs when they change.

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as echarts from 'echarts';

const USER = 'Ahmadhassan30';
const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = process.env.ASSETS_DIR || HERE;
const W = 1000, H = 400;
// One typeface across the README: JetBrains Mono (SIL OFL 1.1, see assets/fonts/OFL.txt).
// GitHub's image proxy blocks web-font requests, so the subsets are embedded in each SVG.
const FONT = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
const FACES = [[400, 'jetbrains-mono-400.woff'], [600, 'jetbrains-mono-600.woff']]
  .map(([w, f]) => `@font-face{font-family:'JetBrains Mono';font-weight:${w};src:url(data:font/woff;base64,${
    readFileSync(join(HERE, 'fonts', f)).toString('base64')}) format('woff')}`).join('');
const withFonts = svg => svg.replace(/<svg\b[^>]*>/, m => `${m}<defs><style>${FACES}</style></defs>`);

const THEMES = {
  // same blues as the hero
  light: { ink: '#1f2328', muted: '#59636e', faint: '#d1d9e0', line: '#0969da', bg: '#ffffff',
    barTop: '#54aeff', barBot: '#b6e3ff', peakTop: '#0969da', peakBot: '#0550ae',
    areaTop: '#0969da', areaBot: 'rgba(84,174,255,.25)', zoomFill: 'rgba(9,105,218,.10)' },
  dark: { ink: '#f0f6fc', muted: '#9198a1', faint: '#3d444d', line: '#58a6ff', bg: '#0d1117',
    barTop: '#1f6feb', barBot: '#0c2d6b', peakTop: '#79c0ff', peakBot: '#1f6feb',
    areaTop: '#58a6ff', areaBot: 'rgba(31,111,235,.18)', zoomFill: 'rgba(88,166,255,.10)' },
};

async function calendar() {
  const token = process.env.GITHUB_TOKEN;
  if (!token) throw new Error('set GITHUB_TOKEN');
  const query = `query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{
    totalContributions weeks{contributionDays{date contributionCount}}}}}}`;
  const res = await fetch('https://api.github.com/graphql', {
    method: 'POST',
    headers: { Authorization: `bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, variables: { login: USER } }),
  });
  const json = await res.json();
  return json.data.user.contributionsCollection.contributionCalendar;
}

function stats(cal) {
  const days = cal.weeks.flatMap(w => w.contributionDays.map(d => [d.date, d.contributionCount]));
  const weeks = cal.weeks.map(w => [w.contributionDays[0].date, w.contributionDays.reduce((s, d) => s + d.contributionCount, 0)]);
  let longest = 0, run = 0;
  for (const [, n] of days) { run = n ? run + 1 : 0; longest = Math.max(longest, run); }
  const active = days.filter(([, n]) => n).length;
  const best = days.reduce((a, b) => (b[1] > a[1] ? b : a));
  const peak = weeks.reduce((a, b) => (b[1] > a[1] ? b : a));
  // bucket edges from the spread of active days, so the colours mean something for this year
  const counts = days.map(([, n]) => n).filter(Boolean).sort((a, b) => a - b);
  const q = p => counts[Math.min(counts.length - 1, Math.floor(p * counts.length))] || 1;
  const edges = [q(.25), q(.5), q(.8)];
  const updated = new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
  return { days, weeks, total: cal.totalContributions, longest, active, best, peak, edges, updated };
}

const fmtDay = d => new Date(d + 'T00:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' });

// Monthly view: one bar per month, the count on top, the strongest month emphasised, the average as a quiet reference line.
function months(s) {
  const by = new Map();
  for (const [d, n] of s.days) by.set(d.slice(0, 7), (by.get(d.slice(0, 7)) || 0) + n);
  return [...by.entries()].map(([ym, n]) => {
    const dt = new Date(ym + '-01T00:00:00Z');
    const m = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][dt.getUTCMonth()];
    return [dt.getUTCMonth() === 0 || ym === [...by.keys()][0] ? `${m} ’${String(dt.getUTCFullYear()).slice(2)}` : m, n];
  });
}

function option(s, t) {
  // rolling 7-day total for every day: the year as one continuous terrain
  // only days with a full 7-day window behind them, so no point is undercounted
  const full = s.days.slice(6);
  const dates = full.map(d => d[0]);
  const roll = full.map((_, k) => s.days.slice(k, k + 7).reduce((x, d) => x + d[1], 0));
  const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  // every month's peak: the highest rolling value inside each calendar month
  // every month's true peak (highest rolling value in that calendar month); when two labels would sit
  // within 10 days of each other, the later one is lifted so both stay readable. Values are never moved.
  const byMonth = new Map();
  dates.forEach((d, i) => { const m = d.slice(0, 7); if (!byMonth.has(m)) byMonth.set(m, []); byMonth.get(m).push(i); });
  const peaks = [...byMonth.values()]
    .map(ix => ix.reduce((x, y) => (roll[y] > roll[x] ? y : x)))
    .filter(i => roll[i] > 0);
  const lift = peaks.map((i, k) => (k > 0 && i - peaks[k - 1] < 10 ? 16 : 0));
  return {
    animationDuration: 1200,
    animationEasing: 'cubicOut',
    textStyle: { fontFamily: FONT },
    graphic: [
      { type: 'text', left: 22, top: 6, style: { text: s.total.toLocaleString('en-US'), fill: t.ink, font: `600 44px ${FONT}` } },
      { type: 'text', left: 22, top: 60, style: { text: 'contributions in the last year', fill: t.muted, font: `400 15px ${FONT}` } },
      ...[
        ['longest streak', `${s.longest} days`],
        ['active days', `${s.active} / ${s.days.length}`],
        ['best day', `${s.best[1]} · ${fmtDay(s.best[0])}`],
      ].flatMap(([label, value], i) => [
        // anchored by x (text-anchor: end) rather than `right`, so layout never depends on ECharts' width estimate
        { type: 'text', x: W - 22 - (2 - i) * 170, y: 14, style: { text: value, fill: t.ink, font: `600 20px ${FONT}`, align: 'right' } },
        { type: 'text', x: W - 22 - (2 - i) * 170, y: 42, style: { text: label, fill: t.muted, font: `400 13px ${FONT}`, align: 'right' } },
      ]),
    ],
    grid: { left: 46, right: 22, top: 124, height: 200 },
    xAxis: {
      type: 'category', data: dates, boundaryGap: false,
      axisLine: { lineStyle: { color: t.faint } }, axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 11, margin: 10,
        interval: (i, v) => v.endsWith('-01'), formatter: v => MON[+v.slice(5, 7) - 1] },
    },
    yAxis: {
      type: 'value', boundaryGap: [0, '12%'], splitNumber: 3,
      axisLabel: { color: t.muted, fontSize: 10 },
      splitLine: { lineStyle: { color: t.faint, type: [3, 4], opacity: .6 } },
    },
    dataZoom: [{
      type: 'slider', start: 0, end: 100, left: 46, right: 22, top: 354, height: 28,
      borderColor: t.faint, backgroundColor: 'transparent', fillerColor: t.zoomFill,
      handleStyle: { color: t.line, borderColor: t.line }, moveHandleStyle: { color: t.faint, opacity: .6 },
      labelFormatter: () => '', brushSelect: false,
      dataBackground: { lineStyle: { color: t.line, width: 1, opacity: .8 }, areaStyle: { color: t.line, opacity: .2 } },
      selectedDataBackground: { lineStyle: { color: t.line, width: 1 }, areaStyle: { color: t.line, opacity: .3 } },
    }],
    series: [{
      type: 'line', data: roll, symbol: 'none', sampling: 'lttb', smooth: .25,
      animation: false,   // ECharts' SSR clip animation leaves lines undrawn in a static image
      itemStyle: { color: t.line },
      lineStyle: { width: 1.6, color: t.line },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: t.areaTop }, { offset: 1, color: t.areaBot }]) },
      markPoint: {
        symbol: 'circle', symbolSize: 6, animation: false,
        itemStyle: { color: t.line, borderColor: t.bg, borderWidth: 1.5 },
        label: { show: true, position: 'top', distance: 6, color: t.ink, fontSize: 11, fontWeight: 600 },
        data: peaks.map((i, k) => ({ coord: [dates[i], roll[i]], value: roll[i], label: { offset: [0, -lift[k]] } })),
      },
    }],
  };
}

const s = stats(await calendar());
for (const [name, t] of Object.entries(THEMES)) {
  const chart = echarts.init(null, null, { renderer: 'svg', ssr: true, width: W, height: H });
  chart.setOption(option(s, t));
  const svg = withFonts(chart.renderToSVGString());
  writeFileSync(join(OUT, `activity-${name}.svg`), svg);
  chart.dispose();
  console.log(`activity-${name}.svg  ${(svg.length / 1024).toFixed(0)} KB`);
}
