"""Run the full pipeline in dependency order.

Stage 2 runs after stage 3 so energy-named charities can join the orgs layer.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
STAGES = ["p01_imd_boundaries.py", "p03_infra.py", "p02_energy_orgs.py",
          "p04_grid.py", "p05_composite.py"]

for stage in STAGES:
    print(f"\n=== {stage} ===")
    rc = subprocess.call([sys.executable, str(HERE / stage)])
    if rc != 0:
        sys.exit(f"{stage} failed with exit code {rc}")
print("\npipeline complete")
