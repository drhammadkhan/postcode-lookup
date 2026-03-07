#!/usr/bin/env python3
"""
generate_extra_maps.py  –  Build 5 supplementary catchment maps.

Outputs to docs/maps/ so they are served as part of the static Netlify site.

Maps 1–3 are lightweight static Leaflet.js pages (~6 KB each) that load
postcodes.json at runtime using an HTML5 canvas dot overlay.

Maps 4–5 are self-contained folium HTML files (~91 KB each).

Maps generated:
  1. docs/maps/map1_levels.html     – per-level catchments (Any / L1 / L2 / L3)
  2. docs/maps/map2_distance.html   – distance gradient to nearest L3 NICU
  3. docs/maps/map3_escalation.html – which postcodes need a different hospital for L3
  4. docs/maps/map4_bubbles.html    – hospital bubble map (catchment size)
  5. docs/maps/map5_voronoi.html    – Voronoi geographic boundaries

Run:  python generate_extra_maps.py
Then open docs/extra_maps.html in a browser.
"""

import colorsys, os
import numpy as np
import pandas as pd
import folium
from scipy.spatial import Voronoi

os.makedirs('docs/maps', exist_ok=True)

# ── Load data ─────────────────────────────────────────────────────────────────
results   = pd.read_csv('output/All_Postcodes.csv', dtype={'Postcode': str})
hospitals = pd.read_csv('hospitals_refined.csv')

hospital_names = sorted(results['Closest_Any'].unique())
n_hosp         = len(hospital_names)


def make_colours(n):
    colours = []
    for i in range(n):
        r, g, b = colorsys.hls_to_rgb(i / n, 0.45, 0.75)
        colours.append(f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}')
    return colours


colour_list = make_colours(n_hosp)
colour_map  = dict(zip(hospital_names, colour_list))

CENTRE   = [51.5, -0.1]
ZOOM     = 10
BASETILE = 'cartodbpositron'


# ── Shared helpers ─────────────────────────────────────────────────────────────

def add_hospital_markers(m):
    """Add a toggleable hospital-marker layer to map m."""
    lg = folium.FeatureGroup(name='Hospitals', show=True)
    for _, r in hospitals.iterrows():
        name = r['Hospital Name']
        c = colour_map.get(name, '#333')
        folium.CircleMarker(
            [r['Latitude'], r['Longitude']],
            radius=8, color='black', weight=2,
            fill=True, fill_color=c, fill_opacity=1.0,
            popup=f"<b>{name}</b><br>Level {r['Level']} | {r['Side']}",
            tooltip=name,
        ).add_to(lg)
    lg.add_to(m)


_TOGGLE_JS = """<script>
document.addEventListener('DOMContentLoaded', function () {
  setTimeout(function () {
    var ctrl = document.querySelector('.leaflet-control-layers-overlays');
    if (!ctrl) return;
    var div = document.createElement('div');
    div.style = 'padding:6px 0 2px;text-align:center;border-top:1px solid #ccc;margin-top:4px;';
    var a = document.createElement('a');
    a.href = '#';
    a.style = 'cursor:pointer;font-size:12px;color:#2d6a9f;font-weight:600;';
    a.textContent = 'Deselect All';
    var on = true;
    a.onclick = function (e) {
      e.preventDefault(); on = !on;
      ctrl.querySelectorAll('input[type=checkbox]').forEach(function (cb) {
        if (cb.checked !== on) cb.click();
      });
      a.textContent = on ? 'Deselect All' : 'Select All';
    };
    div.appendChild(a);
    ctrl.appendChild(div);
  }, 500);
});
</script>"""


def add_layer_control(m):
    folium.LayerControl(collapsed=False).add_to(m)
    m.get_root().html.add_child(folium.Element(_TOGGLE_JS))


def add_legend(m, title, items):
    """items = list of (colour_hex, label_str)"""
    html = (
        '<div style="position:fixed;bottom:20px;left:20px;z-index:9999;'
        'background:white;padding:12px 16px;border-radius:8px;'
        'box-shadow:0 2px 8px rgba(0,0,0,.25);font-size:12px;'
        'max-height:60vh;overflow-y:auto;line-height:1.8;">'
        f'<b style="font-size:13px">{title}</b><br>'
    )
    for c, label in items:
        html += (
            f'<span style="background:{c};width:12px;height:12px;'
            f'display:inline-block;border-radius:2px;margin-right:6px;"></span>'
            f'{label}<br>'
        )
    html += '</div>'
    m.get_root().html.add_child(folium.Element(html))


def add_infobox(m, html_body):
    html = (
        '<div style="position:fixed;bottom:20px;left:20px;z-index:9999;'
        'background:white;padding:12px 16px;border-radius:8px;'
        'box-shadow:0 2px 8px rgba(0,0,0,.25);font-size:12px;'
        'max-width:250px;line-height:1.6;">'
        + html_body + '</div>'
    )
    m.get_root().html.add_child(folium.Element(html))


# ── MAP 4 – Bubble map ────────────────────────────────────────────────────────

def build_map4():
    """Hospital circles scaled by postcode catchment count, per care level."""
    level_defs = [
        ('Any Level',                 'Closest_Any', True),
        ('Level 1 — Special Care',    'Closest_L1',  False),
        ('Level 2 — High Dependency', 'Closest_L2',  False),
        ('Level 3 — NICU',            'Closest_L3',  False),
    ]

    m = folium.Map(location=CENTRE, zoom_start=ZOOM, tiles=None)
    folium.TileLayer(BASETILE, name='Base Map').add_to(m)

    MAX_RADIUS = 45
    for label, col, show in level_defs:
        counts    = results[col].value_counts()
        max_count = counts.max()
        fg = folium.FeatureGroup(name=label, show=show)
        for _, row in hospitals.iterrows():
            name  = row['Hospital Name']
            count = int(counts.get(name, 0))
            if count == 0:
                continue
            c      = colour_map.get(name, '#666')
            radius = MAX_RADIUS * np.sqrt(count / max_count)
            folium.CircleMarker(
                [row['Latitude'], row['Longitude']],
                radius=radius, color=c, weight=2,
                fill=True, fill_color=c, fill_opacity=0.45,
                popup=(
                    f"<b>{name}</b><br>Level {row['Level']} | {row['Side']}<br>"
                    f"{label}: <b>{count:,}</b> postcodes"
                ),
                tooltip=f"{name}: {count:,} postcodes ({label})",
            ).add_to(fg)
        fg.add_to(m)

    add_layer_control(m)
    add_infobox(m,
        '<b style="font-size:13px">Bubble Size</b><br>'
        'Each bubble is one hospital. Area is proportional to the number of postcodes '
        'for which it is the nearest unit at the selected care level.<br><br>'
        '<i>Use the layer control (top right) to switch between levels.</i>'
    )

    path = 'docs/maps/map4_bubbles.html'
    m.save(path)
    print(f"Map 4 saved → {path}  ({n_hosp} hospitals)")


# ── MAP 5 – Voronoi catchment boundaries (North/South Thames-aware) ──────────

# Thames centre-line, west→east, strictly increasing longitude.
# Used as the clipping boundary between North and South Voronoi diagrams.
THAMES_LINE = [
    (51.413, -0.520),  # East Molesey
    (51.444, -0.380),  # Twickenham
    (51.461, -0.310),  # Richmond
    (51.477, -0.260),  # Kew
    (51.482, -0.245),  # Brentford
    (51.487, -0.228),  # Chiswick
    (51.490, -0.205),  # Hammersmith
    (51.480, -0.175),  # Fulham / Putney
    (51.476, -0.155),  # Chelsea Bridge
    (51.485, -0.128),  # Vauxhall
    (51.495, -0.120),  # Westminster
    (51.503, -0.095),  # Waterloo
    (51.507, -0.075),  # Blackfriars
    (51.504, -0.048),  # London Bridge
    (51.499,  0.005),  # Bermondsey
    (51.494,  0.025),  # Rotherhithe
    (51.489,  0.053),  # Greenwich
    (51.480,  0.095),  # Woolwich
    (51.468,  0.145),  # Erith
    (51.457,  0.200),  # Purfleet
    (51.445,  0.335),  # Gravesend
]


def _thames_lat_at(lon):
    """Linearly interpolate Thames latitude at a given longitude."""
    lons = [p[1] for p in THAMES_LINE]
    lats = [p[0] for p in THAMES_LINE]
    if lon <= lons[0]:  return lats[0]
    if lon >= lons[-1]: return lats[-1]
    for i in range(len(lons) - 1):
        if lons[i] <= lon <= lons[i + 1]:
            t = (lon - lons[i]) / (lons[i + 1] - lons[i])
            return lats[i] + t * (lats[i + 1] - lats[i])
    return lats[-1]


def _north_of_thames(lat, lon):
    return lat > _thames_lat_at(lon)


def _thames_crossing(a, b):
    """Binary-search intersection of edge a→b with the Thames line."""
    na, nb = _north_of_thames(a[0], a[1]), _north_of_thames(b[0], b[1])
    if na == nb:
        return None
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        m   = (a[0] + mid * (b[0] - a[0]), a[1] + mid * (b[1] - a[1]))
        if _north_of_thames(m[0], m[1]) == na:
            lo = mid
        else:
            hi = mid
    t = (lo + hi) / 2
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def _clip_to_thames_side(polygon, want_north):
    """Sutherland-Hodgman style clip using the Thames polyline as the boundary."""
    result = []
    n = len(polygon)
    for i in range(n):
        curr  = polygon[i]
        prev  = polygon[i - 1]
        c_in  = (_north_of_thames(curr[0], curr[1]) == want_north)
        p_in  = (_north_of_thames(prev[0], prev[1]) == want_north)
        if c_in:
            if not p_in:
                pt = _thames_crossing(prev, curr)
                if pt: result.append(pt)
            result.append(curr)
        elif p_in:
            pt = _thames_crossing(prev, curr)
            if pt: result.append(pt)
    return result


def _clip_polygon(polygon, lat_min, lat_max, lon_min, lon_max):
    """Sutherland–Hodgman clip of a (lat, lon) polygon to an axis-aligned box."""
    def inside(p, edge):
        lat, lon = p
        return {'L': lon >= lon_min, 'R': lon <= lon_max,
                'B': lat >= lat_min, 'T': lat <= lat_max}[edge]

    def intersect(a, b, edge):
        la, lna = a
        lb, lnb = b
        if edge in ('L', 'R'):
            xb = lon_min if edge == 'L' else lon_max
            t  = (xb - lna) / (lnb - lna) if lnb != lna else 0
            return (la + t * (lb - la), xb)
        else:
            yb = lat_min if edge == 'B' else lat_max
            t  = (yb - la) / (lb - la) if lb != la else 0
            return (yb, lna + t * (lnb - lna))

    out = polygon
    for edge in ('L', 'R', 'B', 'T'):
        if not out:
            return []
        inp, out = out, []
        for i, curr in enumerate(inp):
            prev = inp[i - 1]
            in_c, in_p = inside(curr, edge), inside(prev, edge)
            if in_c:
                if not in_p:
                    out.append(intersect(prev, curr, edge))
                out.append(curr)
            elif in_p:
                out.append(intersect(prev, curr, edge))
    return out


def _densify(polygon, max_seg_deg=0.007):
    """Insert intermediate vertices on long edges for smoother polygon rendering."""
    result = []
    n = len(polygon)
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        result.append(a)
        dist = np.hypot(b[0] - a[0], b[1] - a[1])
        if dist > max_seg_deg:
            steps = int(np.ceil(dist / max_seg_deg))
            for j in range(1, steps):
                t = j / steps
                result.append((a[0] + t * (b[0] - a[0]),
                                a[1] + t * (b[1] - a[1])))
    return result


def build_map5():
    """North/South Thames-aware Voronoi with densified edges."""
    lat_ref  = 51.5
    scale    = np.cos(np.radians(lat_ref))
    LAT_MIN, LAT_MAX = 51.0, 52.1
    LON_MIN, LON_MAX = -1.0,  0.75

    m = folium.Map(location=CENTRE, zoom_start=ZOOM, tiles=None)
    folium.TileLayer(BASETILE, name='Base Map').add_to(m)

    # Draw the Thames as a visual reference line
    folium.PolyLine(
        THAMES_LINE, color='#4a90d9', weight=3, opacity=0.8,
        tooltip='River Thames (approximate)',
    ).add_to(m)

    def _build_side(side_hosps, want_north):
        """Compute Voronoi, clip to Thames side, densify, return list of region dicts."""
        side_hosps = side_hosps.reset_index(drop=True)
        n = len(side_hosps)
        if n == 0:
            return []
        names_s  = list(side_hosps['Hospital Name'])
        levels_s = list(side_hosps['Level'])
        pts = np.array([
            [r['Latitude'], r['Longitude'] * scale]
            for _, r in side_hosps.iterrows()
        ])
        # 48-point mirror ring prevents unbounded outer regions
        cx, cy  = pts.mean(axis=0)
        angles  = np.linspace(0, 2 * np.pi, 48, endpoint=False)
        mirrors = np.array([[cx + 25 * np.sin(a), cy + 25 * np.cos(a)] for a in angles])
        vor     = Voronoi(np.vstack([pts, mirrors]))

        out = []
        for i in range(n):
            region = vor.regions[vor.point_region[i]]
            if not region or -1 in region:
                continue
            # Unscale longitude
            verts = [(vor.vertices[v][0], vor.vertices[v][1] / scale) for v in region]
            # 1. Clip to bounding box
            v = _clip_polygon(verts, LAT_MIN, LAT_MAX, LON_MIN, LON_MAX)
            if len(v) < 3: continue
            # 2. Clip to correct side of Thames
            v = _clip_to_thames_side(v, want_north)
            if len(v) < 3: continue
            # 3. Densify edges
            v = _densify(v)
            out.append({'name': names_s[i], 'level': levels_s[i], 'verts': v})
        return out

    north_hosps = hospitals[hospitals['Side'].isin(['North', 'Both'])]
    south_hosps = hospitals[hospitals['Side'].isin(['South', 'Both'])]

    north_regions = _build_side(north_hosps, want_north=True)
    south_regions = _build_side(south_hosps, want_north=False)

    for label, regions, show in [
        ('North catchments', north_regions, True),
        ('South catchments', south_regions, True),
    ]:
        fg = folium.FeatureGroup(name=label, show=show)
        for reg in regions:
            name = str(reg['name'])
            c    = colour_map.get(name, '#888')
            lv   = int(reg['level']) if pd.notna(reg['level']) else '?'
            folium.Polygon(
                locations=reg['verts'],
                color=c, weight=1.2,
                fill=True, fill_color=c, fill_opacity=0.35,
                popup=f"<b>{name}</b><br>Level {lv}",
                tooltip=name,
            ).add_to(fg)
        fg.add_to(m)

    add_hospital_markers(m)
    add_layer_control(m)
    add_legend(m, 'Voronoi catchment regions (N/S aware)',
               [(colour_map[name], name) for name in hospital_names])

    path = 'docs/maps/map5_voronoi.html'
    m.save(path)
    print(f"Map 5 saved → {path}  "
          f"({len(north_regions)} north + {len(south_regions)} south regions)")


# ── MAPS 1–3: Lightweight Leaflet.js (canvas-based, ~6 KB each) ───────────────

_LOADING = """<div id="loading" style="position:absolute;inset:0;z-index:9999;background:#f0f4f8;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.75rem;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#4a5568;">
  <div style="font-weight:700;font-size:1rem;color:#1e3a5f;">Loading catchment data&hellip;</div>
  <div style="width:260px;height:6px;background:#e2e8f0;border-radius:3px;overflow:hidden;">
    <div id="barFill" style="height:100%;background:#2d6a9f;border-radius:3px;width:0;transition:width .3s;"></div>
  </div>
  <div id="loadMsg" style="font-size:.82rem;">Fetching postcodes.json</div>
</div>"""

_STATUS = ('<div id="status" style="position:absolute;bottom:10px;right:10px;z-index:800;'
           'background:rgba(255,255,255,.92);border-radius:6px;padding:4px 10px;font-size:11px;'
           'color:#718096;box-shadow:0 1px 4px rgba(0,0,0,.15);display:none;"></div>')

_DOT_LAYER = """var DotLayer=L.Layer.extend({
  initialize:function(pts,fn){this._pts=pts;this._fn=fn;},
  onAdd:function(map){
    this._map=map;var c=document.createElement('canvas');
    c.style.cssText='position:absolute;top:0;left:0;pointer-events:none;z-index:400;';
    map.getContainer().appendChild(c);this._canvas=c;this._resize();
    map.on('movestart',function(){this._canvas.style.opacity='0';},this);
    map.on('moveend zoomend',function(){this._canvas.style.opacity='1';this._draw();},this);
    map.on('resize',function(){this._resize();this._draw();},this);this._draw();
  },
  onRemove:function(map){this._canvas.parentNode.removeChild(this._canvas);},
  update:function(fn){this._fn=fn;this._draw();},
  _resize:function(){var s=this._map.getSize();this._canvas.width=s.x;this._canvas.height=s.y;},
  _draw:function(){
    var ctx=this._canvas.getContext('2d'),s=this._map.getSize(),map=this._map,fn=this._fn;
    ctx.clearRect(0,0,s.x,s.y);
    var g={};
    this._pts.forEach(function(pt){var c=fn(pt);if(!g[c])g[c]=[];g[c].push(pt);});
    Object.keys(g).forEach(function(col){
      ctx.fillStyle=col;ctx.beginPath();
      g[col].forEach(function(pt){var p=map.latLngToContainerPoint([pt[0],pt[1]]);
        ctx.moveTo(p.x+2.2,p.y);ctx.arc(p.x,p.y,2.2,0,2*Math.PI);});
      ctx.fill();});
  }
});"""

_BASE_TILE = ("L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',"
              "{attribution:'&copy; OpenStreetMap contributors &copy; CARTO',maxZoom:19}).addTo(map);")

_HOSP_JS = """var nc={};names.forEach(function(n,i){nc[n]='hsl('+Math.round((i/names.length)*360)+',75%,45%)';});
  hospData.forEach(function(h){
    L.circleMarker([h.lat,h.lon],{radius:8,color:'#1a202c',weight:2,fillColor:nc[h.name]||'#666',fillOpacity:1})
     .bindPopup('<b>'+h.name+'</b><br>Level '+h.level+' | '+h.side).bindTooltip(h.name).addTo(map);
  });"""


def _write_leaflet(path, template):
    content = (template
               .replace('_LOADING_', _LOADING)
               .replace('_STATUS_', _STATUS)
               .replace('_DOT_LAYER_', _DOT_LAYER)
               .replace('_BASE_TILE_', _BASE_TILE)
               .replace('_HOSP_JS_', _HOSP_JS))
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    kb = os.path.getsize(path) // 1024
    num = os.path.basename(path)[3]  # e.g. '1' from map1_levels.html
    print(f"Map {num} saved → {path}  ({kb} KB)")


def build_map1():
    _write_leaflet('docs/maps/map1_levels.html', r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Per-Level Catchments</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
html,body{margin:0;height:100%;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}
#map{height:100%;}
#ctrl{position:absolute;top:10px;right:10px;z-index:800;background:white;border-radius:10px;
  box-shadow:0 2px 10px rgba(0,0,0,.2);padding:10px 14px;min-width:205px;font-size:13px;}
#ctrl .t{font-weight:700;color:#1e3a5f;margin-bottom:8px;}
#ctrl label{display:flex;align-items:center;gap:8px;padding:5px 6px;border-radius:6px;
  cursor:pointer;transition:background .12s;color:#2d3748;}
#ctrl label:hover{background:#f7fafc;}
#ctrl label.sel{background:#ebf8ff;color:#2d6a9f;font-weight:600;}
#ctrl input[type=radio]{accent-color:#2d6a9f;}
#ctrl .sep{border-top:1px solid #e2e8f0;margin:8px 0;}
#leg{position:absolute;bottom:20px;left:10px;z-index:800;background:white;border-radius:10px;
  box-shadow:0 2px 8px rgba(0,0,0,.2);padding:10px 14px;font-size:11.5px;
  max-height:55vh;overflow-y:auto;line-height:1.85;max-width:220px;display:none;}
.sw{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:5px;vertical-align:middle;}
</style></head><body>
_LOADING_
<div id="map"></div>
<div id="ctrl" style="display:none;">
  <div class="t">Care level</div>
  <label class="sel"><input type="radio" name="lv" value="0" checked> Any Level</label>
  <label><input type="radio" name="lv" value="1"> Level 1 &mdash; Special Care</label>
  <label><input type="radio" name="lv" value="2"> Level 2 &mdash; High Dependency</label>
  <label><input type="radio" name="lv" value="3"> Level 3 &mdash; NICU</label>
  <div class="sep"></div>
  <label><input type="checkbox" id="hTog" checked> Hospital markers</label>
</div>
<div id="leg"></div>
_STATUS_
<script>
_DOT_LAYER_
var map=L.map('map').setView([51.5,-0.1],10);
_BASE_TILE_
var dotLayer,hospLayer;
Promise.all([
  fetch('../postcodes.json').then(function(r){document.getElementById('barFill').style.width='50%';return r.json();}),
  fetch('../hospitals.json').then(function(r){return r.json();})
]).then(function(res){
  var pcData=res[0],hospData=res[1],names=pcData.names,data=pcData.data;
  document.getElementById('barFill').style.width='80%';
  document.getElementById('loadMsg').textContent='Rendering\u2026';
  var RATE=10,pts=[],keys=Object.keys(data);
  for(var i=0;i<keys.length;i+=RATE){var r=data[keys[i]];pts.push([r[1],r[2],r[4],r[6],r[8],r[10]]);}
  var nc2=names.map(function(_,i){return 'hsl('+Math.round((i/names.length)*360)+',75%,45%)';});
  var lv=0;
  dotLayer=new DotLayer(pts,function(pt){return nc2[pt[2+lv]];});
  dotLayer.addTo(map);
  hospLayer=L.layerGroup().addTo(map);
  _HOSP_JS_
  document.querySelectorAll('input[name=lv]').forEach(function(r){
    r.addEventListener('change',function(){
      lv=parseInt(this.value,10);
      dotLayer.update(function(pt){return nc2[pt[2+lv]];});
      document.querySelectorAll('#ctrl label').forEach(function(l){l.classList.remove('sel');});
      this.parentElement.classList.add('sel');
    });
  });
  document.getElementById('hTog').addEventListener('change',function(){
    if(this.checked)map.addLayer(hospLayer);else map.removeLayer(hospLayer);
  });
  var leg=document.getElementById('leg'),html='<b>Hospital catchment</b><br>';
  names.forEach(function(n,i){html+='<span class="sw" style="background:'+nc2[i]+'"></span>'+n+'<br>';});
  leg.innerHTML=html;
  document.getElementById('status').textContent=pts.length.toLocaleString()+' postcodes (1/'+RATE+' sample)';
  document.getElementById('loading').style.display='none';
  document.getElementById('ctrl').style.display='';
  leg.style.display='';document.getElementById('status').style.display='';
}).catch(function(e){document.getElementById('loadMsg').textContent='Error: '+e.message;});
</script></body></html>""")


def build_map2():
    _write_leaflet('docs/maps/map2_distance.html', r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Distance to Nearest NICU</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
html,body{margin:0;height:100%;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}
#map{height:100%;}
#leg{position:absolute;bottom:20px;left:10px;z-index:800;background:white;border-radius:10px;
  box-shadow:0 2px 8px rgba(0,0,0,.2);padding:12px 16px;font-size:12px;line-height:2;display:none;}
.sw{display:inline-block;width:14px;height:14px;border-radius:3px;margin-right:7px;vertical-align:middle;}
</style></head><body>
_LOADING_
<div id="map"></div>
<div id="leg"></div>
_STATUS_
<script>
var BINS=[{max:3,c:'#1a9641',l:'< 3 km'},{max:6,c:'#a6d96a',l:'3\u20136 km'},
  {max:10,c:'#ffffbf',l:'6\u201310 km'},{max:15,c:'#fd8d3c',l:'10\u201315 km'},
  {max:Infinity,c:'#d73027',l:'> 15 km'}];
function dc(km){for(var i=0;i<BINS.length;i++)if(km<BINS[i].max)return BINS[i].c;return BINS[BINS.length-1].c;}
_DOT_LAYER_
var map=L.map('map').setView([51.5,-0.1],10);
_BASE_TILE_
Promise.all([
  fetch('../postcodes.json').then(function(r){document.getElementById('barFill').style.width='50%';return r.json();}),
  fetch('../hospitals.json').then(function(r){return r.json();})
]).then(function(res){
  var pcData=res[0],hospData=res[1],names=pcData.names,data=pcData.data;
  document.getElementById('barFill').style.width='80%';
  document.getElementById('loadMsg').textContent='Rendering\u2026';
  var RATE=8,pts=[],keys=Object.keys(data);
  for(var i=0;i<keys.length;i+=RATE){var r=data[keys[i]];pts.push([r[1],r[2],r[11]]);}
  new DotLayer(pts,function(pt){return dc(pt[2]);}).addTo(map);
  _HOSP_JS_
  var leg=document.getElementById('leg'),html='<b>Distance to nearest NICU (L3)</b><br>';
  BINS.forEach(function(b){html+='<span class="sw" style="background:'+b.c+'"></span>'+b.l+'<br>';});
  leg.innerHTML=html;
  document.getElementById('status').textContent=pts.length.toLocaleString()+' postcodes (1/8 sample)';
  document.getElementById('loading').style.display='none';
  leg.style.display='';document.getElementById('status').style.display='';
}).catch(function(e){document.getElementById('loadMsg').textContent='Error: '+e.message;});
</script></body></html>""")


def build_map3():
    _write_leaflet('docs/maps/map3_escalation.html', r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NICU Escalation Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
html,body{margin:0;height:100%;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}
#map{height:100%;}
#info{position:absolute;bottom:20px;left:10px;z-index:800;background:white;border-radius:10px;
  box-shadow:0 2px 8px rgba(0,0,0,.2);padding:12px 16px;font-size:12px;line-height:1.8;
  max-width:245px;display:none;}
.sw{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:6px;vertical-align:middle;}
</style></head><body>
_LOADING_
<div id="map"></div>
<div id="info"></div>
_STATUS_
<script>
_DOT_LAYER_
var map=L.map('map').setView([51.5,-0.1],10);
_BASE_TILE_
Promise.all([
  fetch('../postcodes.json').then(function(r){document.getElementById('barFill').style.width='50%';return r.json();}),
  fetch('../hospitals.json').then(function(r){return r.json();})
]).then(function(res){
  var pcData=res[0],hospData=res[1],names=pcData.names,data=pcData.data;
  document.getElementById('barFill').style.width='80%';
  document.getElementById('loadMsg').textContent='Rendering\u2026';
  var nc3=names.map(function(_,i){return 'hsl('+Math.round((i/names.length)*360)+',75%,45%)';});
  var RATE=8,pts=[],keys=Object.keys(data),same=0,diff=0;
  for(var i=0;i<keys.length;i+=RATE){
    var r=data[keys[i]];pts.push([r[1],r[2],r[4],r[10]]);
    if(r[4]===r[10])same++;else diff++;
  }
  new DotLayer(pts,function(pt){return pt[2]===pt[3]?'#aaaaaa':nc3[pt[3]];}).addTo(map);
  _HOSP_JS_
  var total=same+diff,pct=Math.round(diff/total*100);
  document.getElementById('info').innerHTML=
    '<b style="font-size:13px">Escalation to NICU</b><br>'+
    '<span class="sw" style="background:#aaa"></span>No escalation: '+same.toLocaleString()+'<br>'+
    '<span class="sw" style="background:#e53e3e"></span>Escalation needed: '+diff.toLocaleString()+' ('+pct+'%)';
  document.getElementById('status').textContent=pts.length.toLocaleString()+' postcodes (1/8 sample)';
  document.getElementById('loading').style.display='none';
  document.getElementById('info').style.display='';document.getElementById('status').style.display='';
}).catch(function(e){document.getElementById('loadMsg').textContent='Error: '+e.message;});
</script></body></html>""")


# ── Run all ───────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("Building extra maps …\n")
    build_map1()
    build_map2()
    build_map3()
    build_map4()
    build_map5()
    print("\n✓  All done.  Open docs/extra_maps.html in a browser.")
