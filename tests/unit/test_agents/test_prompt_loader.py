"""Tests for prompt template loader."""

import pytest
from pathlib import Path

from nexustrade.agents.prompt_loader import PromptLoader


PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "config" / "prompts"


class TestPromptLoader:
    def test_load_agent_template(self):
        loader = PromptLoader(PROMPTS_DIR)
        prompt = loader.render_agent_prompt(
            "warren_buffett",
            symbol="AAPL",
            current_price=185.50,
            technicals=None,
            fundamentals={},
            news=[],
        )
        assert "AAPL" in prompt
        assert "185.5" in prompt

    def test_load_debate_template(self):
        loader = PromptLoader(PROMPTS_DIR)
        prompt = loader.render_debate_prompt(
            "bull_researcher",
            symbol="AAPL",
            current_price=185.0,
            technicals=None,
            fundamentals={},
            news=[],
            prior_arguments=None,
        )
        assert "AAPL" in prompt

    def test_load_risk_template(self):
        loader = PromptLoader(PROMPTS_DIR)
        prompt = loader.render_risk_prompt(
            "aggressive",
            symbol="AAPL",
            signal_direction="buy",
            signal_confidence=0.8,
            position_size=100,
            current_price=185.0,
            portfolio_value=100000,
            num_positions=3,
        )
        assert "AAPL" in prompt

    def test_list_templates(self):
        loader = PromptLoader(PROMPTS_DIR)
        templates = loader.list_templates("agents")
        assert len(templates) >= 3
        assert any("warren_buffett" in t for t in templates)

    def test_missing_template_raises(self):
        loader = PromptLoader(PROMPTS_DIR)
        with pytest.raises(FileNotFoundError):
            loader.render("nonexistent/template.j2")

    def test_hot_reload(self, tmp_path):
        # Create a template
        template_file = tmp_path / "test.j2"
        template_file.write_text("Hello {{ name }}!")

        loader = PromptLoader(tmp_path)
        result1 = loader.render("test.j2", name="World")
        assert result1 == "Hello World!"

        # Modify template
        import time
        time.sleep(0.1)  # Ensure different mtime
        template_file.write_text("Hi {{ name }}!")

        # Clear Jinja2 internal cache
        loader._env = __import__("jinja2").Environment(
            loader=__import__("jinja2").FileSystemLoader(str(tmp_path)),
            autoescape=False, trim_blocks=True, lstrip_blocks=True,
        )
        loader.clear_cache()

        result2 = loader.render("test.j2", name="World")
        assert result2 == "Hi World!"

    def test_render_aggregation(self):
        loader = PromptLoader(PROMPTS_DIR)
        prompt = loader.render_aggregation_prompt(
            symbol="AAPL",
            current_price=185.0,
            signals=[],
            portfolio=type("P", (), {
                "cash": 50000, "total_value": 100000,
                "positions": [], "daily_pnl": 0,
            })(),
        )
        assert "AAPL" in prompt
