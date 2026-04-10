"""Jinja2 prompt template loader with hot-reload support.

Loads templates from config/prompts/, renders with MarketContext variables,
and checks file mtime for hot-reload.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, Template

logger = logging.getLogger(__name__)

DEFAULT_PROMPTS_DIR = Path("config/prompts")


class PromptLoader:
    """Loads and renders Jinja2 prompt templates.

    Supports hot-reload: checks file modification time and reloads
    templates that have changed since last load.
    """

    def __init__(self, prompts_dir: str | Path | None = None) -> None:
        self._dir = Path(prompts_dir) if prompts_dir else DEFAULT_PROMPTS_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(self._dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._cache: dict[str, tuple[float, Template]] = {}

    def _get_template(self, template_path: str) -> Template:
        """Get template with hot-reload check."""
        full_path = self._dir / template_path
        if not full_path.exists():
            raise FileNotFoundError(f"Template not found: {full_path}")

        mtime = os.path.getmtime(full_path)

        if template_path in self._cache:
            cached_mtime, cached_template = self._cache[template_path]
            if cached_mtime == mtime:
                return cached_template

        logger.debug("Loading template: %s", template_path)
        template = self._env.get_template(template_path)
        self._cache[template_path] = (mtime, template)
        return template

    def render(self, template_path: str, **variables: Any) -> str:
        """Render a template with the given variables.

        Args:
            template_path: Relative path within prompts dir (e.g., "agents/warren_buffett.j2")
            **variables: Template variables (symbol, current_price, technicals, etc.)

        Returns:
            Rendered prompt string.
        """
        template = self._get_template(template_path)
        return template.render(**variables)

    def render_agent_prompt(
        self,
        agent_name: str,
        **variables: Any,
    ) -> str:
        """Render an agent prompt by name.

        Looks for template at agents/{agent_name}.j2
        """
        return self.render(f"agents/{agent_name}.j2", **variables)

    def render_debate_prompt(
        self,
        role: str,
        **variables: Any,
    ) -> str:
        """Render a debate prompt (bull_researcher, bear_researcher, research_manager)."""
        return self.render(f"debate/{role}.j2", **variables)

    def render_risk_prompt(
        self,
        perspective: str,
        **variables: Any,
    ) -> str:
        """Render a risk assessment prompt (aggressive, conservative, neutral, risk_manager)."""
        return self.render(f"risk/{perspective}.j2", **variables)

    def render_aggregation_prompt(self, **variables: Any) -> str:
        """Render the portfolio manager aggregation prompt."""
        return self.render("aggregation/portfolio_manager.j2", **variables)

    def list_templates(self, subdirectory: str = "") -> list[str]:
        """List available templates in a subdirectory."""
        search_dir = self._dir / subdirectory if subdirectory else self._dir
        if not search_dir.exists():
            return []
        return [
            str(p.relative_to(self._dir))
            for p in search_dir.rglob("*.j2")
        ]

    def clear_cache(self) -> None:
        """Force reload of all templates on next access."""
        self._cache.clear()
