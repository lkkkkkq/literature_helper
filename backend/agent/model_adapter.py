"""OpenAI-compatible transport. Credentials live only in request memory."""

import json
from urllib.parse import urlsplit

import httpx

from backend.core.errors import DomainError


class CompatibleModel:
    def complete(self, profile, key, messages):
        if not key:
            raise DomainError("请先在模型设置中保存 API Key。")
        payload = {
            "model": profile["model"],
            "messages": messages,
            "response_format": {"type": "json_object"},
            "max_tokens": 8192,
            "stream": False,
        }
        # DeepSeek's current models enable thinking by default. Structured
        # extraction must not spend its entire output budget on hidden reasoning.
        if urlsplit(profile["base_url"]).hostname == "api.deepseek.com" and profile["model"] in {
            "deepseek-flash",
            "deepseek-v4-flash",
            "deepseek-v4-pro",
            "deepseek-chat",
        }:
            payload["thinking"] = {"type": "disabled"}
            payload["max_tokens"] = 65536
        output_limit = payload["max_tokens"]
        response_limit = 8_000_000 if output_limit > 8192 else 2_000_000
        read_timeout = 600 if output_limit > 8192 else 180
        try:
            with httpx.Client(
                timeout=httpx.Timeout(read_timeout, connect=15),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                with client.stream(
                    "POST",
                    profile["base_url"].rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json=payload,
                ) as response:
                    if response.status_code >= 300:
                        raise DomainError(
                            f"模型服务请求失败（HTTP {response.status_code}），"
                            "请检查接口、密钥、额度或稍后重试。"
                        )
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > response_limit:
                            raise DomainError("模型返回内容过大，请缩小任务范围。")
            body = json.loads(data)
            choice = body["choices"][0]
            reason = choice.get("finish_reason")
            if reason == "length":
                raise DomainError(
                    f"模型输出或上下文达到长度上限（finish_reason=length，"
                    f"本次输出预算 {output_limit} tokens），"
                    "未保存截断结果，未自动重试。"
                )
            if reason == "content_filter":
                raise DomainError("模型服务拦截了回答（content_filter），未保存结果。")
            if reason == "insufficient_system_resource":
                raise DomainError("模型服务资源不足，回答被中断，请稍后重试。")
            if reason != "stop":
                raise DomainError("模型未返回正常结束状态，未保存结果；请检查模型接口兼容性。")
            content = choice["message"]["content"]
            if key and key in content:
                raise DomainError("模型返回异常敏感内容，已拒绝保存。")
            return json.loads(content)
        except httpx.TimeoutException as error:
            raise DomainError("模型响应超时，未保存不完整回答，请重试。") from error
        except httpx.HTTPError as error:
            raise DomainError("无法连接模型服务，请检查网络与接口地址。") from error
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise DomainError("模型没有返回有效的结构化回答，请重试。") from error
