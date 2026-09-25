# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, 'tools')
from script_budget import script_section
from script_render import messages

for f in sorted(os.listdir('work/dm')):
    if not f.endswith('.MDT'):
        continue
    a = open('work/dm/' + f, 'rb').read()
    b = open('work/build/' + f, 'rb').read()
    oa, la, _ = script_section(a)
    ob, lb, _ = script_section(b)
    ma = dict(messages(a[oa:oa + la]))
    mb = dict(messages(b[ob:ob + lb]))
    if set(ma) == set(mb):
        continue
    only_a = sorted(set(ma) - set(mb))
    only_b = sorted(set(mb) - set(ma))
    print('%s  원본 %d개 / 빌드 %d개' % (f, len(ma), len(mb)))
    for p in only_a:
        print('   원본에만 +0x%04X (%dB): %s' % (p, len(ma[p]), ma[p][:24].hex()))
    for p in only_b:
        print('   빌드에만 +0x%04X (%dB): %s' % (p, len(mb[p]), mb[p][:24].hex()))
