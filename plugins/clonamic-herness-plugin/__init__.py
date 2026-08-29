from pathlib import Path


SKILLS = (
    "clonamic-write-control",
    "clonamic-completion-check",
    "clonamic-report",
    "clonamic-executors",
)


def register(ctx):
    plugin_root = Path(__file__).resolve().parent
    for name in SKILLS:
        ctx.register_skill(name, str(plugin_root / "skills" / name))
