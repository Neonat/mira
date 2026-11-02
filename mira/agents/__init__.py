"""Agent roles owned by the orchestrator: planner, analyst and writer (PRD v2 §5.2).

Each role is one prompt plus code checks on what the model returns. Models see
short labels only; every label they cite is resolved through a ``LabelMap``.
"""
