import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
import math
from pyproj import Transformer
import geopandas as gpd
from shapely.geometry import Polygon, Point, LineString
import json

# 1. KONFIGURASI HALAMAN
st.set_page_config(page_title="PUO Geomatics Pro", layout="wide")

LOGO_URL = "https://th.bing.com/th/id/R.7845becf994d6c6a0b2afe8147ecbbf4?rik=l%2bMV7v5yBzHn5g&riu=http%3a%2f%2f1.bp.blogspot.com%2f-wQXM8Oe-ImA%2fTXrQ7Npc7uI%2fAAAAAAAAE34%2f2ref_vtbT5k%2fs1600%2fPoliteknik%252BUngku%252BOmar.png&ehk=IjCxLkjx3O7Lb2LSgWsvprPJ5Dvm%2fAHQVB35yucEm6Q%3d&risl=&pid=ImgRaw&r=0"

# 2. SISTEM LOGIN
def load_users():
    usernames = ["ASYRAAF", "1", "2"]
    password_tetap = "admin1234"
    return {u: password_tetap for u in usernames}

if "user_db" not in st.session_state:
    st.session_state["user_db"] = load_users()
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "current_user" not in st.session_state:
    st.session_state["current_user"] = ""

def auth_interface():
    _, col2, _ = st.columns([1, 1.8, 1])
    with col2:
        st.markdown(f"<div style='text-align: center;'><br><img src='{LOGO_URL}' width='80'><h2>Sistem Geomatik PUO</h2><p>Sila log masuk untuk mula</p></div>", unsafe_allow_html=True)
        with st.form("login_form"):
            u_id = st.text_input("ID PENGGUNA").upper()
            u_pw = st.text_input("KATA LALUAN", type="password")
            if st.form_submit_button("Masuk", use_container_width=True):
                if u_id in st.session_state["user_db"] and st.session_state["user_db"][u_id] == u_pw:
                    st.session_state["logged_in"] = True
                    st.session_state["current_user"] = u_id
                    st.rerun()
                else:
                    st.error("ID atau Kata Laluan salah!")

if not st.session_state["logged_in"]:
    auth_interface()
    st.stop()

# --- FUNGSI GEOMETRI ---
@st.cache_resource
def get_transformer(epsg):
    try:
        return Transformer.from_crs(f"epsg:{epsg}", "epsg:4326", always_xy=True)
    except:
        return None

def kira_data_garisan(p1, p2):
    de, dn = p2['E'] - p1['E'], p2['N'] - p1['N']
    dist = math.sqrt(de**2 + dn**2)
    angle = math.degrees(math.atan2(de, dn)) % 360
    
    # Format DMS
    d = int(angle)
    m = int((angle - d) * 60)
    s = int((((angle - d) * 60) - m) * 60)
    brg_str = f"{d:03d}°{m:02d}'{s:02d}\""
    
    # Rotasi teks
    rot_angle = angle - 90
    if 90 < angle < 270: rot_angle += 180
    return brg_str, round(dist, 3), rot_angle

# 3. SIDEBAR
st.sidebar.markdown(f"👤 **Pengguna:** `{st.session_state['current_user']}`")
if st.sidebar.button("🚪 Log Keluar"):
    st.session_state["logged_in"] = False
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("🎯 Penentukuran (Offset)")
off_n = st.sidebar.slider("Utara/Selatan (m)", -30.0, 30.0, 0.0)
off_e = st.sidebar.slider("Timur/Barat (m)", -30.0, 30.0, 0.0)
epsg_input = st.sidebar.text_input("Kod EPSG (RSO: 3168 / Cassini: 4390)", value="4390")

# 4. LOGIK UTAMA
uploaded_file = st.sidebar.file_uploader("Muat naik CSV (Format: STN, E, N)", type=["csv"])

if uploaded_file:
    try:
        df = pd.read_csv(uploaded_file)
        tf = get_transformer(epsg_input)
        
        if tf:
            df_mod = df.copy()
            df_mod['E_adj'], df_mod['N_adj'] = df_mod['E'] + off_e, df_mod['N'] + off_n
            lons, lats = tf.transform(df_mod['E_adj'].values, df_mod['N_adj'].values)
            df['lat'], df['lon'] = lats, lons
            
            area_m2 = Polygon(zip(df['E'], df['N'])).area
            
            # --- KONFIGURASI PETA ---
            m = folium.Map(location=[df['lat'].mean(), df['lon'].mean()], zoom_start=19, max_zoom=24)
            folium.TileLayer(tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", attr="Google Satellite", name="Google Satelit", max_zoom=24).add_to(m)
            folium.TileLayer(tiles="https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", attr="Google Roadmap", name="Google Jalan", max_zoom=24).add_to(m)

            fg_lot = folium.FeatureGroup(name="Sempadan Lot (Poligon)")
            fg_labels = folium.FeatureGroup(name="Label Bering & Jarak")
            fg_stesen = folium.FeatureGroup(name="Marker Stesen")

            # Data untuk GeoJSON
            points_data = []
            lines_data = []

            for i in range(len(df)):
                p1, p2 = df.iloc[i], df.iloc[(i+1)%len(df)]
                brg, dist, rot = kira_data_garisan(p1, p2)
                
                # Visualisasi Poligon & Label
                mid_lat, mid_lon = (p1['lat']+p2['lat'])/2, (p1['lon']+p2['lon'])/2
                html_label = f"""<div style="transform: rotate({rot}deg); white-space: nowrap; font-size: 8pt; color: #00FF00; font-weight: bold; text-shadow: 1px 1px 2px black; text-align: center; width: 100px; margin-left: -50px;">{brg}<br>{dist}m</div>"""
                folium.Marker([mid_lat, mid_lon], icon=folium.DivIcon(html=html_label)).add_to(fg_labels)
                
                folium.CircleMarker(location=[p1['lat'], p1['lon']], radius=6, color="white", weight=2, fill=True, fill_color="red", fill_opacity=1, popup=f"STN {p1['STN']}").add_to(fg_stesen)

                # Simpan Data GIS
                points_data.append({'geometry': Point(p1['lon'], p1['lat']), 'STN': str(p1['STN']), 'E': p1['E'], 'N': p1['N'], 'Jenis': 'Stesen'})
                lines_data.append({'geometry': LineString([(p1['lon'], p1['lat']), (p2['lon'], p2['lat'])]), 'Dari': str(p1['STN']), 'Ke': str(p2['STN']), 'Bering': brg, 'Jarak_m': dist, 'Jenis': 'Line_Traverse'})

            folium.Polygon(df[['lat', 'lon']].values.tolist(), color="yellow", fill=True, fill_opacity=0.2, weight=3).add_to(fg_lot)
            
            fg_lot.add_to(m); fg_stesen.add_to(m); fg_labels.add_to(m)
            folium.LayerControl(collapsed=False).add_to(m)

            # PAPARAN
            st.title("🗺️ PUO Geomatics Pro")
            st_folium(m, width="100%", height=600, returned_objects=[])
            
            # --- EKSPORT & JADUAL ---
            st.divider()
            col_a, col_b = st.columns([1, 2])
            
            with col_a:
                st.subheader("📥 Eksport Fail")
                gdf_pts = gpd.GeoDataFrame(points_data, crs="EPSG:4326")
                gdf_lines = gpd.GeoDataFrame(lines_data, crs="EPSG:4326")
                gdf_poly = gpd.GeoDataFrame({'STN': ['LOT_UTAMA'], 'Luas_m2': [round(area_m2,3)], 'Jenis': ['Poligon_Lot']}, geometry=[Polygon(zip(df['lon'], df['lat']))], crs="EPSG:4326")
                
                final_geojson = pd.concat([gdf_poly, gdf_lines, gdf_pts], ignore_index=True).to_json()
                
                st.download_button(label="💾 Muat Turun GeoJSON (PRO)", data=final_geojson, file_name=f"Geomatics_{st.session_state['current_user']}.geojson", mime="application/json")
                st.metric("Luas (m²)", f"{area_m2:.3f}")

            with col_b:
                st.subheader("📊 Data Sempadan")
                st.dataframe(gdf_lines[['Dari', 'Ke', 'Bering', 'Jarak_m']], use_container_width=True)

        else:
            st.error("Kod EPSG salah.")
    except Exception as e:
        st.error(f"Ralat: {e}")
else:
    st.info("Sila muat naik CSV di sidebar.")
