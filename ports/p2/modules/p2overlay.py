"""Run cooperating .mpy stages from VFS with at most one imported stage at a time."""
import gc
import sys


class Program:
    """Each stage exports run(state). Return ordinary state, without module references."""

    def __init__(self, directory, stages):
        if not directory.startswith("/") or not stages:
            raise ValueError("absolute directory and stage names required")
        self.directory = directory
        self.stages = tuple(stages)
        for name in self.stages:
            allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
            if not name or any(ch not in allowed for ch in name) or name[0] in "0123456789":
                raise ValueError("invalid module name")

    def run(self, state):
        sys.path.insert(0, self.directory)
        try:
            for name in self.stages:
                if name in sys.modules:
                    raise ValueError("stage name already imported")
                module = None
                try:
                    module = __import__(name)
                    state = module.run(state)
                finally:
                    sys.modules.pop(name, None)
                    module = None
                    gc.collect()
            return state
        finally:
            sys.path.remove(self.directory)
