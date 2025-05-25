import os
import pandas as pd
from PyQt5.QtCore import QObject, pyqtSignal
from app.analysis.output.plan_maintenance import PlanMaintenanceRate
from app.models.common.file_store import FilePaths
from app.utils.item_key_manager import ItemKeyManager

"""
계획 데이터 관리 클래스
"""    
class PlanDataManager(QObject):
    # 상태변경 시그널
    itemStatusChanged = pyqtSignal(str, bool)  # (item_key, is_modified)
    rmcStatusChanged = pyqtSignal(str, bool)   # (rmc_key, is_modified)
    dataChanged = pyqtSignal()                 # 데이터 변경 시그널

    def __init__(self):
        super().__init__()
        self.plan_analyzer = PlanMaintenanceRate()
        self.current_plan = None
        self.previous_plan_path = None

        self.modified_item_keys = set()
        self.modified_rmc_keys = set()
        self.item_to_rmc_map = {}     # 아이템-RMC 매핑 {item_key: rmc_key}
        self.rmc_to_items_map = {}    # RMC-아이템 매핑 {rmc_key: set(item_keys)}

        # 시그널 연경
        self.itemStatusChanged.connect(self._update_rmc_status)
        self.rmcStatusChanged.connect(self._on_rmc_status_changed)

        # 데이터 변경 로깅을 위한 연결
        self.dataChanged.connect(self._log_data_changes)

    """
    현재 계획 설정
    """
    def set_current_plan(self, data):
        if data is None or data.empty:
            return False
            
        self.current_plan = data.copy()
        self.plan_analyzer.set_current_plan(data)

        # 아이템-RMC 관계 초기화
        self._initialize_relationships()
        return True

    """
    아이템-RMC 관계 초기화
    """
    def _initialize_relationships(self):
        if self.current_plan is None or 'RMC' not in self.current_plan.columns:
            print("_initialize_relationships: 현재 계획이 없거나 RMC 컬럼이 없습니다.")
            return
        
        # 기존 매핑 초기화
        self.item_to_rmc_map.clear()
        self.rmc_to_items_map.clear()
        
        # 아이템-RMC 관계 구성
        for _, row in self.current_plan.iterrows():
            if pd.isna(row.get('RMC')):
                continue
                
            line = row.get('Line')
            time = row.get('Time')
            item = row.get('Item')
            rmc = row.get('RMC')
            
            if pd.isna(line) or pd.isna(time) or pd.isna(item) or pd.isna(rmc):
                continue
                
            item_key = ItemKeyManager.get_item_key(line, time, item)
            rmc_key = ItemKeyManager.get_item_key(line, time, rmc)
            
            # 아이템-RMC 매핑 저장
            self.item_to_rmc_map[item_key] = rmc_key
            
            # RMC-아이템 매핑 저장
            if rmc_key not in self.rmc_to_items_map:
                self.rmc_to_items_map[rmc_key] = set()
            self.rmc_to_items_map[rmc_key].add(item_key)
        
        print(f"관계 초기화 완료: {len(self.item_to_rmc_map)} 아이템-RMC 매핑, {len(self.rmc_to_items_map)} RMC-아이템 매핑")
        
        
        
    """
    이전 계획 로드
    """
    def load_previous_plan(self, file_path):
        try:
            previous_df = pd.read_excel(file_path)
            
            if not previous_df.empty:
                self.previous_plan_path = file_path
                self.plan_analyzer.set_prev_plan(previous_df)
                
                # 상태 초기화
                self.modified_item_keys.clear()
                self.modified_rmc_keys.clear()

                return True, os.path.basename(file_path)
            else:
                return False, "Empty file"
        except Exception as e:
            return False, str(e)
            
    
    """
    이전 계획 설정
    FilePaths에서 이전 계획 파일 경로를 가져와서 자동 로드
    """
    def set_previous_plan(self):
        upload_plan = FilePaths.get("result_file")

        if upload_plan and os.path.exists(upload_plan):
            print(f"업로드된 이전 계획 파일 자동 로드: {upload_plan}")
            success, message = self.load_previous_plan(upload_plan)
            if success:
                return success, f"Uploaded previous plan: {message}"
            else:
                print(f"업로드된 파일 로드 실패: {message}")
                return False, f"Failed to load uploaded file: {message}"      
        else:
            # 업로드된 이전 계획 파일이 없음
            return False, "No previous plan uploaded"
        
    """
    아이템 상태 업데이트
    """
    def _update_item_status(self, item_key, is_modified):
        # print(f"_update_item_status 호출됨: {item_key}, is_modified: {is_modified}, item_to_rmc_map 크기: {len(self.item_to_rmc_map)}")
        # print(f"item_key가 item_to_rmc_map에 있는지: {item_key in self.item_to_rmc_map}")
        if is_modified:
            self.modified_item_keys.add(item_key)
        else:
            self.modified_item_keys.discard(item_key)

        # 이벤트 발생
        self.itemStatusChanged.emit(item_key, is_modified)

    """
    item 상태 변경에 따라 rmc 상태 업데이트 - 내부에서만 호출
    """
    def _update_rmc_status(self, item_key, is_modified):
        if item_key in self.item_to_rmc_map:
            rmc_key = self.item_to_rmc_map[item_key]
            # print(f"_update_rmc_status/rmc_key: {rmc_key}")

            if is_modified:
                # 아이템이 수정되면 rmc도 수정
                self.modified_rmc_keys.add(rmc_key)
                # print(f"RMC 키 추가됨: {rmc_key}, 크기: {len(self.modified_rmc_keys)}")
                self.rmcStatusChanged.emit(rmc_key, True)
            else:
                # 아이템이 원래 상태로 돌아가면, 해당 rmc를 사용하는 수정된 아이템이 있는지 확인
                has_other_modified_items = False
                if rmc_key in self.rmc_to_items_map:
                    for i_key in self.rmc_to_items_map[rmc_key]:
                        if i_key != item_key and i_key in self.modified_item_keys:
                            has_other_modified_items = True
                            break

                # 다른 수정된 아이템이 없으면 RMC도 수정 상태 해제
                if not has_other_modified_items and rmc_key in self.modified_rmc_keys:
                    self.modified_rmc_keys.discard(rmc_key)
                    # print(f"RMC 키 제거됨: {rmc_key}, 크기: {len(self.modified_rmc_keys)}")
                    self.rmcStatusChanged.emit(rmc_key, False)
    
    """
    수량 업데이트
    """
    def update_quantity(self, line, time, item, new_qty, item_id=None):
        print(f"DataManager - 수량 업데이트 시도: line={line}, time={time}, item={item}, new_qty={new_qty}, item_id={item_id}")
        if self.plan_analyzer is None:
            return False
            
        # 원래 값 확인
        original_qty = self.get_original_quantity(line, time, item)
        original_qty = int(original_qty) if original_qty is not None else None
        new_qty = int(new_qty) if new_qty is not None else None

        # ID가 있으면 ID 기반 키 생성, 없으면 기존 방식
        if item_id:
            item_key = f"id_{item_id}"  # ID 기반 키
        else:
            item_key = ItemKeyManager.get_item_key(line, time, item) 

        # 두 가지 키 모두 저장 - ID 기반 키와 (Line, Time, Item) 키
        line_time_item_key = ItemKeyManager.get_item_key(line, time, item)

        # rmc 관계 확인 및 추가
        if item_key not in self.item_to_rmc_map and 'RMC' in self.current_plan.columns:
            # 같은 아이템의 다른 위치에서 rmc 정보 가져오기
            same_item_mask = self.current_plan['Item'] == item
            if same_item_mask.any():
                rmc = self.current_plan.loc[same_item_mask, 'RMC'].iloc[0]
                if not pd.isna(rmc):
                    rmc_key = ItemKeyManager.get_item_key(line, time, rmc)
                    print(f"아이템-rmc 키 매핑 추가: {item_key}->{rmc_key}")

                    # 아이템 - rmc 매핑 저장
                    self.item_to_rmc_map[item_key] = rmc_key

                    # rmc - 아이템 메핑 저장
                    if rmc_key not in self.rmc_to_items_map:
                        self.rmc_to_items_map[rmc_key] = set()
                    self.rmc_to_items_map[rmc_key].add(item_key)

        # 값이 원래대로 돌아갔는지 확인
        if original_qty == new_qty and original_qty is not None:
            # 수정된 아이템 목록에서 제거
            self._update_item_status(item_key, False)
            self._update_item_status(line_time_item_key, False)  # 두 가지 키 모두 제거
        else:
            # 값이 변경된 경우 수정된 목록에 추가
            self._update_item_status(item_key, True)
            self._update_item_status(line_time_item_key, True)  # 두 가지 키 모두 추가
            # print(f"Item 키 추가됨: {item_key}")
        
        # 수량 업데이트
        success = self.plan_analyzer.update_quantity(line, time, item, new_qty, item_id)

        if success:
            self.dataChanged.emit()
        
        return success
    

    """
    유지율 계산
    Args:
        compare_with_adjusted: 조정된 계획과 비교할지 여부
        calculate_rmc: RMC 유지율을 계산할지 여부
    Returns:
        tuple: (데이터프레임, 유지율)
    """
    def calculate_maintenance_rates(self, compare_with_adjusted=False,  calculate_rmc=False):
        print(f"calculate_maintenance_rates 호출됨, compare_with_adjusted={compare_with_adjusted}")
    
        if self.plan_analyzer is None:
            print("plan_analyzer가 None입니다")
            return None, None, None, None
        
        print(f"현재 계획: {self.current_plan is not None}")
            
        if calculate_rmc:
            # RMC 유지율 계산
            rmc_df, rmc_rate = self.plan_analyzer.calculate_rmc_maintenance_rate(compare_with_adjusted)
            return rmc_df, rmc_rate
        else:
            # Item 유지율 계산
            item_df, item_rate = self.plan_analyzer.calculate_items_maintenance_rate(compare_with_adjusted)
            return item_df, item_rate
    

    """
    원래 수량 가져오기
    """
    def get_original_quantity(self, line, time, item):
        if not hasattr(self, 'plan_analyzer') or not self.plan_analyzer:
            return None
            
        if not hasattr(self.plan_analyzer, 'prev_plan') or self.plan_analyzer.prev_plan is None:
            return None
        
        # 원래 계획에서 해당 아이템 찾기
        try:
            prev_plan = self.plan_analyzer.prev_plan
            mask = (
                (prev_plan['Line'].astype(str) == str(line)) & 
                (prev_plan['Time'].astype(int) == int(time)) & 
                (prev_plan['Item'] == item)
            )
            
            if mask.any():
                return prev_plan[mask].iloc[0].get('Qty')
            else:
                print(f"원래 계획에서 아이템을 찾을 수 없음: {line}, {time}, {item}")
        except Exception as e:
            print(f"원래 수량 조회 중 오류: {str(e)}")
        
        return None

    """
    RMC 상태가 변경되었을 때 호출
    이 메서드는 RMC 상태 변경에 따른 추가 작업을 수행할 수 있음
    """
    def _on_rmc_status_changed(self, rmc_key, is_modified):
        status_text = "수정됨" if is_modified else "원래대로"
        print(f"RMC 상태 변경: {rmc_key} - {status_text}")

        # RMC 키에서 정보 추출
        line, time, rmc = ItemKeyManager.parse_item_key(rmc_key)
        
        # RMC에 연결된 아이템 목록 출력
        if rmc_key in self.rmc_to_items_map:
            related_items = self.rmc_to_items_map[rmc_key]
            print(f"RMC {rmc}에 연결된 아이템 수: {len(related_items)}개")
            
            # RMC에 연결된 아이템 중 수정된 아이템 수 계산
            modified_count = sum(1 for item_key in related_items if item_key in self.modified_item_keys)
            print(f"RMC {rmc}에 연결된 수정된 아이템 수: {modified_count}개")
            
            # RMC 변경이 여러 아이템에 영향을 미치는 경우 알림
            if len(related_items) > 1:
                print(f"⚠️ 주의: RMC {rmc} 변경이 {len(related_items)}개 아이템에 영향을 미침")
  
        
    """
    데이터 변경 로깅
    """
    def _log_data_changes(self):
        print(f"데이터 변경 감지: 수정된 아이템 {len(self.modified_item_keys)}개, 수정된 RMC {len(self.modified_rmc_keys)}개")
        
        # 데이터 변경 타입 분석 - 어떤 종류의 아이템이 수정되었는지 확인
        if self.modified_item_keys and self.current_plan is not None:
            try:
                # 수정된 아이템들의 특성 분석
                modified_lines = set()
                modified_times = set()
                
                for item_key in self.modified_item_keys:
                    line, time, item = ItemKeyManager.parse_item_key(item_key)
                    if line and time:
                        modified_lines.add(line)
                        modified_times.add(time)
                
                if modified_lines:
                    print(f"수정된 라인: {', '.join(sorted(modified_lines))}")
                if modified_times:
                    print(f"수정된 시간대: {', '.join(sorted(modified_times))}")
                    
                # 여기서는 유지율을 다시 계산하지 않음 - PlanMaintenanceWidget에서 refresh_maintenance_rate 메서드가 
                # 이미 데이터 변경 후 유지율을 다시 계산하기 때문에 중복 방지
                
            except Exception as e:
                print(f"데이터 변경 분석 중 오류: {str(e)}")