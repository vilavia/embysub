import re
import aiohttp
import logging
import base64
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, List, Union
from fnmatch import fnmatch
logger = logging.getLogger(__name__)

@dataclass
class SubscriptionStatus:
    success: bool = False
    token: Optional[str] = None
    expired_at: int = 0
    message: str = ""
    subscription_info: Optional[Dict] = None
    
    def fail(self, message: str) -> Tuple[bool, Optional[str], int, str]:
        self.message = message
        self.success = False
        return self.as_tuple()
    
    def succeed(self) -> Tuple[bool, Optional[str], int, str]:
        self.success = True
        return self.as_tuple()
    
    def as_tuple(self) -> Tuple[bool, Optional[str], int, str]:
        return self.success, self.token, self.expired_at, self.message

class SubscriptionValidator:
    def __init__(self, url: str, config: dict):
        self.url = url
        self.config = config
        self.status = SubscriptionStatus()
        self.current_timestamp = int(datetime.now().timestamp())
        self.headers = {'User-Agent': 'ClashforWindows/0.18.1'}

    async def validate(self) -> Tuple[bool, Optional[str], int, str]:
        try:
            # 验证订阅白名单和 token
            valid = await self._validate_domain_and_token()
            if not valid:
                return self.status.as_tuple()
            # 如果不需要验证内容，则直接返回
            if not self.config.get('validate_content', False):
                return self.status.as_tuple()
            return await self._validate_subscription_content()
        except Exception as e:
            logger.error(f"[subutil验证订阅]验证订阅时发生错误: {str(e)}")
            return self.status.fail("验证订阅时发生错误。")

    async def get_subscription_info(self) -> Optional[Dict]:
        """获取订阅信息"""
        try:
            if not self.url:
                return None

            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, headers=self.headers) as response:
                    if response.status != 200:
                        return None
                    
                    info = response.headers.get('subscription-userinfo', '')
                    if not info:
                        return None
                    # 解析subscription-userinfo
                    info_dict = {}
                    for item in info.split(';'):
                        if '=' in item:
                            key, value = item.strip().split('=')
                            info_dict[key] = value

                    upload = int(info_dict.get('upload', 0))
                    download = int(info_dict.get('download', 0))
                    total = int(info_dict.get('total', 0))
                    remain = int(total - download - upload)
                    # 格式化信息
                    result = {
                        'upload': StrOfSize(upload),
                        'download': StrOfSize(download),
                        'total': StrOfSize(total),
                        'remain': StrOfSize(remain),
                        'expire': 0
                    }

                    # 处理过期时间
                    if 'expire' in info_dict and info_dict['expire']:
                        result['expire'] = int(info_dict['expire'])
                    else:
                        result['expire'] = -1
                    return result

        except Exception as e:
            logger.error(f"[subutil获取订阅到期时间]获取订阅信息时发生错误: {str(e)}")
            return None

    async def _validate_domain_and_token(self) -> bool:
        parsed_url = urlparse(self.url)
        domain = parsed_url.netloc
        if 'allow_domains' in self.config:
            is_allowed = False
            for allowed_domain in self.config['allow_domains']:
                # 如果允许域名以*开头,则使用fnmatch进行通配符匹配
                if fnmatch(domain, allowed_domain):
                    is_allowed = True
                    break
                # 否则进行精确匹配
                elif domain == allowed_domain:
                    is_allowed = True
                    break
                elif domain in allowed_domain:
                    is_allowed = True
                    break
                # 如果域名是允许域名的子域名也算匹配
                elif domain.endswith('.' + allowed_domain):
                    is_allowed = True
                    break
            if not is_allowed:
                logger.warning(f"[subutil验证订阅域名]域名 {domain} 不在白名单中")
                self.status.fail("无效的订阅链接。")
                return False
        query_params = parse_qs(parsed_url.query)
        token_key = self.config.get('token_key', 'token')
        path_key = self.config.get('path_key', 's')
        self.status.token = query_params.get(token_key, [None])[0]
        if not self.status.token:
            # 从路径中获取token，例如 http://localhost:7001/token_key/xxx
            path_parts = parsed_url.path.strip('/').split('/')
            for i in range(len(path_parts) - 1):
                if path_parts[i] == path_key:
                    self.status.token = path_parts[i + 1]
                    logger.info(f"[subutil验证订阅域名]从路径中获取到token: {self.status.token}")
                    self.status.success = True
                    return True
            logger.warning("[subutil验证订阅域名]在订阅链接中未找到token参数")
            self.status.fail("无效的订阅链接。")
            return False
        self.status.success = True
        return True

    async def _validate_subscription_content(self) -> Tuple[bool, Optional[str], int, str]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, headers=self.headers) as res:
                    if res.status in (301, 302):
                        return await self._handle_redirect(session, res)
                    return await self._process_response(res)
        except Exception as e:
            logger.error(f"[subutil验证订阅内容]验证订阅时发生错误: {str(e)}")
            return self.status.fail("验证订阅时发生错误。")

    async def _handle_redirect(self, session: aiohttp.ClientSession, res: aiohttp.ClientResponse) -> Tuple[bool, Optional[str], int, str]:
        redirect_url = res.headers.get('location')
        if not redirect_url:
            logger.error("[subutil验证订阅内容]重定向URL不存在")
            return self.status.fail("无法获取订阅信息，请稍后重试。")
        
        async with session.get(redirect_url, headers=self.headers) as redirect_res:
            return await self._process_response(redirect_res)

    async def _process_response(self, res: aiohttp.ClientResponse) -> Tuple[bool, Optional[str], int, str]:
        if res.status != 200:
            logger.error(f"[subutil验证订阅内容]请求失败: {res.status}")
            return self.status.fail(f"无法获取订阅信息，请稍后重试。")

        # 处理 subscription-userinfo
        if not await self._process_subscription_info(res):
            return self.status.as_tuple()
        if self.config.get('validate_by_clash_user_agent', True):
            content = await res.text()
        else:
            success, content = await self.get_raw_subscription_content(False)
            if not success:
                logger.error("[subutil验证订阅内容]无法获取订阅内容")
                return self.status.fail("无法获取订阅内容，请稍后重试。")
            content = await self._decode_content(content)
        # 验证内容
        if not await self._validate_content(content):
            return self.status.as_tuple()

        return self.status.succeed()

    async def _process_subscription_info(self, res: aiohttp.ClientResponse) -> bool:
        info = res.headers.get('subscription-userinfo', '')
        info_num = re.findall('\d+', info)
        if len(info_num) >= 4:
            if info_num[3] and info_num[3].strip():
                self.status.expired_at = int(info_num[3])
                if self.status.expired_at <= self.current_timestamp:
                    logger.warning("[subutil验证订阅内容]订阅已过期")
                    self.status.fail("此订阅已过期。")
                    return False
            else:
                self.status.expired_at = -1
        else:
            self.status.expired_at = -1
            
        return True

    async def _validate_content(self, content: str) -> bool:
        # 验证必需关键词
        must_keywords = self.config.get('must_keywords', [])
        if must_keywords:
            missing_keywords = [kw for kw in must_keywords if kw not in content]
            if missing_keywords:
                logger.warning(f"[subutil验证订阅内容]套餐内容缺少必需关键词: {missing_keywords}")
                self.status.fail("无效的订阅内容。")
                return False

        # 验证限制关键词
        limit_keywords = self.config.get('limit_keywords', [])
        if limit_keywords:
            found_limits = [kw for kw in limit_keywords if kw in content]
            if found_limits:
                logger.warning(f"[subutil验证订阅内容]套餐内容包含限制关键词: {found_limits}")
                self.status.fail("无效的订阅内容。")
                return False

        # 验证过期时间
        if not await self._validate_expiry_date(content):
            return False

        return True

    async def _decode_content(self, content: str) -> str:
        """
        解码订阅内容
        
        Args:
            content: 原始订阅内容
            
        Returns:
            str: 解码后的内容
        """
        try:
            # 确保内容是字符串类型
            if isinstance(content, tuple) and len(content) > 0:
                content = str(content[0])
            else:
                content = str(content)
            # 移除可能的空白字符
            content = content.strip()
            # 添加必要的填充
            padding = 4 - len(content) % 4
            if padding < 4:
                content += "=" * padding
            
            # 尝试 base64 解码
            decoded_content = base64.b64decode(content).decode('utf-8')
            # URL 解码
            decoded_content = unquote(decoded_content)
            return decoded_content
        except Exception as e:
            logger.warning(f"[subutil验证订阅内容]解码内容失败，使用原始内容: {str(e)}")
            return str(content) if not isinstance(content, str) else content

    async def _validate_expiry_date(self, content: str) -> bool:
        expired_keyword = self.config.get('expired_at_keyword')
        if not expired_keyword or expired_keyword == '':
            return True

        if expired_keyword not in content:
            logger.warning(f"[subutil验证订阅内容]响应内容中未找到'{expired_keyword}'信息")
            self.status.fail("无效的订阅内容。")
            return False

        date_pattern = f'{expired_keyword}[：:]\s*(\d{{4}}-\d{{1,2}}-\d{{1,2}})'
        match = re.search(date_pattern, content)
        if not match:
            logger.warning("[subutil验证订阅内容]未找到有效的到期时间格式")
            self.status.fail("无效的订阅内容。")
            return False

        try:
            expire_date = datetime.strptime(match.group(1).strip(), '%Y-%m-%d')
            expire_date = expire_date.replace(hour=23, minute=59, second=59)
            self.status.expired_at = int(expire_date.timestamp())

            if self.status.expired_at <= self.current_timestamp:
                logger.warning("[subutil验证订阅内容]订阅已过期")
                self.status.fail("此订阅已过期。")
                return False
        except ValueError as e:
            logger.error(f"[subutil验证订阅内容]日期转换错误: {str(e)}")
            self.status.fail("无效的订阅内容。")
            return False

        return True

    async def get_raw_subscription_content(self, use_clash_header: bool = False) -> Tuple[bool, Optional[str]]:
        """
        获取订阅的原始内容，可选是否使用 Clash header
        Args:
            use_clash_header: 是否使用 Clash header
        Returns:
            Tuple[bool, Optional[str]]: (成功状态, 内容)
        """
        try:
            if not self.url:
                return False, None
            headers = self.headers if use_clash_header else {}
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"[subutil获取订阅内容]获取订阅内容失败，状态码: {response.status}")
                        return False, None
                    content = await response.text()
                    return True, content
        except Exception as e:
            logger.error(f"[subutil获取订阅内容]获取订阅内容时发生错误: {str(e)}")
            return False, None

async def verify_sub_content(url: str, config: dict) -> Tuple[bool, Optional[str], int, str]:
    validator = SubscriptionValidator(url, config)
    return await validator.validate()

def convert_time_to_str(ts):
    return str(ts).zfill(2)

def sec_to_data(y):
    h = int(y // 3600 % 24)
    d = int(y // 86400)
    h = convert_time_to_str(h)
    d = convert_time_to_str(d)
    return d + "天" + h + "小时"


def StrOfSize(size):
    def strofsize(integer, remainder, level):
        if integer >= 1024:
            remainder = integer % 1024
            integer //= 1024
            level += 1
            return strofsize(integer, remainder, level)
        elif integer < 0:
            integer = 0
            return strofsize(integer, remainder, level)
        else:
            return integer, remainder, level

    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    integer, remainder, level = strofsize(size, 0, 0)
    if level + 1 > len(units):
        level = -1
    return ('{}.{:>03d} {}'.format(integer, remainder, units[level]))

# 提供一个便捷的函数用于获取订阅信息
async def get_subscription_info(url: str) -> Optional[Dict]:
    validator = SubscriptionValidator(url, {})
    return await validator.get_subscription_info()
