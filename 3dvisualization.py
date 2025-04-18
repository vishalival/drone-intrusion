import pandas as pd
import pydeck as pdk

# === 1. Load drone data ===
df_ohare = pd.read_csv("ohare.csv")

# === 2. Clean drone data ===
# Drop any unnecessary columns if needed
if 'geometry' in df_ohare.columns:
    df_ohare = df_ohare.drop(columns='geometry')

# Convert summary to string
df_ohare['summary'] = df_ohare['summary'].astype(str)

# Handle any missing values
df_ohare = df_ohare.dropna(subset=["drone_latitude", "drone_longitude", "drone_altitude_ft"])

# Optional: Clip extreme altitudes for better visuals
df_ohare["alt_scaled"] = df_ohare["drone_altitude_ft"].clip(upper=6000)

# === 3. Define base view centered on O'Hare ===
INITIAL_VIEW_STATE = pdk.ViewState(
    latitude=41.9742,
    longitude=-87.9073,
    zoom=10,
    pitch=60,
    bearing=0,
)

# === 4. Define airspace GeoJsonLayer ===
airspace_layer = pdk.Layer(
    "GeoJsonLayer",
    "ohare_airspace.geojson",
    stroked=False,
    filled=True,
    extruded=True,
    wireframe=True,
    get_elevation="elevation",
    get_fill_color="[0, 0, 200, 80]",
    get_line_color=[0, 0, 0],
    pickable=True,
)

# === 5. Define drone ScatterplotLayer ===
drone_layer = pdk.Layer(
    "ScatterplotLayer",
    df_ohare,
    get_position=["drone_longitude", "drone_latitude"],
    get_elevation="alt_scaled",
    get_radius=200,
    get_fill_color=[255, 0, 0, 160],
    pickable=True,
    auto_highlight=True,
)

# === 6. Assemble and export the map ===
r = pdk.Deck(
    layers=[airspace_layer, drone_layer],
    initial_view_state=INITIAL_VIEW_STATE,
    tooltip={"text": "Drone: {summary}"}
)

# Save to HTML
r.to_html("ohare_3d_airspace_map.html")

print("✅ Map saved as 'ohare_3d_airspace_map.html'. Open it in a browser to explore!")
