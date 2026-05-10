"""RAG 评估器

基于 RAGAS 框架，自动化评估 RAG 系统效果。
核心指标：
- context_recall: 相关文档是否被召回
- context_precision: 召回的文档是否相关
- faithfulness: 答案是否基于上下文（无幻觉）
- answer_relevancy: 答案是否回答了用户问题
- answer_correctness: 答案的事实准确性
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any

from langchain_core.documents import Document


@dataclass
class EvalResult:
    """单次评估结果"""
    query: str
    answer: str
    contexts: list[str]
    ground_truth: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    passed: bool = True
    details: dict = field(default_factory=dict)


class RAGEvaluator:
    """RAG 自动化评估器"""

    def __init__(self, llm_base_url: str = None, llm_api_key: str = None, llm_model: str = None):
        self.llm_base_url = llm_base_url or os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
        self.llm_api_key = llm_api_key or os.getenv("LLM_API_KEY", "not-needed")
        self.llm_model = llm_model or os.getenv("LLM_MODEL", "qwen2.5:3b")
        self._ragas_available = self._check_ragas()

    def _check_ragas(self) -> bool:
        try:
            import ragas
            return True
        except ImportError:
            return False

    def evaluate_single(
        self,
        query: str,
        answer: str,
        contexts: list[str] | list[Document],
        ground_truth: str | None = None,
    ) -> EvalResult:
        """评估单次问答"""
        if isinstance(contexts[0], Document):
            contexts = [c.page_content for c in contexts]

        result = EvalResult(
            query=query,
            answer=answer,
            contexts=contexts,
            ground_truth=ground_truth,
        )

        if self._ragas_available:
            result.metrics = self._evaluate_with_ragas(query, answer, contexts, ground_truth)
        else:
            result.metrics = self._evaluate_heuristic(query, answer, contexts, ground_truth)

        # 判定是否通过（faithfulness > 0.7 且 answer_relevancy > 0.7）
        result.passed = (
            result.metrics.get("faithfulness", 0) >= 0.7
            and result.metrics.get("answer_relevancy", 0) >= 0.7
        )

        return result

    def _evaluate_with_ragas(
        self,
        query: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None,
    ) -> dict[str, float]:
        """使用 RAGAS 框架评估"""
        try:
            from ragas import evaluate
            from ragas.metrics import (
                faithfulness,
                answer_relevancy,
                context_recall,
                context_precision,
                answer_correctness,
            )
            from datasets import Dataset

            data = {
                "question": [query],
                "answer": [answer],
                "contexts": [contexts],
            }
            if ground_truth:
                data["ground_truth"] = [ground_truth]

            dataset = Dataset.from_dict(data)

            metrics = [faithfulness, answer_relevancy, context_recall, context_precision]
            if ground_truth:
                metrics.append(answer_correctness)

            result = evaluate(dataset, metrics=metrics)
            return {k: round(float(v), 3) for k, v in result.items()}
        except Exception as e:
            return {"error": str(e)}

    def _evaluate_heuristic(
        self,
        query: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None,
    ) -> dict[str, float]:
        """启发式评估（RAGAS 未安装时的降级方案）"""
        import re

        metrics = {}

        # Faithfulness: 答案中的关键信息是否在上下文中
        answer_words = set(re.findall(r"\b\w{2,}\b", answer.lower()))
        context_text = " ".join(contexts).lower()
        context_words = set(re.findall(r"\b\w{2,}\b", context_text))

        if answer_words:
            overlap = len(answer_words & context_words) / len(answer_words)
            metrics["faithfulness"] = round(min(overlap * 1.5, 1.0), 3)  # 放大系数
        else:
            metrics["faithfulness"] = 0.0

        # Answer Relevancy: 答案与问题的词重叠
        query_words = set(re.findall(r"\b\w{2,}\b", query.lower()))
        if query_words:
            overlap = len(answer_words & query_words) / len(query_words)
            metrics["answer_relevancy"] = round(min(overlap * 2.0, 1.0), 3)
        else:
            metrics["answer_relevancy"] = 0.0

        # Context Recall: 问题关键词在上下文中的覆盖度
        if query_words:
            covered = sum(1 for w in query_words if w in context_text)
            metrics["context_recall"] = round(covered / len(query_words), 3)
        else:
            metrics["context_recall"] = 0.0

        # Context Precision: 上下文与问题的相关性（简化）
        if context_words:
            overlap = len(query_words & context_words) / len(context_words)
            metrics["context_precision"] = round(min(overlap * 3.0, 1.0), 3)
        else:
            metrics["context_precision"] = 0.0

        return metrics

    def evaluate_batch(
        self,
        test_cases: list[dict],
    ) -> dict[str, Any]:
        """批量评估

        test_cases: [
            {"query": "...", "answer": "...", "contexts": [...], "ground_truth": "..."},
            ...
        ]
        """
        results = []
        for case in test_cases:
            r = self.evaluate_single(
                query=case["query"],
                answer=case["answer"],
                contexts=case["contexts"],
                ground_truth=case.get("ground_truth"),
            )
            results.append(r)

        # 汇总统计
        metric_keys = results[0].metrics.keys() if results else []
        summary = {}
        for key in metric_keys:
            values = [r.metrics.get(key, 0) for r in results if key in r.metrics and not isinstance(r.metrics.get(key), str)]
            if values:
                summary[key] = {
                    "mean": round(sum(values) / len(values), 3),
                    "min": round(min(values), 3),
                    "max": round(max(values), 3),
                }

        pass_rate = sum(1 for r in results if r.passed) / len(results) if results else 0

        return {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "pass_rate": round(pass_rate, 3),
            "summary": summary,
            "results": [
                {
                    "query": r.query[:50],
                    "metrics": r.metrics,
                    "passed": r.passed,
                }
                for r in results
            ],
        }

    def generate_report(self, batch_result: dict, output_path: str = "data/eval_report.json") -> str:
        """生成评估报告并保存"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(batch_result, f, ensure_ascii=False, indent=2)
        return output_path
