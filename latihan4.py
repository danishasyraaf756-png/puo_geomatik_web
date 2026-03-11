import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
import math
from pyproj import Transformer
import geopandas as gpd
from shapely.geometry import Polygon, Point
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
        # Menukar koordinat tempatan (RSO/Cassini) kepada WGS84 (Lat/Lon)
        return Transformer.from_crs(f"epsg:{epsg}", "epsg:4326", always_xy=True)
    except:
        return None

def kira_data_garisan(p1, p2):
    de, dn = p2['E'] - p1['E'], p2['N'] - p1['N']
    dist = math.sqrt(de**2 + dn**2)
    angle = math.degrees(math.atan2(de, dn)) % 360
    
    # Tukar kepada format DMS (Degree, Minute, Second)
    d = int(angle)
    m = int((angle - d) * 60)
    s = int((((angle - d) * 60) - m) * 60)
    brg_str = f"{d:03d}°{m:02d}'{s:02d}\""
    
    # Sudut rotasi untuk label teks pada peta
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
            # Penyelarasan koordinat dengan offset
            df_mod = df.copy()
            df_mod['E_adj'], df_mod['N_adj'] = df_mod['E'] + off_e, df_mod['N'] + off_n
            lons, lats = tf.transform(df_mod['E_adj'].values, df_mod['N_adj'].values)
            df['lat'], df['lon'] = lats, lons
            
            # Kira Luas menggunakan Shoelace Formula melalui Shapely
            area_m2 = Polygon(zip(df['E'], df['N'])).area
            
            # --- KONFIGURASI PETA ---
            m = folium.Map(location=[df['lat'].mean(), df['lon'].mean()], zoom_start=19, max_zoom=24)

            # Layer Base
            folium.TileLayer(
                tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", 
                attr="Google Satellite", max_zoom=24, name="Google Satelit"
            ).add_to(m)

            folium.TileLayer(
                tiles="https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", 
                attr="Google Roadmap", max_zoom=24, name="Google Jalan"
            ).add_to(m)

            # Kumpulan Ciri (Feature Groups)
            fg_lot = folium.FeatureGroup(name="Sempadan Lot (Poligon)")
            fg_labels = folium.FeatureGroup(name="Label Bering & Jarak")
            fg_stesen = folium.FeatureGroup(name="Marker Stesen")

            # Tambah Poligon Lot
            lot_html = f"<b>Info Lot</b><br>Luas: {area_m2:.3f} m²<br>Surveyor: {st.session_state['current_user']}"
            folium.Polygon(
                df[['lat', 'lon']].values.tolist(), 
                color="yellow", fill=True, fill_opacity=0.2, weight=3, 
                popup=folium.Popup(lot_html, max_width=200)
            ).add_to(fg_lot)

            points_for_geojson = []
            for i in range(len(df)):
                p1 = df.iloc[i]
                p2 = df.iloc[(i+1)%len(df)]
                brg, dist, rot = kira_data_garisan(p1, p2)
                
                # Marker Stesen (Bulatan Merah)
                folium.CircleMarker(
                    location=[p1['lat'], p1['lon']],
                    radius=6, color="white", weight=2, fill=True, fill_color="red", fill_opacity=1,
                    popup=f"<b>STN {p1['STN']}</b><br>E: {p1['E']}<br>N: {p1['N']}"
                ).add_to(fg_stesen)
                
                # Label Bering & Jarak di tengah garisan
                mid_lat, mid_lon = (p1['lat']+p2['lat'])/2, (p1['lon']+p2['lon'])/2
                html_label = f"""<div style="transform: rotate({rot}deg); white-space: nowrap; font-size: 8pt; color: #00FF00; font-weight: bold; text-shadow: 1px 1px 2px black; text-align: center; width: 100px; margin-left: -50px;">{brg}<br>{dist}m</div>"""
                folium.Marker([mid_lat, mid_lon], icon=folium.DivIcon(html=html_label)).add_to(fg_labels)

                # Data untuk GeoJSON
                points_for_geojson.append({
                    'geometry': Point(p1['lon'], p1['lat']),
                    'STN': str(p1['STN']),
                    'E_Asal': p1['E'], 'N_Asal': p1['N'],
                    'Bering_Ke_Next': brg, 'Jarak_Ke_Next': dist
                })

            # Masukkan semua lapisan ke dalam peta
            fg_lot.add_to(m)
            fg_stesen.add_to(m)
            fg_labels.add_to(m)
            folium.LayerControl(collapsed=False).add_to(m)

            # PAPARAN UTAMA
            st.title("🗺️ Pelan Geomatik Interaktif")
            st_folium(m, width="100%", height=600, returned_objects=[])
            
            # Statistik Ringkas
            c1, c2, c3 = st.columns(3)
            c1.metric("Luas (m²)", f"{area_m2:.3f}")
            c2.metric("Luas (Ekar)", f"{(area_m2 * 0.000247105):.4f}")
            c3.metric("Bilangan Stesen", len(df))

            # --- EKSPORT DATA GEOJSON ---
            st.divider()
            st.subheader("📥 Eksport & Jadual Data")
            
            # Bina fail GeoJSON
            gdf_pts = gpd.GeoDataFrame(points_for_geojson, crs="EPSG:4326")
            poly_geom = Polygon(zip(df['lon'], df['lat']))
            gdf_poly = gpd.GeoDataFrame({'STN': ['POLYGON_LOT'], 'Luas_m2': [round(area_m2,3)]}, geometry=[poly_geom], crs="EPSG:4326")
            geojson_out = pd.concat([gdf_poly, gdf_pts], ignore_index=True).to_json()

            st.download_button(
                label="💾 Muat Turun GeoJSON (GIS Ready)", 
                data=geojson_out, 
                file_name=f"Survey_Lot_{st.session_state['current_user']}.geojson",
                mime="application/json"
            )

            st.dataframe(df[['STN', 'E', 'N', 'lat', 'lon']].style.format(precision=3), use_container_width=True)

        else:
            st.error("Ralat EPSG: Kod tidak dikenali.")
    except Exception as e:
        st.error(f"Ralat Pemprosesan: Pastikan kolum CSV adalah STN, E, N. Error: {e}")
else:
    st.info("Sila muat naik fail CSV koordinat di sidebar untuk memulakan pemetaan.")
