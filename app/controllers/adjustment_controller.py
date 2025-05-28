from PyQt5.QtCore import QObject, QTimer
from typing import Any, Dict
import uuid
import pandas as pd
from app.utils.item_key_manager import ItemKeyManager
from app.analysis.output.kpi_score import KpiScore
from app.analysis.output.material_shortage_analysis import MaterialShortageAnalyzer
from app.analysis.output.daily_capa_utilization import CapaUtilization
from app.analysis.output.capa_ratio import CapaRatioAnalyzer

"""
Controller 중심 분석 아키텍처
- Controller가 모든 분석 실행
- View/Page들은 결과만 받아서 UI 업데이트
- 구조적으로 중복 불가능
"""
class AdjustmentController(QObject):

    def __init__(self, model: Any, view: Any, error_manager):
        super().__init__()
        self.model = model
        self.view = view  # ModifiedLeftSection
        self.error_manager = error_manager
        self.result_page = None  # 명시적으로 초기화 (result_page는 외부에서 설정)
        
        # 시그널 연결 상태만 추적 (중복 연결 방지용)
        self._signals_connected = False
        self._views_initialized = False

        # 분석 엔진들 초기화
        self._analysis_engines = self._initialize_analysis_engines()

    """
    모든 분석 엔진을 Controller에서 초기화
    """
    def _initialize_analysis_engines(self):
        engines = {}
        
        try:
            # KPI 분석 엔진
            engines['kpi'] = None  # ResultPage 설정 후 초기화
            
            # 자재 분석 엔진
            engines['material'] = MaterialShortageAnalyzer()
            
            # 가동률 분석 엔진
            engines['utilization'] = CapaUtilization()
            
            # 제조동 비율 분석 엔진
            engines['capa_ratio'] = CapaRatioAnalyzer()
            
            print("Controller: 분석 엔진 초기화 완료")
            
        except Exception as e:
            print(f"Controller: 분석 엔진 초기화 오류: {e}")
            engines = {
                'kpi': None,
                'material': None,
                'utilization': None,
                'capa_ratio': None
            }
    
        return engines

    """
    ResultPage 설정 및 KPI 엔진 초기화
    """
    def set_result_page(self, result_page):
        self.result_page = result_page

        # KPI 엔진 초기화 (ResultPage 필요)
        if hasattr(result_page, 'main_window'):
            self._analysis_engines['kpi'] = KpiScore(result_page.main_window)
            
        print("Controller: ResultPage 설정 및 KPI 엔진 초기화 완료")

    """
    초기 데이터로 뷰 초기화 (시그널 연결 전에 호출)
    """
    def initialize_views(self):
        # 이미 초기화된 경우 중복 초기화 방지
        if self._views_initialized:
            print("Controller: 뷰가 이미 초기화됨.")
            return False
        
        df = self.model.get_dataframe()

         # 초기화는 Controller에서 분석 후 배포
        analysis_results = self._run_all_analyses(df)
        
        # View 초기화 (분석 결과와 함께)
        self.view.initialize_with_data(df, analysis_results)
        
        # ResultPage 초기화
        if self.result_page:
            self.result_page.initialize_with_data(df, analysis_results)

        # 초기화 상태 설정
        self._views_initialized = True
        
        print("Controller: 뷰 초기 데이터 설정 완료")
        return True

    """
    시그널 연결
    """
    def connect_signals(self):
         # 이미 연결된 경우 중복 연결 방지
        if self._signals_connected:
            print("Controller: 시그널이 이미 연결됨.")
            return False
        
        # Model -> Controller (핵심 시그널)
        self.model.modelDataChanged.connect(self._on_model_change)
        print("Controller: modelDataChanged 시그널 연결")
        self.model.validationFailed.connect(self.error_manager.add_validation_error)
        print("Controller: 에러 매니저 시그널 연결")
        self.model.dataModified.connect(self.on_data_modified)
        print("Controller: dataModified 시그널 연결")
        
        # View -> Controller (아이템 데이터 변경)
        if hasattr(self.view, 'itemModified'):
            print("Controller: itemModified 시그널 연결")
            self.view.itemModified.connect(self._on_item_data_changed)
        
        # View -> Controller (셀 이동)  
        if hasattr(self.view, 'cellMoved'):
            print("Controller: cellMoved 시그널 연결")
            self.view.cellMoved.connect(self._on_cell_moved)

        # View -> Controller (아이템 삭제, 복사)
        if hasattr(self.view, 'grid_widget'):
            if hasattr(self.view.grid_widget, 'itemRemoved'):
                print("Controller: itemRemoved 시그널 연결")
                self.view.grid_widget.itemRemoved.connect(self.on_item_deleted)
        
            if hasattr(self.view.grid_widget, 'itemCopied'):
                print("Controller: itemCopied 시그널 연결")
                self.view.grid_widget.itemCopied.connect(self.on_item_copied)

        # 연결 완료 상태 설정
        self._signals_connected = True        
        print("Controller: 시그널 연결 완료")
        return True
    
    """
    모델 변경 시 - 분석 + UI 업데이트 통합 처리
    """
    def _on_model_change(self):
        print("Controller: 모델 변경 감지 → 분석 + UI 업데이트")
        
        df = self.model.get_dataframe()
        
        # Controller에서 모든 분석 실행 (한 번만)
        analysis_results = self._run_all_analyses(df)
        
        # 분석 결과와 함께 UI 업데이트 요청 (재분석 없음)
        self.view.update_ui_only(df, analysis_results)
        
        if self.result_page:
            self.result_page.update_ui_only(df, analysis_results)
        
        # Error Manager 업데이트
        self.error_manager.update_error_display()
        
        print("Controller: 통합 처리 완료")

    def _run_all_analyses(self, df):
        """🎯 Controller에서 모든 분석 실행 - 단일 진입점"""
        print("Controller: 모든 분석 실행 시작")
        
        if df is None or df.empty:
            return self._get_empty_results()
        
        results = {}
        
        try:
            # 1. KPI 분석
            if self._analysis_engines.get('kpi'):
                print("  → KPI 분석")
                kpi_engine = self._analysis_engines['kpi']
                
                # 데이터 설정
                demand_df = self._get_demand_data()
                material_analyzer = self._analysis_engines.get('material')
                kpi_engine.set_data(df, material_analyzer, demand_df)
                
                # Base/Adjust 점수 계산
                base_scores = kpi_engine.calculate_all_scores()
                
                # 조정 여부 확인
                has_adjustments = self._check_for_adjustments()
                if has_adjustments:
                    # 조정된 데이터로 다시 계산
                    adjust_scores = base_scores.copy()  # 임시로 동일
                    results['kpi'] = {
                        'base_scores': base_scores,
                        'adjust_scores': adjust_scores
                    }
                else:
                    results['kpi'] = {
                        'base_scores': base_scores,
                        'adjust_scores': {}
                    }
            
            # 2. 자재 부족 분석
            if self._analysis_engines.get('material'):
                print("  → 자재 분석")
                material_engine = self._analysis_engines['material']
                material_engine.analyze_material_shortage(df)
                results['material'] = {
                    'shortage_results': material_engine.shortage_results,
                    'analyzer': material_engine
                }
            
            # 3. 출하 분석
            print("  → 출하 분석")
            shipment_results = self._analyze_shipment(df)
            results['shipment'] = shipment_results
            
            # 4. 가동률 분석
            if self._analysis_engines.get('utilization'):
                print("  → 가동률 분석")
                utilization_engine = self._analysis_engines['utilization']
                utilization_data = utilization_engine.analyze_utilization(df)
                results['utilization'] = utilization_data
            
            # 5. 제조동 비율 분석
            if self._analysis_engines.get('capa_ratio'):
                print("  → 제조동 비율 분석")
                capa_engine = self._analysis_engines['capa_ratio']
                
                has_adjustments = self._check_for_adjustments()
                if has_adjustments:
                    comparison_df = self.model.get_comparison_dataframe()
                    if comparison_df:
                        results['capa_ratio'] = {
                            'original': capa_engine.analyze_capa_ratio(comparison_df['original']),
                            'adjusted': capa_engine.analyze_capa_ratio(comparison_df['adjusted'])
                        }
                else:
                    results['capa_ratio'] = capa_engine.analyze_capa_ratio(data_df=df, is_initial=True)
            
            # 6. 기타 분석들...
            results['plan_maintenance'] = self._analyze_plan_maintenance(df)
            results['split_allocation'] = self._analyze_split_allocation(df)
            results['summary'] = self._analyze_summary(df)
            
        except Exception as e:
            print(f"Controller: 분석 중 오류: {e}")
            import traceback
            traceback.print_exc()
            results = self._get_empty_results()
        
        print("Controller: 모든 분석 완료")
        return results

    def _analyze_shipment(self, df):
        """출하 분석 실행"""
        try:
            # ResultPage의 shipment_widget을 통해 분석
            if (self.result_page and 
                hasattr(self.result_page, 'shipment_widget') and 
                self.result_page.shipment_widget):
                
                self.result_page.shipment_widget.run_analysis(df)
                return {'analyzed': True}
        except Exception as e:
            print(f"출하 분석 오류: {e}")
        
        return {'analyzed': False}

    def _analyze_plan_maintenance(self, df):
        """계획 유지율 분석"""
        try:
            if (self.result_page and 
                hasattr(self.result_page, 'plan_maintenance_widget') and 
                self.result_page.plan_maintenance_widget):
                
                start_date, end_date = self.result_page.main_window.data_input_page.date_selector.get_date_range()
                return {
                    'data': df,
                    'start_date': start_date,
                    'end_date': end_date
                }
        except Exception as e:
            print(f"계획 유지율 분석 오류: {e}")
        
        return {}

    def _analyze_split_allocation(self, df):
        """분산 배치 분석"""
        try:
            if (self.result_page and 
                hasattr(self.result_page, 'split_allocation_widget') and 
                self.result_page.split_allocation_widget):
                
                self.result_page.split_allocation_widget.run_analysis(df)
                return {'analyzed': True}
        except Exception as e:
            print(f"분산 배치 분석 오류: {e}")
        
        return {'analyzed': False}

    def _analyze_summary(self, df):
        """요약 분석"""
        try:
            if (self.result_page and 
                hasattr(self.result_page, 'summary_widget') and 
                self.result_page.summary_widget):
                
                self.result_page.summary_widget.run_analysis(df)
                return {'analyzed': True}
        except Exception as e:
            print(f"요약 분석 오류: {e}")
        
        return {'analyzed': False}

    def _check_for_adjustments(self):
        """사용자 조정 여부 확인"""
        try:
            if hasattr(self.model, '_original_df') and hasattr(self.model, '_df'):
                original_df = self.model._original_df
                current_df = self.model._df
                
                if original_df is not None and current_df is not None:
                    key_columns = ['Line', 'Time', 'Item', 'Qty']
                    for col in key_columns:
                        if col in original_df.columns and col in current_df.columns:
                            if not original_df[col].equals(current_df[col]):
                                return True
            return False
        except:
            return False

    def _get_demand_data(self):
        """Demand 데이터 가져오기"""
        try:
            from app.models.common.file_store import DataStore
            organized = DataStore.get("organized_dataframes", {})
            return organized.get("demand", pd.DataFrame())
        except:
            return pd.DataFrame()

    def _get_empty_results(self):
        """빈 분석 결과 반환"""
        return {
            'kpi': {'base_scores': {}, 'adjust_scores': {}},
            'material': {'shortage_results': {}, 'analyzer': None},
            'shipment': {'analyzed': False},
            'utilization': {},
            'capa_ratio': {},
            'plan_maintenance': {},
            'split_allocation': {'analyzed': False},
            'summary': {'analyzed': False}
        }

    """
    아이템 데이터 변경 처리 → Model로 전달
    - Qty만 바뀌었으면 update_qty 호출
    - Line/Time이 바뀌었으면 move_item 호출
    """
    def _on_item_data_changed(self, item: object, new_data: Dict, changed_fields=None):
        code = new_data.get('Item')
        line = new_data.get('Line')
        time = new_data.get('Time')
        item_id = new_data.get('_id')  # ID 추출
        
        if not code or not line or time is None:
            print(f"Controller: 필수 데이터 누락 - Item: {code}, Line: {line}, Time: {time}")
            return
        
        # Line/Time 변경 = 이동
        if changed_fields and ('Line' in changed_fields or 'Time' in changed_fields):
                print(f"Controller: 아이템 이동 {code}")

                # 이전 위치 정보 가져오기
                old_line = changed_fields.get('Line', {}).get('from', line)
                old_time = changed_fields.get('Time', {}).get('from', time)
                print(f"이전 위치정보: 라인-{old_line} / 타임-{old_time}")

                self.model.move_item(code, old_line, old_time, line, time, item_id)
                return
        
        # 수량 변경 - 라인과 시간 정보도 함께 전달
        elif 'Qty' in new_data and line and time is not None:
            qty = new_data['Qty']
            print(f"Controller: 수량 변경 {code} @ {line}-{time} -> {qty}")
            # 수정된 모델의 update_qty 메서드 호출 (라인, 시간 포함)
            self.model.update_qty(code, line, time, qty, item_id)

    """
    드래그·드롭으로 위치 이동했을 때 → Model로 전달
    - Controller가 모든 셀 이동 로직 처리
    - 필요시 추가 로직 (시각화 업데이트 등) 수행
    """
    def _on_cell_moved(self, item, old_data, new_data):
        code = new_data.get('Item')
        if not code:
            return
        
        if code:
            item_id = new_data.get('_id')
            old_line = old_data.get('Line')
            old_time = old_data.get('Time')
            new_line = new_data.get('Line')
            new_time = new_data.get('Time')

            print(f"Controller: 셀 이동 {code} @ {old_line}-{old_time} -> {new_line}-{new_time}")

            self.model.move_item(code, old_line, old_time, new_line, new_time, item_id)

            # 스크롤 처리는 한 번만
            QTimer.singleShot(200, lambda: self._ensure_item_visible(item_id))
            print(f"셀 이동 후 스크롤 예약됨: ID={item_id}")

    """
    복사된 아이템 처리 → Model로 전달

    parameter:
        item: 복사된 아이템 위젯
        data: 아이템 데이터가 포함된 딕셔너리
    """
    def on_item_copied(self, item, data):
        print(f"컨트롤러가 복사 아이템 처리 중: {data.get('Item')} @ {data.get('Line')}-{data.get('Time')}")

        # 필수 정보 추출
        code = data.get('Item')
        line = data.get('Line')
        time = data.get('Time')

        # 필수 데이터 검증
        if not code or not line or time is None:
            print(f"Controller: 복사 시 필수 데이터 누락 - Item: {code}, Line: {line}, Time: {time}")
            return

        # 복사된 항목임을 표시하는 플래그 추가
        if '_is_copy' not in data:
            data['_is_copy'] = True
            
        # 모델에 명시적으로 추가 - 기본적으로 수량은 0으로 설정
        qty = data.get('Qty', 0)
        self.model.add_new_item(code, line, time, qty, data)
        print(f"Controller: 복사된 아이템 등록 - {code} @ {line}-{time}")


    """
    삭제된 아이템 처리 → Model로 전달
    """
    def on_item_deleted(self, item_or_id):
        print("DEBUG: AdjustmentController.on_item_deleted 호출됨")

        # item_or_id가 문자열(ID)인 경우
        if isinstance(item_or_id, str):
            item_id = item_or_id
            print(f"DEBUG: ID로 삭제: {item_id}")
            return self.model.delete_item_by_id(item_id)

        if hasattr(item_or_id, 'item_data') and item_or_id.item_data:
            # ID가 있으면 ID 기반으로 삭제
            item_id = ItemKeyManager.extract_item_id(item_or_id)
            if item_id:
                print(f"컨트롤러: 아이템 삭제 처리 - ID: {item_id}")
                return self.model.delete_item_by_id(item_id)
            
            # # ID가 없으면 Line/Time/Item 기반으로 삭제
            line, time, item_code = ItemKeyManager.get_item_from_data(item_or_id.item_data)
            if line is not None and time is not None and item_code is not None:
                print(f"컨트롤러: 아이템 삭제 처리 - {item_code} @ {line}-{time}")
                return self.model.delete_item(item_code, line, time)
        
        return 

    """
    아이템 ID를 기반으로 해당 아이템으로 스크롤
    """
    def _ensure_item_visible(self, item_id):
        if not item_id or not hasattr(self.view, 'grid_widget'):
            return

        # 뷰의 _scroll_to_selected_item 메서드 호출
        if hasattr(self.view, '_scroll_to_selected_item'):
            self.view._scroll_to_selected_item(item_id)

    """
    모델 데이터의 변경 상태에 따라 리셋 버튼 상태 업데이트
    """
    def on_data_modified(self, has_changes: bool):
        if hasattr(self.view, 'reset_button'):
            self.view.reset_button.setEnabled(has_changes)

        """
    재 모델 데이터 반환
    """
    def get_current_data(self):
        return self.model.get_dataframe()

    """
    데이터 리셋
    """
    def reset_data(self):
        self.model.reset()

    """
    변경사항 적용
    """
    def apply_changes(self):
        self.model.apply()

    """
    모델을 완전히 새로운 데이터로 업데이트

    parameter:
        new_data: 사용할 새 데이터가 포함된 DataFrame
    """
    def update_model_data(self, new_df: pd.DataFrame) -> bool:
        if hasattr(self.model, 'set_new_dataframe'):
            self.model.set_new_dataframe(new_df)
            return True
        else:
            print("Controller: model이 set_new_dataframe을 지원하지 않음")
            return False


   