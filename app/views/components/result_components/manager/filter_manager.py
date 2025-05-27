from PyQt5.QtCore import QObject, QTimer
import time

"""
필터 관련 로직 담당 
"""
class FilterManager(QObject):
    def __init__(self, left_section):
        super().__init__()
        self.left_section = left_section

        # 최적화
        self._filter_timer = QTimer()
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self._process_filter_changes)
        self._pending_filter_changes = {}
        self._filter_cache = {}

    """
    외부 호출용 메인 필요 적용 메서드
    """
    def apply_filters(self, filter_states):
        if self._pending_filter_changes == filter_states:
            return
        
        print(f"[FilterManager] 필터 변경 예약")
        self._pending_filter_changes = filter_states.copy()
        self._filter_timer.start(100)  # 디바운싱

    """
    실제 필터 적용 로직
    """
    def _process_filter_changes(self):
        filter_states = self._pending_filter_changes
        cache_key = str(sorted(filter_states.itmes()))

        start_time = time.time()

        # 캐시 확인
        if cache_key in self._filter_cache:
            visible_items = self._filter_cache[cache_key]
        else:
            visible_items = self._calculate_visible_item(filter_states)
            self._filter_cache[cache_key] = visible_items

        # 가시성 적용
        self._apply_visibility_changes(visible_items)
        self._update_status_lines(filter_states)

        end_time = time.time()
        print(f"[FilterManager] 필터 적용 완료: {end_time-start_time:.3f}초")
        

    """
    가시성 계산 로직
    """
    def _calculate_visible_items(self, filter_states):
            visible_items = set()
            
            if not any(filter_states.values()):
                return {id(item) for item in self.left_section.all_items}
            
            for item in self.left_section.all_items:
                if self._should_item_be_visible(item, filter_states):
                    visible_items.add(id(item))
                    
            return visible_items
    
    """
    개별 아이템 가시성 판단
    """
    def _should_item_be_visible(self, item, filter_states):
        if not any(filter_states.values()):
            return True
            
        if filter_states.get('shortage') and not getattr(item, 'is_shortage', False):
            return False
        if filter_states.get('shipment') and not getattr(item, 'is_shipment_failure', False):
            return False
        if filter_states.get('pre_assigned') and not getattr(item, 'is_pre_assigned', False):
            return False
            
        return True


    """
    가시성 변경 적용
    """
    def _apply_visibility_changes(self, visible_items):
        for item in self.left_section.all_items:
            should_visible = id(item) in visible_items
            if item.isVisible() != should_visible:
                item.setVisible(should_visible)
                
    """
    상태선 업데이트
    """
    def _update_status_lines(self, filter_states):
        for item in self.left_section.all_items:
            # 기존 update_item_status_line_visibility 로직을 여기로 이동
            self._update_single_item_status_line(item, filter_states)
            
    """
    개별 아이템 상태선 업데이트
    """
    def _update_single_item_status_line(self, item, filter_states):
        shortage_filter = filter_states.get('shortage', False)
        shipment_filter = filter_states.get('shipment', False)
        pre_assigned_filter = filter_states.get('pre_assigned', False)
        
        if hasattr(item, 'show_shortage_line'):
            item.show_shortage_line = shortage_filter and getattr(item, 'is_shortage', False)
        if hasattr(item, 'show_shipment_line'):
            item.show_shipment_line = shipment_filter and getattr(item, 'is_shipment_failure', False)
        if hasattr(item, 'show_pre_assigned_line'):
            item.show_pre_assigned_line = pre_assigned_filter and getattr(item, 'is_pre_assigned', False)
            
        item.update()


