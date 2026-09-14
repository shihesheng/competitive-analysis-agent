"""Orchestration layer for the LangGraph workflow.

This package wires the multi-agent DAG together. It contains:

- ``workflow.py``: the LangGraph graph (nodes, edges, routing) and the resilient runner hookup.
- ``state.py``: the shared ``CompetitiveAnalysisState`` and its merge reducers.
- ``industry_config.py``: industry presets (competitors, dimensions, data sources).

The agent node *implementations* live in ``app/agents``. Keeping orchestration and
node logic in separate packages avoids the duplicate, identically named stub files that
previously existed here.
"""
