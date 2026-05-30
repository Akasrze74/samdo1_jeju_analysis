# -*- coding: utf-8 -*-
"""
Analytics module: pandas + matplotlib charts for WebGIS
Generates base64-encoded PNG charts for embedding in HTML
"""
import math
import base64
import io
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.size': 10,
    'figure.facecolor': '#1a1a2e',
    'axes.facecolor': '#16213e',
    'text.color': '#e0e0e0',
    'axes.labelcolor': '#e0e0e0',
    'xtick.color': '#aaa',
    'ytick.color': '#aaa',
})

def haversine(lon1, lat1, lon2, lat2):
    R = 6371000
    p = math.pi / 180
    a = (math.sin((lat2-lat1)*p/2)**2 +
         math.cos(lat1*p)*math.cos(lat2*p)*math.sin((lon2-lon1)*p/2)**2)
    return 2*R*math.asin(math.sqrt(a))

def fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=110, bbox_inches='tight',
                facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')

def build_dataframes(hotels_feats, rest_feats):
    """Build pandas DataFrames for hotels and restaurants."""
    h_rows = []
    for f in hotels_feats:
        p = f['properties']
        c = f['geometry']['coordinates']
        h_rows.append({
            'name': p.get('name','?'), 'name_en': p.get('name:en',''),
            'lon': c[0], 'lat': c[1]
        })
    r_rows = []
    for f in rest_feats:
        p = f['properties']
        c = f['geometry']['coordinates']
        r_rows.append({
            'name': p.get('name','?'), 'name_en': p.get('name:en',''),
            'cuisine': p.get('cuisine','-') or '-',
            'lon': c[0], 'lat': c[1]
        })
    return pd.DataFrame(h_rows), pd.DataFrame(r_rows)

def calc_distances(df_hotels, df_restaurants):
    """Calculate nearest hotel distance for each restaurant."""
    dists, nearest = [], []
    for _, r in df_restaurants.iterrows():
        min_d, min_n = float('inf'), ''
        for _, h in df_hotels.iterrows():
            d = haversine(r['lon'], r['lat'], h['lon'], h['lat'])
            if d < min_d:
                min_d, min_n = d, h['name']
        dists.append(round(min_d, 1))
        nearest.append(min_n)
    df_restaurants = df_restaurants.copy()
    df_restaurants['dist_nearest_hotel_m'] = dists
    df_restaurants['nearest_hotel'] = nearest
    df_restaurants['in_buffer_200m'] = [d <= 200 for d in dists]
    return df_restaurants

def multi_radius_analysis(df_rest):
    """Count restaurants within various buffer radii."""
    radii = [100, 200, 300, 500, 750, 1000]
    rows = []
    total = len(df_rest)
    for r in radii:
        n = int((df_rest['dist_nearest_hotel_m'] <= r).sum())
        rows.append({'Radius (m)': r, 'N Restoran': n,
                     'Coverage (%)': round(100*n/max(1,total),1)})
    return pd.DataFrame(rows)

def chart_pie(n_in, n_out):
    fig, ax = plt.subplots(figsize=(2.8, 2.8))
    sizes = [n_in, n_out]
    colors = ['#2ecc71', '#e74c3c']
    explode = (0.04, 0.04)
    wedges, texts, autotexts = ax.pie(
        sizes, explode=explode, colors=colors, autopct='%1.0f%%',
        startangle=90, textprops={'fontsize':11, 'fontweight':'bold', 'color':'white'},
        wedgeprops={'edgecolor':'#1a1a2e', 'linewidth':1.5})
    ax.legend(['Dalam Buffer', 'Luar Buffer'], loc='lower center',
              fontsize=7, ncol=2, framealpha=0.3,
              bbox_to_anchor=(0.5, -0.06))
    ax.set_title('Komposisi Restoran\nTerjangkau vs Tidak', fontsize=10,
                 fontweight='bold', pad=8)
    return fig_to_base64(fig)

def chart_multi_radius(df_radius):
    fig, ax = plt.subplots(figsize=(3.2, 2.4))
    bars = ax.bar(df_radius['Radius (m)'].astype(str),
                  df_radius['N Restoran'],
                  color=['#3498db','#2ecc71','#f39c12','#e67e22','#9b59b6','#1abc9c'],
                  edgecolor='#1a1a2e', linewidth=1, width=0.6)
    for bar, pct in zip(bars, df_radius['Coverage (%)']):
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.12,
                f'{pct:.0f}%', ha='center', va='bottom', fontsize=7,
                fontweight='bold', color='#e0e0e0')
    ax.set_xlabel('Radius (m)', fontsize=8)
    ax.set_ylabel('Restoran', fontsize=8)
    ax.set_title('Multi-Radius Analysis', fontsize=10, fontweight='bold', pad=6)
    ax.set_ylim(0, max(df_radius['N Restoran'])+1.5)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.tick_params(labelsize=7)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#444')
    ax.spines['bottom'].set_color('#444')
    fig.tight_layout()
    return fig_to_base64(fig)

def chart_distance_hist(df_rest):
    fig, ax = plt.subplots(figsize=(3.2, 2.4))
    dists = df_rest['dist_nearest_hotel_m']
    ax.hist(dists, bins=8, color='#3498db', edgecolor='#1a1a2e',
            linewidth=1, alpha=0.85)
    ax.axvline(200, color='#e74c3c', linewidth=1.5, linestyle='--', label='Buffer 200m')
    ax.axvline(dists.mean(), color='#f1c40f', linewidth=1.5, linestyle='-', label=f'Mean={dists.mean():.0f}m')
    ax.set_xlabel('Jarak (m)', fontsize=8)
    ax.set_ylabel('Restoran', fontsize=8)
    ax.set_title('Distribusi Jarak Restoran-Hotel', fontsize=10, fontweight='bold', pad=6)
    ax.legend(fontsize=7, framealpha=0.3)
    ax.tick_params(labelsize=7)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#444')
    ax.spines['bottom'].set_color('#444')
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    fig.tight_layout()
    return fig_to_base64(fig)

def build_stats_html(df_rest):
    d = df_rest['dist_nearest_hotel_m']
    return {
        'min': f'{d.min():.0f}', 'max': f'{d.max():.0f}',
        'mean': f'{d.mean():.0f}', 'median': f'{d.median():.0f}',
        'std': f'{d.std():.0f}'
    }

def generate_all(hotels_feats, rest_feats):
    """Main entry: returns dict with all analytics data."""
    df_h, df_r = build_dataframes(hotels_feats, rest_feats)
    df_r = calc_distances(df_h, df_r)
    df_radius = multi_radius_analysis(df_r)
    n_in = int(df_r['in_buffer_200m'].sum())
    n_out = len(df_r) - n_in
    stats = build_stats_html(df_r)
    print("[INFO] Generating charts with matplotlib...")
    return {
        'pie_b64': chart_pie(n_in, n_out),
        'bar_b64': chart_multi_radius(df_radius),
        'hist_b64': chart_distance_hist(df_r),
        'stats': stats,
        'df_radius': df_radius,
        'df_rest': df_r,
        'n_in': n_in, 'n_out': n_out,
    }
