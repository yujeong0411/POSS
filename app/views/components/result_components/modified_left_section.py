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
    def register_item(self, item) :
        if item not in self.all_items :
            self.all_items.append(item)

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
        if not hasattr(self, 'grid_widget') or not hasattr(self.grid_widget, 'containers'):
            return
            
        # 0. 필터 상태 캐싱
        excel_filter_active = any(not all(states.values()) for states in self.current_excel_filter_states.values())
        legend_filter_active = any(self.current_filter_states.values())
        search_active = self.search_widget.is_search_active()
        search_text = self.search_widget.get_search_text() if search_active else None
        
        # 아이템 상태 캐싱 및 배치 처리
        # 가시성 변경할 아이템, 상태선 변경할 아이템, 검색 하이라이트 변경할 아이템 목록화
        visibility_changes = []    # (아이템, 표시여부) 튜플 목록
        stateline_changes = []     # {아이템, 상태 딕셔너리} 목록
        highlight_changes = []     # (아이템, 하이라이트여부) 튜플 목록
        search_results = []        # 검색 결과 아이템 목록
        
        # 컨테이너별 가시성 변경 여부 추적
        affected_containers = set()
        
        # 배치 처리를 위해 한 번만 순회
        for row_containers in self.grid_widget.containers:
            for container in row_containers:
                container_changed = False
                
                for item in container.items:
                    # 엑셀 필터 적용 (라인/프로젝트)
                    should_show = True
                    if excel_filter_active:
                        should_show = self.should_show_item_excel_filter(item)
                    
                    # 가시성 변경 필요한 경우만 기록
                    if item.isVisible() != should_show:
                        visibility_changes.append((item, should_show))
                        container_changed = True
                    
                    # 상태선 변경 필요한지 확인 (범례 필터)
                    if legend_filter_active:
                        shortage_filter = self.current_filter_states.get('shortage', False)
                        shipment_filter = self.current_filter_states.get('shipment', False)
                        pre_assigned_filter = self.current_filter_states.get('pre_assigned', False)
                        
                        # 현재 상태
                        current_shortage = getattr(item, 'show_shortage_line', False)
                        current_shipment = getattr(item, 'show_shipment_line', False) 
                        current_pre_assigned = getattr(item, 'show_pre_assigned_line', False)
                        
                        # 새로운 상태
                        new_shortage = shortage_filter and getattr(item, 'is_shortage', False)
                        new_shipment = shipment_filter and getattr(item, 'is_shipment_failure', False)
                        new_pre_assigned = pre_assigned_filter and getattr(item, 'is_pre_assigned', False)
                        
                        # 상태가 변경된 경우만 기록
                        if (current_shortage != new_shortage or 
                            current_shipment != new_shipment or
                            current_pre_assigned != new_pre_assigned):
                            stateline_changes.append({
                                'item': item,
                                'shortage': new_shortage,
                                'shipment': new_shipment,
                                'pre_assigned': new_pre_assigned
                            })
                    
                    # 검색 기능 처리
                    if search_active:
                        is_match = search_text in str(item.item_data.get('Item', '')).lower() if hasattr(item, 'item_data') else False
                        
                        # 검색 결과에 추가
                        if is_match:
                            search_results.append(item)
                        
                        # 검색 하이라이트 상태 변경 필요한 경우
                        current_highlight = getattr(item, 'is_search_focused', False)
                        if current_highlight != is_match:
                            highlight_changes.append((item, is_match))
                
                # 컨테이너에 변경이 있으면 기록
                if container_changed:
                    affected_containers.add(container)
        
        # 일괄 처리 단계
        
        # 1. 가시성 변경 일괄 적용
        for item, should_show in visibility_changes:
            item.setVisible(should_show)
        
        # 2. 상태선 변경 일괄 적용
        for change in stateline_changes:
            item = change['item']
            if hasattr(item, 'show_shortage_line'):
                item.show_shortage_line = change['shortage']
            if hasattr(item, 'show_shipment_line'):
                item.show_shipment_line = change['shipment']
            if hasattr(item, 'show_pre_assigned_line'):
                item.show_pre_assigned_line = change['pre_assigned']
            # 상태선 업데이트
            item.update()
        
        # 3. 검색 하이라이트 일괄 적용
        for item, highlight in highlight_changes:
            if hasattr(item, 'set_search_focus'):
                item.set_search_focus(highlight)
        
        # 4. 검색 결과 업데이트
        if search_active:
            self.search_results = search_results
            
            if self.search_results:
                # 선택 위치 업데이트
                if self.current_result_index < 0 or self.current_result_index >= len(self.search_results):
                    self.current_result_index = 0
                self.update_result_navigation()
                
                # 선택된 검색 결과로 스크롤
                if 0 <= self.current_result_index < len(self.search_results):
                    self.select_current_result()
            else:
                # 검색 결과 없음 표시
                self.search_widget.set_result_status(0, 0)
                self.search_widget.show_result_navigation(True)
        
        # 5. 영향 받은 컨테이너만 크기 조정
        for container in affected_containers:
            container.adjustSize()

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
        if not hasattr(self, 'current_excel_filter_states') or not hasattr(item, 'item_data'):
            return True
        
        item_data = item.item_data
        
        # 라인 필터 체크 - Line 컬럼 사용
        if 'Line' in item_data:
            line = item_data['Line']

            if isinstance(line, (int, float)):
                line = str(int(line))
            else:
                line = str(line)
                
            if line in self.current_excel_filter_states['line'] and not self.current_excel_filter_states['line'][line]:
                return False
        
        # 프로젝트 필터 체크 - Project 컬럼 사용
        if 'Project' in item_data:
            project = item_data['Project']

            if pd.isna(project):  # nan 값 처리
                project = "N/A"
            else:
                project = str(project)
                
            if project in self.current_excel_filter_states['project'] and not self.current_excel_filter_states['project'][project]:
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
        데이터 로드 후 필터 데이터 업데이트
        그리드와 동일한 정렬 순서를 사용
        """
        if self.data is None:
            return

        # 그리드와 동일한 정렬 로직 적용
        try:
            # 제조동 정보 추출 (Line 이름의 첫 글자가 제조동)
            temp_data = self.data.copy()
            temp_data['Building'] = temp_data['Line'].str[0]

            # 제조동별 생산량 계산 (정렬 목적)
            building_production = temp_data.groupby('Building')['Qty'].sum()

            # 생산량 기준으로 제조동 정렬 (내림차순)
            sorted_buildings = building_production.sort_values(ascending=False).index.tolist()

            # 모든 고유 라인 가져오기
            all_lines = temp_data['Line'].unique()

            # 제조동별로 정렬된 라인 목록 생성 (그리드와 동일한 로직)
            lines = []
            for building in sorted_buildings:
                # 해당 제조동에 속하는 라인들 찾기
                building_lines = [line for line in all_lines if line.startswith(building)]

                # 라인 이름 기준 오름차순 정렬 (그리드와 동일)
                sorted_building_lines = sorted(building_lines)

                # 정렬된 라인 추가
                lines.extend(sorted_building_lines)

            # 혹시 누락된 라인이 있으면 맨 뒤에 추가
            remaining_lines = [line for line in all_lines if line not in lines]
            if remaining_lines:
                lines.extend(sorted(remaining_lines))

        except Exception as e:
            print(f"라인 정렬 중 오류 발생: {e}")
            # 오류 발생 시 기본 정렬 사용
            lines = sorted(self.data['Line'].unique()) if 'Line' in self.data.columns else []

        # 프로젝트 목록 추출 - Project 컬럼에서 추출
        projects = []
        if 'Project' in self.data.columns:
            # nan 값 처리 및 문자열 변환
            projects = [str(project) if not pd.isna(project) else "N/A" for project in self.data['Project']]
            projects = sorted(set(projects))  # 중복 제거하고 정렬

        # 필터 위젯에 데이터 설정
        self.filter_widget.set_filter_data(lines, projects)

    """
    검색 기능 실행
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

        # 아이템 검색 및 하이라이트 처리
        visible_count = 0
        invalid_items = []

        # 모든 아이템에 대해 검색 적용
        for item in self.all_items[:]:
            try:
                is_match = self.apply_search_to_item(item, search_text)
                if is_match:
                    visible_count += 1
                    self.search_results.append(item)
            except RuntimeError:
                invalid_items.append(item)
            except Exception as e:
                print(f"검색 중 오류 발생: {e}")
        
        # 유효하지 않은 아이템 목록에서 제거
        for item in invalid_items:
            if item in self.all_items:
                self.all_items.remove(item)

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
        else:
            # 검색 결과 없음 표시
            self.search_widget.set_result_status(0, 0)

    """
    아이템에 검색 조건 적용
    """
    def apply_search_to_item(self, item, search_text):
        try :
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
            if hasattr(item, 'set_search_focus'):
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
                    
            # 현재 아이템 저장 및 스크롤
            self._scroll_to_current_result()
        except Exception as e:
            print(f'항목 선택 오류: {str(e)}')

    """
    검색 초기화 (SearchWidget의 searchCleared 시그널에 연결)
    """
    def clear_search(self):
        try:
            # 모든 아이템의 검색 포커스 해제
            for item in self.all_items:
                if hasattr(item, 'set_search_focus'):
                    item.set_search_focus(False)
                if hasattr(item, 'set_search_current'):
                    item.set_search_current(False)
            # 선택 상태 초기화
            if hasattr(self.grid_widget, 'clear_all_selections'):
                self.grid_widget.clear_all_selections()
            self.current_selected_item = None
            self.current_selected_container = None
        except Exception as e:
            print(f"선택 초기화 오류: {e}")
        
        # 검색 상태 초기화
        self.search_results = []
        self.current_result_index = -1
        
        # 필터 적용
        self.apply_all_filters()
    """
    이전 검색 결과로 이동 (SearchWidget의 prevResultRequested 시그널에 연결)
    """
    def go_to_prev_result(self):
        if not self.search_results or self.current_result_index <= 0:
            return
        
        try:
            # 인덱스 변경 전에 현재 아이템 정보 저장
            old_index = self.current_result_index
            old_item = self.search_results[old_index]
            
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
            old_item = self.search_results[old_index]
            
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
        
        # 새 아이템 강조
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
        
        # 스크롤
        if hasattr(self.grid_widget, 'ensure_item_visible'):
            self.grid_widget.ensure_item_visible(container, current_item)
                
        # 데이터 변경 알림
        df = self.extract_dataframe()
        self.viewDataChanged.emit(df)

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
    def search_items_without_clear(self):
        search_text = self.search_widget.get_search_text()
        if not search_text:
            return
        
        # 현재 선택된 아이템 저장
        current_selected_item = self.current_selected_item
        
        # 검색 결과 업데이트
        self.search_results = []
        invalid_items = []
        
        # 검색 조건에 맞는 아이템만 표시 및 결과에 추가
        for item in self.all_items[:]:
            try:
                is_match = self.apply_search_to_item(item, search_text)
                if is_match:
                    self.search_results.append(item)
            except RuntimeError:
                invalid_items.append(item)
            except Exception as e:
                print(f"검색 중 오류 발생: {e}")
        
        # 잘못된 아이템 제거
        for item in invalid_items:
            if item in self.all_items:
                self.all_items.remove(item)
        
        # 모든 필터 적용 (검색 결과 포함)
        self.apply_all_filters()
        
        # 검색 결과 UI 업데이트
        self.search_widget.show_result_navigation(True)
        
        # 검색 결과가 있으면 선택 및 네비게이션 업데이트
        if self.search_results:
            # 이전에 선택된 아이템이 검색 결과에 있으면 선택 유지
            if current_selected_item in self.search_results:
                self.current_result_index = self.search_results.index(current_selected_item)
            else:
                self.current_result_index = 0
            
            self.select_current_result()
            self.update_result_navigation()
        else:
            # 검색 결과 없음 표시
            self.search_widget.set_result_status(0, 0)

    """
    아이템 데이터가 변경되면 호출되는 함수
    """
    def on_item_data_changed(self, item, new_data, changed_fields=None):
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
        if hasattr(self, 'controller') and self.controller:
            print("MVC 컨트롤러로 처리 - 시그널 발생")
            self.itemModified.emit(item, new_data, changed_fields)
            
            # 필터 및 검색 상태 즉시 재적용
            self.apply_all_filters()
            
            # 검색이 활성화된 경우 검색 UI 즉시 업데이트
            if self.search_widget.is_search_active():
                self.search_items_without_clear()
                
            # 출하 분석도 즉시 업데이트
            self.trigger_shipment_analysis()
            return
    
    """데이터 변경 시 출하 분석을 트리거합니다"""
    def trigger_shipment_analysis(self):
        if hasattr(self, 'parent_page') and self.parent_page:
            if hasattr(self.parent_page, 'analyze_shipment_with_current_data'):
                current_data = self.extract_dataframe()
                # 1. 출하 분석 요청
                if current_data is not None and not current_data.empty:
                    print("왼쪽 테이블 변경 감지 - 출하 분석 실행")
                    self.parent_page.analyze_shipment_with_current_data(current_data)
                # 2. 분산 배치 분석 요청 - SplitView 업데이트
                if hasattr(self.parent_page, 'update_split_view_analysis'):
                    print("왼쪽 테이블 변경 감지 - 분산 배치 분석 실행")
                    self.parent_page.update_split_view_analysis(current_data)

    """
    위치 변경 처리 로직 분리
    """
    def _handle_position_change(self, item, new_data, changed_fields, old_data):
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
            self._process_position_change(item, new_data, changed_fields, old_data)
        else:
            # 데이터만 업데이트
            if hasattr(item, 'update_item_data'):
                success, error_message = item.update_item_data(new_data)
                if not success:
                    print(f"아이템 데이터 업데이트 실패: {error_message}")
                    return

            self.mark_as_modified()
            self.itemModified.emit(item, new_data)

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
        self.controller = controller
        print("MVC 컨트롤러가 설정되었습니다")

        # 모델 변경 시그널 연결
        if self.controller and hasattr(self.controller.model, 'modelDataChanged'):
            self.controller.model.modelDataChanged.connect(self.update_from_model)
            print("ModifiedLeftSection: 모델 변경 시그널 연결 완료")

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
        # 데이터가 없으면 건너뜀
        if self.data is None or self.data.empty:
            return
            
        # 결과 페이지 참조 확인
        result_page = self.parent_page
        if not result_page:
            return
            
        try:
            # 탭 위젯들 초기화 요청
            if hasattr(result_page, 'preload_tab_analyses'):
                result_page.preload_tab_analyses(self.data)
                
            # 범례에도 필터 상태 업데이트 알림
            if hasattr(self, 'legend_widget'):
                # 현재 필터 상태 가져오기
                current_states = self.legend_widget.filter_states
                
                # 강제로 필터 변경 이벤트 재발생
                self.on_filter_changed_dict(current_states)
        except Exception as e:
            print(f"사전 분석 초기화 중 오류: {e}")

    """범례 위젯에서 필터가 변경될 때 호출"""
    def on_filter_changed_dict(self, filter_states):
        # 현재 필터 상태 업데이트
        if self.current_filter_states == filter_states:
            return
        
        # 상태선 업데이트만 수행하는 경량 버전 적용
        self.current_filter_states = filter_states.copy()
        self.update_status_lines_only(filter_states)
        
        # 필터 활성화 시 관련 분석 트리거
        for status_type, is_checked in filter_states.items():
            if is_checked and not self.current_filter_states.get(status_type, False):
                # 새로 활성화된 필터에 대한 분석 요청
                self.on_filter_activation_requested(status_type)

    """
    Line과 Time으로 데이터 그룹화하고 개별 아이템으로 표시
    """

    def update_ui_with_signals(self):
        if self.data is None or 'Line' not in self.data.columns or 'Time' not in self.data.columns:
            EnhancedMessageBox.show_validation_error(self, "Grouping Failed",
                                                     "Data is missing or does not contain 'Line' or 'Time' columns.\nPlease load data with the required columns.")
            return

        try:
            # 제조동 정보 추출 (Line 이름의 첫 글자가 제조동)
            self.data['Building'] = self.data['Line'].str[0]  # 라인명의 첫 글자를 제조동으로 사용

            # 제조동별 생산량 계산 (정렬 목적)
            building_production = self.data.groupby('Building')['Qty'].sum()

            # 생산량 기준으로 제조동 정렬 (내림차순)
            sorted_buildings = building_production.sort_values(ascending=False).index.tolist()

            # ---- 데이터프레임 정렬을 위한 전처리 ----
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

            # 5. 원본 데이터도 정렬된 상태로 저장
            self.original_data = self.data.copy()

            # Line과 Time 값 추출
            all_lines = self.data['Line'].unique()
            times = sorted(self.data['Time'].unique())

            # 제조동 별로 정렬된 라인 목록 생성 (각 제조동 내에서는 라인 이름 기준 오름차순으로 정렬)
            lines = []
            for building in sorted_buildings:
                # 해당 제조동에 속하는 라인들 찾기
                building_lines = [line for line in all_lines if line.startswith(building)]

                # 라인 이름 기준 오름차순 정렬
                sorted_building_lines = sorted(building_lines)

                # 정렬된 라인 추가
                lines.extend(sorted_building_lines)

            # 교대 시간 구분
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

            # 행 헤더
            self.row_headers = []
            for line in lines:
                for shift in ["Day", "Night"]:
                    self.row_headers.append(f"{line}_({shift})")

            self.grid_widget.setupGrid(
                rows=len(self.row_headers),
                columns=len(self.days),
                row_headers=self.row_headers,
                column_headers=self.days,
                line_shifts=line_shifts
            )

            # 데이터를 행/열별로 그룹화
            grouped_items = {}  # 키: (row_idx, col_idx), 값: 아이템 목록

            # 첫 번째 단계: 아이템을 행과 열 기준으로 그룹화
            for _, row_data in self.data.iterrows():
                if 'Line' not in row_data or 'Time' not in row_data or 'Item' not in row_data:
                    continue

                line = row_data['Line']
                time = row_data['Time']
                shift = shifts[time]
                day_idx = (int(time) - 1) // 2

                if day_idx >= len(self.days):
                    continue

                row_key = f"{line}_({shift})"

                try:
                    row_idx = self.row_headers.index(row_key)
                    col_idx = day_idx

                    # 키 생성 및 데이터 저장
                    grid_key = (row_idx, col_idx)
                    if grid_key not in grouped_items:
                        grouped_items[grid_key] = []

                    # 아이템 데이터 추가
                    item_data = row_data.to_dict()
                    qty = item_data.get('Qty', 0)
                    if pd.isna(qty):
                        qty = 0

                    # 수량을 정수로 변환하여 저장
                    item_data['Qty'] = int(float(qty)) if isinstance(qty, (int, float, str)) else 0
                    grouped_items[grid_key].append(item_data)
                except ValueError as e:
                    print(f"인덱스 찾기 오류: {e}")
                    continue

            # 두 번째 단계: 아이템을 그리드에 추가
            for (row_idx, col_idx), items in grouped_items.items():
                for item_data in items:
                    item_info = str(item_data.get('Item', ''))

                    # Qty 표시
                    qty = item_data.get('Qty', 0)
                    if pd.notna(qty) and qty != 0:
                        item_info += f"    {qty}"

                    # 아이템 추가
                    new_item = self.grid_widget.addItemAt(row_idx, col_idx, item_info, item_data)

                    if new_item:
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

            # 그룹화된 데이터 저장 (기존 코드 유지)
            if 'Day' in self.data.columns:
                self.grouped_data = self.data.groupby(['Line', 'Day', 'Time']).first().reset_index()
            else:
                self.grouped_data = self.data.groupby(['Line', 'Time']).first().reset_index()

            # 데이터 변경 신호 발생
            df = self.extract_dataframe()
            self.viewDataChanged.emit(df)

            # *** 중요: 필터 데이터를 그리드 설정 직후에 즉시 업데이트 ***
            # 정렬된 라인 순서를 직접 전달
            projects = []
            if 'Project' in self.data.columns:
                projects = [str(project) if not pd.isna(project) else "N/A" for project in self.data['Project']]
                projects = sorted(set(projects))

            # 디버그 출력
            print(f"DEBUG: 그리드에서 정렬된 라인 순서: {lines}")
            print(f"DEBUG: 필터 위젯에 전달할 라인 순서: {lines}")

            # 필터 위젯에 정렬된 라인 순서 직접 설정 - 강제로 호출
            if hasattr(self, 'filter_widget') and self.filter_widget:
                print("DEBUG: 필터 위젯 존재 - 데이터 설정 중...")
                self.filter_widget.set_filter_data(lines, projects)
                print("DEBUG: 필터 위젯 데이터 설정 완료")
            else:
                print("DEBUG: 필터 위젯이 없습니다!")

            # 추가로 직접 호출도 해보기
            try:
                self.update_filter_data()
                print("DEBUG: update_filter_data 직접 호출 완료")
            except Exception as e:
                print(f"DEBUG: update_filter_data 호출 중 오류: {e}")

        except Exception as e:
            # 에러 메시지 표시
            print(f"그룹핑 에러: {e}")
            import traceback
            traceback.print_exc()
            EnhancedMessageBox.show_validation_error(self, "Grouping Error",
                                                     f"An error occurred during data grouping.\n{str(e)}")

    """
    외부에서 데이터 설정
    """
    def set_data_from_external(self, new_data):
        self.data = self._normalize_data_types(new_data.copy())
        self.original_data = self.data.copy()
        self.update_table_from_data()

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
        # 자재 부족 정보 저장
        self.current_shortage_items = shortage_items
        
        # 시프트 기반으로 자재 부족 상태 적용
        self.update_left_widget_shortage_status(shortage_items)

    """
    왼쪽 위젯의 아이템들에 자재 부족 상태 적용

    Args:
        shortage_dict: {item_code: [{shift: shift_num, material: material_code, shortage: shortage_amt}]}
    """
    def update_left_widget_shortage_status(self, shortage_dict):
        if not hasattr(self, 'grid_widget') or not hasattr(self.grid_widget, 'containers'):
            return
        
        print(f"자재 부족 상태 적용 시작: {len(shortage_dict)}개 아이템")
        status_applied_count = 0
        
        # 그리드의 모든 컨테이너 순회
        for row_containers in self.grid_widget.containers:
            for container in row_containers:
                # 각 컨테이너의 아이템들 순회
                for item in container.items:
                    if hasattr(item, 'item_data') and item.item_data and 'Item' in item.item_data:
                        item_code = item.item_data['Item']
                        item_time = item.item_data.get('Time')  # 시프트(Time) 정보 가져오기
                        
                        # 해당 아이템이 자재 부족 목록에 있는지 확인
                        if item_code in shortage_dict:
                            # 시프트별 부족 정보 검사
                            shortages_for_item = shortage_dict[item_code]
                            matching_shortages = []
                            
                            for shortage in shortages_for_item:
                                shortage_shift = shortage.get('shift')
                                
                                # 시프트가 일치하면 부족 정보 저장
                                if shortage_shift and item_time and int(shortage_shift) == int(item_time):
                                    matching_shortages.append(shortage)
                            
                            # 일치하는 시프트의 부족 정보가 있으면 부족 상태로 설정
                            if matching_shortages:
                                item.set_shortage_status(True, matching_shortages)
                                status_applied_count += 1
                            else:
                                item.set_shortage_status(False)
                        else:
                            # 부족 목록에 없는 경우 부족 상태 해제
                            item.set_shortage_status(False)
        
        print(f"자재 부족 상태 적용 완료: {status_applied_count}개 아이템에 적용됨")

    """
    모든 상태 정보를 현재 아이템들에 적용
    """
    def apply_all_states(self):
        if not hasattr(self, 'grid_widget') or not hasattr(self.grid_widget, 'containers'):
            return
        
        for row_containers in self.grid_widget.containers:
            for container in row_containers:
                for item in container.items:
                    if hasattr(item, 'item_data') and item.item_data and 'Item' in item.item_data:
                        item_code = item.item_data['Item']
                        item_time = item.item_data.get('Time')

                        # 사전할당 상태
                        if item_code in self.pre_assigned_items:
                            item.set_pre_assigned_status(True)

                        # 출하 실패 상태
                        if item_code in self.shipment_failure_items:
                            failure_info = self.shipment_failure_items[item_code]
                            item.set_shipment_failure(True, failure_info.get('reason', 'Unknown'))

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
                            else:
                                item.set_shortage_status(False)

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
        if not hasattr(self, 'grid_widget') or not hasattr(self.grid_widget, 'containers'):
            return
        
        # 변경된 아이템 추적
        changed_items = []
        
        # 필터 상태 캐싱
        shortage_filter = filter_states.get('shortage', False)
        shipment_filter = filter_states.get('shipment', False)
        pre_assigned_filter = filter_states.get('pre_assigned', False)
        
        # 아이템 순회하며 상태선 업데이트
        for row_containers in self.grid_widget.containers:
            for container in row_containers:
                for item in container.items:
                    changed = False
                    
                    # 각 상태선 확인 및 변경
                    if hasattr(item, 'show_shortage_line'):
                        new_state = shortage_filter and item.is_shortage
                        if item.show_shortage_line != new_state:
                            item.show_shortage_line = new_state
                            changed = True
                            
                    if hasattr(item, 'show_shipment_line'):
                        new_state = shipment_filter and item.is_shipment_failure
                        if item.show_shipment_line != new_state:
                            item.show_shipment_line = new_state
                            changed = True
                            
                    if hasattr(item, 'show_pre_assigned_line'):
                        new_state = pre_assigned_filter and item.is_pre_assigned
                        if item.show_pre_assigned_line != new_state:
                            item.show_pre_assigned_line = new_state
                            changed = True
                    
                    # 변경된 아이템만 업데이트 대상에 추가
                    if changed:
                        changed_items.append(item)
        
        # 변경된 아이템만 일괄 업데이트
        for item in changed_items:
            item.update()
            
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
        # MVC 컨트롤러 확인
        has_controller = hasattr(self, 'controller') and self.controller is not None
        
        # MVC 컨트롤러가 있으면 컨트롤러에서 처리
        if has_controller:
            # 컨트롤러에 연결이 제대로 되어 있는지 확인
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
        print("ModifiedLeftSection: update_from_model 호출")

        current_selected_item_id = None
        if self.current_selected_item and hasattr(self.current_selected_item, 'item_data'):
            current_selected_item_id = self.current_selected_item.item_data.get('_id')

        # ... UI 업데이트 ...

        # 선택된 아이템으로 스크롤 복원
        if current_selected_item_id:
            QTimer.singleShot(100, lambda: self._scroll_to_selected_item(current_selected_item_id))

        # 현재 검색 및 필터 상태 백업
        current_search_active = self.search_widget.is_search_active()
        current_search_text = self.search_widget.get_search_text()
        current_filter_states = self.current_filter_states.copy()
        current_excel_filter_states = self.current_excel_filter_states.copy()

        # 현재 스크롤 위치 저장
        current_scroll_position = None
        if hasattr(self.grid_widget, 'scroll_area'):
            current_scroll_position = {
                'horizontal': self.grid_widget.scroll_area.horizontalScrollBar().value(),
                'vertical': self.grid_widget.scroll_area.verticalScrollBar().value()
            }
            print(f"현재 스크롤 위치 저장: {current_scroll_position}")

        # 매개변수가 없을 때 컨트롤러에서 데이터 가져오기
        if model_df is None:
            if hasattr(self, 'controller') and self.controller:
                model_df = self.controller.model.get_dataframe()
                print("컨트롤러에서 데이터 가져옴")

        if model_df is None:
            print("데이터가 없습니다.")
            return

        # 타입 변환을 한 번에 처리
        self.data = self._normalize_data_types(model_df.copy())

        # UI 업데이트 시작
        if self.data is None or 'Line' not in self.data.columns or 'Time' not in self.data.columns:
            print("데이터가 없거나 필수 컬럼이 없음")
            return

        try:
            # 정렬 로직 적용 (update_ui_with_signals와 동일한 로직)
            # 제조동 정보 추출 (Line 이름의 첫 글자가 제조동)
            self.data['Building'] = self.data['Line'].str[0]  # 라인명의 첫 글자를 제조동으로 사용

            # 제조동별 생산량 계산 (정렬 목적)
            building_production = self.data.groupby('Building')['Qty'].sum()

            # 생산량 기준으로 제조동 정렬 (내림차순)
            sorted_buildings = building_production.sort_values(ascending=False).index.tolist()

            # ---- 데이터프레임 정렬을 위한 전처리 ----
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

            # 기존 아이템 모두 지우기
            self.clear_all_items()

            # Line과 Time 값 추출
            lines = []
            for building in sorted_buildings:
                # 해당 제조동에 속하는 라인들 찾기
                building_lines = [line for line in self.data['Line'].unique() if line.startswith(building)]
                # 라인 이름 기준 오름차순 정렬
                sorted_building_lines = sorted(building_lines)
                # 정렬된 라인 추가
                lines.extend(sorted_building_lines)

            times = sorted(self.data['Time'].unique())

            # 교대 시간 구분
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

            # 행 헤더
            self.row_headers = []
            for line in lines:
                for shift in ["Day", "Night"]:
                    self.row_headers.append(f"{line}_({shift})")

            # 그리드 설정
            self.grid_widget.setupGrid(
                rows=len(self.row_headers),
                columns=len(self.days),
                row_headers=self.row_headers,
                column_headers=self.days,
                line_shifts=line_shifts
            )

            # 데이터에서 아이템 생성하여 그리드에 배치
            for _, row_data in self.data.iterrows():
                if 'Line' not in row_data or 'Time' not in row_data:
                    continue

                line = row_data['Line']
                time = row_data['Time']
                shift = shifts[time]
                day_idx = (int(time) - 1) // 2

                if day_idx >= len(self.days):
                    continue

                day = self.days[day_idx]
                row_key = f"{line}_({shift})"

                # Item 정보가 있으면 추출하여 저장
                if 'Item' in row_data and pd.notna(row_data['Item']):
                    item_info = str(row_data['Item'])

                    # MFG 정보가 있으면 수량 정보로 추가
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
                            item_code = item_full_data.get('Item', '')

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

                    except ValueError as e:
                        print(f"인덱스 찾기 오류: {e}")

            # 스크롤 위치 복원
            if current_scroll_position and hasattr(self.grid_widget, 'scroll_area'):
                QTimer.singleShot(50, lambda: self._restore_scroll_position(current_scroll_position))

            # 저장했던 필터 및 검색 상태 복원
            self.current_filter_states = current_filter_states
            self.current_excel_filter_states = current_excel_filter_states

            # 필터 상태 즉시 재적용
            if any(v for k, v in self.current_filter_states.items()):
                self.apply_all_filters()
                
            # 검색이 활성화되었던 경우 검색 상태 복원
            if current_search_active and current_search_text:
                # SearchWidget 상태 복원
                self.search_widget.last_search_text = current_search_text
                self.search_widget.search_active = True
                self.search_widget.clear_button.setEnabled(True)
                
                # 검색 실행
                self.search_items(current_search_text)

            # 출하 분석도 즉시 업데이트
            self.trigger_shipment_analysis()

        except Exception as e:
            print(f"UI 업데이트 오류: {e}")
            import traceback
            traceback.print_exc()

    """
    복사된 아이템 처리
    """
    def on_item_copied(self, item, data):
        # 아이템 등록
        self.register_item(item)

        # 데이터 처리는 제거 - 이미 컨트롤러에서 처리함
        # MVC 패턴에서는 뷰는 UI 렌더링만 담당, 데이터 처리는 컨트롤러에서
        
        # 컨트롤러가 없는 경우에만 직접 처리
        if not hasattr(self, 'controller') or not self.controller:
            # 컨트롤러가 없는 경우 기본 처리 - 레거시 지원
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