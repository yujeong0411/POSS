from PyQt5.QtCore import QObject, pyqtSignal
import pandas as pd

"""
필터 관련 로직 담당 
"""
class FilterManager(QObject):
    filter_applied = pyqtSignal()
    
    def __init__(self, left_section):
        super().__init__()
        self.left_section = left_section

    """
    외부 호출용 메인 필터 적용 메서드
    """
    def apply_filters(self, filter_states):
        print(f"[FilterManager] 필터 적용: {filter_states}")
        
        # 현재 활성화된 라인 필터 확인
        active_lines = []
        if 'line' in filter_states:
            for line, is_active in filter_states['line'].items():
                if is_active:
                    active_lines.append(line)

        # 현재 활성화된 프로젝트 필터 확인
        active_projects = []
        if 'project' in filter_states:
            for project, is_active in filter_states['project'].items():
                if is_active:
                    active_projects.append(project)

        if not active_lines and not active_projects:
            # 모든 데이터 표시
            if (hasattr(self.left_section, 'data') and 
                self.left_section.data is not None and 
                not self.left_section.data.empty):
                all_lines = self.left_section.data['Line'].unique().tolist()
                self._rebuild_grid_with_filtered_data(all_lines, None)
            else:
                self._show_empty_grid()
        else:
            # 필터링된 데이터 표시
            self._rebuild_grid_with_filtered_data(active_lines, active_projects)
        
        self.filter_applied.emit()

        print("[FilterManager] 필터 적용 완료")

    """
    실제 필터 적용 로직
    """
    def _process_filter_changes(self):
        filter_states = self._pending_filter_changes

        # 현재 활성화된 라인 필터 확인
        active_lines = []
        if 'line' in filter_states:
            for line, is_active in filter_states['line'].items():
                if is_active:
                    active_lines.append(line)

        # 현재 활성화된 프로젝트 필터 확인
        active_projects = []
        if 'project' in filter_states:
            for project, is_active in filter_states['project'].items():
                if is_active:
                    active_projects.append(project)

        # *** 핵심 수정: 라인과 프로젝트 필터가 모두 없으면 모든 데이터 표시 ***
        if not active_lines and not active_projects:
            print("DEBUG: 활성화된 라인/프로젝트가 없음 - 모든 데이터 표시")
            if hasattr(self.left_section, 'data') and self.left_section.data is not None and not self.left_section.data.empty:
                all_lines = self.left_section.data['Line'].unique().tolist()
                self._rebuild_grid_with_filtered_data(all_lines, None)
            else:
                self._show_empty_grid()
            return

        # 활성화된 필터가 있으면 해당 데이터만 표시
        print(f"DEBUG: 활성화된 라인들: {active_lines}")
        print(f"DEBUG: 활성화된 프로젝트들: {active_projects}")

        # 라인 필터만 있는 경우
        if active_lines and not active_projects:
            self._rebuild_grid_with_filtered_data(active_lines, None)
        # 프로젝트 필터만 있는 경우
        elif not active_lines and active_projects:
            # *** 핵심: 빈 라인 리스트 전달 (필터링된 데이터에서 라인 추출하도록) ***
            self._rebuild_grid_with_filtered_data(None, active_projects)
        # 라인과 프로젝트 필터가 모두 있는 경우
        else:
            self._rebuild_grid_with_filtered_data(active_lines, active_projects)
    
    """
    범례 필터 적용 (상태선 표시)
    """
    def apply_legend_filters(self, filter_states):
        print(f"[FilterManager] 범례 필터 적용: {filter_states}")
        self.left_section.current_filter_states = filter_states
        self._apply_legend_filters_only()

        self.filter_applied.emit()

    """
    활성화된 라인과 프로젝트로 그리드 재구성
    """
    def _rebuild_grid_with_filtered_data(self, active_lines, active_projects=None):
        if self.left_section.data is None:
            return

        try:
            # 데이터 필터링
            filtered_data = self.left_section.data.copy()

            # 라인 필터 적용
            if active_lines:
                filtered_data = filtered_data[filtered_data['Line'].isin(active_lines)]

            # 프로젝트 필터 적용
            if active_projects and 'Project' in filtered_data.columns:
                # NaN 값 처리
                project_mask = filtered_data['Project'].isin(active_projects)
                # NaN을 "N/A"로 처리한 경우도 고려
                if "N/A" in active_projects:
                    nan_mask = filtered_data['Project'].isna()
                    project_mask = project_mask | nan_mask
                filtered_data = filtered_data[project_mask]

            print(f"DEBUG: 필터링 후 데이터 행 수: {len(filtered_data)}")

            if filtered_data.empty:
                self._show_empty_grid()
                return

            # *** 핵심 수정: 필터링된 데이터에서 실제 존재하는 라인만 추출 ***
            actual_lines_in_filtered_data = filtered_data['Line'].unique().tolist()
            print(f"DEBUG: 필터링된 데이터에 실제 존재하는 라인들: {actual_lines_in_filtered_data}")

            # 라인 정렬 (필터링된 데이터의 라인만 사용)
            filtered_data['Building'] = filtered_data['Line'].str[0]
            building_production = filtered_data.groupby('Building')['Qty'].sum()
            sorted_buildings = building_production.sort_values(ascending=False).index.tolist()

            # *** 실제 데이터가 있는 라인들만 정렬 ***
            sorted_active_lines = []
            for building in sorted_buildings:
                building_lines = [line for line in actual_lines_in_filtered_data if line.startswith(building)]
                sorted_building_lines = sorted(building_lines)
                sorted_active_lines.extend(sorted_building_lines)

            # 혹시 누락된 라인이 있으면 추가 (제조동 분류에 실패한 경우)
            remaining_lines = [line for line in actual_lines_in_filtered_data if line not in sorted_active_lines]
            if remaining_lines:
                sorted_active_lines.extend(sorted(remaining_lines))

            print(f"DEBUG: 최종 표시할 라인들: {sorted_active_lines}")

            # 교대 정보 (실제 데이터가 있는 라인만)
            line_shifts = {}
            for line in sorted_active_lines:
                line_shifts[line] = ["Day", "Night"]

            # 행 헤더 (실제 데이터가 있는 라인만)
            filtered_row_headers = []
            for line in sorted_active_lines:
                for shift in ["Day", "Night"]:
                    filtered_row_headers.append(f"{line}_({shift})")

            print(f"DEBUG: 최종 행 헤더: {filtered_row_headers}")

            # 그리드 재구성
            self.left_section.grid_widget.setupGrid(
                rows=len(filtered_row_headers),
                columns=len(self.left_section.days),
                row_headers=filtered_row_headers,
                column_headers=self.left_section.days,
                line_shifts=line_shifts
            )

            # 기존 아이템 모두 지우기
            self.left_section.all_items.clear()

            # 필터링된 데이터로 아이템 추가
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

                if day_idx >= len(self.left_section.days):
                    continue

                row_key = f"{line}_({shift})"

                try:
                    row_idx = filtered_row_headers.index(row_key)
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
                    print(f"필터링된 그리드에서 인덱스 찾기 오류: {e}")
                    continue

            # 아이템을 그리드에 추가
            for (row_idx, col_idx), items in grouped_items.items():
                for item_data in items:
                    item_info = str(item_data.get('Item', ''))
                    qty = item_data.get('Qty', 0)
                    if pd.notna(qty) and qty != 0:
                        item_info += f"    {qty}"

                    new_item = self.left_section.grid_widget.addItemAt(row_idx, col_idx, item_info, item_data)

                    if new_item:
                        item_code = item_data.get('Item', '')

                        # 상태 적용
                        if item_code in self.left_section.pre_assigned_items:
                            new_item.set_pre_assigned_status(True)

                        if item_code in self.left_section.shipment_failure_items:
                            failure_info = self.left_section.shipment_failure_items[item_code]
                            new_item.set_shipment_failure(True, failure_info.get('reason', 'Unknown reason'))

                        if hasattr(self.left_section, 'current_shortage_items') and item_code in self.left_section.current_shortage_items:
                            shortage_info = self.left_section.current_shortage_items[item_code]
                            new_item.set_shortage_status(True, shortage_info)

            # 범례 필터도 적용
            self._apply_legend_filters_only()

            print(f"DEBUG: 필터링된 그리드 재구성 완료 - {len(sorted_active_lines)}개 라인, 프로젝트 필터: {active_projects}")

        except Exception as e:
            print(f"필터링된 그리드 구성 중 오류: {e}")
            import traceback
            traceback.print_exc()

    """
    빈 그리드 표시 - Clear All 했을 때 사용
    """
    def _show_empty_grid(self):
        try:
            # 모든 아이템 제거
            self.left_section.grid_widget.clearAllItems()
            self.left_section.all_items.clear()

            # 빈 그리드 설정 (최소한의 구조만 유지)
            self.left_section.grid_widget.setupGrid(
                rows=0,  # 행 없음
                columns=len(self.left_section.days),
                row_headers=[],  # 빈 행 헤더
                column_headers=self.left_section.days,
                line_shifts={}  # 빈 라인 시프트
            )

            print("DEBUG: 빈 그리드 표시 완료")

        except Exception as e:
            print(f"빈 그리드 표시 중 오류: {e}")
            import traceback
            traceback.print_exc()

    """
    범례 필터만 적용 (상태선 표시)
    """
    def _apply_legend_filters_only(self):
        if not hasattr(self.left_section, 'grid_widget') or not hasattr(self.left_section.grid_widget, 'containers'):
            return

        # 범례 필터 상태 확인
        shortage_filter = self.left_section.current_filter_states.get('shortage', False)
        shipment_filter = self.left_section.current_filter_states.get('shipment', False)
        pre_assigned_filter = self.left_section.current_filter_states.get('pre_assigned', False)

        # 모든 아이템에 상태선 적용
        for row_containers in self.left_section.grid_widget.containers:
            for container in row_containers:
                for item in container.items:
                    # 상태선 설정
                    if hasattr(item, 'show_shortage_line'):
                        item.show_shortage_line = shortage_filter and getattr(item, 'is_shortage', False)
                    if hasattr(item, 'show_shipment_line'):
                        item.show_shipment_line = shipment_filter and getattr(item, 'is_shipment_failure', False)
                    if hasattr(item, 'show_pre_assigned_line'):
                        item.show_pre_assigned_line = pre_assigned_filter and getattr(item, 'is_pre_assigned', False)

                    # 상태선 업데이트
                    item.update()

    """
    종합적인 필터 적용 (엑셀 + 범례 + 검색)
    """
    def apply_standard_filters(self):
        if not hasattr(self.left_section, 'grid_widget') or not hasattr(self.left_section.grid_widget, 'containers'):
            return

        # 0. 필터 상태 캐싱
        excel_filter_active = any(not all(states.values()) for states in self.left_section.current_excel_filter_states.values())
        legend_filter_active = any(self.left_section.current_filter_states.values())
        search_active = self.left_section.search_widget.is_search_active()
        search_text = self.left_section.search_widget.get_search_text() if search_active else None

        # 아이템 상태 캐싱 및 배치 처리
        # 가시성 변경할 아이템, 상태선 변경할 아이템, 검색 하이라이트 변경할 아이템 목록화
        visibility_changes = []  # (아이템, 표시여부) 튜플 목록
        stateline_changes = []  # {아이템, 상태 딕셔너리} 목록
        highlight_changes = []  # (아이템, 하이라이트여부) 튜플 목록
        search_results = []  # 검색 결과 아이템 목록

        # 컨테이너별 가시성 변경 여부 추적
        affected_containers = set()

        # 배치 처리를 위해 한 번만 순회
        for row_containers in self.left_section.grid_widget.containers:
            for container in row_containers:
                container_changed = False

                for item in container.items:
                    # 엑셀 필터 적용 (라인/프로젝트)
                    should_show = True
                    if excel_filter_active:
                        should_show = self.left_section.should_show_item_excel_filter(item)

                    # 가시성 변경 필요한 경우만 기록
                    if item.isVisible() != should_show:
                        visibility_changes.append((item, should_show))
                        container_changed = True

                    # 상태선 변경 필요한지 확인 (범례 필터)
                    if legend_filter_active:
                        shortage_filter = self.left_section.current_filter_states.get('shortage', False)
                        shipment_filter = self.left_section.current_filter_states.get('shipment', False)
                        pre_assigned_filter = self.left_section.current_filter_states.get('pre_assigned', False)

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
                        is_match = search_text in str(item.item_data.get('Item', '')).lower() if hasattr(item,
                                                                                                         'item_data') else False

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
            self.left_section.search_results = search_results

            if self.search_results:
                # 선택 위치 업데이트
                if self.left_section.current_result_index < 0 or self.left_section.current_result_index >= len(self.left_section.search_results):
                    self.left_section.current_result_index = 0
                self.left_section.update_result_navigation()

                # 선택된 검색 결과로 스크롤
                if 0 <= self.current_result_index < len(self.search_results):
                    self.left_section.select_current_result()
            else:
                # 검색 결과 없음 표시
                self.left_section.search_widget.set_result_status(0, 0)
                self.left_section.search_widget.show_result_navigation(True)

        # 5. 영향 받은 컨테이너만 크기 조정
        for container in affected_containers:
            container.adjustSize()

    
    """
    엑셀 필터를 고려한 아이템 표시 여부
    """
    def should_show_item_excel_filter(self, item):
        if not hasattr(self.left_section, 'current_excel_filter_states') or not hasattr(item, 'item_data'):
            return True

        item_data = item.item_data

        # 라인 필터 체크
        if 'Line' in item_data:
            line = str(item_data['Line'])
            line_filters = self.left_section.current_excel_filter_states.get('line', {})
            if line_filters and line in line_filters and not line_filters[line]:
                return False

        # 프로젝트 필터 체크
        if 'Project' in item_data:
            project = item_data['Project']
            if pd.isna(project):
                project = "N/A"
            else:
                project = str(project)

            project_filters = self.left_section.current_excel_filter_states.get('project', {})
            if project_filters and project in project_filters and not project_filters[project]:
                return False

        return True
