/**
 * Minimal inline-SVG charts.
 *
 * Deliberately dependency-free: the legacy dashboard pulled Chart.js from a CDN
 * with no `integrity` attribute, so a compromised CDN owned the page. Rendering
 * locally lets the CSP stay at `script-src 'self'` with no third-party origin at
 * all, and keeps the page working offline.
 */

const SVG_NS = 'http://www.w3.org/2000/svg';

function el(name, attrs = {}) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, String(value));
  }
  return node;
}

function frame(host, width, height) {
  host.replaceChildren();
  const svg = el('svg', {
    viewBox: `0 0 ${width} ${height}`,
    preserveAspectRatio: 'none',
    width: '100%',
    height: '100%',
  });
  host.appendChild(svg);
  return svg;
}

function gridLines(svg, plot, ticks, formatter) {
  for (let i = 0; i <= ticks; i += 1) {
    const y = plot.top + (plot.height * i) / ticks;
    svg.appendChild(
      el('line', {
        x1: plot.left, x2: plot.left + plot.width, y1: y, y2: y,
        stroke: 'var(--border)', 'stroke-width': 1,
      }),
    );
    const label = el('text', {
      x: plot.left - 8, y: y + 4, 'text-anchor': 'end',
      fill: 'var(--muted)', 'font-size': 11,
    });
    label.textContent = formatter(1 - i / ticks);
    svg.appendChild(label);
  }
}

/** Vertical bar chart. `data` is `[{label, value}]`. */
export function barChart(host, data) {
  const width = 640;
  const height = 300;
  const plot = { left: 48, top: 16, width: width - 64, height: height - 56 };
  const svg = frame(host, width, height);
  if (!data.length) return;

  const max = Math.max(...data.map((d) => d.value)) || 1;
  gridLines(svg, plot, 4, (fraction) => Math.round(max * fraction).toString());

  const slot = plot.width / data.length;
  const barWidth = Math.min(46, slot * 0.62);

  data.forEach((point, index) => {
    const barHeight = (point.value / max) * plot.height;
    const x = plot.left + slot * index + (slot - barWidth) / 2;
    const y = plot.top + plot.height - barHeight;

    const rect = el('rect', {
      x, y, width: barWidth, height: Math.max(barHeight, 1),
      rx: 4, fill: 'var(--accent)', 'fill-opacity': 0.78,
    });
    const title = el('title');
    title.textContent = `${point.label}: ${point.value}`;
    rect.appendChild(title);
    svg.appendChild(rect);

    const label = el('text', {
      x: x + barWidth / 2, y: height - 18, 'text-anchor': 'middle',
      fill: 'var(--muted)', 'font-size': 11,
    });
    label.textContent = point.label;
    svg.appendChild(label);
  });
}

/** Line chart over an ordered series. `data` is `[{label, value}]`, value in [0,1]. */
export function lineChart(host, data) {
  const width = 640;
  const height = 300;
  const plot = { left: 48, top: 16, width: width - 64, height: height - 56 };
  const svg = frame(host, width, height);
  if (!data.length) return;

  gridLines(svg, plot, 4, (fraction) => fraction.toFixed(2));

  const stepX = data.length > 1 ? plot.width / (data.length - 1) : 0;
  const pointAt = (index, value) => [
    plot.left + stepX * index,
    plot.top + plot.height - Math.max(0, Math.min(1, value)) * plot.height,
  ];

  const points = data.map((d, i) => pointAt(i, d.value));
  const path = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');

  const areaPath = `${path} L${plot.left + plot.width},${plot.top + plot.height} L${plot.left},${plot.top + plot.height} Z`;
  svg.appendChild(el('path', { d: areaPath, fill: 'var(--accent)', 'fill-opacity': 0.12 }));
  svg.appendChild(el('path', { d: path, fill: 'none', stroke: 'var(--accent)', 'stroke-width': 2 }));

  // Label a handful of x positions so the axis stays readable.
  const labelEvery = Math.max(1, Math.ceil(data.length / 6));
  data.forEach((point, index) => {
    if (index % labelEvery !== 0) return;
    const [x] = pointAt(index, point.value);
    const label = el('text', {
      x, y: height - 18, 'text-anchor': 'middle', fill: 'var(--muted)', 'font-size': 10,
    });
    label.textContent = point.label;
    svg.appendChild(label);
  });
}
