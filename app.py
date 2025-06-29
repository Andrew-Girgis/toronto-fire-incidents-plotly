"""
Toronto Fire Incidents – point / ward choropleth (debug build, fixed)
Runs in PyCafe / Pyodide – no Mapbox token required
"""

import json, re, requests, pandas as pd, plotly.express as px
from dash import Dash, dcc, html, Input, Output, callback

# ───────── CONFIG ─────────
FIRE_URL = (
    "https://raw.githubusercontent.com/jragh/plotlymeetup/"
    "refs/heads/main/June_2025/Fire%20Incidents%20Data%20Raw.csv"
)
GEO_URL = (
    "https://raw.githubusercontent.com/Andrew-Girgis/"
    "toronto-fire-incidents-plotly/main/tor_city_wards25.geojson"
)

POP_URL = (
    "https://raw.githubusercontent.com/Andrew-Girgis/"
    "toronto-fire-incidents-plotly/main/2023-WardProfiles-2011-2021-CensusData.xlsx"
)

TORONTO_CENTER = dict(lat=43.6532, lon=-79.3832)

# ───────── HELPERS ─────────
def safe_load_geojson(url: str) -> dict:
    raw = requests.get(url, timeout=30).content.decode("utf-8", errors="ignore")
    m = re.search(r"\{.*\}", raw, flags=re.S)
    if not m:
        raise ValueError("No JSON object found in downloaded file.")
    return json.loads(m.group(0))

# ───────── 1. DATA ─────────
df_fires = pd.read_csv(FIRE_URL)
df_fires["Latitude"]  = pd.to_numeric(df_fires["Latitude"],  errors="coerce")
df_fires["Longitude"] = pd.to_numeric(df_fires["Longitude"], errors="coerce")
df_fires.dropna(subset=["Latitude", "Longitude"], inplace=True)

tor_geo  = safe_load_geojson(GEO_URL)
props0   = tor_geo["features"][0]["properties"]

# ───────── 2. Choose ward-code key ─────────
WARD_KEY = "AREA_SHORT_CODE"          # "01" … "25" (string, zero-padded)

# --- outline layer (grey polygons) -------------------------------------
ward_codes = [f["properties"][WARD_KEY] for f in tor_geo["features"]]
df_wards   = pd.DataFrame({WARD_KEY: ward_codes, "dummy": 1})

fig_outline = px.choropleth_mapbox(
    df_wards, geojson=tor_geo, locations=WARD_KEY,
    featureidkey=f"properties.{WARD_KEY}",
    color="dummy", color_continuous_scale="Greys",
    mapbox_style="carto-positron",
    center=TORONTO_CENTER, zoom=9, opacity=.25, height=650
).update_traces(marker_line_color="black", marker_line_width=1)

# ───────── 3. Harmonise Incident_Ward → "01"…"25" ─────────
df_fires["Incident_Ward"] = pd.to_numeric(df_fires["Incident_Ward"], errors="coerce")
df_fires["Incident_Ward"] = df_fires["Incident_Ward"].astype("Int64")
mask = df_fires["Incident_Ward"].between(1, 25)   # keep wards present in map
df_fires = df_fires.loc[mask].copy()

df_fires["Incident_Ward"] = (
    df_fires["Incident_Ward"].astype(str).str.zfill(2)     # 7 → "07"
)

# ───────── 4. Aggregate & diagnostics ─────────
df_counts = (
    df_fires.groupby("Incident_Ward", as_index=False)
            .size().rename(columns={"size": "FireCount"})
)

geo_ids   = {f["properties"][WARD_KEY] for f in tor_geo["features"]}
count_ids = set(df_counts["Incident_Ward"])

print("=== ID diagnostics ===")
print("Only in GeoJSON (missing counts)    :", sorted(geo_ids - count_ids))
print("Only in counts (no matching polygon):", sorted(count_ids - geo_ids))
print("Head of df_counts:\n", df_counts.head(), "\n")

# Rows 17–18 of the "2021 One Variable" sheet hold the ward header + totals
raw = pd.read_excel(POP_URL, sheet_name="2021 One Variable", header=None)

ward_names = raw.iloc[17, 2:27].tolist()    # 'Ward 1' … 'Ward 25'
pop_values = raw.iloc[18, 2:27].tolist()    # population numbers

df_pop = (
    pd.DataFrame({
        "WardNum": [f"{int(w.split()[1]):02d}" for w in ward_names],
        "Population": pop_values,
    })
)                                           # WardNum = '01' … '25'
# Join onto the fire-count table
df_rates = (
    df_counts.merge(df_pop, left_on="Incident_Ward", right_on="WardNum")
             .assign(FiresPer1000=lambda d: d["FireCount"] / d["Population"] * 1000)
)

# ───────── 5. Figures ─────────
fig_points = px.scatter_mapbox(
    df_fires,
    lat="Latitude", lon="Longitude",
    hover_data={
        "Incident_Ward": True,            # new
        "Final_Incident_Type": True,
        "TFS_Alarm_Time": True,
    },
    mapbox_style="carto-positron",
    center=TORONTO_CENTER, zoom=10, height=650
).update_layout(margin=dict(t=0, r=0, l=0, b=0))


# ----- Total-fires choropleth (use df_rates so pop is available) -------
fig_choro = px.choropleth_mapbox(
    df_rates,                             # ← was df_counts
    geojson=tor_geo,
    locations="Incident_Ward",
    featureidkey=f"properties.{WARD_KEY}",
    color="FireCount",
    color_continuous_scale="OrRd",
    hover_data={
        "FireCount": True,
        "Population": True,
    },
    mapbox_style="carto-positron",
    center=TORONTO_CENTER,
    zoom=9,
    opacity=0.6,
    height=650,
).update_layout(margin=dict(t=0, r=0, l=0, b=0))



fig_rate = px.choropleth_mapbox(
    df_rates,
    geojson=tor_geo,
    locations="Incident_Ward",
    featureidkey=f"properties.{WARD_KEY}",
    color="FiresPer1000",
    color_continuous_scale="YlGnBu",
    hover_data={ 
        "FiresPer1000": ":.2f",
        "FireCount": True,
        "Population": True,
    },
    mapbox_style="carto-positron",
    center=TORONTO_CENTER, zoom=9, opacity=0.75, height=650,
    labels={"FiresPer1000": "Fires / 1 000 pop"},
).update_layout(margin=dict(t=0, r=0, l=0, b=0))




# ───────── 6. Dash app ─────────
app = Dash(
    __name__,
    external_stylesheets=["/assets/style.css"],   # custom CSS
    external_scripts=["/assets/script.js"],       # optional JS
    title="Toronto Fire Incidents",
)

app.index_string = """
<!DOCTYPE html>
<html>
  <head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
  </head>
  <body>
    <header>
      Toronto Fire Incidents&nbsp;(2011-2024)
    </header>

    <!-- ▼ New intro block ▼ -->
    <section id="intro">
      <p>
        This dashboard was built during Plotly's first ever <em>Data Exploration of Toronto</em>
        meetup (<strong>Toronto Dataset-of-the-Month Hack-Session</strong>).<br>
        Working in small teams, with a quick Python&nbsp;+&nbsp;Plotly workshop
        from <a href="https://www.linkedin.com/in/jordan-raghunandan-398608a6/"
             target="_blank" rel="noopener">
           Jordan Raghunandan
        </a>, we explored the city's open data to answer
        questions that matter to us. 
      </p>
      <p>
        My focus: <strong>Where do most fires occur?</strong> and, more importantly,
        <strong>which neighbourhoods see the highest fire rate once we account for
        population size?</strong> The two choropleth layers (total fires vs.&nbsp;fires per
        1 000 residents) reveal very different patterns.
      </p>
    </section>
    <!-- ▲ Intro block ▲ -->

    <main id="map-area">
      {%app_entry%}
    </main>

    <section id="insights">
  <p>
    The maps confirm what many firefighters already know:
    <strong>downtown density drives risk.</strong>
    Ward&nbsp;13&nbsp;Toronto Centre logged the highest number of incidents
    (2 217) and still tops the <em>fires-per-1 000-residents</em> table, with
    Ward&nbsp;11 University–Rosedale close behind. Ward&nbsp;10 Spadina–Fort
    York is only a whisker behind in raw counts (1 707 fires) yet drops to
    fifth once we adjust for its larger population (~115 k vs.&nbsp;104 k in
    Ward 11 and 103 k in Ward 13).
  </p>

  <p>
    That gap hints at where prevention dollars might stretch furthest:
    neighbourhoods where <q>lots of fires&nbsp;≠ high per-capita risk</q> may
    benefit more from education campaigns, whereas hotspots that remain red
    <em>after</em> scaling for population signal a need for new fire halls or
    sprinkler-retrofit incentives.
  </p>

  <p>
    <strong>Next steps.</strong>  Two easy filters would deepen the analysis:
    <code>Extent_Of_Fire</code> (how severe was each blaze?) and
    <code>Final_Incident_Type</code> (kitchen flare-ups vs. multi-alarm
    structure fires).  Layering those onto the same ward map will help City
    staff target high-damage areas and tailor prevention strategies, getting us
    closer to a safer, more resilient Toronto.
  </p>
</section>

<section id="credits">
  <p>
    Thanks to&nbsp;
    <a href="https://www.linkedin.com/in/jordan-raghunandan-398608a6/"
       target="_blank" rel="noopener">
       Jordan&nbsp;Raghunandan
    </a>
    &nbsp;(Senior Business Intelligence Analyst @ Ivari Canada),
    <a href="https://www.linkedin.com/in/runqi-han/"
       target="_blank" rel="noopener">
       Runqi&nbsp;Han
    </a>&nbsp;(Customer Success SE @ Plotly),
    and Hammad&nbsp;Khan (Front-End Engineer @ Plotly)
    for organising and supporting this event.
  </p>
</section>

<section id="connect">
  <p>
    Like this project?&nbsp;
    <a href="https://www.linkedin.com/in/andrewagirgis/"
       target="_blank" rel="noopener">
       Connect with me on&nbsp;LinkedIn
    </a>
    — I’m always up for data-viz chats!
  </p>
</section>


    <footer style="text-align:center;padding:1rem;color:#666;font-size:.85rem;">
      Data: Toronto Open Data • Population: 2021 Census • Built with Dash & Plotly
    </footer>

    {%config%}
    {%scripts%}
    {%renderer%}
  </body>
</html>
"""


app.layout = html.Div(
    [
        dcc.Tabs(
            id="map_choice",
            value="points",
            children=[
                dcc.Tab(label="Points",             value="points"),
                dcc.Tab(label="Total fires",        value="choro"),
                dcc.Tab(label="Fires / 1 000 pop",  value="rate"),
            ],
        ),
        dcc.Graph(id="map_graph", figure=fig_points, className="map-graph"),
    ]
)



@callback(Output("map_graph", "figure"), Input("map_choice", "value"))
def choose_map(choice):
    return {
        "points":  fig_points,
        "choro":   fig_choro,
        "rate":    fig_rate,
    }[choice]
if __name__ == "__main__":
    app.run(debug=True)
