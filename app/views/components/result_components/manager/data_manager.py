from PyQt5.QtCore import QObject, QTimer
import pandas as pd
from app.utils.item_key_manager import ItemKeyManager

"""
데이터 관련 로직 담당
"""
class DataManager(QObject):
    def __init__(self, left_section):
        super().__init__()
        self.left_section = left_section
        
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
        if hasattr(self.left_section, 'controller') and self.left_section.controller:
            print("MVC 컨트롤러로 처리 - 시그널 발생")
            self.left_section.itemModified.emit(item, new_data, changed_fields)

            # *** 핵심: 모든 후처리를 즉시 실행 - 지연 없음 ***
            self._trigger_analysis()
            return
        
    """
    전체 데이터 새로고침 
    - ResultPage의 on_data_changed 활용
    """
    def trigger_full_data_refresh(self):
        current_data = self.left_section.extract_dataframe()
        
        # ResultPage의 on_data_changed 호출하여 전체 UI 업데이트
        if (hasattr(self.left_section, 'parent_page') and 
            self.left_section.parent_page and 
            hasattr(self.left_section.parent_page, 'on_data_changed')):
            
            print("DataManager: ResultPage.on_data_changed 호출")
            self.left_section.parent_page.on_data_changed(current_data)
        
    def _trigger_analysis(self):
        if hasattr(self.left_section, 'parent_page') and self.left_section.parent_page:
            if hasattr(self.left_section.parent_page, 'analyze_shipment_with_current_data'):
                current_data = self.left_section.extract_dataframe()
                # 1. 출하 분석 요청
                if current_data is not None and not current_data.empty:
                    print("DataManager: 출하 분석 실행")
                    self.left_section.parent_page.analyze_shipment_with_current_data(current_data)
                # 2. 분산 배치 분석 요청 - SplitView 업데이트
                if hasattr(self.left_section.parent_page, 'update_split_view_analysis'):
                    print("DataManager: 분산 배치 분석 실행")
                    self.left_section.parent_page.update_split_view_analysis(current_data)

    """
    엑셀 파일에서 데이터를 읽어와 테이블 업데이트
    """
    def update_table_from_data(self):
        if self.left_section.data is None:
            return

        self.left_section.update_ui_with_signals()

        # 데이터 변경 신호 발생
        df = self.left_section.extract_dataframe()
        self.left_section.viewDataChanged.emit(df)

        self.preload_analyses()

        self._trigger_analysis()

    """
    데이터 로드 후 사전 분석 실행
    """
    def preload_analyses(self):
        # 데이터가 없으면 건너뜀
        if self.left_section.data is None or self.left_section.data.empty:
            return
            
        # 결과 페이지 참조 확인
        result_page = self.left_section.parent_page
        if not result_page:
            return
            
        try:
            # 탭 위젯들 초기화 요청
            if hasattr(result_page, 'preload_tab_analyses'):
                result_page.preload_tab_analyses(self.left_section.data)
                
            # 범례에도 필터 상태 업데이트 알림
            if hasattr(self.left_section, 'legend_widget'):
                # 현재 필터 상태 가져오기
                current_states = self.left_section.legend_widget.filter_states
                
                # 강제로 필터 변경 이벤트 재발생
                self.left_section.on_filter_changed_dict(current_states)
        except Exception as e:
            print(f"사전 분석 초기화 중 오류: {e}")
    

    def handle_filter_data_update(self):
        """필터 데이터 업데이트 (Left Section 전용)"""
        self.left_section.update_filter_data()

    def register_item(self, item):
        """새로 생성된 아이템 등록"""
        if item not in self.left_section.all_items:
            self.left_section.all_items.append(item)

            # 검색이 활성화되어 있으면 해당 아이템에 검색 적용
            if self.left_section.search_widget.is_search_active():
                search_text = self.left_section.search_widget.get_search_text()
                if search_text:
                    self.apply_search_to_item(item, search_text)
                    

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
                if item in self.left_section.all_items:
                    self.left_section.all_items.remove(item)
                return False

            item_code = str(item.item_data.get('Item', '')).lower()
            is_match = search_text in item_code

            if hasattr(item, 'set_search_focus'):
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
    아이템 삭제 처리 메서드 (ItemContainer에서 발생한 삭제를 처리)
    """
    def on_item_removed(self, item_or_id):
        # MVC 컨트롤러 확인
        has_controller = hasattr(self.left_section, 'controller') and self.left_section.controller is not None
        
        # MVC 컨트롤러가 있으면 컨트롤러에서 처리
        if has_controller:
            # 컨트롤러에 연결이 제대로 되어 있는지 확인
            if hasattr(self.left_section.controller, 'on_item_deleted'):
                self.left_section.controller.on_item_deleted(item_or_id)
                self._trigger_analysis()
                return
            else:
                print("DEBUG: 컨트롤러에 on_item_deleted 메서드가 없음")
        
        # 컨트롤러가 없거나 처리하지 않은 경우 기존 로직 사용
        if self.left_section.data is None:
            print("DEBUG: 데이터가 없음")
            return
        
        # item_or_id가 문자열(ID)인 경우
        if isinstance(item_or_id, str):
            item_id = item_or_id
            print(f"DEBUG: ID로 삭제: {item_id}")
            mask = ItemKeyManager.create_mask_by_id(self.left_section.data, item_id)
            if mask.any():
                self.left_section.data = self.left_section.data[~mask].reset_index(drop=True)
                df = self.left_section.extract_dataframe()
                self.left_section.viewDataChanged.emit(df)
                self.left_section.mark_as_modified()

                self._trigger_analysis()
            else:
                print(f"DEBUG: ID {item_id}로 아이템을 찾을 수 없음")
            return
        
        # item_or_id가 아이템 객체인 경우
        if hasattr(item_or_id, 'item_data') and item_or_id.item_data:
            # ID가 있으면 ID로 찾기
            item_id = ItemKeyManager.extract_item_id(item_or_id)
            if item_id:
                print(f"DEBUG: 아이템 객체의 ID로 삭제: {item_id}")
                mask = ItemKeyManager.create_mask_by_id(self.left_section.data, item_id)
                if mask.any():
                    self.left_section.data = self.left_section.data[~mask].reset_index(drop=True)
                    df = self.left_section.extract_dataframe()
                    self.left_section.viewDataChanged.emit(df)
                    self.left_section.mark_as_modified()
                    return
            
            # ID가 없으면 Line/Time/Item으로 찾기
            line, time, item_code = ItemKeyManager.get_item_from_data(item_or_id.item_data)
            if line is not None and time is not None and item_code is not None:
                print(f"DEBUG: Line/Time/Item으로 삭제: {item_code} @ {line}-{time}")
                mask = ItemKeyManager.create_mask_for_item(self.left_section.data, line, time, item_code)
                if mask.any():
                    self.left_section.data = self.left_section.data[~mask].reset_index(drop=True)
                    df = self.left_section.extract_dataframe()
                    self.left_section.viewDataChanged.emit(df)
                    self.left_section.mark_as_modified()
                else:
                    print(f"DEBUG: Line/Time/Item으로 아이템을 찾을 수 없음")
        else:
            print("DEBUG: 유효하지 않은 아이템 객체")

        # 처리 완료 후 출하 분석 업데이트
        df = self.left_section.extract_dataframe()
        self.left_section.viewDataChanged.emit(df)
        self.left_section.mark_as_modified()
        
        # 출하 분석 업데이트 요청
        self._trigger_analysis()

    """
    복사된 아이템 처리
    """
    def on_item_copied(self, item, data):
        # 아이템 등록
        self.register_item(item)

        # 데이터 처리는 제거 - 이미 컨트롤러에서 처리함
        # MVC 패턴에서는 뷰는 UI 렌더링만 담당, 데이터 처리는 컨트롤러에서
        
        # 컨트롤러가 없는 경우에만 직접 처리
        if not hasattr(self.left_section, 'controller') or not self.left_section.controller:
            # 컨트롤러가 없는 경우 기본 처리 - 레거시 지원
            df = self.left_section.extract_dataframe()
            self.left_section.viewDataChanged.emit(df)

            self._trigger_analysis()

    """
    데이터가 수정되었음을 표시하는 메서드
    """
    def mark_as_modified(self):
        print("[DEBUG] mark_as_modified 호출됨 - 리셋 버튼 활성화")
        self.left_section.reset_button.setEnabled(True)

    """
    외부에서 데이터 설정
    """
    def set_data_from_external(self, new_data):
        self.left_section.data = self.left_section._normalize_data_types(new_data.copy())
        self.left_section.original_data = self.left_section.data.copy()
        self.left_section.update_table_from_data()

    """
    모델로부터 UI 업데이트 - 이벤트 발생시키지 않음
    """
    def update_from_model(self, model_df=None):
        print("ModifiedLeftSection: update_from_model 호출")

        current_selected_item_id = None
        if self.left_section.current_selected_item and hasattr(self.left_section.current_selected_item, 'item_data'):
            current_selected_item_id = self.left_section.current_selected_item.item_data.get('_id')

        # ... UI 업데이트 ...

        # 선택된 아이템으로 스크롤 복원
        if current_selected_item_id:
            QTimer.singleShot(100, lambda: self.left_section._scroll_to_selected_item(current_selected_item_id))

        # 현재 검색 및 필터 상태 백업
        current_search_active = self.left_section.search_widget.is_search_active()
        current_search_text = self.left_section.search_widget.get_search_text()
        current_filter_states = self.left_section.current_filter_states.copy()
        current_excel_filter_states = self.left_section.current_excel_filter_states.copy()

        # 현재 스크롤 위치 저장
        current_scroll_position = None
        if hasattr(self.left_section.grid_widget, 'scroll_area'):
            current_scroll_position = {
                'horizontal': self.left_section.grid_widget.scroll_area.horizontalScrollBar().value(),
                'vertical': self.left_section.grid_widget.scroll_area.verticalScrollBar().value()
            }
            print(f"현재 스크롤 위치 저장: {current_scroll_position}")

        # 매개변수가 없을 때 컨트롤러에서 데이터 가져오기
        if model_df is None:
            if hasattr(self.left_section, 'controller') and self.left_section.controller:
                model_df = self.left_section.controller.model.get_dataframe()
                print("컨트롤러에서 데이터 가져옴")

        if model_df is None:
            print("데이터가 없습니다.")
            return

        # 타입 변환을 한 번에 처리
        self.left_section.data = self.left_section._normalize_data_types(model_df.copy())

        # UI 업데이트 시작
        if self.left_section.data is None or 'Line' not in self.left_section.data.columns or 'Time' not in self.left_section.data.columns:
            print("데이터가 없거나 필수 컬럼이 없음")
            return

        try:
            # 정렬 로직 적용 (update_ui_with_signals와 동일한 로직)
            # 제조동 정보 추출 (Line 이름의 첫 글자가 제조동)
            self.left_section.data['Building'] = self.left_section.data['Line'].str[0]  # 라인명의 첫 글자를 제조동으로 사용

            # 제조동별 생산량 계산 (정렬 목적)
            building_production = self.left_section.data.groupby('Building')['Qty'].sum()

            # 생산량 기준으로 제조동 정렬 (내림차순)
            sorted_buildings = building_production.sort_values(ascending=False).index.tolist()

            # ---- 데이터프레임 정렬을 위한 전처리 ----
            # 1. 제조동 정렬 순서 생성
            building_order = {b: i for i, b in enumerate(sorted_buildings)}
            self.left_section.data['Building_sort'] = self.left_section.data['Building'].apply(lambda x: building_order.get(x, 999))

            # 2. 같은 제조동 내에서 라인명으로 정렬 (I_01 -> 01 형태로 변환)
            self.left_section.data['Line_sort'] = self.left_section.data['Line'].apply(
                lambda x: x.split('_')[1] if '_' in x else x
            )

            # 3. 최종 정렬 적용 (제조동 순위 -> 라인명 -> 시간)
            self.left_section.data = self.left_section.data.sort_values(by=['Building_sort', 'Line_sort', 'Time']).reset_index(drop=True)

            # 4. 임시 정렬 컬럼 제거
            self.left_section.data = self.left_section.data.drop(columns=['Building_sort', 'Line_sort'], errors='ignore')

            # 기존 아이템 모두 지우기
            self.left_section.clear_all_items()

            # Line과 Time 값 추출
            lines = []
            for building in sorted_buildings:
                # 해당 제조동에 속하는 라인들 찾기
                building_lines = [line for line in self.left_section.data['Line'].unique() if line.startswith(building)]
                # 라인 이름 기준 오름차순 정렬
                sorted_building_lines = sorted(building_lines)
                # 정렬된 라인 추가
                lines.extend(sorted_building_lines)

            times = sorted(self.left_section.data['Time'].unique())

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
            self.left_section.row_headers = []
            for line in lines:
                for shift in ["Day", "Night"]:
                    self.left_section.row_headers.append(f"{line}_({shift})")

            # 그리드 설정
            self.left_section.grid_widget.setupGrid(
                rows=len(self.left_section.row_headers),
                columns=len(self.left_section.days),
                row_headers=self.left_section.row_headers,
                column_headers=self.left_section.days,
                line_shifts=line_shifts
            )

            # 데이터에서 아이템 생성하여 그리드에 배치
            for _, row_data in self.left_section.data.iterrows():
                if 'Line' not in row_data or 'Time' not in row_data:
                    continue

                line = row_data['Line']
                time = row_data['Time']
                shift = shifts[time]
                day_idx = (int(time) - 1) // 2

                if day_idx >= len(self.left_section.days):
                    continue

                day = self.left_section.days[day_idx]
                row_key = f"{line}_({shift})"

                # Item 정보가 있으면 추출하여 저장
                if 'Item' in row_data and pd.notna(row_data['Item']):
                    item_info = str(row_data['Item'])

                    # MFG 정보가 있으면 수량 정보로 추가
                    if 'Qty' in row_data and pd.notna(row_data['Qty']):
                        item_info += f"    {row_data['Qty']}"

                    try:
                        # 그리드에 아이템 추가
                        row_idx = self.left_section.row_headers.index(row_key)
                        col_idx = day_idx

                        # 전체 행 데이터를 아이템 데이터(dict 형태)로 전달
                        item_full_data = row_data.to_dict()
                        new_item = self.left_section.grid_widget.addItemAt(row_idx, col_idx, item_info, item_full_data)

                        if new_item:
                            item_code = item_full_data.get('Item', '')

                            # 사전할당 아이템인 경우
                            if item_code in self.left_section.pre_assigned_items:
                                new_item.set_pre_assigned_status(True)

                            # 출하 실패 아이템인 경우
                            if item_code in self.left_section.shipment_failure_items:
                                failure_info = self.left_section.shipment_failure_items[item_code]
                                new_item.set_shipment_failure(True, failure_info.get('reason', 'Unknown reason'))

                            # 자재부족 아이템인 경우
                            if hasattr(self, 'current_shortage_items') and item_code in self.current_shortage_items:
                                shortage_info = self.left_section.current_shortage_items[item_code]
                                new_item.set_shortage_status(True, shortage_info)

                    except ValueError as e:
                        print(f"인덱스 찾기 오류: {e}")

            # 스크롤 위치 복원
            if current_scroll_position and hasattr(self.left_section.grid_widget, 'scroll_area'):
                QTimer.singleShot(50, lambda: self.left_section._restore_scroll_position(current_scroll_position))

            # 저장했던 필터 및 검색 상태 복원
            self.current_filter_states = current_filter_states
            self.current_excel_filter_states = current_excel_filter_states

            # 필터 상태 즉시 재적용
            if any(v for k, v in self.left_section.current_filter_states.items()):
                self.left_section.apply_all_filters()
                
            # 검색이 활성화되었던 경우 검색 상태 복원
            if current_search_active and current_search_text:
                # SearchWidget 상태 복원
                self.left_section.search_widget.last_search_text = current_search_text
                self.left_section.search_widget.search_active = True
                self.left_section.search_widget.clear_button.setEnabled(True)
                
                # 검색 실행
                self.left_section.search_items(current_search_text)

            # 출하 분석도 즉시 업데이트
            self._trigger_analysis()

        except Exception as e:
            print(f"UI 업데이트 오류: {e}")
            import traceback
            traceback.print_exc()

    

