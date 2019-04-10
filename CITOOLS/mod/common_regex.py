import re


int_firstline_reg = re.compile(r'<(.*?)>\s+on\s+<(.*?)>\s+of\s+<(.*?)>\s+topic\s+<(.*?)>', re.DOTALL)
