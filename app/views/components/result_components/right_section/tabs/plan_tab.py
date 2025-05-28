from PyQt5.QtWidgets import QWidget, QVBoxLayout
from app.views.components.result_components.table_widget.maintenance_rate.plan_maintenance_widget import PlanMaintenanceWidget


class PlanTab(QWidget):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_page = parent
        self.plan_maintenance_widget = None
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 계획 유지율 위젯 생성
        self.plan_maintenance_widget = PlanMaintenanceWidget()
        layout.addWidget(self.plan_maintenance_widget)
        
        # 부모의 plan_maintenance_widget 속성 설정 (호환성)
        if hasattr(self.parent_page, 'plan_maintenance_widget'):
            self.parent_page.plan_maintenance_widget = self.plan_maintenance_widget
    
        
    """
    데이터 설정
    """
    def set_data(self, data, start_date, end_date):
        if self.plan_maintenance_widget:
            self.plan_maintenance_widget.set_data(data, start_date, end_date)
    
    """
    수량 업데이트
    """
    def update_quantity(self, line, time, item, qty):
        if self.plan_maintenance_widget:
            self.plan_maintenance_widget.update_quantity(line, time, item, qty)
    
    """
    콘텐츠 업데이트
    """
    def update_content(self, data=None):
        if data is not None and self.plan_maintenance_widget:
            # 날짜 범위 가져오기
            if (hasattr(self.parent_page, 'main_window') and 
                hasattr(self.parent_page.main_window, 'data_input_page')):
                start_date, end_date = self.parent_page.main_window.data_input_page.date_selector.get_date_range()
                self.set_data(data, start_date, end_date)
    
    """
    위젯 반환
    """
    def get_widget(self):
        return self.plan_maintenance_widget