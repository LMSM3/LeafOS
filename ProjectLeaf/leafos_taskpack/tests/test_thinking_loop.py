import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = ROOT / "core" / "runtime" / "thinking_loop.py"
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("thinking_loop", MODULE)
thinking_loop = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = thinking_loop
SPEC.loader.exec_module(thinking_loop)


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        self.value += 0.1
        return self.value


class ThinkingLoopTests(unittest.TestCase):
    def test_unmarked_text_is_retained_as_thinking(self):
        engine = thinking_loop.ThinkingLoopEngine("run-1", clock=Clock())
        event = engine.feed("plain response text")
        result = engine.finalize()
        self.assertEqual("thinking", event.phase)
        self.assertEqual(3, result["total_tokens"])
        self.assertEqual("thinking", result["phases"][0]["phase"])

    def test_thinking_to_action_boundary(self):
        engine = thinking_loop.ThinkingLoopEngine("run-2", clock=Clock())
        engine.feed("<think>consider options")
        event = engine.feed("</think><action>run validator")
        phases = {item["phase"] for item in engine.finalize()["phases"]}
        self.assertEqual("acting", event.phase)
        self.assertEqual({"thinking", "acting"}, phases)

    def test_thinking_code_error_timeline(self):
        observed = []
        engine = thinking_loop.ThinkingLoopEngine("run-3", clock=Clock(), on_event=observed.append)
        engine.feed("[THOUGHT] choose implementation")
        engine.feed("[CODE] int main(void) {}")
        engine.feed("[ERROR] compiler failed")
        result = engine.finalize()
        self.assertEqual(["thinking", "coding", "error"], [item.phase for item in observed])
        self.assertEqual(3, len(result["phases"]))
        self.assertTrue(all(len(item["text_sha256"]) == 64 for item in result["phases"]))

    def test_multiple_markers_in_one_chunk_drop_no_text(self):
        engine = thinking_loop.ThinkingLoopEngine("run-4", clock=Clock())
        engine.feed("<think>one</think><action>two</action>three")
        result = engine.finalize()
        self.assertEqual(3, result["total_tokens"])
        self.assertEqual(3, sum(item["event_count"] for item in result["phases"]))


if __name__ == "__main__":
    unittest.main()
