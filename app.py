import os
import pandas as pd
import geopandas as gpd
import numpy as np
import json

from dash import Dash, dcc, html, Input, Output, dash_table
import plotly.express as px

# ----- Cargar datos (intento automático, con fallback sintético) -----
shapefile_vih = os.path.join("VIH","Casos_notificados_VIH_-_SIDA.shp")
shapefile_co = os.path.join("coordenadas","COLOMBIA","COLOMBIA.shp")

def load_data():
    # Intentar leer los shapefiles del notebook original
    if os.path.exists(shapefile_vih) and os.path.exists(shapefile_co):
        gdf_vih = gpd.read_file(shapefile_vih, encoding="utf-8")
        gdf_co = gpd.read_file(shapefile_co, encoding="utf-8")
        # Merge esperado en el notebook original por código: DPTO_CCDGO <-> DANE
        try:
            gdf_co["DPTO_CCDGO"] = gdf_co["DPTO_CCDGO"].astype(str).str.zfill(2)
            gdf_vih["DANE"] = gdf_vih["DANE"].astype(str).str.zfill(2)
            gdf_merged = gdf_co.merge(gdf_vih, left_on="DPTO_CCDGO", right_on="DANE", how="left")
            gdf_merged = gpd.GeoDataFrame(gdf_merged, geometry="geometry", crs=gdf_co.crs)
        except Exception as e:
            print("Advertencia merge real:", e)
            gdf_merged = gdf_vih
        return gdf_merged
    else:
        # Fallback: usar dataset 'naturalearth_lowres' y generar datos sintéticos para Colombia por departamento aproximado
        world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
        colombia = world[world["iso_a3"]=="COL"].copy()
        # crear departamentos sintéticos: duplicar geometría en 10 "departamentos" por subdivisión aproximada por centroid offsets
        geoms = []
        for i in range(1,11):
            row = colombia.iloc[0].copy()
            row["DPTO_CCDGO"] = str(i).zfill(2)
            row["name"] = f"Depto_{i}"
            # Slightly buffer/scale to create variations (not realistic, only demo)
            geoms.append(row)
        gdf = gpd.GeoDataFrame(geoms, crs=colombia.crs)
        # Añadir columnas de años 2009-2012 con valores sintéticos
        np.random.seed(42)
        for year in range(2009,2013):
            gdf[f"Ano{year}"] = np.random.poisson(lam=100* (year-2008), size=len(gdf))
        gdf["Casos"] = gdf[[f"Ano{y}" for y in range(2009,2013)]].sum(axis=1)
        return gdf

gdf = load_data()

# Preparar datos para la app
years = ["2009","2010","2011","2012","2009-2012"]
def compute_metric(df, year):
    if year == "2009-2012":
        val = df["Casos"]
    else:
        col = "Ano" + year
        if col in df.columns:
            val = df[col]
        else:
            # si no existe, devolver NaN
            val = pd.Series([np.nan]*len(df))
    return val

gdf = gdf.reset_index(drop=True)

# crear GeoJSON sencillo para el mapa (Plotly acepta GeoPandas directly but we'll export geojson)
geojson = json.loads(gdf.to_json())

# ----- Dash App -----
app = Dash(__name__, suppress_callback_exceptions=True)
server = app.server

app.layout = html.Div([
    html.H2("Dashboard georreferenciado — Taller: Casos VIH (demo)"),
    html.Div([
        html.Label("Año / rango"),
        dcc.Dropdown(id="year-dropdown", options=[{"label":y,"value":y} for y in years], value="2009-2012"),
    ], style={"width":"200px","display":"inline-block","verticalAlign":"top","marginRight":"20px"}),
    html.Div([
        html.Label("Vista"),
        dcc.Dropdown(id="view-dropdown", options=[{"label":"Mapa choropleth","value":"choropleth"},{"label":"Mapa de círculos proporcionales","value":"bubbles"}], value="bubbles"),
    ], style={"width":"260px","display":"inline-block","verticalAlign":"top"}),
    html.Div(id="kpis", style={"display":"flex","gap":"20px","marginTop":"15px"}),
    html.Div([
        dcc.Graph(id="map-graph", style={"height":"600px"})
    ], style={"width":"65%","display":"inline-block","verticalAlign":"top"}),
    html.Div([
        html.H4("Tabla de departamentos (Top 10)"),
        dash_table.DataTable(id="table", page_size=10,
                             columns=[{"name":"DPTO_CCDGO","id":"DPTO_CCDGO"},{"name":"Departamento","id":"name"},{"name":"Casos","id":"Casos"}],
                             style_table={"overflowX":"auto"})
    ], style={"width":"32%","display":"inline-block","verticalAlign":"top","paddingLeft":"10px"})
], style={"fontFamily":"Arial, sans-serif", "margin":"20px"})

# Callbacks
@app.callback(
    Output("map-graph","figure"),
    Output("kpis","children"),
    Output("table","data"),
    Input("year-dropdown","value"),
    Input("view-dropdown","value")
)
def update_dashboard(year, view):
    df = gdf.copy()
    metric = compute_metric(df, year)
    df["metric"] = metric.fillna(0)
    # KPIs
    total = int(df["metric"].sum())
    mean = float(df["metric"].mean())
    max_depto = df.loc[df["metric"].idxmax()]["name"] if len(df)>0 else ""
    kpi_children = [
        html.Div([html.H5("Total de casos"), html.P(f"{total:,}")], style={"padding":"10px","border":"1px solid #ddd","borderRadius":"6px"}),
        html.Div([html.H5("Promedio por departamento"), html.P(f"{mean:,.1f}")], style={"padding":"10px","border":"1px solid #ddd","borderRadius":"6px"}),
        html.Div([html.H5("Departamento con más casos"), html.P(f"{max_depto}")], style={"padding":"10px","border":"1px solid #ddd","borderRadius":"6px"}),
    ]

    # Table data
    table_df = df[["DPTO_CCDGO","name","metric"]].rename(columns={"metric":"Casos"}).sort_values("Casos", ascending=False).head(10)
    table_data = table_df.to_dict("records")

    # Map
    if view == "choropleth":
        fig = px.choropleth(df, geojson=geojson, locations=df.index, color="metric",
                            hover_name="name", projection="mercator")
        fig.update_geos(fitbounds="locations", visible=False)
    else:
        # bubbles: use centroids
        df_cent = df.copy()
        df_cent["lon"] = df_cent.geometry.centroid.x
        df_cent["lat"] = df_cent.geometry.centroid.y
        fig = px.scatter_geo(df_cent, lon="lon", lat="lat", size="metric",
                             hover_name="name", projection="natural earth")
        fig.update_geos(fitbounds="locations", visible=False)

    fig.update_layout(margin={"r":0,"t":30,"l":0,"b":0}, title_text=f"Casos VIH - {year} - Vista: {view}")
    return fig, kpi_children, table_data

if __name__ == "__main__":
    app.run_server(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8050)))