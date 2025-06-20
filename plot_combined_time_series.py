"""
Combined Time Series Visualization Script

This script creates comparative visualizations of InSAR and GNSS time series data.
It generates plots showing both data sources together, allowing direct comparison
of displacement patterns, trends, and seasonal variations between measurement techniques.

Features:
- Side-by-side visualization of InSAR and GNSS time series
- Automatic data alignment to common time references
- Statistical comparison between measurement techniques
- Support for seasonal pattern analysis
- Multiple visualization formats (raw, detrended, normalized)
"""

import os
import glob
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import linregress
from datetime import datetime
from geopy.distance import geodesic
import matplotlib.patheffects as path_effects
from pathlib import Path

# Read DATA_DIR from the environment variable and set up global paths.
data_dir_value = os.getenv("DATA_DIR")
if not data_dir_value:
    print("Error: DATA_DIR environment variable is not set.")
    exit(1)
data_dir = Path(data_dir_value).resolve()

# Global parameters that can be configured from master.py (e.g., via environment variables)
MIN_TEMPORAL_COHERENCE = float(os.getenv("MIN_TEMPORAL_COHERENCE", "0.7"))
INSAR_RADIUS = int(os.getenv("INSAR_RADIUS", "500"))

# Global file paths (all files are assumed to be in DATA_DIR)
stations_file = data_dir / os.getenv("STATIONS_FILE", "stations_list")
parameters_file = data_dir / "parameters.csv"
insar_before = data_dir / os.getenv("INSAR_FILE", "insar.csv")
insar_after = insar_before.with_name(insar_before.stem + "_aligned" + insar_before.suffix)

# All plots will be saved in a single folder named "plots"
plots_dir = data_dir / "plots"

def find_stations_file():
    """
    Returns the path to the stations_list file located in DATA_DIR.
    Since the file has no suffix, it searches only by that name.
    """
    stations_path = os.path.join(data_dir, "stations_list")
    return stations_path if os.path.exists(stations_path) else None


def decimal_year(date_str, start_date):
    """
    Converts a date string (YYYYMMDD) to a decimal year relative to start_date.
    """
    date = datetime.strptime(date_str, "%Y%m%d")
    delta_days = (date - start_date).days
    return delta_days / 365.25


def load_gnss_data(filepath):
    """
    Loads GNSS data from a file and handles inconsistent formatting.
    Expects at least 7 columns: MJD, time (split into two parts), North, East, Up, and LOS.
    Converts MJD to datetime and computes a decimal year based on the first date.
    """
    data = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('MJD') or line.startswith('---') or "in mm" in line:
                continue
            parts = line.split()
            if len(parts) >= 7:
                try:
                    mjd = float(parts[0])
                    time_str = parts[1] + " " + parts[2]
                    north = float(parts[3])
                    east = float(parts[4])
                    up = float(parts[5])
                    los = float(parts[6])
                    data.append([mjd, time_str, north, east, up, los])
                except ValueError:
                    print(f"Skipping invalid line in GNSS file: {line}")
                    continue
    df = pd.DataFrame(data, columns=["MJD", "TIME", "North", "East", "Up", "LOS"])
    if df.empty or df["MJD"].isnull().all():
        raise ValueError(f"GNSS file {filepath} contains no valid MJD data.")
    df["DATE"] = pd.to_datetime(df["MJD"], origin="1858-11-17", unit="D")
    start_date = df["DATE"].iloc[0]
    df["decimal_year"] = ((df["DATE"] - start_date).dt.total_seconds() /
                          (365.25 * 24 * 3600))
    return df


def haversine_distance_vectorized(lat1, lon1, lat2, lon2):
    """Calculate the geodetic distance between two points (vectorized)."""
    R = 6371000  # Earth's radius in meters
    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return R * c


def find_insar_average_within_radius(insar_df, station_lat, station_lon, radius=INSAR_RADIUS):
    """
    Computes the average displacement of all InSAR points within a given radius (in meters)
    around the GNSS station. Returns a Series with the mean for each time column.
    """
    distances = haversine_distance_vectorized(
        station_lat, station_lon,
        insar_df["latitude"].values, insar_df["longitude"].values
    )
    within_radius = insar_df[distances <= radius]
    time_columns = [col for col in within_radius.columns if col.isdigit()]
    return within_radius[time_columns].mean()


def plot_combined_time_series():
    """
    Generates combined time series plots for each GNSS station with two subplots:
      - InSAR time series before alignment,
      - Combined InSAR time series after alignment and GNSS LOS displacement.
    The plots are saved in the "plots" folder.
    """
    before_df = pd.read_csv(insar_before)
    after_df = pd.read_csv(insar_after)
    stations_df = pd.read_csv(stations_file, delim_whitespace=True)
    stations_df.columns = stations_df.columns.str.strip()
    before_df = before_df[before_df["temporal_coherence"] >= MIN_TEMPORAL_COHERENCE]
    after_df = after_df[after_df["temporal_coherence"] >= MIN_TEMPORAL_COHERENCE]

    # Precompute coordinates as numpy arrays for fast access
    before_coords = before_df[["latitude", "longitude"]].values
    after_coords = after_df[["latitude", "longitude"]].values
    before_time_columns = [col for col in before_df.columns if col.isdigit()]
    after_time_columns = [col for col in after_df.columns if col.isdigit()]

    for idx, station in stations_df.iterrows():
        station_name = station["Station"]
        station_lat = station["latitude"]
        station_lon = station["longitude"]

        gnss_pattern = os.path.join(data_dir, f"{station_name}_NEU_TIME*_LOS.txt")
        gnss_files = glob.glob(gnss_pattern)
        if not gnss_files:
            print(f"GNSS file not found for pattern: {gnss_pattern}. Skipping station {station_name}.")
            continue
        gnss_file = gnss_files[0]
        print(f"Using GNSS file: {gnss_file} for station {station_name}")

        # Use fast vectorized Haversine for both before and after
        def fast_haversine(lat1, lon1, coords):
            R = 6371000
            lat1 = np.radians(lat1)
            lon1 = np.radians(lon1)
            lat2 = np.radians(coords[:, 0])
            lon2 = np.radians(coords[:, 1])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
            c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
            return R * c

        before_dist = fast_haversine(station_lat, station_lon, before_coords)
        after_dist = fast_haversine(station_lat, station_lon, after_coords)
        before_mask = before_dist <= INSAR_RADIUS
        after_mask = after_dist <= INSAR_RADIUS
        before_displacement = before_df.loc[before_mask, before_time_columns].mean()
        after_displacement = after_df.loc[after_mask, after_time_columns].mean()

        gnss_data = load_gnss_data(gnss_file)
        time_dates = [pd.to_datetime(col, format="%Y%m%d") for col in before_time_columns]

        fig, axes = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
        # Subplot 1: InSAR before alignment
        axes[0].plot(time_dates, before_displacement, 'r.', label="Before Alignment (Displacement)")
        slope_before, intercept_before, _, _, _ = linregress(range(len(time_dates)), before_displacement)
        trend_before = slope_before * np.arange(len(time_dates)) + intercept_before
        axes[0].plot(time_dates, trend_before, 'r-', label=f"Trend (Slope: {slope_before:.5f} mm/year)", linewidth=2.5)
        axes[0].set_title(f"InSAR Time Series Before Alignment - Station {station_name}")
        axes[0].set_ylabel("Displacement (mm)")
        axes[0].legend()
        axes[0].grid()
        # Subplot 2: Combined time series (after alignment and GNSS)
        axes[1].plot(time_dates, after_displacement, 'b.', label="After Alignment (Displacement)")
        slope_after, intercept_after, _, _, _ = linregress(range(len(time_dates)), after_displacement)
        trend_after = slope_after * np.arange(len(time_dates)) + intercept_after
        axes[1].plot(time_dates, trend_after, 'b-', label=f"InSAR Trend (Slope: {slope_after:.5f} mm/year)", linewidth=2.5)
        axes[1].plot(gnss_data["DATE"], gnss_data["LOS"], 'g.', label="GNSS LOS Displacement")
        slope_gnss, intercept_gnss, _, _, _ = linregress(gnss_data["decimal_year"], gnss_data["LOS"])
        axes[1].plot(gnss_data["DATE"], slope_gnss * gnss_data["decimal_year"] + intercept_gnss,
                     'g-', label=f"GNSS Trend (Slope: {slope_gnss:.5f} mm/year)", linewidth=2.5)
        axes[1].set_title(f"Combined InSAR After Alignment and GNSS LOS - Station {station_name}")
        axes[1].set_ylabel("Displacement (mm)")
        axes[1].legend()
        axes[1].grid()
        axes[1].set_xlabel("TIME (YYYY-MM-DD)")
        axes[1].xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%Y-%m-%d"))
        plt.setp(axes[1].xaxis.get_majorticklabels(), rotation=45, ha="right")
        date_start = time_dates[0].strftime("%Y-%m-%d")
        date_end = time_dates[-1].strftime("%Y-%m-%d")
        fig.suptitle(f"Date Range: {date_start} to {date_end}", fontsize=10)
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        output_path = os.path.join(plots_dir, f"{station_name}_combined_plot.png")
        plt.savefig(output_path)
        plt.close()
        print(f"Combined time series plot saved for station {station_name}: {output_path}")


def plot_global_velocity_map(before_df, after_df, stations_df, parameters_file, output_dir, title="Regional Velocity Map", suffix=""):
    """
    Generates a scatter plot of velocities in longitude-latitude space, consisting of three subplots:
      - Before alignment,
      - After alignment, and
      - The velocity correction plane.
    """
    os.makedirs(output_dir, exist_ok=True)
    parameters_df = pd.read_csv(parameters_file)
    a = parameters_df["Plane Coefficient a"].iloc[0]
    b = parameters_df["Plane Coefficient b"].iloc[0]
    c = parameters_df["Plane Coefficient c"].iloc[0]

    def filter_normal_points(df):
        time_columns = [col for col in df.columns if col.isdigit()]
        velocities = df[time_columns].mean(axis=1)
        q1 = velocities.quantile(0.25)
        q3 = velocities.quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - 2.0 * iqr
        upper_bound = q3 + 2.0 * iqr
        normal_points = df[(velocities >= lower_bound) & (velocities <= upper_bound)]
        normal_velocities = velocities[(velocities >= lower_bound) & (velocities <= upper_bound)]
        return normal_points, normal_velocities

    before_points, before_velocities = filter_normal_points(before_df)
    after_points, after_velocities = filter_normal_points(after_df)
    before_mean = before_velocities.mean()
    before_std = before_velocities.std()
    after_mean = after_velocities.mean()
    after_std = after_velocities.std()
    global_mean = np.mean([before_mean, after_mean])
    global_std = np.mean([before_std, after_std])
    color_min = global_mean - 3 * global_std
    color_max = global_mean + 3 * global_std

    fig, axes = plt.subplots(3, 1, figsize=(18, 40), sharex=True)
    scatter1 = axes[0].scatter(before_points["longitude"], before_points["latitude"],
                               c=before_velocities, cmap="seismic", s=1, alpha=0.7, marker=".")
    axes[0].set_title("Before Alignment", fontsize=16)
    axes[0].set_ylabel("Latitude (decimal degrees)", fontsize=14)
    axes[0].grid(alpha=0.5)
    axes[0].set_aspect('equal')
    fig.colorbar(scatter1, ax=axes[0], pad=0.02).set_label("Velocity (mm/year)")
    scatter2 = axes[1].scatter(after_points["longitude"], after_points["latitude"],
                               c=after_velocities, cmap="seismic", s=1, alpha=0.7, marker=".")
    axes[1].set_title("After Alignment", fontsize=16)
    axes[1].set_ylabel("Latitude (decimal degrees)", fontsize=14)
    axes[1].grid(alpha=0.5)
    axes[1].set_aspect('equal')
    fig.colorbar(scatter2, ax=axes[1], pad=0.02).set_label("Velocity (mm/year)")
    lons = before_points["longitude"]
    lats = before_points["latitude"]
    correction_plane = a * lons + b * lats + c
    scatter3 = axes[2].scatter(lons, lats, c=correction_plane, cmap="plasma", s=1, alpha=0.7, marker=".")
    axes[2].set_title("Velocity Correction Plane", fontsize=16)
    axes[2].set_xlabel("Longitude (decimal degrees)", fontsize=14)
    axes[2].set_ylabel("Latitude (decimal degrees)", fontsize=14)
    axes[2].grid(alpha=0.5)
    axes[2].set_aspect('equal')
    fig.colorbar(scatter3, ax=axes[2], pad=0.02).set_label("Correction Value (mm/year)")
    for _, station in stations_df.iterrows():
        station_name = station["Station"]
        station_lat = station["latitude"]
        station_lon = station["longitude"]
        for ax in axes:
            ax.scatter(station_lon, station_lat, color="black", edgecolor="white", s=50, marker="^", zorder=5)
            ax.text(station_lon, station_lat, station_name,
                    color="black", fontsize=10, ha="left", va="bottom",
                    path_effects=[path_effects.withStroke(linewidth=1, foreground="white")])
    fig.suptitle(title, fontsize=20)
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    output_path = os.path.join(output_dir, f"{suffix}_velocity_map_with_correction.png")
    plt.savefig(output_path, dpi=300)
    plt.close()
    print(f"Velocity map with correction saved: {output_path}")


def plot_station_velocity_map(before_df, after_df, stations_df, output_dir, radius=INSAR_RADIUS):
    """
    Generates a scatter plot for each station showing velocities in longitude-latitude space,
    with two subplots: before and after alignment.
    """
    os.makedirs(output_dir, exist_ok=True)
    for _, station in stations_df.iterrows():
        station_name = station["Station"]
        station_lat = station["latitude"]
        station_lon = station["longitude"]

        def filter_within_radius(df):
            df["distance"] = df.apply(
                lambda row: geodesic((row["latitude"], row["longitude"]), (station_lat, station_lon)).meters,
                axis=1
            )
            within_radius = df[df["distance"] <= radius]
            time_columns = [col for col in within_radius.columns if col.isdigit()]
            velocities = within_radius[time_columns].mean(axis=1)
            q1 = velocities.quantile(0.25)
            q3 = velocities.quantile(0.75)
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            normal_points = within_radius[(velocities >= lower_bound) & (velocities <= upper_bound)]
            normal_velocities = velocities[(velocities >= lower_bound) & (velocities <= upper_bound)]
            return normal_points, normal_velocities

        before_points, before_velocities = filter_within_radius(before_df)
        after_points, after_velocities = filter_within_radius(after_df)

        fig, axes = plt.subplots(1, 2, figsize=(16, 8), sharey=True)
        scatter1 = axes[0].scatter(before_points["longitude"], before_points["latitude"],
                                   c=before_velocities, cmap="plasma", s=15, alpha=0.7)
        axes[0].set_title("Before Alignment", fontsize=14)
        axes[0].set_xlabel("Longitude", fontsize=12)
        axes[0].set_ylabel("Latitude", fontsize=12)
        axes[0].grid(alpha=0.5)
        fig.colorbar(scatter1, ax=axes[0], label="Velocity (mm/year)")
        scatter2 = axes[1].scatter(after_points["longitude"], after_points["latitude"],
                                   c=after_velocities, cmap="plasma", s=15, alpha=0.7)
        axes[1].set_title("After Alignment", fontsize=14)
        axes[1].set_xlabel("Longitude", fontsize=12)
        axes[1].grid(alpha=0.5)
        fig.colorbar(scatter2, ax=axes[1], label="Velocity (mm/year)")
        for ax in axes:
            ax.scatter(station_lon, station_lat, color="black", edgecolor="white", s=50, marker="^", zorder=5)
            ax.text(station_lon, station_lat, station_name,
                    color="black", fontsize=10, ha="left", va="bottom",
                    path_effects=[path_effects.withStroke(linewidth=1, foreground="white")])
        fig.suptitle(f"Velocity Map for Station {station_name}", fontsize=16)
        output_path = os.path.join(output_dir, f"{station_name}_velocity_map.png")
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        plt.savefig(output_path, dpi=300)
        plt.close()
        print(f"Velocity map saved for station {station_name}: {output_path}")


if __name__ == "__main__":
    # First, generate the combined time series plots.
    plot_combined_time_series()

    # Then, load DataFrames for global and station-specific velocity maps:
    before_df = pd.read_csv(insar_before)
    after_df = pd.read_csv(insar_after)
    stations_df = pd.read_csv(stations_file, delim_whitespace=True)
    stations_df.columns = stations_df.columns.str.strip()

    # Global velocity map plot (including velocity correction plane)
    plot_global_velocity_map(before_df, after_df, stations_df, parameters_file, plots_dir,
                               title="Regional Velocity Map", suffix="combined")

    # Velocity map for each station.
    plot_station_velocity_map(before_df, after_df, stations_df, plots_dir, radius=INSAR_RADIUS)

    print("All plots were successfully saved in the folder 'plots'.")