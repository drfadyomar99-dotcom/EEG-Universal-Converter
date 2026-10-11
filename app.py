import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget, QScrollArea,
    QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QToolButton, QSizePolicy, QDialog)

APP = 'EEG Universal Converter'

TEAM_IMAGE_NAME = 'our_team_bci_research_profiles.png'


def asset_path(filename):
    """Find bundled resources in development, PyInstaller and installed builds."""
    roots = []
    if getattr(sys, 'frozen', False):
        roots.append(Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent)))
        roots.append(Path(sys.executable).resolve().parent)
    roots.append(Path(__file__).resolve().parent)
    for root in roots:
        for candidate in (root / 'assets' / filename, root / filename):
            if candidate.is_file():
                return candidate
    return roots[-1] / 'assets' / filename


def configure_app_identity(app):
    """Use a stable Windows taskbar identity and the same icon as the EXE."""
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                'EEGUniversalConverter.ResearchTeam.Desktop')
        except (AttributeError, OSError):
            pass
    icon_file = asset_path('EEGUniversalConverter.ico')
    if icon_file.is_file():
        icon = QIcon(str(icon_file))
        if not icon.isNull():
            app.setWindowIcon(icon)
    return icon_file


class TeamDialog(QDialog):
    # Responsive team profile image viewer.
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Our Team | EEG Universal Converter')
        self.setWindowIcon(QApplication.instance().windowIcon())
        self.resize(1050, 780)
        self.setMinimumSize(540, 440)
        self.setStyleSheet('''
            QDialog { background: #F5F8FC; color: #20384F; }
            QLabel { background: transparent; }
            QPushButton { background: #087E88; color: white; padding: 10px 24px;
                border: 0; border-radius: 8px; font: 600 10pt 'Segoe UI'; }
            QPushButton:hover { background: #086B76; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(10)

        title = QLabel('Our Team')
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet('color:#15324F; font: 700 23pt "Segoe UI";')
        layout.addWidget(title)

        subtitle = QLabel('The researchers behind EEG Universal Converter')
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet('color:#60778D; font: 10pt "Segoe UI";')
        layout.addWidget(subtitle)

        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignCenter)
        self.picture.setMinimumHeight(200)
        self.picture.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.picture.setStyleSheet('background:white; border:1px solid #DBE5EF; border-radius:12px;')
        layout.addWidget(self.picture, 1)

        close = QPushButton('Close')
        close.clicked.connect(self.accept)
        close.setFixedWidth(135)
        layout.addWidget(close, 0, Qt.AlignHCenter)

        filename = asset_path(TEAM_IMAGE_NAME)
        self.original = QPixmap(str(filename))
        if self.original.isNull():
            self.picture.setText('Team image not found.\nExpected: assets/' + TEAM_IMAGE_NAME)
            self.picture.setStyleSheet('color:#9C4A29; background:white; border:1px solid #DBE5EF;')
        else:
            self._scale_image()

    def _scale_image(self):
        if not self.original.isNull():
            size = self.picture.size()
            if size.width() > 12 and size.height() > 12:
                self.picture.setPixmap(self.original.scaled(
                    size.width()-12, size.height()-12,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._scale_image()

    def showEvent(self, event):
        super().showEvent(event)
        self._scale_image()


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP + ' | 0.4.2')
        icon = asset_path('EEGUniversalConverter.ico')
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1120, 800)
        self.setMinimumSize(850, 640)
        self.path = None
        self.raw = None
        self._ui()

    def _ui(self):
        self.pages = QStackedWidget()
        self.setCentralWidget(self.pages)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.pages.addWidget(scroll)
        center = QWidget()
        scroll.setWidget(center)
        layout = QVBoxLayout(center)
        layout.setContentsMargins(28, 22, 28, 28)
        layout.setSpacing(18)
        top = QHBoxLayout()
        title = QLabel('EEG Universal Converter')
        title.setObjectName('title')
        top.addWidget(title)
        top.addStretch()
        team_button = QPushButton('Our Team')
        team_button.setObjectName('subtleButton')
        team_button.setToolTip('Meet the EEG Universal Converter team')
        team_button.clicked.connect(self.open_team_dialog)
        top.addWidget(team_button)
        version = QLabel('RESEARCH WORKSPACE   •   v0.4.2')
        version.setObjectName('version')
        top.addWidget(version)
        layout.addLayout(top)
        subtitle = QLabel('Inspect, convert and validate continuous EEG recordings — all in one workspace.')
        subtitle.setObjectName('subtitle')
        layout.addWidget(subtitle)
        steps = QLabel('1   SELECT RECORDING      →      2   REVIEW DATA      →      3   EXPORT & VALIDATE')
        steps.setObjectName('steps')
        layout.addWidget(steps)

        upload = QFrame(); upload.setObjectName('panel')
        ul = QVBoxLayout(upload); ul.setContentsMargins(20, 18, 20, 18); ul.setSpacing(10)
        ul.addWidget(QLabel('01  SOURCE DATASET', objectName='section'))
        self.path_edit = QLineEdit(); self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText('Choose an EDF, BDF, GDF, FIF, SET, VHDR or CSV recording')
        row = QHBoxLayout(); row.addWidget(self.path_edit, 1)
        btn = QPushButton('  Open recording…  '); btn.setObjectName('accent'); btn.clicked.connect(self.browse)
        row.addWidget(btn); ul.addLayout(row)
        form = QFormLayout()
        self.csv_fs = QLineEdit('250')
        self.csv_fs.setToolTip('CSV files do not contain a standard sampling rate. Supply it manually.')
        self.csv_unit = QComboBox(); self.csv_unit.addItems(['µV', 'V'])
        form.addRow('CSV sampling rate (Hz)', self.csv_fs)
        form.addRow('CSV signal units', self.csv_unit)
        self.csv_settings = QWidget()
        self.csv_settings.setLayout(form)
        ul.addWidget(self.csv_settings)
        self.csv_settings.setVisible(False)
        self.inspect = QPushButton('↻  Reinspect file')
        self.inspect.clicked.connect(self.inspect_file)
        self.inspect.setEnabled(False)
        self.inspect.setMaximumWidth(165)
        ul.addWidget(self.inspect)
        layout.addWidget(upload)

        overview_header = QLabel('02  DATASET CONTENTS')
        overview_header.setObjectName('section')
        layout.addWidget(overview_header)
        cards = QHBoxLayout()
        cards.setSpacing(14)
        self.detail_sections = {}
        self.cards = {}
        for key, title, symbol in [
            ('signals', 'EEG SIGNALS', '∿'),
            ('events', 'ANNOTATIONS / EVENTS', '◷'),
            ('metadata', 'METADATA', '▤')
        ]:
            card = QFrame(); card.setObjectName('overviewCard')
            c = QVBoxLayout(card); c.setContentsMargins(18, 15, 18, 14); c.setSpacing(8)
            h = QLabel(symbol + '   ' + title); h.setObjectName('cardHeader'); c.addWidget(h)
            number = QLabel('—'); number.setObjectName('cardNumber'); c.addWidget(number)
            summary = QLabel('Select an EEG recording'); summary.setObjectName('cardSummary')
            summary.setWordWrap(True); summary.setMinimumHeight(48); c.addWidget(summary)
            detail = QPushButton('View details  →'); detail.setObjectName('cardLink')
            detail.clicked.connect(lambda checked=False, name=key: self.show_details(name))
            detail.setEnabled(False)
            c.addWidget(detail)
            cards.addWidget(card, 1)
            self.cards[key] = (number, summary, detail)
        layout.addLayout(cards)
        self.info_text = QLabel('No recording inspected yet.')
        self.types_text = QLabel('Channel types: —')
        self.modality_text = QLabel('Not inspected')
        self.modality_text.setObjectName('modalityValue')
        self.compatibility_text = QLabel('Select a file to inspect compatibility.')
        self.compatibility_text.setObjectName('compatibilityStatus')
        info = QFrame(); info.setObjectName('panel')
        il = QVBoxLayout(info); il.setContentsMargins(20, 17, 20, 17); il.setSpacing(7)
        il.addWidget(QLabel('DETECTION & COMPATIBILITY', objectName='section'))
        il.addWidget(QLabel('Identified signal type', objectName='hint'))
        il.addWidget(self.modality_text)
        il.addWidget(self.compatibility_text)
        il.addSpacing(8)
        for t in (self.info_text, self.types_text):
            t.setWordWrap(True); il.addWidget(t)
        layout.addWidget(info)

        output = QFrame(); output.setObjectName('panel')
        ol = QVBoxLayout(output); ol.setContentsMargins(20, 18, 20, 18); ol.setSpacing(12)
        ol.addWidget(QLabel('03  CONVERSION WORKSPACE', objectName='section'))
        form2 = QFormLayout()
        self.format = QComboBox(); self.format.addItems(['FIF (.fif)', 'CSV (.csv)', 'EDF (.edf)', 'EEGLAB SET (.set)', 'BrainVision VHDR (.vhdr)', 'MAT (.mat)'])
        self.format.setToolTip('FIF, CSV bundle, EDF, EEGLAB SET, BrainVision VHDR, MAT. BDF/GDF remain input-only.')
        self.format.currentTextChanged.connect(self._update_format_hint)
        form2.addRow('Output format', self.format)
        self.output_dir = QLineEdit(str(Path.home() / 'Documents'))
        folder = QPushButton('Browse…'); folder.clicked.connect(self.select_folder)
        rr = QHBoxLayout(); rr.addWidget(self.output_dir, 1); rr.addWidget(folder)
        form2.addRow('Save to', rr)
        ol.addLayout(form2)
        self.export_hint = QLabel('CSV creates a research bundle. Some other formats may have precision or metadata limitations.')
        self.export_hint.setObjectName('hint'); self.export_hint.setWordWrap(True)
        ol.addWidget(self.export_hint)
        self._update_format_hint(self.format.currentText())
        self.convert = QPushButton('Convert & validate  →')
        self.convert.setMinimumHeight(44)
        self.convert.setObjectName('primary')
        self.convert.clicked.connect(self.convert_file)
        self.convert.setEnabled(False)
        ol.addWidget(self.convert)
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setValue(0); self.progress.setFixedHeight(14)
        ol.addWidget(self.progress)
        layout.addWidget(output)

        logs = QFrame(); logs.setObjectName('panel')
        ll = QVBoxLayout(logs); ll.setContentsMargins(20, 16, 20, 16); ll.setSpacing(10)
        tools = QHBoxLayout()
        tools.addWidget(QLabel('04  ACTIVITY & VALIDATION', objectName='section'))
        tools.addStretch()
        self.toggle_log = QPushButton('Show technical log  ▾')
        self.toggle_log.setObjectName('subtleButton')
        self.toggle_log.setCheckable(True)
        self.toggle_log.setChecked(False)
        self.toggle_log.toggled.connect(self._toggle_log)
        tools.addWidget(self.toggle_log)
        ll.addLayout(tools)
        self.activity_summary = QLabel('Choose a recording to get started.')
        self.activity_summary.setObjectName('hint')
        self.activity_summary.setWordWrap(True)
        ll.addWidget(self.activity_summary)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True)
        self.log.setPlaceholderText('Technical conversion and validation logs appear here.')
        self.log.setMinimumHeight(165)
        self.log.setVisible(False)
        ll.addWidget(self.log)
        self.view_validation = QPushButton('Open latest validation results  →')
        self.view_validation.setObjectName('accent')
        self.view_validation.setEnabled(False)
        self.view_validation.clicked.connect(lambda: self.pages.setCurrentIndex(2))
        ll.addWidget(self.view_validation)
        layout.addWidget(logs)
        self._build_detail_page()
        self._build_validation_page()
        self.statusBar().showMessage('Ready. No file selected.')
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#F5F8FC; color:#24394E; font-family:'Segoe UI'; font-size:10pt; }
            #title { font-size:24pt; font-weight:750; color:#15324F; }
            #version { color:#637F94; font-size:9pt; font-weight:700; }
            #subtitle { color:#657A8D; font-size:10pt; }
            #steps { background:#EAF2F8; color:#235879; border:1px solid #D5E5F1;
                     border-radius:9px; padding:13px 15px; font-size:9pt; font-weight:700; }
            #section { font-size:10pt; color:#087D87; font-weight:750; }
            #hint { color:#708397; font-size:9pt; }
            #overviewCard { background:white; border:1px solid #D9E5EF; border-radius:13px; }
            #cardHeader { color:#087F85; font-size:10pt; font-weight:750; }
            #cardNumber { color:#193958; font-size:23pt; font-weight:750; }
            #cardSummary { color:#60778D; font-size:9pt; }
            QScrollArea { border:none; background:#F5F8FC; }
            #panel { background:white; border:1px solid #DBE5EF; border-radius:12px; }
            QLabel { background:transparent; }
            QLineEdit, QPlainTextEdit, QComboBox { background:white; border:1px solid #CAD8E5;
                border-radius:7px; padding:8px 10px; selection-background-color:#BFE7E5; }
            QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border:2px solid #178F98; }
            QComboBox { min-height:22px; }
            QPushButton { background:#EFF5FA; color:#244C65; border:1px solid #CADDEB;
                border-radius:7px; padding:9px 14px; font-weight:650; }
            QPushButton:hover { background:#E0EEF8; border-color:#A3C7DC; }
            QPushButton:pressed { background:#CCDEE9; }
            QPushButton:disabled { color:#9BA9B8; background:#F3F5F7; border-color:#E5EAF0; }
            #primary, #accent { background:#087E88; color:white; border:1px solid #087E88; }
            #primary:hover, #accent:hover { background:#086B76; border-color:#086B76; }
            #primary:disabled, #accent:disabled { background:#B8CBCE; border-color:#B8CBCE; }
            #cardLink { background:#F0F9F9; border:1px solid #D2ECEA; color:#087F85; text-align:left; }
            #subtleButton { background:white; border:0; color:#32718A; font-size:9pt; }
            #detailTitle { color:#193958; font-size:22pt; font-weight:750; }
            #detailSubtitle { color:#60788E; font-size:10pt; }
            #modalityValue { color:#13717B; font-size:16pt; font-weight:750; }
            #compatibilityStatus { color:#536E85; font-weight:700; }
            QTableWidget { background:white; alternate-background-color:#F7FAFD; border:1px solid #DFE7EF;
                border-radius:7px; gridline-color:#E7EDF3; }
            QHeaderView::section { background:#EAF2F8; color:#28506A; font-weight:700; padding:10px; border:0; }
            #backButton { background:#EDF5FB; color:#244C65; }
            QProgressBar { background:#E9F0F5; border:0; border-radius:6px; text-align:center; }
            QProgressBar::chunk { background:#078B8E; border-radius:6px; }
            QStatusBar { background:#EBF1F7; color:#5C7387; }
        """)

    def open_team_dialog(self):
        TeamDialog(self).exec()

    def _update_format_hint(self, value):
        if value.startswith('CSV'):
            hint = 'CSV research bundle: signals, annotations, metadata and validation report.'
        elif value.startswith('EDF'):
            hint = 'EDF may quantize EEG values and omit some source metadata. Validation reports the differences.'
        elif value.startswith('MAT'):
            hint = 'MAT export uses the application’s documented MATLAB structure, not arbitrary .mat layouts.'
        elif value.startswith('BrainVision'):
            hint = 'BrainVision export creates multiple related files. Keep them together.'
        elif value.startswith('EEGLAB'):
            hint = 'EEGLAB export: check round-trip validation and metadata limitations.'
        else:
            hint = 'FIF preserves MNE recording structure; check the validation results for any limitations.'
        self.export_hint.setText(hint)

    def _toggle_log(self, visible):
        self.log.setVisible(visible)
        self.toggle_log.setText('Hide technical log  ▴' if visible else 'Show technical log  ▾')

    def _reset_cards(self):
        self.detail_sections = {}
        for number, summary, detail in self.cards.values():
            number.setText('—')
            summary.setText('Not inspected')
            detail.setEnabled(False)

    def _populate_cards(self, types, modality):
        raw = self.raw
        eeg_count = types.get('eeg', 0)
        annotations = raw.annotations
        fs = float(raw.info['sfreq'])
        counts = ', '.join(f'{kind}: {count}' for kind, count in sorted(types.items()))
        channel_details = '\n'.join(
            f'{i+1:>3}. {name}  [{kind}]'
            for i, (name, kind) in enumerate(zip(raw.ch_names, raw.get_channel_types()))
        )
        signal_lines = (f'EEG channels: {eeg_count} / total channels: {len(raw.ch_names)}\n'
                        f'Sampling rate: {fs:g} Hz\nSamples: {raw.n_times:,}\n'
                        f'Duration: {raw.n_times/fs:.3f} s\nChannel types: {counts}\n\n'
                        f'CHANNELS\n{channel_details}')
        event_rows = '\n'.join(
            f'{i+1}. Onset: {float(a):.6f} s | Duration: {float(b):.6f} s | Label: {c}'
            for i, (a,b,c) in enumerate(zip(annotations.onset,annotations.duration,annotations.description))
        ) or 'No annotations exposed through MNE Raw.annotations. Stim channels/embedded events may still exist.'
        event_lines = ('Annotations from Raw.annotations (not necessarily all trigger events):\n'
                       + event_rows + '\n\nStim channels: ' + ', '.join(
                           name for name, kind in zip(raw.ch_names,raw.get_channel_types()) if kind == 'stim'
                       ))
        montage = raw.get_montage()
        original_ref = raw.info.get('custom_ref_applied')
        meta_lines = (f'Source: {self.path.name}\nFormat: {self.path.suffix.upper()}\n'
                      f'Channel types: {counts}\nSampling frequency: {fs:g} Hz\n'
                      f'Annotations: {len(annotations)}\n'
                      f'Montage available: {"Yes" if montage is not None else "No"}\n'
                      f'Custom reference flag: {original_ref}\n'
                      f'Measurement date: {raw.info.get("meas_date") or "Not available"}\n'
                      'Full device / amplifier metadata may be unavailable or format-dependent.')
        self.detail_sections = {'signals': signal_lines, 'events': event_lines, 'metadata': meta_lines}
        content = {
            'signals': (str(eeg_count), f'EEG / {len(raw.ch_names)} total channels\n{fs:g} Hz  ·  {raw.n_times:,} samples'),
            'events': (str(len(annotations)), 'Raw.annotations entries\nStim-channel events checked separately'),
            'metadata': (self.path.suffix.upper().lstrip('.'), f'{counts}\nMontage: {"available" if montage else "not available"}')
        }
        for key,(n,s) in content.items():
            number, summary, detail = self.cards[key]
            number.setText(n); summary.setText(s); detail.setEnabled(True)

    def _build_detail_page(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        inner = QWidget()
        page.setWidget(inner)
        column = QVBoxLayout(inner)
        column.setContentsMargins(35, 26, 35, 30)
        column.setSpacing(15)
        nav = QHBoxLayout()
        back = QPushButton('←  Back to dashboard')
        back.setObjectName('backButton')
        back.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        nav.addWidget(back)
        nav.addStretch()
        nav.addWidget(QLabel('DATASET EXPLORER  ·  v0.4.2'))
        column.addLayout(nav)
        self.detail_title = QLabel('Dataset details')
        self.detail_title.setObjectName('detailTitle')
        column.addWidget(self.detail_title)
        self.detail_subtitle = QLabel('')
        self.detail_subtitle.setObjectName('detailSubtitle')
        self.detail_subtitle.setWordWrap(True)
        column.addWidget(self.detail_subtitle)
        self.detail_description = QLabel('')
        self.detail_description.setWordWrap(True)
        column.addWidget(self.detail_description)
        self.detail_table = QTableWidget()
        self.detail_table.setAlternatingRowColors(True)
        self.detail_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.detail_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.detail_table.verticalHeader().setVisible(False)
        self.detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.detail_table.setMinimumHeight(430)
        column.addWidget(self.detail_table)
        self.detail_footnote = QLabel('')
        self.detail_footnote.setWordWrap(True)
        self.detail_footnote.setObjectName('detailSubtitle')
        column.addWidget(self.detail_footnote)
        column.addStretch()
        self.pages.addWidget(page)

    def _build_validation_page(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        inside = QWidget()
        page.setWidget(inside)
        column = QVBoxLayout(inside)
        column.setContentsMargins(35, 26, 35, 30)
        back = QPushButton('←  Back to dashboard')
        back.setObjectName('backButton')
        back.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        column.addWidget(back)
        heading = QLabel('Conversion Validation Results')
        heading.setObjectName('detailTitle')
        column.addWidget(heading)
        self.validation_status = QLabel('No validation run yet.')
        self.validation_status.setObjectName('modalityValue')
        column.addWidget(self.validation_status)
        self.validation_description = QLabel('')
        self.validation_description.setWordWrap(True)
        column.addWidget(self.validation_description)
        self.validation_table = QTableWidget()
        self.validation_table.setColumnCount(2)
        self.validation_table.setHorizontalHeaderLabels(['Validation metric', 'Result'])
        self.validation_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.validation_table.verticalHeader().setVisible(False)
        self.validation_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.validation_table.setAlternatingRowColors(True)
        column.addWidget(self.validation_table)
        footnote = QLabel('PASS reflects the documented checks only. Full metadata equivalence and stim reconstruction are not verified.')
        footnote.setWordWrap(True)
        column.addWidget(footnote)
        self.pages.addWidget(page)

    def _show_validation_report(self, report, folder):
        passed = bool(report.get('overall_validation_passed', False))
        self.validation_status.setText('PASS  •  All implemented checks passed' if passed else 'REVIEW  •  One or more checks failed')
        self.validation_description.setText('Report saved to: ' + str(folder / report['files'][-1]))
        sections = [('Signal', report.get('signal_validation', {})),
                    ('Annotations', report.get('annotation_validation', {})),
                    ('Core metadata', report.get('metadata_validation', {}))]
        rows = []
        for title, values in sections:
            for key, value in values.items():
                shown = 'PASS' if value is True else 'FAIL' if value is False else str(value)
                rows.append((title + '  /  ' + key.replace('_',' '), shown))
        rows.append(('Complete metadata equivalence', str(report.get('full_metadata_equivalence', 'NOT_VERIFIED'))))
        self.validation_table.setRowCount(len(rows))
        for i, (name, value) in enumerate(rows):
            self.validation_table.setItem(i, 0, QTableWidgetItem(name))
            self.validation_table.setItem(i, 1, QTableWidgetItem(value))
        self.view_validation.setEnabled(True)
        self.pages.setCurrentIndex(2)

    def show_details(self, key):
        if self.raw is None: return
        raw = self.raw
        types = raw.get_channel_types()
        names = raw.ch_names
        self.detail_subtitle.setText(f'Source: {self.path.name}   •   Continuous recording')
        if key == 'signals':
            self.detail_title.setText('EEG Signals  /  Channel Explorer')
            self.detail_description.setText(f'{len(names)} total channels  •  {raw.info["sfreq"]:g} Hz  •  {raw.n_times:,} samples. All channel types are listed below; non-EEG channels are not relabeled.')
            headers = ['#','Channel name','Detected type','Unit (MNE)']
            unit_lookup = {0:'FIFF_UNIT_NONE', 107:'V', 201:'T', 202:'T/m', 203:'A', 204:'K', 6:'mol'}
            rows = []
            for i,(name,kind,ch) in enumerate(zip(names, types, raw.info['chs'])):
                unit = ch.get('unit')
                label = unit_lookup.get(unit, str(unit) if unit is not None else 'Not available')
                rows.append([str(i+1),name,kind.upper(),label])
            note = 'Units shown as recorded in the MNE channel metadata. Unit code values outside the display mapping are shown numerically.'
        elif key == 'events':
            self.detail_title.setText('Annotations & Events')
            self.detail_description.setText(f'{len(raw.annotations)} annotation(s) exposed through MNE Raw.annotations.')
            headers = ['#','Onset (s)','Duration (s)','Description']
            rows = [[str(i+1),f'{float(a):.6f}',f'{float(b):.6f}',str(c)] for i,(a,b,c) in enumerate(zip(raw.annotations.onset,raw.annotations.duration,raw.annotations.description))]
            note = 'Stim-channel triggers and other embedded events may require separate extraction. This table is not a complete event audit.'
            if not rows: rows = [['—','—','—','No Raw.annotations entries found']]
        else:
            self.detail_title.setText('Recording Metadata')
            self.detail_description.setText('Metadata reported by the reader. Unavailable fields are shown explicitly.')
            headers = ['Property','Value']
            from collections import Counter
            count = Counter(types)
            montage = raw.get_montage()
            details = [('Input filename',self.path.name),('Input format',self.path.suffix.upper()),('Signal sampling rate',f'{raw.info["sfreq"]:g} Hz'),('Total channels',len(names)),('Samples',raw.n_times),('Duration',f'{raw.n_times/raw.info["sfreq"]:.3f} s'),('Channel types',', '.join(f'{k}: {v}' for k,v in sorted(count.items()))),('Annotations',len(raw.annotations)),('Montage','Available' if montage is not None else 'Not available'),('Measurement date',str(raw.info.get('meas_date') or 'Not available')),('High-pass filter',raw.info.get('highpass','Not available')),('Low-pass filter',raw.info.get('lowpass','Not available')),('Description',raw.info.get('description') or 'Not available')]
            rows = [[str(k),str(v)] for k,v in details]
            note = 'Metadata completeness varies by input format. Export validation remains a separate step.'
        self.detail_table.clear()
        self.detail_table.setColumnCount(len(headers))
        self.detail_table.setHorizontalHeaderLabels(headers)
        self.detail_table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate(row):
                self.detail_table.setItem(i,j,QTableWidgetItem(str(value)))
        self.detail_footnote.setText(note)
        self.pages.setCurrentIndex(1)

    def browse(self):
        filters = ('EEG files (*.edf *.bdf *.gdf *.fif *.fif.gz *.set *.vhdr *.csv *.mat);;'
                   'All files (*.*)')
        path, _ = QFileDialog.getOpenFileName(self, 'Choose continuous EEG recording', '', filters)
        if path:
            self.path = Path(path)
            self.path_edit.setText(path)
            self.csv_settings.setVisible(self.path.suffix.lower() == '.csv')
            self.types_text.setText('Channel types: —')
            self.modality_text.setText('Not inspected')
            self.compatibility_text.setText('Select a file to inspect compatibility.')
            self.raw = None
            self.inspect.setEnabled(True)
            self.convert.setEnabled(False)
            self.progress.setValue(0)
            self.info_text.setText('File selected. Click Inspect selected file.')
            self.log.clear()
            self.view_validation.setEnabled(False)
            self._reset_cards()
            self.inspect_file()  # Auto-inspect immediately after loading a file.

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Output folder', self.output_dir.text())
        if folder: self.output_dir.setText(folder)

    def _read(self):
        import mne
        ext = self.path.suffix.lower()
        if self.path.name.lower().endswith('.fif.gz'): ext = '.fif'
        if ext == '.csv':
            fs = float(self.csv_fs.text())
            if not np.isfinite(fs) or fs <= 0: raise ValueError('CSV sampling rate must be positive.')
            df = pd.read_csv(self.path)
            # Numeric columns only; skip an explicitly named time axis.
            numeric = df.select_dtypes(include=[np.number]).copy()
            for col in list(numeric.columns):
                if str(col).strip().lower() in ('time','timestamp','time_s','time_sec','seconds'):
                    numeric.drop(columns=[col], inplace=True)
            if numeric.empty: raise ValueError('CSV must contain numeric channel columns.')
            values = numeric.to_numpy(dtype=float)
            if not np.isfinite(values).all():
                raise ValueError('CSV contains NaN or infinite values; clean or resolve before converting.')
            scale = 1e-6 if self.csv_unit.currentText() == 'µV' else 1.0
            info = mne.create_info([str(c) for c in numeric.columns], fs, ch_types='eeg')
            return mne.io.RawArray((values * scale).T, info, verbose='ERROR')
        if ext == '.mat':
            from multiformat import read_mat
            return read_mat(self.path)
        if ext == '.edf': return mne.io.read_raw_edf(self.path, preload=False, verbose='ERROR')
        if ext == '.bdf': return mne.io.read_raw_bdf(self.path, preload=False, verbose='ERROR')
        if ext == '.gdf': return mne.io.read_raw_gdf(self.path, preload=False, verbose='ERROR')
        if ext == '.fif': return mne.io.read_raw_fif(self.path, preload=False, verbose='ERROR')
        if ext == '.set': return mne.io.read_raw_eeglab(self.path, preload=False, verbose='ERROR')
        if ext == '.vhdr': return mne.io.read_raw_brainvision(self.path, preload=False, verbose='ERROR')
        raise ValueError(f'Unsupported source format: {ext}.')

    @staticmethod
    def _identify_modality(types):
        keys = set(types)
        groups = [
            ('EEG', {'eeg','ecog','seeg','dbs'}),
            ('fNIRS', {'hbo','hbr','fnirs_cw_amplitude','fnirs_od','fnirs_fd_ac_amplitude','fnirs_fd_phase','fnirs_fd_od'}),
            ('ECG', {'ecg'}), ('EMG', {'emg'}), ('EOG', {'eog'}),
            ('MEG', {'mag','grad','ref_meg'}),
            ('Other biological / auxiliary signals', {'bio','resp','stim','misc','temperature','gsr'})
        ]
        matches = [label for label, member in groups if keys & member]
        unclassified = keys - set().union(*(members for _,members in groups))
        if unclassified: matches.append('Other (' + ', '.join(sorted(unclassified)) + ')')
        if not matches: return 'Unknown signal type'
        if len(matches) == 1: return matches[0]
        return 'Mixed recording  •  ' + ' + '.join(matches)

    def _modality_summary(self):
        from collections import Counter
        types = Counter(self.raw.get_channel_types())
        eeg_count = types.get('eeg', 0)
        # Channel types are the evidence; extension alone cannot establish modality.
        if eeg_count == 0:
            modality = 'Non-EEG recording — EEG conversion disabled'
        elif eeg_count == len(self.raw.ch_names):
            modality = 'EEG only'
        else:
            modality = 'Mixed EEG and non-EEG channels — conversion requires an EEG-only selection'
        return types, modality, eeg_count

    def inspect_file(self):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.raw = self._read()
            self.info_text.setText(f'File: {self.path.name}   |   Channels: {len(self.raw.ch_names)}   |   Sampling: {self.raw.info["sfreq"]:g} Hz   |   Samples: {self.raw.n_times:,}   |   Duration: {self.raw.n_times/self.raw.info["sfreq"]:.2f} s   |   Annotations: {len(self.raw.annotations)}')
            types, modality, eeg_count = self._modality_summary()
            self.types_text.setText('Channel types: ' + ', '.join(f'{k}: {v}' for k,v in sorted(types.items())))
            display = self._identify_modality(types)
            self.modality_text.setText(display)
            self.compatibility_text.setText('CONVERSION READY  •  EEG-only recording' if eeg_count == len(self.raw.ch_names) else ('NOT SUPPORTED  •  No EEG channels in this dataset' if eeg_count == 0 else 'REVIEW REQUIRED  •  EEG mixed with other signal types'))
            self._populate_cards(types, modality)
            self.convert.setEnabled(eeg_count > 0 and eeg_count == len(self.raw.ch_names))
            if eeg_count == 0:
                self.log.appendPlainText('BLOCKED: This file contains no EEG channels. No conversion was performed.')
            elif eeg_count < len(self.raw.ch_names):
                self.log.appendPlainText('BLOCKED: Mixed channel types detected. EEG-only conversion is not supported for this dataset in v0.2.')
            else:
                self.log.appendPlainText('PASS: File inspected. Choose output format and convert.')
            self.log.appendPlainText('NOTE: Format extension does not identify signal modality.')
            self.log.appendPlainText('Note: export compatibility varies by format; FIF, CSV, and EDF outputs are available.')
            # Original v0.1 message kept below for backward compatibility, but is unreachable.

            self.activity_summary.setText('Recording inspected. Select an output format, then choose Convert & validate.')
            self.statusBar().showMessage('Inspection completed. Ready to convert.')
        except Exception as exc:
            self.raw = None; self.convert.setEnabled(False)
            self.types_text.setText('Channel types: —')
            self.modality_text.setText('Unknown modality')
            self.compatibility_text.setText('Reader could not inspect this recording.')
            self._reset_cards()
            QMessageBox.critical(self, 'Cannot read recording', str(exc))
            self.log.appendPlainText('ERROR: ' + str(exc))
            self.activity_summary.setText('An error occurred: ' + str(exc))
        finally: QApplication.restoreOverrideCursor()

    def convert_file(self):
        if self.raw is None: return
        types, modality, eeg_count = self._modality_summary()
        if eeg_count != len(self.raw.ch_names):
            QMessageBox.warning(self, 'Unsupported channel types',
                'This MVP converts EEG-only recordings.\n' + modality +
                '\nChannel types: ' + ', '.join(f'{k}: {v}' for k,v in sorted(types.items())))
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.convert.setEnabled(False)
            self.view_validation.setEnabled(False)
            outdir = Path(self.output_dir.text().strip())
            if not outdir.is_dir(): raise ValueError('Output folder does not exist.')
            fmt = self.format.currentText()
            if fmt.startswith('CSV'):
                from conversion_bundle import export_csv_bundle
                self.log.appendPlainText(f'Creating four-file CSV research package for {self.path.name}...')
                self.progress.setValue(15)
                QApplication.processEvents()
                folder, report = export_csv_bundle(self.raw, self.path, outdir)
                self.progress.setValue(100)
                status = 'PASS' if report['overall_validation_passed'] else 'REVIEW'
                signal_info = report['signal_validation']
                self.log.appendPlainText(f'{status}: Automatic signal, annotation, and core metadata validation.')
                self.log.appendPlainText('Numerical max error (uV): ' + str(signal_info['max_absolute_error_uv']))
                self.log.appendPlainText('Numerical RMSE (uV): ' + str(signal_info['rmse_uv']))
                self.log.appendPlainText('Compared values: ' + str(signal_info['values_compared']))
                for file_name in report['files']:
                    self.log.appendPlainText('Saved: ' + str(folder / file_name))
                self.log.appendPlainText('NOTE: Full format metadata equivalence is not verified.')
                self.activity_summary.setText(f'Export complete: {status}. View the detailed checks below.')
                self._show_validation_report(report, folder)
                QMessageBox.information(self, 'Conversion package complete',
                    f'Output folder: {folder}\nFiles: 4\nImplemented validation checks: {status}\nSee validation results for details.')
                return
            if fmt.startswith('EDF'):
                from edf_export import export_edf_checked
                self.log.appendPlainText(f'Exporting and validating EDF: {self.path.name}...')
                self.progress.setValue(15)
                QApplication.processEvents()
                edf_path, report = export_edf_checked(self.raw, self.path, outdir)
                self.progress.setValue(100)
                status = 'PASS' if report['overall_validation_passed'] else 'REVIEW'
                self.log.appendPlainText(f'{status}: EDF read-back validation (16-bit quantized, not lossless).')
                self.log.appendPlainText('Max error (uV): ' + str(report['signal_validation']['max_absolute_error_uv']))
                self.log.appendPlainText('RMSE (uV): ' + str(report['signal_validation']['rmse_uv']))
                self.log.appendPlainText('Saved: ' + str(edf_path))
                self.log.appendPlainText('Report: ' + str(edf_path.with_name(report['report_file'])))
                self.log.appendPlainText('NOTE: EDF does not preserve all FIF metadata; read validation limitations.')
                self.activity_summary.setText(f'EDF export complete: {status}. See the validation results.')
                self._show_validation_report(report, edf_path.parent)
                QMessageBox.information(self, 'EDF export completed',
                    f'Output: {edf_path}\nImplemented checks: {status}\nEDF is 16-bit quantized (not lossless).')
                return
            if not fmt.startswith('FIF'):
                from multiformat import export_checked
                label = fmt.split(' (')[0]
                self.log.appendPlainText(f'Exporting and validating {label}: {self.path.name}...')
                self.progress.setValue(15)
                QApplication.processEvents()
                exported, report = export_checked(self.raw, self.path, outdir, label)
                self.progress.setValue(100)
                status = 'PASS' if report['overall_validation_passed'] else 'REVIEW'
                self.log.appendPlainText(f'{status}: {label} read-back signal and annotation validation.')
                for fn in report['files']:
                    self.log.appendPlainText('Saved: ' + str(exported.parent / fn))
                self.log.appendPlainText('NOTE: Full metadata/geometry and stim preservation not verified.')
                self.activity_summary.setText(f'{label} export complete: {status}. See the validation results.')
                self._show_validation_report(report, exported.parent)
                QMessageBox.information(self, 'Export completed', f'Format: {label}\nImplemented checks: {status}\nOutput: {exported}')
                return
            # Do not overwrite input or existing output.
            stem = self.path.stem.replace('-raw', '')
            out = outdir / (stem + ('_converted_raw.fif' if fmt.startswith('FIF') else '_converted.csv'))
            if out.exists(): raise FileExistsError(f'Output already exists: {out}')
            self.progress.setValue(20)
            self.log.appendPlainText(f'Converting {self.path.name} → {fmt}...')
            self.raw.load_data()
            self.progress.setValue(45)
            if fmt.startswith('FIF'):
                self.raw.save(out, overwrite=False, verbose='ERROR')
                import mne
                reloaded = mne.io.read_raw_fif(out, preload=False, verbose='ERROR')
                out_channels = reloaded.ch_names
                out_fs = float(reloaded.info['sfreq'])
                out_samples = int(reloaded.n_times)
            else:
                fs = float(self.raw.info['sfreq'])
                labels = list(self.raw.ch_names)
                # MNE data are expressed in V for EEG. Export EEG to microvolts, not raw V.
                # For non-EEG channel types, conversion to CSV is disabled to prevent mislabeled units.
                types = self.raw.get_channel_types()
                if any(t != 'eeg' for t in types):
                    raise ValueError('CSV export in v0.1 supports EEG-only recordings. Other channel types must be handled explicitly.')
                samples = self.raw.get_data().T * 1e6
                df = pd.DataFrame(samples, columns=labels)
                df.to_csv(out, index=False)
                out_channels = list(pd.read_csv(out, nrows=0).columns)
                out_fs = fs  # verified via metadata sidecar below
                out_samples = sum(1 for _ in open(out, encoding='utf-8')) - 1
                sidecar = out.with_suffix('.json')
                sidecar.write_text(json.dumps({'sampling_rate_hz':fs,'units':'µV','channel_names':labels,'source_file':self.path.name,'note':'CSV does not retain MNE annotations or channel geometry. This is a lossy representation.'},indent=2,ensure_ascii=False),encoding='utf-8')
            self.progress.setValue(85)
            check = (out_channels == self.raw.ch_names and
                     np.isclose(out_fs, self.raw.info['sfreq']) and
                     out_samples == self.raw.n_times)
            report = {'source':self.path.name,'output':out.name,'timestamp':datetime.now().isoformat(timespec='seconds'),
                      'output_format':fmt,'channels_match':out_channels==self.raw.ch_names,
                      'sampling_rate_match':bool(np.isclose(out_fs,self.raw.info['sfreq'])),
                      'sample_count_match':bool(out_samples==self.raw.n_times),
                      'structural_validation_passed':bool(check),
                      'limitations':'Structural checks only; waveform numerical equivalence and event metadata fidelity are not guaranteed. CSV omits annotations and montage.'}
            validation = out.with_name(out.stem + '_validation.json')
            validation.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
            self.progress.setValue(100)
            self.log.appendPlainText(('PASS' if check else 'REVIEW') + ': Basic structural validation (channels, sampling, sample count).')
            self.log.appendPlainText('Saved: '+str(out)+'\nValidation report: '+str(validation))
            if fmt.startswith('CSV'):
                self.log.appendPlainText('WARNING: CSV loses event annotations, sensor locations and some metadata. JSON sidecar records fs/units.')
            else:
                self.log.appendPlainText('NOTICE: Metadata equivalence and numerical signal fidelity not yet fully validated.')
            QMessageBox.information(self, 'Conversion complete', f'Output: {out}\nBasic structural validation: {"PASS" if check else "REVIEW"}')
        except Exception as exc:
            self.log.appendPlainText('ERROR: ' + str(exc))
            self.activity_summary.setText('An error occurred: ' + str(exc))
            QMessageBox.critical(self, 'Conversion failed', str(exc))
        finally:
            self.convert.setEnabled(self.raw is not None and all(t == 'eeg' for t in self.raw.get_channel_types()))
            QApplication.restoreOverrideCursor()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    configure_app_identity(app)
    window = Window(); window.show()
    sys.exit(app.exec())
