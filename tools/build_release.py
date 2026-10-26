from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--windowed',
    '--onedir', '--name', 'ArmsHub',
    '--distpath', str(root/'dist'), '--workpath', str(root/'.build/work'),
    '--specpath', str(root/'.build/spec'), str(root/'armshub_main.py')], cwd=root, check=True)
