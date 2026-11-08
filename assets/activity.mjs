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

// Idle stretches (a week or more with no contributions) are cut out of the time axis with ECharts axis breaks,
// the way an intraday chart drops the hours a market is closed. Active periods get the room.
const DAY = 864e5;
const IDLE = 7;

function series(s) {
  const pts = [], breaks = [];
  let i = 0;
  while (i < s.days.length) {
    let j = i;
    while (j < s.days.length && s.days[j][1] === 0) j++;
    const run = j - i;
    if (run >= IDLE && i > 0 && j < s.days.length) {
      const start = Date.parse(s.days[i][0] + 'T00:00:00Z'), end = Date.parse(s.days[j - 1][0] + 'T00:00:00Z');
      pts.push([start - DAY / 2, NaN]);                     // lift the pen across the break
      breaks.push({ start, end, gap: '1.2%' });
      i = j;
    } else {
      for (let k = i; k < Math.max(j, i + 1) && k < s.days.length; k++) pts.push([Date.parse(s.days[k][0] + 'T00:00:00Z'), s.days[k][1]]);
      i = Math.max(j, i + 1);
    }
  }
  return { pts, breaks };
}

function option(s, t) {
  const { pts, breaks } = series(s);
  const fmt = echarts.time.format;
  const bg = t.cells[0] === '#161b22' ? '#0d1117' : '#ffffff';
  const idleDays = breaks.reduce((n, b) => n + Math.round((b.end - b.start) / DAY) + 1, 0);
  return {
    useUTC: true,
    animation: false,   // SSR clip animation truncates lines when the axis has breaks
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
      { type: 'text', right: 22, top: H - 22, style: { text: `${breaks.length} idle stretches (${idleDays} days) folded out of the axis`, fill: t.muted, font: `400 11px ${FONT}`, align: 'right' } },
    ],
    grid: { left: 52, right: 22, top: 104, height: 196 },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: t.faint } }, axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: {
        color: t.muted, fontSize: 11, showMinLabel: true, showMaxLabel: true, hideOverlap: true,
        formatter: (ts, _, opt) => (opt && opt.break ? fmt(ts, '{MMM}\n{weak|{d}}', true) : fmt(ts, '{MMM}', true)),
        rich: { weak: { color: t.faint, fontSize: 10 } },
      },
      breaks,
      breakArea: { expandOnClick: false, zigzagAmplitude: 0, zigzagZ: 200, itemStyle: { borderColor: 'none', opacity: 0 } },
    },
    yAxis: {
      type: 'value', min: 0, splitNumber: 3,
      axisLabel: { color: t.muted, fontSize: 10, margin: 10 },
      splitLine: { lineStyle: { color: t.faint, type: [3, 4], opacity: .7 } },
    },
    dataZoom: [{
      type: 'slider', left: 52, right: 22, top: 336, height: 34, start: 0, end: 100,
      borderColor: t.faint, backgroundColor: 'transparent', fillerColor: t.glow.replace(/[\d.]+\)$/, '.10)'),
      handleStyle: { color: t.line, borderColor: t.line }, moveHandleStyle: { color: t.faint, opacity: .6 },
      textStyle: { color: t.muted, fontSize: 10 }, labelFormatter: () => '',
      dataBackground: { lineStyle: { color: t.line, opacity: .7, width: 1 }, areaStyle: { color: t.line, opacity: .18 } },
      selectedDataBackground: { lineStyle: { color: t.line, width: 1 }, areaStyle: { color: t.line, opacity: .28 } },
      brushSelect: false,
    }],
    series: [{
      type: 'line', data: pts, showSymbol: false, symbolSize: 0, connectNulls: false, z: 3,
      lineStyle: { width: 1.8, color: t.line, shadowColor: t.glow, shadowBlur: 10, shadowOffsetY: 4 },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: t.glow }, { offset: 1, color: 'rgba(0,0,0,0)' }]) },
      markPoint: {
        symbol: 'circle', symbolSize: 9,
        data: [{ coord: [Date.parse(s.best[0] + 'T00:00:00Z'), s.best[1]], value: s.best[1] }],
        itemStyle: { color: t.line, borderColor: bg, borderWidth: 2 },
        label: { show: true, position: 'top', distance: 8, color: t.ink, fontSize: 12, fontWeight: 600,
          formatter: `busiest day · ${s.best[1]}` },
      },
    }],
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
