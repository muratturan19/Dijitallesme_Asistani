"""LLM prompt builder for deep learning analysis."""
from __future__ import annotations

import json
from typing import Any, Dict

from ..prompts import DL_ANALYSIS_PROMPT


class LLMAnalyzer:
    """Helper to build structured prompts for the analysis LLM."""

    def __init__(self, prompt_template: str = DL_ANALYSIS_PROMPT) -> None:
        self.prompt_template = prompt_template

    def build_prompt(
        self,
        metrics: Dict[str, Any],
        config: Dict[str, Any],
        recall: float,
        precision: float,
    ) -> str:
        """Format the default prompt using analysis context values."""

        metrics_text = json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True)
        config_text = json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True)

        return self.prompt_template.format(
            metrics=metrics_text,
            config=config_text,
            recall=f"{recall:.2f}",
            precision=f"{precision:.2f}",
        )


__all__ = ["LLMAnalyzer"]
