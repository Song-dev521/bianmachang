# -*- coding: utf-8 -*-
"""prompts 模块测试：Skill 注册表、prompt 读取与输出格式适配层。"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import prompts


class SkillMetaTest(unittest.TestCase):
    def test_review_skill_order_and_meta_shape(self):
        meta = prompts.all_skill_meta()

        self.assertEqual(
            [item["key"] for item in meta],
            ["security", "performance", "architecture", "standard"],
        )
        self.assertEqual(
            [item["name"] for item in meta],
            ["安全评审", "性能评审", "架构评审", "规范评审"],
        )
        self.assertEqual(
            [item["short"] for item in meta], ["安全", "性能", "架构", "规范"]
        )
        for item in meta:
            self.assertEqual(set(item), {"key", "name", "short"})

    def test_conflict_skill_metadata(self):
        self.assertEqual(prompts.CONFLICT_SKILL["key"], "conflict")
        self.assertEqual(prompts.CONFLICT_SKILL["name"], "冲突汇总")
        self.assertEqual(prompts.CONFLICT_SKILL["prompt_file"], "conflict-summary/prompt.md")


class PromptLoadingTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        patcher = mock.patch.object(prompts, "SKILLS_DIR", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_system_prompt_appends_level_hint_without_touching_source(self):
        source = "# 安全评审\n原始 prompt 正文"
        self._write("security-review/prompt.md", source)

        prompt = prompts.system_prompt(prompts.REVIEW_SKILLS[0])

        self.assertTrue(prompt.startswith(source))
        self.assertIn("【输出格式（必须遵守）】", prompt)
        self.assertIn("LEVEL: <低|中|高>", prompt)
        self.assertEqual(prompt, source + prompts.LEVEL_HINT)

    def test_conflict_prompt_returns_raw_file_content(self):
        source = "# 冲突汇总\n原始汇总 prompt"
        self._write("conflict-summary/prompt.md", source)

        self.assertEqual(prompts.conflict_prompt(), source)

    def test_missing_skill_prompt_raises_with_path(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            prompts.system_prompt(prompts.REVIEW_SKILLS[0])

        message = str(ctx.exception)
        self.assertIn("找不到 Skill prompt", message)
        self.assertIn("security-review", message)
        self.assertIn("prompt.md", message)

    def test_missing_conflict_prompt_raises(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            prompts.conflict_prompt()

        self.assertIn("conflict-summary", str(ctx.exception))
        self.assertIn("prompt.md", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)