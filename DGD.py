from sys import exit, argv
from datetime import datetime, timedelta
from io import StringIO
import requests
import pandas as pd
from PySide6 import QtWidgets, QtCore, QtUiTools


class DownloaderApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        # Loading .ui file
        ui_file = QtCore.QFile("DGD_Interface/DGD_GUI.ui")
        if not ui_file.open(QtCore.QFile.ReadOnly):
            print("Nie udało się otworzyć pliku .ui")
            exit(-1)

        loader = QtUiTools.QUiLoader()
        self.window = loader.load(ui_file)
        ui_file.close()

        # GUI elements
        self.resolution_combo = self.window.findChild(QtWidgets.QComboBox, "ResolutionComboBox")
        self.source_combo = self.window.findChild(QtWidgets.QComboBox, "SourceDataComboBox")
        self.start_date_edit = self.window.findChild(QtWidgets.QDateEdit, "StartDateEdit")
        self.end_date_edit = self.window.findChild(QtWidgets.QDateEdit, "EndDateEdit")
        self.countries_list = self.window.findChild(QtWidgets.QTableWidget, "CountriesTable")
        self.select_all_btn = self.window.findChild(QtWidgets.QPushButton, "SelectAllButton")
        self.clear_all_btn = self.window.findChild(QtWidgets.QPushButton, "ClearAllButton")
        self.output_line = self.window.findChild(QtWidgets.QLineEdit, "OutputLineEdit")
        self.output_button = self.window.findChild(QtWidgets.QToolButton, "OutputButton")
        self.error_messages = self.window.findChild(QtWidgets.QTextEdit, "ErrorMessages")
        self.progress_bar = self.window.findChild(QtWidgets.QProgressBar, "progressBar")
        self.start_btn = self.window.findChild(QtWidgets.QPushButton, "pushButton")

        # Signals
        self.select_all_btn.clicked.connect(self.select_all)
        self.clear_all_btn.clicked.connect(self.clear_all)
        self.output_button.clicked.connect(self.choose_folder)
        self.start_btn.clicked.connect(self.on_start_clicked)

        self.window.show()

    # Help function
    def select_all(self):
        self.countries_list.selectAll()

    def clear_all(self):
        self.countries_list.clearSelection()

    def choose_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self.window, "Choose output folder")
        if folder:
            self.output_line.setText(folder)

    # Downloading with Intermagnet
    def downloading_data_intermagnet(self, start: str, end: str, resolution: str, stations: list):
        startTime = datetime.strptime(start, "%Y-%m-%d")
        endTime = datetime.strptime(end, "%Y-%m-%d")

        delta = endTime - startTime
        total_days = delta.days + 1
        step = 0

        for station in stations:
            print(station)
            final_dataframe = pd.DataFrame()
            for i in range(total_days):
                date = (startTime + timedelta(days=i)).strftime("%Y-%m-%d")
                print("Pobieram:", date)
                data_link = (
                    f"https://imag-data.bgs.ac.uk/GIN_V1/GINServices?"
                    f"Request=GetData&format=HTML&testObsys=0"
                    f"&observatoryIagaCode={station}"
                    f"&samplesPerDay={resolution}"
                    f"&publicationState=Best%20available"
                    f"&dataStartDate={date}"
                    f"&dataDuration=1"
                    f"&orientation=native"
                )
                print("Link:", data_link)

                try:
                    response = requests.get(data_link, timeout=10)
                    response.raise_for_status()
                    tables = pd.read_html(StringIO(response.text))
                    if tables:
                        final_dataframe = pd.concat([final_dataframe, tables[0]], ignore_index=True)
                        print("Dodano dane dla", station, date)
                    else:
                        print("Brak danych dla", station, date)
                except Exception as e:
                    print(f"Błąd przy {station} {date}: {e}")
                    continue

            step += 1
            percent = int(step / total_days * 100)
            self.progress_bar.setValue(percent)
            QtWidgets.QApplication.processEvents()
            print(final_dataframe)

    # Start button
    def on_start_clicked(self):
        resolution = self.resolution_combo.currentText()
        source = self.source_combo.currentIndex()
        start_date = self.start_date_edit.date().toString("yyyy-MM-dd")
        end_date = self.end_date_edit.date().toString("yyyy-MM-dd")

        selected = []
        for idx in self.countries_list.selectionModel().selectedRows():
            station = self.countries_list.item(idx.row(), 0).text()
            selected.append(station)

        if not selected:
            self.error_messages.setText("Not selected stations!")
        else:
            self.error_messages.setText("Selected stations: " + ", ".join(selected))
            match source:
                case 0:
                    self.downloading_data_intermagnet(start_date, end_date, resolution, selected)
                case 1:
                    pass


def main():
    app = QtWidgets.QApplication(argv)
    app_instance = DownloaderApp()
    app_instance.window.show()
    exit(app.exec())


if __name__ == "__main__":
    main()
