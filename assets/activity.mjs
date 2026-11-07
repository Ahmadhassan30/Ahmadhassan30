// Renders assets/activity-{light,dark}.svg with Apache ECharts (server-side, SVG, animated).
//
//   npm install --no-save --no-package-lock echarts@6.1.0
//   GITHUB_TOKEN=$(gh auth token) node assets/activity.mjs
//
// The workflow (.github/workflows/activity.yml) runs this every 6 hours and commits the SVGs when they change.

import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as echarts from 'echarts';

const USER = 'Ahmadhassan30';
const OUT = process.env.ASSETS_DIR || dirname(fileURLToPath(import.meta.url));
const W = 1000, H = 432;
const FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif";

const THEMES = {
  light: { ink: '#1f2328', muted: '#59636e', faint: '#d1d9e0', line: '#1a7f37', glow: 'rgba(26,127,55,.28)',
    cells: ['#ebedf0', '#9be9a8', '#40c463', '#30a14e', '#216e39'] },
  dark: { ink: '#f0f6fc', muted: '#9198a1', faint: '#3d444d', line: '#3fb950', glow: 'rgba(63,185,80,.30)',
    cells: ['#161b22', '#0e4429', '#006d32', '#26a641', '#39d353'] },
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

function option(s, t) {
  const [e1, e2, e3] = s.edges;
  const pieces = [
    { value: 0, color: t.cells[0] },
    { min: 1, max: e1, color: t.cells[1] },
    { min: e1 + 1, max: e2, color: t.cells[2] },
    { min: e2 + 1, max: e3, color: t.cells[3] },
    { min: e3 + 1, color: t.cells[4] },
  ];
  const legendX = W - 22 - 5 * 15 - 34;   // leaves room for the word 'More'
  return {
    animationDuration: 1600,
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
        { type: 'text', right: 22 + (2 - i) * 170, top: 14, style: { text: value, fill: t.ink, font: `600 20px ${FONT}`, align: 'right' } },
        { type: 'text', right: 22 + (2 - i) * 170, top: 42, style: { text: label, fill: t.muted, font: `400 13px ${FONT}`, align: 'right' } },
      ]),
      { type: 'circle', left: 22, top: H - 21, shape: { r: 4 }, style: { fill: t.line } },
      { type: 'text', left: 36, top: H - 22, style: { text: `live from the GitHub API · updated ${s.updated}`, fill: t.muted, font: `400 11px ${FONT}` } },
      { type: 'text', left: legendX - 34, top: H - 22, style: { text: 'Less', fill: t.muted, font: `400 11px ${FONT}` } },
      ...t.cells.map((c, i) => ({ type: 'rect', left: legendX + i * 15, top: H - 23, shape: { width: 11, height: 11, r: 2.5 }, style: { fill: c } })),
      { type: 'text', left: legendX + 5 * 15 + 4, top: H - 22, style: { text: 'More', fill: t.muted, font: `400 11px ${FONT}` } },
    ],
    grid: { left: 52, right: 22, top: 100, height: 150 },   // same columns as the calendar below
    xAxis: {
      type: 'time', boundaryGap: false,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value', splitNumber: 3, axisLabel: { show: false },
      splitLine: { lineStyle: { color: t.faint, type: [3, 4], opacity: .7 } },
    },
    visualMap: { show: false, type: 'piecewise', seriesIndex: 1, pieces },
    calendar: {
      left: 52, right: 22, top: 284, cellSize: ['auto', 15],
      range: [s.days[0][0], s.days[s.days.length - 1][0]],
      splitLine: { show: false },
      itemStyle: { color: 'transparent', borderWidth: 3, borderColor: 'transparent' },
      yearLabel: { show: false },
      monthLabel: { color: t.muted, fontSize: 11, margin: 8 },
      dayLabel: { color: t.muted, fontSize: 10, firstDay: 0, nameMap: ['', 'Mon', '', 'Wed', '', 'Fri', ''], margin: 10 },
    },
    series: [
      {
        type: 'line', data: s.weeks, smooth: .45, showSymbol: false, z: 3,
        lineStyle: { width: 2.6, color: t.line, shadowColor: t.glow, shadowBlur: 12, shadowOffsetY: 6 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: t.glow }, { offset: 1, color: 'rgba(0,0,0,0)' }]) },
        markPoint: {
          symbol: 'circle', symbolSize: 9, data: [{ coord: s.peak, value: s.peak[1] }],
          itemStyle: { color: t.line, borderColor: t.cells[0] === '#161b22' ? '#0d1117' : '#ffffff', borderWidth: 2 },
          label: { show: true, position: 'top', distance: 8, color: t.ink, fontSize: 12, fontWeight: 600,
            formatter: `busiest week · ${s.peak[1]}` },
        },
      },
      {
        type: 'heatmap', coordinateSystem: 'calendar', data: s.days,
        itemStyle: { borderRadius: 3, borderColor: 'transparent', borderWidth: 2 },
      },
    ],
  };
}

const s = stats(await calendar());
for (const [name, t] of Object.entries(THEMES)) {
  const chart = echarts.init(null, null, { renderer: 'svg', ssr: true, width: W, height: H });
  chart.setOption(option(s, t));
  const svg = chart.renderToSVGString();
  writeFileSync(join(OUT, `activity-${name}.svg`), svg);
  chart.dispose();
  console.log(`activity-${name}.svg  ${(svg.length / 1024).toFixed(0)} KB`);
}
