"""
自主任务规划专用 Prompt 模板
覆盖三个阶段：
1. 生成澄清选择题
2. 多轮循环拆分（HTN 分层任务网络）
3. 原子任务生成
"""


class PlanningPrompts:
    """任务规划 Prompt 集合"""

    # ─── 阶段一：根据目标生成澄清选择题 ───

    @staticmethod
    def build_clarify_questions_prompt(goal_description: str) -> str:
        """
        根据用户目标描述生成 3-5 个选择题，用于收集规划所需的关键信息。
        """
        return f"""你是一个专业的任务规划助手。用户描述了一个目标，你需要分析这个目标的详细程度，
然后生成 3-5 个关键的选择题来收集规划所需的信息。

用户目标：{goal_description}

请根据以下维度生成选择题（根据目标类型选择最相关的维度）：
- 时间维度：期望完成的总时长/截止日期
- 当前水平：用户在该领域的现有基础
- 投入程度：每天/每周可投入的时间
- 优先级偏好：更注重速度还是质量
- 资源条件：可用的工具、预算、环境等

输出要求：严格按以下 JSON 格式返回，不要包含任何其他文字：
{{
  "goal_summary": "对用户目标的一句话复述",
  "questions": [
    {{
      "question_id": "q1",
      "question_text": "问题文本",
      "options": [
        {{"key": "A", "label": "选项A文本"}},
        {{"key": "B", "label": "选项B文本"}},
        {{"key": "C", "label": "选项C文本"}},
        {{"key": "D", "label": "选项D文本"}}
      ],
      "allow_multiple": false
    }}
  ]
}}

注意：
1. 问题数量 3-5 个，根据目标的模糊程度决定（越模糊越多）
2. 每个问题 3-4 个选项
3. 问题应该互补，覆盖不同维度
4. 使用中文
5. 选项应该具体、可操作，避免模糊表述"""

    # ─── 阶段二：高层拆分（目标 → 阶段性子目标） ───

    @staticmethod
    def build_high_level_decompose_prompt(
        goal_description: str,
        clarify_context: str,
    ) -> str:
        """
        第一轮拆分：将大目标拆解为 3-7 个阶段性子目标。
        """
        return f"""你是一个专业的任务规划助手，擅长将宏大目标拆解为可执行的阶段。

## 用户目标
{goal_description}

## 用户补充信息
{clarify_context}

## 任务
请将上述目标拆解为 3-7 个**阶段性子目标**（里程碑），每个子目标应该：
- 有明确的完成标准
- 有合理的时间跨度（几天到几周）
- 按逻辑顺序排列
- 前后有依赖关系

严格按以下 JSON 格式返回，不要包含任何其他文字：
{{
  "progress_message": "一句话描述你的拆分思路",
  "milestones": [
    {{
      "id": "m1",
      "title": "阶段标题",
      "description": "阶段描述和完成标准",
      "estimated_days": 7,
      "order": 1
    }}
  ]
}}"""

    # ─── 阶段二续：中层拆分（阶段 → 具体任务） ───

    @staticmethod
    def build_mid_level_decompose_prompt(
        goal_description: str,
        milestone_title: str,
        milestone_description: str,
        clarify_context: str,
    ) -> str:
        """
        第二轮拆分：将阶段性子目标拆解为具体的日级任务。
        """
        return f"""你是一个专业的任务规划助手，正在将一个阶段性目标细化为具体任务。

## 总体目标
{goal_description}

## 当前阶段
标题：{milestone_title}
描述：{milestone_description}

## 用户背景
{clarify_context}

## 任务
请将当前阶段拆解为具体的任务，每个任务应该：
- 可在半天到一天内完成
- 有明确的行动描述
- 按执行顺序排列

严格按以下 JSON 格式返回，不要包含任何其他文字：
{{
  "progress_message": "一句话描述当前阶段的拆分思路",
  "tasks": [
    {{
      "id": "t1",
      "title": "任务标题",
      "description": "具体要做什么",
      "estimated_hours": 2,
      "order": 1
    }}
  ]
}}"""

    # ─── 阶段三：原子化拆分（日级任务 → 原子任务） ───

    @staticmethod
    def build_atomic_decompose_prompt(
        goal_description: str,
        task_title: str,
        task_description: str,
        estimated_hours: float,
        clarify_context: str,
    ) -> str:
        """
        第三轮拆分：将日级任务拆解为原子级任务（30min-2h）。
        仅当任务预估时间 > 2h 时才需要进一步拆分。
        """
        return f"""你是一个专业的任务规划助手，正在将任务细化为可立即执行的原子步骤。

## 总体目标
{goal_description}

## 当前任务
标题：{task_title}
描述：{task_description}
预估耗时：{estimated_hours} 小时

## 用户背景
{clarify_context}

## 任务
请将当前任务拆解为**原子级步骤**，每个步骤应该：
- 可在 30 分钟到 2 小时内完成
- 描述具体、明确，看到就知道该做什么
- 包含建议的执行时间段

严格按以下 JSON 格式返回，不要包含任何其他文字：
{{
  "progress_message": "一句话描述拆分结果",
  "atomic_tasks": [
    {{
      "title": "原子任务标题",
      "description": "具体行动描述",
      "estimated_duration_minutes": 60,
      "suggested_time_slot": "09:00-10:00",
      "order": 1
    }}
  ]
}}"""

    # ─── 系统提示词 ───

    @staticmethod
    def get_planning_system_prompt() -> str:
        """规划模式的系统提示词"""
        return (
            "你是一个专业的个人任务规划助手，擅长使用分层任务网络（HTN）方法将宏大目标逐步拆解为可执行的原子任务。\n\n"
            "核心原则：\n"
            "1. 自顶向下拆分：大目标 → 阶段里程碑 → 日级任务 → 原子步骤\n"
            "2. 每个原子任务应在 30 分钟到 2 小时内可完成\n"
            "3. 任务描述要具体、可操作，避免模糊表述\n"
            "4. 考虑任务间的依赖关系和逻辑顺序\n"
            "5. 根据用户的实际情况（水平、时间、资源）调整难度和节奏\n\n"
            "输出规范：\n"
            "- 始终返回合法的 JSON 格式\n"
            "- 不要在 JSON 外添加任何解释文字\n"
            "- 使用中文"
        )
