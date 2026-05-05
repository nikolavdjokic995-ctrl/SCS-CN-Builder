from pathlib import Path

from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QCoreApplication

from .gui.main_dialog import LULC2HMSCNDialog


class LULC2HMSCNPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None
        self.plugin_dir = Path(__file__).parent

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("SCSCNBuilder", message)

    def initGui(self):
        self.action = QAction(QIcon(str(self.plugin_dir / "icon.png")), self.tr("SCS-CN Builder"), self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu(self.tr("&SCS-CN Builder"), self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu(self.tr("&SCS-CN Builder"), self.action)
            self.iface.removeToolBarIcon(self.action)

    def run(self):
        try:
            if self.dialog is None:
                self.dialog = LULC2HMSCNDialog(self.iface)
            self.dialog.show()
            self.dialog.raise_()
            self.dialog.activateWindow()
        except Exception as exc:
            QMessageBox.critical(self.iface.mainWindow(), self.tr("Plugin error"), str(exc))
