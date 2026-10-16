# -*- coding: utf-8 -*-
"""安全中间件：视频域名白名单校验 / 内容审核 / 防刷限制 / 内置人机验证。

三个开关都在 config.py 里，由部署面板可视化控制，关闭后对应检查直接放行。
"""
import random
import re
from urllib.parse import urlparse

from config import Config as CFG
from models import execute, ip_hash as _ip_hash, now, query_one

# --------------------------------------------------------------------------- #
# 1. 视频域名白名单
# --------------------------------------------------------------------------- #
_DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?)+$")


def normalize_domain(value):
    """把用户输入或 URL 归一成裸域名。"""
    v = (value or "").strip().lower()
    if not v:
        return ""
    if "://" in v:
        v = urlparse(v).netloc or v
    v = v.split("/")[0].split("?")[0].split("#")[0]
    if v.startswith("www."):
        v = v[4:]
    return v.split(":")[0]


def allowlist():
    return [normalize_domain(d) for d in CFG.load_allowlist_from_db() if d]


def domain_allowed(domain, allowed=None):
    """支持子域名匹配：channels.weixin.qq.com 命中 weixin.qq.com 时也算通过。"""
    domain = normalize_domain(domain)
    if not domain:
        return False, ""
    allowed = allowed if allowed is not None else allowlist()
    for a in allowed:
        if domain == a or domain.endswith("." + a):
            return True, a
    return False, ""


def check_video_url(url, allowed=None):
    """校验视频链接；返回 (ok, message, domain)。"""
    if not url or not str(url).strip():
        return True, "未填写视频链接", ""
    raw = str(url).strip()
    parsed = urlparse(raw if "://" in raw else "http://" + raw)
    if parsed.scheme not in ("http", "https", ""):
        return False, "只允许 http/https 链接", ""
    domain = normalize_domain(parsed.netloc)
    if not _DOMAIN_RE.match(domain or ""):
        return False, "链接域名不合法：%s" % domain, domain
    ok, hit = domain_allowed(domain, allowed)
    if not ok:
        return False, "该域名不在视频白名单内：%s（允许：%s）" % (
            domain, "、".join(allowed or allowlist())), domain
    return True, "链接已通过白名单校验（命中 %s）" % hit, domain


# --------------------------------------------------------------------------- #
# 2. 内容标记（只提示，不拦截）
# --------------------------------------------------------------------------- #
_HIGH_RISK_WORDS = ("刷单", "博彩", "赌博", "贷款", "套现", "代开发票")
_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
_CONTACT_RE = re.compile(r"(?i)(微信|weixin|wechat|qq|vx|wx)\s*[:：]?\s*[a-zA-Z0-9_\-]{5,}")
_URL_RE = re.compile(r"(?i)https?://[^\s]+")


def review_text(text, extra_words=None):
    """返回 (flagged, detail)。

    只做标记：站点不设人工审核，任何内容都会直接发布，
    命中敏感词时记一条流水并在提交结果里提示，不做拦截。
    """
    if not CFG.ENABLE_CONTENT_REVIEW:
        return False, "内容标记已关闭"
    body = str(text or "")
    for w in list(CFG.REVIEW_BLOCK_WORDS) + list(extra_words or []):
        if w and w in body:
            if w in _HIGH_RISK_WORDS:
                return True, "含高危词：%s（已记录，内容照常发布）" % w
            return True, "含敏感词：%s（已记录，内容照常发布）" % w
    if _PHONE_RE.search(body):
        return True, "疑似包含手机号（已记录，内容照常发布）"
    if _CONTACT_RE.search(body):
        return True, "疑似包含联系方式（已记录，内容照常发布）"
    if len(_URL_RE.findall(body)) > 2:
        return True, "正文含多个外链（已记录，内容照常发布）"
    return False, "未命中标记规则"


def log_review(report_id, rule, action, detail):
    try:
        execute("INSERT INTO review_log (report_id, rule, action, detail, created_at) "
                "VALUES (?,?,?,?,?)", (report_id, rule, action, detail, now()))
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# 3. 防刷限制
# --------------------------------------------------------------------------- #
def _window_key(seconds=60):
    import time
    return time.strftime("%Y-%m-%dT%H:%M", time.localtime())


def rate_limit_check(ip, limit=None):
    """返回 (ok, message, hits)。"""
    if not CFG.ENABLE_RATE_LIMIT:
        return True, "防刷限制已关闭", 0
    limit = int(limit or CFG.RATE_LIMIT_PER_MIN)
    h = _ip_hash(ip)
    key = _window_key()
    row = query_one("SELECT id, hits FROM rate_limit WHERE ip_hash=? AND window_key=?", (h, key))
    hits = (row["hits"] if row else 0) + 1
    if row:
        execute("UPDATE rate_limit SET hits=?, updated_at=? WHERE id=?", (hits, now(), row["id"]))
    else:
        execute("INSERT INTO rate_limit (ip_hash, window_key, hits, updated_at) VALUES (?,?,?,?)",
                (h, key, hits, now()))
    if hits > limit:
        return False, "提交过于频繁（本分钟第 %d 次，上限 %d）" % (hits, limit), hits
    return True, "频率正常（%d/%d）" % (hits, limit), hits


# --------------------------------------------------------------------------- #
# 4. 内置人机验证（算术题，答案存 session）
# --------------------------------------------------------------------------- #
def make_captcha():
    """生成算术题；返回 (题面, 答案)。"""
    a = random.randint(3, 19)
    b = random.randint(2, 9)
    op = random.choice(["+", "-", "×"])
    if op == "+":
        ans = a + b
    elif op == "-":
        if b > a:
            a, b = b, a
        ans = a - b
    else:
        b = random.randint(2, 9)
        ans = a * b
    return "%d %s %d = ?" % (a, op, b), ans


def verify_captcha(session, answer):
    if not CFG.ENABLE_CAPTCHA:
        return True, "人机验证已关闭"
    expect = session.get("captcha_answer")
    if expect is None:
        return False, "验证码已过期，请点击刷新"
    try:
        got = int(str(answer).strip())
    except (TypeError, ValueError):
        return False, "请输入数字答案"
    if got != int(expect):
        session.pop("captcha_answer", None)
        return False, "答案不正确，请重新作答"
    session.pop("captcha_answer", None)
    return True, "验证通过"


# --------------------------------------------------------------------------- #
# 提交前的统一检查：人机验证（挡机器人）+ 链接平台限制 + 内容标记（只记录）
# --------------------------------------------------------------------------- #
def pre_submit(session, ip, form):
    """返回 (ok, payload, messages)。站点不设人工审核，验证通过即直接发布。"""
    messages = []
    ok_captcha, msg = verify_captcha(session, form.get("captcha"))
    messages.append({"step": "人机验证", "ok": ok_captcha, "detail": msg})
    if not ok_captcha:
        return False, {}, messages

    url = form.get("video_url", "")
    if url and str(url).strip():
        ok_url, url_detail, domain = check_video_url(url)
        messages.append({"step": "链接平台", "ok": ok_url, "detail": url_detail})
        if not ok_url:
            return False, {}, messages

    text = "%s %s" % (form.get("title", ""), form.get("content", ""))
    flagged, detail = review_text(text)
    messages.append({"step": "内容标记", "ok": True,
                     "detail": detail + ("（仅记录，不拦截）" if flagged else "")})
    return True, {"status": "approved", "flagged": flagged, "review": detail}, messages
