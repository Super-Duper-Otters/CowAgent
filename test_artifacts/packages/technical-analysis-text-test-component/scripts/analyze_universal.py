# encoding:utf-8
import json
import sys


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}

    target = str(payload.get("target_text") or "").strip() or "未提供标的"
    raw_input = str(payload.get("raw_input") or "").strip()
    reply_text = "\n".join(
        [
            "【技术分析组件更新测试】",
            "当前执行的是上传后的文本测试组件。",
            f"目标标的：{target}",
            f"原始输入：{raw_input}",
            "测试结论：AI 和图片渲染链路已被此测试组件绕过，仅返回固定文本。",
        ]
    )

    print(
        json.dumps(
            {
                "success": True,
                "reply_text": reply_text,
                "output_files": [],
                "detail": "technical-analysis text component smoke test",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
