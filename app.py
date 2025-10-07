import os
import pandas as pd
import geopandas as gpd
import numpy as np
import json

from dash import Dash, dcc, html, Input, Output, dash_table
import plotly.express as px

# --- Rutas a archivos ---
shapefile_vih = "data/vih.geojson"
shapefile_co = "data/colombia_simplificado.geojson"

# --- Cargar datos ---
gdf_vih = gpd.read_file(shapefile_vih)
gdf_co = gpd.read_file(shapefile_co)

# --- Intentar merge ---
try:
    gdf_co["DPTO_CCDGO"] = gdf_co["DPTO_CCDGO"].astype(str).str.zfill(2)
    gdf_vih["DANE"] = gdf_vih["DANE"].astype(str).str.zfill(2)
    gdf_merged = gdf_co.merge(gdf_vih, left_on="DPTO_CCDGO", right_on="DANE", how="left")
    gdf_merged = gpd.GeoDataFrame(gdf_merged, geometry="geometry", crs=gdf_co.crs)
except Exception as e:
    print("⚠️ Advertencia en el merge:", e)
    gdf_merged = gdf_vih.copy()

# --- Preparar datos para la app ---
years = ["2009", "2010", "2011", "2012", "2009-2012"]

def compute_metric(df, year):
    if year == "2009-2012":
        val = df["Casos"]
    else:
        col = "Ano" + year
        if col in df.columns:
            val = df[col]
        else:
            # si no existe, devolver NaN
            val = pd.Series([np.nan] * len(df))
    return val

gdf = gdf_merged.reset_index(drop=True)

# Crear GeoJSON para el mapa
geojson = json.loads(gdf.to_json())

# --- Dash App ---
app = Dash(__name__, suppress_callback_exceptions=True)
server = app.server

app.layout = html.Div([
    html.H2("Dashboard georreferenciado — Taller: Casos VIH (demo)"),

    html.Div([
        html.Label("Año / rango"),
        dcc.Dropdown(
            id="year-dropdown",
            options=[{"label": y, "value": y} for y in years],
            value="2009-2012"
        ),
    ], style={"width": "200px", "display": "inline-block", "verticalAlign": "top", "marginRight": "20px"}),

    html.Div([
        html.Label("Vista"),
        dcc.Dropdown(
            id="view-dropdown",
            options=[
                {"label": "Mapa choropleth", "value": "choropleth"},
                {"label": "Mapa de círculos proporcionales", "value": "bubbles"}
            ],
            value="bubbles"
        ),
    ], style={"width": "260px", "display": "inline-block", "verticalAlign": "top"}),

    html.Div(id="kpis", style={"display": "flex", "gap": "20px", "marginTop": "15px"}),

    html.Div([
        dcc.Graph(id="map-graph", style={"height": "600px"})
    ], style={"width": "65%", "display": "inline-block", "verticalAlign": "top"}),

    html.Div([
        html.H4("Tabla de departamentos (Top 10)"),
        dash_table.DataTable(
            id="table",
            page_size=10,
            columns=[
                {"name": "DPTO_CCDGO", "id": "DPTO_CCDGO"},
                {"name": "Departamento", "id": "name"},
                {"name": "Casos", "id": "Casos"}
            ],
            style_table={"overflowX": "auto"}
        )
    ], style={"width": "32%", "display": "inline-block", "verticalAlign": "top", "paddingLeft": "10px"})
], style={"fontFamily": "Arial, sans-serif", "margin": "20px"})


# --- Callbacks ---
@app.callback(
    Output("map-graph", "figure"),
    Output("kpis", "children"),
    Output("table", "data"),
    Input("year-dropdown", "value"),
    Input("view-dropdown", "value")
)
def update_dashboard(year, view):
    df = gdf.copy()
    metric = compute_metric(df, year)
    df["metric"] = metric.fillna(0)

    # KPIs
    total = int(df["metric"].sum())
    mean = float(df["metric"].mean())
    max_depto = df.loc[df["metric"].idxmax(), "name"] if len(df) > 0 else ""
    kpi_children = [
        html.Div([
            html.H5("Total de casos"),
            html.P(f"{total:,}")
        ], style={"padding": "10px", "border": "1px solid #ddd", "borderRadius": "6px"}),

        html.Div([
            html.H5("Promedio por departamento"),
            html.P(f"{mean:,.1f}")
        ], style={"padding": "10px", "border": "1px solid #ddd", "borderRadius": "6px"}),

        html.Div([
            html.H5("Departamento con más casos"),
            html.P(f"{max_depto}")
        ], style={"padding": "10px", "border": "1px solid #ddd", "borderRadius": "6px"}),
    ]

    # Tabla
    table_df = df[["DPTO_CCDGO", "name", "metric"]].rename(columns={"metric": "Casos"}).sort_values("Casos", ascending=False).head(10)
    table_data = table_df.to_dict("records")

    # Mapa
    if view == "choropleth":
        fig = px.choropleth(
            df,
            geojson=geojson,
            locations=df.index,
            color="metric",
            hover_name="name",
            projection="mercator"
        )
        fig.update_geos(fitbounds="locations", visible=False)
    else:
        df_cent = df.copy()
        df_cent["lon"] = df_cent.geometry.centroid.x
        df_cent["lat"] = df_cent.geometry.centroid.y
        fig = px.scatter_geo(
            df_cent,
            lon="lon",
            lat="lat",
            size="metric",
            hover_name="name",
            projection="natural earth"
        )
        fig.update_geos(fitbounds="locations", visible=False)

    fig.update_layout(margin={"r": 0, "t": 30, "l": 0, "b": 0}, title_text=f"Casos VIH - {year} - Vista: {view}")

    return fig, kpi_children, table_data


# --- Run ---
if __name__ == "__main__":
    app.run_server(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8050)))
