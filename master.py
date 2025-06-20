"""
Master Control Script for InSAR-GNSS Processing Workflow

This script orchestrates the complete InSAR and GNSS data processing workflow.
It sets environment variables, defines processing parameters, and executes
all analysis scripts in the correct order, ensuring proper data flow between steps.

Features:
- Centralized parameter configuration via environment variables
- Automated sequential execution of processing scripts
- Comprehensive logging of all processing steps
- Error handling and status reporting
- Support for multi-resolution analysis configuration
"""

import os
import subprocess
from pathlib import Path
import time

# Set global data directory as an environment variable
data_dir = Path("C:/insar_gnss_data")
os.environ["DATA_DIR"] = str(data_dir)

# Set global parameters
os.environ["MIN_TEMPORAL_COHERENCE"] = "0.7"    # Minimum temporal coherence threshold
os.environ["INSAR_RADIUS"] = "500"              # Radius in m for InSAR averaging

# Settings for grid_amplitude_analysis.py
os.environ["GRID_SIZE_KM"] = "0.5"              # Grid size in km (used when MULTI_RESOLUTION=False)
os.environ["USE_DETRENDED"] = "True"            # Whether to detrend time series before amplitude calculation
os.environ["HALF_AMPLITUDE"] = "True"           # Whether to use scientific amplitude definition (max-min)/2
os.environ["MULTI_RESOLUTION"] = "True"         # Whether to create plots at multiple resolutions
os.environ["GRID_SIZES"] = "0.25, 0.5, 1.0, 1.5, 2.5, 5.0"  # Comma-separated list of grid sizes in km to use when MULTI_RESOLUTION=True

# Set file names for INSAR and the stations_list.
os.environ["INSAR_FILE"] = "EGMS_L2a_088_0297_IW3_VV_2019_2023_1_A.csv"
os.environ["STATIONS_FILE"] = "stations_list"

# List of scripts to run (uncomment any additional scripts as needed but beware of dependencies)
scripts = [
    "gnss_3d_vels.py",
    "filter_insar_save_parameters.py",
    "fit_plane_correct_insar.py",
    "gnss_los_displ.py",
    "plot_combined_time_series.py",
    "grid_amplitude_analysis.py"
]

log_file = "workflow.log"

def run_script(script):
    """Executes a script, logs output, and confirms success."""
    try:
        with open(log_file, "a") as log:
            result = subprocess.run(
                ["python", script],
                capture_output=True,
                text=True,
                env=os.environ
            )
            log.write(f"Running {script}...\n")
            log.write(result.stdout)
            log.write(result.stderr)
            log.write("\n" + "-" * 50 + "\n")
        
        if result.returncode != 0:
            print(f"Error in {script}, see {log_file}")
            return False
        
        print(f"{script} executed successfully!")
        return True
    
    except Exception as e:
        print(f"Error while executing {script}: {e}")
        return False

start_time = time.time()

# Main workflow: execute each script in order and abort if any fail.
for script in scripts:
    success = run_script(script)
    if not success:
        print("Workflow aborted due to error.")
        break

end_time = time.time()
duration = end_time - start_time
if duration < 60:
    print(f"Total runtime: {duration:.2f} seconds")
else:
    print(f"Total runtime: {duration/60:.2f} minutes")