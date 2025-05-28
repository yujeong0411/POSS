import pandas as pd
from app.utils.item_key_manager import ItemKeyManager

"""
생산 계획의 유지율을 계산하는 클래스
원본 계획과 현재 계획 간의 유지율을 Item별, RMC별로 계산

- 첫 번째 계획인 경우 이전 계획 없음 처리
- 계획 조정 시 조정 전/후 비교 기능 추가
"""
class PlanMaintenanceRate:
    def __init__(self):
        self.prev_plan = None # 초기 계획
        self.current_plan = None # 현재 계획(새로 수정한 계획)
        self.adjusted_plan = None # 조정 후 계획
    
    """
    초기 계획 설정

    Parameters:
        plan_data (DataFrame) : 생산계획 결과 데이터
    Return:
        bool : 설정 성공 여부
    """
    def set_prev_plan(self, plan_data):
        if plan_data is None or plan_data.empty:
            return False
        
        self.prev_plan = plan_data.copy()
        self.current_plan = plan_data.copy()
        return True
    
    """
    새로 수정한 계획 데이터 설정
    
    Parameters:
        plan_data (DataFrame): 새 계획 데이터
    Returns:
        bool: 설정 성공 여부
    """
    def set_current_plan(self, plan_data):
        if plan_data is None or plan_data.empty:
            return False
        
        self.current_plan = plan_data.copy()
        self.adjusted_plan = plan_data.copy()
        return True
    

    """
    특정 항목의 수량 업데이트 (계획 조정)
    
    Parameters:
        line (str): 생산 라인 ID
        time (str): 시프트 번호
        item (str): 제품 코드
        new_qty (str): 새로운 수량
    Returns:
        bool: 업데이트 성공 여부
    """
    def update_quantity(self, line, time, item, new_qty, item_id=None):
        print(f"PlanMaintenanceWidget - 수량 업데이트 시도: line={line}, time={time}, item={item}, new_qty={new_qty}, item_id={item_id}")
        
        # modified_items 딕셔너리가 없으면 초기화 - 이 부분 추가
        if not hasattr(self, 'modified_items'):
            self.modified_items = {}
            
        if self.adjusted_plan is None:
            # 아직 조정하지 않았다면, 현재 계획으로 초기화
            print("adjusted_plan이 초기화되지 않았습니다.")
            if self.current_plan is not None:
                self.adjusted_plan = self.current_plan.copy()
            else:
                print("current_plan도 없습니다.")
                return False
            
        try :
            # 조건에 맞는 행 찾기 - ID가 있으면 ID로 찾고, 없으면 기존 방식
            if item_id and '_id' in self.adjusted_plan.columns:
                # ID로 검색 시도
                mask = ItemKeyManager.create_mask_by_id(self.adjusted_plan, item_id)
                
                # ID 검색 결과 확인
                if mask.any():
                    print(f"ID {item_id}로 아이템 찾음")
                else:
                    print(f"ID {item_id}로 아이템을 찾지 못함, 기존 방식 사용")
                    # 기존 방식으로 마스크 생성
                    mask = ItemKeyManager.create_mask_for_item(self.adjusted_plan, line, time, item)
            else:
                # 기존 방식으로 마스크 생성
                mask = ItemKeyManager.create_mask_for_item(self.adjusted_plan, line, time, item)
            
            # 일치하는 행이 있으면 수량 업데이트
            if mask.any():
                # 복수 행이 일치할 경우 로그 - 디버깅
                if mask.sum() > 1:
                    print(f"경고: {mask.sum()}개 행이 조건과 일치합니다. 첫 번째 행만 업데이트합니다.")

                self.adjusted_plan.loc[mask, 'Qty'] = new_qty

                # 수정된 아이템 기록 - 디버깅
                # ID가 있으면 ID를 키로 사용, 없으면 기존 방식
                if item_id:
                    key = f"id_{item_id}"
                else:
                    key = ItemKeyManager.get_item_by_not_id(line, time, item)
                    
                self.modified_items[key] = new_qty
                
                print(f"수량 업데이트 성공: {line}, {time}, {item} -> {new_qty}")
                return True
            else:
                # 동일한 아이템의 다른 위치 행 찾아서 복사하기
                # ID가 있으면 사용하지 않음 (ID는 고유함)
                if not item_id:
                    same_item_mask = self.adjusted_plan['Item'] == item
                    
                    if same_item_mask.any():
                        # 기존 행 찾기
                        old_row = self.adjusted_plan[same_item_mask].iloc[0].copy()

                        # 새 위치와 수량 정보로 복사본 생성
                        new_row = old_row.copy()
                        new_row['Line'] = line
                        new_row['Time'] = time
                        new_row['Qty'] = new_qty
                        
                        # ID가 있는 경우 새 ID 생성
                        if '_id' in self.adjusted_plan.columns:
                            import uuid
                            new_row['_id'] = str(uuid.uuid4())

                    # 기존 행 삭제
                    self.adjusted_plan = self.adjusted_plan[~same_item_mask]

                    # 새 행 추가
                    self.adjusted_plan = pd.concat([self.adjusted_plan, pd.DataFrame([new_row], index=[0])], ignore_index=True)
                    
                    # 수정된 아이템 기록  - 디버깅
                    key = (line, time, item)
                    self.modified_items[key] = new_qty
                    
                    print(f"아이템 이동 완료: {item}을(를) 새 위치({line},{time})로 이동하고 수량을 {new_qty}로 변경")
                    return True
            
        except Exception as e:
            print(f"유효하지 않은 시간 또는 수량: time={time}, new_qty={new_qty}")
            return False
        
        # 수량 업데이트 성공 시
        print(f"PlanMaintenanceWidget - 수량 업데이트 성공: line={line}, time={time}, item={item}, new_qty={new_qty}")
        return True
            

    """
    item별 유지율 계산 및 테이블 생성
    
    Parameters:
        compare_with_adjusted (bool): 조정된 계획과 비교할지 여부
        
    Returns:
        tuple: (결과 DataFrame, 유지율 %)
    """
    def calculate_items_maintenance_rate(self, compare_with_adjusted=False):
        # 이전 계획이 없으면 계산 제외 
        if self.prev_plan is None:
            return pd.DataFrame(), None
        
        # 비교 대상 결정
        if compare_with_adjusted:
            # 조정 결과와 비료
            if self.adjusted_plan is None:
                return pd.DataFrame(), None
            comparison_plan = self.adjusted_plan
        else:
            # 현재 계획과 비교
            if self.current_plan is None:
                return pd.DataFrame(), None
            comparison_plan = self.current_plan
        
        # 이전 계획 집계
        prev_grouped = self.prev_plan.groupby(['Line', 'Time', 'Item'])['Qty'].sum().reset_index()

        # 비교할 계획 집계 
        curr_grouped = comparison_plan.groupby(['Line', 'Time', 'Item'])['Qty'].sum().reset_index()

        # 이전 계획과 비교 계획 병합(중복없이)
        merged = pd.merge(
            prev_grouped,
            curr_grouped,
            on=['Line', 'Time', 'Item'],
            how='outer', # 외부 병합으로 모든 항목 포함
            suffixes=('_prev', '_curr')
        )

        # 유지 수량 계산 - 둘 다 0보다 큰 경우에만 min 적용, 아니면 0
        merged['maintenance'] = merged.apply(
            lambda x: min(x['Qty_prev'], x['Qty_curr']) if x['Qty_prev'] > 0 and x['Qty_curr'] > 0 else 0, 
            axis=1
        )

        # 필드명 수정
        result_df = merged.rename(columns={
            'Line': 'Line',
            'Time': 'Shift',
            'Item': 'Item',
            'Qty_prev': 'prev_plan',
            'Qty_curr': 'curr_plan'
        })

        # 합계 계산
        prev_plan_sum = result_df['prev_plan'].sum()
        curr_plan_sum = result_df['curr_plan'].sum()
        maintenance_sum = result_df['maintenance'].sum()

        # 유지율 계산
        maintenance_rate = (maintenance_sum / prev_plan_sum) * 100 if prev_plan_sum > 0 else 0
        
        # Total 행 추가
        total_row = {
            'Line': 'Total',
            'Shift': '',
            'Item': '',
            'prev_plan': prev_plan_sum,
            'curr_plan': curr_plan_sum,
            'maintenance': maintenance_sum
        }

        result_df = pd.concat([result_df, pd.DataFrame([total_row])], ignore_index=True)

        return result_df, maintenance_rate

    """
    RMC별 유지율 계산
    
    Parameters:
        compare_with_adjusted (bool): 조정된 계획과 비교할지 여부
        
    Returns:
        tuple: (결과 DataFrame, 유지율 %)
    """
    def calculate_rmc_maintenance_rate(self, compare_with_adjusted=False):
        # 이전 계획이 없으면 계산 제외 
        if self.prev_plan is None:
            return pd.DataFrame(), None
        
        # 비교 대상 결정
        if compare_with_adjusted:
            # 조정된 계획과 비교
            if self.adjusted_plan is None:
                return pd.DataFrame(), None
            comparison_plan = self.adjusted_plan
        else:
            # 현재 계획과 비교
            if self.current_plan is None:
                return pd.DataFrame(), None
            comparison_plan = self.current_plan
        
        # 원본 계획 집계
        prev_grouped = self.prev_plan.groupby(['Line', 'Time', 'RMC'])['Qty'].sum().reset_index()

        # 수정 계획 집계
        curr_grouped = comparison_plan.groupby(['Line', 'Time', 'RMC'])['Qty'].sum().reset_index()
        
        # 이전 계획과 병합
        merged = pd.merge(
            prev_grouped,
            curr_grouped,
            on=['Line', 'Time', 'RMC'],
            how='outer',
            suffixes=('_prev', '_curr')
        )

        # 유지 수량 계산 - 둘 다 0보다 큰 경우에만 min 적용, 아니면 0
        merged['maintenance'] = merged.apply(
            lambda x: min(x['Qty_prev'], x['Qty_curr']) if x['Qty_prev'] > 0 and x['Qty_curr'] > 0 else 0, 
            axis=1
        )

        result_df = merged.rename(columns={
            'Line': 'Line',
            'Time': 'Shift',
            'RMC': 'RMC',
            'Qty_prev': 'prev_plan',
            'Qty_curr': 'curr_plan'
        })
       
        # 합계
        prev_plan_sum = result_df['prev_plan'].sum()
        curr_plan_sum = result_df['curr_plan'].sum()
        maintenance_sum = result_df['maintenance'].sum()

        # RMC별 유지율 계산
        maintenance_rate = (maintenance_sum / prev_plan_sum) * 100 if prev_plan_sum > 0 else 0

        # Total 행 추가
        total_row = {
            'Line': 'Total',
            'Shift': '',
            'RMC': '',
            'prev_plan': prev_plan_sum,
            'curr_plan': curr_plan_sum,
            'maintenance': maintenance_sum
        }

        # 결과에 추가
        result_df = pd.concat([result_df, pd.DataFrame([total_row])], ignore_index=True)

        return result_df, maintenance_rate
    
    
    """ 현재 데이터 반환 """
    def get_current_plan(self):
        return self.current_plan.copy() if self.current_plan is not None else None
    
    """조정된 계획 데이터 반환"""
    def get_adjusted_plan(self):
        return self.adjusted_plan.copy() if self.adjusted_plan is not None else None

    
    """
    수량 변경된 항목 확인

    Parameters:
        compare_with_adjusted (bool): 조정된 계획과 비교할지 여부
    Returns:
        DataFrame: 변경된 항목 목록
    """
    def get_changed_items(self, compare_with_adjusted=False):        
        if self.prev_plan is None:
            return pd.DataFrame()
        
        # 비교 대상 결정
        if compare_with_adjusted:
            if self.adjusted_plan is None:
                return pd.DataFrame()
            comparison_plan = self.adjusted_plan
        else:
            if self.current_plan is None:
                return pd.DataFrame()
            comparison_plan = self.current_plan
        
        # 집계 후 비교
        prev_grouped = self.prev_plan.groupby(['Line', 'Time', 'Item'])['Qty'].sum().reset_index()
        curr_grouped = comparison_plan.groupby(['Line', 'Time', 'Item'])['Qty'].sum().reset_index()
        
        # 병합
        merged = pd.merge(
            prev_grouped, 
            curr_grouped,
            on=['Line', 'Time', 'Item'],
            how='outer',
            suffixes=('_prev', '_curr')
        )
        
        # 변경된 항목 필터링
        changed = merged[merged['Qty_prev'] != merged['Qty_curr']]
        return changed
        
    