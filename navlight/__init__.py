"""Read data from Navlight tags"""

import io
import re
from pathlib import Path
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point


def to_hms(x: str) -> str:
    """Ensure time delta string include hours.
    e.g. '9:21' -> '0:9:21'
    """
    if x.count(":") == 2:
        return x
    else:
        return "0:" + x


class Tag(object):
    def __init__(self, filepath: str | Path, hours: int | float) -> None:
        self.filepath = filepath
        self.hours = hours  # Event duration
        self.route = None
        self._parse()

    def __repr__(self) -> str:
        return f"Tag({self.filepath})"

    def _parse(self):
        with open(self.filepath, "r") as f:
            lines = f.readlines()
            header = lines[3]
            data = [line for line in lines[4:] if len(line) > 40]

        # Get team details
        self.score = int(re.findall("Score: ([0-9]+) points", lines[-1])[0])
        self.number = int(re.findall("Team No: ([0-9]+)", lines[1])[0])
        self.names = lines[1].split(":")[-1][6:].strip().split(",")

        # Get target line length
        length = len(header) + 4

        # Get string width before and after 'Pl/Cnt' column
        match = re.search("Pl/Cnt", header)
        if match is not None:
            before = match.start() - 1
            after = match.end()
        else:
            raise ValueError("Invalid header.")

        # Get column headers
        header = lines[3].strip().split()

        # Pad columns ('Pl/Cnt' column gets too wide if >99 teams)
        for i, line in enumerate(data[:]):
            pad = length - len(line)
            if pad < 10:
                data[i] = line[:before] + " " * pad + line[before:]

        content = "\n".join(data)
        df = pd.read_fwf(io.StringIO(content), header=None)
        if len(header) > len(df.columns):
            header.remove("KmRate")  # This column is often empty

        # Set header columns
        df.columns = header

        # Get elapsed time from leg splits
        df["Time"] = pd.to_timedelta(df["TmSplit"].map(to_hms)).cumsum()

        # Ensure last control is hash house
        df.loc[df["Con"].isnull(), "Con"] = 0
        df["Con"] = df["Con"].astype(int).astype(str)
        df.loc[df["Con"] == "0", "Con"] = "HH"

        # Insert starting point
        df.loc[-1, "Con"] = "HH"
        df.loc[-1, "Time"] = pd.Timedelta(0)
        df.loc[-1, "CmPts"] = 0
        df = df.sort_index()

        # Only use selected columns
        self.df = df[["Con", "Time", "CmPts"]]

    def interpolate(
        self,
        gdf: gpd.GeoDataFrame,
        dt: pd.Timedelta = pd.Timedelta(minutes=5),
    ):
        """Interpolate path over event duration over given timestep"""
        # Add geospatial locations of controls
        if self.route is not None:
            return
        self.df = self.df.join(gdf, on="Con")

        # Get points along path
        self.df["x"] = [p.x for p in self.df.geometry]
        self.df["y"] = [p.y for p in self.df.geometry]

        # Use event time as index
        self.df = self.df.set_index("Time").sort_index()

        # keep only the columns we need
        df = self.df[["Con", "CmPts", "x", "y"]].copy()

        # Interpolate route
        xy = df[["x", "y"]].resample(dt).mean().interpolate()
        pts = df["CmPts"].resample(dt).ffill()
        self.route = xy.join(pts)

        soft_end = pd.Timedelta(hours=self.hours)
        hard_end = soft_end + pd.Timedelta(minutes=30)

        # Calculate point deductions
        deductions = pts.copy() * 0
        values = ((deductions.index - soft_end).total_seconds() / 6).values
        values[values < 0] = 0
        deductions[:] = values
        self.route["CmPts"] -= values

        # Fill scores to end of event
        self.route.loc[hard_end, "CmPts"] = self.score
        self.route = self.route.ffill()

        # Rename columns
        self.route = self.route.rename(columns={"CmPts": "Score"})
