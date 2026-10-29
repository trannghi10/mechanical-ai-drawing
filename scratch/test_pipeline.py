# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.abspath('.'))

from backend.services.sheet_thickness_planner import command

req1 = 'Tất cả vật liệu sắt tấm cắt lazer đổi từ 1.5 mm thành 1mm'
print('Without code:', command(req1))

req2 = 'Mã 8.1.05417.258: Tất cả vật liệu sắt tấm cắt lazer đổi từ 1.5 mm thành 1mm'
print('With code:', command(req2))
