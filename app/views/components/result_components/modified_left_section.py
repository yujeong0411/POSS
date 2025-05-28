from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QFileDialog,
                             QLabel, QSizePolicy)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QTimer
from PyQt5.QtGui import QCursor
import pandas as pd
from .item_grid_widget import ItemGridWidget
from .item_position_manager import ItemPositionManager
from app.views.components.common.enhanced_message_box import EnhancedMessageBox
from app.models.common.file_store import FilePaths
from .legend_widget import LegendWidget
from .filter_widget import FilterWidget
from .search_widget import SearchWidget
from app.utils.fileHandler import load_file
from app.utils.item_key_manager import ItemKeyManager
from app.resources.fonts.font_manager import font_manager
from app.models.common.screen_manager import *
from app.utils.search_index_manager import SearchIndexManager, SearchResultSorter
from app.utils.filter_pipeline import FilterPipeline, ItemFilterFactory

class ModifiedLeftSection(QWidget):
    # 데이터 변경을 통합해서 한 번만 내보내는 시그널
    viewDataChanged = pyqtSignal(pd.DataFrame)  # 수정 후 변경된 DataFrame을 전달
    item_selected = pyqtSignal(object, object)
    itemModified = pyqtSignal(object, dict, dict)
    cellMoved = pyqtSignal(object, dict, dict)
    validation_error_occured = pyqtSignal(dict, str)
    validation_error_resolved = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_page = None
        self.data = None
        self.original_data = None
        self.grouped_data = None
        self.days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        self.time_periods = ['Day', 'Night']
        self.pre_assigned_items = set()  # 사전할당된 아이템 저장
        self.shipment_failure_items = {}  # 출하 실패 아이템 저장

        # ===== 핵심 상태 변수 추가 =====
        self._signals_connected = False
        self._mvc_mode = False

        # ===== 검색 최적화 관련 추가 =====
        self.search_index_manager = SearchIndexManager()
        self.search_result_sorter = SearchResultSorter()

        self.filter_pipeline = FilterPipeline()
        self.item_filter_factory = ItemFilterFactory()

        self.init_ui()

        # MVC 컴포넌트 초기화
        self.controller = None
        self.validator = None

        # 아이템 이동을 위한 정보 저장
        self.row_headers = []

        # 검색 관련 변수
        self.all_items = []
        self.search_results = []
        self.current_result_index = -1

        if not hasattr(self, 'current_selected_item'):
            self.current_selected_item = None
        if not hasattr(self, 'current_selected_container'):
            self.current_selected_container = None

        # 필터 상태 저장
        self.current_filter_states = {
            'shortage': False,
            'shipment': False,
            'pre_assigned': False
        }

        # 엑셀 스타일 필터 상태 저장 (새로 추가된 부분)
        self.current_excel_filter_states = {
            'line': {},
            'project': {}
        }

        # 시그널 연결은 명시적으로 호출할 때만
        print("ModifiedLeftSection 초기화 완료 - 시그널 연결 보류, 검색 인덱스 매니저 준비됨")

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 범례 위젯 추가
        self.legend_widget = LegendWidget()
        self.legend_widget.filter_changed.connect(self.on_filter_changed_dict)
        self.legend_widget.filter_activation_requested.connect(self.on_filter_activation_requested)
        main_layout.addWidget(self.legend_widget)

        # 통합 컨트롤 레이아웃 (버튼, 필터, 검색 섹션을 한 줄에 배치)
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(5, 5, 5, 5)
        control_layout.setSpacing(w(5))

        # 왼쪽 버튼 섹션 (Import/Reset)
        button_section = QHBoxLayout()
        button_section.setSpacing(10)

        bold_font = font_manager.get_just_font("SamsungSharpSans-Bold").family()
        normal_font = font_manager.get_just_font("SamsungOne-700").family()

        # 엑셀 파일 불러오기 버튼 - 길이 증가
        self.load_button = QPushButton("Import Excel")
        self.load_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #1428A0;
                color: white;
                font-weight: bold;
                padding: 8px 15px;
                border-radius: 4px;
                min-width: {w(80)}px;
                border:none;
                font-family:{normal_font};
                font-size: {f(16)}px;
                min-height: {h(28)}px;
            }}
            QPushButton:hover {{
                background-color: #004C99;
            }}
            QPushButton:pressed {{
                background-color: #003366;
            }}
        """)
        self.load_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.load_button.clicked.connect(self.load_excel_file)
        button_section.addWidget(self.load_button)

        # 원본 복원 버튼 
        self.reset_button = QPushButton("Reset")
        self.reset_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #808080;
                color: white;
                font-weight: bold;
                padding: 8px 15px;
                border-radius: 4px;
                min-width: {w(80)}px;
                border:none;
                font-family:{normal_font};
                font-size: {f(16)}px;
                min-height: {h(28)}px;
            }}
            QPushButton:hover {{
                background-color: #606060;
            }}
            QPushButton:pressed {{
                background-color: #404040;
            }}
        """)
        self.reset_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.reset_button.clicked.connect(self.reset_to_original)
        self.reset_button.setEnabled(False)
        button_section.addWidget(self.reset_button)

        # 버튼 섹션을 통합 레이아웃에 추가 (왼쪽에 붙이기)
        control_layout.addLayout(button_section)
        
        # 가운데 여백 추가
        control_layout.addStretch(1)  # 가운데 여백 추가

        # 필터 위젯 추가 - Line과 Project 버튼 간격 조정 및 스타일 변경
        self.filter_widget = FilterWidget()
        self.filter_widget.filter_changed.connect(self.on_excel_filter_changed)
        # self.filter_widget.setFixedWidth(400)
        control_layout.addWidget(self.filter_widget)
        control_layout.addStretch(1)

        # 검색 위젯 추가 (기존 검색 관련 UI 요소 대체)
        self.search_widget = SearchWidget(self)
        self.search_widget.searchRequested.connect(self.search_items)
        self.search_widget.searchCleared.connect(self.clear_search)
        self.search_widget.nextResultRequested.connect(self.go_to_next_result)
        self.search_widget.prevResultRequested.connect(self.go_to_prev_result)
        control_layout.addWidget(self.search_widget)

        # 통합 컨트롤 레이아웃을 메인 레이아웃에 추가
        main_layout.addLayout(control_layout)

        # 새로운 그리드 위젯 추가
        self.grid_widget = ItemGridWidget()
        self.grid_widget.scroll_area.setStyleSheet("""
            QScrollBar:vertical {
                border: none;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #CCCCCC;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                border: none;
                height: 10px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #CCCCCC;
                min-width: 20px;
                border-radius: 5px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                border: none;
                background: none;
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)
        self.grid_widget.itemSelected.connect(self.on_grid_item_selected)  # 아이템 선택 이벤트 연결
        self.grid_widget.itemDataChanged.connect(self.on_item_data_changed)  # 아이템 데이터 변경 이벤트 연결
        self.grid_widget.itemCreated.connect(self.register_item)
        self.grid_widget.itemRemoved.connect(self.on_item_removed)
        self.grid_widget.itemCopied.connect(self.on_item_copied)  # 아이템 복사 이벤트 연결
        main_layout.addWidget(self.grid_widget, 1)

    def connect_signals(self):
        """시그널 연결 - 중복 방지 로직 포함"""
        if self._signals_connected:
            print("ModifiedLeftSection: 시그널이 이미 연결되어 있음 - 중복 연결 방지")
            return

        if self._mvc_mode and hasattr(self, 'controller') and self.controller:
            print("ModifiedLeftSection: MVC 모드 시그널 연결")
            # MVC 모드: 컨트롤러를 통한 처리만 활성화
            if hasattr(self.controller.model, 'modelDataChanged'):
                self.controller.model.modelDataChanged.connect(self.update_from_model)
                print("ModifiedLeftSection: 모델 modelDataChanged 시그널 -> UI 업데이트 연결")
        else:
            print("ModifiedLeftSection: 레거시 모드 시그널 연결")
            # 레거시 모드: 직접 처리 방식 사용
            if hasattr(self, 'grid_widget') and hasattr(self.grid_widget, 'itemDataChanged'):
                self.grid_widget.itemDataChanged.connect(self.on_item_data_changed)
                print("ModifiedLeftSection: 그리드 위젯 itemDataChanged 시그널 연결")

            if hasattr(self, 'grid_widget') and hasattr(self.grid_widget, 'itemSelected'):
                self.grid_widget.itemSelected.connect(self.on_grid_item_selected)
                print("ModifiedLeftSection: 그리드 위젯 itemSelected 시그널 연결")

            if hasattr(self, 'grid_widget') and hasattr(self.grid_widget, 'itemRemoved'):
                self.grid_widget.itemRemoved.connect(self.on_item_removed)
                print("ModifiedLeftSection: 그리드 위젯 itemRemoved 시그널 연결")

            if hasattr(self, 'grid_widget') and hasattr(self.grid_widget, 'itemCopied'):
                self.grid_widget.itemCopied.connect(self.on_item_copied)
                print("ModifiedLeftSection: 그리드 위젯 itemCopied 시그널 연결")

        self._signals_connected = True
        print("ModifiedLeftSection: 시그널 연결 완료")

    def on_filter_changed_dict(self, filter_states):
        """
        범례 위젯에서 필터가 변경될 때 호출
        ✅ 수정: 중복 호출 방지 및 효율적인 상태선 업데이트
        """
        # 현재 필터 상태 업데이트
        if self.current_filter_states == filter_states:
            return

        # 이전 상태 백업 (필터 활성화 감지용)
        previous_states = self.current_filter_states.copy()

        # 상태선 업데이트만 수행하는 경량 버전 적용
        self.current_filter_states = filter_states.copy()
        self.update_status_lines_only(filter_states)

        # 필터 활성화 시 관련 분석 트리거
        for status_type, is_checked in filter_states.items():
            was_checked = previous_states.get(status_type, False)
            # 새로 활성화된 필터에 대한 분석 요청
            if is_checked and not was_checked:
                self.on_filter_activation_requested(status_type)
    
    """
    데이터프레임 타입 정규화
    """
    def _normalize_data_types(self, df):
        if df is not None and not df.empty:
            # Line은 항상 문자열
            if 'Line' in df.columns:
                df['Line'] = df['Line'].astype(str)
            
            # Time은 항상 정수
            if 'Time' in df.columns:
                df['Time'] = pd.to_numeric(df['Time'], errors='coerce').fillna(0).astype(int)
            
            # Item은 항상 문자열
            if 'Item' in df.columns:
                df['Item'] = df['Item'].astype(str)
            
            # Qty는 항상 정수
            if 'Qty' in df.columns:
                df['Qty'] = pd.to_numeric(df['Qty'], errors='coerce').fillna(0).astype(int)
        
        return df
    

    """
    새로 생성된 아이템 등록
    """

    def register_item(self, item):
        """새로 생성된 아이템 등록 - 검색 인덱스 무효화 추가"""
        if item not in self.all_items:
            self.all_items.append(item)

            # ===== 검색 인덱스 무효화 =====
            self.search_index_manager.mark_dirty()
            # print(f"[최적화] 새 아이템 등록으로 검색 인덱스 무효화: {len(self.all_items)}개 아이템")

            # 검색이 활성화되어 있으면 해당 아이템에 검색 적용
            if self.search_widget.is_search_active():
                search_text = self.search_widget.get_search_text()
                if search_text:
                    self.apply_search_to_item(item, search_text)

    """
    엑셀 스타일 필터 상태 변경 처리
    """
    def on_excel_filter_changed(self, filter_states):
        self.current_excel_filter_states = filter_states
        self.apply_all_filters()

    """
    모든 필터 (범례 & 엑셀 스타일) 적용
    """

    def apply_all_filters(self):
        """모든 필터 적용 - 파이프라인 패턴으로 단순화"""
        if hasattr(self, '_filter_applying') and self._filter_applying:
            print("ModifiedLeftSection: 필터 적용이 이미 진행 중 - 중복 실행 방지")
            return

        self._filter_applying = True

        try:
            if not hasattr(self, 'grid_widget') or not hasattr(self.grid_widget, 'containers'):
                return

            print("[파이프라인] 필터링 시작")

            # ===== 1. 파이프라인 초기화 =====
            self.filter_pipeline.clear()

            # ===== 2. 활성 필터 상태 확인 =====
            # 라인 필터
            active_lines = []
            if hasattr(self, 'current_excel_filter_states') and 'line' in self.current_excel_filter_states:
                for line, is_active in self.current_excel_filter_states['line'].items():
                    if is_active:
                        active_lines.append(line)

            # 프로젝트 필터
            active_projects = []
            if hasattr(self, 'current_excel_filter_states') and 'project' in self.current_excel_filter_states:
                for project, is_active in self.current_excel_filter_states['project'].items():
                    if is_active:
                        active_projects.append(project)

            # 검색 필터
            search_text = ""
            if hasattr(self, 'search_widget') and self.search_widget.is_search_active():
                search_text = self.search_widget.get_search_text()

            # ===== 3. 특별 케이스: 모든 필터가 비활성화 =====
            if not active_lines and not active_projects and not search_text:
                print("[파이프라인] 모든 필터 비활성화 - 전체 데이터 표시")
                if hasattr(self, 'data') and self.data is not None and not self.data.empty:
                    all_lines = self.data['Line'].unique().tolist()
                    self.rebuild_grid_with_filtered_data(all_lines, None)
                else:
                    self.show_empty_grid()
                return

            # ===== 4. 파이프라인 구성 =====
            print(
                f"[파이프라인] 필터 구성 - 라인:{len(active_lines)}, 프로젝트:{len(active_projects)}, 검색:{'Y' if search_text else 'N'}")

            # 라인 필터 추가
            if active_lines:
                line_filter = self.item_filter_factory.create_line_filter(active_lines)
                self.filter_pipeline.add_filter(line_filter, "라인필터")

            # 프로젝트 필터 추가
            if active_projects:
                project_filter = self.item_filter_factory.create_project_filter(active_projects)
                self.filter_pipeline.add_filter(project_filter, "프로젝트필터")

            # 상태선 필터 추가 (항상 적용)
            status_filter = self.item_filter_factory.create_status_line_filter(self.current_filter_states)
            self.filter_pipeline.add_filter(status_filter, "상태선필터")

            # 검색 필터 추가
            if search_text:
                search_filter = self.item_filter_factory.create_search_filter(search_text)
                self.filter_pipeline.add_filter(search_filter, "검색필터")

            # ===== 5. 파이프라인 실행 =====
            # 필터링 대상: 라인/프로젝트 필터가 있으면 그리드 재구성, 없으면 현재 아이템들 필터링
            if active_lines or active_projects:
                # 그리드 재구성 방식
                print("[파이프라인] 그리드 재구성 모드")
                self.rebuild_grid_with_filtered_data(active_lines, active_projects)

                # 재구성 후 상태선과 검색 적용
                if hasattr(self, 'all_items') and self.all_items:
                    context = {
                        'filter_states': self.current_filter_states,
                        'search_text': search_text
                    }

                    # 상태선과 검색만 적용
                    status_pipeline = FilterPipeline()
                    status_pipeline.add_filter(status_filter, "상태선필터")
                    if search_text:
                        status_pipeline.add_filter(search_filter, "검색필터")

                    filtered_items = status_pipeline.apply(self.all_items, context)

                    # 검색 결과 업데이트
                    if search_text:
                        self.search_results = self.search_result_sorter.sort_by_position(
                            filtered_items, self.grid_widget
                        )
                        if self.search_results:
                            self.current_result_index = 0
                            self.select_current_result()
                            self.update_result_navigation()
                            self.search_widget.show_result_navigation(True)
                        else:
                            self.search_widget.set_result_status(0, 0)
            else:
                # 현재 아이템 필터링 방식 (검색 전용)
                print("[파이프라인] 아이템 필터링 모드")
                if hasattr(self, 'all_items') and self.all_items:
                    context = {
                        'filter_states': self.current_filter_states,
                        'search_text': search_text
                    }

                    filtered_items = self.filter_pipeline.apply(self.all_items, context)

                    # 검색 결과 처리
                    if search_text:
                        self.search_results = self.search_result_sorter.sort_by_position(
                            filtered_items, self.grid_widget
                        )
                        if self.search_results:
                            self.current_result_index = 0
                            self.select_current_result()
                            self.update_result_navigation()
                            self.search_widget.show_result_navigation(True)
                        else:
                            self.search_widget.set_result_status(0, 0)

            print("[파이프라인] 필터링 완료")

        except Exception as e:
            print(f"[파이프라인] 필터링 중 오류: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 중복 실행 방지 플래그 해제
            QTimer.singleShot(50, lambda: setattr(self, '_filter_applying', False))

    def rebuild_grid_with_filtered_data(self, active_lines, active_projects=None):
        """
        활성화된 라인과 프로젝트로 그리드 재구성
        ✅ 리팩토링: 거대한 메서드를 명확한 단계로 분할
        """
        if self.data is None:
            return

        try:
            print(f"[그리드재구성] 시작 - 라인: {active_lines}, 프로젝트: {active_projects}")

            # ===== 1. 데이터 필터링 =====
            filtered_data = self._filter_data_by_criteria(active_lines, active_projects)
            if filtered_data.empty:
                self.show_empty_grid()
                return

            # ===== 2. 라인 정렬 및 구조 준비 =====
            sorted_lines = self._prepare_filtered_lines(filtered_data)
            line_shifts, row_headers = self._create_filtered_grid_structure(sorted_lines)

            # ===== 3. 그리드 재구성 =====
            self._setup_filtered_grid(row_headers, line_shifts)

            # ===== 4. 아이템 생성 및 배치 =====
            item_count = self._populate_filtered_grid(filtered_data, sorted_lines, row_headers)

            # ===== 5. 상태 적용 =====
            self.apply_legend_filters_only()

            print(f"[그리드재구성] 완료 - {len(sorted_lines)}개 라인, {item_count}개 아이템")

        except Exception as e:
            print(f"[그리드재구성] 오류: {e}")
            import traceback
            traceback.print_exc()

    def _filter_data_by_criteria(self, active_lines, active_projects):
        """기준에 따른 데이터 필터링"""
        filtered_data = self.data.copy()

        # 라인 필터 적용
        if active_lines:
            filtered_data = filtered_data[filtered_data['Line'].isin(active_lines)]

        # 프로젝트 필터 적용
        if active_projects and 'Project' in filtered_data.columns:
            project_mask = filtered_data['Project'].isin(active_projects)
            # NaN을 "N/A"로 처리한 경우도 고려
            if "N/A" in active_projects:
                nan_mask = filtered_data['Project'].isna()
                project_mask = project_mask | nan_mask
            filtered_data = filtered_data[project_mask]

        print(f"[필터링] 원본 {len(self.data)}행 → 필터링 후 {len(filtered_data)}행")
        return filtered_data

    def _prepare_filtered_lines(self, filtered_data):
        """필터링된 데이터에서 라인 정렬"""
        # 실제 존재하는 라인만 추출
        actual_lines = filtered_data['Line'].unique().tolist()

        # 제조동별 생산량으로 정렬
        filtered_data['Building'] = filtered_data['Line'].str[0]
        building_production = filtered_data.groupby('Building')['Qty'].sum()
        sorted_buildings = building_production.sort_values(ascending=False).index.tolist()

        # 제조동 순서대로 라인 정렬
        sorted_lines = []
        for building in sorted_buildings:
            building_lines = [line for line in actual_lines if line.startswith(building)]
            sorted_building_lines = sorted(building_lines)
            sorted_lines.extend(sorted_building_lines)

        # 누락된 라인 추가
        remaining_lines = [line for line in actual_lines if line not in sorted_lines]
        if remaining_lines:
            sorted_lines.extend(sorted(remaining_lines))

        return sorted_lines

    def _create_filtered_grid_structure(self, sorted_lines):
        """필터링된 그리드 구조 생성"""
        # 라인별 교대 정보
        line_shifts = {}
        for line in sorted_lines:
            line_shifts[line] = ["Day", "Night"]

        # 행 헤더 생성
        row_headers = []
        for line in sorted_lines:
            for shift in ["Day", "Night"]:
                row_headers.append(f"{line}_({shift})")

        return line_shifts, row_headers

    def _setup_filtered_grid(self, row_headers, line_shifts):
        """필터링된 그리드 설정"""
        self.grid_widget.setupGrid(
            rows=len(row_headers),
            columns=len(self.days),
            row_headers=row_headers,
            column_headers=self.days,
            line_shifts=line_shifts
        )

    def _populate_filtered_grid(self, filtered_data, sorted_lines, row_headers):
        """필터링된 그리드에 아이템 배치"""
        # 기존 아이템 정리
        self.all_items.clear()

        # 교대 정보 준비
        times = sorted(filtered_data['Time'].unique())
        shifts = {}
        for time in times:
            if int(time) % 2 == 1:
                shifts[time] = "Day"
            else:
                shifts[time] = "Night"

        # 데이터를 행/열별로 그룹화
        grouped_items = {}
        for _, row_data in filtered_data.iterrows():
            line = row_data['Line']
            time = row_data['Time']
            shift = shifts[time]
            day_idx = (int(time) - 1) // 2

            if day_idx >= len(self.days):
                continue

            row_key = f"{line}_({shift})"

            try:
                row_idx = row_headers.index(row_key)
                col_idx = day_idx

                grid_key = (row_idx, col_idx)
                if grid_key not in grouped_items:
                    grouped_items[grid_key] = []

                item_data = row_data.to_dict()
                qty = item_data.get('Qty', 0)
                if pd.isna(qty):
                    qty = 0
                item_data['Qty'] = int(float(qty)) if isinstance(qty, (int, float, str)) else 0
                grouped_items[grid_key].append(item_data)

            except ValueError as e:
                print(f"[그리드배치] 인덱스 오류: {e}")
                continue

        # 아이템을 그리드에 추가
        item_count = 0
        for (row_idx, col_idx), items in grouped_items.items():
            for item_data in items:
                item_info = str(item_data.get('Item', ''))
                qty = item_data.get('Qty', 0)
                if pd.notna(qty) and qty != 0:
                    item_info += f"    {qty}"

                new_item = self.grid_widget.addItemAt(row_idx, col_idx, item_info, item_data)

                if new_item:
                    item_count += 1
                    # 상태 적용
                    self._apply_item_states(new_item, item_data)

        return item_count

    def _apply_item_states(self, new_item, item_data):
        """개별 아이템에 상태 적용"""
        item_code = item_data.get('Item', '')

        # 사전할당 상태
        if item_code in self.pre_assigned_items:
            new_item.set_pre_assigned_status(True)

        # 출하 실패 상태
        if item_code in self.shipment_failure_items:
            failure_info = self.shipment_failure_items[item_code]
            new_item.set_shipment_failure(True, failure_info.get('reason', 'Unknown reason'))

        # 자재부족 상태
        if hasattr(self, 'current_shortage_items') and item_code in self.current_shortage_items:
            shortage_info = self.current_shortage_items[item_code]
            new_item.set_shortage_status(True, shortage_info)

    def show_empty_grid(self):
        """
        빈 그리드 표시 - Clear All 했을 때 사용
        """
        try:
            # 모든 아이템 제거
            self.grid_widget.clearAllItems()
            self.all_items.clear()

            # 빈 그리드 설정 (최소한의 구조만 유지)
            self.grid_widget.setupGrid(
                rows=0,  # 행 없음
                columns=len(self.days),
                row_headers=[],  # 빈 행 헤더
                column_headers=self.days,
                line_shifts={}  # 빈 라인 시프트
            )

            print("DEBUG: 빈 그리드 표시 완료")

        except Exception as e:
            print(f"빈 그리드 표시 중 오류: {e}")
            import traceback
            traceback.print_exc()


    def should_show_item_excel_filter(self, item):
        """엑셀 필터를 고려한 아이템 표시 여부 - 파이프라인 패턴 적용"""
        if not hasattr(self, 'current_excel_filter_states') or not hasattr(item, 'item_data'):
            return True

        try:
            # ===== 1. 빠른 검사: 엑셀 필터가 활성화되어 있는지 확인 =====
            line_filters = self.current_excel_filter_states.get('line', {})
            project_filters = self.current_excel_filter_states.get('project', {})

            # 모든 필터가 비활성화되면 모든 아이템 표시
            if not any(line_filters.values()) and not any(project_filters.values()):
                return True

            # ===== 2. 파이프라인 방식으로 필터링 검사 =====
            from app.utils.filter_pipeline import FilterPipeline
            excel_pipeline = FilterPipeline()

            # 라인 필터 추가
            active_lines = [line for line, active in line_filters.items() if active]
            if active_lines:
                line_filter = self.item_filter_factory.create_line_filter(active_lines)
                excel_pipeline.add_filter(line_filter, "라인검사")

            # 프로젝트 필터 추가
            active_projects = [project for project, active in project_filters.items() if active]
            if active_projects:
                project_filter = self.item_filter_factory.create_project_filter(active_projects)
                excel_pipeline.add_filter(project_filter, "프로젝트검사")

            # ===== 3. 단일 아이템에 대해 파이프라인 실행 =====
            context = {'mode': 'visibility_check'}
            result = excel_pipeline.apply([item], context)

            # 결과: 필터를 통과했으면 표시, 아니면 숨김
            should_show = len(result) > 0

            if hasattr(self, 'debug_filter') and self.debug_filter:
                item_info = item.item_data.get('Item', 'Unknown') if item.item_data else 'Unknown'
                print(f"[파이프라인] 엑셀 필터 검사: {item_info} → {'표시' if should_show else '숨김'}")

            return should_show

        except Exception as e:
            if hasattr(self, 'debug_filter') and self.debug_filter:
                print(f"[파이프라인] 엑셀 필터 검사 오류: {e}")
            # 오류 시 안전하게 표시
            return True

    """
    상태 필터에 따른 아이템 표시 여부 결정
    """
    def should_show_item_legend_filter(self, item):
        # 모든 필터가 꺼져 있으면 모든 아이템 표시
        if not any(self.current_filter_states.values()):
            return True
        
        # 각 상태 확인
        shortage_filter = self.current_filter_states.get('shortage', False)
        shipment_filter = self.current_filter_states.get('shipment', False)
        pre_assigned_filter = self.current_filter_states.get('pre_assigned', False)
        
        # 아이템 상태 확인
        is_shortage = hasattr(item, 'is_shortage') and item.is_shortage
        is_shipment = hasattr(item, 'is_shipment_failure') and item.is_shipment_failure
        is_pre_assigned = hasattr(item, 'is_pre_assigned') and item.is_pre_assigned
        
        # 필터 적용
        if shortage_filter and not is_shortage:
            return False
        if shipment_filter and not is_shipment:
            return False
        if pre_assigned_filter and not is_pre_assigned:
            return False
        
        return True
    
    """
    아이템이 검색어와 일치하는지 확인
    """
    def is_search_match(self, item, search_text):
        
        if not item or not hasattr(item, 'item_data') or not item.item_data:
            return False
        
        try:
            item_code = str(item.item_data.get('Item', '')).lower()
            return search_text in item_code
        except:
            return False
    
    """
    상태 필터 활성화 요청 처리
    """
    def on_filter_activation_requested(self, status_type):
    
        # 출하 상태 필터가 활성화된 경우
        if status_type == 'shipment':
            self.trigger_shipment_analysis()
        
        # 필터 상태 업데이트 후 필터 적용
        self.current_filter_states[status_type] = True
        self.apply_all_filters()

    """
    엑셀 필터를 고려한 아이템 표시 여부
    """

    def should_show_item_excel_filter(self, item):
        """
        엑셀 필터를 고려한 아이템 표시 여부 (Line과 Project 모두 확인)
        """
        if not hasattr(self, 'current_excel_filter_states') or not hasattr(item, 'item_data'):
            return True

        item_data = item.item_data

        # 라인 필터 체크
        if 'Line' in item_data:
            line = str(item_data['Line'])
            line_filters = self.current_excel_filter_states.get('line', {})
            if line_filters and line in line_filters and not line_filters[line]:
                return False

        # 프로젝트 필터 체크
        if 'Project' in item_data:
            project = item_data['Project']
            if pd.isna(project):
                project = "N/A"
            else:
                project = str(project)

            project_filters = self.current_excel_filter_states.get('project', {})
            if project_filters and project in project_filters and not project_filters[project]:
                return False

        return True
    
    """필터 활성화 요청 처리"""
    def on_filter_activation_requested(self, status_type):
        # 출하 상태 필터가 활성화된 경우
        if status_type == 'shipment':
            self.trigger_shipment_analysis()
    
    """
    데이터 로드 후 필터 데이터 업데이트
    """

    def update_filter_data(self):
        """
        데이터 로드 후 필터 데이터 업데이트 (디버깅 강화)
        """
        print("DEBUG: update_filter_data 시작")

        if self.data is None or self.data.empty:
            print("DEBUG: 필터 업데이트 - 데이터가 없음")
            return

        try:
            print(f"DEBUG: 필터 업데이트 시작 - 데이터 행 수: {len(self.data)}")
            print(f"DEBUG: 데이터 컬럼: {list(self.data.columns)}")

            # 라인 데이터 확인
            if 'Line' in self.data.columns:
                unique_lines = self.data['Line'].unique()
                print(f"DEBUG: 고유 라인 수: {len(unique_lines)}")
                print(f"DEBUG: 라인 목록: {list(unique_lines)[:10]}...")  # 처음 10개만 출력
            else:
                print("DEBUG: Line 컬럼이 없습니다!")
                return

            # 프로젝트 데이터 확인
            if 'Project' in self.data.columns:
                unique_projects = self.data['Project'].unique()
                print(f"DEBUG: 고유 프로젝트 수: {len(unique_projects)}")
                print(f"DEBUG: 프로젝트 목록: {list(unique_projects)[:10]}...")
            else:
                print("DEBUG: Project 컬럼이 없습니다!")

            # ★ 수정: 제조동은 생산량순, 제조동 내부는 번호순으로 정렬
            temp_data = self.data.copy()
            temp_data['Building'] = temp_data['Line'].str[0]
            building_production = temp_data.groupby('Building')['Qty'].sum()
            sorted_buildings = building_production.sort_values(ascending=False).index.tolist()

            all_lines = temp_data['Line'].unique()
            lines = []
            for building in sorted_buildings:
                building_lines = [line for line in all_lines if line.startswith(building)]
                # ★ 각 제조동 내에서는 번호순으로 정렬
                if building_lines:
                    def extract_line_number(line):
                        if '_' in line:
                            try:
                                return int(line.split('_')[1])
                            except ValueError:
                                return 999
                        return 999

                    sorted_building_lines = sorted(building_lines, key=extract_line_number)
                    lines.extend(sorted_building_lines)

            remaining_lines = [line for line in all_lines if line not in lines]
            if remaining_lines:
                lines.extend(sorted(remaining_lines))

            print(f"DEBUG: 정렬된 라인 수: {len(lines)}")

            # 프로젝트 목록 추출
            projects = []
            if 'Project' in self.data.columns:
                unique_projects = self.data['Project'].unique()
                for project in unique_projects:
                    if pd.isna(project):
                        projects.append("N/A")
                    else:
                        projects.append(str(project))
                projects = sorted(set(projects))
                print(f"DEBUG: 최종 프로젝트 목록 수: {len(projects)}")

            # 필터 위젯에 데이터 설정 (★ 데이터프레임도 함께 전달 ★)
            print("DEBUG: 필터 위젯에 데이터 설정 시작")
            if hasattr(self, 'filter_widget') and self.filter_widget:
                print("DEBUG: filter_widget 존재 확인됨")
                # ★ 핵심: 데이터프레임도 함께 전달
                self.filter_widget.set_filter_data(lines, projects, self.data)
                print(f"DEBUG: 필터 데이터 설정 완료 - 라인: {len(lines)}개, 프로젝트: {len(projects)}개")
            else:
                print("DEBUG: filter_widget이 없습니다!")
                print(f"DEBUG: hasattr(self, 'filter_widget'): {hasattr(self, 'filter_widget')}")
                if hasattr(self, 'filter_widget'):
                    print(f"DEBUG: self.filter_widget type: {type(self.filter_widget)}")
                    print(f"DEBUG: self.filter_widget is None: {self.filter_widget is None}")

        except Exception as e:
            print(f"DEBUG: 필터 데이터 업데이트 중 오류: {e}")
            import traceback
            traceback.print_exc()

    """
    검색 기능 실행
    """

    def search_items(self, search_text):
        """검색 기능 실행 - 인덱스 기반 최적화 + 파이프라인 통합"""
        if hasattr(self, '_search_in_progress') and self._search_in_progress:
            print("ModifiedLeftSection: 검색이 이미 진행 중 - 중복 실행 방지")
            return

        self._search_in_progress = True

        try:
            search_text = search_text.strip().lower()

            if not search_text:
                self.clear_search()
                return

            print(f"[파이프라인] 통합 검색 시작: '{search_text}'")

            # ===== 1. 인덱스가 오래되었으면 재구축 =====
            if self.search_index_manager.dirty:
                print("[최적화] 검색 인덱스 재구축 중...")
                valid_items = self.search_index_manager.build_index(self.all_items)
                self.all_items = valid_items

            # ===== 2. 인덱스 기반 빠른 검색 =====
            matched_items = self.search_index_manager.search(search_text)
            print(f"[파이프라인] 인덱스 검색 결과: {len(matched_items)}개")

            # ===== 3. 파이프라인을 통한 통합 필터링 =====
            from app.utils.filter_pipeline import PipelineTemplates
            search_pipeline = PipelineTemplates.create_search_only_pipeline()

            # 현재 활성화된 엑셀 필터들 확인
            active_lines = []
            active_projects = []
            if hasattr(self, 'current_excel_filter_states'):
                line_filters = self.current_excel_filter_states.get('line', {})
                project_filters = self.current_excel_filter_states.get('project', {})

                active_lines = [line for line, active in line_filters.items() if active]
                active_projects = [project for project, active in project_filters.items() if active]

            # 엑셀 필터가 활성화된 경우 추가 필터링
            if active_lines:
                line_filter = self.item_filter_factory.create_line_filter(active_lines)
                search_pipeline.add_filter(line_filter, "검색+라인필터")

            if active_projects:
                project_filter = self.item_filter_factory.create_project_filter(active_projects)
                search_pipeline.add_filter(project_filter, "검색+프로젝트필터")

            # 상태선 필터 (항상 적용)
            status_filter = self.item_filter_factory.create_status_line_filter(self.current_filter_states)
            search_pipeline.add_filter(status_filter, "검색+상태선필터")

            # ===== 4. 파이프라인 실행으로 최종 필터링 =====
            context = {
                'search_text': search_text,
                'filter_states': self.current_filter_states,
                'mode': 'search_with_filters'
            }

            # 검색된 아이템들에 추가 필터 적용
            if matched_items:
                final_filtered_items = search_pipeline.apply(matched_items, context)
                print(f"[파이프라인] 최종 검색 결과: {len(final_filtered_items)}개")
            else:
                final_filtered_items = []

            # ===== 5. 모든 아이템에 검색 포커스 적용 =====
            for item in self.all_items:
                try:
                    if hasattr(item, 'set_search_focus'):
                        is_match = item in matched_items
                        current_focus = getattr(item, 'is_search_focused', False)
                        if current_focus != is_match:
                            item.set_search_focus(is_match)
                except RuntimeError:
                    continue
                except Exception as e:
                    print(f"검색 포커스 설정 중 오류: {e}")
                    continue

            # ===== 6. 검색 결과 위치 기반 정렬 =====
            if final_filtered_items:
                self.search_results = self.search_result_sorter.sort_by_position(
                    final_filtered_items, self.grid_widget
                )
                print(f"[파이프라인] 검색 결과 정렬 완료: {len(self.search_results)}개")
            else:
                self.search_results = []

            # ===== 7. 그리드 선택 상태 초기화 =====
            if hasattr(self.grid_widget, 'clear_all_selections'):
                self.grid_widget.clear_all_selections()
            self.current_selected_item = None
            self.current_selected_container = None

            # ===== 8. 컨테이너 가시성 업데이트 =====
            if hasattr(self.grid_widget, 'update_container_visibility'):
                self.grid_widget.update_container_visibility()

            # ===== 9. 결과 네비게이션 표시 =====
            self.search_widget.show_result_navigation(True)

            # ===== 10. 검색 결과 처리 =====
            if self.search_results:
                self.current_result_index = 0
                self.select_current_result()
                self.update_result_navigation()
                print(f"[파이프라인] 통합 검색 완료: '{search_text}' - {len(self.search_results)}개 결과 (인덱스+파이프라인)")
            else:
                self.search_widget.set_result_status(0, 0)
                print(f"[파이프라인] 검색 결과 없음: '{search_text}'")

        finally:
            # 중복 실행 방지 플래그 해제
            QTimer.singleShot(100, lambda: setattr(self, '_search_in_progress', False))

    """
    아이템에 검색 조건 적용
    """
    """
    아이템에 검색 조건 적용
    """

    def apply_search_to_item(self, item, search_text):
        try:
            if not item or not hasattr(item, 'item_data') or not item.item_data:
                return False

            try:
                _ = item.isVisible()
            except RuntimeError:
                if item in self.all_items:
                    self.all_items.remove(item)
                return False

            item_code = str(item.item_data.get('Item', '')).lower()
            is_match = search_text in item_code

            # 검색 포커스 설정 시 추가 업데이트 방지
            if hasattr(item, 'set_search_focus'):
                # 상태가 같으면 설정하지 않음
                current_focus = getattr(item, 'is_search_focused', False)
                if current_focus != is_match:
                    item.set_search_focus(is_match)

            return is_match
        except RuntimeError:
            return False
        except Exception as e:
            print(f"아이템 검색 중 오류: {e}")
            return False

    """
    선택된 검색 결과를 포커스하고 강조 표시
    """

    def select_current_result(self):
        if not self.search_results or not (0 <= self.current_result_index < len(self.search_results)):
            return

        try:
            # 모든 아이템의 현재 검색 포커스 상태 초기화
            for i, item in enumerate(self.search_results):
                if hasattr(item, 'set_search_current'):
                    # 현재 아이템만 강조
                    is_current = (i == self.current_result_index)
                    item.set_search_current(is_current)
                    # 강제 업데이트
                    item.repaint()
                    item.update()

            # 현재 아이템 저장 및 스크롤
            self._scroll_to_current_result()
        except Exception as e:
            print(f'항목 선택 오류: {str(e)}')

    """
    검색 초기화 (SearchWidget의 searchCleared 시그널에 연결)
    """

    def clear_search(self):
        """검색 초기화 - 최적화된 포커스 해제"""
        try:
            print("[최적화] 검색 초기화 시작")

            # ===== 1. 인덱스 기반 효율적인 포커스 해제 =====
            if hasattr(self, 'search_index_manager') and not self.search_index_manager.dirty:
                # 인덱스가 유효하면 검색된 아이템들만 포커스 해제
                if hasattr(self, 'search_results') and self.search_results:
                    print(f"[최적화] 검색 결과 {len(self.search_results)}개 아이템만 포커스 해제")
                    for item in self.search_results:
                        try:
                            if hasattr(item, 'set_search_focus'):
                                item.set_search_focus(False)
                            if hasattr(item, 'set_search_current'):
                                item.set_search_current(False)
                            # 강제 업데이트
                            if hasattr(item, 'repaint'):
                                item.repaint()
                            if hasattr(item, 'update'):
                                item.update()
                        except RuntimeError:
                            # 삭제된 위젯은 무시
                            continue
                        except Exception as e:
                            print(f"검색 포커스 해제 중 오류: {e}")
                            continue
                else:
                    print("[최적화] 검색 결과가 없어 포커스 해제 스킵")
            else:
                # 인덱스가 무효하면 전체 아이템 순회 (기존 방식)
                print("[최적화] 인덱스 무효 - 전체 아이템 포커스 해제")
                for item in self.all_items:
                    try:
                        if hasattr(item, 'set_search_focus'):
                            item.set_search_focus(False)
                        if hasattr(item, 'set_search_current'):
                            item.set_search_current(False)
                        # 강제 업데이트
                        if hasattr(item, 'repaint'):
                            item.repaint()
                        if hasattr(item, 'update'):
                            item.update()
                    except RuntimeError:
                        # 삭제된 위젯은 무시
                        continue
                    except Exception as e:
                        print(f"검색 포커스 해제 중 오류: {e}")
                        continue

            # ===== 2. 선택 상태 초기화 =====
            if hasattr(self.grid_widget, 'clear_all_selections'):
                self.grid_widget.clear_all_selections()
            self.current_selected_item = None
            self.current_selected_container = None

        except Exception as e:
            print(f"검색 초기화 오류: {e}")

        # ===== 3. 검색 상태 초기화 =====
        self.search_results = []
        self.current_result_index = -1

        # ===== 4. 필터 적용 =====
        self.apply_all_filters()

        print("[최적화] 검색 초기화 완료")
    """
    이전 검색 결과로 이동 (SearchWidget의 prevResultRequested 시그널에 연결)
    """

    def go_to_prev_result(self):
        if not self.search_results or self.current_result_index <= 0:
            return

        try:
            # 인덱스 변경 전에 현재 아이템 정보 저장
            old_index = self.current_result_index

            # 이전 결과로 인덱스 변경
            self.current_result_index -= 1

            # 아이템 강조 상태 업데이트 (이전 아이템 -> 일반 검색, 현재 아이템 -> 강조)
            self._update_search_highlight(old_index, self.current_result_index)

            # 현재 결과 표시 및 네비게이션 업데이트
            self._scroll_to_current_result()
            self.update_result_navigation()
        except Exception as e:
            print(f"이전 결과 이동 오류: {str(e)}")

    """
    다음 검색 결과로 이동 (SearchWidget의 nextResultRequested 시그널에 연결)
    """

    def go_to_next_result(self):
        if not self.search_results or self.current_result_index >= len(self.search_results) - 1:
            return

        try:
            # 인덱스 변경 전에 현재 아이템 정보 저장
            old_index = self.current_result_index

            # 다음 결과로 인덱스 변경
            self.current_result_index += 1

            # 아이템 강조 상태 업데이트 (이전 아이템 -> 일반 검색, 현재 아이템 -> 강조)
            self._update_search_highlight(old_index, self.current_result_index)

            # 현재 결과 표시 및 네비게이션 업데이트
            self._scroll_to_current_result()
            self.update_result_navigation()
        except Exception as e:
            print(f"다음 결과 이동 오류: {str(e)}")

    """
    검색 결과 강조 상태 업데이트 (새로운 헬퍼 메서드)
    """

    def _update_search_highlight(self, old_index, new_index):
        # 이전 아이템 강조 해제
        if 0 <= old_index < len(self.search_results):
            old_item = self.search_results[old_index]
            if hasattr(old_item, 'set_search_current'):
                old_item.set_search_current(False)

        # 새 아이템 강조 (repaint/update 제거)
        if 0 <= new_index < len(self.search_results):
            new_item = self.search_results[new_index]
            if hasattr(new_item, 'set_search_current'):
                new_item.set_search_current(True)

    """
    현재 검색 결과로 스크롤 (새로운 헬퍼 메서드)
    """

    def _scroll_to_current_result(self):
        if not (0 <= self.current_result_index < len(self.search_results)):
            return

        current_item = self.search_results[self.current_result_index]
        container = current_item.parent()

        # 아이템 표시 확인
        if hasattr(current_item, 'isVisible') and not current_item.isVisible():
            current_item.setVisible(True)

        # 스크롤만 수행 (데이터 변경 시그널 제거)
        if hasattr(self.grid_widget, 'ensure_item_visible'):
            self.grid_widget.ensure_item_visible(container, current_item)

        # 데이터 변경 알림 제거 - 이 부분이 중복 호출의 원인
        # df = self.extract_dataframe()
        # self.viewDataChanged.emit(df)

    """
    검색 결과 상태 업데이트
    """
    def update_result_navigation(self):
        if not self.search_results:
            # 검색 결과 없음
            self.search_widget.set_result_status(0, 0)
            return
        
        try:
            total_results = len(self.search_results)
            current_index = self.current_result_index + 1  # UI에 표시할 때는 1부터 시작

            # 검색 위젯의 결과 상태 업데이트
            self.search_widget.set_result_status(current_index, total_results)
        except Exception as e:
            print(f'네비게이션 업데이트 오류: {str(e)}')

    """
    그리드에서 아이템이 선택되면 호출되는 함수
    """
    def on_grid_item_selected(self, selected_item, container):
        # 현재 선택 상태 저장
        self.current_selected_item = selected_item
        self.current_selected_container = container

        # 선택 시그널 방출
        self.item_selected.emit(selected_item, container)

    """
    검색 항목을 재검색하되 기존 검색 결과와 선택 상태를 유지
    """

    def search_items(self, search_text):
        search_text = search_text.strip().lower()

        if not search_text:
            self.clear_search()
            return

        # 검색 상태 업데이트
        self.search_results = []
        self.current_result_index = -1

        # 그리드의 모든 선택 상태 초기화
        if hasattr(self.grid_widget, 'clear_all_selections'):
            self.grid_widget.clear_all_selections()
        self.current_selected_item = None
        self.current_selected_container = None

        # 검색 결과를 행 우선으로 정렬하기 위한 임시 리스트
        row_ordered_results = []
        invalid_items = []

        # *** 핵심 변경: 행 우선 순서로 아이템 수집 ***
        if hasattr(self.grid_widget, 'containers'):
            for row_idx, row_containers in enumerate(self.grid_widget.containers):
                for col_idx, container in enumerate(row_containers):
                    for item in container.items:
                        try:
                            # 검색 조건 확인
                            if hasattr(item, 'item_data') and item.item_data:
                                item_code = str(item.item_data.get('Item', '')).lower()
                                is_match = search_text in item_code

                                if is_match:
                                    # 행과 열 정보와 함께 저장 (행 우선 정렬용)
                                    row_ordered_results.append({
                                        'item': item,
                                        'row': row_idx,
                                        'col': col_idx
                                    })

                                # 검색 포커스 설정
                                if hasattr(item, 'set_search_focus'):
                                    current_focus = getattr(item, 'is_search_focused', False)
                                    if current_focus != is_match:
                                        item.set_search_focus(is_match)

                        except RuntimeError:
                            invalid_items.append(item)
                        except Exception as e:
                            print(f"검색 중 오류 발생: {e}")

        # 유효하지 않은 아이템 목록에서 제거
        for item in invalid_items:
            if item in self.all_items:
                self.all_items.remove(item)

        # *** 핵심 변경: 행 우선 정렬 (row -> col 순서) ***
        row_ordered_results.sort(key=lambda x: (x['row'], x['col']))

        # 정렬된 순서로 검색 결과 저장
        self.search_results = [result['item'] for result in row_ordered_results]

        # 컨테이너 가시성 업데이트
        if hasattr(self.grid_widget, 'update_container_visibility'):
            self.grid_widget.update_container_visibility()

        # 결과 네비게이션 표시
        self.search_widget.show_result_navigation(True)

        # 검색 결과 처리
        if self.search_results:
            self.current_result_index = 0
            self.select_current_result()
            self.update_result_navigation()

            print(f"검색 완료: '{search_text}' - {len(self.search_results)}개 결과 (행 우선 정렬)")
        else:
            # 검색 결과 없음 표시
            self.search_widget.set_result_status(0, 0)
            print(f"검색 결과 없음: '{search_text}'")


    """
    아이템 데이터가 변경되면 호출되는 함수
    """

    def on_item_data_changed(self, item, new_data, changed_fields=None):
        """아이템 데이터 변경 처리 - 모드별 분기"""
        if not item or not new_data or not hasattr(item, 'item_data'):
            print("아이템 또는 데이터가 없음")
            return

        # 현재 아이템의 원래 위치 정보 확인
        original_data = item.item_data.copy() if hasattr(item, 'item_data') else {}

        # 위치 정보가 변경되지 않았다면 원래 위치 정보 사용
        if changed_fields and 'Line' not in changed_fields and 'Time' not in changed_fields:
            new_data['Line'] = original_data.get('Line', new_data.get('Line'))
            new_data['Time'] = original_data.get('Time', new_data.get('Time'))

        # MVC 컨트롤러가 있으면 시그널 발생
        if self._mvc_mode and hasattr(self, 'controller') and self.controller:
            print("ModifiedLeftSection: MVC 모드 - 컨트롤러로 처리")
            self.itemModified.emit(item, new_data, changed_fields)

            # *** 핵심: 모든 후처리를 즉시 실행 - 지연 없음 ***
            # 출하 분석만 간단하게 트리거
            self.trigger_shipment_analysis()
            return
        else:
            print("ModifiedLeftSection: 레거시 모드 - 직접 처리")
            # 레거시 모드에서는 기존 로직 실행
            self._handle_legacy_item_change(item, new_data, changed_fields, original_data)

    def _handle_legacy_item_change(self, item, new_data, changed_fields, original_data):
        """레거시 모드에서 아이템 변경 처리"""
        position_change_needed = False

        if changed_fields:
            if 'Time' in changed_fields:
                position_change_needed = True
                time_change = changed_fields['Time']
                old_time = time_change['from']
                new_time = time_change['to']

            if 'Line' in changed_fields:
                position_change_needed = True
                line_change = changed_fields['Line']
                old_line = line_change['from']
                new_line = line_change['to']

        if position_change_needed:
            # 위치 변경 로직 (기존 코드 유지)
            self._process_position_change(item, new_data, changed_fields, original_data)
        else:
            # 데이터만 업데이트
            if hasattr(item, 'update_item_data'):
                success, error_message = item.update_item_data(new_data)
                if not success:
                    print(f"아이템 데이터 업데이트 실패: {error_message}")
                    return

            self.mark_as_modified()
            self.itemModified.emit(item, new_data)
    
    """데이터 변경 시 출하 분석을 트리거합니다"""

    def trigger_shipment_analysis(self):
        """
        데이터 변경 시 출하 분석을 트리거
        ✅ 최적화: 중복 호출 방지 및 효율적인 일괄 처리
        """
        # ===== 중복 호출 방지 =====
        if hasattr(self, '_shipment_analysis_pending') and self._shipment_analysis_pending:
            print("[출하분석] 이미 예약된 분석이 있어 중복 실행 방지")
            return

        self._shipment_analysis_pending = True

        try:
            if hasattr(self, 'parent_page') and self.parent_page:
                current_data = self.extract_dataframe()

                if current_data is not None and not current_data.empty:
                    # ===== 1. 출하 분석 실행 =====
                    if hasattr(self.parent_page, 'analyze_shipment_with_current_data'):
                        print("[출하분석] 출하 분석 실행")
                        self.parent_page.analyze_shipment_with_current_data(current_data)

                    # ===== 2. 분산 배치 분석 실행 =====
                    if hasattr(self.parent_page, 'update_split_view_analysis'):
                        print("[출하분석] 분산 배치 분석 실행")
                        self.parent_page.update_split_view_analysis(current_data)

                    print("[출하분석] 완료")
                else:
                    print("[출하분석] 데이터가 없어 분석 건너뜀")

        except Exception as e:
            print(f"[출하분석] 오류: {e}")
        finally:
            # 분석 완료 후 플래그 해제
            QTimer.singleShot(100, lambda: setattr(self, '_shipment_analysis_pending', False))

    """
    위치 변경 처리 로직 분리
    """

    def _handle_position_change(self, item, new_data, changed_fields, old_data):
        """
        위치 변경 처리 로직 - 단순화 및 헬퍼 메서드 활용
        ✅ 리팩토링: 복잡한 로직을 명확한 단계로 분리
        """
        try:
            print(f"[위치변경] 아이템 위치 변경 처리 시작: {new_data.get('Item')}")

            # ===== 1. 기본 검증 =====
            if not self._validate_position_change_data(new_data, changed_fields):
                return False

            # ===== 2. 위치 정보 계산 =====
            position_info = self._calculate_position_info(new_data, changed_fields, old_data)
            if not position_info:
                return False

            # ===== 3. 기존 아이템 제거 =====
            old_container = item.parent() if hasattr(item, 'parent') else None
            if old_container and hasattr(old_container, 'remove_item'):
                old_container.remove_item(item)

            # ===== 4. 새 위치에 아이템 추가 =====
            new_item = self._create_item_at_new_position(new_data, position_info)

            if new_item:
                # ===== 5. 상태 복원 및 완료 처리 =====
                self._finalize_position_change(new_item, new_data, old_data)
                print(f"[위치변경] 완료: {new_data.get('Item')} @ {position_info['new_line']}-{position_info['new_time']}")
                return True
            else:
                print(f"[위치변경] 실패: 새 아이템 생성 실패")
                return False

        except Exception as e:
            print(f"[위치변경] 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _validate_position_change_data(self, new_data, changed_fields):
        """위치 변경 데이터 검증"""
        line = new_data.get('Line')
        new_time = new_data.get('Time')

        if not line or not new_time:
            print("[위치변경] 필수 데이터 누락: Line 또는 Time")
            return False

        if not changed_fields:
            print("[위치변경] 변경 필드 정보 없음")
            return False

        return True

    def _calculate_position_info(self, new_data, changed_fields, old_data):
        """위치 정보 계산"""
        try:
            line = new_data.get('Line')
            new_time = new_data.get('Time')

            # 이전 위치 정보 추출
            old_time = changed_fields.get('Time', {}).get('from', new_time) if changed_fields else new_time
            old_line = changed_fields.get('Line', {}).get('from', line) if changed_fields else line

            # 위치 인덱스 계산
            old_day_idx, old_shift = ItemPositionManager.get_day_and_shift(old_time)
            new_day_idx, new_shift = ItemPositionManager.get_day_and_shift(new_time)

            old_row_key = ItemPositionManager.get_row_key(old_line, old_shift)
            new_row_key = ItemPositionManager.get_row_key(line, new_shift)

            old_row_idx = ItemPositionManager.find_row_index(old_row_key, self.row_headers)
            new_row_idx = ItemPositionManager.find_row_index(new_row_key, self.row_headers)

            old_col_idx = ItemPositionManager.get_col_from_day_idx(old_day_idx, self.days)
            new_col_idx = ItemPositionManager.get_col_from_day_idx(new_day_idx, self.days)

            # 유효성 검사
            if any(idx < 0 for idx in [old_row_idx, old_col_idx, new_row_idx, new_col_idx]):
                print("[위치변경] 유효하지 않은 인덱스")
                return None

            return {
                'old_line': old_line, 'old_time': old_time,
                'new_line': line, 'new_time': new_time,
                'old_row_idx': old_row_idx, 'old_col_idx': old_col_idx,
                'new_row_idx': new_row_idx, 'new_col_idx': new_col_idx,
                'new_day_idx': new_day_idx, 'new_shift': new_shift
            }

        except Exception as e:
            print(f"[위치변경] 위치 계산 오류: {e}")
            return None

    def _create_item_at_new_position(self, new_data, position_info):
        """새 위치에 아이템 생성"""
        try:
            # 아이템 텍스트 생성
            item_text = str(new_data.get('Item', ''))
            if 'Qty' in new_data and pd.notna(new_data['Qty']):
                item_text += f"    {new_data['Qty']}"

            # 드롭 인덱스 계산
            drop_index = self._calculate_drop_index(new_data, position_info)

            # 새 위치에 아이템 추가
            new_item = self.grid_widget.addItemAt(
                position_info['new_row_idx'],
                position_info['new_col_idx'],
                item_text,
                new_data,
                drop_index
            )

            return new_item

        except Exception as e:
            print(f"[위치변경] 아이템 생성 오류: {e}")
            return None

    def _calculate_drop_index(self, new_data, position_info):
        """드롭 인덱스 계산"""
        drop_index = 0

        try:
            # 드롭 위치 정보가 있는 경우
            if '_drop_pos' in new_data:
                drop_pos_info = new_data['_drop_pos']
                x = int(drop_pos_info.get('x', 0))
                y = int(drop_pos_info.get('y', 0))

                target_container = self.grid_widget.containers[position_info['new_row_idx']][
                    position_info['new_col_idx']]
                drop_index = target_container.findDropIndex(QPoint(x, y))

        except Exception as e:
            print(f"[위치변경] 드롭 인덱스 계산 오류: {e}")
            drop_index = 0

        return drop_index

    def _finalize_position_change(self, new_item, new_data, old_data):
        """위치 변경 완료 처리"""
        # 수정 상태 표시
        self.mark_as_modified()

        # 아이템 상태 복원
        self._restore_item_states(new_item, new_data)

        # 셀 이동 이벤트 발생
        self.cellMoved.emit(new_item, old_data, new_data)


    """
    위치 변경 처리 (기존 로직 유지)
    """
    def _process_position_change(self, item, new_data, changed_fields, old_data):
        old_container = item.parent() if hasattr(item, 'parent') else None
        
        if not isinstance(old_container, QWidget):
            return

        # 변경된 Line과 Time에 따른 새 위치 계산
        line = new_data.get('Line')
        new_time = new_data.get('Time')

        if not line or not new_time:
            return

        # 위치 계산 로직 (기존 코드 유지)
        old_time = changed_fields.get('Time', {}).get('from', new_time) if changed_fields else new_time
        old_line = changed_fields.get('Line', {}).get('from', line) if changed_fields else line

        old_day_idx, old_shift = ItemPositionManager.get_day_and_shift(old_time)
        new_day_idx, new_shift = ItemPositionManager.get_day_and_shift(new_time)

        old_row_key = ItemPositionManager.get_row_key(old_line, old_shift)
        new_row_key = ItemPositionManager.get_row_key(line, new_shift)

        old_row_idx = ItemPositionManager.find_row_index(old_row_key, self.row_headers)
        new_row_idx = ItemPositionManager.find_row_index(new_row_key, self.row_headers)

        old_col_idx = ItemPositionManager.get_col_from_day_idx(old_day_idx, self.days)
        new_col_idx = ItemPositionManager.get_col_from_day_idx(new_day_idx, self.days)

        # 유효한 인덱스인 경우 아이템 이동
        if old_row_idx >= 0 and old_col_idx >= 0 and new_row_idx >= 0 and new_col_idx >= 0:
            # 이전 위치에서 아이템 제거
            if old_container:
                old_container.remove_item(item)

            # 새 위치에 아이템 추가
            item_text = str(new_data.get('Item', ''))
            if 'Qty' in new_data and pd.notna(new_data['Qty']):
                item_text += f"    {new_data['Qty']}"

            # 드롭 위치 정보 처리
            drop_index = 0
            if changed_fields and '_drop_pos' in changed_fields:
                try:
                    drop_pos_info = changed_fields['_drop_pos']
                    x = int(drop_pos_info['x'])
                    y = int(drop_pos_info['y'])
                    target_container = self.grid_widget.containers[new_row_idx][new_col_idx]
                    drop_index = target_container.findDropIndex(QPoint(x, y))
                except Exception as e:
                    drop_index = 0

            # 새 위치에 아이템 추가
            new_item = self.grid_widget.addItemAt(new_row_idx, new_col_idx, item_text, new_data, drop_index)

            if new_item:
                self.mark_as_modified()
                
                # 아이템 상태 복원
                self._restore_item_states(new_item, new_data)
                
                # 셀 이동 이벤트 발생
                self.cellMoved.emit(new_item, old_data, new_data)
            else:
                print("새 아이템 생성 실패")

    """
    아이템 상태 복원
    """
    def _restore_item_states(self, new_item, new_data):
        item_code = new_data.get('Item', '')
        
        # 사전할당 상태
        if item_code in self.pre_assigned_items:
            new_item.set_pre_assigned_status(True)
            
        # 출하 실패 상태
        if item_code in self.shipment_failure_items:
            failure_info = self.shipment_failure_items[item_code]
            new_item.set_shipment_failure(True, failure_info.get('reason', 'Unknown reason'))

        # 자재부족 상태
        if hasattr(self, 'current_shortage_items') and item_code in self.current_shortage_items:
            shortage_info = self.current_shortage_items[item_code]
            new_item.set_shortage_status(True, shortage_info)

    """
    MVC 컨트롤러 설정
    """

    def set_controller(self, controller):
        """MVC 컨트롤러 설정 및 MVC 모드 활성화"""
        self.controller = controller
        self._mvc_mode = True
        print("ModifiedLeftSection: MVC 모드로 전환됨")

        # 모델 변경 시그널 연결
        if self.controller and hasattr(self.controller.model, 'modelDataChanged'):
            # 기존 연결이 있다면 해제하고 새로 연결
            try:
                self.controller.model.modelDataChanged.disconnect(self.update_from_model)
            except TypeError:
                pass  # 연결되어 있지 않은 경우 무시

            self.controller.model.modelDataChanged.connect(self.update_from_model)
            print("ModifiedLeftSection: 모델 변경 시그널 연결 완료")

        # 시그널이 아직 연결되지 않았다면 연결
        if not self._signals_connected:
            self.connect_signals()

    """
    검증기 설정
    """
    def set_validator(self, validator):
        self.validator = validator
        if hasattr(self.grid_widget, 'set_validator'):
            self.grid_widget.set_validator(validator)
        print("검증기가 설정되었습니다")
        

    """
    엑셀 파일 로드 -  ResultPage의 통합 메서드 호출
    """
    def load_excel_file(self):
        # 부모 페이지 확인
        if not hasattr(self, 'parent_page') or self.parent_page is None:
            print("[ERROR] parent_page 참조가 없습니다.")
            EnhancedMessageBox.show_validation_error(
                self, 
                "오류", 
                "페이지 참조가 설정되지 않았습니다."
            )
            return
        
        # ResultPage의 load_result_file 메서드 호출
        file_path, _ = QFileDialog.getOpenFileName(
            self, "엑셀 파일 선택", "", "Excel Files (*.xlsx *.xls *.csv)"
        )
        
        if file_path:
            self.parent_page.load_result_file(file_path)


    """
    아이템 목록과 그리드 초기화하는 메서드
    """
    def clear_all_items(self) :
        self.all_items = []
        self.search_widget.on_clear()
        if hasattr(self, 'grid_widget'):
            self.grid_widget.clearAllItems()

    """
    엑셀 파일에서 데이터를 읽어와 테이블 업데이트
    """
    def update_table_from_data(self):
        if self.data is None:
            return

        self.update_ui_with_signals()

        # 데이터 변경 신호 발생
        df = self.extract_dataframe()
        self.viewDataChanged.emit(df)

        self.preload_analyses()

        self.trigger_shipment_analysis()

    """데이터 로드 후 사전 분석 실행"""

    def preload_analyses(self):
        """
        데이터 로드 후 사전 분석 실행
        ✅ 리팩토링: 중복 분석 호출 정리 및 효율적인 일괄 처리
        """
        # 데이터가 없으면 건너뜀
        if self.data is None or self.data.empty:
            print("[사전분석] 데이터가 없어 분석 건너뜀")
            return

        # 결과 페이지 참조 확인
        result_page = self.parent_page
        if not result_page:
            print("[사전분석] parent_page 참조가 없어 분석 건너뜀")
            return

        try:
            print(f"[사전분석] 시작 - {len(self.data)}행 데이터")

            # ===== 1. 핵심 분석만 사전 실행 (중복 제거) =====
            analysis_results = self._execute_core_analyses()

            # ===== 2. 탭 위젯 초기화 (필요한 것만) =====
            self._initialize_essential_tabs(analysis_results)

            # ===== 3. 범례 필터 상태 정리 =====
            self._update_legend_filters()

            print("[사전분석] 완료 - 핵심 분석만 실행")

        except Exception as e:
            print(f"[사전분석] 오류: {e}")
            import traceback
            traceback.print_exc()

    def _initialize_essential_tabs(self, analysis_results):
        """필수 탭만 초기화 - 불필요한 중복 제거"""
        try:
            # Summary 탭만 사전 초기화 (가장 자주 사용됨)
            if (hasattr(self.parent_page, 'summary_widget') and
                    self.parent_page.summary_widget and
                    analysis_results['data_summary']):

                print("[사전분석] Summary 위젯 초기화")
                # Summary 위젯에 기본 정보만 설정
                summary_data = analysis_results['data_summary']
                # summary_widget가 set_basic_info 메서드를 가지고 있다면 사용
                if hasattr(self.parent_page.summary_widget, 'set_basic_info'):
                    self.parent_page.summary_widget.set_basic_info(summary_data)

            # 다른 탭들은 필요할 때 lazy loading으로 처리
            # (사용자가 탭을 클릭할 때 초기화)

        except Exception as e:
            print(f"[사전분석] 탭 초기화 중 오류: {e}")

    def _update_legend_filters(self):
        """범례 필터 상태 정리 - 중복 이벤트 방지"""
        try:
            if hasattr(self, 'legend_widget') and self.legend_widget:
                # 현재 필터 상태 백업
                current_states = self.legend_widget.filter_states.copy()

                # 상태가 변경된 경우에만 이벤트 발생
                if current_states != self.current_filter_states:
                    print("[사전분석] 범례 필터 상태 동기화")
                    # 직접 상태 설정 (이벤트 발생 방지)
                    self.legend_widget.set_filter_states(current_states)

        except Exception as e:
            print(f"[사전분석] 범례 필터 업데이트 중 오류: {e}")

    def _execute_core_analyses(self):
        """핵심 분석만 실행 - 중복 제거"""
        analysis_results = {
            'material_completed': False,
            'shipment_completed': False,
            'data_summary': None
        }

        try:
            # Material 분석 (자재 부족 분석)
            if hasattr(self.parent_page, 'material_widget') and self.parent_page.material_widget:
                print("[사전분석] 자재 부족 분석 실행")
                self.parent_page.material_widget.run_analysis(self.data)
                self.parent_page.material_analyzer = self.parent_page.material_widget.get_material_analyzer()
                analysis_results['material_completed'] = True

            # Shipment 분석 (한 번만 실행)
            if hasattr(self.parent_page, 'shipment_widget') and self.parent_page.shipment_widget:
                print("[사전분석] 출하 분석 실행")
                self.parent_page.shipment_widget.run_analysis(self.data)
                analysis_results['shipment_completed'] = True

            # 기본 데이터 요약 (Summary용)
            analysis_results['data_summary'] = {
                'total_items': len(self.data),
                'unique_lines': self.data['Line'].nunique(),
                'total_qty': self.data['Qty'].sum() if 'Qty' in self.data.columns else 0
            }

        except Exception as e:
            print(f"[사전분석] 핵심 분석 중 오류: {e}")

        return analysis_results

    """범례 위젯에서 필터가 변경될 때 호출"""

    def update_status_lines_only(self, filter_states):
        """상태선만 효율적으로 업데이트 - 파이프라인 패턴으로 중복 제거"""
        if not hasattr(self, 'grid_widget') or not hasattr(self.grid_widget, 'containers'):
            return

        print(f"[파이프라인] 상태선 업데이트 시작 - {sum(1 for v in filter_states.values() if v)}개 필터 활성화")

        try:
            # ===== 1. 상태선 전용 파이프라인 생성 =====
            from app.utils.filter_pipeline import PipelineTemplates
            status_pipeline = PipelineTemplates.create_status_only_pipeline()

            # ===== 2. 상태선 필터 설정 =====
            status_filter = self.item_filter_factory.create_status_line_filter(filter_states)
            status_pipeline.add_filter(status_filter, "상태선업데이트")

            # ===== 3. 효율적인 업데이트 실행 =====
            if hasattr(self, 'all_items') and self.all_items:
                context = {
                    'filter_states': filter_states,
                    'mode': 'status_update_only',  # 상태선만 업데이트, 가시성 변경 없음
                    'batch_update': True  # 배치 업데이트 모드
                }

                # 파이프라인 실행
                status_pipeline.apply(self.all_items, context)

                print(f"[파이프라인] 상태선 업데이트 완료 - {len(self.all_items)}개 아이템 처리")
            else:
                print("[파이프라인] 업데이트할 아이템이 없음")

        except Exception as e:
            print(f"[파이프라인] 상태선 업데이트 중 오류: {e}")
            import traceback
            traceback.print_exc()

    """
    Line과 Time으로 데이터 그룹화하고 개별 아이템으로 표시
    """

    def update_ui_with_signals(self):
        """새 데이터 로드 시 UI 업데이트 - 공통 로직 활용"""
        if self.data is None or 'Line' not in self.data.columns or 'Time' not in self.data.columns:
            EnhancedMessageBox.show_validation_error(self, "Grouping Failed",
                                                     "Data is missing or does not contain 'Line' or 'Time' columns.\nPlease load data with the required columns.")
            return

        try:
            print("[단순화] update_ui_with_signals 시작 - 새 데이터 로드 모드")

            # ===== 1. 공통 UI 업데이트 실행 =====
            success = self._update_ui_components(
                data_df=self.data,
                source="signals",
                preserve_search=False,  # 새 데이터이므로 검색 상태 초기화
                preserve_filters=False  # 새 데이터이므로 필터 상태 초기화
            )

            if not success:
                print("[단순화] UI 업데이트 실패")
                return

            # ===== 2. signals 모드만의 고유 작업들 =====

            # 원본 데이터 저장 (새 데이터이므로)
            self.original_data = self.data.copy()
            print("[단순화] 원본 데이터 저장 완료")

            # 그룹화된 데이터 저장 (기존 코드 유지)
            if 'Day' in self.data.columns:
                self.grouped_data = self.data.groupby(['Line', 'Day', 'Time']).first().reset_index()
            else:
                self.grouped_data = self.data.groupby(['Line', 'Time']).first().reset_index()

            # 데이터 변경 신호 발생
            df = self.extract_dataframe()
            self.viewDataChanged.emit(df)
            print("[단순화] 데이터 변경 신호 발생")

            # 필터 데이터 업데이트 (새 데이터이므로 필터 옵션 재설정)
            self.update_filter_data()
            print("[단순화] 필터 데이터 업데이트 완료")

            print("[단순화] update_ui_with_signals 완료")

        except Exception as e:
            print(f"[단순화] update_ui_with_signals 오류: {e}")
            import traceback
            traceback.print_exc()
            EnhancedMessageBox.show_validation_error(self, "Grouping Error",
                                                     f"An error occurred during data grouping.\n{str(e)}")

    """
    외부에서 데이터 설정
    """

    def set_data_from_external(self, new_data):
        """외부에서 데이터 설정 - 공통 로직 활용"""
        print("[단순화] set_data_from_external 호출")

        try:
            # ===== 1. 데이터 정규화 =====
            self.data = self._normalize_data_types(new_data.copy())
            self.original_data = self.data.copy()

            # ===== 2. 공통 UI 업데이트 실행 =====
            success = self._update_ui_components(
                data_df=self.data,
                source="external",
                preserve_search=False,  # 외부 데이터이므로 검색 상태 초기화
                preserve_filters=False  # 외부 데이터이므로 필터 상태 초기화
            )

            if not success:
                print("[단순화] 외부 데이터 설정 실패")
                return

            # ===== 3. external 모드만의 고유 작업들 =====

            # ★★★ 필터 데이터 업데이트 강제 실행 ★★★
            print("[단순화] 필터 데이터 업데이트 강제 실행")
            self.update_filter_data()

            # 데이터 변경 신호 발생
            df = self.extract_dataframe()
            self.viewDataChanged.emit(df)

            # 사전 분석 실행
            self.preload_analyses()

            # 출하 분석 트리거
            self.trigger_shipment_analysis()

            print("[단순화] set_data_from_external 완료")

        except Exception as e:
            print(f"[단순화] set_data_from_external 오류: {e}")
            import traceback
            traceback.print_exc()

    """
    원본 데이터로 되돌리기
    """
    def reset_to_original(self):
        if self.original_data is None:
            EnhancedMessageBox.show_validation_error(self, "Reset Failed", 
                                "No original data to reset to.")
            return
        
        # 사용자 확인 Dialog
        reply = EnhancedMessageBox.show_confirmation(
            self, "Reset to Original", "Are you sure you want to reset all changes and return to the original data?\nAll modifications will be lost."
        )

        if reply:
            # 컨트롤러 연결
            if hasattr(self, 'controller') and self.controller:
                print("컨트롤러를 통해 리셋 요청")
                self.controller.reset_data()
                
                # Reset 버튼 비활성화
                self.reset_button.setEnabled(False)

                # 성공 메세지
                EnhancedMessageBox.show_validation_success(
                    self, "Reset Complete", "Data has been successfully reset to the original values."
                )
            else: 
                # 레거시 방식
                # 원본 데이터로 복원
                self.data = self.original_data.copy()
                self.update_table_from_data()

                # Reset 버튼 비활성화
                self.reset_button.setEnabled(False)

                # 성공 메세지
                EnhancedMessageBox.show_validation_success(
                    self, "Reset Complete", "Data has been successfully reset to the original values."
                )
    
    """
    데이터가 수정되었음을 표시하는 메서드
    """
    def mark_as_modified(self):
        print("[DEBUG] mark_as_modified 호출됨 - 리셋 버튼 활성화")
        self.reset_button.setEnabled(True)

    """
    현재 자재부족 아이템 정보 저장
    """
    def set_current_shortage_items(self, shortage_items):
        """
        현재 자재부족 아이템 정보 저장
        ✅ 수정: update_left_widget_shortage_status() → apply_all_states() 호출
        """
        # 자재 부족 정보 저장
        self.current_shortage_items = shortage_items

        # ✅ 수정: 개별 메서드 대신 통합 상태 적용 메서드 사용
        self.apply_all_states()

        print(f"자재 부족 상태 적용 완료: {len(shortage_items)}개 아이템")


    """
    모든 상태 정보를 현재 아이템들에 적용
    """

    def apply_all_states(self):
        """
        모든 상태 정보를 현재 아이템들에 적용
        ✅ 개선: 효율적인 일괄 처리로 성능 향상
        """
        if not hasattr(self, 'grid_widget') or not hasattr(self.grid_widget, 'containers'):
            return

        print("[상태적용] 모든 아이템에 상태 정보 적용 시작")
        applied_count = {'pre_assigned': 0, 'shipment_failure': 0, 'shortage': 0}

        for row_containers in self.grid_widget.containers:
            for container in row_containers:
                for item in container.items:
                    if not hasattr(item, 'item_data') or not item.item_data or 'Item' not in item.item_data:
                        continue

                    item_code = item.item_data['Item']
                    item_time = item.item_data.get('Time')

                    # 사전할당 상태
                    if item_code in self.pre_assigned_items:
                        item.set_pre_assigned_status(True)
                        applied_count['pre_assigned'] += 1

                    # 출하 실패 상태
                    if item_code in self.shipment_failure_items:
                        failure_info = self.shipment_failure_items[item_code]
                        item.set_shipment_failure(True, failure_info.get('reason', 'Unknown'))
                        applied_count['shipment_failure'] += 1

                    # 자재 부족 상태 - 시프트별 체크 적용
                    if hasattr(self, 'current_shortage_items') and item_code in self.current_shortage_items:
                        shortages = self.current_shortage_items[item_code]
                        matching_shortages = []

                        # 시프트별 부족 정보 검사
                        for shortage in shortages:
                            shortage_shift = shortage.get('shift')

                            # 시프트가 일치하는 경우만 처리
                            if shortage_shift and item_time and int(shortage_shift) == int(item_time):
                                matching_shortages.append(shortage)

                        # 일치하는 시프트의 부족 정보가 있으면 부족 상태로 설정
                        if matching_shortages:
                            item.set_shortage_status(True, matching_shortages)
                            applied_count['shortage'] += 1
                        else:
                            item.set_shortage_status(False)
                    else:
                        item.set_shortage_status(False)

        print(f"[상태적용] 완료 - 사전할당: {applied_count['pre_assigned']}, "
              f"출하실패: {applied_count['shipment_failure']}, 자재부족: {applied_count['shortage']}")

    def apply_filters_safely(self):
        """
        안전한 필터 적용 - 드래그앤드롭 후 호출
        ✅ 수정: apply_standard_filters() → apply_all_filters() 호출
        """
        try:
            # 현재 데이터가 있는지 확인
            if not hasattr(self, 'data') or self.data is None or self.data.empty:
                print("DEBUG: 데이터가 없어서 필터 적용 스킵")
                return

            # ✅ 수정: 통합된 필터 적용 메서드 사용
            self.apply_all_filters()

            # 검색이 활성화된 경우에만 검색 상태 복원
            if hasattr(self, 'search_widget') and self.search_widget.is_search_active():
                search_text = self.search_widget.get_search_text()
                if search_text:
                    QTimer.singleShot(50, lambda: self.search_items(search_text))

        except Exception as e:
            print(f"안전한 필터 적용 중 오류: {e}")
            import traceback
            traceback.print_exc()

    """범례 위젯에서 필터가 변경될 때 호출"""
    def on_filter_changed(self, status_type, is_checked):
        # 이전 상태와 동일하면 불필요한 처리 방지
        if self.current_filter_states.get(status_type) == is_checked:
            return
        
        # 상태 업데이트
        self.current_filter_states[status_type] = is_checked
        
        # 필터 적용
        self.apply_all_filters()
        
        # 필터가 활성화되면 해당 상태 분석 요청 
        if is_checked:
            self.filter_activation_requested.emit(status_type)

    """
    상태선만 효율적으로 업데이트 (가시성은 변경하지 않음)
    """

    def update_status_lines_only(self, filter_states):
        """상태선만 효율적으로 업데이트 - 파이프라인 패턴으로 중복 제거"""
        if not hasattr(self, 'grid_widget') or not hasattr(self.grid_widget, 'containers'):
            return

        print(f"[파이프라인] 상태선 업데이트 시작 - {sum(1 for v in filter_states.values() if v)}개 필터 활성화")

        try:
            # ===== 1. 상태선 전용 파이프라인 생성 =====
            from app.utils.filter_pipeline import PipelineTemplates
            status_pipeline = PipelineTemplates.create_status_only_pipeline()

            # ===== 2. 상태선 필터 설정 =====
            status_filter = self.item_filter_factory.create_status_line_filter(filter_states)
            status_pipeline.add_filter(status_filter, "상태선업데이트")

            # ===== 3. 효율적인 업데이트 실행 =====
            if hasattr(self, 'all_items') and self.all_items:
                context = {
                    'filter_states': filter_states,
                    'mode': 'status_update_only',  # 상태선만 업데이트, 가시성 변경 없음
                    'batch_update': True  # 배치 업데이트 모드
                }

                # 파이프라인 실행
                status_pipeline.apply(self.all_items, context)

                print(f"[파이프라인] 상태선 업데이트 완료 - {len(self.all_items)}개 아이템 처리")
            else:
                print("[파이프라인] 업데이트할 아이템이 없음")

        except Exception as e:
            print(f"[파이프라인] 상태선 업데이트 중 오류: {e}")
            import traceback
            traceback.print_exc()
            
    """
    현재 필터 상태에 따라 아이템 가시성 조정
    """
    def apply_visibility_filter(self):
        if not hasattr(self, 'grid_widget') or not hasattr(self.grid_widget, 'containers'):
            return
        
        self.apply_all_filters()
    
    """
    아이템의 상태선 업데이트
    """
    def update_item_status_line_visibility(self, item):
        if not hasattr(self, 'current_filter_states'):
            return
        
        # 상태 변수 캐싱
        shortage_filter = self.current_filter_states.get('shortage', False)
        shipment_filter = self.current_filter_states.get('shipment', False)
        pre_assigned_filter = self.current_filter_states.get('pre_assigned', False)
        
        # 변경 필요 여부 추적
        need_update = False
        
        # 각 상태선 설정 (이전과 다른 경우만 변경)
        if hasattr(item, 'is_shortage') and hasattr(item, 'show_shortage_line'):
            new_state = shortage_filter and item.is_shortage
            if item.show_shortage_line != new_state:
                item.show_shortage_line = new_state
                need_update = True
        
        if hasattr(item, 'is_shipment_failure') and hasattr(item, 'show_shipment_line'):
            new_state = shipment_filter and item.is_shipment_failure
            if item.show_shipment_line != new_state:
                item.show_shipment_line = new_state
                need_update = True
        
        if hasattr(item, 'is_pre_assigned') and hasattr(item, 'show_pre_assigned_line'):
            new_state = pre_assigned_filter and item.is_pre_assigned
            if item.show_pre_assigned_line != new_state:
                item.show_pre_assigned_line = new_state
                need_update = True
        
        # 변경이 필요한 경우만 repaint 요청
        if need_update and hasattr(item, 'update'):
            item.update()

    """
    아이템 삭제 처리 메서드 (ItemContainer에서 발생한 삭제를 처리)
    """

    def on_item_removed(self, item_or_id):
        """아이템 삭제 처리 - 검색 인덱스 무효화 추가"""
        # ===== 검색 인덱스 무효화 =====
        self.search_index_manager.mark_dirty()
        print(f"[최적화] 아이템 삭제로 검색 인덱스 무효화")

        # MVC 컨트롤러가 있으면 컨트롤러에서 처리
        if self._mvc_mode and hasattr(self, 'controller') and self.controller:
            print("ModifiedLeftSection: MVC 모드 - 컨트롤러로 삭제 처리")
            if hasattr(self.controller, 'on_item_deleted'):
                self.controller.on_item_deleted(item_or_id)
                self.trigger_shipment_analysis()
                return
            else:
                print("DEBUG: 컨트롤러에 on_item_deleted 메서드가 없음")

        # 컨트롤러가 없거나 처리하지 않은 경우 기존 로직 사용
        if self.data is None:
            print("DEBUG: 데이터가 없음")
            return

        # item_or_id가 문자열(ID)인 경우
        if isinstance(item_or_id, str):
            item_id = item_or_id
            print(f"DEBUG: ID로 삭제: {item_id}")
            mask = ItemKeyManager.create_mask_by_id(self.data, item_id)
            if mask.any():
                self.data = self.data[~mask].reset_index(drop=True)
                df = self.extract_dataframe()
                self.viewDataChanged.emit(df)
                self.mark_as_modified()
                self.trigger_shipment_analysis()
            else:
                print(f"DEBUG: ID {item_id}로 아이템을 찾을 수 없음")
            return

        # item_or_id가 아이템 객체인 경우
        if hasattr(item_or_id, 'item_data') and item_or_id.item_data:
            # ID가 있으면 ID로 찾기
            item_id = ItemKeyManager.extract_item_id(item_or_id)
            if item_id:
                print(f"DEBUG: 아이템 객체의 ID로 삭제: {item_id}")
                mask = ItemKeyManager.create_mask_by_id(self.data, item_id)
                if mask.any():
                    self.data = self.data[~mask].reset_index(drop=True)
                    df = self.extract_dataframe()
                    self.viewDataChanged.emit(df)
                    self.mark_as_modified()
                    return

            # ID가 없으면 Line/Time/Item으로 찾기
            line, time, item_code = ItemKeyManager.get_item_from_data(item_or_id.item_data)
            if line is not None and time is not None and item_code is not None:
                print(f"DEBUG: Line/Time/Item으로 삭제: {item_code} @ {line}-{time}")
                mask = ItemKeyManager.create_mask_for_item(self.data, line, time, item_code)
                if mask.any():
                    self.data = self.data[~mask].reset_index(drop=True)
                    df = self.extract_dataframe()
                    self.viewDataChanged.emit(df)
                    self.mark_as_modified()
                else:
                    print(f"DEBUG: Line/Time/Item으로 아이템을 찾을 수 없음")
        else:
            print("DEBUG: 유효하지 않은 아이템 객체")

        # 처리 완료 후 출하 분석 업데이트
        df = self.extract_dataframe()
        self.viewDataChanged.emit(df)
        self.mark_as_modified()

        # 출하 분석 업데이트 요청
        self.trigger_shipment_analysis()

    """
    현재 뷰에 로드된 DataFrame(self.data)의 사본 반환
    viewDataChanged 신호를 뿌릴 때 사용 
    """
    def extract_dataframe(self) -> pd.DataFrame:
        if hasattr(self, 'data') and isinstance(self.data, pd.DataFrame):
            return self._normalize_data_types(self.data.copy())
        else:
            return pd.DataFrame()
        
    """
    모델로부터 UI 업데이트 - 이벤트 발생시키지 않음
    """

    def update_from_model(self, model_df=None):
        """모델로부터 UI 업데이트 - 공통 로직 활용"""
        print("ModifiedLeftSection: update_from_model 호출")

        if not self._mvc_mode:
            print("WARNING: 레거시 모드에서 update_from_model이 호출됨 - 하지만 처리 계속")

        try:
            # ===== 1. 모델 데이터 가져오기 =====
            if model_df is None:
                if hasattr(self, 'controller') and self.controller:
                    model_df = self.controller.model.get_dataframe()
                    print("[단순화] 컨트롤러에서 데이터 가져옴")
                else:
                    print("[단순화] 모델 데이터가 없습니다.")
                    return

            if model_df is None:
                print("[단순화] 데이터가 없습니다.")
                return

            # ===== 2. 공통 UI 업데이트 실행 =====
            success = self._update_ui_components(
                data_df=model_df,
                source="model",
                preserve_search=True,  # 모델 변경이므로 검색 상태 보존
                preserve_filters=True  # 모델 변경이므로 필터 상태 보존
            )

            if not success:
                print("[단순화] UI 업데이트 실패")
                return

            # ===== 3. model 모드만의 고유 작업들 =====

            # 출하 분석 즉시 업데이트 (모델 변경 후 분석 갱신)
            self.trigger_shipment_analysis()
            print("[단순화] 출하 분석 업데이트 요청")

            print("[단순화] update_from_model 완료")

        except Exception as e:
            print(f"[단순화] update_from_model 오류: {e}")
            import traceback
            traceback.print_exc()

    """
    복사된 아이템 처리
    """

    def on_item_copied(self, item, data):
        """복사된 아이템 처리 - 모드별 분기"""
        print("ModifiedLeftSection: on_item_copied 호출됨")

        # 아이템 등록
        self.register_item(item)

        # MVC 모드와 레거시 모드 분기
        if self._mvc_mode and hasattr(self, 'controller') and self.controller:
            print("ModifiedLeftSection: MVC 모드 - 컨트롤러로 복사 처리")
            # MVC 패턴에서는 뷰는 UI 렌더링만 담당, 데이터 처리는 컨트롤러에서
            # 데이터 처리는 이미 컨트롤러에서 완료되었으므로 추가 처리 불필요
            return
        else:
            print("ModifiedLeftSection: 레거시 모드 - 직접 복사 처리")
            # 레거시 모드: 직접 데이터 처리
            df = self.extract_dataframe()
            self.viewDataChanged.emit(df)
            self.trigger_shipment_analysis()

    """
    출하 실패 아이템 정보 설정
    """
    def set_shipment_failure_items(self, failure_items):
                
        # 이전 출하 실패 정보 초기화
        old_failure_items = getattr(self, 'shipment_failure_items', {})
        
        # 새 출하 실패 정보 저장
        self.shipment_failure_items = failure_items
        
        # 상태 변화가 있을 때만 UI 업데이트
        if old_failure_items != failure_items:
            self.apply_shipment_failure_status()

    """출하 실패 상태를 모든 아이템에 적용"""
    def apply_shipment_failure_status(self):
        if not hasattr(self, 'grid_widget') or not hasattr(self.grid_widget, 'containers'):
            return
        
        # 출하 실패 아이템 목록이 없는 경우 초기화
        if not hasattr(self, 'shipment_failure_items'):
            self.shipment_failure_items = {}
        
        status_applied_count = 0
        
        # 모든 컨테이너와 아이템 순회
        for row_containers in self.grid_widget.containers:
            for container in row_containers:
                for item in container.items:
                    if not hasattr(item, 'item_data') or not item.item_data:
                        continue
                        
                    item_data = item.item_data
                    
                    # 필수 필드 확인
                    if 'Item' not in item_data:
                        continue
                        
                    item_code = item_data['Item']
                    
                    # 간단하게 아이템 코드로만 검색 (복합 키는 제외)
                    if item_code in self.shipment_failure_items:
                        # 출하 실패 정보 가져오기
                        failure_info = self.shipment_failure_items[item_code]
                        reason = failure_info.get('reason', '출하 실패')
                        
                        # 출하 실패 상태로 설정
                        item.set_shipment_failure(True, reason)
                        status_applied_count += 1
                    else:
                        # 출하 성공 상태로 설정 (기존 실패였던 경우)
                        if hasattr(item, 'is_shipment_failure') and item.is_shipment_failure:
                            item.set_shipment_failure(False, None)

    def _restore_scroll_position(self, position):
        """스크롤 위치 복원"""
        if hasattr(self.grid_widget, 'scroll_area'):
            # 약간의 지연을 주고 스크롤 위치 복원
            h_bar = self.grid_widget.scroll_area.horizontalScrollBar()
            v_bar = self.grid_widget.scroll_area.verticalScrollBar()

            if 'horizontal' in position:
                h_bar.setValue(position['horizontal'])
            if 'vertical' in position:
                v_bar.setValue(position['vertical'])

    def _scroll_to_selected_item(self, item_id):
        """선택된 아이템으로 스크롤 이동"""
        if not item_id or not hasattr(self, 'grid_widget'):
            return

        # 아이템 ID로 아이템 위젯 찾기
        found_item = None
        found_container = None

        for row_idx, row_containers in enumerate(self.grid_widget.containers):
            for col_idx, container in enumerate(row_containers):
                for item in container.items:
                    if hasattr(item, 'item_data') and item.item_data and item.item_data.get('_id') == item_id:
                        found_item = item
                        found_container = container
                        print(f"아이템 찾음: ID={item_id}, 위치=[{row_idx}][{col_idx}]")
                        break
                if found_item:
                    break
            if found_item:
                break

        if found_item and found_container:
            # 아이템 선택 상태 설정
            found_item.set_selected(True)
            self.current_selected_item = found_item
            self.current_selected_container = found_container

            # 스크롤 위치 직접 설정 (아래 방법도 추가)
            QTimer.singleShot(50, lambda: self._force_scroll_to_item(found_container, found_item))

            # ItemGridWidget의 ensure_item_visible 호출 (기존 방식)
            if hasattr(self.grid_widget, 'ensure_item_visible'):
                self.grid_widget.ensure_item_visible(found_container, found_item)

            print(f"아이템으로 스크롤 요청 완료: {item_id}")

    def _force_scroll_to_item(self, container, item):
        """직접 스크롤 위치 설정 (더 강력한 방법)"""
        if not container or not item or not hasattr(self.grid_widget, 'scroll_area'):
            return

        try:
            # 컨테이너 위치 계산
            for row_idx, row in enumerate(self.grid_widget.containers):
                if container in row:
                    col_idx = row.index(container)

                    # 스크롤 영역 가져오기
                    scroll_area = self.grid_widget.scroll_area

                    # 컨테이너와 아이템의 전역 위치 계산
                    container_pos = container.mapTo(self.grid_widget.scroll_content, QPoint(0, 0))
                    item_pos = item.mapTo(container, QPoint(0, 0))

                    # 최종 타겟 위치 계산
                    target_y = container_pos.y() + item_pos.y()

                    # 스크롤바 이동
                    v_bar = scroll_area.verticalScrollBar()

                    # 아이템이 화면 중앙에 오도록 스크롤
                    viewport_height = scroll_area.viewport().height()
                    target_y = max(0, target_y - (viewport_height // 2) + (item.height() // 2))

                    # 스크롤 위치 설정
                    v_bar.setValue(target_y)
                    print(f"스크롤 위치 설정: y={target_y}")

                    break
        except Exception as e:
            print(f"강제 스크롤 중 오류 발생: {str(e)}")

    def _update_ui_components(self, data_df, source="unknown", preserve_search=True, preserve_filters=True):
        """
        공통 UI 업데이트 메서드 - 중복 로직 통합 + 헬퍼 메서드 활용

        Args:
            data_df: 업데이트할 데이터프레임
            source: 호출 소스 ("signals", "model", "external")
            preserve_search: 검색 상태 보존 여부
            preserve_filters: 필터 상태 보존 여부
        """
        if data_df is None or 'Line' not in data_df.columns or 'Time' not in data_df.columns:
            print(f"[UI업데이트] {source}에서 호출 - 데이터가 없거나 필수 컬럼 누락")
            return False

        try:
            print(f"[UI업데이트] {source}에서 UI 업데이트 시작 - {len(data_df)}행")

            # ===== 1. 검색 인덱스 무효화 =====
            self.search_index_manager.mark_dirty()
            print(f"[최적화] {source} UI 재구성으로 검색 인덱스 무효화")

            # ===== 2. 상태 백업 (preserve 옵션에 따라) =====
            backup_data = self._backup_ui_state(preserve_search, preserve_filters)

            # ===== 3. 데이터 정규화 및 정렬 =====
            self.data = self._normalize_data_types(data_df.copy())
            self._sort_data_by_building()

            # ===== 4. 기존 아이템 정리 =====
            self.clear_all_items()
            print(f"[UI업데이트] 기존 아이템 정리 완료")

            # ===== 5. 그리드 설정 =====
            lines, line_shifts, row_headers = self._prepare_grid_structure()

            self.grid_widget.setupGrid(
                rows=len(row_headers),
                columns=len(self.days),
                row_headers=row_headers,
                column_headers=self.days,
                line_shifts=line_shifts
            )

            # ===== 6. 아이템 생성 및 배치 =====
            item_count = self._populate_grid_with_items()

            # ===== 7. 필터 데이터 업데이트 (★★★ 이 부분 추가 ★★★) =====
            print(f"[UI업데이트] 필터 데이터 업데이트 시작")
            self.update_filter_data()
            print(f"[UI업데이트] 필터 데이터 업데이트 완료")

            # ===== 8. 상태 복원 =====
            self._restore_ui_state(backup_data, preserve_search, preserve_filters)

            print(f"[UI업데이트] {source} UI 업데이트 완료 - 총 {item_count}개 아이템")
            return True

        except Exception as e:
            print(f"[UI업데이트] {source} UI 업데이트 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _sort_data_by_building(self):
        """데이터를 제조동별로 정렬하는 헬퍼 메서드"""
        try:
            # 제조동 정보 추출 (Line 이름의 첫 글자가 제조동)
            self.data['Building'] = self.data['Line'].str[0]

            # 제조동별 생산량 계산 (정렬 목적)
            building_production = self.data.groupby('Building')['Qty'].sum()

            # 생산량 기준으로 제조동 정렬 (내림차순)
            sorted_buildings = building_production.sort_values(ascending=False).index.tolist()

            # 1. 제조동 정렬 순서 생성
            building_order = {b: i for i, b in enumerate(sorted_buildings)}
            self.data['Building_sort'] = self.data['Building'].apply(lambda x: building_order.get(x, 999))

            # 2. 같은 제조동 내에서 라인명으로 정렬 (I_01 -> 01 형태로 변환)
            self.data['Line_sort'] = self.data['Line'].apply(
                lambda x: x.split('_')[1] if '_' in x else x
            )

            # 3. 최종 정렬 적용 (제조동 순위 -> 라인명 -> 시간)
            self.data = self.data.sort_values(by=['Building_sort', 'Line_sort', 'Time']).reset_index(drop=True)

            # 4. 임시 정렬 컬럼 제거
            self.data = self.data.drop(columns=['Building_sort', 'Line_sort'], errors='ignore')

            print(f"[헬퍼] 제조동별 정렬 완료 - {len(sorted_buildings)}개 제조동: {sorted_buildings}")
            return sorted_buildings

        except Exception as e:
            print(f"[헬퍼] 제조동 정렬 중 오류: {e}")
            return []

    def _prepare_grid_structure(self):
        """그리드 구조 준비 헬퍼 메서드"""
        try:
            # 정렬된 라인 목록 생성
            sorted_buildings = self.data['Building'].unique()
            building_production = self.data.groupby('Building')['Qty'].sum()
            sorted_buildings = building_production.sort_values(ascending=False).index.tolist()

            lines = []
            for building in sorted_buildings:
                # 해당 제조동에 속하는 라인들 찾기
                building_lines = [line for line in self.data['Line'].unique() if line.startswith(building)]
                # 라인 이름 기준 오름차순 정렬
                sorted_building_lines = sorted(building_lines)
                lines.extend(sorted_building_lines)

            # 교대 시간 구분
            times = sorted(self.data['Time'].unique())
            shifts = {}
            for time in times:
                if int(time) % 2 == 1:
                    shifts[time] = "Day"
                else:
                    shifts[time] = "Night"

            # 라인별 교대 정보
            line_shifts = {}
            for line in lines:
                line_shifts[line] = ["Day", "Night"]

            # 행 헤더 생성
            row_headers = []
            for line in lines:
                for shift in ["Day", "Night"]:
                    row_headers.append(f"{line}_({shift})")

            # 클래스 변수에 저장
            self.row_headers = row_headers

            print(f"[헬퍼] 그리드 구조 준비 완료 - {len(lines)}개 라인, {len(row_headers)}개 행")
            return lines, line_shifts, row_headers

        except Exception as e:
            print(f"[헬퍼] 그리드 구조 준비 중 오류: {e}")
            return [], {}, []

    def _populate_grid_with_items(self):
        """그리드에 아이템들을 배치하는 헬퍼 메서드"""
        try:
            # 교대 시간 구분 재생성
            times = sorted(self.data['Time'].unique())
            shifts = {}
            for time in times:
                if int(time) % 2 == 1:
                    shifts[time] = "Day"
                else:
                    shifts[time] = "Night"

            # 데이터에서 아이템 생성하여 그리드에 배치
            item_count = 0
            for _, row_data in self.data.iterrows():
                if 'Line' not in row_data or 'Time' not in row_data:
                    continue

                line = row_data['Line']
                time = row_data['Time']
                shift = shifts[time]
                day_idx = (int(time) - 1) // 2

                if day_idx >= len(self.days):
                    continue

                row_key = f"{line}_({shift})"

                # Item 정보가 있으면 추출하여 저장
                if 'Item' in row_data and pd.notna(row_data['Item']):
                    item_info = str(row_data['Item'])

                    # Qty 정보가 있으면 수량 정보로 추가
                    if 'Qty' in row_data and pd.notna(row_data['Qty']):
                        item_info += f"    {row_data['Qty']}"

                    try:
                        # 그리드에 아이템 추가
                        row_idx = self.row_headers.index(row_key)
                        col_idx = day_idx

                        # 전체 행 데이터를 아이템 데이터(dict 형태)로 전달
                        item_full_data = row_data.to_dict()
                        new_item = self.grid_widget.addItemAt(row_idx, col_idx, item_info, item_full_data)

                        if new_item:
                            # 새 아이템을 all_items에 추가
                            self.all_items.append(new_item)
                            item_count += 1

                            # 상태 적용
                            self._apply_item_states(new_item, item_full_data)

                    except ValueError as e:
                        print(f"[헬퍼] 인덱스 찾기 오류: {e}")
                        continue

            print(f"[헬퍼] 그리드 아이템 배치 완료 - {item_count}개 아이템 생성")
            return item_count

        except Exception as e:
            print(f"[헬퍼] 그리드 아이템 배치 중 오류: {e}")
            return 0

    def _apply_item_states(self, new_item, item_data):
        """아이템에 상태 적용하는 헬퍼 메서드"""
        try:
            item_code = item_data.get('Item', '')

            # 사전할당 아이템인 경우
            if item_code in self.pre_assigned_items:
                new_item.set_pre_assigned_status(True)

            # 출하 실패 아이템인 경우
            if item_code in self.shipment_failure_items:
                failure_info = self.shipment_failure_items[item_code]
                new_item.set_shipment_failure(True, failure_info.get('reason', 'Unknown reason'))

            # 자재부족 아이템인 경우
            if hasattr(self, 'current_shortage_items') and item_code in self.current_shortage_items:
                shortage_info = self.current_shortage_items[item_code]
                new_item.set_shortage_status(True, shortage_info)

        except Exception as e:
            print(f"[헬퍼] 아이템 상태 적용 중 오류: {e}")

    def _backup_ui_state(self, preserve_search, preserve_filters):
        """UI 상태 백업 헬퍼 메서드"""
        backup_data = {
            'search_active': False,
            'search_text': "",
            'filter_states': {},
            'excel_filter_states': {},
            'scroll_position': None,
            'selected_item_id': None
        }

        if preserve_search and hasattr(self, 'search_widget'):
            backup_data['search_active'] = self.search_widget.is_search_active()
            backup_data['search_text'] = self.search_widget.get_search_text()

        if preserve_filters:
            backup_data['filter_states'] = self.current_filter_states.copy()
            backup_data['excel_filter_states'] = self.current_excel_filter_states.copy()

        # 선택된 아이템 ID 백업
        if self.current_selected_item and hasattr(self.current_selected_item, 'item_data'):
            backup_data['selected_item_id'] = self.current_selected_item.item_data.get('_id')

        # 스크롤 위치 백업
        if hasattr(self.grid_widget, 'scroll_area'):
            backup_data['scroll_position'] = {
                'horizontal': self.grid_widget.scroll_area.horizontalScrollBar().value(),
                'vertical': self.grid_widget.scroll_area.verticalScrollBar().value()
            }

        return backup_data

    def _restore_ui_state(self, backup_data, preserve_search, preserve_filters):
        """
        UI 상태 복원 헬퍼 메서드
        ✅ 수정: apply_standard_filters() → apply_all_filters() 호출
        """
        try:
            # 필터 상태 복원
            if preserve_filters:
                self.current_filter_states = backup_data['filter_states']
                self.current_excel_filter_states = backup_data['excel_filter_states']

            # 스크롤 위치 복원
            if backup_data['scroll_position'] and hasattr(self.grid_widget, 'scroll_area'):
                QTimer.singleShot(50, lambda: self._restore_scroll_position(backup_data['scroll_position']))

            # 검색 상태 복원
            if preserve_search and backup_data['search_active'] and backup_data['search_text']:
                self.search_widget.last_search_text = backup_data['search_text']
                self.search_widget.search_active = True
                self.search_widget.clear_button.setEnabled(True)

                print(f"[UI업데이트] 검색 상태 복원: '{backup_data['search_text']}'")
                QTimer.singleShot(100, lambda: self.search_items(backup_data['search_text']))

            # ✅ 수정: 필터 재적용 시 통합된 메서드 사용
            if preserve_filters and any(v for v in backup_data['filter_states'].values()):
                QTimer.singleShot(50, lambda: self.apply_all_filters())

            # 선택된 아이템 복원
            if backup_data['selected_item_id']:
                QTimer.singleShot(150, lambda: self._scroll_to_selected_item(backup_data['selected_item_id']))

        except Exception as e:
            print(f"[UI업데이트] 상태 복원 중 오류: {e}")

    def apply_legend_filters_only(self):
        """
        범례 필터만 적용 (상태선 업데이트)
        rebuild_grid_with_filtered_data에서 호출됨
        """
        try:
            if hasattr(self, 'current_filter_states'):
                self.update_status_lines_only(self.current_filter_states)
                print(f"[필터적용] 범례 필터만 적용 완료")
            else:
                print("[필터적용] current_filter_states가 없어 범례 필터 적용 스킵")
        except Exception as e:
            print(f"[필터적용] 범례 필터 적용 중 오류: {e}")
            import traceback
            traceback.print_exc()