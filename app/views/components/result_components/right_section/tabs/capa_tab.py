from PyQt5.QtWidgets import QWidget, QVBoxLayout
from app.views.components.visualization.mpl_canvas import MplCanvas
from app.views.components.visualization.visualization_updater import VisualizationUpdater


class CapaTab(QWidget):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_page = parent
        self.capa_canvas = None
        self.util_canvas = None
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Capa 차트 캔버스
        self.capa_canvas = MplCanvas(width=4, height=5, dpi=100)
        layout.addWidget(self.capa_canvas)
        
        # 여백 추가
        layout.addSpacing(5)
        
        # Utilization 차트 캔버스
        self.util_canvas = MplCanvas(width=5, height=5, dpi=100)
        layout.addWidget(self.util_canvas)
    
    """
    콘텐츠 업데이트
    """
    def update_content(self, capa_data, utilization_data):
        if self.capa_canvas and capa_data is not None:
            VisualizationUpdater.update_capa_chart(self.capa_canvas, capa_data)
        
        if self.util_canvas and utilization_data is not None:
            VisualizationUpdater.update_utilization_chart(self.util_canvas, utilization_data)
    
    """
    캔버스들 반환
    """
    def get_canvases(self):
        return [self.capa_canvas, self.util_canvas]
    
    """
    초기 시각화 생성
    """
    def create_initial_visualizations(self, capa_data, utilization_data):
        if self.capa_canvas:
            VisualizationUpdater.update_capa_chart(self.capa_canvas, capa_data)
        
        if self.utilization_canvas:
            VisualizationUpdater.update_utilization_chart(self.util_canvas, utilization_data)