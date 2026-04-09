"""Agent executor for running analysis agents in different modes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nexustrade.core.interfaces import AgentInterface
from nexustrade.core.models import AgentSignal, MarketContext

logger = logging.getLogger(__name__)


class AgentExecutor:
    """Executes a list of agents against a MarketContext.

    Supports 3 execution modes:
    - parallel: Run all agents concurrently with asyncio.gather().
    - sequential: Run agents one by one, updating context.recent_signals.
    - dag: Dependency-based execution using agent capabilities.
    """

    VALID_MODES = ("parallel", "sequential", "dag")

    def __init__(self, mode: str = "parallel") -> None:
        if mode not in self.VALID_MODES:
            raise ValueError(
                f"Invalid execution mode '{mode}'. "
                f"Must be one of {self.VALID_MODES}"
            )
        self.mode = mode
        self.skip_on_sell: bool = True  # For DAG mode: skip dependents if dep returned SELL

    async def execute(
        self,
        agents: list[AgentInterface],
        context: MarketContext,
    ) -> list[AgentSignal]:
        """Execute agents and return their signals."""
        method = getattr(self, f"_execute_{self.mode}")
        return await method(agents, context)

    async def _execute_parallel(
        self,
        agents: list[AgentInterface],
        context: MarketContext,
    ) -> list[AgentSignal]:
        """Run all agents concurrently."""
        tasks = [self._safe_analyze(agent, context) for agent in agents]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]

    async def _execute_sequential(
        self,
        agents: list[AgentInterface],
        context: MarketContext,
    ) -> list[AgentSignal]:
        """Run agents one by one, updating recent_signals after each."""
        signals: list[AgentSignal] = []
        for agent in agents:
            # Update context with signals from prior agents
            context.recent_signals = list(signals)
            result = await self._safe_analyze(agent, context)
            if result is not None:
                signals.append(result)
        return signals

    async def _execute_dag(
        self,
        agents: list[AgentInterface],
        context: MarketContext,
    ) -> list[AgentSignal]:
        """Dependency-based execution.

        Each agent may declare ``depends_on`` in its capabilities dict.
        Agents without dependencies run first. If a dependency returned
        SELL (or STRONG_SELL) and skip_on_sell is True, dependent agents
        are skipped.
        """
        from nexustrade.core.models import SignalDirection

        # Build dependency graph
        agent_map: dict[str, AgentInterface] = {a.name: a for a in agents}
        deps: dict[str, list[str]] = {}
        for agent in agents:
            caps = agent.get_capabilities()
            depends_on = caps.get("depends_on", [])
            deps[agent.name] = depends_on

        # Topological sort (Kahn's algorithm)
        in_degree: dict[str, int] = {name: 0 for name in agent_map}
        dependents: dict[str, list[str]] = {name: [] for name in agent_map}
        for name, dep_list in deps.items():
            for dep in dep_list:
                if dep in agent_map:
                    in_degree[name] += 1
                    dependents[dep].append(name)

        # Queue starts with agents that have no dependencies
        ready: list[str] = [
            name for name, degree in in_degree.items() if degree == 0
        ]
        signals: list[AgentSignal] = []
        results_by_name: dict[str, AgentSignal] = {}
        skipped: set[str] = set()

        while ready:
            # Run all ready agents concurrently
            current_agents = [agent_map[name] for name in ready if name not in skipped]
            if current_agents:
                tasks = [self._safe_analyze(a, context) for a in current_agents]
                batch_results = await asyncio.gather(*tasks)
                for agent, result in zip(current_agents, batch_results):
                    if result is not None:
                        signals.append(result)
                        results_by_name[agent.name] = result

            # Process next level
            next_ready: list[str] = []
            for name in ready:
                for dependent in dependents.get(name, []):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        # Check if we should skip this dependent
                        should_skip = False
                        if self.skip_on_sell:
                            for dep_name in deps[dependent]:
                                dep_result = results_by_name.get(dep_name)
                                if dep_result and dep_result.direction in (
                                    SignalDirection.SELL,
                                    SignalDirection.STRONG_SELL,
                                ):
                                    should_skip = True
                                    logger.info(
                                        "Skipping agent '%s' because dependency "
                                        "'%s' returned %s",
                                        dependent,
                                        dep_name,
                                        dep_result.direction.value,
                                    )
                                    break
                        if should_skip:
                            skipped.add(dependent)
                        next_ready.append(dependent)

            ready = next_ready

        return signals

    async def _safe_analyze(
        self,
        agent: AgentInterface,
        context: MarketContext,
    ) -> AgentSignal | None:
        """Run a single agent, catching and logging any errors."""
        try:
            return await agent.analyze(context)
        except Exception:
            logger.exception("Agent '%s' failed during analysis", agent.name)
            return None
