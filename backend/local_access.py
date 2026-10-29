import ipaddress
import os
from urllib.parse import urlsplit


def loopback(value):
    try:return ipaddress.ip_address(value).is_loopback
    except ValueError:return False


def origin_key(value):
    parsed=urlsplit(value)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError('Invalid origin')
    if parsed.path not in ('','/') or parsed.query or parsed.fragment:raise ValueError('Invalid origin path')
    return parsed.scheme,parsed.hostname.lower(),parsed.port or (443 if parsed.scheme=='https' else 80)


def remote_access_enabled():
    return os.getenv('CAD_ALLOW_REMOTE','0').lower() in ('1','true','yes') or os.getenv('PUBLIC_ACCESS','0').lower() in ('1','true','yes')


def denial(request):
    peer=request.client.host if request.client else ''
    allow_remote=remote_access_enabled()
    if not allow_remote and peer!='testclient' and not loopback(peer):
        return 'Website hiện chỉ phục vụ trên máy này; chưa bật truy cập mạng nội bộ có đăng nhập.'
    try:
        expected=origin_key(str(request.base_url))
        host=expected[1]
        if not allow_remote and host!='localhost' and not loopback(host) and not (peer=='testclient' and host=='testserver'):
            return 'Địa chỉ website không thuộc máy chủ CAD cục bộ.'
        supplied=request.headers.get('origin')
        if supplied is not None:
            s_scheme,s_host,s_port=origin_key(supplied)
            e_scheme,e_host,e_port=expected
            if s_host!=e_host:
                return 'Không cho website khác truy cập dữ liệu hoặc thực thi thao tác CAD.'
    except ValueError:return 'Nguồn truy cập hoặc địa chỉ website không hợp lệ.'
    return None
