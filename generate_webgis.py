# -*- coding: utf-8 -*-
"""
WebGIS Interaktif: Keseimbangan Kapasitas Hotel dan Restoran
di Samdo 1-dong, Jeju City

Libraries: Folium, pandas, matplotlib, pyproj
"""

import json, math
import folium
from folium import FeatureGroup, LayerControl, CircleMarker, Marker, GeoJson
from folium.plugins import MiniMap
from pathlib import Path

# === REPROJEKSI ===
try:
    from pyproj import Transformer
    _tr = Transformer.from_crs("EPSG:5179", "EPSG:4326", always_xy=True)
    def to_lonlat(x, y): return _tr.transform(x, y)
    print("[OK] pyproj loaded")
except ImportError:
    print("[WARN] pyproj missing, using approx")
    def to_lonlat(x, y):
        a,f=6378137.0,1/298.257222101; e2=2*f-f*f; k0=0.9996
        lon0,lat0=math.radians(127.5),math.radians(38.0)
        xa,ya=x-1000000,y-2000000
        e1=(1-math.sqrt(1-e2))/(1+math.sqrt(1-e2))
        M0=a*((1-e2/4-3*e2**2/64-5*e2**3/256)*lat0-(3*e2/8+3*e2**2/32+45*e2**3/1024)*math.sin(2*lat0)+(15*e2**2/256+45*e2**3/1024)*math.sin(4*lat0)-(35*e2**3/3072)*math.sin(6*lat0))
        M=M0+ya/k0; mu=M/(a*(1-e2/4-3*e2**2/64-5*e2**3/256))
        p1=mu+(3*e1/2-27*e1**3/32)*math.sin(2*mu)+(21*e1**2/16-55*e1**4/32)*math.sin(4*mu)+(151*e1**3/96)*math.sin(6*mu)+(1097*e1**4/512)*math.sin(8*mu)
        N1=a/math.sqrt(1-e2*math.sin(p1)**2); T1=math.tan(p1)**2; C1=(e2/(1-e2))*math.cos(p1)**2; R1=a*(1-e2)/(1-e2*math.sin(p1)**2)**1.5; D=xa/(N1*k0)
        lat=p1-(N1*math.tan(p1)/R1)*(D**2/2-(5+3*T1+10*C1-4*C1**2-9*(e2/(1-e2)))*D**4/24+(61+90*T1+298*C1+45*T1**2-252*(e2/(1-e2))-3*C1**2)*D**6/720)
        lon=lon0+(D-(1+2*T1+C1)*D**3/6+(5-2*C1+28*T1-3*C1**2+8*(e2/(1-e2))+24*T1**2)*D**5/120)/math.cos(p1)
        return (math.degrees(lon), math.degrees(lat))

def reproj_coords(coords, gt):
    if gt == "Point":
        return list(to_lonlat(coords[0], coords[1]))
    elif gt == "Polygon":
        return [[list(to_lonlat(c[0],c[1])) for c in r] for r in coords]
    elif gt == "MultiPolygon":
        return [[[list(to_lonlat(c[0],c[1])) for c in r] for r in p] for p in coords]
    return coords

def reproj_geojson(data):
    need = "5179" in data.get("crs",{}).get("properties",{}).get("name","")
    feats = []
    for f in data["features"]:
        nf = json.loads(json.dumps(f))
        if need:
            nf["geometry"]["coordinates"] = reproj_coords(nf["geometry"]["coordinates"], nf["geometry"]["type"])
        feats.append(nf)
    return {"type":"FeatureCollection","features":feats}

def pip(px, py, ring):
    n=len(ring); inside=False; j=n-1
    for i in range(n):
        xi,yi=ring[i]; xj,yj=ring[j]
        if ((yi>py)!=(yj>py)) and (px<(xj-xi)*(py-yi)/(yj-yi)+xi): inside=not inside
        j=i
    return inside

def pip_multi(px, py, mp):
    for poly in mp:
        if pip(px, py, poly[0]): return True
    return False

# === LOAD DATA ===
BD = Path(__file__).parent
hotels_raw = json.loads((BD/"samdo1_hotels.geojson").read_text(encoding="utf-8"))
rest_raw = json.loads((BD/"samdo1_restaurants.geojson").read_text(encoding="utf-8"))
buf_raw = json.loads((BD/"hotels_buffer_200m.geojson").read_text(encoding="utf-8"))
bnd_raw = json.loads((BD/"samdo1_boundary.geojson").read_text(encoding="utf-8"))

print("[INFO] Reprojecting...")
hotels = reproj_geojson(hotels_raw)
buf_data = reproj_geojson(buf_raw)
boundary = reproj_geojson(bnd_raw)
restaurants = {"type":"FeatureCollection","features":rest_raw["features"]}

# Center from boundary
bc = boundary["features"][0]["geometry"]["coordinates"]
lats,lons=[],[]
for p in bc:
    for r in p:
        for c in r: lons.append(c[0]); lats.append(c[1])
clat,clon = sum(lats)/len(lats), sum(lons)/len(lons)

# === SPATIAL ANALYSIS ===
print("[INFO] Spatial analysis...")
bpolys = []
for f in buf_data["features"]:
    g = f["geometry"]
    if g["type"]=="MultiPolygon": bpolys.append(g["coordinates"])
    else: bpolys.append([g["coordinates"]])

rest_in, rest_out = [], []
for f in restaurants["features"]:
    c = f["geometry"]["coordinates"]
    inside = any(pip_multi(c[0],c[1],mp) for mp in bpolys)
    (rest_in if inside else rest_out).append(f)

print(f"  Inside: {len(rest_in)}, Outside: {len(rest_out)}")

# === PANDAS + MATPLOTLIB ANALYTICS ===
from analytics import generate_all
ana = generate_all(hotels["features"], restaurants["features"])
df_radius = ana['df_radius']
stats = ana['stats']

# Print summary table
print("\n[ANALYTICS] Distance Statistics:")
print(f"  Min: {stats['min']}m | Max: {stats['max']}m | Mean: {stats['mean']}m | Median: {stats['median']}m")
print("\n[ANALYTICS] Multi-Radius Coverage:")
print(df_radius.to_string(index=False))

# === BUILD MAP ===
print("\n[INFO] Building Folium map...")
m = folium.Map(location=[clat,clon], zoom_start=15, tiles=None, control_scale=True)

folium.TileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    attr='CARTO', name="CartoDB Dark", max_zoom=19).add_to(m)
folium.TileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attr='OSM', name="OpenStreetMap", max_zoom=19).add_to(m)
folium.TileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    attr='CARTO', name="CartoDB Positron", max_zoom=19).add_to(m)

# Boundary
fg = FeatureGroup(name="Batas Kecamatan", show=True)
GeoJson(boundary, style_function=lambda x:{"color":"#FFD700","weight":3,"dashArray":"10 6","fillOpacity":0.05,"fillColor":"#FFD700"},
    tooltip="Samdo 1-dong Boundary").add_to(fg)
fg.add_to(m)

# Buffer
fg = FeatureGroup(name="Buffer Hotel 200m", show=True)
GeoJson(buf_data, style_function=lambda x:{"color":"#4A90D9","weight":1.5,"fillColor":"#4A90D9","fillOpacity":0.18,"dashArray":"4 3"},
    tooltip="Buffer 200m").add_to(fg)
fg.add_to(m)

# Hotels
fg = FeatureGroup(name="Hotel", show=True)
for f in hotels["features"]:
    c=f["geometry"]["coordinates"]; p=f["properties"]
    nm = p.get("name","?"); en = p.get("name:en","")
    disp = f"{nm} ({en})" if en else nm
    popup = f'<div style="font-family:sans-serif"><b style="color:#E67E22">{disp}</b><br>Lat:{c[1]:.5f} Lon:{c[0]:.5f}</div>'
    Marker([c[1],c[0]], popup=folium.Popup(popup,max_width=250), tooltip=disp,
        icon=folium.Icon(color="orange",icon="bed",prefix="fa")).add_to(fg)
fg.add_to(m)

# Restaurants inside
fg = FeatureGroup(name="Restoran (Dalam Buffer)", show=True)
for f in rest_in:
    c=f["geometry"]["coordinates"]; p=f["properties"]
    nm=p.get("name","?"); en=p.get("name:en",""); cu=p.get("cuisine","-") or "-"
    disp = f"{nm} ({en})" if en else nm
    # Find distance from analytics df
    row = ana['df_rest'][ana['df_rest']['name']==nm]
    dist_str = f"{row['dist_nearest_hotel_m'].values[0]:.0f}m" if len(row)>0 else "?"
    popup = f'<div style="font-family:sans-serif"><b style="color:#27AE60">{disp}</b><br>Cuisine: {cu}<br>Jarak ke hotel: {dist_str}<br><span style="color:#27AE60;font-weight:bold">Dalam Buffer</span></div>'
    CircleMarker([c[1],c[0]], radius=8, color="#27AE60", fill=True, fill_color="#2ECC71",
        fill_opacity=0.85, weight=2, popup=folium.Popup(popup,max_width=250), tooltip=disp).add_to(fg)
fg.add_to(m)

# Restaurants outside
fg = FeatureGroup(name="Restoran (Luar Buffer)", show=True)
for f in rest_out:
    c=f["geometry"]["coordinates"]; p=f["properties"]
    nm=p.get("name","?"); en=p.get("name:en",""); cu=p.get("cuisine","-") or "-"
    disp = f"{nm} ({en})" if en else nm
    row = ana['df_rest'][ana['df_rest']['name']==nm]
    dist_str = f"{row['dist_nearest_hotel_m'].values[0]:.0f}m" if len(row)>0 else "?"
    popup = f'<div style="font-family:sans-serif"><b style="color:#E74C3C">{disp}</b><br>Cuisine: {cu}<br>Jarak ke hotel: {dist_str}<br><span style="color:#E74C3C;font-weight:bold">Luar Buffer</span></div>'
    CircleMarker([c[1],c[0]], radius=8, color="#E74C3C", fill=True, fill_color="#E74C3C",
        fill_opacity=0.85, weight=2, popup=folium.Popup(popup,max_width=250), tooltip=disp).add_to(fg)
fg.add_to(m)

LayerControl(collapsed=False).add_to(m)
MiniMap(toggle_display=True, position="bottomright").add_to(m)

# === TITLE ===
m.get_root().html.add_child(folium.Element("""
<div style="position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:9999;
background:rgba(20,20,30,0.88);backdrop-filter:blur(12px);padding:12px 28px;border-radius:14px;
border:1px solid rgba(255,255,255,0.15);box-shadow:0 8px 32px rgba(0,0,0,0.4);
font-family:'Segoe UI',sans-serif;text-align:center;pointer-events:none;">
<h2 style="margin:0;color:#fff;font-size:16px;font-weight:600;">Keseimbangan Kapasitas Hotel & Restoran</h2>
<p style="margin:3px 0 0;color:rgba(255,255,255,0.6);font-size:11px;">Samdo 1-dong, Jeju City &mdash; Gap Analysis WebGIS</p>
</div>"""))

# === LEGEND ===
ni,no = len(rest_in), len(rest_out)
tot = ni+no
pct = 100*ni/max(1,tot)
m.get_root().html.add_child(folium.Element(f"""
<div style="position:fixed;bottom:30px;left:14px;z-index:9999;background:rgba(20,20,30,0.9);
backdrop-filter:blur(12px);padding:14px 18px;border-radius:12px;border:1px solid rgba(255,255,255,0.12);
box-shadow:0 8px 32px rgba(0,0,0,0.35);font-family:'Segoe UI',sans-serif;min-width:210px;color:#fff;">
<h4 style="margin:0 0 10px;font-size:13px;border-bottom:1px solid rgba(255,255,255,0.2);padding-bottom:6px;">Legenda</h4>
<div style="font-size:11px;line-height:2;">
<span style="display:inline-block;width:14px;height:14px;background:#FFD700;border-radius:2px;vertical-align:middle;margin-right:6px;border:1px dashed #333;"></span>Batas Kecamatan<br>
<span style="display:inline-block;width:14px;height:14px;background:rgba(74,144,217,0.5);border:1.5px solid #4A90D9;border-radius:50%;vertical-align:middle;margin-right:6px;"></span>Buffer 200m<br>
<span style="display:inline-block;width:14px;height:14px;background:#E67E22;border-radius:3px;vertical-align:middle;margin-right:6px;"></span>Hotel ({len(hotels['features'])})<br>
<span style="display:inline-block;width:14px;height:14px;background:#2ECC71;border-radius:50%;vertical-align:middle;margin-right:6px;border:2px solid #27AE60;"></span>Restoran Dalam ({ni})<br>
<span style="display:inline-block;width:14px;height:14px;background:#E74C3C;border-radius:50%;vertical-align:middle;margin-right:6px;border:2px solid #C0392B;"></span>Restoran Luar ({no})
</div>
<div style="margin-top:8px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.15);font-size:10px;color:rgba(255,255,255,0.5);">
Coverage: {ni}/{tot} ({pct:.0f}%) | Mean dist: {stats['mean']}m
</div></div>"""))

# === ANALYTICS SIDEBAR — Premium Collapsible Left Panel ===
radius_rows = ""
for _, r in df_radius.iterrows():
    hl = ' style="background:rgba(46,204,113,0.12);"' if int(r['Radius (m)']) == 200 else ""
    radius_rows += f'<tr{hl}><td>{int(r["Radius (m)"])}m</td><td style="text-align:center">{int(r["N Restoran"])}</td><td style="text-align:center">{r["Coverage (%)"]:.0f}%</td></tr>'

# Build restaurant detail rows for data table
rest_detail_rows = ""
for _, r in ana['df_rest'].iterrows():
    nm = r['name'] if r['name'] else '?'
    cu = r['cuisine'] if r['cuisine'] != '-' else '-'
    dist = r['dist_nearest_hotel_m']
    inside = r['in_buffer_200m']
    badge_color = "#2ecc71" if inside else "#e74c3c"
    badge_text = "Dalam" if inside else "Luar"
    rest_detail_rows += f'<tr><td style="max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{nm}</td><td>{cu}</td><td style="text-align:right">{dist:.0f}m</td><td><span style="background:{badge_color};color:#fff;padding:1px 8px;border-radius:10px;font-size:9px;font-weight:600">{badge_text}</span></td></tr>'

coverage_pct_val = 100 * ana['n_in'] / max(1, ana['n_in'] + ana['n_out'])
dash_offset = 283 - (283 * coverage_pct_val / 100)

panel_html = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* --- Sidebar --- */
#ap-sidebar {{
    position: fixed; top: 0; left: -360px; bottom: 0; width: 360px;
    z-index: 9999; display: flex; flex-direction: column;
    background: rgba(14, 16, 28, 0.95); backdrop-filter: blur(20px) saturate(1.4);
    border-right: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow: 12px 0 40px rgba(0,0,0,0.6);
    transition: left 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    font-family: 'Inter', 'Segoe UI', sans-serif; color: #e0e0e0;
}}
#ap-sidebar.open {{ left: 0; }}

/* --- Sidebar Toggle Tab --- */
#ap-toggle-tab {{
    position: absolute; top: 80px; right: -42px; width: 42px; height: 48px;
    background: rgba(14, 16, 28, 0.95); border-radius: 0 8px 8px 0;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    border-right: 1px solid rgba(255, 255, 255, 0.1);
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    color: #fff; cursor: pointer; display: flex; align-items: center;
    justify-content: center; font-size: 18px; box-shadow: 6px 4px 15px rgba(0,0,0,0.3);
    transition: background 0.3s;
}}
#ap-toggle-tab:hover {{ background: #242840; }}
#ap-toggle-tab .arrow {{ transition: transform 0.4s; }}
#ap-sidebar.open #ap-toggle-tab .arrow {{ transform: rotate(180deg); }}

/* --- Header --- */
.ap-header {{
    padding: 24px 20px 14px; border-bottom: 1px solid rgba(255,255,255,0.06);
}}
.ap-header h3 {{ margin: 0; font-size: 16px; font-weight: 600; color: #fff; }}
.ap-header p {{ margin: 4px 0 0; font-size: 10px; color: rgba(255,255,255,0.5); text-transform: uppercase; letter-spacing: 1px; }}

/* --- Tabs --- */
.ap-tabs {{
    display: flex; gap: 0; padding: 0 10px; border-bottom: 1px solid rgba(255,255,255,0.06);
}}
.ap-tab {{
    flex: 1; padding: 12px 0; text-align: center; cursor: pointer;
    font-size: 11px; font-weight: 500; color: rgba(255,255,255,0.45);
    border-bottom: 2px solid transparent; transition: all 0.25s;
}}
.ap-tab:hover {{ color: rgba(255,255,255,0.7); }}
.ap-tab.active {{
    color: #fff; font-weight: 600; border-bottom: 2px solid #667eea;
}}

/* --- Content Panel --- */
.ap-content {{ flex: 1; overflow-y: auto; padding: 20px; }}
.ap-pane {{ display: none; }}
.ap-pane.active {{ display: block; animation: fadeUp 0.35s ease; }}
@keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(10px); }}
    to {{ opacity: 1; transform: translateY(0); }}
}}

/* --- Cards & UI Elements --- */
.ov-hero {{ display: flex; align-items: center; gap: 20px; margin-bottom: 18px; }}
.ov-ring {{ flex-shrink: 0; position: relative; width: 80px; height: 80px; }}
.ov-ring svg {{ transform: rotate(-90deg); }}
.ov-ring .pct-label {{
    position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
    font-size: 18px; font-weight: 700; color: #fff;
}}
.ov-ring .pct-sub {{
    position: absolute; top: 68%; left: 50%; transform: translateX(-50%);
    font-size: 7px; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 0.5px;
}}
.ov-summary {{ flex: 1; }}
.ov-summary .big {{ font-size: 20px; font-weight: 700; color: #fff; line-height: 1.2; }}
.ov-summary .sub {{ font-size: 10px; color: rgba(255,255,255,0.45); margin-top: 4px; }}

.stat-row {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 18px; }}
.s-card {{
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px; padding: 12px 6px; text-align: center; transition: all 0.25s;
}}
.s-card:hover {{ background: rgba(102,126,234,0.1); border-color: rgba(102,126,234,0.3); }}
.s-card .v {{ font-size: 18px; font-weight: 700; color: #a78bfa; }}
.s-card .l {{ font-size: 8px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }}

.count-row {{ display: flex; gap: 10px; margin-bottom: 18px; }}
.c-card {{
    flex: 1; border-radius: 8px; padding: 10px 12px; display: flex; align-items: center; gap: 10px;
}}
.c-card.green {{ background: rgba(46,204,113,0.08); border: 1px solid rgba(46,204,113,0.15); }}
.c-card.red {{ background: rgba(231,76,60,0.08); border: 1px solid rgba(231,76,60,0.15); }}
.c-card .ic {{ font-size: 18px; }}
.c-card .num {{ font-size: 18px; font-weight: 700; }}
.c-card.green .num {{ color: #2ecc71; }}
.c-card.red .num {{ color: #e74c3c; }}
.c-card .desc {{ font-size: 9px; color: #888; }}

/* --- Charts --- */
.chart-block {{ margin-bottom: 18px; }}
.chart-block h4 {{
    font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px;
    color: rgba(255,255,255,0.4); margin: 0 0 8px;
}}
.chart-block img {{
    width: 100%; border-radius: 8px; border: 1px solid rgba(255,255,255,0.06);
}}

/* --- Tables --- */
.ap-table {{ width: 100%; border-collapse:separate; border-spacing:0; font-size:10px; }}
.ap-table thead th {{
    background: rgba(102,126,234,0.12); padding: 8px; text-align: left;
    font-weight: 600; font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px;
    color: rgba(255,255,255,0.6); position: sticky; top: 0;
}}
.ap-table thead th:first-child {{ border-radius: 6px 0 0 0; }}
.ap-table thead th:last-child {{ border-radius: 0 6px 0 0; }}
.ap-table td {{ padding: 7px 8px; border-bottom: 1px solid rgba(255,255,255,0.04); }}
.ap-table tbody tr:hover {{ background: rgba(255,255,255,0.03); }}

.radius-table {{ width:100%; border-collapse:separate; border-spacing:0 4px; font-size:10px; margin-top:6px; }}
.radius-table th {{
    background: rgba(102,126,234,0.12); padding: 6px 10px; text-align: left;
    font-weight: 600; font-size: 9px; text-transform: uppercase;
    color: rgba(255,255,255,0.6);
}}
.radius-table td {{
    padding: 6px 10px; background: rgba(255,255,255,0.01);
    border-bottom: 1px solid rgba(255,255,255,0.04);
}}
</style>

<div id="ap-sidebar">
    <div id="ap-toggle-tab" onclick="toggleSidebar()">
        <span class="arrow">▶</span>
    </div>

    <div class="ap-header">
        <h3>📊 Analytics Dashboard</h3>
        <p>Samdo 1-dong WebGIS</p>
    </div>

    <!-- Tabs -->
    <div class="ap-tabs">
        <div class="ap-tab active" onclick="switchTab(0,this)">Overview</div>
        <div class="ap-tab" onclick="switchTab(1,this)">Charts</div>
        <div class="ap-tab" onclick="switchTab(2,this)">Data</div>
    </div>

    <div class="ap-content">
        <!-- TAB 0: Overview -->
        <div class="ap-pane active">
            <div class="ov-hero">
                <div class="ov-ring">
                    <svg width="80" height="80" viewBox="0 0 100 100">
                        <circle cx="50" cy="50" r="45" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="8"/>
                        <circle cx="50" cy="50" r="45" fill="none" stroke="url(#ringGrad)" stroke-width="8"
                            stroke-dasharray="283" stroke-dashoffset="{dash_offset:.1f}"
                            stroke-linecap="round"/>
                        <defs><linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
                            <stop offset="0%" stop-color="#2ecc71"/><stop offset="100%" stop-color="#27ae60"/>
                        </linearGradient></defs>
                    </svg>
                    <div class="pct-label">{coverage_pct_val:.0f}%</div>
                    <div class="pct-sub">Coverage</div>
                </div>
                <div class="ov-summary">
                    <div class="big">{ana['n_in']}/{tot} Terjangkau</div>
                    <div class="sub">Restoran dalam radius 200m hotel</div>
                </div>
            </div>

            <div class="stat-row">
                <div class="s-card"><div class="v">{stats['min']}m</div><div class="l">Min Dist</div></div>
                <div class="s-card"><div class="v">{stats['max']}m</div><div class="l">Max Dist</div></div>
                <div class="s-card"><div class="v">{stats['mean']}m</div><div class="l">Rata-rata</div></div>
                <div class="s-card"><div class="v">{stats['median']}m</div><div class="l">Median</div></div>
            </div>

            <div class="count-row">
                <div class="c-card green">
                    <div class="ic">🟢</div>
                    <div><div class="num">{ana['n_in']}</div><div class="desc">Dalam Buffer</div></div>
                </div>
                <div class="c-card red">
                    <div class="ic">🔴</div>
                    <div><div class="num">{ana['n_out']}</div><div class="desc">Luar Buffer</div></div>
                </div>
            </div>

            <div class="chart-block">
                <h4>Multi-Radius Coverage</h4>
                <table class="radius-table">
                    <tr><th>Radius</th><th style="text-align:center">N Restoran</th><th style="text-align:center">Coverage</th></tr>
                    {radius_rows}
                </table>
            </div>
        </div>

        <!-- TAB 1: Charts -->
        <div class="ap-pane">
            <div class="chart-block">
                <h4>Komposisi Terjangkau vs Tidak</h4>
                <img src="data:image/png;base64,{ana['pie_b64']}" alt="Pie Chart">
            </div>
            <div class="chart-block">
                <h4>Multi-Radius Analysis</h4>
                <img src="data:image/png;base64,{ana['bar_b64']}" alt="Bar Chart">
            </div>
            <div class="chart-block">
                <h4>Distribusi Jarak ke Hotel Terdekat</h4>
                <img src="data:image/png;base64,{ana['hist_b64']}" alt="Histogram">
            </div>
        </div>

        <!-- TAB 2: Data Table -->
        <div class="ap-pane">
            <table class="ap-table">
                <thead><tr><th>Nama Restoran</th><th>Cuisine</th><th style="text-align:right">Jarak</th><th>Status</th></tr></thead>
                <tbody>{rest_detail_rows}</tbody>
            </table>
        </div>
    </div>
</div>

<script>
function toggleSidebar() {{
    var s = document.getElementById('ap-sidebar');
    s.classList.toggle('open');
}}
function switchTab(idx, el) {{
    var tabs = document.querySelectorAll('.ap-tab');
    var panes = document.querySelectorAll('.ap-pane');
    tabs.forEach(function(t){{ t.classList.remove('active'); }});
    panes.forEach(function(p){{ p.classList.remove('active'); }});
    el.classList.add('active');
    panes[idx].classList.add('active');
}}
</script>
"""
m.get_root().html.add_child(folium.Element(panel_html))

# === SAVE ===
out = BD / "samdo1_webgis_folium.html"
m.save(str(out))
print(f"\n[SUCCESS] Map saved: {out}")
