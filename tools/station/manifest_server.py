"""Run deployed Manifest with the proxy maintained in Armstrong."""
import os
from pathlib import Path
import runpy
import sys

runtime = Path(os.environ['ARMSTRONG_STATION_DIR']).resolve()
sys.path.insert(0, str(runtime))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import proxy  # preload Armstrong's error-preserving proxy before the deployed server imports it

if __name__ == '__main__':
    runpy.run_path(str(runtime / 'server.py'), run_name='__main__')
