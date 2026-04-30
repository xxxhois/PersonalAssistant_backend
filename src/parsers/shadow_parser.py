import json
from typing import Optional, List, Tuple, Dict, Any
from src.schemas.sse import SSEEventType
from src.schemas.htn import JsonValue

class ShadowParser:
    """
    ShadowParser 实现 (ShadowParser)
    遵循架构约束：仅信任 <!--TASK_START-->...<!--TASK_END-->，输出多 Event 类型
    采用状态机处理流式 Buffer，支持跨 Chunk 的标记块提取。
    """
    START_MARKER = "<!--TASK_START-->"
    END_MARKER = "<!--TASK_END-->"

    def __init__(self) -> None:
        self.buffer = ""
        self.in_block = False

    def feed(self, chunk: str) -> List[Tuple[SSEEventType, JsonValue]]:
        """
        输入流式 Chunk，返回解析出的 SSE 事件列表
        """
        self.buffer += chunk
        events: List[Tuple[SSEEventType, JsonValue]] = []

        while True:
            if not self.in_block:
                # 寻找开始标记
                start_idx = self.buffer.find(self.START_MARKER)
                if start_idx == -1:
                    # 全是普通文本
                    if self.buffer:
                        # 留下一部分 buffer 防止标记被截断
                        text_to_send = self._safe_text_extract()
                        if text_to_send:
                            events.append((SSEEventType.TOKEN, {"token": text_to_send}))
                    break
                else:
                    # 发送开始标记前的文本
                    pre_text = self.buffer[:start_idx]
                    if pre_text:
                        events.append((SSEEventType.TOKEN, {"token": pre_text}))
                    
                    self.buffer = self.buffer[start_idx + len(self.START_MARKER):]
                    self.in_block = True
            else:
                # 寻找结束标记
                end_idx = self.buffer.find(self.END_MARKER)
                if end_idx == -1:
                    # 块未结束，继续等待
                    break
                else:
                    # 提取并解析 JSON 块
                    json_str = self.buffer[:end_idx].strip()
                    try:
                        payload = json.loads(json_str)
                        events.append((SSEEventType.TASK_EVENT, payload))
                    except json.JSONDecodeError:
                        # 容错处理：记录解析失败，不中断流
                        events.append((SSEEventType.ERROR, {
                            "code": "PARSER_JSON_ERROR",
                            "message": "Failed to parse task JSON",
                            "recoverable": False
                        }))
                    
                    self.buffer = self.buffer[end_idx + len(self.END_MARKER):]
                    self.in_block = False

        return events

    def _safe_text_extract(self) -> str:
        """安全提取文本，只保留可能属于标记前缀的尾部"""
        markers = [self.START_MARKER, self.END_MARKER]

        # 找到 buffer 尾部最长的“可能是某个 marker 开头”的片段
        keep_len = 0
        max_check_len = min(len(self.buffer), max(len(m) for m in markers))

        for i in range(1, max_check_len + 1):
            suffix = self.buffer[-i:]
            if any(marker.startswith(suffix) for marker in markers):
                keep_len = i

        if keep_len == 0:
            text = self.buffer
            self.buffer = ""
            return text

        text = self.buffer[:-keep_len]
        self.buffer = self.buffer[-keep_len:]
        return text

    def flush(self) -> List[Tuple[SSEEventType, JsonValue]]:
        """刷新剩余 Buffer (流结束时调用)"""
        events: List[Tuple[SSEEventType, JsonValue]] = []
        if self.buffer and not self.in_block:
            events.append((SSEEventType.TOKEN, {"token": self.buffer}))
            self.buffer = ""
        return events
