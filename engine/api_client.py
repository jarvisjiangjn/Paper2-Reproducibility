"""OpenAI-compatible API request helper used by the Paper 2 revision methods.

Implements the model request protocol used by the Paper 2 revision methods.
"""
from __future__ import annotations
import json
import random
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

class APIStop(RuntimeError):
    """认证、余额或配置错误：停止整批实验，避免产生大量失败记录。"""


class APIRetryExhausted(RuntimeError):
    """暂时性错误已经用尽重试次数。"""


def request_sql(question: str, ddl: str, model: str, url: str, keys: list[str], slot: int,
                timeout: float, retries: int, *, sleep=None, jitter=None, request=None,
                max_wait: float = 120) -> str:
    """兼容 OpenAI Chat API；区分永久错误与临时错误，尊重 Retry-After。"""
    import email.utils
    import datetime
    sleep = sleep or time.sleep
    jitter = jitter or random.uniform
    request = request or urlopen
    if not keys:
        raise APIStop('缺少 API 密钥，请设置 PAPER2_API_KEY 或 PAPER2_API_KEYS')
    prompt = ('你是 Text-to-SQL 生成器。只输出一条只读 SELECT SQL，不输出 Markdown 或解释。'
              '数据库结构如下：\n'+ddl+'\n用户问题：\n'+question)
    payload = json.dumps({'model':model,'temperature':0,'messages':[{'role':'user','content':prompt}]}).encode()
    bad_keys = set()
    for attempt in range(retries+1):
        available = [i for i in range(len(keys)) if i not in bad_keys]
        if not available:
            raise APIStop('全部 API Key 均不可用；检查认证、余额和模型权限')
        key_index = available[(slot+attempt) % len(available)]
        req = Request(url.rstrip('/')+'/chat/completions', data=payload,
                      headers={'Authorization':'Bearer '+keys[key_index],'Content-Type':'application/json'})
        delay = min(max_wait, 2 ** attempt + jitter(0,1))
        try:
            with request(req, timeout=timeout) as response:
                result = json.load(response)
            text = result['choices'][0]['message']['content'].strip()
            if text.startswith('```'):
                text = text.split('\n',1)[-1].rsplit('```',1)[0].strip()
                if text.lower().startswith('sql\n'):
                    text = text[4:].strip()
            if not text:
                raise ValueError('模型返回空内容')
            return text
        except HTTPError as exc:
            if exc.code in {401,403}:
                bad_keys.add(key_index)
                if len(bad_keys)==len(keys):
                    raise APIStop('全部 API Key 认证或权限失败') from None
                continue
            if exc.code in {400,402,404,413,422}:
                raise APIStop(f'API HTTP {exc.code}：检查余额、模型、接口和请求参数') from None
            if exc.code not in {408,409,425,429,500,502,503,504}:
                raise APIStop(f'API HTTP {exc.code}：非可重试错误') from None
            retry_after = exc.headers.get('Retry-After') if exc.headers else None
            if retry_after:
                try:
                    delay = max(0,float(retry_after))
                except ValueError:
                    try:
                        when=email.utils.parsedate_to_datetime(retry_after)
                        delay=max(0,(when-datetime.datetime.now(datetime.timezone.utc)).total_seconds())
                    except (TypeError,ValueError,OverflowError):
                        pass
                delay=min(max_wait,delay)
        except (URLError, TimeoutError, OSError):
            pass
        if attempt < retries:
            sleep(delay)
    raise APIRetryExhausted('临时错误重试耗尽；可使用 retry-failed 补跑')

