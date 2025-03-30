import sys
import random
import json
import requests
from bs4 import BeautifulSoup
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QGroupBox,
    QMenuBar, QAction, QFileDialog, QSpinBox, QTextEdit, QComboBox, QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal


class IMEIValidationThread(QThread):
    update_status = pyqtSignal(int, str)
    update_progress = pyqtSignal(int, int)  # Signal pour la progression (actuel, total)

    def __init__(self, imeis, row_indices, parent=None):
        super().__init__(parent)
        self.imeis = imeis
        self.row_indices = row_indices
        self.running = True

    def stop(self):
        self.running = False  # properly stopping thread 

    def run(self):
        total_imeis = len(self.imeis)
        for index, (row, imei) in enumerate(zip(self.row_indices, self.imeis)):
            if not self.running:
                break  # Interrompre le thread si demandé

            # Mettre à jour la progression
            self.update_progress.emit(index + 1, total_imeis)

            url = f"https://swappa.com/imei/info/{imei}"
            try:
                # Effectuer la requête HTTP
                response = requests.get(url, timeout=30)

                # Analyser le contenu HTML avec BeautifulSoup
                soup = BeautifulSoup(response.content, 'html.parser')

                # Vérifier si c'est un message d'erreur
                error_message = soup.find('div', class_='alert alert-error alert-dismissible fade show alert-danger')
                if error_message and "Invalid IMEI or TAC number" in error_message.text:
                    self.update_status.emit(row, "❌ Invalide")
                    continue  # Passer au prochain IMEI

                # Vérifier si c'est un message de succès
                success_message = soup.find('div', class_='alert alert-success text-center')
                if success_message and "Allowed." in success_message.text:
                    self.update_status.emit(row, "✅ Validé")
                else:
                    # Si aucun message n'est détecté
                    self.update_status.emit(row, "⚠️ Erreur inconnue")
            except requests.RequestException as e:
                # En cas d'erreur réseau
                print(f"Erreur réseau pour l'IMEI {imei}: {e}")
                self.update_status.emit(row, "⚠️ Erreur réseau")


class IMEIGeneratorApp(QMainWindow):
    SAVE_FILE = "models_data.json"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("IMEI's Generator and Validator")
        self.setGeometry(100, 100, 1400, 900)

        # Liste des modèles
        self.models = self.load_models()

        # Mise en place du style
        self.setStyleSheet("""
            QPushButton {
                background-color: #007ACC;
                color: white;
                border-radius: 5px;
                padding: 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #005F9E;
            }
            QLineEdit, QTableWidget {
                border: 2px solid #007ACC;
                border-radius: 5px;
                padding: 5px;
                font-size: 14px;
            }
            QLabel {
                font-size: 16px;
                font-weight: bold;
            }
            QHeaderView::section {
                background-color: #007ACC;
                color: white;
                font-size: 14px;
            }
        """)

        # Layout principal
        self.main_layout = QVBoxLayout()

        # Sections de l'interface
        self.create_menu_bar()
        self.create_intro_section()
        self.create_model_input_section()
        self.create_model_table_section()
        self.create_generate_section()
        self.create_imei_display_section()

        # Conteneur principal
        container = QWidget()
        container.setLayout(self.main_layout)
        self.setCentralWidget(container)

    def create_menu_bar(self):
        menu_bar = QMenuBar(self)
        file_menu = menu_bar.addMenu("Files")

        export_json_action = QAction("Export to JSON", self)
        export_json_action.triggered.connect(self.export_to_json)
        file_menu.addAction(export_json_action)

        export_text_action = QAction("Export to Text", self)
        export_text_action.triggered.connect(self.export_to_text)
        file_menu.addAction(export_text_action)

        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        menu_bar.addAction(about_action)

        self.setMenuBar(menu_bar)

    def show_about(self):
        QMessageBox.information(
            self,
            "About",
            "<p><b>Generate / Validate IMEI's - Not Improved Version</b></p>"
            "<p>Developed to manage, validate, and export multi-brand IMEI's.</p>"
            "<p>Made by <a href='https://github.com/enokseth'>@enok.seth</a> with ♥️</p>"
        )


    def create_intro_section(self):
        intro_box = QGroupBox()
        intro_layout = QVBoxLayout()

        intro_label = QLabel("Add models, generate IMEIs, validate them and export your results.")
        intro_label.setAlignment(Qt.AlignCenter)
        intro_layout.addWidget(intro_label)

        intro_box.setLayout(intro_layout)
        self.main_layout.addWidget(intro_box)

    def create_model_input_section(self):
        input_box = QGroupBox("Add or Edit a template")
        input_layout = QHBoxLayout()

        self.model_name_input = QLineEdit()
        self.model_name_input.setPlaceholderText("Model Name (ex: Galaxy S10)")

        self.brand_input = QLineEdit()
        self.brand_input.setPlaceholderText("Brand (ex: Samsung)")

        self.tac_input = QLineEdit()
        self.tac_input.setPlaceholderText("TAC (ex: 35191210 must be TAC must concerned model)")

        add_model_button = QPushButton("Add")
        add_model_button.clicked.connect(self.add_model)

        input_layout.addWidget(self.model_name_input)
        input_layout.addWidget(self.brand_input)
        input_layout.addWidget(self.tac_input)
        input_layout.addWidget(add_model_button)

        input_box.setLayout(input_layout)
        self.main_layout.addWidget(input_box)

    def create_model_table_section(self):
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Brand", "Model", "TAC", "BASE-IMEI", "Status", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.main_layout.addWidget(self.table)
        self.update_table()

    def create_generate_section(self):
        generate_box = QGroupBox("Generate multiple IMEIs")
        generate_layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setValue(0)

        horizontal_layout = QHBoxLayout()
        self.model_selector = QComboBox()
        self.model_selector.addItems([model["model_name"] for model in self.models])

        self.imei_count_spinner = QSpinBox()
        self.imei_count_spinner.setRange(1, 100)
        self.imei_count_spinner.setValue(10)

        generate_button = QPushButton("Generate")
        generate_button.clicked.connect(self.generate_multiple_imeis)

        horizontal_layout.addWidget(QLabel("Model :"))
        horizontal_layout.addWidget(self.model_selector)
        horizontal_layout.addWidget(QLabel("Number:"))
        horizontal_layout.addWidget(self.imei_count_spinner)
        horizontal_layout.addWidget(generate_button)

        generate_layout.addLayout(horizontal_layout)
        generate_layout.addWidget(self.progress_bar)

        generate_box.setLayout(generate_layout)
        self.main_layout.addWidget(generate_box)

    def create_imei_display_section(self):
        imei_box = QGroupBox("🔰 Generated IMEIs 🔰 ")
        imei_box.setStyleSheet("QGroupBox { text-align: center; font-weight: bold; }")
        imei_layout = QVBoxLayout()
        imei_layout.setAlignment(Qt.AlignCenter)  # Centrer les widgets internes

        self.imei_display = QTextEdit()
        self.imei_display.setReadOnly(True)

        # self.imei_display.setAlignment(Qt.AlignCenter)

        imei_layout.addWidget(self.imei_display)
        imei_box.setLayout(imei_layout)
        self.main_layout.addWidget(imei_box)

    def add_model(self):
        model_name = self.model_name_input.text().strip()
        brand = self.brand_input.text().strip()
        tac = self.tac_input.text().strip()

        if not model_name or not brand:
            QMessageBox.warning(self, "Error", "The model name and brand are required.")
            return

        if not tac.isdigit() or len(tac) != 8:
            QMessageBox.warning(self, "Error", "The TAC must be an 8-digit code.")
            return

        self.models.append({"brand": brand, "model_name": model_name, "tac": tac, "generated_imei": "", "status": "Not generated"})
        self.update_table()
        self.save_models()
        self.model_selector.addItem(model_name)

    def update_table(self):
        self.table.setRowCount(len(self.models))
        for row, model in enumerate(self.models):
            self.table.setItem(row, 0, QTableWidgetItem(model["brand"]))
            self.table.setItem(row, 1, QTableWidgetItem(model["model_name"]))
            self.table.setItem(row, 2, QTableWidgetItem(model["tac"]))
            self.table.setItem(row, 3, QTableWidgetItem(model["generated_imei"]))
            self.table.setItem(row, 4, QTableWidgetItem(model["status"]))


            generate_button = QPushButton("Générer")
            generate_button.clicked.connect(lambda _, r=row: self.generate_for_model(r))
            self.table.setCellWidget(row, 5, generate_button)

    def generate_for_model(self, row):
        model = self.models[row]
        imei = self.generate_imei_with_luhn(model["tac"])
        self.models[row]["generated_imei"] = imei
        self.imei_display.append(f"IMEI Généré : {imei} {model}")
        self.validate_imeis([imei], [row])
        self.update_table()

    def generate_multiple_imeis(self):
        model_name = self.model_selector.currentText()
        model = next((m for m in self.models if m["model_name"] == model_name), None)
        if not model:
            QMessageBox.warning(self, "Erreur", "Modèle non trouvé.")
            return

        imei_count = self.imei_count_spinner.value()
        imeis = [self.generate_imei_with_luhn(model["tac"]) for _ in range(imei_count)]
        row_indices = [self.models.index(model)] * imei_count
        for imei in imeis:
            self.imei_display.append(f"IMEI Généré : {imei}")
        self.validate_imeis(imeis, row_indices)

    def validate_imeis(self, imeis, row_indices):
        self.validation_thread = IMEIValidationThread(imeis, row_indices)
        self.validation_thread.update_status.connect(self.update_imei_status)
        self.validation_thread.update_progress.connect(self.update_progress_bar)
        self.validation_thread.start()

    def update_progress_bar(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def update_imei_status(self, row, status):
        self.models[row]["status"] = status
        self.update_table()

    def save_models(self):
        with open(self.SAVE_FILE, "w") as file:
            json.dump(self.models, file, indent=4)

    def load_models(self):
        try:
            with open(self.SAVE_FILE, "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return []

    def export_to_json(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to JSON", "", "JSON file (*.json)")
        if file_path:
            with open(file_path, "w") as file:
                json.dump(self.models, file, indent=4)

    def export_to_text(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to Text", "", "Text file (*.txt)")
        if file_path:
            with open(file_path, "w") as file:
                for model in self.models:
                    file.write(f"{model['brand']} - {model['model_name']} - {model['tac']} - {model['generated_imei']}\n")

    @staticmethod
    def generate_imei_with_luhn(tac):
        serial_number = "".join(str(random.randint(0, 9)) for _ in range(6))
        imei_without_checksum = tac + serial_number
        checksum = IMEIGeneratorApp.calculate_luhn_checksum(imei_without_checksum)
        return imei_without_checksum + str(checksum)

    @staticmethod
    def calculate_luhn_checksum(imei):
        digits = [int(d) for d in imei]
        total = sum(digits[-1::-2]) + sum((d * 2) % 9 for d in digits[-2::-2])
        return (10 - total % 10) % 10


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IMEIGeneratorApp()
    window.show()
    sys.exit(app.exec_())
