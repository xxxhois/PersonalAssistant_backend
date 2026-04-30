import pytest
import json
from src.parsers.shadow_parser import ShadowParser
from src.schemas.sse import SSEEventType

def test_shadow_parser_mixed_content():
    """测试 ShadowParser 混合内容解析：口语文本 + 标记块"""
    parser = ShadowParser()
    
    # 模拟流式输入
    chunk1 = "好的，这是你的计划："
    chunk2 = "<!--TASK_START-->"
    chunk3 = '{"type": "PLAN_UPDATE", "payload": {"id": "123"}}'
    chunk4 = "<!--TASK_END-->"
    chunk5 = " 请确认。"

    events = []
    events.extend(parser.feed(chunk1))
    events.extend(parser.feed(chunk2))
    events.extend(parser.feed(chunk3))
    events.extend(parser.feed(chunk4))
    events.extend(parser.feed(chunk5))
    events.extend(parser.flush())

    # 验证事件序列
    assert len(events) >= 3
    
    # 第一个事件应该是 token
    assert events[0][0] == SSEEventType.TOKEN
    assert "好的，这是你的计划" in events[0][1]["token"]

    # 第二个事件应该是 task_event
    assert events[1][0] == SSEEventType.TASK_EVENT
    assert events[1][1]["type"] == "PLAN_UPDATE"
    assert events[1][1]["payload"]["id"] == "123"

    # 第三个事件应该是 token
    assert events[2][0] == SSEEventType.TOKEN
    assert "请确认" in events[2][1]["token"]

def test_shadow_parser_split_markers():
    """测试 ShadowParser 处理被切断的标记"""
    parser = ShadowParser()
    
    # 将标记切断在两个 chunk 中
    chunk1 = "Text before <!--TASK_ST"
    chunk2 = "ART-->"
    chunk3 = '{"id": 1}'
    chunk4 = "<!--TASK_EN"
    chunk5 = "D--> Text after"

    events = []
    events.extend(parser.feed(chunk1))
    events.extend(parser.feed(chunk2))
    events.extend(parser.feed(chunk3))
    events.extend(parser.feed(chunk4))
    events.extend(parser.feed(chunk5))
    events.extend(parser.flush())

    # 验证事件
    token_events = [e for e in events if e[0] == SSEEventType.TOKEN]
    task_events = [e for e in events if e[0] == SSEEventType.TASK_EVENT]

    assert any("Text before" in e[1]["token"] for e in token_events)
    assert any("Text after" in e[1]["token"] for e in token_events)
    assert len(task_events) == 1
    assert task_events[0][1]["id"] == 1

def test_shadow_parser_invalid_json():
    """测试 ShadowParser 处理非法 JSON"""
    parser = ShadowParser()
    
    chunk1 = "<!--TASK_START--> {invalid json} <!--TASK_END-->"
    events = parser.feed(chunk1)
    
    # 应该产生一个 ERROR 事件
    error_events = [e for e in events if e[0] == SSEEventType.ERROR]
    assert len(error_events) == 1
    assert error_events[0][1]["code"] == "PARSER_JSON_ERROR"
    assert error_events[0][1]["recoverable"] is False
