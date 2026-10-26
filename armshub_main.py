import os
from pathlib import Path
import sys

if '--self-test' in sys.argv:os.environ['QT_QPA_PLATFORM']='offscreen'
from PyQt6.QtWidgets import QApplication
from armshub.app import ArmsHubWindow


def main():
    app=QApplication(sys.argv);app.setApplicationName('ArmsHub');app.setApplicationVersion('0.3.2')
    root=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    window=ArmsHubWindow(root)
    if '--self-test' in sys.argv:
        assert window.arms.rowCount()==8 and not window.profiles
        assert window.procedural_mode.currentData()=='repair'
        window.procedural_mode.setCurrentIndex(1)
        assert window.procedural_mode.currentData()=='skip'
        print('ArmsHub PyQt6 UI smoke test passed');window.close();return 0
    window.show();return app.exec()


if __name__=='__main__':sys.exit(main())
