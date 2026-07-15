#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from typing import Optional

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QTabWidget, QGroupBox, QLabel,
                             QComboBox, QPushButton, QTableWidget,
                             QTableWidgetItem, QSpinBox, QMessageBox)
from PyQt5.QtCore import QTimer

from pymodbus.client.sync import ModbusSerialClient
from pymodbus.exceptions import ModbusException, ConnectionException

# ===========================================================================
# Константы регистров (из документации WB-M1W2 v.3)
# ===========================================================================
REG_INPUT_MODE_1 = 275
REG_INPUT_MODE_2 = 276
REG_FILTER_COEFF = 99
REG_POLL_PERIOD = 101
REG_DEBOUNCE_CH1 = 340
REG_DEBOUNCE_CH2 = 341
REG_LONG_PRESS_TIME_1 = 1100
REG_LONG_PRESS_TIME_2 = 1101
REG_DOUBLE_CLICK_WINDOW_1 = 1140
REG_DOUBLE_CLICK_WINDOW_2 = 1141
REG_RESET_COUNTERS = 100
REG_COUNTER_CH1 = 277
REG_COUNTER_CH2 = 278
REG_DISCRETE_INPUT_1 = 0
REG_DISCRETE_INPUT_2 = 1
REG_TEMP_CH1_START = 1536
REG_TEMP_CH2_START = 1576
REG_STATUS_CH1_START = 128
REG_STATUS_CH2_START = 168
REG_FW_VERSION = 320           # Input, числовая версия прошивки

# ===========================================================================
# Класс-обёртка для Modbus-клиента (pymodbus 2.5.3)
# ===========================================================================
class ModbusClientWrapper:
    def __init__(self):
        self.client: Optional[ModbusSerialClient] = None
        self.connected = False

    def connect(self, port: str, baudrate: int, parity: str, stopbits: int, timeout: float = 1.0):
        parity_map = {'N': 'N', 'E': 'E', 'O': 'O'}
        self.client = ModbusSerialClient(
            method='rtu',
            port=port,
            baudrate=baudrate,
            parity=parity_map.get(parity, 'N'),
            stopbits=stopbits,
            timeout=timeout
        )
        if self.client.connect():
            self.connected = True
            return True
        self.connected = False
        return False

    def disconnect(self):
        if self.client:
            self.client.close()
            self.connected = False

    def read_holding_registers(self, address: int, count: int, unit: int = 1):
        if not self.connected:
            raise ConnectionException("Not connected")
        result = self.client.read_holding_registers(address, count, unit=unit)
        if result.isError():
            raise ModbusException(f"Read error: {result}")
        return result.registers

    def write_holding_register(self, address: int, value: int, unit: int = 1):
        if not self.connected:
            raise ConnectionException("Not connected")
        result = self.client.write_register(address, value, unit=unit)
        if result.isError():
            raise ModbusException(f"Write error: {result}")
        return True

    def read_input_registers(self, address: int, count: int, unit: int = 1):
        if not self.connected:
            raise ConnectionException("Not connected")
        result = self.client.read_input_registers(address, count, unit=unit)
        if result.isError():
            raise ModbusException(f"Read error: {result}")
        return result.registers

    def read_discrete_inputs(self, address: int, count: int, unit: int = 1):
        if not self.connected:
            raise ConnectionException("Not connected")
        result = self.client.read_discrete_inputs(address, count, unit=unit)
        if result.isError():
            raise ModbusException(f"Read error: {result}")
        return result.bits

    def read_firmware_version(self, unit: int = 1) -> str:
        """Чтение версии прошивки (регистр 320)."""
        try:
            regs = self.read_input_registers(REG_FW_VERSION, 1, unit)
            major = (regs[0] >> 8) & 0xFF
            minor = regs[0] & 0xFF
            return f"{major}.{minor}"
        except:
            return "неизвестно"

# ===========================================================================
# Главное окно приложения
# ===========================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WB-M1W2 v.3 Конфигуратор и мониторинг")
        self.setMinimumSize(800, 600)

        self.modbus = ModbusClientWrapper()
        self.unit_id = 1
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self.update_monitoring)
        self.poll_interval_ms = 2000
        self.use_extended_regs = True   # флаг использования расширенных регистров

        self.setup_ui()
        self.update_port_list()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        tabs = QTabWidget()
        main_layout.addWidget(tabs)

        # ---------- Вкладка "Подключение" ----------
        conn_tab = QWidget()
        tabs.addTab(conn_tab, "Подключение")
        conn_layout = QVBoxLayout(conn_tab)

        port_group = QGroupBox("Параметры RS-485")
        port_layout = QHBoxLayout(port_group)

        port_layout.addWidget(QLabel("Порт:"))
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        port_layout.addWidget(self.port_combo)

        port_layout.addWidget(QLabel("Скорость:"))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(['9600', '19200', '38400', '57600', '115200'])
        self.baud_combo.setCurrentText('9600')
        port_layout.addWidget(self.baud_combo)

        port_layout.addWidget(QLabel("Чётность:"))
        self.parity_combo = QComboBox()
        self.parity_combo.addItems(['N', 'E', 'O'])
        port_layout.addWidget(self.parity_combo)

        port_layout.addWidget(QLabel("Стоп-биты:"))
        self.stopbits_combo = QComboBox()
        self.stopbits_combo.addItems(['1', '2'])
        port_layout.addWidget(self.stopbits_combo)

        port_layout.addWidget(QLabel("Modbus адрес:"))
        self.unit_spin = QSpinBox()
        self.unit_spin.setRange(1, 247)
        self.unit_spin.setValue(1)
        port_layout.addWidget(self.unit_spin)

        self.connect_btn = QPushButton("Подключиться")
        self.connect_btn.clicked.connect(self.toggle_connection)
        port_layout.addWidget(self.connect_btn)

        self.refresh_ports_btn = QPushButton("Обновить порты")
        self.refresh_ports_btn.clicked.connect(self.update_port_list)
        port_layout.addWidget(self.refresh_ports_btn)

        conn_layout.addWidget(port_group)
        conn_layout.addStretch()

        # ---------- Вкладка "Конфигурация" ----------
        config_tab = QWidget()
        tabs.addTab(config_tab, "Конфигурация")
        config_layout = QVBoxLayout(config_tab)

        mode_group = QGroupBox("Режимы входов")
        mode_layout = QHBoxLayout(mode_group)
        mode_layout.addWidget(QLabel("Вход 1:"))
        self.mode1_combo = QComboBox()
        self.mode1_combo.addItems(['1-Wire', 'Счёт и нажатия'])
        mode_layout.addWidget(self.mode1_combo)
        mode_layout.addWidget(QLabel("Вход 2:"))
        self.mode2_combo = QComboBox()
        self.mode2_combo.addItems(['1-Wire', 'Счёт и нажатия'])
        mode_layout.addWidget(self.mode2_combo)
        config_layout.addWidget(mode_group)

        poll_group = QGroupBox("Параметры опроса 1-Wire")
        poll_layout = QHBoxLayout(poll_group)
        poll_layout.addWidget(QLabel("Период опроса (с):"))
        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(1, 60)
        self.poll_spin.setValue(2)
        poll_layout.addWidget(self.poll_spin)
        poll_layout.addWidget(QLabel("Коэф. фильтра (x0.0625°C):"))
        self.filter_spin = QSpinBox()
        self.filter_spin.setRange(0, 19200)
        self.filter_spin.setValue(32)
        poll_layout.addWidget(self.filter_spin)
        config_layout.addWidget(poll_group)

        click_group = QGroupBox("Детектирование нажатий")
        click_layout = QVBoxLayout(click_group)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Дребезг вход 1 (мс):"))
        self.debounce1 = QSpinBox()
        self.debounce1.setRange(0, 100)
        self.debounce1.setValue(50)
        row1.addWidget(self.debounce1)
        row1.addWidget(QLabel("Дребезг вход 2 (мс):"))
        self.debounce2 = QSpinBox()
        self.debounce2.setRange(0, 100)
        self.debounce2.setValue(50)
        row1.addWidget(self.debounce2)
        click_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Длит. длинного нажатия (мс):"))
        self.long_press1 = QSpinBox()
        self.long_press1.setRange(500, 5000)
        self.long_press1.setValue(1000)
        row2.addWidget(self.long_press1)
        row2.addWidget(QLabel("Окно двойного (мс):"))
        self.double_win1 = QSpinBox()
        self.double_win1.setRange(0, 2000)
        self.double_win1.setValue(300)
        row2.addWidget(self.double_win1)
        row2.addWidget(QLabel("Вход 2:"))
        self.long_press2 = QSpinBox()
        self.long_press2.setRange(500, 5000)
        self.long_press2.setValue(1000)
        row2.addWidget(self.long_press2)
        self.double_win2 = QSpinBox()
        self.double_win2.setRange(0, 2000)
        self.double_win2.setValue(300)
        row2.addWidget(self.double_win2)
        click_layout.addLayout(row2)
        config_layout.addWidget(click_group)

        btn_row = QHBoxLayout()
        self.read_config_btn = QPushButton("Прочитать конфигурацию")
        self.read_config_btn.clicked.connect(self.read_config)
        btn_row.addWidget(self.read_config_btn)
        self.write_config_btn = QPushButton("Записать конфигурацию")
        self.write_config_btn.clicked.connect(self.write_config)
        btn_row.addWidget(self.write_config_btn)
        config_layout.addLayout(btn_row)
        config_layout.addStretch()

        # ---------- Вкладка "Мониторинг" ----------
        mon_tab = QWidget()
        tabs.addTab(mon_tab, "Мониторинг")
        mon_layout = QVBoxLayout(mon_tab)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Вход", "№ датчика", "Температура, °C", "Статус", "Счётчик"])
        self.table.horizontalHeader().setStretchLastSection(True)
        mon_layout.addWidget(self.table)

        ctrl_layout = QHBoxLayout()
        self.start_mon_btn = QPushButton("Запустить мониторинг")
        self.start_mon_btn.clicked.connect(self.start_monitoring)
        ctrl_layout.addWidget(self.start_mon_btn)
        self.stop_mon_btn = QPushButton("Остановить")
        self.stop_mon_btn.clicked.connect(self.stop_monitoring)
        self.stop_mon_btn.setEnabled(False)
        ctrl_layout.addWidget(self.stop_mon_btn)
        ctrl_layout.addWidget(QLabel("Интервал обновления (с):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 60)
        self.interval_spin.setValue(2)
        ctrl_layout.addWidget(self.interval_spin)
        self.apply_interval_btn = QPushButton("Применить")
        self.apply_interval_btn.clicked.connect(self.apply_interval)
        ctrl_layout.addWidget(self.apply_interval_btn)
        mon_layout.addLayout(ctrl_layout)

        self.populate_table()

    def update_port_list(self):
        import serial.tools.list_ports
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo.clear()
        self.port_combo.addItems(ports if ports else ["Нет портов"])

    def toggle_connection(self):
        if self.modbus.connected:
            self.modbus.disconnect()
            self.connect_btn.setText("Подключиться")
            self.set_status("Отключено")
        else:
            port = self.port_combo.currentText()
            baud = int(self.baud_combo.currentText())
            parity = self.parity_combo.currentText()
            stopbits = int(self.stopbits_combo.currentText())
            self.unit_id = self.unit_spin.value()
            if self.modbus.connect(port, baud, parity, stopbits):
                self.connect_btn.setText("Отключиться")
                fw = self.modbus.read_firmware_version(self.unit_id)
                self.set_status(f"Подключено к {port}, адрес {self.unit_id}, прошивка v{fw}")
                # Попытаемся прочитать конфигурацию
                self.read_config()
            else:
                QMessageBox.critical(self, "Ошибка", "Не удалось подключиться к устройству")
                self.set_status("Ошибка подключения")

    def set_status(self, text):
        self.statusBar().showMessage(text)

    def populate_table(self):
        self.table.setRowCount(40)
        for row in range(40):
            ch = 1 if row < 20 else 2
            sensor_num = row + 1 if row < 20 else row - 19
            self.table.setItem(row, 0, QTableWidgetItem(str(ch)))
            self.table.setItem(row, 1, QTableWidgetItem(str(sensor_num)))
            self.table.setItem(row, 2, QTableWidgetItem("---"))
            self.table.setItem(row, 3, QTableWidgetItem("---"))
            self.table.setItem(row, 4, QTableWidgetItem("---"))

    def read_config(self):
        if not self.modbus.connected:
            QMessageBox.warning(self, "Предупреждение", "Сначала подключитесь к устройству")
            return
        try:
            # Попытка прочитать режимы входов
            modes = self.modbus.read_holding_registers(REG_INPUT_MODE_1, 2, self.unit_id)
            self.mode1_combo.setCurrentIndex(modes[0])
            self.mode2_combo.setCurrentIndex(modes[1])

            # Период опроса и фильтр
            poll = self.modbus.read_holding_registers(REG_POLL_PERIOD, 1, self.unit_id)
            self.poll_spin.setValue(poll[0])
            filt = self.modbus.read_holding_registers(REG_FILTER_COEFF, 1, self.unit_id)
            self.filter_spin.setValue(filt[0])

            # Антидребезг
            deb1 = self.modbus.read_holding_registers(REG_DEBOUNCE_CH1, 1, self.unit_id)
            self.debounce1.setValue(deb1[0])
            deb2 = self.modbus.read_holding_registers(REG_DEBOUNCE_CH2, 1, self.unit_id)
            self.debounce2.setValue(deb2[0])

            # Параметры нажатий
            lp1 = self.modbus.read_holding_registers(REG_LONG_PRESS_TIME_1, 1, self.unit_id)
            self.long_press1.setValue(lp1[0])
            dw1 = self.modbus.read_holding_registers(REG_DOUBLE_CLICK_WINDOW_1, 1, self.unit_id)
            self.double_win1.setValue(dw1[0])
            lp2 = self.modbus.read_holding_registers(REG_LONG_PRESS_TIME_2, 1, self.unit_id)
            self.long_press2.setValue(lp2[0])
            dw2 = self.modbus.read_holding_registers(REG_DOUBLE_CLICK_WINDOW_2, 1, self.unit_id)
            self.double_win2.setValue(dw2[0])

            self.set_status("Конфигурация прочитана")
        except Exception as e:
            # Если ошибка, покажем сообщение, но не прерываем работу
            QMessageBox.warning(self, "Ошибка чтения конфигурации",
                                f"Не удалось прочитать некоторые регистры.\nВозможно, устройство имеет старую прошивку.\nОшибка: {str(e)}")
            self.set_status("Ошибка чтения конфигурации")

    def write_config(self):
        if not self.modbus.connected:
            QMessageBox.warning(self, "Предупреждение", "Сначала подключитесь к устройству")
            return
        try:
            self.modbus.write_holding_register(REG_INPUT_MODE_1, self.mode1_combo.currentIndex(), self.unit_id)
            self.modbus.write_holding_register(REG_INPUT_MODE_2, self.mode2_combo.currentIndex(), self.unit_id)
            self.modbus.write_holding_register(REG_POLL_PERIOD, self.poll_spin.value(), self.unit_id)
            self.modbus.write_holding_register(REG_FILTER_COEFF, self.filter_spin.value(), self.unit_id)
            self.modbus.write_holding_register(REG_DEBOUNCE_CH1, self.debounce1.value(), self.unit_id)
            self.modbus.write_holding_register(REG_DEBOUNCE_CH2, self.debounce2.value(), self.unit_id)
            self.modbus.write_holding_register(REG_LONG_PRESS_TIME_1, self.long_press1.value(), self.unit_id)
            self.modbus.write_holding_register(REG_DOUBLE_CLICK_WINDOW_1, self.double_win1.value(), self.unit_id)
            self.modbus.write_holding_register(REG_LONG_PRESS_TIME_2, self.long_press2.value(), self.unit_id)
            self.modbus.write_holding_register(REG_DOUBLE_CLICK_WINDOW_2, self.double_win2.value(), self.unit_id)

            self.set_status("Конфигурация записана")
            QMessageBox.information(self, "Успех", "Настройки записаны в устройство")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка записи", str(e))

    def start_monitoring(self):
        if not self.modbus.connected:
            QMessageBox.warning(self, "Предупреждение", "Сначала подключитесь к устройству")
            return
        self.poll_interval_ms = self.interval_spin.value() * 1000
        self.poll_timer.start(self.poll_interval_ms)
        self.start_mon_btn.setEnabled(False)
        self.stop_mon_btn.setEnabled(True)
        self.set_status("Мониторинг запущен")
        # Попробуем сначала использовать расширенные регистры
        self.use_extended_regs = True
        self.update_monitoring()

    def stop_monitoring(self):
        self.poll_timer.stop()
        self.start_mon_btn.setEnabled(True)
        self.stop_mon_btn.setEnabled(False)
        self.set_status("Мониторинг остановлен")

    def apply_interval(self):
        if self.poll_timer.isActive():
            self.poll_interval_ms = self.interval_spin.value() * 1000
            self.poll_timer.setInterval(self.poll_interval_ms)
            self.set_status(f"Интервал обновлён: {self.interval_spin.value()} с")

    def update_monitoring(self):
        if not self.modbus.connected:
            return
        try:
            if self.use_extended_regs:
                # Пытаемся прочитать расширенные регистры (для прошивки >= 4.35.0)
                status1 = self.modbus.read_discrete_inputs(REG_STATUS_CH1_START, 20, self.unit_id)
                status2 = self.modbus.read_discrete_inputs(REG_STATUS_CH2_START, 20, self.unit_id)
                temps1 = self.modbus.read_input_registers(REG_TEMP_CH1_START, 20, self.unit_id)
                temps2 = self.modbus.read_input_registers(REG_TEMP_CH2_START, 20, self.unit_id)
            else:
                # Используем базовые регистры (только по одному датчику на вход)
                temps1 = self.modbus.read_input_registers(7, 1, self.unit_id)   # вход 1
                temps2 = self.modbus.read_input_registers(8, 1, self.unit_id)   # вход 2
                status1 = [1] * 20  # условно считаем, что датчики есть
                status2 = [1] * 20
                # Заполняем остальные температуры нулями
                temps1 = temps1 + [0] * 19
                temps2 = temps2 + [0] * 19

            # Чтение дискретных входов и счётчиков (для режима нажатий)
            try:
                disc1 = self.modbus.read_discrete_inputs(REG_DISCRETE_INPUT_1, 1, self.unit_id)
                disc2 = self.modbus.read_discrete_inputs(REG_DISCRETE_INPUT_2, 1, self.unit_id)
                cnt1 = self.modbus.read_input_registers(REG_COUNTER_CH1, 1, self.unit_id)[0]
                cnt2 = self.modbus.read_input_registers(REG_COUNTER_CH2, 1, self.unit_id)[0]
            except:
                disc1 = [0]
                disc2 = [0]
                cnt1 = cnt2 = 0

            # Обновляем таблицу
            for row in range(40):
                ch = 1 if row < 20 else 2
                sensor_idx = row if row < 20 else row - 20
                if ch == 1:
                    temp_raw = temps1[sensor_idx] if sensor_idx < len(temps1) else 0x7FFF
                    status = status1[sensor_idx] if sensor_idx < len(status1) else 0
                else:
                    temp_raw = temps2[sensor_idx] if sensor_idx < len(temps2) else 0x7FFF
                    status = status2[sensor_idx] if sensor_idx < len(status2) else 0

                if temp_raw == 0x7FFF:
                    temp_str = "Ошибка"
                else:
                    temp_val = temp_raw * 0.0625
                    temp_str = f"{temp_val:.2f}"

                status_str = "OK" if status else "Нет датчика"

                mode = self.mode1_combo.currentIndex() if ch == 1 else self.mode2_combo.currentIndex()
                if mode == 1:  # дискретный
                    if ch == 1:
                        disc_state = disc1[0] if disc1 else 0
                        counter = cnt1
                    else:
                        disc_state = disc2[0] if disc2 else 0
                        counter = cnt2
                    extra = f"Состояние: {disc_state}, Счётчик: {counter}"
                else:
                    extra = "---"

                self.table.setItem(row, 2, QTableWidgetItem(temp_str))
                self.table.setItem(row, 3, QTableWidgetItem(status_str))
                self.table.setItem(row, 4, QTableWidgetItem(extra))

            self.set_status("Данные обновлены")
        except Exception as e:
            # Если ошибка при чтении расширенных регистров, переключаемся на базовые
            if self.use_extended_regs and "IllegalAddress" in str(e):
                self.use_extended_regs = False
                self.set_status("Расширенные регистры не поддерживаются, переключение на базовые")
                # Повторяем обновление с базовыми
                self.update_monitoring()
            else:
                self.set_status(f"Ошибка чтения: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())