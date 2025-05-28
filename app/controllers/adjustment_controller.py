from PyQt5.QtCore import QObject, QTimer
from typing import Any, Dict
import uuid
import pandas as pd
from app.utils.item_key_manager import ItemKeyManager

"""
Controller 역할:
    - View에서 발생한 사용자 액션을 Model에 전달
    - Model에서 발생한 변경/오류 시그널을 View에 전달

model: AssignmentModel 인스턴스
view: AdjustmentView 인스턴스
"""
class AdjustmentController(QObject):

    def __init__(self, model: Any, view: Any, error_manager):
        super().__init__()
        self.model = model
        self.view = view  # ModifiedLeftSection
        self.error_manager = error_manager
        self.result_page = None  # 명시적으로 초기화 (result_page는 외부에서 설정)
        
        # 시그널 연결 상태 추적 (중복 연결 방지)
        self._signals_connected = False

        # 초기화 상태 추적
        self._views_initialized = False
        self._processing_move = False

    """
    ResultPage 참조 설정
    """
    def set_result_page(self, result_page):
        self.result_page = result_page
        print("Controller: ResultPage 참조 설정됨")


    """
    초기 데이터로 뷰 초기화 (시그널 연결 전에 호출)
    """
    def initialize_views(self):
        # 이미 초기화된 경우 중복 초기화 방지
        if self._views_initialized:
            print("Controller: 뷰가 이미 초기화되어 있어 중복 초기화를 방지합니다.")
            return False
        
        df = self.model.get_dataframe()
        
        # 왼쪽 섹션 초기화
        self.view.set_data_from_external(df)
        print("Controller: initialize_views 왼쪽 섹션 초기화)")
        
        # ResultPage 초기화 (설정된 경우)
        if self.result_page and hasattr(self.result_page, 'on_data_changed'):
            self.result_page.on_data_changed(df)
            print("Controller: initialize_views 오른쪽 섹션 초기화)")

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
            print("Controller: 시그널이 이미 연결되어 있어 중복 연결을 방지합니다.")
            return False
        
        # Model -> Error Manager
        self.model.validationFailed.connect(self.error_manager.add_validation_error)
        print("Controller: 에러 매니저 시그널 연결")
        
        # Model -> Controller (데이터 변경 시)
        self.model.modelDataChanged.connect(self._on_model_data_changed)
        print("Controller: modelDataChanged 시그널 연결")
        
        # View -> Controller (아이템 데이터 변경)
        if hasattr(self.view, 'itemModified'):
            print("Controller: itemModified 시그널 연결")
            self.view.itemModified.connect(self._on_item_data_changed)
        
        # View -> Controller (셀 이동)  
        if hasattr(self.view, 'cellMoved'):
            print("Controller: cellMoved 시그널 연결")
            self.view.cellMoved.connect(self._on_cell_moved)

        # View -> Controller (아이템 삭제) - 이 부분이 추가되어야 함
        if hasattr(self.view, 'grid_widget') and hasattr(self.view.grid_widget, 'itemRemoved'):
            print("Controller: itemRemoved 시그널 연결")
            self.view.grid_widget.itemRemoved.connect(self.on_item_deleted)
        
        # View -> Controller (아이템 복사)
        if hasattr(self.view, 'grid_widget') and hasattr(self.view.grid_widget, 'itemCopied'):
            print("Controller: itemCopied 시그널 연결")
            self.view.grid_widget.itemCopied.connect(self.on_item_copied)

        # 모델의 데이터 변경 상태 시그널 연결
        if hasattr(self.model, 'dataModified'):
            self.model.dataModified.connect(self.on_data_modified)

        # 연결 완료 상태 설정
        self._signals_connected = True        
        print("Controller: 시그널 연결 완료")
        return True


    """
    아이템 데이터 변경 처리
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
        
        # changed_fields를 활용한 더 정확한 판단
        if changed_fields:
            # Line 또는 Time 변경 = 이동
            if 'Line' in changed_fields or 'Time' in changed_fields:
                print(f"Controller: 아이템 이동 {code}")

                # 이전 위치 정보 가져오기
                old_line = changed_fields.get('Line', {}).get('from', line)
                old_time = changed_fields.get('Time', {}).get('from', time)
                print(f"이전 위치정보: 라인-{old_line} / 타임-{old_time}")

                self.model.move_item(code, old_line, old_time, line, time, item_id)
                return
        
        # 수량 변경 - 라인과 시간 정보도 함께 전달
        if 'Qty' in new_data and line and time is not None:
            qty = new_data['Qty']
            print(f"Controller: 수량 변경 {code} @ {line}-{time} -> {qty}")
            # 수정된 모델의 update_qty 메서드 호출 (라인, 시간 포함)
            self.model.update_qty(code, line, time, qty, item_id)


    """
    모델 데이터가 바뀔 때마다 뷰를 업데이트
    - 전체 덮어쓰기보다는 델타 업데이트가 더 효율적일 수 있음
    """
    def _on_model_data_changed(self):
        print("Controller: Model 변경 감지, View 업데이트")
        df = self.model.get_dataframe()
        
        # left_section(View) 업데이트
        self.view.update_from_model(df)
        print("Controller: view.update_from_model 업데이트")
        

        if self.result_page:
            if hasattr(self.result_page, 'update_ui_from_model'):
                print("Controller: result_page.update_ui_from_model 호출")
                self.result_page.update_ui_from_model(df)
            elif hasattr(self.result_page, 'on_data_changed'):
                print("Controller: result_page.on_data_changed 호출")
                self.result_page.on_data_changed(df)
        
        self.error_manager.update_error_display()

    """
    드래그·드롭으로 위치 이동했을 때
    - Controller가 모든 셀 이동 로직 처리
    - 필요시 추가 로직 (시각화 업데이트 등) 수행
    """

    def _on_cell_moved(self, item, old_data, new_data):
        # 중복 처리 방지
        if self._processing_move:
            print("Controller: 이동 처리 중복 방지")
            return

        self._processing_move = True

        try:
            code = new_data.get('Item')
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
        finally:
            # 처리 완료 후 플래그 해제
            QTimer.singleShot(100, lambda: setattr(self, '_processing_move', False))

    """아이템 ID를 기반으로 해당 아이템으로 스크롤"""
    def _ensure_item_visible(self, item_id):
        if not item_id or not hasattr(self.view, 'grid_widget'):
            return

        # 뷰의 _scroll_to_selected_item 메서드 호출
        if hasattr(self.view, '_scroll_to_selected_item'):
            self.view._scroll_to_selected_item(item_id)
        
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
    복사된 아이템 처리

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
    삭제된 아이템 처리
    """
    def on_item_deleted(self, item_or_id):
        print("DEBUG: AdjustmentController.on_item_deleted 호출됨")

        # item_or_id가 문자열(ID)인 경우
        if isinstance(item_or_id, str):
            item_id = item_or_id
            print(f"DEBUG: ID로 삭제: {item_id}")
            return self.model.delete_item_by_id(item_id)

        if hasattr(item_or_id, 'item_data') and item_or_id.item_data:
            # ItemKeyManager를 사용하여 아이템 정보 추출
            line, time, item_code = ItemKeyManager.get_item_from_data(item_or_id.item_data)
            
            # ID가 있으면 ID 기반으로 삭제
            item_id = ItemKeyManager.extract_item_id(item_or_id)
            if item_id:
                print(f"컨트롤러: 아이템 삭제 처리 - ID: {item_id}")
                return self.model.delete_item_by_id(item_id)
            
            # ID가 없으면 Line/Time/Item 기반으로 삭제
            if line is not None and time is not None and item_code is not None:
                print(f"컨트롤러: 아이템 삭제 처리 - {item_code} @ {line}-{time}")
                return self.model.delete_item(item_code, line, time)
        
        return 
    

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
        
    """
    데이터 원본 복원
    """
    def reset_data(self):
        print("Controller: reset_data 호출")
        if hasattr(self, 'model') and self.model:
            # 모델에 리셋 요청
            self.model.reset()
            print("Controller: 모델 reset 완료")
        else:
            print("Controller: 모델을 찾을 수 없음")

    """
    모델 데이터의 변경 상태에 따라 리셋 버튼 상태 업데이트
    """
    def on_data_modified(self, has_changes: bool):
        if hasattr(self.view, 'reset_button'):
            self.view.reset_button.setEnabled(has_changes)