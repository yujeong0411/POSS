import pandas as pd
from app.analysis.output.kpi_score import KpiScore
from app.analysis.output.material_shortage_analysis import MaterialShortageAnalyzer
from app.analysis.output.daily_capa_utilization import CapaUtilization
from app.analysis.output.capa_ratio import CapaRatioAnalyzer
from app.models.common.file_store import DataStore
from app.analysis.output.plan_maintenance import PlanMaintenanceAnalyzer

"""
모든 분석을 담당하는 클래스
"""
class AnalysisManager:
    
    def __init__(self, result_page, controller=None):
        self.result_page = result_page
        self.controller = controller
        self.engines = self._initialize_engines()

    """
    모든 분석 엔진을 Controller에서 초기화
    """
    def _initialize_engines(self):
        engines = {}
        
        try:
            # KPI 분석 엔진 (ResultPage 필요)
            if hasattr(self.result_page, 'main_window'):
                engines['kpi'] = KpiScore(self.result_page.main_window)
            else:
                engines['kpi'] = None
            
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
    모든 분석의 단일 진입점
    """
    def run_all_analyses(self, df):
        print("AnalysisManager: 분석 시작")
        
        if df is None or df.empty:
            return self._get_empty_results()
        
        results = {}
        
        # 1. KPI 분석
        results['kpi'] = self._run_kpi_analysis(df)
        
        # 2. 자재 분석
        results['material'] = self._run_material_analysis(df)
        
        # 3. 출하 분석
        results['shipment'] = self._run_shipment_analysis(df)
        
        # 4. 가동률 분석
        results['utilization'] = self._run_utilization_analysis(df)
        
        # 5. 제조동 비율 분석
        results['capa_ratio'] = self._run_capa_analysis(df)
        
        # 6. 계획 유지율 분석
        results['plan_maintenance'] = self._run_plan_maintenance_analysis(df)
        
        # 7. 분산 배치 분석
        results['split_allocation'] = self._run_split_allocation_analysis(df)

        # 8. PortCapa 분석 추가
        results['portcapa'] = self._run_portcapa_analysis(df)
        
        # 9. 요약 분석
        results['summary'] = self._run_summary_analysis(df)
        
        print("AnalysisManager: 모든 분석 완료")
        return results
    
    """
    KPI 분석 - 기존 로직을 별도 메서드로 분리
    """
    def _run_kpi_analysis(self, df):
        try:
            kpi_engine = self.engines['kpi']
            
            # 데이터 설정
            demand_df = self._get_demand_data()
            material_analyzer = self.engines.get('material')
            kpi_engine.set_data(df, material_analyzer, demand_df)
            
            # Base/Adjust 점수 계산
            base_scores = kpi_engine.calculate_all_scores()
            
            # 조정 여부 확인
            has_adjustments = self._check_for_adjustments()
            if has_adjustments:
                # 조정된 데이터로 다시 계산
                adjust_scores = kpi_engine.calculate_all_scores()
                return {
                    'base_scores': base_scores,
                    'adjust_scores': adjust_scores
                }
            else:
                return {
                    'base_scores': base_scores,
                    'adjust_scores': {}
                }
            
        except Exception as e:
            print(f"KPI 분석 오류: {e}")
            return {'base_scores': {}, 'adjust_scores': {}}
    
    """
    출하 분석 중앙집중화 - 한 곳에서만 실행
    """
    def _run_shipment_analysis(self, df):
        try:
            if (self.result_page and 
                hasattr(self.result_page, 'shipment_widget') and 
                self.result_page.shipment_widget):
                
                print("    → 출하 위젯 분석 실행")
                self.result_page.shipment_widget.run_analysis(df)
                
                # 🔧 분석 결과를 바로 가져와서 반환
                failure_items = getattr(self.result_page.shipment_widget, 'failure_items', {})
                
                return {
                    'analyzed': True,
                    'failure_items': failure_items
                }
        except Exception as e:
            print(f"출하 분석 오류: {e}")
            
        return {'analyzed': False, 'failure_items': {}}
    
    """
    가동률 분석
    """
    def _run_utilization_analysis(self, df):
        try:
            if self.engines.get('utilization'):
                utilization_engine = self.engines['utilization']
                has_adjustments = self._check_for_adjustments()

                if has_adjustments:
                    # 조정이 있는 경우: 원본과 조정된 데이터 모두 분석
                    comparison_df = self.controller.model.get_comparison_dataframe()
                    if comparison_df:
                        return {
                            'original': utilization_engine.analyze_utilization(comparison_df['original']),
                            'adjusted': utilization_engine.analyze_utilization(comparison_df['adjusted'])
                        }
                else:
                    # 조정이 없는 경우: 현재 데이터만 분석
                    return utilization_engine.analyze_utilization(df)
        except Exception as e:
            print(f"가동률 분석 오류: {e}")
        return {}

    """
    제조동 비율 분석
    """
    def _run_capa_analysis(self, df):
        try:
            if self.engines.get('capa_ratio'):
                capa_engine = self.engines['capa_ratio']
                has_adjustments = self._check_for_adjustments()
                
                if has_adjustments:
                    comparison_df = self.controller.model.get_comparison_dataframe()
                    if comparison_df:
                        return {
                            'original': capa_engine.analyze_capa_ratio(comparison_df['original']),
                            'adjusted': capa_engine.analyze_capa_ratio(comparison_df['adjusted'])
                        }
                else:
                    return capa_engine.analyze_capa_ratio(data_df=df, is_initial=True)
        except Exception as e:
            print(f"제조동 비율 분석 오류: {e}")
        return {}
    

    """
    자재 분석
    """
    def _run_material_analysis(self, df):
        try:
            if not self.engines.get('material'):
                return {'shortage_results': {}, 'analyzer': None}
                
            material_engine = self.engines['material']
            material_engine.analyze_material_shortage(df)
            
            return {
                'shortage_results': material_engine.shortage_results,
                'analyzer': material_engine
            }
        except Exception as e:
            print(f"자재 분석 오류: {e}")
            return {'shortage_results': {}, 'analyzer': None}

      
    """
    계획 유지율 분석
    """
    def _run_plan_maintenance_analysis(self, df):
        try:
            if (self.result_page and 
                hasattr(self.result_page, 'plan_maintenance_widget') and 
                self.result_page.plan_maintenance_widget):
                
                print("    → 계획 유지율 위젯 분석 실행")
                self.result_page.plan_maintenance_widget.run_analysis(df)
                return {'analyzed': True}
        except Exception as e:
            print(f"계획 유지율 분석 오류: {e}")
        
        return {'analyzed': False}
    
    """
    분산 배치 분석
    """
    def _run_split_allocation_analysis(self, df):
        try:
            if (self.result_page and 
                hasattr(self.result_page, 'split_allocation_widget') and 
                self.result_page.split_allocation_widget):
                
                self.result_page.split_allocation_widget.run_analysis(df)
                return {'analyzed': True}
        except Exception as e:
            print(f"분산 배치 분석 오류: {e}")
        
        return {'analyzed': False}

    """
    요약 분석
    """
    def _run_summary_analysis(self, df):
        try:
            if (self.result_page and 
                hasattr(self.result_page, 'summary_widget') and 
                self.result_page.summary_widget):
                
                self.result_page.summary_widget.run_analysis(df)
                return {'analyzed': True}
        except Exception as e:
            print(f"요약 분석 오류: {e}")
        
        return {'analyzed': False}
    
    """
    PortCapa 분석 - 새로 추가
    """
    def _run_portcapa_analysis(self, df):
        try:
            if (self.result_page and 
                hasattr(self.result_page, 'portcapa_widget') and 
                self.result_page.portcapa_widget):
                
                print("    → PortCapa 위젯 분석 실행")
                self.result_page.portcapa_widget.run_analysis(df)
                return {'analyzed': True}
        except Exception as e:
            print(f"PortCapa 분석 오류: {e}")
        
        return {'analyzed': False}

    """
    사용자 조정 여부 확인
    """
    def _check_for_adjustments(self):
        try:
            if self.controller and hasattr(self.controller, 'model'):
                model = self.controller.model
                if hasattr(model, '_original_df') and hasattr(model, '_df'):
                    original_df = model._original_df
                    current_df = model._df
                
                    if original_df is not None and current_df is not None:
                        key_columns = ['Line', 'Time', 'Item', 'Qty']
                        for col in key_columns:
                            if col in original_df.columns and col in current_df.columns:
                                if not original_df[col].equals(current_df[col]):
                                    return True
            return False
        except:
            return False

    """
    Demand 데이터 가져오기
    """
    def _get_demand_data(self):
        try:
            organized = DataStore.get("organized_dataframes", {})
            return organized.get("demand", pd.DataFrame())
        except:
            return pd.DataFrame()

    """
    빈 분석 결과 반환
    """
    def _get_empty_results(self):
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
    


