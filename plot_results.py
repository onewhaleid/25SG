from pathlib import Path
import pandas as pd
import geopandas as gpd
from PIL import Image
import plotly.express as px
import plotly.graph_objects as go
from shapely.geometry import Point
import matplotlib.pyplot as plt
from navlight import Tag


folder = Path("../25SGv1/tags/")
filepaths = list(folder.glob("*.txt"))
hours = 6
dt = pd.Timedelta(minutes=5)

# Get control coordinates
csv_path = "points.csv"
controls = pd.read_csv(csv_path, index_col=0)[["x", "y"]]
geometry = [Point(x, y) for x, y in controls.values]
gdf = gpd.GeoDataFrame(index=controls.index, geometry=geometry)

# Load tag data
folder = Path("25SGv1/tags/")
filepaths = list(folder.glob("*.txt"))

df = pd.DataFrame()

# Load team data
teams = []
for filepath in filepaths[:]:
    tag = Tag(filepath, hours)
    if tag.number in teams:
        continue
    else:
        teams.append(tag.number)

    tag.interpolate(gdf)

    tag.route["team"] = tag.number
    tag.route["time"] = tag.route.index

    df = pd.concat([df, tag.route])

# Round coordinates to nearest pixel
df[["x", "y"]] = df[["x", "y"]].astype(int)


# Get top score for each timestep
max_score = df.groupby(["time"]).max()[["Score"]].rename(columns={"Score": "max score"})
df = df.join(max_score)
df["leader"] = (df["Score"] == df["max score"]) & (df["Score"] > 0)
df = df.rename(columns={"team": "Team"})

# Format time labels as HH:MM
df["time"] = df["time"].astype(str).str.extract(r"(\d+:\d+):\d+")


bg_path = Path("basemap-1946x1783-bw.jpg")
img = Image.open(bg_path)

x0 = 0
x1 = img.width
y0 = 0
y1 = img.height

fig = px.scatter(
    df,
    x="x",
    y="y",
    color="Score",
    range_color=[0, df["Score"].max()],
    color_continuous_scale="viridis",
    animation_frame="time",
    animation_group="Team",
    range_x=[x0, x1],
    range_y=[y0, y1],
    hover_data={
        "Team": True,
        "Score": True,
        "x": False,
        "y": False,
        "time": False,
    },
)


fig.update_layout(
    images=[
        dict(
            source=img,
            xref="x",
            yref="y",
            x=x0,
            y=y1,
            sizex=x1 - x0,
            sizey=y1 - y0,
            sizing="stretch",
            layer="below",
        )
    ],
    xaxis=dict(range=[x0, x1], constrain="domain"),
    yaxis=dict(range=[y0, y1], scaleanchor="x", scaleratio=1, autorange=False),
    margin=dict(l=0, r=0, t=0, b=0),
    sliders=[{"pad": {"t": 0, "b": 0}}],
)

fig.add_trace(
    go.Scatter(
        x=controls.x,
        y=controls.y,
        showlegend=False,
        mode="markers",
        hoverinfo="skip",
        marker=dict(symbol="circle-open", size=12, color="red", line=dict(width=2)),
    )
)

fig.update_traces(marker={"size": 10})
fig.update_xaxes(visible=False)
fig.update_yaxes(visible=False)
fig.show()

fig.write_html("index.html", auto_play=False)
