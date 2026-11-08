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
  const ms = months(s);
  const top = Math.max(...ms.map(m => m[1]));
  const avg = Math.round(s.total / ms.length);
  const dark = t.cells[0] === '#161b22';
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
        { type: 'text', right: 22 + (2 - i) * 170, top: 14, style: { text: value, fill: t.ink, font: `600 20px ${FONT}`, align: 'right' } },
        { type: 'text', right: 22 + (2 - i) * 170, top: 42, style: { text: label, fill: t.muted, font: `400 13px ${FONT}`, align: 'right' } },
      ]),
      { type: 'circle', left: 22, top: H - 21, shape: { r: 4 }, style: { fill: t.line } },
      { type: 'text', left: 36, top: H - 22, style: { text: `live from the GitHub API · updated ${s.updated}`, fill: t.muted, font: `400 11px ${FONT}` } },
      { type: 'text', right: 22, top: H - 22, style: { text: 'contributions per month', fill: t.muted, font: `400 11px ${FONT}`, align: 'right' } },
    ],
    grid: { left: 22, right: 22, top: 128, bottom: 70 },
    xAxis: {
      type: 'category', data: ms.map(m => m[0]),
      axisLine: { lineStyle: { color: t.faint } }, axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 12, margin: 12 },
    },
    yAxis: { type: 'value', show: false, max: Math.ceil(top * 1.12) },
    series: [{
      type: 'bar', barWidth: '54%',
      data: ms.map(([, n]) => ({
        value: n,
        itemStyle: {
          borderRadius: [5, 5, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, n === top
            ? [{ offset: 0, color: t.line }, { offset: 1, color: t.cells[3] }]
            : [{ offset: 0, color: t.cells[2] }, { offset: 1, color: dark ? t.cells[1] : t.cells[1] }]),
        },
        label: { show: true, position: 'top', distance: 6, color: n === top ? t.ink : t.muted,
          fontSize: n === top ? 13 : 12, fontWeight: n === top ? 600 : 400, formatter: n ? String(n) : '–' },
      })),
      markLine: {
        silent: true, symbol: 'none',
        lineStyle: { color: t.muted, type: [4, 4], width: 1, opacity: .55 },
        label: { position: 'insideEndTop', color: t.muted, fontSize: 11, formatter: `avg ${avg} / month` },
        data: [{ yAxis: avg }],
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
