// Local equirectangular projection: good to a few metres over a few kilometres, which is the scale of a site.
export interface Pt { lat: number; lon: number }

export class Projection {
  private kx: number;
  private ky = 110540;
  private minX: number; private minY: number; private scale: number;
  constructor(points: Pt[], public w: number, public h: number, public pad = 56, minSpanM = 900) {
    const lat0 = points.length ? points.reduce((s, p) => s + p.lat, 0) / points.length : 0;
    this.kx = 111320 * Math.cos((lat0 * Math.PI) / 180);
    const xs = points.map((p) => p.lon * this.kx), ys = points.map((p) => p.lat * this.ky);
    let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    if (!points.length) { x0 = y0 = 0; x1 = y1 = minSpanM; }
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const spanX = Math.max(x1 - x0, minSpanM), spanY = Math.max(y1 - y0, minSpanM * (h / w));
    this.scale = Math.min((w - 2 * pad) / spanX, (h - 2 * pad) / spanY);
    this.minX = cx - (w / 2) / this.scale;
    this.minY = cy - (h / 2) / this.scale;
  }
  xy(p: Pt): [number, number] {
    return [(p.lon * this.kx - this.minX) * this.scale, this.h - (p.lat * this.ky - this.minY) * this.scale];
  }
  metres(px: number) { return px / this.scale; }
  px(m: number) { return m * this.scale; }
}

export function niceScale(maxMetres: number): number {
  const steps = [50, 100, 200, 250, 500, 1000, 2000, 2500, 5000];
  let best = steps[0];
  for (const s of steps) if (s <= maxMetres) best = s;
  return best;
}
