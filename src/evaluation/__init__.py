"""RAG 评估模块

支持自动化评估：
- 检索质量：context_recall, context_precision
- 生成质量：faithfulness, answer_relevancy
- 端到端：answer_correctness

Usage:
    from src.evaluation import RAGEvaluator

    evaluator = RAGEvaluator()
    metrics = evaluator.evaluate_single(query, answer, contexts, ground_truth)
"""

from src.evaluation.rag_evaluator import RAGEvaluator

__all__ = ["RAGEvaluator"]
