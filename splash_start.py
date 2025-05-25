import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QProgressBar, QMessageBox
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QBrush, QLinearGradient
from app.resources.fonts.font_manager import font_manager
from app.models.common.screen_manager import *

from app.views.main_window import MainWindow
import traceback


class SamsungSplashScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Samsung Production Planning System")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

        screen = self.screen()
        screen_size = screen.availableGeometry()

        self.resize(int(screen_size.width()*0.5), int(screen_size.height()*0.4))
        self.center()

        # 배경 설정
        self.backgroundColor = QColor(255, 255, 255) # 흰색
        self.accentColor = QColor(20, 40, 160) # 파란색

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        bold_font = font_manager.get_just_font("SamsungSharpSans-Bold").family()
        normal_font = font_manager.get_just_font("SamsungOne-700").family()

        # 로고 텍스트
        logo_label = QLabel("SAMSUNG")
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet(
            f"font-family: {bold_font}; font-size: {f(40)}px; font-weight:bold; color: rgb({self.accentColor.red()}, {self.accentColor.green()}, {self.accentColor.blue()});")

        # 부제목
        subtitle_label = QLabel("Production Planning Optimization System")
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setStyleSheet(f"font-family:{normal_font}; font-size: {f(21)}px;  color: #555555;")

        # 로딩 상태 메시지
        self.status_label = QLabel("Initializing...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(f"font-family:{normal_font}; font-size: {f(16)}px; color: #888888;")

        # 프로그레스 바
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background-color: #F0F0F0;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: rgb({self.accentColor.red()}, {self.accentColor.green()}, {self.accentColor.blue()});
                border-radius: 3px;
            }}
        """)

        # 버전 정보
        version_label = QLabel("Version 1.0.0")
        version_label.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        version_label.setStyleSheet(f"font-family:{normal_font}; font-size: {f(11)}px; color: #AAAAAA;")

        layout.addStretch(1)
        layout.addWidget(logo_label)
        layout.addWidget(subtitle_label)
        layout.addStretch(1)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.addStretch(1)
        layout.addWidget(version_label)

        # 타이머 설정
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_progress)
        self.timer.start(30)  # 30ms마다 업데이트

        self.progress_value = 0
        self.loading_stages = [
            "Initializing application...",
            "Loading resources...",
            "Preparing UI components...",
            "Starting main application..."
        ]
        self.current_stage = 0
        self.main_window = None

    """
    창을 화면 중앙에 배치
    """
    def center(self):
        screen = QApplication.primaryScreen().geometry()
        size = self.geometry()
        self.move(int((screen.width() - size.width()) / 2),
                  int((screen.height() - size.height()) / 2))

    """
    프로그레스 바 업데이트 및 메인 앱 시작
    """
    def update_progress(self):
        self.progress_value += 1
        self.progress_bar.setValue(self.progress_value)

        # 진행 단계 업데이트
        stage_progress = 100 / len(self.loading_stages)

        if self.progress_value % int(stage_progress) == 0 and self.current_stage < len(self.loading_stages):
            self.status_label.setText(self.loading_stages[self.current_stage])
            self.current_stage += 1

        # 로딩 완료 시 메인 앱 실행 및 스플래시 숨기기
        if self.progress_value >= 100:
            self.timer.stop()
            self.hide()

            try:
                self.main_window = MainWindow()
                self.main_window.show()

                self.close()

            except Exception as e:
                traceback.print_exc()

                # 사용자에게 오류 메시지 표시
                error_box = QMessageBox()
                error_box.setIcon(QMessageBox.Critical)
                error_box.setText("Failed to start the application")
                error_box.setInformativeText(f"Error occurred: {str(e)}")
                error_box.setDetailedText(traceback.format_exc())
                error_box.setWindowTitle("Start Error")
                error_box.exec_()

                # 오류 발생 시 애플리케이션 종료
                self.close()
                QApplication.instance().quit()

    """
    배경 그라데이션 및 테두리 그리기
    """
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 배경
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(255, 255, 255))  # 흰색
        gradient.setColorAt(1, QColor(245, 245, 250))  # 연한 파란색

        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 15, 15)

        # 테두리
        painter.setPen(QPen(QColor(230, 230, 240), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(0, 0, self.width() - 1, self.height() - 1, 15, 15)
