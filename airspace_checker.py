import streamlit as st
import re
import pandas as pd
import numpy as np
from shapely.geometry import Point, Polygon
from shapely.ops import nearest_points
from geopy import Point as GeoPoint
from geopy.distance import distance
import geopandas as gpd
from zipfile import ZipFile
import pydeck as pdk
from fuzzywuzzy import process, fuzz

'''
This script analyzes drone sighting reports and checks for intersections with controlled airspace.
It uses the FAA summary text to extract location and altitude information, then checks against airspace polygons.
It visualizes the results using pydeck.
The script requires the following libraries:
- streamlit
- pandas
- numpy
- shapely
- geopy
- geopandas
- pydeck
- fuzzywuzzy   

Author: Vishali Vallioor

MUST BE RUN IN A TERMINAL WITH THE FOLLOWING COMMAND:
streamlit run airspace_checker.py
PLEASE MAKE SURE TO HAVE THE FOLLOWING FILES IN THE SAME DIRECTORY:
- all-airport-data.xlsx.zip
- airspaces.geojson
- all-airport-data.xlsx
- all-airport-data.xlsx.zip
- airspaces.geojson
- all-airport-data.xlsx
- all-airport-data.xlsx.zip
- airspaces.geojson

PLEASE DOWNLOAD TO THE TERMINAL TO USE.
'''

st.title("🚈 Drone Sighting Airspace Analyzer")

sample_string = st.text_area("Paste FAA summary text:", """PRELIM INFO FROM FAA OPS: NASHVILLE, TN/UAS INCIDENT/1205C/\nNASHVILLE APCH ADVISED CESSNA C650, REPORTED A WHITE UAS FROM THE 10 O'CLOCK \nPOSITION WHILE NE BOUND AT 4,000 FEET 10 SE NASHVILLE. NO EVASIVE ACTION \nREPORTED. NASHVILLE ARPT PD NOTIFIED. WOC 7-3333 DJ/ER""")

show_airspace = st.checkbox("Show Airspace Polygons", value=True)

if sample_string:
    with ZipFile("all-airport-data.xlsx.zip") as z:
        with z.open("all-airport-data.xlsx") as f:
            airport_codes_2 = pd.read_excel(f)

    airport_trimmed = airport_codes_2.rename(columns={
        "Loc Id": "faa_code",
        "ARP Latitude DD": "latitude",
        "ARP Longitude DD": "longitude",
        "Name": "Facility Name",
        "State Id": "state"
    }).dropna(subset=["latitude", "longitude"])

    def extract_city_state(summary):
        match = re.search(r'FROM FAA OPS:\s+([A-Z\s]+),\s+([A-Z]{2})', summary.upper())
        return f"{match.group(1).title()} {match.group(2)}" if match else None

    facility = extract_city_state(sample_string)
    latitude = longitude = np.nan

    if facility is not None:
        try:
            city_part, state_part = facility.rsplit(" ", 1)
            filtered_airports = airport_trimmed[
                (airport_trimmed["state"].str.upper() == state_part.upper()) &
                (airport_trimmed["Facility Type"].str.upper().str.contains("AIRPORT"))
            ]
            matched_facility = process.extractOne(
                city_part,
                filtered_airports["Facility Name"].dropna().unique().tolist(),
                scorer=fuzz.token_set_ratio
            )[0]
            origin_row = filtered_airports[filtered_airports["Facility Name"] == matched_facility].iloc[0]
            latitude = origin_row["latitude"]
            longitude = origin_row["longitude"]
        except:
            pass

    def extract_location(summary):
        match = re.search(r'([0-9]+(?:\.\d+)?)\s+(N|NE|E|SE|S|SW|W|NW)\b', summary.upper())
        return f"{match.group(1)} {match.group(2)}" if match else None

    def extract_altitude(summary):
        match = re.search(r'([0-9,]+)\s+FEET', summary.upper())
        return int(match.group(1).replace(",", "")) if match else np.nan

    location_cleaned = extract_location(sample_string)
    altitude = extract_altitude(sample_string)

    DIRECTION_TO_BEARING = {
        "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90, "ESE": 112.5, "SE": 135,
        "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5, "W": 270, "WNW": 292.5,
        "NW": 315, "NNW": 337.5
    }

    def compute_3d_coordinates(loc_cleaned, lat, lon, alt):
        try:
            dist_nm, direction = loc_cleaned.split()
            bearing = DIRECTION_TO_BEARING.get(direction.upper())
            dist_km = float(dist_nm) * 1.852
            origin = GeoPoint(lat, lon)
            dest = distance(kilometers=dist_km).destination(origin, bearing)
            return dest.latitude, dest.longitude, alt
        except:
            return np.nan, np.nan, np.nan

    final_lat, final_lon, final_alt = compute_3d_coordinates(location_cleaned, latitude, longitude, altitude)

    drone_point_2d = Point(final_lon, final_lat)

    gdf_airspace = gpd.read_file("airspaces.geojson")
    gdf_airspace["coordinates"] = gdf_airspace["geometry"].apply(lambda poly: [[list(pt) for pt in poly.exterior.coords]])
    gdf_airspace["elevation"] = gdf_airspace["max_altitude"]

    intersecting_airspaces = gdf_airspace[gdf_airspace.geometry.contains(drone_point_2d)]

    if not intersecting_airspaces.empty:
        st.error("\u26a0\ufe0f Drone intersects the following airspace(s):")
        st.dataframe(intersecting_airspaces[["airspace_name", "min_altitude", "max_altitude"]])
    else:
        st.success("\u2705 Drone is not inside any known controlled airspace.")

        gdf_airspace["distance_km"] = gdf_airspace.geometry.centroid.distance(drone_point_2d)
        gdf_airspace_sorted = gdf_airspace.sort_values("distance_km")
        nearest = gdf_airspace_sorted.iloc[0]
        distance_km = nearest["distance_km"] * 111  # rough conversion degrees to km

        if distance_km < 25:
            st.info(f"Nearest airspace: {nearest['airspace_name']} ({distance_km:.2f} km away)")

    df_intrusion = pd.DataFrame([{
        "longitude": final_lon,
        "latitude": final_lat,
        "alt_scaled": final_alt * 0.3048
    }])

    sighting_layer = pdk.Layer(
        "ColumnLayer",
        data=df_intrusion,
        get_position='[longitude, latitude]',
        get_elevation='alt_scaled',
        elevation_scale=1.2,
        radius=300,
        get_fill_color='[255, 255, 0, 255]',  # Fully opaque yellow
        elevation_range=[1, 10000],  # Starts above polygon base
        extruded=True,
        pickable=True,
        auto_highlight=True
    )

    polygon_layer = pdk.Layer(
        "PolygonLayer",
        data=gdf_airspace,
        get_polygon="coordinates",
        get_fill_color="[200, 30, 0, 50]",
        get_elevation="elevation",
        elevation_scale=1,
        extruded=True,
        pickable=True,
        get_line_color='[255, 255, 255]',
        get_text='airspace_name',
        tooltip=True
    )

    view_state = pdk.ViewState(
        latitude=final_lat,
        longitude=final_lon,
        zoom=9,
        pitch=60
    )

    layers_to_render = [polygon_layer, sighting_layer] if show_airspace else [sighting_layer]
    layers_to_render.insert(0, polygon_layer)

    r = pdk.Deck(
        layers=layers_to_render,
        initial_view_state=view_state,
        tooltip={"html": "<b>Airspace:</b> {airspace_name}"}
    )

    st.pydeck_chart(r)
