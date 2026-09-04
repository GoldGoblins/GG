#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from backend import web_operator as op


class WebOperatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(
            prefix="gg-web-op-",
            dir=Path("/run/user") / str(os.getuid()),
        )
        self.saved = op.ROOT
        op.ROOT = Path(self.tmp.name)

    def tearDown(self) -> None:
        op.ROOT = self.saved
        self.tmp.cleanup()

    def test_open_goldgoblins_is_yellow_visible(self) -> None:
        cmd = op.make_command("OPEN", url="goldgoblins.se")
        self.assertEqual(cmd["url"], "https://goldgoblins.se")
        self.assertEqual(cmd["risk_class"], "YELLOW")
        self.assertEqual(cmd["general_action_authority"], "NONE")

    def test_one_com_is_red_password_blocked(self) -> None:
        cmd = op.make_command("OPEN", url="https://www.one.com/login")
        self.assertEqual(cmd["risk_class"], "RED")
        with self.assertRaises(op.WebOperatorError) as exc:
            op.make_command("TYPE", selector="#password", text="secret")
        self.assertIn("PASSWORD_FIELD_FORBIDDEN", str(exc.exception))
        with self.assertRaises(op.WebOperatorError):
            op.make_command("TYPE", selector="input[type=password]", text="x")

    def test_javascript_url_rejected(self) -> None:
        with self.assertRaises(op.WebOperatorError):
            op.make_command("OPEN", url="javascript:alert(1)")
        with self.assertRaises(op.WebOperatorError):
            op.make_command("CLICK", selector="javascript:foo")

    def test_click_type_reload_helpers_exist(self) -> None:
        click = op.make_command("CLICK", selector="a.cta")
        self.assertEqual(click["action"], "CLICK")
        typed = op.make_command("TYPE", selector="#q", text="lidkoping")
        self.assertEqual(typed["action"], "TYPE")
        self.assertEqual(op.make_command("RELOAD")["action"], "RELOAD")
        self.assertEqual(op.make_command("BACK")["action"], "BACK")
        self.assertTrue(callable(op.click))
        self.assertTrue(callable(op.type_text))
        self.assertTrue(callable(op.reload_page))
        self.assertTrue(callable(op.go_back))

    def test_take_and_result_roundtrip(self) -> None:
        cmd = op.make_command("SNAPSHOT")
        op.ensure_root()
        path = op.ROOT / op.COMMAND_NAME
        path.write_text(json.dumps(cmd), encoding="utf-8")
        taken = op.take_command()
        self.assertIsNotNone(taken)
        assert taken is not None
        self.assertEqual(taken["command_id"], cmd["command_id"])
        result = op.make_result(
            taken,
            ok=True,
            reason_code="SNAPSHOT",
            url="https://goldgoblins.se/",
            title="Gold Goblins",
            text="hello",
        )
        self.assertTrue(result["visible_web_tab"])
        op.write_result(result)
        stored = json.loads((op.ROOT / op.RESULT_NAME).read_text(encoding="utf-8"))
        self.assertEqual(stored["reason_code"], "SNAPSHOT")
        self.assertFalse((op.ROOT / op.ACTIVE_NAME).exists())


if __name__ == "__main__":
    unittest.main()
