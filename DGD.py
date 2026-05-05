from sys import argv, exit
from datetime import date, datetime, timedelta
from io import StringIO

import requests
import pandas as pd

from PySide6 import QtWidgets, QtCore, QtUiTools
from PySide6.QtCore import QObject, Signal


class DownloadWorker(QObject):
    progress = Signal(int)
    message = Signal(str)
    finished = Signal()

    def __init__(self, stations, ranges, resolution, source, output):
        super().__init__()
        self.stations = stations
        self.ranges = ranges
        self.resolution = resolution
        self.source = source  # 0 = Intermagnet, 1 = Image
        self.output = output

    def run(self):
        days = 0
        for rang in self.ranges:
            date1 = datetime.strptime(rang[0], "%Y-%m-%d")
            date2 = datetime.strptime(rang[1], "%Y-%m-%d")
            days =+ (date2 - date1).days + 1

        total_tasks = len(self.stations) * len(self.ranges) * days
        print(total_tasks, days)
        done = 0

        for station in self.stations:
            sheets = {}

            for start, end in self.ranges:
                try:
                    df = self.download_range(station, start, end)
                    if df is not None and not df.empty:
                        sheet_name = f"{start}_{end}"
                        sheets[sheet_name] = df
                        self.message.emit(f"{station}: downloaded {start}–{end}")
                    else:
                        self.message.emit(f"{station}: no data for {start}–{end}")
                except Exception as e:
                    self.message.emit(f"Error for {station} {start}–{end}: {e}")

                done += 1
                self.progress.emit(int(done / total_tasks * 100))

            if sheets:
                filename = f"{self.output}/{station}.xlsx"
                with pd.ExcelWriter(filename, engine="openpyxl") as writer:
                    for sheet_name, df in sheets.items():
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                self.message.emit(f"Saved file: {filename}")
            else:
                self.message.emit(f"No data to save for station {station}")

        self.finished.emit()

    def download_range(self, station, start, end):
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        total_days = (end_dt - start_dt).days + 1

        final_df = pd.DataFrame()

        for i in range(total_days):
            date = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")

            if self.source == 0:
                df = self.download_intermagnet(station, date)
            else:
                df = self.download_image(station, date)

            if df is not None and not df.empty:
                final_df = pd.concat([final_df, df], ignore_index=True)

        return final_df

    def download_intermagnet(self, station, date):
        samples = self.resolution

        link = (
            f"https://imag-data.bgs.ac.uk/GIN_V1/GINServices?"
            f"Request=GetData&format=HTML&testObsys=0"
            f"&observatoryIagaCode={station}"
            f"&samplesPerDay={samples}"
            f"&publicationState=Best%20available"
            f"&dataStartDate={date}"
            f"&dataDuration=1"
            f"&orientation=native"
        )

        r = requests.get(link, timeout=1000)
        r.raise_for_status()
        tables = pd.read_html(StringIO(r.text))

        tables[0]['Time'] = tables[0]['Time'].str.replace('T', ' ').str.replace('Z', '')

        tables[0] = tables[0].rename(columns={
            'Time': 'DATETIME',
            'X': 'BX',
            'Y': 'BY',
            'Z': 'BZ',
            'G': 'BG'
        })

        return tables[0] if tables else None

    def download_image(self, station, date):
        date_fmt = date.replace("-", "")
        if self.resolution == "10-second":
            sample = 10
        else:
            sample = 60

        link = (
            "https://space.fmi.fi/image/www/data_download.php?"
            f"starttime={date_fmt}&length=1440&format=text&sample_rate={sample}&stations={station}"
        )

        r = requests.get(link, timeout=1000)
        r.raise_for_status()

        df = pd.read_csv(StringIO(r.text), header=None)
        df = df[0].str.split(r"\s+", expand=True)
        df = df.drop([0, 1])
        df = df.iloc[:, :9]
        df = df.reset_index(drop=True)
        df.columns = ["YYYY", "MO", "DD", "HH", "MI", "SS", "BX", "BY", "BZ"]

        df["DATETIME"] = (
            df["YYYY"].astype(str) + "-" +
            df["MO"].astype(str).str.zfill(2) + "-" +
            df["DD"].astype(str).str.zfill(2) + " " +
            df["HH"].astype(str).str.zfill(2) + ":" +
            df["MI"].astype(str).str.zfill(2) + ":" +
            df["SS"].astype(str).str.zfill(2)
        )
        print(df)

        return df[["DATETIME", "BX", "BY", "BZ"]]


class DownloaderApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        ui_file = QtCore.QFile("DGD_GUI.ui")
        if not ui_file.open(QtCore.QFile.ReadOnly):
            print("Nie udało się otworzyć pliku .ui")
            exit(-1)

        loader = QtUiTools.QUiLoader()
        self.window = loader.load(ui_file)
        ui_file.close()

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

        self.date_ranges_table = self.window.findChild(QtWidgets.QTableWidget, "DateRangesTable")
        self.add_range_btn = self.window.findChild(QtWidgets.QPushButton, "AddRangeButton")
        self.remove_range_btn = self.window.findChild(QtWidgets.QPushButton, "RemoveRangeButton")

        self.select_all_btn.clicked.connect(self.select_all)
        self.clear_all_btn.clicked.connect(self.clear_all)
        self.output_button.clicked.connect(self.choose_folder)
        self.start_btn.clicked.connect(self.on_start_clicked)
        self.add_range_btn.clicked.connect(self.add_range)
        self.remove_range_btn.clicked.connect(self.remove_range)

        self.window.show()

    def select_all(self):
        self.countries_list.selectAll()

    def clear_all(self):
        self.countries_list.clearSelection()

    def choose_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self.window, "Choose output folder")
        if folder:
            self.output_line.setText(folder)

    def add_range(self):
        start = self.start_date_edit.date().toString("yyyy-MM-dd")
        end = self.end_date_edit.date().toString("yyyy-MM-dd")
        row = self.date_ranges_table.rowCount()
        self.date_ranges_table.insertRow(row)
        self.date_ranges_table.setItem(row, 0, QtWidgets.QTableWidgetItem(start))
        self.date_ranges_table.setItem(row, 1, QtWidgets.QTableWidgetItem(end))

    def remove_range(self):
        selected = self.date_ranges_table.selectionModel().selectedRows()
        for idx in sorted(selected, key=lambda x: x.row(), reverse=True):
            self.date_ranges_table.removeRow(idx.row())

    def on_start_clicked(self):
        resolution = self.resolution_combo.currentText()
        source = self.source_combo.currentIndex()
        output = self.output_line.text().strip()

        stations = [
            self.countries_list.item(idx.row(), 0).text()
            for idx in self.countries_list.selectionModel().selectedRows()
        ]

        ranges = []
        for row in range(self.date_ranges_table.rowCount()):
            start_item = self.date_ranges_table.item(row, 0)
            end_item = self.date_ranges_table.item(row, 1)
            if start_item and end_item:
                start = start_item.text()
                end = end_item.text()
                if start and end:
                    ranges.append((start, end))

        if not stations:
            self.error_messages.setText("No stations selected.")
            return
        if not ranges:
            self.error_messages.setText("No date ranges added.")
            return
        if not output:
            self.error_messages.setText("No output folder selected.")
            return

        self.error_messages.clear()
        self.progress_bar.setValue(0)
        self.start_btn.setEnabled(False)

        self.thread = QtCore.QThread()
        self.worker = DownloadWorker(stations, ranges, resolution, source, output)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.message.connect(self.error_messages.append)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(lambda: self.start_btn.setEnabled(True))

        self.thread.start()

def main():
    app = QtWidgets.QApplication(argv)
    app_instance = DownloaderApp()
    app_instance.window.show()
    exit(app.exec())


if __name__ == "__main__":
    main()
